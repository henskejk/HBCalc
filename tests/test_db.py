from brewcalc import db


def test_recipe_round_trip(tmp_path):
    path = tmp_path / "t.db"
    rid = db.save_recipe({"name": "Test IPA", "style": "American IPA", "grains": []}, path=path)
    assert db.get_recipe(rid, path)["name"] == "Test IPA"

    db.save_recipe({"name": "Renamed", "style": ""}, recipe_id=rid, path=path)
    assert [r["name"] for r in db.list_recipes(path)] == ["Renamed"]

    db.delete_recipe(rid, path)
    assert db.list_recipes(path) == []


def test_log_keeps_recipe_name_after_recipe_deleted(tmp_path):
    path = tmp_path / "t.db"
    rid = db.save_recipe({"name": "Stout"}, path=path)
    lid = db.save_log("2026-09-30", {"og": 1.05}, rid, {"name": "Stout"}, path=path)
    db.delete_recipe(rid, path)
    (log,) = db.list_logs(path)
    assert (log["recipe_id"], log["recipe_name"]) == (None, "Stout")
    assert db.get_log(lid, path)["data"] == {"og": 1.05}
