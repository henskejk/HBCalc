import pandas as pd
import streamlit as st

from brewcalc import reference

st.title("Ingredients")
st.caption(
    "Reference data from your spreadsheet, stored in the `data/` folder as CSV files. "
    "Edit those files to add or change ingredients, then click Reload."
)

query = st.text_input("Search", placeholder="e.g. crystal, citra, WLP001, stout").strip().lower()


def show(df: pd.DataFrame, **config) -> None:
    if query:
        mask = df.astype(str).apply(lambda col: col.str.lower().str.contains(query, regex=False)).any(axis=1)
        df = df[mask]
    st.dataframe(df, hide_index=True, width="stretch", column_config=config)
    st.caption(f"{len(df)} shown")


tabs = st.tabs(["Grains", "Hops", "Yeast", "Styles"])
with tabs[0]:
    show(
        pd.DataFrame(reference.grains().values()),
        name="Grain", lovibond=st.column_config.NumberColumn("°L", format="%g"),
        ppg=st.column_config.NumberColumn("PPG", format="%g"), origin="Origin",
        description=st.column_config.TextColumn("Description", width="large"), notes="Notes",
    )
with tabs[1]:
    show(pd.DataFrame(reference.hops().values()), name="Hop", type="Type", use="Recommended use",
         alpha_acid=st.column_config.NumberColumn("Avg alpha acid %", format="%g"))
with tabs[2]:
    show(
        pd.DataFrame(reference.yeasts().values()),
        name="Yeast", code="Code", lab="Lab", type="Type", form="Form",
        attenuation=st.column_config.NumberColumn("Avg atten. %", format="%g"),
        flocculation="Flocc.", temp_range_f="Temp (°F)", best_for="Best for",
        notes=st.column_config.TextColumn("Notes", width="large"),
        label=None, attenuation_range=None, alcohol_tolerance=None, temp_min_f=None, temp_max_f=None, issues=None,
    )
with tabs[3]:
    def span(r, fmt):
        return f"{r[0]:{fmt}}–{r[1]:{fmt}}" if r else ""

    rows = [
        {
            "Style": s.name,
            "ABV": span(s.abv, "g"),
            "IBU": span(s.ibu, "g"),
            "OG": span(s.og, ".3f"),
            "FG": span(s.fg, ".3f"),
            "SRM": span(s.srm, "g"),
        }
        for s in reference.styles().values()
    ]
    show(pd.DataFrame(rows))

if st.button("Reload data files"):
    for f in (reference.grains, reference.hops, reference.yeasts, reference.styles, reference.srm_colors):
        f.cache_clear()
    st.rerun()
