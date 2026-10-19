import math

import pandas as pd
import streamlit as st

from brewcalc import calcs, db, reference, ui
from brewcalc import recipe as rcp

ui.init_state()
k = ui.key
current: dict = st.session_state.recipe

grain_ref = reference.grains()
hop_ref = reference.hops()
yeast_ref = reference.yeasts()
style_ref = reference.styles()


def blank(v) -> bool:
    return v is None or (isinstance(v, float) and math.isnan(v))


# --------------------------------------------------------------------------
# Sidebar: open / save / import / export
# --------------------------------------------------------------------------

with st.sidebar:
    st.subheader("Recipe")
    saved = db.list_recipes()
    labels = {r["id"]: f"{r['name']}" + (f" · {r['style']}" if r["style"] else "") for r in saved}
    choice = st.selectbox("Saved recipes", list(labels), format_func=labels.get, index=None, placeholder="Open…")
    c1, c2 = st.columns(2)
    if c1.button("Open", disabled=choice is None, width="stretch"):
        ui.load_recipe(db.get_recipe(choice), choice)
        st.rerun()
    if c2.button("New", width="stretch"):
        ui.load_recipe(rcp.DEFAULT_RECIPE, None)
        st.rerun()

    st.divider()
    rid = st.session_state.recipe_id
    if ui.has_unsaved_changes():
        st.caption("Unsaved changes" if rid else "Not saved yet")
    c1, c2 = st.columns(2)
    if c1.button("Save", type="primary", width="stretch"):
        ui.mark_saved(db.save_recipe(current, rid))
        st.toast(f"Saved “{current['name']}”")
        st.rerun()
    if c2.button("Save as new", disabled=rid is None, width="stretch"):
        ui.mark_saved(db.save_recipe(current, None))
        st.toast("Saved a copy")
        st.rerun()

    with st.expander("Import / export"):
        st.download_button(
            "Download recipe (.json)",
            rcp.to_json(current),
            file_name=f"{current['name'] or 'recipe'}.json",
            mime="application/json",
            width="stretch",
        )
        upload = st.file_uploader("Open a recipe file", type="json", key=k("upload"))
        if upload is not None:
            try:
                ui.load_recipe(rcp.from_json(upload.getvalue().decode()), None)
                st.rerun()
            except ValueError as e:
                st.error(f"Couldn't read that file: {e}")
        if st.button("Load spreadsheet example", width="stretch"):
            ui.load_recipe(rcp.from_json(ui.EXAMPLE_PATH.read_text()), None)
            st.rerun()

    if rid is not None:
        with st.expander("Delete"):
            if st.button("Delete this recipe", type="secondary", width="stretch"):
                db.delete_recipe(rid)
                ui.load_recipe(rcp.DEFAULT_RECIPE, None)
                st.rerun()


# --------------------------------------------------------------------------
# Recipe basics
# --------------------------------------------------------------------------

st.title("Brewing Calculator")

c1, c2 = st.columns([3, 2])
name = c1.text_input("Recipe name", current["name"], key=k("name"))
styles = list(style_ref)
style = c2.selectbox(
    "Style",
    styles,
    index=styles.index(current["style"]) if current["style"] in style_ref else None,
    placeholder="Choose a style",
    key=k("style"),
)

c1, c2, c3 = st.columns(3)
b = current["batch"]
pre_boil = c1.number_input("Pre-boil volume (gal)", 0.0, 100.0, float(b["pre_boil_gal"]), 0.25, key=k("pre"))
post_boil = c2.number_input("Post-boil volume (gal)", 0.0, 100.0, float(b["post_boil_gal"]), 0.25, key=k("post"))
efficiency = c3.number_input("Mash efficiency (%)", 0.0, 100.0, float(b["efficiency_pct"]), 1.0, key=k("eff"))

summary_slot = st.container()


# --------------------------------------------------------------------------
# Ingredient editors (results are shown further down)
# --------------------------------------------------------------------------

# The editors' starting data must stay the same between reruns, or Streamlit
# discards in-progress edits. It's rebuilt only when a recipe is loaded.
if st.session_state.get("editor_version") != st.session_state.version:
    st.session_state.grain_df = pd.DataFrame(current["grains"], columns=["name", "lbs"])
    st.session_state.hop_df = pd.DataFrame(
        current["hops"], columns=["name", "oz", "form", "use", "minutes", "alpha_acid", "notes"]
    ).astype({"alpha_acid": "float"})
    st.session_state.editor_version = st.session_state.version

st.subheader("Grain bill")
grain_df = st.data_editor(
    st.session_state.grain_df,
    key=k("grains"),
    num_rows="dynamic",
    width="stretch",
    column_config={
        "name": st.column_config.SelectboxColumn("Grain", options=list(grain_ref), required=True, width="large"),
        "lbs": st.column_config.NumberColumn("Amount (lb)", min_value=0.0, step=0.25, format="%.2f", default=1.0),
    },
)
grains = [
    {"name": r.name, "lbs": 0.0 if blank(r.lbs) else float(r.lbs)}
    for r in grain_df.itertuples()
    if not blank(r.name)
]

grain_slot = st.container()  # breakdown table, filled in after calculating

st.subheader("Hops")
hop_df = st.data_editor(
    st.session_state.hop_df,
    key=k("hops"),
    num_rows="dynamic",
    width="stretch",
    column_config={
        "name": st.column_config.SelectboxColumn("Hop", options=list(hop_ref), required=True, width="medium"),
        "oz": st.column_config.NumberColumn("Amount (oz)", min_value=0.0, step=0.25, format="%.2f", default=1.0),
        "form": st.column_config.SelectboxColumn("Form", options=list(calcs.HOP_FORM_FACTOR), default="pellet"),
        "use": st.column_config.SelectboxColumn("Use", options=calcs.HOP_USES, default="boil"),
        "minutes": st.column_config.NumberColumn("Time (min)", min_value=0, step=1, default=60),
        "alpha_acid": st.column_config.NumberColumn(
            "AA % override", min_value=0.0, max_value=30.0, step=0.1, format="%.1f",
            help="Leave blank to use the average from the hop reference. Enter the value on your package.",
        ),
        "notes": st.column_config.TextColumn("Notes"),
    },
)
hops = [
    {
        "name": r.name,
        "oz": 0.0 if blank(r.oz) else float(r.oz),
        "form": r.form if not blank(r.form) else "pellet",
        "use": r.use if not blank(r.use) else "boil",
        "minutes": 0.0 if blank(r.minutes) else float(r.minutes),
        "alpha_acid": None if blank(r.alpha_acid) else float(r.alpha_acid),
        "notes": "" if blank(r.notes) else r.notes,
    }
    for r in hop_df.itertuples()
    if not blank(r.name)
]

hop_slot = st.container()

st.subheader("Yeast")
yeasts = list(yeast_ref)


def yeast_label(name: str) -> str:
    """Yeast name plus manufacturer and code, e.g. "London Ale (White Labs WLP013)".
    Anything the name already says (like a code in a label) is left out."""
    y = yeast_ref[name]
    parts = [t for t in (y["lab"], y["code"]) if t and t not in name]
    return f"{name} ({' '.join(parts)})" if parts else name


c1, c2 = st.columns([3, 1])
yeast = c1.selectbox(
    "Yeast",
    yeasts,
    index=yeasts.index(current["yeast"]) if current["yeast"] in yeast_ref else None,
    format_func=yeast_label,
    placeholder="Choose a yeast",
    key=k("yeast"),
    label_visibility="collapsed",
)
att_override = c2.number_input(
    "Attenuation override (%)",
    0.0,
    100.0,
    current["attenuation_pct"],
    0.5,
    placeholder="from yeast",
    key=k("att"),
    label_visibility="collapsed",
    help="Leave blank to use the yeast's average attenuation.",
)
if yeast:
    y = yeast_ref[yeast]
    cols = st.columns(4)
    att_help = f"Range {y['attenuation_range']}" if y["attenuation_range"] else None
    cols[0].metric("Attenuation", f"{y['attenuation']:g}%", help=att_help)
    cols[1].metric("Flocculation", y["flocculation"] or "–")
    cols[2].metric("Temp range", f"{y['temp_range_f']} °F" if y["temp_range_f"] else "–")
    cols[3].metric("Lab", y["lab"] or "–", help=f"{y['type']} · {y['form']}")
    if y["notes"]:
        st.caption(y["notes"])

st.subheader("Mash")
m = current["mash"]
c1, c2, c3 = st.columns(3)
thickness = c1.number_input("Mash thickness (qt/lb)", 0.5, 4.0, float(m["thickness_qt_per_lb"]), 0.05, key=k("thick"))
grain_temp = c2.number_input("Grain temp (°F)", 0.0, 120.0, float(m["grain_temp_f"]), 1.0, key=k("gtemp"))
mash_temp = c3.number_input("Mash temp (°F)", 100.0, 180.0, float(m["mash_temp_f"]), 1.0, key=k("mtemp"))
steps_text = st.text_input(
    "Infusion step temps (°F)",
    ", ".join(f"{t:g}" for t in m["step_temps_f"]),
    key=k("steps"),
    help="Boiling-water infusions after the main rest, comma separated. E.g. 170 for a mash-out.",
    placeholder="e.g. 170",
)
step_temps = []
for part in steps_text.replace(";", ",").split(","):
    try:
        if part.strip():
            step_temps.append(float(part))
    except ValueError:
        st.warning(f"Ignoring step temperature “{part.strip()}”: not a number")
with st.expander("Equipment settings"):
    c1, c2, c3, c4 = st.columns(4)
    boil_temp = c1.number_input("Boiling water (°F)", 180.0, 212.0, float(m["boiling_water_temp_f"]), 1.0, key=k("tw"))
    temp_loss = c2.number_input(
        "Temp drop before each step (°F)", 0.0, 20.0, float(m["rest_temp_loss_f"]), 0.5, key=k("loss"),
        help="How much the mash cools during a rest before the next infusion.",
    )
    absorption = c3.number_input(
        "Grain absorption (gal/lb)", 0.0, 0.3, float(m["grain_absorption_gal_per_lb"]), 0.005, format="%.3f",
        key=k("abs"),
    )
    deadspace = c4.number_input("Mash tun deadspace (gal)", 0.0, 5.0, float(m["mash_tun_deadspace_gal"]), 0.05,
                                key=k("dead"))

mash_slot = st.container()

notes = st.text_area("Recipe notes", current["notes"], key=k("notes"))


# --------------------------------------------------------------------------
# Calculate
# --------------------------------------------------------------------------

current = {
    "name": name,
    "style": style or "",
    "batch": {"pre_boil_gal": pre_boil, "post_boil_gal": post_boil, "efficiency_pct": efficiency},
    "yeast": yeast or "",
    "attenuation_pct": att_override,
    "grains": grains,
    "hops": hops,
    "mash": {
        "thickness_qt_per_lb": thickness,
        "grain_temp_f": grain_temp,
        "mash_temp_f": mash_temp,
        "step_temps_f": step_temps,
        "boiling_water_temp_f": boil_temp,
        "rest_temp_loss_f": temp_loss,
        "grain_absorption_gal_per_lb": absorption,
        "mash_tun_deadspace_gal": deadspace,
    },
    "notes": notes,
}
st.session_state.recipe = current
res = rcp.calculate(current)
g_in, h_in, batch, _ = rcp.to_inputs(current)
target = reference.find_style(style)


with summary_slot.container(border=True):
    cols = st.columns(3) + st.columns(3)
    cols[0].metric("OG", f"{res.og:.3f}")
    cols[0].caption(ui.range_check(res.og, target and target.og, "{:.3f}"))
    cols[1].metric("FG", f"{res.fg:.3f}", help=f"{batch.attenuation_pct:g}% attenuation")
    cols[1].caption(ui.range_check(res.fg, target and target.fg, "{:.3f}"))
    cols[2].metric("ABV", f"{res.abv:.1f}%", help=f"Alternate formula: {res.abv_alternate:.2f}%")
    cols[2].caption(ui.range_check(res.abv, target and target.abv, "{:g}"))
    cols[3].metric("IBU", f"{res.ibu:.0f}", help="Tinseth")
    cols[3].caption(ui.range_check(res.ibu, target and target.ibu, "{:g}"))
    cols[4].metric("SRM", f"{res.srm:.1f}", help="Morey")
    cols[4].caption(ui.range_check(res.srm, target and target.srm, "{:g}"))
    cols[4].markdown(
        ui.srm_swatch(calcs.srm_to_hex(res.srm), calcs.srm_color_name(res.srm, reference.srm_colors())),
        unsafe_allow_html=True,
    )
    cols[5].metric("Pre-boil SG", f"{res.pre_boil_gravity:.3f}")
    unknown = [g["name"] for g in grains if g["name"] not in grain_ref]
    if unknown:
        st.warning(f"Not in the grain reference, so left out: {', '.join(unknown)}")

with grain_slot:
    if g_in:
        total = res.total_grain_lbs or 1
        pts_scale = batch.efficiency_pct / 100 * batch.pre_boil_gal / batch.post_boil_gal if batch.post_boil_gal else 0
        st.dataframe(
            pd.DataFrame(
                {
                    "Grain": [g.name for g in g_in],
                    "°L": [g.lovibond for g in g_in],
                    "PPG": [g.ppg for g in g_in],
                    "%": [g.lbs / total * 100 for g in g_in],
                    "OG points": [g.ppg * g.lbs / batch.pre_boil_gal * pts_scale if batch.pre_boil_gal else 0 for g in g_in],
                    "MCU": [g.lbs * g.lovibond / batch.post_boil_gal if batch.post_boil_gal else 0 for g in g_in],
                }
            ),
            hide_index=True,
            width="stretch",
            column_config={
                "°L": st.column_config.NumberColumn(format="%g"),
                "PPG": st.column_config.NumberColumn(format="%g"),
                "%": st.column_config.ProgressColumn(format="%.1f%%", min_value=0, max_value=100),
                "OG points": st.column_config.NumberColumn(format="%.1f"),
                "MCU": st.column_config.NumberColumn(format="%.2f"),
            },
        )
        st.caption(f"Total {res.total_grain_lbs:g} lb · max {res.max_points_per_gal:.1f} points/gal pre-boil at 100%")

with hop_slot:
    if h_in:
        bg = calcs.boil_gravity_points(g_in, batch)
        st.dataframe(
            pd.DataFrame(
                {
                    "Hop": [h.name for h in h_in],
                    "Use": [h.use for h in h_in],
                    "Time": [h.minutes for h in h_in],
                    "AA %": [h.alpha_acid for h in h_in],
                    "Utilization": [
                        calcs.tinseth_utilization(h.minutes, bg, h.form) if h.use in calcs.BITTERING_USES else 0
                        for h in h_in
                    ],
                    "IBU": res.hop_ibus,
                }
            ),
            hide_index=True,
            width="stretch",
            column_config={
                "Time": st.column_config.NumberColumn(format="%g min"),
                "AA %": st.column_config.NumberColumn(format="%.1f"),
                "Utilization": st.column_config.NumberColumn(format="%.3f"),
                "IBU": st.column_config.NumberColumn(format="%.1f"),
            },
        )
        missing = [h["name"] for h in hops if h["name"] not in hop_ref and h["alpha_acid"] is None]
        if missing:
            st.warning(f"No reference alpha acid for {', '.join(missing)}; enter an AA % override.")

with mash_slot:
    cols = st.columns(4)
    cols[0].metric("Strike water temp", f"{res.strike_water_temp_f:.1f} °F")
    cols[1].metric("Strike water", f"{res.strike_water_qt:.1f} qt", help=f"{res.strike_water_qt / 4:.2f} gal")
    for i, step in enumerate(res.infusions[:2], start=2):
        cols[i].metric(
            f"Boiling water → {step.target_temp_f:g} °F",
            f"{step.boiling_water_qt:.1f} qt",
            help=f"Assumes the mash has cooled to {step.start_temp_f:g} °F",
        )
    for step in res.infusions[2:]:
        st.metric(f"Boiling water → {step.target_temp_f:g} °F", f"{step.boiling_water_qt:.1f} qt")
    mash_water_gal = (res.infusions[-1].total_mash_water_qt if res.infusions else res.strike_water_qt) / 4
    st.info(
        f"**Sparge water: {res.sparge_water_gal:.2f} gal** "
        f"(total water {mash_water_gal + res.sparge_water_gal:.2f} gal: {mash_water_gal:.2f} in the mash, "
        f"{res.total_grain_lbs * absorption:.2f} absorbed by grain)"
    )
