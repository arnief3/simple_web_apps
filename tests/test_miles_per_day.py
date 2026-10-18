"""Interaction checks for miles-per-day, with all search and routing services faked."""

import functools
import re
from collections import Counter
from datetime import date, timedelta
from urllib.parse import parse_qs, urlparse

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

DARWIN = (-12.46, 130.84)
ALICE = (-23.70, 133.88)
ROUTE_METERS = 1_609_344  # exactly 1000 miles
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
    return (DARWIN, "Darwin, NT") if "darwin" in query.lower() else (ALICE, "Alice Springs, NT")


def ok_body(service: str, url: str) -> object:
    qs = parse_qs(urlparse(url).query)
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
    if service in ("osrm", "osrm_fossgis"):
        geometry = {
            "type": "LineString",
            "coordinates": [[DARWIN[1], DARWIN[0]], [ALICE[1], ALICE[0]]],
        }
        return {
            "code": "Ok",
            "routes": [{"distance": ROUTE_METERS, "duration": ROUTE_SECONDS, "geometry": geometry}],
        }
    if service == "valhalla":
        return {
            "trip": {
                "summary": {"length": ROUTE_METERS / 1000, "time": ROUTE_SECONDS},
                "legs": [{"shape": encode_polyline6([DARWIN, ALICE])}],
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
        for name, pattern in SERVICES.items():
            page.route(pattern, functools.partial(self._handle, name))

    def _handle(self, name: str, route: Route, *_: object) -> None:
        self.calls[name] += 1
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
) -> None:
    page.fill("#start", start)
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
