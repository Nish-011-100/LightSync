# Original inputs

Local copies are preserved byte for byte:

- `solar_station_original.csv`: the user's IIT Solar Energy Lab Guwahati 2024–2025 export, with five metadata rows.
- `lighting_observations_original.xlsx`: the user's completed LightSync entry workbook. Read only columns A:H of `Fill here`; unused exported columns are not data.

These files are ignored by Git by default. Reproduction requires placing the originals at these paths. Source checksums are recorded in `reports/source_manifest.json`. Do not overwrite the originals with cleaned data.
