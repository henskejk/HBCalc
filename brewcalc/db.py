"""Saved recipes and brew-day logs, stored in a local SQLite file."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parent.parent / "brewing.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS recipes (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    style TEXT,
    data TEXT NOT NULL,          -- the recipe as JSON
    created TEXT NOT NULL,
    updated TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS brew_logs (
    id INTEGER PRIMARY KEY,
    recipe_id INTEGER REFERENCES recipes(id) ON DELETE SET NULL,
    brew_date TEXT NOT NULL,
    data TEXT NOT NULL,          -- measurements, readings and notes as JSON
    recipe_snapshot TEXT,        -- the recipe as it was on brew day
    created TEXT NOT NULL,
    updated TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


@contextmanager
def connect(path: Path = DEFAULT_DB):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# --- recipes ---------------------------------------------------------------


def list_recipes(path: Path = DEFAULT_DB) -> list[dict]:
    with connect(path) as conn:
        rows = conn.execute("SELECT id, name, style, updated FROM recipes ORDER BY updated DESC").fetchall()
    return [dict(r) for r in rows]


def get_recipe(recipe_id: int, path: Path = DEFAULT_DB) -> dict | None:
    with connect(path) as conn:
        row = conn.execute("SELECT data FROM recipes WHERE id = ?", (recipe_id,)).fetchone()
    return json.loads(row["data"]) if row else None


def save_recipe(recipe: dict, recipe_id: int | None = None, path: Path = DEFAULT_DB) -> int:
    """Insert a new recipe, or update the one with recipe_id. Returns the id."""
    data = json.dumps(recipe)
    now = _now()
    with connect(path) as conn:
        if recipe_id is None:
            cur = conn.execute(
                "INSERT INTO recipes (name, style, data, created, updated) VALUES (?, ?, ?, ?, ?)",
                (recipe["name"], recipe.get("style", ""), data, now, now),
            )
            return cur.lastrowid
        conn.execute(
            "UPDATE recipes SET name = ?, style = ?, data = ?, updated = ? WHERE id = ?",
            (recipe["name"], recipe.get("style", ""), data, now, recipe_id),
        )
        return recipe_id


def delete_recipe(recipe_id: int, path: Path = DEFAULT_DB) -> None:
    with connect(path) as conn:
        conn.execute("DELETE FROM recipes WHERE id = ?", (recipe_id,))


# --- brew logs -------------------------------------------------------------


def list_logs(path: Path = DEFAULT_DB) -> list[dict]:
    with connect(path) as conn:
        rows = conn.execute(
            """SELECT l.id, l.recipe_id, l.brew_date, l.updated,
                      COALESCE(r.name, json_extract(l.recipe_snapshot, '$.name')) AS recipe_name
               FROM brew_logs l LEFT JOIN recipes r ON r.id = l.recipe_id
               ORDER BY l.brew_date DESC, l.id DESC"""
        ).fetchall()
    return [dict(r) for r in rows]


def get_log(log_id: int, path: Path = DEFAULT_DB) -> dict | None:
    with connect(path) as conn:
        row = conn.execute("SELECT * FROM brew_logs WHERE id = ?", (log_id,)).fetchone()
    if not row:
        return None
    out = dict(row)
    out["data"] = json.loads(out["data"])
    out["recipe_snapshot"] = json.loads(out["recipe_snapshot"]) if out["recipe_snapshot"] else None
    return out


def save_log(
    brew_date: str,
    data: dict,
    recipe_id: int | None,
    recipe_snapshot: dict | None,
    log_id: int | None = None,
    path: Path = DEFAULT_DB,
) -> int:
    now = _now()
    snapshot = json.dumps(recipe_snapshot) if recipe_snapshot else None
    with connect(path) as conn:
        if log_id is None:
            cur = conn.execute(
                """INSERT INTO brew_logs (recipe_id, brew_date, data, recipe_snapshot, created, updated)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (recipe_id, brew_date, json.dumps(data), snapshot, now, now),
            )
            return cur.lastrowid
        conn.execute(
            "UPDATE brew_logs SET brew_date = ?, data = ?, updated = ? WHERE id = ?",
            (brew_date, json.dumps(data), now, log_id),
        )
        return log_id


def delete_log(log_id: int, path: Path = DEFAULT_DB) -> None:
    with connect(path) as conn:
        conn.execute("DELETE FROM brew_logs WHERE id = ?", (log_id,))
