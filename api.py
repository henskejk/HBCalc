"""JSON API for the React front end.

Start with:  uvicorn api:app --port 8000   (or double-click run_react.command)

This is a thin layer over the existing brewcalc modules: every formula still lives in
brewcalc/calcs.py, and recipes and brew logs still live in brewing.db. The React app
(web/) does no brewing maths; it sends the recipe here and shows what comes back.
If web/dist exists (the built React app), this server also serves it at /.

Uses Starlette (the framework FastAPI is built on) so there is nothing else to install
besides uvicorn.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict
from pathlib import Path

from starlette.applications import Starlette
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from brewcalc import calcs, db
from brewcalc import recipe as rcp
from brewcalc import reference

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "web" / "dist"
EXAMPLE_PATH = ROOT / "data" / "example_recipe.json"
DB_PATH = db.DEFAULT_DB  # tests point this at a temporary file

# Order hops go in on brew day: first wort, boil (longest first), then after the boil.
_HOP_ORDER = {"first wort": 0, "boil": 1, "flameout": 2, "whirlpool": 3, "dry hop": 4}


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def clean(obj):
    """Make a value safe for JSON: NaN and infinity become null."""
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [clean(v) for v in obj]
    return obj


def reply(data, status: int = 200) -> JSONResponse:
    return JSONResponse(clean(data), status_code=status)


def error(message: str, status: int) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=status)


async def body(request: Request) -> dict:
    try:
        data = await request.json()
    except ValueError:
        raise HTTPException(400, "The request body is not valid JSON") from None
    if not isinstance(data, dict):
        raise HTTPException(400, "Expected a JSON object")
    return data


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


# --------------------------------------------------------------------------
# Reference data
# --------------------------------------------------------------------------


async def get_reference(request: Request) -> JSONResponse:
    return reply(
        {
            "grains": list(reference.grains().values()),
            "hops": list(reference.hops().values()),
            "yeasts": [{**y, "display": yeast_label(y)} for y in reference.yeasts().values()],
            "styles": [style_dict(s) for s in reference.styles().values()],
            "hop_forms": list(calcs.HOP_FORM_FACTOR),
            "hop_uses": calcs.HOP_USES,
            "hop_time_units": calcs.HOP_TIME_UNIT,
        }
    )


async def reload_reference(request: Request) -> JSONResponse:
    for f in (reference.grains, reference.hops, reference.yeasts, reference.styles, reference.srm_colors):
        f.cache_clear()
    return await get_reference(request)


async def get_defaults(request: Request) -> JSONResponse:
    return reply({"default": rcp.DEFAULT_RECIPE, "example": rcp.from_json(EXAMPLE_PATH.read_text())})


async def normalize(request: Request) -> JSONResponse:
    """Fill in any missing parts of a recipe (used when opening a recipe file)."""
    try:
        return reply(rcp.normalize(await body(request)))
    except (TypeError, ValueError, AttributeError) as e:
        return error(f"That doesn't look like a recipe: {e}", 422)


# --------------------------------------------------------------------------
# Calculating
# --------------------------------------------------------------------------


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
    return {
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


async def calculate(request: Request) -> JSONResponse:
    try:
        return reply(analyze(await body(request)))
    except (ZeroDivisionError, ValueError, TypeError, KeyError) as e:
        return error(f"Can't calculate this recipe: {e!r}", 422)


# --------------------------------------------------------------------------
# Saved recipes
# --------------------------------------------------------------------------


async def list_recipes(request: Request) -> JSONResponse:
    return reply(db.list_recipes(DB_PATH))


async def create_recipe(request: Request) -> JSONResponse:
    recipe = await body(request)
    return reply({"id": db.save_recipe(recipe, None, DB_PATH)}, 201)


async def get_recipe(request: Request) -> JSONResponse:
    recipe = db.get_recipe(int(request.path_params["id"]), DB_PATH)
    return reply(rcp.normalize(recipe)) if recipe else error("No such recipe", 404)


async def update_recipe(request: Request) -> JSONResponse:
    recipe_id = int(request.path_params["id"])
    if db.get_recipe(recipe_id, DB_PATH) is None:
        return error("No such recipe", 404)
    return reply({"id": db.save_recipe(await body(request), recipe_id, DB_PATH)})


async def delete_recipe(request: Request) -> JSONResponse:
    db.delete_recipe(int(request.path_params["id"]), DB_PATH)
    return reply({"ok": True})


# --------------------------------------------------------------------------
# Brew day
# --------------------------------------------------------------------------


async def list_logs(request: Request) -> JSONResponse:
    return reply(db.list_logs(DB_PATH))


async def create_log(request: Request) -> JSONResponse:
    b = await body(request)
    log_id = db.save_log(b["brew_date"], b.get("data") or {}, b.get("recipe_id"), b.get("recipe_snapshot"), None, DB_PATH)
    return reply({"id": log_id}, 201)


async def get_log(request: Request) -> JSONResponse:
    log = db.get_log(int(request.path_params["id"]), DB_PATH)
    return reply(log) if log else error("No such log", 404)


async def update_log(request: Request) -> JSONResponse:
    log_id = int(request.path_params["id"])
    old = db.get_log(log_id, DB_PATH)
    if old is None:
        return error("No such log", 404)
    b = await body(request)
    db.save_log(b["brew_date"], b.get("data") or {}, old["recipe_id"], old["recipe_snapshot"], log_id, DB_PATH)
    return reply({"id": log_id})


async def delete_log(request: Request) -> JSONResponse:
    db.delete_log(int(request.path_params["id"]), DB_PATH)
    return reply({"ok": True})


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


async def brew_day_endpoint(request: Request) -> JSONResponse:
    b = await body(request)
    try:
        return reply(brew_day(b.get("recipe") or {}, b.get("data") or {}))
    except (ZeroDivisionError, ValueError, TypeError, KeyError) as e:
        return error(f"Can't work out this brew plan: {e!r}", 422)


# --------------------------------------------------------------------------
# App
# --------------------------------------------------------------------------


async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
    return error(exc.detail, exc.status_code)


routes = [
    Route("/api/reference", get_reference),
    Route("/api/reference/reload", reload_reference, methods=["POST"]),
    Route("/api/defaults", get_defaults),
    Route("/api/normalize", normalize, methods=["POST"]),
    Route("/api/calculate", calculate, methods=["POST"]),
    Route("/api/recipes", list_recipes, methods=["GET"]),
    Route("/api/recipes", create_recipe, methods=["POST"]),
    Route("/api/recipes/{id:int}", get_recipe, methods=["GET"]),
    Route("/api/recipes/{id:int}", update_recipe, methods=["PUT"]),
    Route("/api/recipes/{id:int}", delete_recipe, methods=["DELETE"]),
    Route("/api/logs", list_logs, methods=["GET"]),
    Route("/api/logs", create_log, methods=["POST"]),
    Route("/api/logs/{id:int}", get_log, methods=["GET"]),
    Route("/api/logs/{id:int}", update_log, methods=["PUT"]),
    Route("/api/logs/{id:int}", delete_log, methods=["DELETE"]),
    Route("/api/brewday", brew_day_endpoint, methods=["POST"]),
]

class FreshStaticFiles(StaticFiles):
    """Static files that the browser re-checks on every load, so a rebuilt app shows up on a normal refresh."""

    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache"
        return response


if DIST.is_dir():
    routes.append(Mount("/", FreshStaticFiles(directory=DIST, html=True)))
else:

    async def no_build(request: Request) -> JSONResponse:
        return error("The React app hasn't been built yet (web/dist is missing). See web/README.md.", 404)

    routes.append(Route("/", no_build))

app = Starlette(routes=routes, exception_handlers={HTTPException: http_error})
