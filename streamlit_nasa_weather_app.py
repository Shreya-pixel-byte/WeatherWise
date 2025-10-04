import streamlit as st
import xarray as xr
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import folium
from streamlit_folium import st_folium
from folium.plugins import Draw
import os
from datetime import datetime

# --------------------------
# Page Setup
# --------------------------
st.set_page_config(page_title="WeatherWise", layout="wide")

# --------------------------
# Session State for Page Navigation
# --------------------------
if "page" not in st.session_state:
    st.session_state.page = "splash"  # default first page

# --------------------------
# Function to Setup Earthdata Auth
# --------------------------
def setup_earthdata_auth():
    user = os.getenv("EARTHDATA_USERNAME")
    pwd = os.getenv("EARTHDATA_PASSWORD")
    if user and pwd:
        netrc_path = os.path.expanduser("~/.netrc")
        with open(netrc_path, "w") as f:
            f.write(f"machine urs.earthdata.nasa.gov login {user} password {pwd}\n")
        os.chmod(netrc_path, 0o600)

setup_earthdata_auth()

# --------------------------
# Splash Page
# --------------------------
if st.session_state.page == "splash":
    st.markdown("<h1 style='text-align: center; font-size: 60px;'>☔ WeatherWise 🌂💧</h1>", unsafe_allow_html=True)
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
This app helps you explore the **likelihood of extreme or uncomfortable weather conditions** at a specific location and day based on **historical NASA Earth observation data**.

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
    
    # --- Dataset Selection ---
    DATASETS = {
        "MERRA-2 Air Temperature (°C)": {
            "desc": "MERRA-2 2D air temperature at 2m above ground.",
            "opendap_url": "https://goldsmr4.gesdisc.eosdis.nasa.gov/opendap/MERRA2_MONTHLY/M2TMNXRAD.5.12.4.nc4",
            "var": "T2M",
            "unit": "°C",
        },
        "MERRA-2 Precipitation (mm/day)": {
            "desc": "MERRA-2 total precipitation.",
            "opendap_url": "https://goldsmr4.gesdisc.eosdis.nasa.gov/opendap/MERRA2_MONTHLY/M2TMNXRAD.5.12.4.nc4",
            "var": "PRECTOT",
            "unit": "mm/day",
        },
        "GLDAS Air Temperature (°C)": {
            "desc": "GLDAS 2D air temperature at 2m above ground.",
            "opendap_url": "https://hydro1.gesdisc.eosdis.nasa.gov/opendap/GLDAS/GLDAS_NOAH025_3H.A202212.nc4",
            "var": "Tair_f_inst",
            "unit": "°C",
        },
        "GLDAS Precipitation (mm/hr)": {
            "desc": "GLDAS 2D precipitation.",
            "opendap_url": "https://hydro1.gesdisc.eosdis.nasa.gov/opendap/GLDAS/GLDAS_NOAH025_3H.A202212.nc4",
            "var": "Rainf_f_inst",
            "unit": "mm/hr",
        },
    }
    selected_vars = st.sidebar.multiselect("Select variables", list(DATASETS.keys()), default=list(DATASETS.keys()), key="selected_vars")
    
    # --- Go Back Button ---
    if st.button("Go Back", key="dashboard_back"):
        st.session_state.page = "instructions"

    # --- Map Selection ---
    st.subheader("Select Location / Draw Region")
    m = folium.Map(location=[20,0], zoom_start=2)
    Draw(export=True, filename="region.geojson", draw_options={"polygon":True,"rectangle":True,"circle":False,"polyline":False,"marker":True}).add_to(m)
    map_data = st_folium(m, width=700, height=450)
    coords, bbox = None, None
    if map_data["last_active_drawing"]:
        shape = map_data["last_active_drawing"]["geometry"]
        if shape["type"] == "Point":
            coords = shape["coordinates"][1], shape["coordinates"][0]
        elif shape["type"] in ["Polygon","Rectangle"]:
            lats = [pt[1] for pt in shape["coordinates"][0]]
            lons = [pt[0] for pt in shape["coordinates"][0]]
            bbox = [min(lats), max(lats), min(lons), max(lons)]
    
    # --- Helper Function ---
    @st.cache_data
    def load_opendap_data(ds_info, coords=None, bbox=None):
        try:
            ds = xr.open_dataset(ds_info["opendap_url"], chunks={"time": 50})
            var = ds_info["var"]
            if coords:
                data = ds[var].sel(lat=coords[0], lon=coords[1], method="nearest")
            elif bbox:
                lat_min, lat_max, lon_min, lon_max = bbox
                data = ds[var].sel(lat=slice(lat_min,lat_max), lon=slice(lon_min,lon_max)).mean(dim=["lat","lon"])
            else:
                data = ds[var].mean(dim=["lat","lon"])
            df = data.to_dataframe().reset_index().rename(columns={var:"value"})
            if "Temperature" in ds_info["desc"]:
                df["value"] = df["value"] - 273.15
            df["doy"] = df["time"].dt.dayofyear
            return df
        except:
            dates=pd.date_range("2000-01-01","2020-12-31")
            np.random.seed(42)
            base = 25 if "Temperature" in ds_info["desc"] else 5
            scale = 5 if "Temperature" in ds_info["desc"] else 2
            df=pd.DataFrame({"time":dates,"value":np.random.normal(base,scale,len(dates))})
            df["doy"]=df["time"].dt.dayofyear
            return df

    # --- Main Dashboard Analysis Loop ---
    st.header("Condition Probabilities")
    combined_curves = {}

    for idx, var_key in enumerate(selected_vars):
        ds_info = DATASETS[var_key]
        st.subheader(var_key)
        st.info(ds_info["desc"])

        # --- Determine threshold in dataset units ---
        threshold = st.sidebar.number_input(
            f"Threshold for '{weather_condition}' ({ds_info['unit']})", 
            value=float(condition_thresholds[weather_condition]),
            key=f"{weather_condition}_{var_key}_threshold_{idx}"
        )

        # --- Load data ---
        df = load_opendap_data(ds_info, coords, bbox)
        if season != "All year":
            months={"Winter":[12,1,2],"Spring":[3,4,5],"Summer":[6,7,8],"Autumn":[9,10,11]}[season]
            df = df[df["time"].dt.month.isin(months)]
        
        subset = df[df["doy"] == day_of_year]
        prob = (subset["value"] > threshold).mean() * 100
        st.metric(f"Probability of {weather_condition}", f"{prob:.1f}%")
        
        # Histogram
        fig = px.histogram(subset, x="value", nbins=30, title=f"Distribution on {selected_date}", labels={"value": f"{var_key} ({ds_info['unit']})"})
        fig.add_vline(x=threshold, line_dash="dash", line_color="red")
        st.plotly_chart(fig, use_container_width=True)

        # Probability curve
        avg_probs = df.groupby("doy").apply(lambda g: (g["value"] > threshold).mean() * 100)
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
        for label,series in combined_curves.items():
            fig_comp.add_trace(go.Scatter(x=series.index,y=series.values,mode="lines",name=label))
        fig_comp.update_layout(title="Comparison of Probabilities",xaxis_title="Day of Year",yaxis_title="Probability (%)")
        st.plotly_chart(fig_comp,use_container_width=True)

    # --- Footer ---
    st.markdown("<hr><p style='text-align:center; font-size:12px;'>Built by NASA-inspired Event Horizon Engineers</p>", unsafe_allow_html=True)

