import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import folium
from streamlit_folium import st_folium
from folium.plugins import Draw
from datetime import datetime
from math import radians, cos, sin, asin, sqrt

# --------------------------
# CONFIG
# --------------------------
st.set_page_config(page_title="WeatherWise", layout="wide")

# Your dataset raw GitHub URL
DATA_URL = "https://raw.githubusercontent.com/Shreya-pixel-byte/WeatherWise/main/global_weather.xlsx"

# --------------------------
# Haversine distance helper
# --------------------------
def haversine(lon1, lat1, lon2, lat2):
    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat/2)**2 + cos(lat1)*cos(lat2)*sin(dlon/2)**2
    c = 2*asin(sqrt(a))
    r = 6371  # km
    return c * r

# --------------------------
# Load + preprocess data
# --------------------------
@st.cache_data
def load_and_preprocess(url: str):
    df = pd.read_excel(url, sheet_name="weather")  # adjust sheet_name if needed

    # --- Preprocessing ---
    # Ensure time column exists
    if "time" not in df.columns:
        raise ValueError("Expected a 'time' column in dataset")

    df["time"] = pd.to_datetime(df["time"], errors="coerce")
    df = df.dropna(subset=["time"])
    df["date"] = df["time"].dt.date
    df["doy"] = df["time"].dt.dayofyear

    # Melt if wide-format (multiple weather vars as columns)
    id_vars = ["time", "date", "doy"]
    if "lat" in df.columns: id_vars.append("lat")
    if "lon" in df.columns: id_vars.append("lon")

    value_vars = [c for c in df.columns if c not in id_vars]
    df_long = df.melt(id_vars=id_vars, value_vars=value_vars,
                      var_name="variable", value_name="value")
    return df_long

df_all = load_and_preprocess(DATA_URL)

# --------------------------
# Session State
# --------------------------
if "page" not in st.session_state:
    st.session_state.page = "splash"

# --------------------------
# Splash Page
# --------------------------
if st.session_state.page == "splash":
    st.markdown("<h1 style='text-align:center;font-size:60px;'>WeatherWise</h1>", unsafe_allow_html=True)
    st.markdown("<h3 style='text-align:center;'>Check the likelihood of weather affecting your outdoor plans!</h3>", unsafe_allow_html=True)

    st.markdown("<div style='text-align:center;margin-top:50px;'>", unsafe_allow_html=True)
    if st.button("Would you like to check?", key="splash_button"):
        st.session_state.page = "instructions"
    st.markdown("</div>", unsafe_allow_html=True)

# --------------------------
# Instructions Page
# --------------------------
elif st.session_state.page == "instructions":
    st.title("How to Use WeatherWise?")
    st.markdown("""
Plan an outdoor activity—like a vacation, hike, fishing trip, or parade?  
This app helps you explore the **likelihood of extreme or uncomfortable weather conditions** at a specific location and day, based on your uploaded dataset.

### Steps:
1. **Pick a condition** (hot, cold, wet, windy, uncomfortable).  
2. **Select variables** (temperature, precipitation, wind speed, etc.).  
3. **Choose location** (map point or region).  
4. **Pick season and date**.  
5. **See results**: probability metrics, histograms, curves.  
6. **Download data** for offline analysis.  
""")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("⬅️ Go Back"):
            st.session_state.page = "splash"
    with col2:
        if st.button("Go to Dashboard"):
            st.session_state.page = "dashboard"

# --------------------------
# Dashboard Page
# --------------------------
elif st.session_state.page == "dashboard":
    st.title("Personalized Weather Probability Dashboard")

    # --- Sidebar controls ---
    st.sidebar.title("Customize Your Query")
    weather_condition = st.sidebar.selectbox(
        "Select condition",
        ["Very Hot", "Very Cold", "Very Wet", "Very Windy", "Very Uncomfortable"]
    )

    # Default thresholds
    condition_thresholds = {
        "Very Hot": 30.0,
        "Very Cold": 0.0,
        "Very Wet": 10.0,
        "Very Windy": 15.0,
        "Very Uncomfortable": 30.0
    }

    season = st.sidebar.selectbox("Season Filter", ["All year","Winter","Spring","Summer","Autumn"])
    selected_date = st.sidebar.date_input("Select Date", datetime.today().date())
    day_of_year = selected_date.timetuple().tm_yday

    variables_available = sorted(df_all["variable"].unique())
    selected_vars = st.sidebar.multiselect("Select variables", variables_available, default=variables_available)

    if not selected_vars:
        st.warning("Please select at least one variable to analyze.")
        st.stop()

    # Map
    st.subheader("Select Location / Draw Region")
    default_location = [20, 0]
    if "lat" in df_all.columns and "lon" in df_all.columns:
        default_location = [float(df_all["lat"].median()), float(df_all["lon"].median())]

    m = folium.Map(location=default_location, zoom_start=2)
    Draw(export=True, draw_options={"polygon":True,"rectangle":True,"circle":False,"polyline":False,"marker":True}).add_to(m)
    map_data = st_folium(m, width=700, height=450)
    coords, bbox = None, None
    if map_data.get("last_active_drawing"):
        shape = map_data["last_active_drawing"]["geometry"]
        if shape["type"] == "Point":
            coords = (shape["coordinates"][1], shape["coordinates"][0])
        elif shape["type"] in ("Polygon", "Rectangle"):
            lats = [pt[1] for pt in shape["coordinates"][0]]
            lons = [pt[0] for pt in shape["coordinates"][0]]
            bbox = [min(lats), max(lats), min(lons), max(lons)]

    # Thresholds per variable
    thresholds = {}
    for idx, var in enumerate(selected_vars):
        thresholds[var] = st.sidebar.number_input(
            f"Threshold for '{weather_condition}' — {var}",
            value=float(condition_thresholds[weather_condition]),
            key=f"thr_{idx}"
        )

    # --- Filter function ---
    @st.cache_data
    def filter_data(df, vars, coords=None, bbox=None, season="All year"):
        d = df[df["variable"].isin(vars)].copy()
        if bbox is not None and "lat" in d and "lon" in d:
            latmin, latmax, lonmin, lonmax = bbox
            d = d[(d["lat"]>=latmin)&(d["lat"]<=latmax)&(d["lon"]>=lonmin)&(d["lon"]<=lonmax)]
        elif coords is not None and "lat" in d and "lon" in d:
            # nearest location
            unique_pts = d[["lat","lon"]].drop_duplicates()
            unique_pts["dist"] = unique_pts.apply(lambda r: haversine(coords[1], coords[0], r["lon"], r["lat"]), axis=1)
            nearest = unique_pts.loc[unique_pts["dist"].idxmin()]
            d = d[(d["lat"]==nearest["lat"]) & (d["lon"]==nearest["lon"])]
        if season != "All year":
            months = {"Winter":[12,1,2],"Spring":[3,4,5],"Summer":[6,7,8],"Autumn":[9,10,11]}[season]
            d = d[d["time"].dt.month.isin(months)]
        return d

    df_filtered = filter_data(df_all, selected_vars, coords, bbox, season)
    if df_filtered.empty:
        st.warning("No data for chosen filters.")
        st.stop()

    # --- Analysis ---
    st.header("Condition Probabilities")
    combined_curves = {}

    for var in selected_vars:
        st.subheader(var)
        dsub = df_filtered[df_filtered["variable"]==var].copy()
        if dsub.empty:
            st.info("No data for this variable here.")
            continue

        thr = thresholds[var]
        subset = dsub[dsub["doy"]==day_of_year]
        prob = (subset["value"] > thr).mean() * 100 if not subset.empty else 0
        st.metric(f"Probability of {weather_condition}", f"{prob:.1f}%")

        # Histogram
        fig = px.histogram(subset, x="value", nbins=30, title=f"Distribution on {selected_date}")
        fig.add_vline(x=thr, line_dash="dash", line_color="red")
        st.plotly_chart(fig, use_container_width=True)

        # Probability curve
        probs = dsub.groupby("doy").apply(lambda g: (g["value"]>thr).mean()*100)
        combined_curves[var] = probs
        fig2 = px.line(probs, labels={"index":"Day of Year","value":"Probability (%)"}, title=f"Probability Curve — {var}")
        st.plotly_chart(fig2, use_container_width=True)

        # Download
        st.download_button(
            f"Download {var} data",
            dsub.to_csv(index=False).encode("utf-8"),
            f"{var}_filtered.csv",
            "text/csv"
        )

    if combined_curves:
        st.header("Combined Probability Curves")
        figc = go.Figure()
        for label, series in combined_curves.items():
            figc.add_trace(go.Scatter(x=series.index, y=series.values, mode="lines", name=label))
        figc.update_layout(title="Comparison of Probabilities", xaxis_title="Day of Year", yaxis_title="Probability (%)")
        st.plotly_chart(figc, use_container_width=True)

    st.markdown("<hr><p style='text-align:center;font-size:12px;'>Built by Event Horizon Engineers</p>", unsafe_allow_html=True)
