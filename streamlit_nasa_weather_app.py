import streamlit as st
import pandas as pd
import numpy as np
import xarray as xr
import plotly.express as px
import plotly.graph_objects as go
import folium
from streamlit_folium import st_folium
from folium.plugins import Draw
import os
from datetime import datetime
from pathlib import Path

# --------------------------
# Page Setup
# --------------------------
st.set_page_config(page_title="WeatherWise", layout="wide")

# --------------------------
# GitHub Dataset URL (raw file)
# --------------------------
DATA_URL = "https://raw.githubusercontent.com/Shreya-pixel-byte/WeatherWise/main/global_weather.xlsx"

# --------------------------
# Preprocessing Function
# --------------------------
@st.cache_data
def load_and_preprocess(url: str):
    # Detect file type
    if url.endswith(".csv"):
        df = pd.read_csv(url)
    elif url.endswith(".xlsx"):
        try:
            df = pd.read_excel(url, sheet_name=0)  # read first sheet
        except ImportError:
            st.error("⚠️ Missing dependency `openpyxl`. Add it to requirements.txt or convert Excel to CSV.")
            st.stop()
    else:
        st.error("Unsupported file format. Please use CSV or Excel.")
        st.stop()

    # --- Fix time column ---
    if "time" not in df.columns:
        if "date" in df.columns:
            df.rename(columns={"date": "time"}, inplace=True)
        elif "Date" in df.columns:
            df.rename(columns={"Date": "time"}, inplace=True)
        elif {"year","month","day"}.issubset(df.columns):
            df["time"] = pd.to_datetime(df[["year","month","day"]])
        else:
            st.error(f"Dataset columns are {list(df.columns)} — please ensure there is a date or time column.")
            st.stop()

    # --- Parse datetime ---
    df["time"] = pd.to_datetime(df["time"], errors="coerce")
    df = df.dropna(subset=["time"])
    df["date"] = df["time"].dt.date
    df["doy"] = df["time"].dt.dayofyear

    return df

# Load dataset
df_all = load_and_preprocess(DATA_URL)

# --------------------------
# Session State for Page Navigation
# --------------------------
if "page" not in st.session_state:
    st.session_state.page = "splash"  # default first page

# --------------------------
# Splash Page
# --------------------------
if st.session_state.page == "splash":
    st.markdown("<h1 style='text-align: center; font-size: 60px;'>WeatherWise</h1>", unsafe_allow_html=True)
    st.markdown("<h3 style='text-align: center;'>Check the likelihood of weather affecting your outdoor plans!</h3>", unsafe_allow_html=True)

    st.markdown("<div style='text-align:center; margin-top:50px;'>", unsafe_allow_html=True)
    if st.button("Would you like to check?", key="splash_button"):
        st.session_state.page = "instructions"
    st.markdown("</div>", unsafe_allow_html=True)

# --------------------------
# Instructions / Description Page
# --------------------------
elif st.session_state.page == "instructions":
    st.title("How to Use 'WeatherWise?'")
    st.markdown("""
Planning an outdoor activity—like a vacation, hike, fishing trip, or parade?  
This app helps you explore the **likelihood of extreme or uncomfortable weather conditions** at a specific location and day based on **historical data**.

### Steps to Use the App:
1. **Select Weather Conditions**: Very hot, very cold, very wet, very windy, or very uncomfortable.
2. **Choose Variables**: Temperature, precipitation, wind speed, etc.
3. **Select Location**: Click on the map for a point, or draw a polygon/rectangle for region analysis.
4. **Choose Season and Date**.
5. **View Results**: Probability metrics, histograms, probability curves, combined curves.
6. **Download Data**: Option to download CSVs with your selected query.
""")
    st.markdown("<div style='text-align:center; margin-top:50px;'>", unsafe_allow_html=True)
    col1, col2 = st.columns(2)
    with col1:
        if st.button("⬅️ Go Back", key="instructions_back"):
            st.session_state.page = "splash"
    with col2:
        if st.button("Go to Dashboard", key="instructions_forward"):
            st.session_state.page = "dashboard"
    st.markdown("</div>", unsafe_allow_html=True)

# --------------------------
# Dashboard Page
# --------------------------
elif st.session_state.page == "dashboard":
    st.title("Personalized Weather Probability Dashboard")

    # --- Sidebar for user input ---
    st.sidebar.title("Customize Your Query")
    weather_condition = st.sidebar.selectbox(
        "Select condition",
        ["Very Hot", "Very Cold", "Very Wet", "Very Windy", "Very Uncomfortable"],
        key="weather_condition"
    )

    # Thresholds in °C for temperature datasets
    condition_thresholds = {
        "Very Hot": 30.0,        # °C
        "Very Cold": 0.0,        # °C
        "Very Wet": 10.0,        # mm/day
        "Very Windy": 15.0,      # m/s
        "Very Uncomfortable": 30.0 # °C
    }

    season = st.sidebar.selectbox("Season Filter", ["All year","Winter","Spring","Summer","Autumn"], key="season_filter")

    # --- Calendar Date Picker ---
    selected_date = st.sidebar.date_input("Select Date", datetime.today(), key="selected_date")
    day_of_year = selected_date.timetuple().tm_yday

    # --- Variables from dataset ---
    available_vars = [col for col in df_all.columns if col not in ["time","date","doy"]]
    selected_vars = st.sidebar.multiselect("Select variables", available_vars, default=available_vars[:2], key="selected_vars")

    # --- Go Back Button ---
    if st.button("Go Back", key="dashboard_back"):
        st.session_state.page = "instructions"

    # --- Map Selection ---
    st.subheader("Select Location / Draw Region")
    m = folium.Map(location=[20,0], zoom_start=2)
    Draw(export=True, filename="region.geojson", draw_options={"polygon":True,"rectangle":True,"circle":False,"polyline":False,"marker":True}).add_to(m)
    st_folium(m, width=700, height=450)

    # --- Main Dashboard Analysis Loop ---
    st.header("Condition Probabilities")
    combined_curves = {}

    for idx, var_key in enumerate(selected_vars):
        st.subheader(var_key)

        # --- Determine threshold ---
        threshold = st.sidebar.number_input(
            f"Threshold for '{weather_condition}' ({var_key})",
            value=float(condition_thresholds.get(weather_condition, 0.0)),
            key=f"{weather_condition}_{var_key}_threshold_{idx}"
        )

        # --- Filter season ---
        df = df_all.copy()
        if season != "All year":
            months = {"Winter":[12,1,2],"Spring":[3,4,5],"Summer":[6,7,8],"Autumn":[9,10,11]}[season]
            df = df[df["time"].dt.month.isin(months)]

        # --- Subset for selected day ---
        subset = df[df["doy"] == day_of_year]
        if not subset.empty and var_key in subset.columns:
            prob = (subset[var_key] > threshold).mean() * 100
            st.metric(f"Probability of {weather_condition}", f"{prob:.1f}%")

            # Histogram
            fig = px.histogram(subset, x=var_key, nbins=30, title=f"Distribution on {selected_date}", labels={var_key: var_key})
            fig.add_vline(x=threshold, line_dash="dash", line_color="red")
            st.plotly_chart(fig, use_container_width=True)

            # Probability curve
            avg_probs = df.groupby("doy").apply(lambda g: (g[var_key] > threshold).mean() * 100)
            combined_curves[var_key] = avg_probs
            fig2 = px.line(avg_probs, title=f"Probability Curve – {var_key}", labels={"doy":"Day of Year","y":"Probability (%)"})
            st.plotly_chart(fig2, use_container_width=True)

            # Download button
            st.download_button(
                f"Download {var_key} data",
                df.to_csv(index=False).encode("utf-8"),
                f"{var_key}_data.csv",
                "text/csv",
                key=f"download_{var_key}_{idx}"
            )

    # Combined Curves Plot
    if combined_curves:
        st.header("Combined Probability Curves")
        fig_comp=go.Figure()
        for label, series in combined_curves.items():
            fig_comp.add_trace(go.Scatter(x=series.index,y=series.values,mode="lines",name=label))
        fig_comp.update_layout(title="Comparison of Probabilities",xaxis_title="Day of Year",yaxis_title="Probability (%)")
        st.plotly_chart(fig_comp,use_container_width=True)

    # --- Footer ---
    st.markdown("<hr><p style='text-align:center; font-size:12px;'>Built by NASA-inspired Event Horizon Engineers</p>", unsafe_allow_html=True)
