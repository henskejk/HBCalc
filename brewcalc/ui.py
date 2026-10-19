"""Streamlit session helpers shared by the pages."""

from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

from brewcalc import recipe as rcp

EXAMPLE_PATH = Path(__file__).resolve().parent.parent / "data" / "example_recipe.json"


def init_state() -> None:
    if "recipe" not in st.session_state:
        load_recipe(rcp.from_json(EXAMPLE_PATH.read_text()), None)


def load_recipe(recipe: dict, recipe_id: int | None) -> None:
    """Make `recipe` the one being edited.

    Widget keys include a version number, so bumping it makes every widget
    on the calculator page start fresh from the loaded values.
    """
    recipe = rcp.normalize(recipe)
    st.session_state.recipe = recipe
    st.session_state.recipe_id = recipe_id
    st.session_state.saved_json = rcp.to_json(recipe) if recipe_id else None
    st.session_state.version = st.session_state.get("version", 0) + 1


def key(name: str) -> str:
    """Widget key tied to the currently loaded recipe."""
    return f"{name}_v{st.session_state.version}"


def has_unsaved_changes() -> bool:
    return rcp.to_json(st.session_state.recipe) != st.session_state.saved_json


def mark_saved(recipe_id: int) -> None:
    st.session_state.recipe_id = recipe_id
    st.session_state.saved_json = rcp.to_json(st.session_state.recipe)


def srm_swatch(hex_color: str, label: str) -> str:
    """A pint glass filled with beer of the given color, plus its color name."""
    # Shaker pint: rim from x=2 to 22 at the top, tapering to x=4.5..19.5 at
    # the base. The beer and foam follow the same taper.
    glass = (
        f'<svg width="34" height="46" viewBox="0 0 24 34" role="img" aria-label="Beer color: {label}">'
        f'<path d="M2.48 7 L21.52 7 L19.5 32 Q19.4 33 18.4 33 L5.6 33 Q4.6 33 4.5 32 Z" fill="{hex_color}"/>'
        '<path d="M2.12 2.5 L21.88 2.5 L21.52 7 L2.48 7 Z" fill="#FFF8E7"/>'
        '<g fill="#FFF8E7">'
        '<circle cx="4.2" cy="2.6" r="1.6"/><circle cx="7.6" cy="2.1" r="1.8"/>'
        '<circle cx="11.2" cy="2.5" r="1.7"/><circle cx="14.8" cy="2.0" r="1.8"/>'
        '<circle cx="18.2" cy="2.4" r="1.7"/><circle cx="20.4" cy="2.8" r="1.4"/>'
        "</g>"
        '<path d="M5 9 L6.6 30" stroke="#fff" stroke-opacity=".35" stroke-width="1.1" stroke-linecap="round"/>'
        '<path d="M2 1 L22 1 L19.5 32 Q19.4 33 18.4 33 L5.6 33 Q4.6 33 4.5 32 Z" fill="none" '
        'stroke="rgba(128,128,128,.7)" stroke-width=".9" stroke-linejoin="round"/>'
        "</svg>"
    )
    return (
        f'<div style="display:flex;align-items:center;gap:.6rem;margin-top:.25rem">'
        f"{glass}<span>{label}</span></div>"
    )


def range_check(value: float, bounds: tuple[float, float] | None, fmt: str) -> str:
    """Caption text like '✅ 5.5–7.5' for a style range."""
    if not bounds:
        return ""
    lo, hi = bounds
    mark = "✅" if lo <= value <= hi else "⚠️"
    return f"{mark} style {fmt.format(lo)}–{fmt.format(hi)}"


def dumps(obj) -> str:
    return json.dumps(obj, indent=2)
