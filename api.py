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

from pathlib import Path

from starlette.applications import Starlette
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from brewcalc import calcs, db, reference
from brewcalc import recipe as rcp
from brewcalc.service import (  # noqa: F401  (shared with the browser version)
    analyze,
    brew_day,
    clean,
    num,
    style_dict,
    style_target,
    yeast_label,
)

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "web" / "dist"
EXAMPLE_PATH = ROOT / "data" / "example_recipe.json"
DB_PATH = db.DEFAULT_DB  # tests point this at a temporary file




# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


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
