"""Interaction checks for miles-per-day, with all search and routing services faked."""

import functools
import json
import re
from collections import Counter
from datetime import date, timedelta
from urllib.parse import parse_qs, urlsplit

import pytest
from playwright.sync_api import Page, Route, expect

SERVICES = {
    "nominatim": "https://nominatim.openstreetmap.org/**",
    "photon": "https://photon.komoot.io/**",
    "openmeteo": "https://geocoding-api.open-meteo.com/**",
    "osrm": "https://router.project-osrm.org/**",
    "osrm_fossgis": "https://routing.openstreetmap.de/**",
    "valhalla": "https://valhalla1.openstreetmap.de/**",
}
CORS = {"Access-Control-Allow-Origin": "*"}

PLACES = {  # query keyword -> (lat, lon), display name; anything else is Alice Springs
    "darwin": ((-12.46, 130.84), "Darwin, NT"),
    "katherine": ((-14.47, 132.26), "Katherine, NT"),
    "tennant": ((-19.65, 134.19), "Tennant Creek, NT"),
}
ALICE = ((-23.70, 133.88), "Alice Springs, NT")
ROUTE_METERS = 1_609_344  # exactly 1000 miles, whatever the stops
ROUTE_SECONDS = 36_000  # 10 hours


def encode_polyline6(points: list[tuple[float, float]]) -> str:
    out, prev = [], (0, 0)
    for lat, lon in points:
        cur = (round(lat * 1e6), round(lon * 1e6))
        for delta in (cur[0] - prev[0], cur[1] - prev[1]):
            v = ~(delta << 1) if delta < 0 else delta << 1
            while v >= 0x20:
                out.append(chr((0x20 | (v & 0x1F)) + 63))
                v >>= 5
            out.append(chr(v + 63))
        prev = cur
    return "".join(out)


def place_for(query: str) -> tuple[tuple[float, float], str]:
    return next((v for k, v in PLACES.items() if k in query.lower()), ALICE)


def route_points(service: str, url: str) -> list[tuple[float, float]]:
    """The (lat, lon) points the app asked a router to visit, in order."""
    if service == "valhalla":
        req = json.loads(parse_qs(urlsplit(url).query)["json"][0])
        return [(loc["lat"], loc["lon"]) for loc in req["locations"]]
    coords = urlsplit(url).path.split("/driving/")[1].split(";")
    return [(float(c.split(",")[1]), float(c.split(",")[0])) for c in coords]


UNKNOWN_PLACE = "Atlantis"  # every fake search service answers "not found" for this


def ok_body(service: str, url: str) -> object:
    qs = parse_qs(urlsplit(url).query)
    if service in EMPTY and UNKNOWN_PLACE in (qs.get("q") or qs.get("name"))[0]:
        return EMPTY[service]
    if service == "nominatim":
        (lat, lon), name = place_for(qs["q"][0])
        return [{"lat": str(lat), "lon": str(lon), "display_name": name}]
    if service == "photon":
        (lat, lon), name = place_for(qs["q"][0])
        return {
            "features": [{"geometry": {"coordinates": [lon, lat]}, "properties": {"name": name}}]
        }
    if service == "openmeteo":
        if re.search(r"\s[A-Z]{2,3}$", qs["name"][0]):
            return {}  # like the real service: "Darwin NT" finds nothing, "Darwin" does
        (lat, lon), name = place_for(qs["name"][0])
        return {"results": [{"latitude": lat, "longitude": lon, "name": name}]}

    # Routers: the total is always ROUTE_*, split evenly over the legs between the points.
    points = route_points(service, url)
    n_legs = len(points) - 1
    leg_m, leg_s = ROUTE_METERS / n_legs, ROUTE_SECONDS / n_legs
    if service in ("osrm", "osrm_fossgis"):
        geometry = {"type": "LineString", "coordinates": [[lon, lat] for lat, lon in points]}
        legs = [{"distance": leg_m, "duration": leg_s}] * n_legs
        return {
            "code": "Ok",
            "routes": [
                {
                    "distance": ROUTE_METERS,
                    "duration": ROUTE_SECONDS,
                    "geometry": geometry,
                    "legs": legs,
                }
            ],
        }
    if service == "valhalla":
        legs = [
            {
                "summary": {"length": leg_m / 1000, "time": leg_s},
                "shape": encode_polyline6(points[i : i + 2]),
            }
            for i in range(n_legs)
        ]
        return {
            "trip": {
                "summary": {"length": ROUTE_METERS / 1000, "time": ROUTE_SECONDS},
                "legs": legs,
            }
        }
    raise AssertionError(service)


EMPTY = {"nominatim": [], "photon": {"features": []}, "openmeteo": {}}
NO_ROUTE = {
    "osrm": {"code": "NoRoute"},
    "osrm_fossgis": {"code": "NoRoute"},
    "valhalla": {"error_code": 442},
}


class FakeServices:
    """Per-service behaviour: "ok", "empty" (not found), "noroute", "hang", or an HTTP status."""

    def __init__(self, page: Page) -> None:
        self.mode: dict[str, object] = dict.fromkeys(SERVICES, "ok")
        self.calls: Counter[str] = Counter()
        self.urls: dict[str, list[str]] = {name: [] for name in SERVICES}
        for name, pattern in SERVICES.items():
            page.route(pattern, functools.partial(self._handle, name))

    def _handle(self, name: str, route: Route, *_: object) -> None:
        self.calls[name] += 1
        self.urls[name].append(route.request.url)
        mode = self.mode[name]
        if mode == "hang":
            return  # never answer; the app's timeout must kick in
        if mode == "ok":
            route.fulfill(json=ok_body(name, route.request.url), headers=CORS)
        elif mode == "empty":
            route.fulfill(json=EMPTY[name], headers=CORS)
        elif mode == "noroute":
            route.fulfill(status=400, json=NO_ROUTE[name], headers=CORS)
        else:
            route.fulfill(status=int(mode), json={"error": "fake"}, headers=CORS)

    def geocoder_calls(self) -> int:
        return sum(self.calls[s] for s in ("nominatim", "photon", "openmeteo"))


@pytest.fixture
def svc(page: Page, base_url: str) -> FakeServices:
    fake = FakeServices(page)
    page.add_init_script(
        "window.MPD_TEST = {timeoutMs: 400, retries: 1, retryDelayMs: 10, rateLimit: false}"
    )
    page.goto(f"{base_url}/miles-per-day/")
    return fake


def plan(
    page: Page,
    start: str = "Darwin NT",
    dest: str = "Alice Springs NT",
    days_ahead: int = 4,
    rest: int = 0,
    stops: tuple[str, ...] = (),
) -> None:
    page.fill("#start", start)
    for i, stop in enumerate(stops):
        page.click("#addStop")
        page.locator("#stops input").nth(i).fill(stop)
    page.fill("#dest", dest)
    page.fill("#date", (date.today() + timedelta(days=days_ahead)).isoformat())
    page.fill("#rest", str(rest))
    page.click("#go")


def expect_result(page: Page, per_day: str) -> None:
    expect(page.locator("#perDay")).to_have_text(per_day)
    # Faked outages make the browser log "Failed to load resource"; only real JS errors count.
    assert [e for e in page.js_errors if not e.startswith("Failed to load resource")] == []


# ---------- calculation ----------


def test_calculates_daily_distance(page: Page, svc: FakeServices) -> None:
    plan(page, days_ahead=4)  # today + 4 more days = 5 driving days
    expect_result(page, "200")
    expect(page.locator("#total")).to_have_text("1,000 mi")
    expect(page.locator("#days")).to_have_text("5")
    expect(page.locator("#hrsDay")).to_have_text("2h 0m")
    expect(page.locator("#routeNote")).to_contain_text("Search: Nominatim · Route: OSRM")


def test_rest_days_and_kilometres(page: Page, svc: FakeServices) -> None:
    plan(page, days_ahead=4, rest=1)  # 5 days - 1 rest = 4
    expect_result(page, "250")
    page.click('.units button[data-u="km"]')
    expect(page.locator("#perDay")).to_have_text("403")  # ceil(1609.344 / 4)
    expect(page.locator("#total")).to_have_text("1,609 km")


def test_too_many_rest_days(page: Page, svc: FakeServices) -> None:
    plan(page, days_ahead=2, rest=5)
    expect(page.locator("#msg")).to_contain_text("No driving days left")


# ---------- address search fallbacks ----------


def test_search_retries_then_falls_back_to_photon(page: Page, svc: FakeServices) -> None:
    svc.mode["nominatim"] = 503
    plan(page)
    expect_result(page, "200")
    expect(page.locator("#routeNote")).to_contain_text("Search: Photon")
    assert svc.calls["nominatim"] == 4  # 1 try + 1 retry, for start and destination
    assert svc.calls["photon"] == 2


def test_search_timeout_falls_back(page: Page, svc: FakeServices) -> None:
    svc.mode["nominatim"] = "hang"
    plan(page)
    expect_result(page, "200")
    expect(page.locator("#routeNote")).to_contain_text("Search: Photon")


def test_search_falls_back_to_open_meteo(page: Page, svc: FakeServices) -> None:
    svc.mode["nominatim"] = svc.mode["photon"] = 500
    plan(page)
    expect_result(page, "200")
    expect(page.locator("#routeNote")).to_contain_text("Search: Open-Meteo")
    assert svc.calls["openmeteo"] == 4  # "Darwin NT" then "Darwin", for start and destination


def test_not_found_anywhere(page: Page, svc: FakeServices) -> None:
    for s in ("nominatim", "photon", "openmeteo"):
        svc.mode[s] = "empty"
    plan(page, start="Nowhere at all")
    expect(page.locator("#msg")).to_contain_text('Couldn\'t find "Nowhere at all"')
    assert svc.calls["nominatim"] == 1  # "not found" is not retried


def test_search_services_all_down(page: Page, svc: FakeServices) -> None:
    for s in ("nominatim", "photon", "openmeteo"):
        svc.mode[s] = 500
    plan(page)
    expect(page.locator("#msg")).to_contain_text("Address search is unavailable")
    expect(page.locator("#go")).to_be_enabled()


def test_coordinates_skip_search_and_results_are_cached(page: Page, svc: FakeServices) -> None:
    plan(page, start="-12.46, 130.84")
    expect_result(page, "200")
    expect(page.locator("#routeNote")).to_contain_text("Search: coordinates, Nominatim")
    assert svc.geocoder_calls() == 1  # destination only

    page.click("#go")  # same trip again: destination now comes from the saved cache
    expect(page.locator("#routeNote")).to_contain_text("Search: coordinates, saved")
    assert svc.geocoder_calls() == 1


# ---------- routing fallbacks ----------


@pytest.mark.parametrize(
    ("down", "used"),
    [(["osrm"], "OSRM (FOSSGIS)"), (["osrm", "osrm_fossgis"], "Valhalla (FOSSGIS)")],
)
def test_routing_falls_back(page: Page, svc: FakeServices, down: list[str], used: str) -> None:
    for s in down:
        svc.mode[s] = 502
    plan(page)
    expect_result(page, "200")
    expect(page.locator("#total")).to_have_text("1,000 mi")
    expect(page.locator("#routeNote")).to_contain_text(f"Route: {used}")


def test_no_route(page: Page, svc: FakeServices) -> None:
    for s in ("osrm", "osrm_fossgis", "valhalla"):
        svc.mode[s] = "noroute"
    plan(page)
    expect(page.locator("#msg")).to_contain_text("No driving route found")


def test_routing_all_down(page: Page, svc: FakeServices) -> None:
    for s in ("osrm", "osrm_fossgis", "valhalla"):
        svc.mode[s] = 503
    plan(page)
    expect(page.locator("#msg")).to_contain_text("Routing services are busy")


# ---------- stops along the way ----------


def test_route_passes_through_stops_in_order(page: Page, svc: FakeServices) -> None:
    plan(page, stops=("Katherine NT", "Tennant Creek NT"))
    expect_result(page, "200")  # same 1000 mi total over 5 days
    assert route_points("osrm", svc.urls["osrm"][-1]) == [
        (-12.46, 130.84),
        (-14.47, 132.26),
        (-19.65, 134.19),
        (-23.70, 133.88),
    ]
    legs = page.locator("#legs li")
    expect(legs).to_have_count(3)
    expect(legs.nth(0)).to_contain_text("Darwin → Katherine")
    expect(legs.nth(0)).to_contain_text("333 mi · 3h 20m")
    expect(legs.nth(2)).to_contain_text("Tennant Creek → Alice Springs")
    expect(page.locator("#routeNote")).to_contain_text("Via: Katherine · Tennant Creek")


def test_stops_work_with_valhalla_fallback(page: Page, svc: FakeServices) -> None:
    svc.mode["osrm"] = svc.mode["osrm_fossgis"] = 502
    plan(page, stops=("Katherine NT",))
    expect_result(page, "200")
    assert len(route_points("valhalla", svc.urls["valhalla"][-1])) == 3
    expect(page.locator("#legs li")).to_have_count(2)
    expect(page.locator("#routeNote")).to_contain_text("Route: Valhalla (FOSSGIS)")


def test_no_stops_shows_no_leg_list(page: Page, svc: FakeServices) -> None:
    plan(page)
    expect_result(page, "200")
    expect(page.locator("#legs li")).to_have_count(0)
    expect(page.locator("#routeNote")).not_to_contain_text("Via:")


def test_blank_stops_are_ignored(page: Page, svc: FakeServices) -> None:
    plan(page, stops=("", "Katherine NT", "  "))
    expect_result(page, "200")
    assert len(route_points("osrm", svc.urls["osrm"][-1])) == 3


def test_unknown_stop_is_named_in_error(page: Page, svc: FakeServices) -> None:
    plan(page, stops=("Katherine NT", UNKNOWN_PLACE))
    expect(page.locator("#msg")).to_contain_text(f'Couldn\'t find "{UNKNOWN_PLACE}"')
    expect(page.locator("#result")).to_be_hidden()
    assert svc.calls["osrm"] == 0


def test_remove_and_move_stops(page: Page, svc: FakeServices) -> None:
    for name in ("A", "B", "C"):
        page.click("#addStop")
        page.locator("#stops input").last.fill(name)
    stops = page.locator("#stops input")
    expect(page.locator("#stops .up").first).to_be_disabled()
    page.locator("#stops .up").nth(2).click()  # C moves above B
    assert [stops.nth(i).input_value() for i in range(3)] == ["A", "C", "B"]
    page.locator("#stops .del").nth(0).click()  # remove A
    assert [stops.nth(i).input_value() for i in range(2)] == ["C", "B"]
    expect(stops.nth(0)).to_have_attribute("placeholder", "Stop 1")


def test_stop_limit(page: Page, svc: FakeServices) -> None:
    for _ in range(10):
        page.click("#addStop")
    expect(page.locator("#addStop")).to_be_disabled()
    expect(page.locator("#stops input")).to_have_count(10)
    page.locator("#stops .del").first.click()
    expect(page.locator("#addStop")).to_be_enabled()


# ---------- saved input ----------


def test_input_is_restored_on_return(page: Page, svc: FakeServices) -> None:
    arrive = (date.today() + timedelta(days=6)).isoformat()
    page.fill("#start", "Darwin NT")
    for stop in ("Katherine NT", "Tennant Creek NT"):
        page.click("#addStop")
        page.locator("#stops input").last.fill(stop)
    page.fill("#dest", "Alice Springs NT")
    page.fill("#date", arrive)
    page.uncheck("#today")
    page.fill("#rest", "2")
    page.click('.units button[data-u="km"]')

    page.reload()  # never pressed Calculate: typing alone must be saved

    expect(page.locator("#start")).to_have_value("Darwin NT")
    stops = page.locator("#stops input")
    expect(stops).to_have_count(2)
    expect(stops.nth(0)).to_have_value("Katherine NT")
    expect(stops.nth(1)).to_have_value("Tennant Creek NT")
    expect(page.locator("#dest")).to_have_value("Alice Springs NT")
    expect(page.locator("#date")).to_have_value(arrive)
    expect(page.locator("#today")).not_to_be_checked()
    expect(page.locator("#rest")).to_have_value("2")
    expect(page.locator('.units button[data-u="km"]')).to_have_class("on")
    assert page.js_errors == []


def test_removed_stops_stay_removed_on_return(page: Page, svc: FakeServices) -> None:
    page.click("#addStop")
    page.fill("#stops input", "Katherine NT")
    page.click("#stops .del")
    page.reload()
    expect(page.locator("#stops input")).to_have_count(0)


def test_old_saved_settings_still_load(page: Page, base_url: str) -> None:
    """Settings saved by the earlier version (key 'mpd', no stops) are picked up."""
    page.add_init_script(
        """if (!sessionStorage.getItem('seeded')) {
             localStorage.setItem('mpd', JSON.stringify({start: 'Darwin NT', dest: 'Alice Springs NT',
               today: true, rest: '1', units: 'km'}));
             sessionStorage.setItem('seeded', '1');
           }"""
    )
    page.goto(f"{base_url}/miles-per-day/")
    expect(page.locator("#start")).to_have_value("Darwin NT")
    expect(page.locator("#dest")).to_have_value("Alice Springs NT")
    expect(page.locator("#stops input")).to_have_count(0)
    expect(page.locator('.units button[data-u="km"]')).to_have_class("on")
    assert page.js_errors == []
