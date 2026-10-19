"""Recipes as plain dicts (easy to save as JSON), and conversion to calc inputs.

A recipe looks like data/example_recipe.json. Ingredient values such as
Lovibond or alpha acid come from the reference data unless the recipe
overrides them (alpha_acid / attenuation_pct set to a number).
"""

from __future__ import annotations

import copy
import json

from brewcalc import calcs, reference

DEFAULT_RECIPE: dict = {
    "name": "New recipe",
    "style": "",
    "base_style": "",  # for styles whose ranges depend on an underlying base beer
    # post_boil_gal is the target batch volume (what you want after the trub is left behind). pre_boil_gal is always
    # post_boil_gal + boil_off_gal + trub_loss_gal; the calculator itself only reads pre_boil_gal and post_boil_gal.
    "batch": {"pre_boil_gal": 6.5, "post_boil_gal": 5.5, "boil_off_gal": 0.5, "trub_loss_gal": 0.5, "efficiency_pct": 65.0},
    "yeast": "",
    "attenuation_pct": None,
    "grains": [],
    "hops": [],
    # Free-text additions that do not affect gravity or colour: {"name", "amount", "unit", "notes"} (all strings).
    "additions": [],
    "mash": {
        "thickness_qt_per_lb": 1.25,
        "grain_temp_f": 68.0,
        "mash_temp_f": 152.0,
        "step_temps_f": [],
        "boiling_water_temp_f": 210.0,
        "rest_temp_loss_f": 3.0,
        "grain_absorption_gal_per_lb": 0.125,
        "mash_tun_deadspace_gal": 0.0,
    },
    # "basic" = strike water plus boiling-water infusions (the "mash" settings above);
    # "decoction" = the stepped schedule below, reached by pulling and boiling part of the mash.
    "mash_type": "basic",
    "decoction_steps": [
        {"name": "Protein rest", "temp_f": 131.0, "minutes": 20.0},
        {"name": "Saccharification", "temp_f": 152.0, "minutes": 60.0},
        {"name": "Mash out", "temp_f": 170.0, "minutes": 10.0},
    ],
    "notes": "",
}

# Used when the recipe has no yeast selected.
FALLBACK_ATTENUATION = 75.0


def normalize(recipe: dict) -> dict:
    """Fill in any missing keys from DEFAULT_RECIPE."""
    out = copy.deepcopy(DEFAULT_RECIPE)
    for key, value in recipe.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key].update(value)
        else:
            out[key] = value
    _sync_volume_losses(out["batch"], recipe.get("batch") or {})
    found = reference.find_style(out["style"])  # old or un-numbered style names become the BJCP 2021 name
    if found:
        out["style"] = found.name
    base = reference.find_style(out["base_style"])
    out["base_style"] = base.name if base else ""
    return out


def _sync_volume_losses(batch: dict, given: dict) -> None:
    """Keep boil-off + trub loss equal to pre-boil minus post-boil volume.

    Older recipes (and the Streamlit app) only store the two volumes, so the whole difference is shown as boil-off.
    If the volumes were edited elsewhere, trub loss is kept and boil-off takes up the difference.
    """
    loss = max(0.0, float(batch["pre_boil_gal"]) - float(batch["post_boil_gal"]))
    if given and "boil_off_gal" not in given and "trub_loss_gal" not in given:
        batch["boil_off_gal"], batch["trub_loss_gal"] = loss, 0.0
        return
    trub = min(float(batch.get("trub_loss_gal") or 0), loss)
    batch["trub_loss_gal"], batch["boil_off_gal"] = trub, loss - trub


def from_json(text: str) -> dict:
    return normalize(json.loads(text))


def to_json(recipe: dict) -> str:
    return json.dumps(recipe, indent=2)


def attenuation(recipe: dict) -> float:
    if recipe.get("attenuation_pct"):  # blank or 0 means "use the yeast's average"
        return float(recipe["attenuation_pct"])
    yeast = reference.yeasts().get(recipe.get("yeast", ""))
    return yeast["attenuation"] if yeast else FALLBACK_ATTENUATION


def hop_alpha_acid(hop: dict) -> float:
    if hop.get("alpha_acid") is not None:
        return float(hop["alpha_acid"])
    ref = reference.hops().get(hop["name"])
    return ref["alpha_acid"] if ref else 0.0


def to_inputs(recipe: dict) -> tuple[list[calcs.Grain], list[calcs.Hop], calcs.Batch, calcs.Mash]:
    """Build calculator inputs. Unknown ingredients are skipped."""
    recipe = normalize(recipe)
    grain_ref = reference.grains()
    grains = [
        calcs.Grain(g["name"], float(g["lbs"] or 0), grain_ref[g["name"]]["lovibond"], grain_ref[g["name"]]["ppg"])
        for g in recipe["grains"]
        if g.get("name") in grain_ref
    ]
    hops = [
        calcs.Hop(
            name=h["name"],
            oz=float(h.get("oz") or 0),
            alpha_acid=hop_alpha_acid(h),
            minutes=float(h.get("minutes") or 0),
            form=h.get("form") or "pellet",
            use=h.get("use") or "boil",
        )
        for h in recipe["hops"]
        if h.get("name")
    ]
    b = recipe["batch"]
    # OG, IBU and color are worked out on the wort at the end of the boil: the target batch volume plus the trub
    # that stays behind in the kettle. Trub is lost after the boil, so it doesn't change the sugar concentration.
    kettle_post_boil = float(b["post_boil_gal"]) + float(b.get("trub_loss_gal") or 0)
    batch = calcs.Batch(
        pre_boil_gal=float(b["pre_boil_gal"]),
        post_boil_gal=kettle_post_boil,
        efficiency_pct=float(b["efficiency_pct"]),
        attenuation_pct=attenuation(recipe),
    )
    mash = calcs.Mash(**recipe["mash"])
    return grains, hops, batch, mash


def calculate(recipe: dict) -> calcs.RecipeResult:
    return calcs.calculate(*to_inputs(recipe))
