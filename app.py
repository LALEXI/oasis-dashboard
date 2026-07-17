import streamlit as st
import cvxpy as cp
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import requests
import json
from datetime import datetime, timedelta

# ==========================================
# PROJECT O.A.S.I.S. -- Streamlit Web/Mobile App
# Deploy via Streamlit Community Cloud for a public URL.
# Run locally with: streamlit run app.py
# ==========================================

st.set_page_config(page_title="Project O.A.S.I.S.", layout="wide")

# ------------------------------------------
# CONSTANTS (Phase 1)
# ------------------------------------------
SEASON_DAYS = 120
MPC_WINDOW_DAYS = 7
AWD_MIN_CM = -15.0
AWD_MAX_CM = 5.0
PADDY_AREA_M2 = 10000.0
DIESEL_PRICE_PHP = 80.0
MAX_PUMP_CAPACITY_M3_HR = 90.0
PUMP_MAX_HOURS_PER_DAY = 12.0
MAX_DAILY_DIESEL_VOLUME_M3 = MAX_PUMP_CAPACITY_M3_HR * PUMP_MAX_HOURS_PER_DAY
PUMP_COEFF_A = 0.05
PUMP_COEFF_B = 2.1
MAX_SOLAR_CAPACITY_M3_HR = 30.0
SOLAR_HOURS_PER_DAY = 6.0
MAX_DAILY_SOLAR_VOLUME_M3 = MAX_SOLAR_CAPACITY_M3_HR * SOLAR_HOURS_PER_DAY
WATER_USE_EPSILON = 0.01
DIESEL_CO2_KG_PER_LITER = 2.68
DAVAO_LAT = 7.19
DAVAO_LON = 125.45


# ------------------------------------------
# CORE SOLVERS (Phase 2 & 4)
# ------------------------------------------
def solve_mpc_window(W_start, rainfall_window, et_window, irradiance_window, diesel_price=DIESEL_PRICE_PHP):
    N = len(rainfall_window)
    rainfall_arr = np.array(rainfall_window)
    et_arr = np.array(et_window)
    irradiance_arr = np.array(irradiance_window)

    Q_diesel = cp.Variable(N, nonneg=True)
    Q_solar = cp.Variable(N, nonneg=True)
    available_solar = MAX_DAILY_SOLAR_VOLUME_M3 * irradiance_arr
    depth_added_cm = (Q_diesel + Q_solar) / PADDY_AREA_M2 * 100.0
    net_daily_change = depth_added_cm + rainfall_arr - et_arr
    W_levels = W_start + cp.cumsum(net_daily_change)

    fuel_liters = PUMP_COEFF_A * cp.square(Q_diesel) + PUMP_COEFF_B * Q_diesel
    diesel_cost = cp.sum(fuel_liters) * diesel_price
    water_tiebreak = WATER_USE_EPSILON * cp.sum(Q_diesel + Q_solar)
    objective = cp.Minimize(diesel_cost + water_tiebreak)

    constraints = [
        Q_diesel <= MAX_DAILY_DIESEL_VOLUME_M3,
        Q_solar <= available_solar,
        W_levels >= AWD_MIN_CM,
        W_levels <= AWD_MAX_CM,
    ]
    problem = cp.Problem(objective, constraints)
    problem.solve(solver=cp.CLARABEL)

    return {
        "status": problem.status, "Q_diesel": Q_diesel.value, "Q_solar": Q_solar.value,
        "available_solar": available_solar, "W_levels": W_levels.value,
        "total_diesel_cost_php": diesel_cost.value,
    }


# ------------------------------------------
# WEATHER SOURCES (Phase 3 & 7) -- cached so re-running the app doesn't
# re-fetch/re-generate every time a widget is touched
# ------------------------------------------
@st.cache_data
def generate_mock_weather(days=SEASON_DAYS, seed=42, dry_spell_start=50, dry_spell_length=20,
                           cloudy_dry_spell_start=90, cloudy_dry_spell_length=15):
    rng = np.random.default_rng(seed)
    rain_occurs = rng.random(days) < 0.55
    rain_amount_cm = rng.gamma(shape=1.5, scale=0.8, size=days)
    rainfall_cm = np.where(rain_occurs, rain_amount_cm, 0.0)
    et_cm = rng.normal(loc=0.6, scale=0.1, size=days)
    et_cm = np.clip(et_cm, 0.3, 1.0)
    irradiance_noise = rng.normal(loc=0.0, scale=0.05, size=days)
    irradiance_index = 0.85 - (rainfall_cm * 0.15) + irradiance_noise
    irradiance_index = np.clip(irradiance_index, 0.0, 1.0)

    dry_start_idx = dry_spell_start - 1
    dry_end_idx = dry_start_idx + dry_spell_length
    rainfall_cm[dry_start_idx:dry_end_idx] = 0.0
    dry_et = rng.normal(loc=0.8, scale=0.05, size=dry_spell_length)
    et_cm[dry_start_idx:dry_end_idx] = np.clip(dry_et, 0.6, 1.0)
    dry_irradiance = rng.normal(loc=0.95, scale=0.03, size=dry_spell_length)
    irradiance_index[dry_start_idx:dry_end_idx] = np.clip(dry_irradiance, 0.8, 1.0)

    cloudy_start_idx = cloudy_dry_spell_start - 1
    cloudy_end_idx = cloudy_start_idx + cloudy_dry_spell_length
    rainfall_cm[cloudy_start_idx:cloudy_end_idx] = 0.0
    cloudy_et = rng.normal(loc=0.6, scale=0.05, size=cloudy_dry_spell_length)
    et_cm[cloudy_start_idx:cloudy_end_idx] = np.clip(cloudy_et, 0.5, 0.7)
    cloudy_irradiance = rng.normal(loc=0.04, scale=0.02, size=cloudy_dry_spell_length)
    irradiance_index[cloudy_start_idx:cloudy_end_idx] = np.clip(cloudy_irradiance, 0.0, 0.08)

    return pd.DataFrame({
        "day": np.arange(1, days + 1), "rainfall_cm": np.round(rainfall_cm, 3),
        "et_cm": np.round(et_cm, 3), "irradiance_index": np.round(irradiance_index, 3),
    })


def extraterrestrial_radiation_mj(lat_deg, day_of_year):
    lat_rad = np.radians(lat_deg)
    dr = 1 + 0.033 * np.cos(2 * np.pi * day_of_year / 365)
    delta = 0.409 * np.sin(2 * np.pi * day_of_year / 365 - 1.39)
    ws = np.arccos(max(min(-np.tan(lat_rad) * np.tan(delta), 1.0), -1.0))
    return (24 * 60 / np.pi) * 0.0820 * dr * (
        ws * np.sin(lat_rad) * np.sin(delta) + np.cos(lat_rad) * np.cos(delta) * np.sin(ws)
    )


def clear_sky_radiation_mj(lat_deg, day_of_year, elevation_m=20):
    Ra = extraterrestrial_radiation_mj(lat_deg, day_of_year)
    return (0.75 + 2e-5 * elevation_m) * Ra


def hargreaves_et0_mm(tmax, tmin, lat_deg, day_of_year):
    tmean = (tmax + tmin) / 2.0
    Ra = extraterrestrial_radiation_mj(lat_deg, day_of_year)
    et0 = 0.0023 * (tmean + 17.8) * np.sqrt(max(tmax - tmin, 0)) * 0.408 * Ra
    return max(et0, 0.0)


@st.cache_data
def fetch_real_weather(days=SEASON_DAYS, lat=DAVAO_LAT, lon=DAVAO_LON, end_date_str=None):
    """end_date_str: 'YYYY-MM-DD' or None (defaults to 10 days before today)."""
    if end_date_str:
        end_date = datetime.strptime(end_date_str, "%Y-%m-%d")
    else:
        end_date = datetime.utcnow() - timedelta(days=10)
    start_date = end_date - timedelta(days=days - 1)
    url = (
        "https://power.larc.nasa.gov/api/temporal/daily/point"
        f"?parameters=PRECTOTCORR,ALLSKY_SFC_SW_DWN,T2M_MAX,T2M_MIN"
        f"&community=AG&longitude={lon}&latitude={lat}"
        f"&start={start_date.strftime('%Y%m%d')}&end={end_date.strftime('%Y%m%d')}&format=JSON"
    )
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        params = response.json()["properties"]["parameter"]
    except (requests.exceptions.RequestException, KeyError, json.JSONDecodeError) as e:
        st.warning(f"NASA POWER API request failed ({e}). Using mock weather instead.")
        return generate_mock_weather(days=days)

    date_keys = sorted(params.get("PRECTOTCORR", {}).keys())
    if not date_keys:
        st.warning("NASA POWER returned no data for this range. Using mock weather instead.")
        return generate_mock_weather(days=days)

    records = []
    for i, date_key in enumerate(date_keys, start=1):
        precip_mm = params["PRECTOTCORR"].get(date_key, -999)
        solar_mj = params["ALLSKY_SFC_SW_DWN"].get(date_key, -999)
        tmax = params["T2M_MAX"].get(date_key, -999)
        tmin = params["T2M_MIN"].get(date_key, -999)
        if min(precip_mm, solar_mj, tmax, tmin) <= -998:
            precip_mm, solar_mj, tmax, tmin = 0.0, 14.0, 32.0, 24.0

        day_of_year = datetime.strptime(date_key, "%Y%m%d").timetuple().tm_yday
        clear_sky_mj = clear_sky_radiation_mj(lat, day_of_year)
        irradiance_index = float(np.clip(solar_mj / clear_sky_mj, 0.0, 1.0))
        et_cm = hargreaves_et0_mm(tmax, tmin, lat, day_of_year) / 10.0

        records.append({
            "day": i, "rainfall_cm": round(precip_mm / 10.0, 3),
            "et_cm": round(et_cm, 3), "irradiance_index": round(irradiance_index, 3),
        })
    return pd.DataFrame(records)


# ------------------------------------------
# SIMULATION (Phase 5) -- cached, keyed on the weather data itself
# ------------------------------------------
@st.cache_data
def run_mpc_season_simulation(weather_df, W_start=AWD_MAX_CM, diesel_price=DIESEL_PRICE_PHP, window_days=MPC_WINDOW_DAYS):
    records = []
    W_prev = W_start
    n_days = len(weather_df)
    for day_idx in range(n_days):
        day = int(weather_df.iloc[day_idx]["day"])
        window_end = min(day_idx + window_days, n_days)
        window = weather_df.iloc[day_idx:window_end]
        rainfall_window = window["rainfall_cm"].tolist()
        et_window = window["et_cm"].tolist()
        irradiance_window = window["irradiance_index"].tolist()

        result = solve_mpc_window(W_prev, rainfall_window, et_window, irradiance_window, diesel_price)
        if result["status"] != "optimal":
            Q_diesel_today, Q_solar_today = 0.0, 0.0
            W_today = min(W_prev + rainfall_window[0] - et_window[0], AWD_MAX_CM)
            overflow = True
        else:
            Q_diesel_today = result["Q_diesel"][0]
            Q_solar_today = result["Q_solar"][0]
            W_today = result["W_levels"][0]
            overflow = False

        fuel_liters_today = PUMP_COEFF_A * Q_diesel_today ** 2 + PUMP_COEFF_B * Q_diesel_today
        cost_today = fuel_liters_today * diesel_price
        records.append({
            "day": day, "W_start_cm": W_prev, "rainfall_cm": rainfall_window[0],
            "et_cm": et_window[0], "irradiance_index": irradiance_window[0],
            "Q_diesel_m3": Q_diesel_today, "Q_solar_m3": Q_solar_today,
            "W_end_cm": W_today, "fuel_liters": fuel_liters_today, "cost_php": cost_today,
            "overflow_event": overflow,
        })
        W_prev = W_today
    return pd.DataFrame(records)


def get_mpc_lookahead_plan(day_number, weather_df, season_results, window_days=MPC_WINDOW_DAYS):
    day_idx = day_number - 1
    W_start = season_results.iloc[day_idx]["W_start_cm"]
    window_end = min(day_idx + window_days, len(weather_df))
    window = weather_df.iloc[day_idx:window_end]
    result = solve_mpc_window(W_start, window["rainfall_cm"].tolist(),
                               window["et_cm"].tolist(), window["irradiance_index"].tolist())
    plan_days = list(range(day_number, day_number + len(window)))
    return {"plan_days": plan_days, "Q_diesel": result["Q_diesel"], "Q_solar": result["Q_solar"]}


# ==========================================
# STREAMLIT UI
# ==========================================
st.title("🌾 Project O.A.S.I.S.")
st.caption("Optimized Alternative Saturating Irrigation System -- Davao Region")

with st.sidebar:
    st.header("Data Source")
    data_source = st.radio("Weather data:", ["Mock (demo)", "Real (NASA POWER)"])
    if data_source == "Real (NASA POWER)":
        use_fixed_date = st.checkbox("Use a fixed end date (reproducible)", value=False)
        end_date_str = None
        if use_fixed_date:
            picked_date = st.date_input("Season end date", value=datetime(2026, 6, 25))
            end_date_str = picked_date.strftime("%Y-%m-%d")

if data_source == "Mock (demo)":
    weather = generate_mock_weather()
else:
    weather = fetch_real_weather(end_date_str=end_date_str)

season_results = run_mpc_season_simulation(weather)
weather_diesel_only = weather.copy()
weather_diesel_only["irradiance_index"] = 0.0
baseline_results = run_mpc_season_simulation(weather_diesel_only)

# --- KPIs ---
total_hybrid_cost = season_results["cost_php"].sum()
total_baseline_cost = baseline_results["cost_php"].sum()
savings_php = total_baseline_cost - total_hybrid_cost
savings_pct = (savings_php / total_baseline_cost * 100) if total_baseline_cost > 0 else 0
total_solar_m3 = season_results["Q_solar_m3"].sum()
total_diesel_m3 = season_results["Q_diesel_m3"].sum()
fuel_liters_avoided = baseline_results["fuel_liters"].sum() - season_results["fuel_liters"].sum()
co2e_avoided_kg = fuel_liters_avoided * DIESEL_CO2_KG_PER_LITER

col1, col2, col3, col4 = st.columns(4)
col1.metric("Diesel Cost", f"PHP {total_hybrid_cost:,.0f}", f"-{savings_pct:.1f}% vs diesel-only")
col2.metric("Savings", f"PHP {savings_php:,.0f}")
col3.metric("Solar Used", f"{total_solar_m3:,.0f} m3")
col4.metric("CO2e Avoided", f"{co2e_avoided_kg:,.0f} kg")

# --- Water level chart ---
st.subheader("Paddy Water Level vs AWD Safe Zone")
fig_water = go.Figure()
fig_water.add_trace(go.Scatter(x=season_results["day"], y=[AWD_MAX_CM] * len(season_results),
                                line=dict(width=0), showlegend=False, hoverinfo="skip"))
fig_water.add_trace(go.Scatter(x=season_results["day"], y=[AWD_MIN_CM] * len(season_results),
                                fill="tonexty", fillcolor="rgba(70,130,220,0.15)", line=dict(width=0),
                                name="AWD safe zone", hoverinfo="skip"))
fig_water.add_trace(go.Scatter(x=season_results["day"], y=season_results["W_end_cm"],
                                mode="lines", name="Water level", line=dict(color="royalblue", width=2)))
fig_water.update_layout(xaxis_title="Day of season", yaxis_title="Water level (cm)", height=400)
st.plotly_chart(fig_water, use_container_width=True)

# --- Energy mix chart ---
st.subheader("Daily Solar vs Diesel Contribution")
fig_energy = go.Figure()
fig_energy.add_trace(go.Bar(x=season_results["day"], y=season_results["Q_solar_m3"], name="Solar (m3)", marker_color="gold"))
fig_energy.add_trace(go.Bar(x=season_results["day"], y=season_results["Q_diesel_m3"], name="Diesel (m3)", marker_color="dimgray"))
fig_energy.update_layout(barmode="stack", xaxis_title="Day of season", yaxis_title="Water pumped (m3)", height=400)
st.plotly_chart(fig_energy, use_container_width=True)

# --- MPC look-ahead: interactive day selector ---
st.subheader("MPC 7-Day Look-Ahead Plan")
st.caption("Pick any day to see what the system committed to, and what it tentatively expects for the following week.")
selected_day = st.slider("Select a day", min_value=1, max_value=int(season_results["day"].max()) - MPC_WINDOW_DAYS + 1,
                          value=min(60, int(season_results["day"].max())))
plan = get_mpc_lookahead_plan(selected_day, weather, season_results)

fig_plan = go.Figure()
fig_plan.add_trace(go.Bar(x=plan["plan_days"], y=plan["Q_solar"], name="Planned Solar", marker_color="gold"))
fig_plan.add_trace(go.Bar(x=plan["plan_days"], y=plan["Q_diesel"], name="Planned Diesel", marker_color="dimgray"))
fig_plan.add_annotation(x=plan["plan_days"][0], y=max(max(plan["Q_solar"]), max(plan["Q_diesel"]), 1) * 1.15,
                         text="Committed today", showarrow=True, arrowhead=2)
fig_plan.update_layout(barmode="stack", xaxis_title="Day of season (forecast)", yaxis_title="Water pumped (m3)", height=400)
st.plotly_chart(fig_plan, use_container_width=True)

st.caption(f"Diesel CO2 factor: {DIESEL_CO2_KG_PER_LITER} kg/L (combustion only). Data source: {data_source}.")
