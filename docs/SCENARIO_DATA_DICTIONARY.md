# Model and scenario outputs

## `reports/modeling`

- `validation_leaderboard.csv`: one row per candidate; validation score is 0.7 low-sun MAE + 0.3 daytime MAE. `selected` is fixed before test scoring.
- `validation_metrics.csv`, `test_metrics.csv`: one model/segment pair per row; `n` is sample count; MAE, RMSE and bias use W/m². R² is dimensionless and missing for constant targets. Negative R² is retained.
- `test_predictions.parquet`: historical held-out timestamp, target radiation, predicted radiation, geometric solar elevation, minute of day and model name. These are not September 2026 observations.
- `model_card.json` / `.md`: model parameters, partition sizes, input checksum, selection rule and limitations.

## `models`

- `evaluation_model.joblib`: selected model fitted on the training partition only; used for held-out metrics.
- `demo_radiation_model.joblib`: same selected specification refitted on all historical valid labels. This has no independent current-year evaluation. Bundle includes ordered feature names and training-input checksum.

## `data/scenarios/lighting_profiles`

One row per observation interval × daylight scenario × one-minute timestamp. Values interpolate 15-minute predictions using shape-preserving PCHIP. These derived rows are not additional field observations and do not imply one-minute physical accuracy.

| Column | Meaning |
|---|---|
| timestamp_local | Asia/Kolkata, offset retained |
| solar_elevation_deg | Calculated geometric solar elevation at common campus proxy |
| radiation_prediction_w_m2 | Saved model's historical-profile estimate; no current weather input |
| lux_proxy | Interpolated radiation × scenario luminous efficacy × scenario transmission; astronomical guards address unresolved twilight uncertainty |
| manual_on_reconstructed | Boolean ON between supplied observed endpoints, OFF elsewhere in noon-to-noon window |
| recommended_on | Boolean ON during the proposed interval |
| observation_id / location_id | Foreign keys into processed observations/inventory |
| scenario | `lower_daylight`, `central`, or `higher_daylight`; not probabilities or confidence bounds |
| on_threshold_lux / off_threshold_lux | Editable demonstration thresholds; not calibrated lighting standards |

## `data/scenarios/recommended_schedules`

One row per original observation interval × daylight scenario (60 rows).

- `manual_on_local` / `manual_off_local`: observed endpoints from user data.
- `recommended_on_local` / `recommended_off_local`: proposed interval at one-minute decision resolution; conditional on interpolated model and policy. Not a claim of one-minute accuracy.
- `decision_resolution_minutes` / `input_cadence_minutes`: distinguish the one-minute decision grid from 15-minute source sampling.
- `sunset_local` / `sunrise_local`: calculated campus astronomical event times.
- `daylight_transfer`, `luminous_efficacy_lm_per_w`, thresholds: uncalibrated inputs recorded on each row for traceability.
- `review_required`: true for every proposal.
- `off_not_reached_within_window`: true if insufficient proxy daylight persists until noon; the interval ends at the analysis boundary, not an established safe OFF time.
- `basis`: distinguishes scenario proposals from observed schedules.

## `data/scenarios/energy_impact`

One row per observation × daylight scenario × working-count case (120 rows).

- `working_count_case` = min/max **fixture count**, not necessarily minimum/maximum savings. For negative savings, more fixtures mean a more negative result.
- `manual_hours` / `recommended_hours`: exact elapsed hours, including midnight rollover.
- `excess_on_hours`: manual interval outside proposed interval.
- `additional_on_hours`: proposed interval outside manual interval; a scenario request for extra light, not measured underlighting duration.
- `manual_kwh`, `recommended_kwh`, `excess_kwh`, `additional_kwh`: hours × identical working count × power / 1000.
- `net_savings_kwh`: manual minus proposed, also excess minus additional. Negative values are retained.
- `tariff_inr_per_kwh`, `emission_factor_kg_co2_per_kwh`: nullable configuration inputs.
- `net_savings_inr`, `net_avoided_kg_co2`: nullable products of net kWh and configured factors. Negative means added cost/emissions.
- `status`: explicitly marks scenario estimates rather than measured savings.

`impact_summary.csv` sums the recorded intervals by scenario and count case. Do not sum across scenarios/count cases: they are alternative calculations over the same lights. Percent savings is total net kWh / total manual kWh, not an average of location percentages. No annual extrapolation is made.

`scenario_metadata.json` records model and policy checksums and interpretation limits.
