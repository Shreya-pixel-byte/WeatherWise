import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import folium
from streamlit_folium import st_folium
from folium.plugins import Draw
from datetime import datetime, timedelta
import requests
from requests.auth import HTTPBasicAuth
import os

# --------------------------
# Page Setup
# --------------------------
st.set_page_config(page_title="☔ WeatherWise", layout="wide")

# --------------------------
# Session State for Navigation
# --------------------------
if "page" not in st.session_state:
    st.session_state.page = "splash"

# --------------------------
# Helper: Get OAuth Token for Meteomatics
# --------------------------
def get_meteomatics_token():
    user = os.getenv("mishra_shreya")
    pwd = os.getenv("Ns4CcuHe1yU1zZbTe5bb")
    if not user or not pwd:
        st.error("Meteomatics credentials not found in environment variables.")
        return None
    resp = requests.post("https://login.meteomatics.com/api/v1/token",
                         auth=HTTPBasicAuth(user, pwd))
    if resp.status_code != 200:
        st.error("Failed to obtain Meteomatics OAuth token.")
        return None
    return resp.json()["access_token"]

# --------------------------
# Fetch Data from Meteomatics
# --------------------------
@st.cache_data
def fetch_meteomatics(var, coords, date):
    token = get_meteomatics_token()
    if token is None:
        return pd.DataFrame()  # empty fallback
    
    lat, lon = coords if coords else (0,0)
    coords_str = f"{lat},{lon}"
    date_str = date.strftime("%Y-%m-%dT00:00:00Z")
    
    url = f"https://api.meteomatics.com/{date_str}/{coords_str}/{var}/json"
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(url, headers=headers)
    
    if resp.status_code != 200:
        st.warning(f"Failed to fetch {var} data from Meteomatics.")
        return pd.DataFrame()
    
    data_json = resp.json()
    # Meteomatics JSON -> DataFrame
    df = pd.DataFrame({
        "time": pd.to_datetime([d["date"] for d in data_json[0]["coordinates"][0]["dates"]]),
        "value": [d["value"] for d in data_json[0]["coordinates"][0]["dates"]]
    })
    df["doy"] = df["time"].dt.dayofyear
    return df

# --------------------------
# Splash Page
# --------------------------
if st.session_state.page == "splash":
    st.markdown("<h1 style='text-align: center; font-size: 60px;'>☔ WeatherWise 🌂💧</h1>", unsafe_allow_html=True)
    st.markdown("<h3 style='text-align: center;'>Check the likelihood of weather affecting your outdoor plans!</h3>", unsafe_allow_html=True)
    if st.button("🌟 Would you like to check? 🌟"):
        st.session_state.page = "instructions"

# --------------------------
# Instructions Page
# --------------------------
elif st.session_state.page == "instructions":
    st.title("📖 How to Use 'WeatherWise?'")
    st.markdown("""
Planning an outdoor activity?  
This app helps you explore the **likelihood of extreme or uncomfortable weather** at a specific location and date.

### Steps:
1. Select weather conditions.
2. Choose variables (temperature, precipitation, wind, etc.).
3. Select location on map.
4. Choose season and date.
5. View probability metrics, histograms, and probability curves.
6. Download CSV data.
""")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("⬅️ Go Back"):
            st.session_state.page = "splash"
    with col2:
        if st.button("🚀 Go to Dashboard 🚀"):
            st.session_state.page = "dashboard"

# --------------------------
# Dashboard Page
# --------------------------
elif st.session_state.page == "dashboard":
    st.title("🌦️ Personalized Weather Probability Dashboard")

    # --- Sidebar Inputs ---
    st.sidebar.title("Customize Your Query")
    weather_condition = st.sidebar.selectbox(
        "Select condition",
        ["Very Hot", "Very Cold", "Very Wet", "Very Windy", "Very Uncomfortable"]
    )
    condition_thresholds = {
        "Very Hot": 303.15,
        "Very Cold": 273.15,
        "Very Wet": 10.0,
        "Very Windy": 15.0,
        "Very Uncomfortable": 30.0
    }
    season = st.sidebar.selectbox("Season Filter", ["All year","Winter","Spring","Summer","Autumn"])
    selected_date = st.sidebar.date_input("Select Date", datetime.today())
    day_of_year = selected_date.timetuple().tm_yday
    selected_vars = st.sidebar.multiselect(
        "Select variables",
        ["temperature_2m:C", "precip_1h:mm", "wind_10m:ms"],
        default=["temperature_2m:C", "precip_1h:mm"]
    )

    if st.button("⬅️ Go Back"):
        st.session_state.page = "instructions"

    # --- Map for Location ---
    st.subheader("📌 Select Location / Draw Region")
    m = folium.Map(location=[20,0], zoom_start=2)
    Draw(export=True, filename="region.geojson", draw_options={"polygon":True,"rectangle":True,"circle":False,"polyline":False,"marker":True}).add_to(m)
    map_data = st_folium(m, width=700, height=450)
    coords = None
    if map_data["last_active_drawing"]:
        shape = map_data["last_active_drawing"]["geometry"]
        if shape["type"] == "Point":
            coords = shape["coordinates"][1], shape["coordinates"][0]

    # --- Main Dashboard ---
    st.header("🌦️ Condition Probabilities")
    combined_curves = {}
    for var in selected_vars:
        st.subheader(var)
        threshold = st.sidebar.number_input(f"Threshold for '{weather_condition}'", value=25.0)
        df = fetch_meteomatics(var, coords, selected_date)
        if df.empty:
            st.warning(f"No data available for {var}.")
            continue
        if season != "All year":
            months={"Winter":[12,1,2],"Spring":[3,4,5],"Summer":[6,7,8],"Autumn":[9,10,11]}[season]
            df = df[df["time"].dt.month.isin(months)]
        subset = df[df["doy"]==day_of_year]
        prob = (subset["value"]>threshold).mean()*100
        st.metric(f"Probability of {weather_condition}", f"{prob:.1f}%")

        # Histogram
        fig = px.histogram(subset, x="value", nbins=30, title=f"Distribution on {selected_date}", labels={"value": var})
        fig.add_vline(x=threshold, line_dash="dash", line_color="red")
        st.plotly_chart(fig,use_container_width=True)

        # Probability curve
        avg_probs = df.groupby("doy").apply(lambda g:(g["value"]>threshold).mean()*100)
        combined_curves[var] = avg_probs
        fig2 = px.line(avg_probs, title=f"Probability Curve – {var}", labels={"doy":"Day of Year","y":"Probability (%)"})
        st.plotly_chart(fig2,use_container_width=True)

        # Download
        st.download_button(f"Download {var} data", df.to_csv(index=False).encode("utf-8"), f"{var}_data.csv","text/csv")

    # Combined Probability Curves
    if combined_curves:
        st.header("📊 Combined Probability Curves")
        fig_comp = go.Figure()
        for label, series in combined_curves.items():
            fig_comp.add_trace(go.Scatter(x=series.index, y=series.values, mode="lines", name=label))
        fig_comp.update_layout(title="Comparison of Probabilities", xaxis_title="Day of Year", yaxis_title="Probability (%)")
        st.plotly_chart(fig_comp, use_container_width=True)

    # Footer
    st.markdown("<hr><p style='text-align:center; font-size:12px;'>Built by NASA-inspired Event Horizon Engineers 🌌</p>", unsafe_allow_html=True)
