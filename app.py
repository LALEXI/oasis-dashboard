import streamlit as st
import cvxpy as cp
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import requests
import json
from datetime import datetime, timedelta

# ==========================================
# PROJECT O.A.S.I.S. -- Streamlit Web/Mobile App (v2, full feature set)
# ==========================================

st.set_page_config(page_title="Project O.A.S.I.S.", layout="wide")

# ------------------------------------------
# TRANSLATIONS (Feature 4)
# NOTE: English and Filipino strings below were written directly.
# Cebuano/Bisaya strings are machine-assisted and have NOT been verified by
# a native speaker -- flagged clearly in the UI. Please have a native
# speaker review before using this with real farmers.
# ------------------------------------------
TRANSLATIONS = {
    "English": {
        "title": "Project O.A.S.I.S.",
        "subtitle": "Optimized Alternative Saturating Irrigation System -- Davao Region",
        "data_source": "Data Source",
        "weather_data": "Weather data:",
        "mock": "Mock (demo)",
        "real": "Real (NASA POWER)",
        "season_preset": "Season preset:",
        "preset_custom": "Custom date",
        "preset_dry": "Dry Season (Dec-Apr)",
        "preset_wet": "Wet Season (Jun-Oct)",
        "multi_year": "Compare across multiple years",
        "num_years": "Number of years to compare",
        "field_params": "Field & Pump Settings",
        "paddy_area": "Paddy area (m2)",
        "diesel_capacity": "Diesel pump capacity (m3/hr)",
        "diesel_hours": "Diesel pump max hours/day",
        "solar_capacity": "Solar pump capacity (m3/hr)",
        "solar_hours": "Solar pump hours/day",
        "diesel_price": "Diesel price (PHP/L)",
        "view_mode": "View mode",
        "simple_view": "Simple (Farmer View)",
        "detailed_view": "Detailed (Researcher View)",
        "fallback_warning": "Showing MOCK data -- the real NASA POWER fetch failed and this is a fallback, not real weather.",
        "last_updated": "Data last fetched",
        "date_range": "Date range",
        "diesel_cost": "Diesel Cost",
        "savings": "Savings",
        "solar_used": "Solar Used",
        "co2e_avoided": "CO2e Avoided",
        "water_level_chart": "Paddy Water Level vs AWD Safe Zone",
        "energy_mix_chart": "Daily Solar vs Diesel Contribution",
        "lookahead_chart": "MPC 7-Day Look-Ahead Plan",
        "lookahead_caption": "Pick any day to see what the system committed to, and what it tentatively expects for the following week.",
        "select_day": "Select a day",
        "committed_today": "Committed today",
        "download_csv": "Download season data (CSV)",
        "footer": "Diesel CO2 factor: {factor} kg/L (combustion only). Data source: {source}.",
        "simple_today_msg": "Today's Plan (Day {day})",
        "simple_solar_line": "Use SOLAR pump for about {hours:.1f} hours",
        "simple_diesel_line": "Use DIESEL pump for about {hours:.1f} hours",
        "simple_none_line": "No pumping needed today -- rainfall is enough",
        "multi_year_table_title": "Results Across {n} Years",
        "multi_year_avg": "Average across years",
    },
    "Filipino": {
        "title": "Project O.A.S.I.S.",
        "subtitle": "Optimized Alternative Saturating Irrigation System -- Rehiyon ng Davao",
        "data_source": "Pinagmulan ng Datos",
        "weather_data": "Datos ng panahon:",
        "mock": "Mock (demo)",
        "real": "Totoo (NASA POWER)",
        "season_preset": "Preset ng season:",
        "preset_custom": "Custom na petsa",
        "preset_dry": "Tag-init/Tuyo (Dis-Abr)",
        "preset_wet": "Tag-ulan (Hun-Okt)",
        "multi_year": "Ikumpara sa maraming taon",
        "num_years": "Bilang ng taon na ikukumpara",
        "field_params": "Setting ng Bukid at Pump",
        "paddy_area": "Sukat ng palayan (m2)",
        "diesel_capacity": "Kapasidad ng diesel pump (m3/oras)",
        "diesel_hours": "Max oras/araw ng diesel pump",
        "solar_capacity": "Kapasidad ng solar pump (m3/oras)",
        "solar_hours": "Oras/araw ng solar pump",
        "diesel_price": "Presyo ng diesel (PHP/L)",
        "view_mode": "Mode ng view",
        "simple_view": "Simple (Para sa Magsasaka)",
        "detailed_view": "Detalyado (Para sa Mananaliksik)",
        "fallback_warning": "Ipinapakita ang MOCK data -- nabigo ang pagkuha ng totoong datos mula sa NASA POWER.",
        "last_updated": "Huling kinuha ang datos",
        "date_range": "Saklaw ng petsa",
        "diesel_cost": "Gastos sa Diesel",
        "savings": "Naipon/Natipid",
        "solar_used": "Solar na Nagamit",
        "co2e_avoided": "CO2e Naiwasan",
        "water_level_chart": "Lebel ng Tubig sa Palayan vs AWD Safe Zone",
        "energy_mix_chart": "Araw-araw na Solar vs Diesel",
        "lookahead_chart": "MPC 7-Araw na Plano",
        "lookahead_caption": "Pumili ng araw para makita ang plano ngayon at sa susunod na linggo.",
        "select_day": "Pumili ng araw",
        "committed_today": "Nakatakda ngayon",
        "download_csv": "I-download ang datos (CSV)",
        "footer": "Diesel CO2 factor: {factor} kg/L (combustion lang). Pinagmulan ng datos: {source}.",
        "simple_today_msg": "Plano Ngayong Araw (Araw {day})",
        "simple_solar_line": "Gamitin ang SOLAR pump ng humigit-kumulang {hours:.1f} oras",
        "simple_diesel_line": "Gamitin ang DIESEL pump ng humigit-kumulang {hours:.1f} oras",
        "simple_none_line": "Walang kailangan i-pump ngayon -- sapat na ang ulan",
        "multi_year_table_title": "Resulta sa {n} Taon",
        "multi_year_avg": "Average sa lahat ng taon",
    },
}

# ------------------------------------------
# SIDEBAR -- language, view mode, data source, field params (Features 4, 5, 1, 2, 6)
# ------------------------------------------
with st.sidebar:
    language = st.selectbox("Language / Wika / Pinulongan", list(TRANSLATIONS.keys()))
    T = TRANSLATIONS[language]

    st.header(T["data_source"])
    data_source = st.radio(T["weather_data"], [T["mock"], T["real"]])

    end_date_str = None
    multi_year = False
    num_years = 3
    if data_source == T["real"]:
        preset = st.radio(T["season_preset"], [T["preset_custom"], T["preset_dry"], T["preset_wet"]])
        if preset == T["preset_dry"]:
            end_date_str = "2025-04-30"   # 120 days back from here lands in Davao's Dec-Apr dry season
        elif preset == T["preset_wet"]:
            end_date_str = "2025-10-31"   # 120 days back from here lands in Davao's Jun-Oct wet season
        else:
            picked_date = st.date_input("Season end date", value=datetime(2026, 6, 25))
            end_date_str = picked_date.strftime("%Y-%m-%d")

        multi_year = st.checkbox(T["multi_year"])
        if multi_year:
            num_years = st.slider(T["num_years"], min_value=2, max_value=5, value=3)

    st.header(T["view_mode"])
    view_mode = st.radio(T["view_mode"], [T["simple_view"], T["detailed_view"]], label_visibility="collapsed")

    with st.expander(T["field_params"]):
        paddy_area_m2 = st.number_input(T["paddy_area"], value=10000.0, min_value=100.0)
        max_pump_capacity_m3_hr = st.number_input(T["diesel_capacity"], value=90.0, min_value=1.0)
        pump_max_hours_per_day = st.number_input(T["diesel_hours"], value=12.0, min_value=0.5, max_value=24.0)
        max_solar_capacity_m3_hr = st.number_input(T["solar_capacity"], value=30.0, min_value=1.0)
        solar_hours_per_day = st.number_input(T["solar_hours"], value=6.0, min_value=0.5, max_value=24.0)
        diesel_price_php = st.number_input(T["diesel_price"], value=80.0, min_value=1.0)

# ------------------------------------------
# CONFIG BUNDLE -- explicit, not reliant on global-reassignment ordering
# ------------------------------------------
cfg = {
    "paddy_area_m2": paddy_area_m2,
    "max_daily_diesel_volume_m3": max_pump_capacity_m3_hr * pump_max_hours_per_day,
    "max_daily_solar_volume_m3": max_solar_capacity_m3_hr * solar_hours_per_day,
    "pump_coeff_a": 0.05,
    "pump_coeff_b": 2.1,
    "awd_min_cm": -15.0,
    "awd_max_cm": 5.0,
    "water_use_epsilon": 0.01,
    "diesel_price_php": diesel_price_php,
    "diesel_co2_kg_per_liter": 2.68,
}
SEASON_DAYS = 120
MPC_WINDOW_DAYS = 7
DAVAO_LAT = 7.19
DAVAO_LON = 125.45


# ------------------------------------------
# CORE SOLVERS (Phase 2 & 4) -- now take cfg explicitly
# ------------------------------------------
def solve_mpc_window(W_start, rainfall_window, et_window, irradiance_window, cfg):
    N = len(rainfall_window)
    rainfall_arr = np.array(rainfall_window)
    et_arr = np.array(et_window)
    irradiance_arr = np.array(irradiance_window)

    Q_diesel = cp.Variable(N, nonneg=True)
    Q_solar = cp.Variable(N, nonneg=True)
    available_solar = cfg["max_daily_solar_volume_m3"] * irradiance_arr
    depth_added_cm = (Q_diesel + Q_solar) / cfg["paddy_area_m2"] * 100.0
    net_daily_change = depth_added_cm + rainfall_arr - et_arr
    W_levels = W_start + cp.cumsum(net_daily_change)

    fuel_liters = cfg["pump_coeff_a"] * cp.square(Q_diesel) + cfg["pump_coeff_b"] * Q_diesel
    diesel_cost = cp.sum(fuel_liters) * cfg["diesel_price_php"]
    water_tiebreak = cfg["water_use_epsilon"] * cp.sum(Q_diesel + Q_solar)
    objective = cp.Minimize(diesel_cost + water_tiebreak)

    constraints = [
        Q_diesel <= cfg["max_daily_diesel_volume_m3"],
        Q_solar <= available_solar,
        W_levels >= cfg["awd_min_cm"],
        W_levels <= cfg["awd_max_cm"],
    ]
    problem = cp.Problem(objective, constraints)
    problem.solve(solver=cp.CLARABEL)

    return {
        "status": problem.status, "Q_diesel": Q_diesel.value, "Q_solar": Q_solar.value,
        "available_solar": available_solar, "W_levels": W_levels.value,
        "total_diesel_cost_php": diesel_cost.value,
    }


# ------------------------------------------
# WEATHER SOURCES (Phase 3 & 7)
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
def fetch_real_weather_cached(days, lat, lon, end_date_str):
    """Returns (weather_df, used_fallback: bool, fetched_at: str) -- Feature 3 & 8."""
    end_date = datetime.strptime(end_date_str, "%Y-%m-%d") if end_date_str else datetime.utcnow() - timedelta(days=10)
    start_date = end_date - timedelta(days=days - 1)
    url = (
        "https://power.larc.nasa.gov/api/temporal/daily/point"
        f"?parameters=PRECTOTCORR,ALLSKY_SFC_SW_DWN,T2M_MAX,T2M_MIN"
        f"&community=AG&longitude={lon}&latitude={lat}"
        f"&start={start_date.strftime('%Y%m%d')}&end={end_date.strftime('%Y%m%d')}&format=JSON"
    )
    fetched_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        params = response.json()["properties"]["parameter"]
    except (requests.exceptions.RequestException, KeyError, json.JSONDecodeError):
        return generate_mock_weather(days=days), True, fetched_at

    date_keys = sorted(params.get("PRECTOTCORR", {}).keys())
    if not date_keys:
        return generate_mock_weather(days=days), True, fetched_at

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
    return pd.DataFrame(records), False, fetched_at


# ------------------------------------------
# SIMULATION (Phase 5) -- now takes cfg explicitly
# ------------------------------------------
@st.cache_data
def run_mpc_season_simulation(weather_df, cfg, W_start=None, window_days=MPC_WINDOW_DAYS):
    if W_start is None:
        W_start = cfg["awd_max_cm"]
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

        result = solve_mpc_window(W_prev, rainfall_window, et_window, irradiance_window, cfg)
        if result["status"] != "optimal":
            Q_diesel_today, Q_solar_today = 0.0, 0.0
            W_today = min(W_prev + rainfall_window[0] - et_window[0], cfg["awd_max_cm"])
            overflow = True
        else:
            Q_diesel_today = result["Q_diesel"][0]
            Q_solar_today = result["Q_solar"][0]
            W_today = result["W_levels"][0]
            overflow = False

        fuel_liters_today = cfg["pump_coeff_a"] * Q_diesel_today ** 2 + cfg["pump_coeff_b"] * Q_diesel_today
        cost_today = fuel_liters_today * cfg["diesel_price_php"]
        records.append({
            "day": day, "W_start_cm": W_prev, "rainfall_cm": rainfall_window[0],
            "et_cm": et_window[0], "irradiance_index": irradiance_window[0],
            "Q_diesel_m3": Q_diesel_today, "Q_solar_m3": Q_solar_today,
            "W_end_cm": W_today, "fuel_liters": fuel_liters_today, "cost_php": cost_today,
            "overflow_event": overflow,
        })
        W_prev = W_today
    return pd.DataFrame(records)


def get_mpc_lookahead_plan(day_number, weather_df, season_results, cfg, window_days=MPC_WINDOW_DAYS):
    day_idx = day_number - 1
    W_start = season_results.iloc[day_idx]["W_start_cm"]
    window_end = min(day_idx + window_days, len(weather_df))
    window = weather_df.iloc[day_idx:window_end]
    result = solve_mpc_window(W_start, window["rainfall_cm"].tolist(),
                               window["et_cm"].tolist(), window["irradiance_index"].tolist(), cfg)
    plan_days = list(range(day_number, day_number + len(window)))
    return {"plan_days": plan_days, "Q_diesel": result["Q_diesel"], "Q_solar": result["Q_solar"]}


def run_multi_year_analysis(base_end_date_str, num_years, cfg):
    """Feature 2: re-runs the full pipeline across several past years, same month/day."""
    base_date = datetime.strptime(base_end_date_str, "%Y-%m-%d")
    rows = []
    for offset in range(num_years):
        year = base_date.year - offset
        try:
            this_end_date = base_date.replace(year=year)
        except ValueError:
            this_end_date = base_date.replace(year=year, day=28)  # handles Feb 29 edge case
        weather_y, fallback_y, _ = fetch_real_weather_cached(SEASON_DAYS, DAVAO_LAT, DAVAO_LON, this_end_date.strftime("%Y-%m-%d"))
        results_y = run_mpc_season_simulation(weather_y, cfg)
        baseline_y = weather_y.copy()
        baseline_y["irradiance_index"] = 0.0
        baseline_results_y = run_mpc_season_simulation(baseline_y, cfg)
        rows.append({
            "year": year,
            "cost_php": results_y["cost_php"].sum(),
            "baseline_cost_php": baseline_results_y["cost_php"].sum(),
            "diesel_m3": results_y["Q_diesel_m3"].sum(),
            "solar_m3": results_y["Q_solar_m3"].sum(),
            "used_fallback": fallback_y,
        })
    return pd.DataFrame(rows)


# ==========================================
# MAIN UI
# ==========================================
st.title(f"🌾 {T['title']}")
st.caption(T["subtitle"])

if data_source == T["mock"]:
    weather = generate_mock_weather()
    used_fallback, fetched_at = False, None
elif multi_year:
    weather = None  # not used directly in multi-year mode
else:
    weather, used_fallback, fetched_at = fetch_real_weather_cached(SEASON_DAYS, DAVAO_LAT, DAVAO_LON, end_date_str)

# Feature 3: persistent fallback banner
if data_source == T["real"] and not multi_year and used_fallback:
    st.warning(f"⚠️ {T['fallback_warning']}")

if data_source == T["real"] and not multi_year and fetched_at:
    st.caption(f"{T['last_updated']}: {fetched_at} | {T['date_range']}: {end_date_str} (120 days back)")

# --- Multi-year comparison mode (Feature 2) ---
if data_source == T["real"] and multi_year:
    st.subheader(T["multi_year_table_title"].format(n=num_years))
    with st.spinner("Running simulation across multiple years..."):
        multi_df = run_multi_year_analysis(end_date_str, num_years, cfg)
    multi_df["savings_php"] = multi_df["baseline_cost_php"] - multi_df["cost_php"]
    st.dataframe(multi_df.style.format({
        "cost_php": "PHP {:,.2f}", "baseline_cost_php": "PHP {:,.2f}", "savings_php": "PHP {:,.2f}",
        "diesel_m3": "{:,.1f}", "solar_m3": "{:,.1f}",
    }), use_container_width=True)
    st.metric(T["multi_year_avg"] + " -- " + T["savings"], f"PHP {multi_df['savings_php'].mean():,.2f}")
    if multi_df["used_fallback"].any():
        st.warning(f"⚠️ {T['fallback_warning']} (one or more years used fallback mock data)")
    st.stop()  # multi-year mode replaces the rest of the single-season UI

season_results = run_mpc_season_simulation(weather, cfg)
baseline_weather = weather.copy()
baseline_weather["irradiance_index"] = 0.0
baseline_results = run_mpc_season_simulation(baseline_weather, cfg)

total_hybrid_cost = season_results["cost_php"].sum()
total_baseline_cost = baseline_results["cost_php"].sum()
savings_php = total_baseline_cost - total_hybrid_cost
savings_pct = (savings_php / total_baseline_cost * 100) if total_baseline_cost > 0 else 0
total_solar_m3 = season_results["Q_solar_m3"].sum()
total_diesel_m3 = season_results["Q_diesel_m3"].sum()
fuel_liters_avoided = baseline_results["fuel_liters"].sum() - season_results["fuel_liters"].sum()
co2e_avoided_kg = fuel_liters_avoided * cfg["diesel_co2_kg_per_liter"]

max_day = int(season_results["day"].max()) - MPC_WINDOW_DAYS + 1
if season_results["Q_diesel_m3"].max() > 1e-6:
    default_day = int(season_results.loc[season_results["Q_diesel_m3"].idxmax(), "day"])
elif season_results["Q_solar_m3"].max() > 1e-6:
    default_day = int(season_results.loc[season_results["Q_solar_m3"].idxmax(), "day"])
else:
    default_day = max_day // 2
default_day = min(default_day, max_day)

# --- Feature 5: Simple Farmer View vs Detailed Researcher View ---
if view_mode == T["simple_view"]:
    selected_day = st.slider(T["select_day"], min_value=1, max_value=max_day, value=default_day)
    row = season_results.loc[season_results["day"] == selected_day].iloc[0]

    st.subheader(T["simple_today_msg"].format(day=selected_day))
    if row["Q_solar_m3"] > 1e-6:
        hours = row["Q_solar_m3"] / max_solar_capacity_m3_hr
        st.success(T["simple_solar_line"].format(hours=hours))
    if row["Q_diesel_m3"] > 1e-6:
        hours = row["Q_diesel_m3"] / max_pump_capacity_m3_hr
        st.error(T["simple_diesel_line"].format(hours=hours))
    if row["Q_solar_m3"] <= 1e-6 and row["Q_diesel_m3"] <= 1e-6:
        st.info(T["simple_none_line"])

    with st.expander(T["detailed_view"]):
        col1, col2, col3, col4 = st.columns(4)
        col1.metric(T["diesel_cost"], f"PHP {total_hybrid_cost:,.2f}", f"-{savings_pct:.1f}%")
        col2.metric(T["savings"], f"PHP {savings_php:,.2f}")
        col3.metric(T["solar_used"], f"{total_solar_m3:,.2f} m3")
        col4.metric(T["co2e_avoided"], f"{co2e_avoided_kg:,.2f} kg")

else:
    col1, col2, col3, col4 = st.columns(4)
    col1.metric(T["diesel_cost"], f"PHP {total_hybrid_cost:,.2f}", f"-{savings_pct:.1f}% vs diesel-only")
    col2.metric(T["savings"], f"PHP {savings_php:,.2f}")
    col3.metric(T["solar_used"], f"{total_solar_m3:,.2f} m3")
    col4.metric(T["co2e_avoided"], f"{co2e_avoided_kg:,.2f} kg")

    st.subheader(T["water_level_chart"])
    fig_water = go.Figure()
    fig_water.add_trace(go.Scatter(x=season_results["day"], y=[cfg["awd_max_cm"]] * len(season_results),
                                    line=dict(width=0), showlegend=False, hoverinfo="skip"))
    fig_water.add_trace(go.Scatter(x=season_results["day"], y=[cfg["awd_min_cm"]] * len(season_results),
                                    fill="tonexty", fillcolor="rgba(70,130,220,0.15)", line=dict(width=0),
                                    name="AWD safe zone", hoverinfo="skip"))
    fig_water.add_trace(go.Scatter(x=season_results["day"], y=season_results["W_end_cm"],
                                    mode="lines", name="Water level", line=dict(color="royalblue", width=2)))
    fig_water.update_layout(xaxis_title="Day of season", yaxis_title="Water level (cm)", height=400)
    st.plotly_chart(fig_water, use_container_width=True)

    st.subheader(T["energy_mix_chart"])
    fig_energy = go.Figure()
    fig_energy.add_trace(go.Bar(x=season_results["day"], y=season_results["Q_solar_m3"], name="Solar (m3)", marker_color="gold"))
    fig_energy.add_trace(go.Bar(x=season_results["day"], y=season_results["Q_diesel_m3"], name="Diesel (m3)", marker_color="dimgray"))
    fig_energy.update_layout(barmode="stack", xaxis_title="Day of season", yaxis_title="Water pumped (m3)", height=400)
    st.plotly_chart(fig_energy, use_container_width=True)

    st.subheader(T["lookahead_chart"])
    st.caption(T["lookahead_caption"])
    selected_day = st.slider(T["select_day"], min_value=1, max_value=max_day, value=default_day)
    plan = get_mpc_lookahead_plan(selected_day, weather, season_results, cfg)

    fig_plan = go.Figure()
    fig_plan.add_trace(go.Bar(x=plan["plan_days"], y=plan["Q_solar"], name="Planned Solar", marker_color="gold"))
    fig_plan.add_trace(go.Bar(x=plan["plan_days"], y=plan["Q_diesel"], name="Planned Diesel", marker_color="dimgray"))
    fig_plan.add_annotation(x=plan["plan_days"][0], y=max(max(plan["Q_solar"]), max(plan["Q_diesel"]), 1) * 1.15,
                             text=T["committed_today"], showarrow=True, arrowhead=2)
    fig_plan.update_layout(barmode="stack", xaxis_title="Day of season (forecast)", yaxis_title="Water pumped (m3)", height=400)
    st.plotly_chart(fig_plan, use_container_width=True)

# --- Feature 7: CSV download (available in both view modes) ---
csv_data = season_results.to_csv(index=False).encode("utf-8")
st.download_button(T["download_csv"], data=csv_data, file_name="oasis_season_results.csv", mime="text/csv")

st.caption(T["footer"].format(factor=cfg["diesel_co2_kg_per_liter"], source=data_source))
