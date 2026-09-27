# LightSync

Daylight-aware lighting schedule proposals for ten IIT Guwahati road and corridor zones. The prototype combines observed manual switching times, historical solar radiation and obstruction scenarios to compare lighting duration and estimated energy use.

## Submission contents

| Required item | File / folder |
|---|---|
| Code | `app.py`, `src/`, `tests/` |
| Collected-data sample | [20 event observations](data/sample/event_observations.csv) |
| Sample schema | [SAMPLE_SCHEMA.csv](docs/SAMPLE_SCHEMA.csv) |
| Full dataset schema | [DATA_DICTIONARY.csv](docs/DATA_DICTIONARY.csv) |
| Derived-output schema | [SCENARIO_DATA_DICTIONARY.md](docs/SCENARIO_DATA_DICTIONARY.md) |
| Row counts, collection window, sources, provenance and AI use | [DATA_DOCUMENTATION.md](docs/DATA_DOCUMENTATION.md) |
| Executed analysis | Three numbered notebooks in this folder |
| Model evaluation | `reports/modeling/` |

## Run the dashboard

Python 3.12 was used for verification. From this folder:

```sh
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

The included processed data and saved model files support the dashboard without API keys. Use the tested versions in `reports/tested_package_versions.json` when reproducing the environment. Saved scikit-learn models may need regeneration if library versions differ.

## Notebooks and reproducibility

1. `01_Data_Preparation.ipynb`: cleaning, missingness, schema and provenance. Its executed outputs are included. Rerunning requires original inputs at the paths in `data/raw/README.md`; those originals are excluded from this public bundle.
2. `02_Model_Training.ipynb`: train and compare simple models using included processed historical data.
3. `03_Lighting_and_Energy.ipynb`: generate lighting scenarios and compare energy against observed schedules.

To retrain and regenerate from included processed data:

```sh
python -m src.modeling
python -m src.lighting
python -m unittest discover -s tests
```

`data/processed` contains clean data; `data/scenarios` contains predictions and calculated impacts. CSV files are openly inspectable; Parquet files preserve types and power the app. `models` contains evaluation and dashboard model artifacts. `config` stores parameters and source references. `scripts` contains app/notebook checks and map retrieval. Map attribution is in `data/map/SOURCE.md`.

## Evidence and limits

- Ten locations; 20 independently observed manual switching intervals across nights of 25–26 and 26–27 September 2026. Event window reported as 25 September evening through 27 September at 17:00 IST. Checking cadence and timing precision remain undocumented.
- 20,193 valid historical solar radiation targets, separate from event-collected observations. No synthetic measurement augmentation.
- Installed light counts are assumed. Road counts use approximate road lengths and fixture spacing, not direct counts; corridor estimation method is undocumented. Wattages are published product references, not verified installed models.
- Random Forest predicts a historical radiation profile. Daylight/lux conversion and obstruction factors are uncalibrated scenarios; one-minute interpolation does not establish one-minute accuracy.
- Central scenario: approximately 108–109 kWh net saving across two nights, including extra requested lighting. Lower daylight can require more energy. These are conditional estimates, not metered savings or proof of adequate illumination.
- Cost/carbon depend on entered factors. AI coding assistance and model use are described in the data documentation.

No live infrastructure control or image-model processing is implemented. Optional weather forecasts are now supported.

## Selected-date predictions

Choose a future night in the sidebar calendar. The trained model predicts a new radiation profile using the selected date and solar position, with recalculated sunrise/sunset. All ten locations receive schedules. For dates without observations, manual timings reuse the latest observed night as a labelled baseline. Predictions are historical-pattern estimates, not live weather forecasts. The custom-location form uses the same date. Original observations remain unchanged.

## Optional weather forecast integration

Enable **Use weather forecast when available** in the sidebar. Open-Meteo provides hourly instantaneous shortwave radiation, cloud cover, temperature and precipitation probability, with daily sunrise/sunset. Forecast radiation replaces the historical ML radiation profile when the complete noon-to-next-noon window is available; cloud attenuation is not applied twice. Historical ML remains the fallback and is not claimed to have been retrained on forecast weather.

Forecast requests use the public campus reference coordinate. The 16-day API window allows complete overnight predictions for today through today + 14 days. Other dates, incomplete responses and network failures use historical ML with Astral sunrise/sunset. API results are cached for 30 minutes; source, retrieval time and hourly cadence are shown. Weather values are predictions, not event-collected observations. One-minute interpolation does not give minute-level forecast accuracy.

Source and attribution: [Open-Meteo](https://open-meteo.com/), [API documentation](https://open-meteo.com/en/docs). No key is configured for this prototype; review provider terms before commercial deployment.

## Field logging and stronger evaluation

The **Observation log** tab saves real timestamped field checks locally and exports CSV; no test records are included. See [log schema and storage](docs/OBSERVATION_LOG.md). Local field logs are Git-ignored and separate from the original observations and scenario tables.

[Rolling evaluation](docs/MODEL_EVALUATION.md) compares three candidates over four expanding chronological folds, emphasising dawn and dusk equally. Random Forest remains selected, narrowly ahead of the hybrid; no statistically significant superiority or new unseen-test claim is made. Run `python -m src.rolling_evaluation` to reproduce.

## Streamlit Community Cloud

Deploy `Nish-011-100/LightSync`, branch `main`, entrypoint `app.py`, with Python 3.12. Runtime dependencies are pinned to the tested local versions, including scikit-learn and its numerical dependencies for saved-model compatibility. Server address is left to the hosting provider. No secrets are required for the public weather endpoint. Local startup remains `python -m streamlit run app.py`; to restrict a local session to loopback, add `--server.address 127.0.0.1`.

The observation log is a shared, unauthenticated demo feature on a hosted server. Use anonymous test data only; export anything needed because local storage may reset on redeployment. Durable private field logging requires authenticated external storage.
