# Rolling chronological evaluation

Three candidates: elevation baseline, Random Forest, Random Forest plus monotone dawn/dusk curves. Four expanding folds train on all available earlier data from March 2024 and validate June, July, August and September separately. No later-month labels enter a fold fit. October onward is excluded from this comparison.

The declared score for this run is 40% dawn MAE + 40% dusk MAE + 20% daytime MAE. Each eligible month has equal weight and at least 30 labels in each segment. Reports include sample counts, per-segment MAE/RMSE/bias/R², fold spread and worst-fold score. This is retrospective development validation on previously inspected data, not a new untouched test. Radiation units are W/m²; this does not validate lux or switching-time accuracy.

Result: retain Random Forest (mean score 35.840; worst fold 38.177), narrowly ahead of the hybrid (35.857; worst fold 38.331). Elevation baseline: 39.487. The hybrid has slightly better mean dusk MAE (14.041 vs 14.140), while Random Forest has better dawn MAE (8.715 vs 8.856). The overall difference is tiny and no statistical superiority is claimed. The previously reported later test dusk weakness remains; this evaluation does not erase it.

Run `python -m src.rolling_evaluation` to reproduce. Inspect reports/modeling/rolling_folds.csv, rolling_metrics.csv, rolling_leaderboard.csv and rolling_evaluation.json. Model artifacts and existing scenario values are unchanged. Local lux validation and new independent transition observations remain the next evidence needed.
