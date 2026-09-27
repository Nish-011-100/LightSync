"""Rebuild clean LightSync datasets without modifying the raw inputs.

Run: python -m src.prepare_data
All filesystem paths are relative to this project, not a developer's machine.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
from astral import Observer
from astral.sun import elevation, sun

ROOT = Path(__file__).resolve().parents[1]
TABLES: dict[str, pd.DataFrame] = {}
MEANINGS: dict[str, str] = {}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snake_column(label: str) -> str:
    text = label.strip().lower()
    replacements = {"w/m^2": "w_m2", "mm/h": "mm_h", "m/s": "m_s",
                    "mm hg": "mmhg", "°c": "c", "%": "pct", "&": "and"}
    for old, new in replacements.items():
        text = text.replace(old, new)
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


def export_table(name: str, frame: pd.DataFrame, root: Path) -> None:
    TABLES[name] = frame
    frame.to_csv(root / "data/processed" / f"{name}.csv", index=False,
                 encoding="utf-8", float_format="%.10g")
    frame.to_parquet(root / "data/processed" / f"{name}.parquet", index=False)


def check(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def prepare_solar(root: Path, cfg: dict, observer: Observer) -> dict:
    raw_path = root / "data/raw/solar_station_original.csv"
    raw = pd.read_csv(raw_path, skiprows=5, encoding="cp1252", na_values=["--"],
                      low_memory=False)
    mapping = {col: snake_column(col) for col in raw.columns}
    check(len(set(mapping.values())) == len(mapping), "Normalized weather names collide.")
    weather = raw.rename(columns=mapping).copy()
    weather.insert(0, "source_row_number", np.arange(7, 7 + len(raw)))
    weather = weather.rename(columns={"date_and_time": "timestamp_source_text",
                                     "solar_rad_w_m2": "solar_radiation_w_m2"})
    timestamps = pd.to_datetime(weather["timestamp_source_text"],
                               format="%m/%d/%y %I:%M %p", errors="raise")
    weather.insert(0, "timestamp_local", timestamps.dt.tz_localize(cfg["timezone"]))
    check(not weather["timestamp_local"].duplicated().any(), "Duplicate station timestamps.")
    check(bool(((timestamps.dt.minute % 15 == 0) & (timestamps.dt.second == 0)).all()),
          "Station timestamp falls outside the 15-minute grid.")
    directions = {"prevailing_wind_direction", "high_wind_direction"}
    for col in weather.columns:
        if col not in {"timestamp_local", "timestamp_source_text"} | directions:
            weather[col] = pd.to_numeric(weather[col], errors="raise")
    weather = weather.sort_values("timestamp_local").reset_index(drop=True)
    rad = weather["solar_radiation_w_m2"]
    weather["radiation_valid"] = rad.notna() & np.isfinite(rad) & rad.ge(0)
    weather["radiation_status"] = np.select(
        [rad.isna(), ~np.isfinite(rad) | rad.lt(0)],
        ["missing_measurement", "invalid_measurement"], default="observed")
    weather["source_kind"] = "historical_station_observation"
    weather["timezone_status"] = cfg["station_timezone_status"]
    for original, normalized in mapping.items():
        normalized = {"date_and_time": "timestamp_source_text",
                      "solar_rad_w_m2": "solar_radiation_w_m2"}.get(normalized, normalized)
        MEANINGS[normalized] = f"Source station field: {original}; missing values preserved."
    pd.DataFrame([{"source_column": a, "clean_column":
                   {"date_and_time": "timestamp_source_text", "solar_rad_w_m2": "solar_radiation_w_m2"}.get(b, b)}
                  for a, b in mapping.items()]).to_csv(root / "docs/solar_column_mapping.csv", index=False)
    export_table("solar_weather_clean", weather, root)

    grid_index = pd.date_range(timestamps.min(), timestamps.max(), freq="15min", tz=cfg["timezone"])
    grid = weather.set_index("timestamp_local")[["source_row_number", "solar_radiation_w_m2",
                                                "radiation_valid", "radiation_status"]].reindex(grid_index)
    grid.index.name = "timestamp_local"
    grid["source_row_present"] = grid["source_row_number"].notna()
    grid["source_row_number"] = grid["source_row_number"].astype("Int64")
    grid["radiation_valid"] = grid["radiation_valid"].eq(True)
    grid["radiation_status"] = grid["radiation_status"].fillna("missing_source_row")
    grid = grid.reset_index()
    dt = grid["timestamp_local"].dt
    grid["local_date"] = dt.strftime("%Y-%m-%d")
    grid["minute_of_day"] = dt.hour * 60 + dt.minute
    grid["day_of_year"] = dt.dayofyear
    grid["month"] = dt.month
    year_length = np.where(dt.is_leap_year, 366, 365)
    grid["time_sin"] = np.sin(2 * np.pi * grid["minute_of_day"] / 1440)
    grid["time_cos"] = np.cos(2 * np.pi * grid["minute_of_day"] / 1440)
    grid["year_sin"] = np.sin(2 * np.pi * (grid["day_of_year"] - 1) / year_length)
    grid["year_cos"] = np.cos(2 * np.pi * (grid["day_of_year"] - 1) / year_length)
    grid["solar_elevation_deg"] = [elevation(observer, t.to_pydatetime(), with_refraction=False)
                                    for t in grid["timestamp_local"]]
    grid["geometry_scope"] = "campus_proxy"
    export_table("solar_15min_grid", grid, root)
    features = ["minute_of_day", "day_of_year", "month", "time_sin", "time_cos",
                "year_sin", "year_cos", "solar_elevation_deg"]
    model = grid.loc[grid["radiation_valid"],
                     ["timestamp_local", "source_row_number", *features, "solar_radiation_w_m2"]].copy()
    dates = model["timestamp_local"].dt.strftime("%Y-%m-%d")
    model["split"] = np.select([dates < cfg["validation_start"], dates < cfg["test_start"]],
                                ["train", "validation"], default="test")
    export_table("solar_model_input", model, root)
    (root / "config/model_features.json").write_text(json.dumps({
        "features": features, "target": "solar_radiation_w_m2",
        "excluded_from_features": ["timestamp_local", "source_row_number", "split"],
        "geometry_scope": "campus_proxy", "mode": "historical_seasonal_profile",
        "notes": "No contemporaneous weather, target-derived high radiation, or future measurements."}, indent=2), encoding="utf-8")
    daily = grid.groupby("local_date", as_index=False).agg(
        expected_slots_in_export_window=("source_row_present", "size"),
        source_rows_present=("source_row_present", "sum"),
        valid_radiation_slots=("radiation_valid", "sum"))
    daily["missing_source_slots"] = daily["expected_slots_in_export_window"] - daily["source_rows_present"]
    daily["missing_or_invalid_radiation_slots"] = daily["expected_slots_in_export_window"] - daily["valid_radiation_slots"]
    daily["radiation_coverage_fraction"] = daily["valid_radiation_slots"] / daily["expected_slots_in_export_window"]
    daily["partial_export_day"] = daily["expected_slots_in_export_window"].ne(96)
    export_table("solar_daily_coverage", daily, root)
    return {"source_rows": len(raw), "source_measurement_columns": len(raw.columns) - 1,
            "first_timestamp": str(weather.timestamp_local.min()),
            "last_timestamp": str(weather.timestamp_local.max()),
            "valid_radiation_rows": int(weather.radiation_valid.sum()),
            "missing_radiation_in_source_rows": int(rad.isna().sum()),
            "invalid_nonmissing_radiation_rows": int((rad.notna() & ~weather.radiation_valid).sum()),
            "expected_grid_rows": len(grid), "missing_source_rows": int((~grid.source_row_present).sum()),
            "last_valid_radiation_timestamp": str(model.timestamp_local.max()),
            "split_counts": {k: int(v) for k, v in model.split.value_counts().items()},
            "negative_radiation_rows": int(rad.lt(0).sum()), "synthetic_measurements": 0}


def combine_date_time(date_value, time_value, timezone: str) -> pd.Timestamp:
    check(pd.notna(date_value) and pd.notna(time_value), "Missing switching date or time.")
    date = pd.Timestamp(date_value).date()
    if hasattr(time_value, "hour"):
        time_text = f"{time_value.hour:02d}:{time_value.minute:02d}:{time_value.second:02d}"
    else:
        time_text = str(time_value).strip()
    return pd.Timestamp(f"{date} {time_text}").tz_localize(timezone)


def prepare_lighting(root: Path, cfg: dict) -> dict:
    frame = pd.read_excel(root / "data/raw/lighting_observations_original.xlsx",
                          sheet_name="Fill here", usecols="A:H")
    # Instruction rows below the entry area lack a numeric installed count.
    count = pd.to_numeric(frame.iloc[:, 3], errors="coerce")
    frame = frame.loc[count.notna()].copy()
    frame.columns = ["location_name", "source_type", "obstruction", "installed_lights",
                     "on_date", "on_time", "off_date", "off_time"]
    frame["source_excel_row"] = frame.index + 2
    for col in ["location_name", "source_type", "obstruction"]:
        frame[col] = frame[col].astype(str).str.strip()
    check(set(frame.location_name) == set(cfg["location_ids"]), "Unexpected or missing inventory locations.")
    check(bool((pd.to_numeric(frame.installed_lights) % 1 == 0).all()), "Noninteger fixture counts.")
    frame["installed_lights"] = pd.to_numeric(frame.installed_lights).astype(int)
    check(bool(frame.installed_lights.gt(0).all()), "Installed counts must be positive.")
    check(bool((frame.groupby("location_name")[["source_type", "obstruction", "installed_lights"]]
                .nunique() <= 1).all().all()), "Conflicting inventory across observations.")
    locations = []
    observations = []
    for name, group in frame.groupby("location_name", sort=False):
        row = group.iloc[0]
        fixture = "floodlight" if name == cfg["border_road_name"] else (
            "tube_light" if row.source_type == "Corridor lights" else "streetlight")
        nmin, nmax = cfg["nonworking_ranges"][fixture]
        power = cfg["power_ratings"][fixture]
        location_id = cfg["location_ids"][name]
        locations.append({"location_id": location_id, "location_name": name,
            "site_type": "corridor" if fixture == "tube_light" else "outdoor_road",
            "fixture_type": fixture, "source_workbook_type": row.source_type,
            "main_obstruction": row.obstruction, "installed_lights": int(row.installed_lights),
            "installed_count_basis": "user_assumed_not_field_counted",
            "nonworking_min": nmin, "nonworking_max": nmax,
            "working_lights_min": int(row.installed_lights) - nmax,
            "working_lights_max": int(row.installed_lights) - nmin,
            "availability_basis": "no_failures_reported_all_installed_used" if fixture == "tube_light"
                else "user_occasional_failure_estimate_not_daily_inspection",
            "rated_power_w": power["watts"], "power_basis": cfg["power_basis"],
            "power_source_id": power["source_id"], "power_source_url": power["source_url"],
            "installed_model_verified": False,
            "technology_status": "led_variant_used_actual_technology_unverified",
            "latitude": np.nan, "longitude": np.nan, "coordinate_status": "individual_location_unverified",
            "astronomy_latitude": cfg["campus_proxy"]["latitude"],
            "astronomy_longitude": cfg["campus_proxy"]["longitude"],
            "geometry_scope": "campus_proxy", "timezone": cfg["timezone"],
            "inventory_source": "user_workbook_with_conversation_corrections"})
        for _, entry in group.iterrows():
            on = combine_date_time(entry.on_date, entry.on_time, cfg["timezone"])
            off = combine_date_time(entry.off_date, entry.off_time, cfg["timezone"])
            check(off > on and off - on <= pd.Timedelta(days=1), "Invalid ON/OFF interval.")
            observations.append({"observation_id": f"{location_id}_{on:%Y%m%d}",
                "location_id": location_id, "on_timestamp_local": on, "off_timestamp_local": off,
                "night_start_date": on.strftime("%Y-%m-%d"),
                "manual_on_duration_hours": (off-on).total_seconds()/3600,
                "timing_basis": "user_observed", "timing_resolution_minutes": np.nan,
                "source_excel_row": int(entry.source_excel_row), "source_sheet": "Fill here",
                "continuous_on_between_endpoints_verified": False})
    loc = pd.DataFrame(locations).sort_values("location_id").reset_index(drop=True)
    obs = pd.DataFrame(observations).sort_values(["on_timestamp_local", "location_id"]).reset_index(drop=True)
    check(not obs.observation_id.duplicated().any(), "Duplicate location-night observations.")
    check(bool(loc.working_lights_min.ge(0).all()), "Nonworking count exceeds installed fixtures.")
    check(bool(loc.working_lights_max.le(loc.installed_lights).all()), "Working count exceeds installed.")
    export_table("locations", loc, root)
    export_table("switching_observations", obs, root)
    energy = obs[["observation_id", "location_id", "night_start_date", "manual_on_duration_hours"]].merge(
        loc[["location_id", "rated_power_w", "working_lights_min", "working_lights_max"]],
        on="location_id", validate="many_to_one")
    for bound in ["min", "max"]:
        energy[f"working_fixture_hours_{bound}"] = energy[f"working_lights_{bound}"] * energy.manual_on_duration_hours
        energy[f"manual_energy_kwh_{bound}"] = energy[f"working_fixture_hours_{bound}"] * energy.rated_power_w / 1000
    energy["energy_basis"] = "estimated_continuous_operation_at_rated_power"
    export_table("manual_energy_baseline", energy, root)
    return {"locations": len(loc), "observed_intervals": len(obs),
            "installed_fixtures": int(loc.installed_lights.sum()),
            "working_fixtures_min": int(loc.working_lights_min.sum()),
            "working_fixtures_max": int(loc.working_lights_max.sum()),
            "observed_nights": sorted(obs.night_start_date.unique().tolist()),
            "manual_energy_total_kwh_min": float(energy.manual_energy_kwh_min.sum()),
            "manual_energy_total_kwh_max": float(energy.manual_energy_kwh_max.sum()),
            "note": "Totals cover only the recorded intervals. Energy is estimated consumption, not waste or savings."}


def prepare_astronomy(root: Path, cfg: dict, observer: Observer) -> None:
    dates = set()
    obs = TABLES["switching_observations"]
    dates.update(obs.on_timestamp_local.dt.strftime("%Y-%m-%d"))
    dates.update(obs.off_timestamp_local.dt.strftime("%Y-%m-%d"))
    rows = []
    for date in sorted(dates):
        times = sun(observer, date=pd.Timestamp(date).date(), dawn_dusk_depression=6,
                    tzinfo=cfg["timezone"])
        rows.append({"local_date": date, "civil_dawn_local": times["dawn"],
                     "sunrise_local": times["sunrise"], "solar_noon_local": times["noon"],
                     "sunset_local": times["sunset"], "civil_dusk_local": times["dusk"],
                     "astronomy_latitude": observer.latitude, "astronomy_longitude": observer.longitude,
                     "geometry_scope": "campus_proxy", "source_kind": "astral_3_2_calculation"})
    export_table("astronomy_daily", pd.DataFrame(rows), root)


def unit_for(col: str) -> str:
    if "timestamp" in col and "text" not in col or col in {"civil_dawn_local", "sunrise_local", "solar_noon_local", "sunset_local", "civil_dusk_local"}:
        return "ISO 8601, Asia/Kolkata (+05:30)"
    for suffix, unit in [("_w_m2", "W/m²"), ("_kwh_min", "kWh"), ("_kwh_max", "kWh"),
                         ("_w", "W/fixture"), ("_hours", "hours"), ("_pct", "%"),
                         ("_c", "°C"), ("_mmhg", "mmHg"), ("_m_s", "m/s"),
                         ("_mm_h", "mm/h"), ("_mm", "mm"), ("_deg", "degrees")]:
        if col.endswith(suffix): return unit
    if "latitude" in col or "longitude" in col: return "decimal degrees"
    if "fixture_hours" in col: return "fixture-hours"
    if "lights" in col or "nonworking" in col or "slots" in col or "rows_present" in col: return "count"
    return "see definition"


def build(root: Path = ROOT) -> dict:
    TABLES.clear()
    root = Path(root)
    for name in ["data/processed", "docs", "reports", "reports/figures"]:
        (root / name).mkdir(parents=True, exist_ok=True)
    cfg = json.loads((root / "config/project_config.json").read_text(encoding="utf-8"))
    proxy = cfg["campus_proxy"]
    observer = Observer(proxy["latitude"], proxy["longitude"], proxy["elevation_m"])
    solar_report = prepare_solar(root, cfg, observer)
    lighting_report = prepare_lighting(root, cfg)
    prepare_astronomy(root, cfg, observer)
    raw_files = [root / "data/raw/solar_station_original.csv", root / "data/raw/lighting_observations_original.xlsx"]
    sources = [{"path": str(p.relative_to(root)).replace("\\", "/"), "sha256": sha256(p),
                "bytes": p.stat().st_size} for p in raw_files]
    (root / "reports/source_manifest.json").write_text(json.dumps(sources, indent=2), encoding="utf-8")
    report = {"status": "passed", "solar": solar_report, "lighting": lighting_report,
              "limitations": ["Station timezone interpreted as campus local; provider confirmation pending.",
                "Individual location GPS and installed fixture models unverified.",
                "Historical radiation and 2026 observations do not overlap.",
                "No measured lux, recommended schedule ground truth, metered energy or computed savings.",
                "Identical schedules on both nights retained as supplied, not expanded into more observations."]}
    (root / "reports/data_quality.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    text = ["# LightSync data quality report", "", "Preparation and structural checks passed.", "",
            "## Solar export", *[f"- {k}: {v}" for k, v in solar_report.items()], "",
            "## Lighting inventory and observations", *[f"- {k}: {v}" for k, v in lighting_report.items()], "",
            "## Interpretation limits", *[f"- {v}" for v in report["limitations"]]]
    (root / "reports/data_quality.md").write_text("\n".join(text) + "\n", encoding="utf-8")
    definitions = json.loads((root / "config/field_definitions.json").read_text(encoding="utf-8"))
    MEANINGS.update(definitions)
    dictionary = []
    manifest = []
    for name, frame in TABLES.items():
        for col in frame:
            check(col in MEANINGS, f"Missing dictionary definition: {col}")
            dictionary.append({"dataset": name, "column": col, "dtype": str(frame[col].dtype),
                               "unit": unit_for(col), "missing_rows": int(frame[col].isna().sum()),
                               "definition": MEANINGS[col]})
        paths = [root / "data/processed" / f"{name}.{ext}" for ext in ["csv", "parquet"]]
        manifest.append({"dataset": name, "rows": len(frame), "columns": len(frame.columns),
                         "files": [{"path": str(p.relative_to(root)).replace("\\", "/"),
                                    "sha256": sha256(p), "bytes": p.stat().st_size} for p in paths]})
    pd.DataFrame(dictionary).to_csv(root / "docs/DATA_DICTIONARY.csv", index=False)
    (root / "reports/dataset_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    print(json.dumps(build(), indent=2))
