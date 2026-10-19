"""Tests for api.py. Calls the ASGI app directly, so no extra packages (like httpx) are needed."""

import asyncio
import json

import pytest

import api
from brewcalc import calcs, reference
from brewcalc import recipe as rcp

EXAMPLE = rcp.from_json(api.EXAMPLE_PATH.read_text())
for _hop in EXAMPLE["hops"]:  # pin the alpha acid, like tests/test_calcs.py, so reference edits don't move these
    _hop["alpha_acid"] = 11.0


def call(method: str, path: str, payload=None):
    """Send one request to the app. Returns (status, parsed JSON)."""
    raw = b"" if payload is None else json.dumps(payload).encode()
    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": method, "path": path,
        "raw_path": path.encode(), "query_string": b"", "root_path": "", "scheme": "http",
        "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(raw)).encode())],
        "server": ("test", 80), "client": ("test", 1),
    }
    sent = []

    async def receive():
        return {"type": "http.request", "body": raw, "more_body": False}

    async def send(message):
        sent.append(message)

    asyncio.run(api.app(scope, receive, send))
    status = next(m["status"] for m in sent if m["type"] == "http.response.start")
    data = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    return status, json.loads(data) if data else None


def use_temp_db(tmp_path):
    """Point the API at an empty database file for one test."""
    api.DB_PATH = tmp_path / "t.db"


def test_calculate_matches_the_python_calculator():
    status, out = call("POST", "/api/calculate", EXAMPLE)
    assert status == 200
    expected = rcp.calculate(EXAMPLE)
    for key in ("og", "fg", "abv", "ibu", "srm", "pre_boil_gravity", "sparge_water_gal", "strike_water_temp_f"):
        assert out[key] == pytest.approx(getattr(expected, key))
    assert out["srm_color_name"] == calcs.srm_color_name(expected.srm, reference.srm_colors())
    assert out["style_target"]["name"] == "21A. American IPA"


def test_calculate_rows_line_up_with_the_recipe():
    recipe = {**EXAMPLE, "grains": [*EXAMPLE["grains"], {"name": "Nonexistent malt", "lbs": 1}, {"name": None, "lbs": None}]}
    recipe["hops"] = [{"name": "", "oz": 1}, *EXAMPLE["hops"]]
    _, out = call("POST", "/api/calculate", recipe)
    assert len(out["grain_rows"]) == len(recipe["grains"])
    assert out["grain_rows"][3] is None and out["grain_rows"][4] is None
    assert sum(r["pct"] for r in out["grain_rows"] if r) == pytest.approx(100)
    assert out["unknown_grains"] == ["Nonexistent malt"]
    assert len(out["hop_rows"]) == len(recipe["hops"]) and out["hop_rows"][0] is None
    assert sum(r["ibu"] for r in out["hop_rows"] if r) == pytest.approx(out["ibu"])


def test_calculate_reports_a_problem_instead_of_crashing():
    bad = {**EXAMPLE, "mash": {**EXAMPLE["mash"], "thickness_qt_per_lb": 0}}
    status, out = call("POST", "/api/calculate", bad)
    assert status == 422 and "error" in out


def test_calculate_empty_recipe():
    status, out = call("POST", "/api/calculate", rcp.DEFAULT_RECIPE)
    assert status == 200 and out["og"] == pytest.approx(1.0) and out["grain_rows"] == []


def test_bad_json_is_a_400():
    scope_status, _ = call("POST", "/api/calculate", [1, 2])
    assert scope_status == 400


def test_reference_lists():
    status, out = call("GET", "/api/reference")
    assert status == 200
    assert {y["name"] for y in out["yeasts"]} == set(reference.yeasts())
    assert all("display" in y for y in out["yeasts"])
    assert "Brewers Malt, Briess" in {g["name"] for g in out["grains"]}
    assert out["hop_forms"] == ["pellet", "leaf"]
    assert out["hop_time_units"]["dry hop"] == "days" and out["hop_time_units"]["whirlpool"] == "min"


def test_recipe_round_trip(tmp_path):
    use_temp_db(tmp_path)
    status, out = call("POST", "/api/recipes", EXAMPLE)
    assert status == 201
    rid = out["id"]
    assert call("GET", f"/api/recipes/{rid}")[1]["name"] == EXAMPLE["name"]
    assert call("PUT", f"/api/recipes/{rid}", {**EXAMPLE, "name": "Renamed"})[0] == 200
    assert [r["name"] for r in call("GET", "/api/recipes")[1]] == ["Renamed"]
    assert call("DELETE", f"/api/recipes/{rid}")[0] == 200
    assert call("GET", f"/api/recipes/{rid}")[0] == 404
    assert call("PUT", f"/api/recipes/{rid}", EXAMPLE)[0] == 404


def test_normalize_fills_in_missing_parts():
    _, out = call("POST", "/api/normalize", {"name": "Bare"})
    assert out["batch"] == rcp.DEFAULT_RECIPE["batch"] and out["grains"] == []


def test_brew_day_plan_and_actuals():
    status, out = call("POST", "/api/brewday", {"recipe": EXAMPLE, "data": {"pre_boil_sg": 1.05, "og": 1.06, "fg": 1.012}})
    assert status == 200
    plan = rcp.calculate(EXAMPLE)
    assert out["plan"]["og"] == pytest.approx(plan.og)
    assert [h["use"] for h in out["plan"]["hops"]] == ["first wort", "boil", "boil", "flameout", "dry hop"]
    assert [h["minutes"] for h in out["plan"]["hops"]][1:3] == [40, 5]
    assert [h["time_unit"] for h in out["plan"]["hops"]] == ["min", "min", "min", "min", "days"]
    grains, _, batch, _ = rcp.to_inputs(EXAMPLE)
    eff = calcs.actual_efficiency(1.05, grains, batch.pre_boil_gal)
    assert out["actual"]["efficiency"]["value"] == pytest.approx(eff)
    assert out["actual"]["efficiency"]["delta"] == pytest.approx(eff - batch.efficiency_pct)
    assert out["actual"]["abv"]["value"] == pytest.approx(calcs.abv(1.06, 1.012))
    assert out["actual"]["attenuation"]["value"] == pytest.approx((1.06 - 1.012) / 0.06 * 100)


def test_brew_day_with_nothing_measured():
    _, out = call("POST", "/api/brewday", {"recipe": EXAMPLE, "data": {}})
    assert out["actual"] == {"efficiency": None, "og": None, "fg": None, "abv": None, "attenuation": None}


def test_log_round_trip_keeps_snapshot(tmp_path):
    use_temp_db(tmp_path)
    snap = {"name": "Stout"}
    _, out = call("POST", "/api/logs", {"brew_date": "2026-10-09", "data": {"og": 1.05}, "recipe_id": None, "recipe_snapshot": snap})
    lid = out["id"]
    log = call("GET", f"/api/logs/{lid}")[1]
    assert log["data"] == {"og": 1.05} and log["recipe_snapshot"] == snap
    call("PUT", f"/api/logs/{lid}", {"brew_date": "2026-10-10", "data": {"og": 1.06}})
    log = call("GET", f"/api/logs/{lid}")[1]
    assert log["brew_date"] == "2026-10-10" and log["data"] == {"og": 1.06} and log["recipe_snapshot"] == snap
    assert call("GET", "/api/logs")[1][0]["recipe_name"] == "Stout"
    call("DELETE", f"/api/logs/{lid}")
    assert call("GET", f"/api/logs/{lid}")[0] == 404


def test_hop_rows_follow_the_use():
    def line(use, minutes):
        return {"name": "Citra", "oz": 1, "form": "pellet", "use": use, "minutes": minutes, "alpha_acid": 10}

    recipe = {**EXAMPLE, "hops": [line("boil", 15), line("first wort", 15), line("flameout", 10), line("dry hop", 4)]}
    _, out = call("POST", "/api/calculate", recipe)
    boil, fw, flameout, dry = out["hop_rows"]
    assert fw["ibu"] == pytest.approx(boil["ibu"] * 1.1)
    assert fw["utilization"] == pytest.approx(boil["utilization"] * 1.1)
    assert flameout["ibu"] == 0 and dry["ibu"] == 0 and dry["utilization"] == 0
    assert out["ibu"] == pytest.approx(boil["ibu"] + fw["ibu"])


def test_decoction_in_the_calculation():
    _, out = call("POST", "/api/calculate", EXAMPLE)
    dec = out["decoction"]
    assert [s["name"] for s in dec["steps"]] == ["Protein rest", "Saccharification", "Mash out"]
    assert dec["steps"][0]["pull_qt"] == 0 and dec["steps"][1]["pull_qt"] > 0
    _, out = call("POST", "/api/calculate", {**EXAMPLE, "decoction_steps": []})
    assert out["decoction"] is None
    assert call("POST", "/api/normalize", {"name": "Bare"})[1]["mash_type"] == "basic"


def test_style_without_ranges_borrows_the_base_style_ranges():
    fruit = reference.find_style("29A. Fruit Beer")
    target = api.style_target(fruit, None)
    assert target["needs_base"] and target["og"] is None and "base" not in target
    target = api.style_target(fruit, reference.find_style("Kolsch"))
    assert target["base"] == "5B. Kölsch" and target["abv"] == (4.4, 5.2)
    assert not api.style_target(reference.find_style("5B. Kölsch"), None)["needs_base"]
    assert rcp.normalize({"base_style": "Kolsch"})["base_style"] == "5B. Kölsch"
