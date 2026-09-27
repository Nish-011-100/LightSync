# Radiation model card

Selected: **Random Forest**.

Lowest 0.7 * validation low-sun MAE + 0.3 * validation daytime MAE; baseline eligible.

The test is held out during selection. The separate demo artifact is subsequently refitted on all historical targets. Test scores describe the train-only evaluation artifact, not the all-data refit.

- No independent 2026 weather or lux validation.
- One station and less than a complete year of valid targets.
- September validation is sparse; no guaranteed switching-time accuracy.
- Model predicts radiation, not illuminance or lamp state.
