"""Offline lighting scenarios and exact interval energy accounting.

These are conditional schedule proposals, not calibrated lux predictions or safety certification.
"""
from __future__ import annotations
import json
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from scipy.interpolate import PchipInterpolator
from src.modeling import make_features, predict_nonnegative
from src.prepare_data import ROOT, sha256


def interval_impact(manual_on, manual_off, proposed_on, proposed_off, power_w, working_count):
    """Use exact interval intersections; supports both positive and negative net savings."""
    for start, end in [(manual_on, manual_off), (proposed_on, proposed_off)]:
        if end < start:
            raise ValueError('Interval end precedes its start.')
    if power_w < 0 or working_count < 0:
        raise ValueError('Power and working counts must be nonnegative.')
    hours = lambda delta: delta.total_seconds()/3600
    actual = hours(manual_off-manual_on)
    proposed = hours(proposed_off-proposed_on)
    overlap = max(0., hours(min(manual_off, proposed_off)-max(manual_on, proposed_on)))
    excess_hours = actual-overlap
    added_hours = proposed-overlap
    kw = power_w * working_count / 1000
    return {'manual_hours': actual, 'recommended_hours': proposed,
            'excess_on_hours': excess_hours, 'additional_on_hours': added_hours,
            'manual_kwh': actual*kw, 'recommended_kwh': proposed*kw,
            'excess_kwh': excess_hours*kw, 'additional_kwh': added_hours*kw,
            'net_savings_kwh': (actual-proposed)*kw}


def first_persistent(mask, samples=2):
    mask = np.asarray(mask, dtype=bool)
    for i in range(len(mask)-samples+1):
        if mask[i:i+samples].all():
            return i
    return None


def propose_interval(profile, sunset, sunrise, on_lux, off_lux, policy):
    if off_lux <= on_lux or on_lux < 0:
        raise ValueError('OFF threshold must exceed nonnegative ON threshold.')
    times = pd.DatetimeIndex(profile.timestamp_local)
    sunset = pd.Timestamp(sunset)
    sunrise = pd.Timestamp(sunrise)
    step = pd.Timedelta(minutes=policy['step_minutes'])
    evening = profile.loc[(profile.timestamp_local.dt.date == sunset.date()) & (profile.timestamp_local <= sunset)]
    # Cover every modelled evening deficit, not just persistent darkness. The first
    # deficit is the latest feasible ON boundary for one continuous overnight interval.
    dim = evening.loc[evening.lux_proxy.lt(on_lux)]
    guard_on = sunset.floor('min')
    proposed_on = guard_on
    if not dim.empty:
        proposed_on = min(dim.iloc[0].timestamp_local - pd.Timedelta(minutes=policy.get('switch_on_buffer_minutes',0)), guard_on)
    proposed_on = max(times[0],proposed_on).floor('min')
    morning = profile.loc[profile.timestamp_local >= sunrise.ceil('min')].copy()
    stable = policy.get('stable_daylight_minutes',5)
    n = max(1,int(np.ceil(stable/policy['step_minutes'])))
    # Earliest OFF satisfying the full remaining forecast window. Lookahead persistence
    # validates stability without adding a whole sampling interval of wasted ON time.
    values=morning.lux_proxy.to_numpy()
    candidates=np.flatnonzero(np.logical_and.accumulate((values>=off_lux)[::-1])[::-1])
    candidates=[i for i in candidates if len(morning)-i>=n]
    unresolved = len(candidates)==0
    proposed_off = times[-1]+step if unresolved else morning.iloc[candidates[0]].timestamp_local + pd.Timedelta(minutes=policy.get('switch_off_buffer_minutes',0))
    proposed_off = min(proposed_off,times[-1]+step).ceil('min')
    if proposed_off <= proposed_on:
        raise ValueError('Schedule crosses the wrong date boundary.')
    return proposed_on, proposed_off, unresolved


def build_scenarios(root=ROOT):
    root = Path(root)
    cfg = json.loads((root/'config/project_config.json').read_text())
    policy = json.loads((root/'config/lighting_policy.json').read_text())
    loc = pd.read_parquet(root/'data/processed/locations.parquet').set_index('location_id')
    obs = pd.read_parquet(root/'data/processed/switching_observations.parquet')
    astro = pd.read_parquet(root/'data/processed/astronomy_daily.parquet').set_index('local_date')
    model_path = root/'models/demo_radiation_model.joblib'
    bundle = joblib.load(model_path)
    if bundle['source_sha256'] != sha256(root/'data/processed/solar_model_input.parquet'):
        raise ValueError('Model input changed. Rerun the training notebook before scenarios.')
    all_profiles, schedules, impacts = [], [], []
    # Predict once per night; all sites share campus geometry, then apply site scenarios.
    profiles = {}
    for day in obs.night_start_date.unique():
        start = pd.Timestamp(f'{day} 12:00').tz_localize(cfg['timezone'])
        coarse = pd.date_range(start, start+pd.Timedelta(days=1), freq=f'{policy["source_step_minutes"]}min')
        X = make_features(coarse, cfg)
        radiation = predict_nonnegative(bundle['model'], X[bundle['features']])
        ts = pd.date_range(start,start+pd.Timedelta(days=1),freq=f'{policy["step_minutes"]}min',inclusive='left')
        minutes=(ts-start).total_seconds()/60
        interpolator=PchipInterpolator((coarse-start).total_seconds()/60,radiation)
        dense=make_features(ts,cfg)
        profiles[day] = pd.DataFrame({'timestamp_local':ts, 'solar_elevation_deg':dense.solar_elevation_deg,
            'radiation_prediction_w_m2':np.maximum(0,interpolator(minutes))})
    for row in obs.itertuples(index=False):
        site = loc.loc[row.location_id]
        base = profiles[row.night_start_date]
        sunset = astro.loc[row.night_start_date, 'sunset_local']
        sunrise = astro.loc[row.off_timestamp_local.strftime('%Y-%m-%d'), 'sunrise_local']
        if site.main_obstruction not in policy['daylight_transfer']:
            raise ValueError(f'No daylight scenario for {site.main_obstruction}')
        thresholds = policy['thresholds_lux'][site.site_type]
        for scenario in ['lower_daylight', 'central', 'higher_daylight']:
            transfer = policy['daylight_transfer'][site.main_obstruction][scenario]
            efficacy = policy['luminous_efficacy_lm_per_w'][scenario]
            p = base.copy()
            # Preserve low-sun station-profile information without inventing twilight lux.
            # Astronomy guards prevent OFF in the night even if tiny model residuals exist.
            daylight_rad = np.where(p.solar_elevation_deg.gt(-6), p.radiation_prediction_w_m2, 0)
            p['lux_proxy'] = daylight_rad * efficacy * transfer
            on, off, unresolved = propose_interval(p, sunset, sunrise, thresholds['on'], thresholds['off'], policy)
            p['manual_on_reconstructed'] = (p.timestamp_local >= row.on_timestamp_local) & (p.timestamp_local < row.off_timestamp_local)
            p['recommended_on'] = (p.timestamp_local >= on) & (p.timestamp_local < off)
            p['observation_id'] = row.observation_id
            p['location_id'] = row.location_id
            p['scenario'] = scenario
            p['on_threshold_lux'] = thresholds['on']
            p['off_threshold_lux'] = thresholds['off']
            all_profiles.append(p)
            schedules.append({'observation_id': row.observation_id, 'location_id': row.location_id,
                'location_name': site.location_name, 'night_start_date': row.night_start_date,
                'scenario': scenario, 'manual_on_local': row.on_timestamp_local,
                'manual_off_local': row.off_timestamp_local, 'recommended_on_local': on,
                'recommended_off_local': off, 'sunset_local': sunset, 'sunrise_local': sunrise,
                'daylight_transfer': transfer, 'luminous_efficacy_lm_per_w': efficacy,
                'on_threshold_lux': thresholds['on'], 'off_threshold_lux': thresholds['off'],
                'review_required': True, 'off_not_reached_within_window': unresolved,
                'decision_resolution_minutes': policy['step_minutes'],
                'input_cadence_minutes': policy['source_step_minutes'],
                'basis': 'uncalibrated_historical_profile_scenario'})
            for bound in ['min', 'max']:
                count = int(site[f'working_lights_{bound}'])
                impact = interval_impact(row.on_timestamp_local, row.off_timestamp_local,
                                         on, off, site.rated_power_w, count)
                tariff = cfg['electricity_tariff_inr_per_kwh']
                carbon = cfg['grid_emission_factor_kg_co2_per_kwh']
                impacts.append({'observation_id': row.observation_id, 'location_id': row.location_id,
                    'night_start_date': row.night_start_date, 'scenario': scenario,
                    'working_count_case': bound, 'working_lights': count, 'rated_power_w': site.rated_power_w,
                    **impact, 'tariff_inr_per_kwh': tariff, 'emission_factor_kg_co2_per_kwh': carbon,
                    'net_savings_inr': None if tariff is None else impact['net_savings_kwh']*tariff,
                    'net_avoided_kg_co2': None if carbon is None else impact['net_savings_kwh']*carbon,
                    'status': 'scenario_estimate_not_measured_savings'})
    result = {'lighting_profiles': pd.concat(all_profiles, ignore_index=True),
              'recommended_schedules': pd.DataFrame(schedules), 'energy_impact': pd.DataFrame(impacts)}
    out = root/'data/scenarios'
    out.mkdir(parents=True, exist_ok=True)
    for name, frame in result.items():
        frame.to_csv(out/f'{name}.csv', index=False)
        frame.to_parquet(out/f'{name}.parquet', index=False)
    impact = result['energy_impact']
    totals = impact.groupby(['scenario', 'working_count_case'], as_index=False)[[
        'manual_kwh', 'recommended_kwh', 'excess_kwh', 'additional_kwh', 'net_savings_kwh']].sum()
    totals['net_savings_percent'] = 100 * totals.net_savings_kwh / totals.manual_kwh
    totals.to_csv(out/'impact_summary.csv', index=False)
    assert np.allclose(impact.manual_kwh-impact.recommended_kwh, impact.net_savings_kwh)
    assert np.allclose(impact.excess_kwh-impact.additional_kwh, impact.net_savings_kwh)
    assert (impact[['excess_kwh','additional_kwh']] >= 0).all().all()
    manual = pd.read_parquet(root/'data/processed/manual_energy_baseline.parquet').set_index('observation_id')
    for bound in ['min','max']:
        subset = impact[impact.working_count_case.eq(bound)]
        assert np.allclose(subset.manual_kwh, subset.observation_id.map(manual[f'manual_energy_kwh_{bound}']))
    metadata = {'prediction_mode': policy['mode'], 'selected_model': bundle['name'],
        'model_sha256': sha256(model_path), 'policy_sha256': sha256(root/'config/lighting_policy.json'),
        'observation_intervals': len(obs), 'scenario_schedule_rows': len(result['recommended_schedules']),
        'all_schedules_require_field_review': True, 'lux_validation': 'unavailable',
        'counts_are_scenarios_not_dated_failure_logs': True,
        'manual_off_outside_observed_interval': 'schedule_reconstruction_not_continuous_state_measurement',
        'cost_carbon_status': 'unset' if cfg['electricity_tariff_inr_per_kwh'] is None or cfg['grid_emission_factor_kg_co2_per_kwh'] is None else 'configured',
        'not_confidence_intervals': True}
    metadata['decision_resolution_minutes']=policy['step_minutes']
    metadata['source_cadence_minutes']=policy['source_step_minutes']
    metadata['interpolation']='shape-preserving PCHIP; no new measured information'
    (out/'scenario_metadata.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    return result, totals


if __name__ == '__main__':
    result, totals = build_scenarios()
    print(totals.to_string(index=False))
