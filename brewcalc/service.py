"""The app's behaviour without any web framework: what each API request does.

api.py (the Starlette server used on the Mac) and the browser version (Pyodide, for GitHub Pages) both use this,
so the maths and the responses are the same in both. Nothing here imports Starlette or Streamlit.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import asdict
from pathlib import Path

from brewcalc import calcs, db, reference
from brewcalc import recipe as rcp

# Order hops go in on brew day: first wort, boil (longest first), then after the boil.
_HOP_ORDER = {"first wort": 0, "boil": 1, "flameout": 2, "whirlpool": 3, "dry hop": 4}


def clean(obj):
    """Make a value safe for JSON: NaN and infinity become null."""
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [clean(v) for v in obj]
    return obj


def yeast_label(y: dict) -> str:
    """Yeast name plus manufacturer and code, e.g. "London Ale (White Labs WLP013)".
    Anything the name already says (like a code in a label) is left out."""
    parts = [t for t in (y["lab"], y["code"]) if t and t not in y["name"]]
    return f"{y['name']} ({' '.join(parts)})" if parts else y["name"]


def style_dict(s: calcs.StyleRange, detail: bool = False) -> dict:
    out = {"name": s.name, "abv": s.abv, "ibu": s.ibu, "og": s.og, "fg": s.fg, "srm": s.srm}
    if detail:  # the BJCP text sections, only sent for the style in use
        out["info"] = s.info
    return out


def style_target(style: calcs.StyleRange, base: calcs.StyleRange | None) -> dict:
    """The style to compare against. A style with no ranges of its own (Fruit Beer, Smoked Beer...) borrows
    the ranges of the chosen base beer style."""
    out = style_dict(style, detail=True)
    out["needs_base"] = all(getattr(style, k) is None for k in ("abv", "ibu", "og", "fg", "srm"))
    if out["needs_base"] and base:
        out.update({k: getattr(base, k) for k in ("abv", "ibu", "og", "fg", "srm")}, base=base.name)
    return out


def num(value, default=0.0) -> float:
    return default if value is None else float(value)


def carbonation_summary(recipe: dict, batch_gal: float) -> dict:
    """Priming sugar for bottling and regulator pressure for kegging, from the recipe's carbonation settings."""
    c = recipe.get("carbonation") or {}
    volumes = num(c.get("volumes"), 2.4)
    sugar = c.get("sugar") if c.get("sugar") in calcs.PRIMING_SUGARS else calcs.DEFAULT_PRIMING_SUGAR
    beer_temp = num(c.get("beer_temp_f"), 68.0)
    gal = num(c.get("volume_gal"), 0.0) or batch_gal
    residual = calcs.residual_co2_volumes(beer_temp)
    keg_temp = num(c.get("keg_temp_f"), 38.0)
    return {
        "volume_gal": gal,
        "residual_volumes": residual,
        "needed_volumes": max(0.0, volumes - residual),
        "sugar_g": calcs.priming_sugar_g(gal, beer_temp, volumes, sugar),
        "keg_psi": calcs.keg_psi(keg_temp, volumes),
    }


def analyze(recipe: dict) -> dict:
    """Everything the calculator page shows for a recipe."""
    recipe = rcp.normalize(recipe)
    grain_ref, hop_ref = reference.grains(), reference.hops()
    grains, hops, batch, mash = rcp.to_inputs(recipe)
    res = calcs.calculate(grains, hops, batch, mash)

    # One row per grain and hop line the recipe has, in the same order (None for unknown grains and
    # for hop lines without a name), so the page can show them next to the editable cells.
    total = res.total_grain_lbs or 1
    scale = batch.efficiency_pct / 100 * batch.pre_boil_gal / batch.post_boil_gal if batch.post_boil_gal else 0
    grain_rows = []
    for g in recipe["grains"]:
        ref = grain_ref.get(g.get("name"))
        if not ref:
            grain_rows.append(None)
            continue
        lbs = num(g.get("lbs"))
        grain_rows.append(
            {
                "lovibond": ref["lovibond"],
                "ppg": ref["ppg"],
                "pct": lbs / total * 100,
                "og_points": ref["ppg"] * lbs / batch.pre_boil_gal * scale if batch.pre_boil_gal else 0.0,
                "mcu": lbs * ref["lovibond"] / batch.post_boil_gal if batch.post_boil_gal else 0.0,
            }
        )

    hop_iter = iter(zip(hops, res.hop_ibus, strict=True))
    hop_rows = []
    for h in recipe["hops"]:
        if not h.get("name"):
            hop_rows.append(None)
            continue
        hop, ibu = next(hop_iter)
        util = calcs.hop_utilization(hop, grains, batch)
        hop_rows.append({"alpha_acid": hop.alpha_acid, "utilization": util, "ibu": ibu})

    decoction = calcs.decoction_schedule(res.total_grain_lbs, mash, recipe["decoction_steps"], batch.pre_boil_gal)
    style = reference.find_style(recipe["style"])
    mash_water_qt = res.infusions[-1].total_mash_water_qt if res.infusions else res.strike_water_qt
    carbonation = carbonation_summary(recipe, num(recipe["batch"].get("post_boil_gal")))  # the target (packaged) volume, not the wort at end of boil
    return {
        "carbonation": carbonation,
        "og": res.og,
        "fg": res.fg,
        "abv": res.abv,
        "abv_alternate": res.abv_alternate,
        "ibu": res.ibu,
        "srm": res.srm,
        "srm_hex": calcs.srm_to_hex(res.srm),
        "srm_color_name": calcs.srm_color_name(res.srm, reference.srm_colors()),
        "pre_boil_gravity": res.pre_boil_gravity,
        "attenuation_pct": batch.attenuation_pct,
        "total_grain_lbs": res.total_grain_lbs,
        "max_points_per_gal": res.max_points_per_gal,
        "strike_water_qt": res.strike_water_qt,
        "strike_water_temp_f": res.strike_water_temp_f,
        "infusions": [asdict(s) for s in res.infusions],
        "sparge_water_gal": res.sparge_water_gal,
        "mash_water_gal": mash_water_qt / 4,
        "absorbed_gal": res.total_grain_lbs * mash.grain_absorption_gal_per_lb,
        "decoction": asdict(decoction) if decoction else None,
        "style_target": style_target(style, reference.find_style(recipe["base_style"])) if style else None,
        "grain_rows": grain_rows,
        "hop_rows": hop_rows,
        "unknown_grains": [g["name"] for g in recipe["grains"] if g.get("name") and g["name"] not in grain_ref],
        "missing_hops": [
            h["name"] for h in recipe["hops"] if h.get("name") and h["name"] not in hop_ref and h.get("alpha_acid") is None
        ],
    }


def brew_day(recipe: dict, data: dict) -> dict:
    """The brew plan for a recipe, and how a log's measurements compare with it."""
    recipe = rcp.normalize(recipe)
    plan = rcp.calculate(recipe)
    grains, hops, batch, mash = rcp.to_inputs(recipe)

    ordered = sorted(hops, key=lambda h: (_HOP_ORDER.get(h.use, 99), -h.minutes))
    out = {
        "recipe_name": recipe["name"],
        "style": recipe["style"],
        "plan": {
            "strike_water_qt": plan.strike_water_qt,
            "strike_water_temp_f": plan.strike_water_temp_f,
            "mash_temp_f": mash.mash_temp_f,
            "infusions": [asdict(s) for s in plan.infusions],
            "sparge_water_gal": plan.sparge_water_gal,
            "pre_boil_gal": batch.pre_boil_gal,
            "pre_boil_gravity": plan.pre_boil_gravity,
            "grains": [{"name": g.name, "lbs": g.lbs} for g in grains],
            "hops": [{**asdict(h), "time_unit": calcs.HOP_TIME_UNIT.get(h.use, "min")} for h in ordered],
            "additions": [a for a in recipe.get("additions", []) if any(str(a.get(k) or "").strip() for k in ("name", "amount", "unit", "notes"))],
            "yeast": recipe["yeast"],
            "attenuation_pct": batch.attenuation_pct,
            "og": plan.og,
            "fg": plan.fg,
            "abv": plan.abv,
            "efficiency_pct": batch.efficiency_pct,
        },
    }

    pre_sg, pre_gal = data.get("pre_boil_sg"), data.get("pre_boil_gal")
    og, fg = data.get("og"), data.get("fg")
    actual: dict = {"efficiency": None, "og": None, "fg": None, "abv": None, "attenuation": None}
    if pre_sg:
        eff = calcs.actual_efficiency(pre_sg, grains, pre_gal or batch.pre_boil_gal)
        actual["efficiency"] = {"value": eff, "delta": eff - batch.efficiency_pct}
    if og:
        actual["og"] = {"value": og, "delta_points": (og - plan.og) * 1000}
    if fg:
        actual["fg"] = {"value": fg, "delta_points": (fg - plan.fg) * 1000}
    if og and fg:
        abv = calcs.abv(og, fg)
        actual["abv"] = {"value": abv, "delta": abv - plan.abv}
        if og > 1:
            att = (og - fg) / (og - 1) * 100
            actual["attenuation"] = {"value": att, "delta": att - batch.attenuation_pct}
    out["actual"] = actual
    return out


# --------------------------------------------------------------------------
# Request handling (used by the browser version; api.py has its own Starlette routes for the same things)
# --------------------------------------------------------------------------


def reference_payload() -> dict:
    return {
        "grains": list(reference.grains().values()),
        "hops": list(reference.hops().values()),
        "yeasts": [{**y, "display": yeast_label(y)} for y in reference.yeasts().values()],
        "styles": [style_dict(s) for s in reference.styles().values()],
        "hop_forms": list(calcs.HOP_FORM_FACTOR),
        "hop_uses": calcs.HOP_USES,
        "hop_time_units": calcs.HOP_TIME_UNIT,
        "carbonation": {
            "sugars": list(calcs.PRIMING_SUGARS),
            "styles": [{"name": n, "low": lo, "high": hi} for n, lo, hi in calcs.CARBONATION_STYLES],
        },
    }


_ROUTES = re.compile(r"^/api/(reference/reload|reference|defaults|normalize|calculate|brewday|recipes|logs)(?:/(\d+))?$")


def handle(method: str, path: str, raw_body: str | None, db_path: Path, example_path: Path) -> tuple[int, object]:
    """Do what api.py's route for (method, path) does. Returns (HTTP status, JSON-ready data)."""
    m = _ROUTES.match(path)
    if not m:
        return 404, {"error": "No such endpoint"}
    name, ident = m.group(1), (int(m.group(2)) if m.group(2) else None)

    body: dict = {}
    if method in ("POST", "PUT"):
        try:
            body = json.loads(raw_body or "{}")
        except ValueError:
            return 400, {"error": "The request body is not valid JSON"}
        if not isinstance(body, dict):
            return 400, {"error": "Expected a JSON object"}

    def ok(data, status=200):
        return status, clean(data)

    def err(message, status):
        return status, {"error": message}

    calc_errors = (ZeroDivisionError, ValueError, TypeError, KeyError)
    if name == "reference" and method == "GET" and ident is None:
        return ok(reference_payload())
    if name == "reference/reload" and method == "POST":
        for f in (reference.grains, reference.hops, reference.yeasts, reference.styles, reference.srm_colors):
            f.cache_clear()
        return ok(reference_payload())
    if name == "defaults" and method == "GET":
        return ok({"default": rcp.DEFAULT_RECIPE, "example": rcp.from_json(example_path.read_text())})
    if name == "normalize" and method == "POST":
        try:
            return ok(rcp.normalize(body))
        except (TypeError, ValueError, AttributeError) as e:
            return err(f"That doesn't look like a recipe: {e}", 422)
    if name == "calculate" and method == "POST":
        try:
            return ok(analyze(body))
        except calc_errors as e:
            return err(f"Can't calculate this recipe: {e!r}", 422)
    if name == "brewday" and method == "POST":
        try:
            return ok(brew_day(body.get("recipe") or {}, body.get("data") or {}))
        except calc_errors as e:
            return err(f"Can't work out this brew plan: {e!r}", 422)

    if name == "recipes":
        if ident is None and method == "GET":
            return ok(db.list_recipes(db_path))
        if ident is None and method == "POST":
            return ok({"id": db.save_recipe(body, None, db_path)}, 201)
        if ident is not None and method == "GET":
            recipe = db.get_recipe(ident, db_path)
            return ok(rcp.normalize(recipe)) if recipe else err("No such recipe", 404)
        if ident is not None and method == "PUT":
            if db.get_recipe(ident, db_path) is None:
                return err("No such recipe", 404)
            return ok({"id": db.save_recipe(body, ident, db_path)})
        if ident is not None and method == "DELETE":
            db.delete_recipe(ident, db_path)
            return ok({"ok": True})

    if name == "logs":
        if ident is None and method == "GET":
            return ok(db.list_logs(db_path))
        if ident is None and method == "POST":
            if "brew_date" not in body:
                return err("brew_date is required", 422)
            log_id = db.save_log(body["brew_date"], body.get("data") or {}, body.get("recipe_id"), body.get("recipe_snapshot"), None, db_path)
            return ok({"id": log_id}, 201)
        if ident is not None and method == "GET":
            log = db.get_log(ident, db_path)
            return ok(log) if log else err("No such log", 404)
        if ident is not None and method == "PUT":
            old = db.get_log(ident, db_path)
            if old is None:
                return err("No such log", 404)
            db.save_log(body["brew_date"], body.get("data") or {}, old["recipe_id"], old["recipe_snapshot"], ident, db_path)
            return ok({"id": ident})
        if ident is not None and method == "DELETE":
            db.delete_log(ident, db_path)
            return ok({"ok": True})

    return err("Method not allowed", 405)
