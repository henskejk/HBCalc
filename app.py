"""Brewing calculator. Start with:  streamlit run app.py"""

import streamlit as st

st.set_page_config(page_title="Henske Brewing Calculator", page_icon="🍺", layout="wide")

st.navigation(
    [
        st.Page("views/calculator.py", title="Calculator", icon="🧮", default=True),
        st.Page("views/brew_day.py", title="Brew Day", icon="📋"),
        st.Page("views/ingredients.py", title="Ingredients", icon="🌾"),
    ]
).run()
