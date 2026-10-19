"""Tests for brewcalc/service.py's request handler, which the browser (GitHub Pages) version uses in place of api.py."""

import json
from pathlib import Path

import pytest

from brewcalc import service

EXAMPLE_PATH = Path(__file__).resolve().parent.parent / "data" / "example_recipe.json"


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "test.db"


def call(db_path, method, path, payload=None):
    raw = None if payload is None else json.dumps(payload)
    status, data = service.handle(method, path, raw, db_path, EXAMPLE_PATH)
    return status, json.loads(json.dumps(data))  # must be JSON-serialisable, as it is sent to the page


def test_reference_defaults_and_calculate(db_path):
    status, ref = call(db_path, "GET", "/api/reference")
    assert status == 200 and len(ref["grains"]) > 200 and len(ref["hops"]) > 100 and ref["yeasts"] and ref["styles"]
    status, d = call(db_path, "GET", "/api/defaults")
    assert status == 200 and d["example"]["grains"]
    status, res = call(db_path, "POST", "/api/calculate", d["example"])
    assert status == 200 and 1.03 < res["og"] < 1.12 and res["ibu"] > 0 and len(res["grain_rows"]) == len(d["example"]["grains"])
    assert res["srm_hex"].startswith("#")


def test_bad_input_gives_errors_not_crashes(db_path):
    assert call(db_path, "POST", "/api/calculate", {"batch": {"post_boil_gal": 0, "pre_boil_gal": 0}})[0] in (200, 422)
    assert service.handle("POST", "/api/calculate", "not json", db_path, EXAMPLE_PATH)[0] == 400
    assert service.handle("POST", "/api/calculate", "[1]", db_path, EXAMPLE_PATH)[0] == 400
    assert call(db_path, "GET", "/api/nothing")[0] == 404
    assert call(db_path, "DELETE", "/api/calculate")[0] == 405


def test_recipes_round_trip_including_additions(db_path):
    _, d = call(db_path, "GET", "/api/defaults")
    recipe = {**d["example"], "name": "Test IPA", "additions": [{"name": "Whirlfloc", "amount": "1", "unit": "tablet", "notes": ""}]}
    status, made = call(db_path, "POST", "/api/recipes", recipe)
    assert status == 201
    assert call(db_path, "GET", "/api/recipes")[1][0]["name"] == "Test IPA"
    status, got = call(db_path, "GET", f"/api/recipes/{made['id']}")
    assert status == 200 and got["additions"][0]["name"] == "Whirlfloc"
    assert call(db_path, "PUT", f"/api/recipes/{made['id']}", {**recipe, "name": "Renamed"})[0] == 200
    assert call(db_path, "GET", f"/api/recipes/{made['id']}")[1]["name"] == "Renamed"
    assert call(db_path, "PUT", "/api/recipes/999", recipe)[0] == 404
    assert call(db_path, "DELETE", f"/api/recipes/{made['id']}")[0] == 200
    assert call(db_path, "GET", f"/api/recipes/{made['id']}")[0] == 404


def test_logs_and_brew_day(db_path):
    _, d = call(db_path, "GET", "/api/defaults")
    status, made = call(db_path, "POST", "/api/logs", {"brew_date": "2026-10-19", "data": {"og": 1.06}, "recipe_snapshot": d["example"]})
    assert status == 201
    assert call(db_path, "GET", "/api/logs")[1][0]["recipe_name"] == d["example"]["name"]
    status, plan = call(db_path, "POST", "/api/brewday", {"recipe": d["example"], "data": {"og": 1.06, "fg": 1.012, "pre_boil_sg": 1.05}})
    assert status == 200 and plan["plan"]["strike_water_qt"] > 0 and plan["actual"]["abv"]["value"] > 0
    assert call(db_path, "PUT", f"/api/logs/{made['id']}", {"brew_date": "2026-10-20", "data": {}})[0] == 200
    assert call(db_path, "DELETE", f"/api/logs/{made['id']}")[0] == 200
    assert call(db_path, "GET", f"/api/logs/{made['id']}")[0] == 404
