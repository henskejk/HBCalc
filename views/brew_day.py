import math
from datetime import date

import pandas as pd
import streamlit as st

from brewcalc import calcs, db, ui
from brewcalc import recipe as rcp

ui.init_state()

EMPTY_LOG = {
    "pre_boil_sg": None,
    "pre_boil_gal": None,
    "og": None,
    "post_boil_gal": None,
    "fg": None,
    "mash_readings": [],
    "notes": "",
}


def open_log(log_id, brew_date, data, recipe_id, snapshot):
    st.session_state.log = {
        "id": log_id,
        "brew_date": brew_date,
        "data": {**EMPTY_LOG, **data},
        "recipe_id": recipe_id,
        "snapshot": snapshot,
    }
    st.session_state.log_version = st.session_state.get("log_version", 0) + 1


def blank(v) -> bool:
    return v is None or (isinstance(v, float) and math.isnan(v))


st.title("Brew Day")

# --------------------------------------------------------------------------
# Choose a log
# --------------------------------------------------------------------------

with st.sidebar:
    st.subheader("Brew logs")
    logs = db.list_logs()
    labels = {l["id"]: f"{l['brew_date']} · {l['recipe_name'] or 'no recipe'}" for l in logs}
    choice = st.selectbox("Past brews", list(labels), format_func=labels.get, index=None, placeholder="Open…")
    if st.button("Open log", disabled=choice is None, width="stretch"):
        log = db.get_log(choice)
        open_log(log["id"], log["brew_date"], log["data"], log["recipe_id"], log["recipe_snapshot"])
        st.rerun()
    recipe_name = st.session_state.recipe["name"]
    if st.button(f"New log for “{recipe_name}”", type="primary", width="stretch"):
        open_log(None, date.today().isoformat(), {}, st.session_state.recipe_id, st.session_state.recipe)
        st.rerun()
    st.caption("New logs use the recipe open on the Calculator page, as it is right now.")

log = st.session_state.get("log")
if not log:
    st.info("Start a new log from the sidebar, or open a past one.")
    st.stop()

v = st.session_state.log_version
recipe = rcp.normalize(log["snapshot"] or {})
plan = rcp.calculate(recipe)
grains, hops, batch, mash = rcp.to_inputs(recipe)
d = log["data"]

st.subheader(recipe["name"] + (f" · {recipe['style']}" if recipe["style"] else ""))
if log["id"] is None:
    st.caption("Not saved yet")

# --------------------------------------------------------------------------
# Brew plan
# --------------------------------------------------------------------------

with st.expander("Brew plan", expanded=log["id"] is None):
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Water**")
        lines = [
            f"- Strike: **{plan.strike_water_qt:.1f} qt** at **{plan.strike_water_temp_f:.1f} °F**",
            f"- Mash at {mash.mash_temp_f:g} °F",
        ]
        lines += [f"- Add **{s.boiling_water_qt:.1f} qt** boiling water → {s.target_temp_f:g} °F" for s in plan.infusions]
        lines += [
            f"- Sparge: **{plan.sparge_water_gal:.2f} gal**",
            f"- Target pre-boil: {batch.pre_boil_gal:g} gal at {plan.pre_boil_gravity:.3f}",
        ]
        st.markdown("\n".join(lines))
        st.markdown("**Grains**")
        st.markdown("\n".join(f"- {g.lbs:g} lb {g.name}" for g in grains) or "–")
    with c2:
        st.markdown("**Hops**")
        # In the order they go in: first wort, boil (longest first), then after the boil.
        order = {"first wort": 0, "boil": 1, "flameout": 2, "whirlpool": 3, "dry hop": 4}
        hop_lines = []
        for h in sorted(hops, key=lambda h: (order.get(h.use, 99), -h.minutes)):
            when = f"{h.minutes:g} min" if h.use == "boil" else h.use
            hop_lines.append(f"- {when}: {h.oz:g} oz {h.name} ({h.alpha_acid:g}% {h.form})")
        st.markdown("\n".join(hop_lines) or "–")
        st.markdown("**Yeast**")
        st.markdown(f"- {recipe['yeast'] or '–'} ({batch.attenuation_pct:g}% attenuation)")

# --------------------------------------------------------------------------
# Measurements
# --------------------------------------------------------------------------

brew_date = st.date_input("Brew date", date.fromisoformat(log["brew_date"]), key=f"date_{v}")

st.markdown("**Mash temperature readings**")
readings_df = st.data_editor(
    pd.DataFrame(d["mash_readings"], columns=["time", "temp_f", "notes"]).astype({"temp_f": "float"}),
    key=f"readings_{v}",
    num_rows="dynamic",
    width="stretch",
    column_config={
        "time": st.column_config.TextColumn("Time", help="Clock time or minutes into the mash"),
        "temp_f": st.column_config.NumberColumn("Temp (°F)", format="%.1f"),
        "notes": st.column_config.TextColumn("Notes"),
    },
)


def num_input(label, value, step, fmt, key):
    return st.number_input(label, value=value, step=step, format=fmt, placeholder="–", key=f"{key}_{v}")


st.markdown("**Gravity and volume**")
c1, c2, c3, c4, c5 = st.columns(5)
with c1:
    pre_sg = num_input("Pre-boil SG", d["pre_boil_sg"], 0.001, "%.3f", "presg")
with c2:
    pre_gal = num_input("Pre-boil volume (gal)", d["pre_boil_gal"], 0.25, "%.2f", "pregal")
with c3:
    og = num_input("OG", d["og"], 0.001, "%.3f", "og")
with c4:
    post_gal = num_input("Post-boil volume (gal)", d["post_boil_gal"], 0.25, "%.2f", "postgal")
with c5:
    fg = num_input("FG", d["fg"], 0.001, "%.3f", "fg")

notes = st.text_area("Notes", d["notes"], key=f"notes_{v}", placeholder="Tasting notes, what to change next time…")

# --------------------------------------------------------------------------
# Actual vs planned
# --------------------------------------------------------------------------

st.markdown("**Actual vs planned**")
cols = st.columns(5)
if pre_sg:
    eff = calcs.actual_efficiency(pre_sg, grains, pre_gal or batch.pre_boil_gal)
    cols[0].metric("Mash efficiency", f"{eff:.1f}%", f"{eff - batch.efficiency_pct:+.1f} vs plan",
                   help="From pre-boil SG and pre-boil volume (planned volume if not entered)")
else:
    cols[0].metric("Mash efficiency", "–", help="Enter pre-boil SG")
if og:
    cols[1].metric("OG", f"{og:.3f}", f"{(og - plan.og) * 1000:+.0f} pts vs plan")
if fg:
    cols[2].metric("FG", f"{fg:.3f}", f"{(fg - plan.fg) * 1000:+.0f} pts vs plan", delta_color="inverse")
if og and fg:
    cols[3].metric("ABV", f"{calcs.abv(og, fg):.1f}%", f"{calcs.abv(og, fg) - plan.abv:+.1f} vs plan")
    if og > 1:
        att = (og - fg) / (og - 1) * 100
        cols[4].metric("Apparent attenuation", f"{att:.0f}%", f"{att - batch.attenuation_pct:+.0f} vs yeast avg")

# --------------------------------------------------------------------------
# Save
# --------------------------------------------------------------------------

data = {
    "pre_boil_sg": pre_sg,
    "pre_boil_gal": pre_gal,
    "og": og,
    "post_boil_gal": post_gal,
    "fg": fg,
    "mash_readings": [
        {"time": "" if blank(r.time) else r.time, "temp_f": None if blank(r.temp_f) else r.temp_f,
         "notes": "" if blank(r.notes) else r.notes}
        for r in readings_df.itertuples()
    ],
    "notes": notes,
}
c1, c2, _ = st.columns([1, 1, 3])
if c1.button("Save log", type="primary", width="stretch"):
    log_id = db.save_log(brew_date.isoformat(), data, log["recipe_id"], log["snapshot"], log["id"])
    log.update(id=log_id, brew_date=brew_date.isoformat(), data=data)
    st.toast("Brew log saved")
    st.rerun()
if log["id"] is not None and c2.button("Delete log", width="stretch"):
    db.delete_log(log["id"])
    del st.session_state.log
    st.rerun()
