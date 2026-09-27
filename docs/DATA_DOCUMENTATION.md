# Submission data documentation

## Collection and row counts

The team reports collection during the event from 25 September 2026 evening to 27 September 2026 at 17:00 IST. The exact kickoff time was not provided. Ten IIT Guwahati road/corridor zones have 20 independently observed overnight ON/OFF intervals: nights of 25–26 and 26–27 September. Both nights were independently observed even where timings match. Checking frequency, timestamp precision, observer aliases and missed-visit logs are not documented. This is endpoint observation, not continuous monitoring.

The collected-data sample is `data/sample/event_observations.csv` (20 rows). The full inventory is `data/processed/locations.csv` (10 rows). These overlap: do not sum them as independent observations. Schema: `docs/SAMPLE_SCHEMA.csv`, with full field definitions in `docs/DATA_DICTIONARY.csv`.

## Sources and cadence

Field source: the team-supplied workbook, with sheet and source-row references retained. Historical source: the supplied IIT Solar Energy Lab Guwahati CSV, nominally every 15 minutes, 7 March 2024–7 March 2025. It contains 33,441 records, of which 20,193 have valid radiation targets; 13,248 lack radiation. Another 1,600 expected timestamp slots are absent. Last valid radiation is 15 January 2025. Station timezone is interpreted as IST pending provider confirmation. Historical readings were not collected by the team during the event.

Manufacturer power-reference URLs are recorded in `config/project_config.json` and the location inventory. Map source and attribution are in `data/map/SOURCE.md`. Individual lamp GPS and installed fixture models are unverified.

## Observed versus assumed, inferred and synthetic

- Observed during event: 20 manual switching intervals and reported location/obstruction descriptions.
- Assumed: installed light counts. Road counts use approximate road lengths and fixture spacing/frequency, not direct physical counts. Exact supporting lengths/spacing were not supplied; corridor count method is undocumented. Occasional faulty-light ranges are scenarios, not dated counts.
- Referenced: historical radiation, manufacturer-rated wattages and map geometry.
- Inferred: astronomy, radiation predictions, uncalibrated daylight/lux proxies, schedules and energy/cost/carbon estimates. The 60 proposed schedule rows and 120 impact rows are derived cases, not new observations. One-minute interpolation does not add measured information.
- Synthetic measurement augmentation: zero. The event switching observations are 100% real and 0% synthetic; that percentage does not apply to assumed inventory fields, historic data or model outputs. We do not claim the whole mixed submission was collected during the event.

## AI use

An AI coding assistant assisted with cleaning code, documentation and dashboard design. Local scikit-learn models predict historical radiation from calendar and sun-position features. Random Forest was selected by chronological validation against simple alternatives. Target rows: 13,840 train, 1,820 validation and 4,533 test. The test benchmark has been inspected during development; it is not a new field trial. The demo model is refitted on the historical targets. The offline demo needs no image model, paid AI API or GPU. Optional Open-Meteo forecasts are supported as described below.

## Impact and limits

Across the two nights the central scenario estimates 107.91–108.94 kWh net savings (about 2.9%), including 29.16 kWh of additional requested lighting. Lower-daylight scenarios require approximately 25–26 kWh more energy overall. These are count- and wattage-dependent estimates, not measured savings. There are no local lux measurements or energy-meter validation. Timing changes cannot repair lamps or guarantee lighting safety. Financial/emissions factors are optional user inputs; defaults in the UI are illustrative. No annual savings claim is validated.

## Reproduction and access

Use the supplied processed data and model artifacts to run the demo. Training and scenario generation can be rerun using notebooks 02 and 03. The preparation notebook documents the original cleaning workflow; rerunning it requires the original inputs, which are not included in the public upload bundle. Their checksums are in `reports/source_manifest.json`. Original workbooks, caches, environments and local editor settings are excluded from the upload bundle. No private credentials are required.

## Optional weather forecast integration

Enable **Use weather forecast when available** in the sidebar. Open-Meteo provides hourly instantaneous shortwave radiation, cloud cover, temperature and precipitation probability, with daily sunrise/sunset. Forecast radiation replaces the historical ML radiation profile when the complete noon-to-next-noon window is available; cloud attenuation is not applied twice. Historical ML remains the fallback and is not claimed to have been retrained on forecast weather.

Forecast requests use the public campus reference coordinate. The 16-day API window allows complete overnight predictions for today through today + 14 days. Other dates, incomplete responses and network failures use historical ML with Astral sunrise/sunset. API results are cached for 30 minutes; source, retrieval time and hourly cadence are shown. Weather values are predictions, not event-collected observations. One-minute interpolation does not give minute-level forecast accuracy.

Source and attribution: [Open-Meteo](https://open-meteo.com/), [API documentation](https://open-meteo.com/en/docs). No key is configured for this prototype; review provider terms before commercial deployment.
