"""Small, chronological model comparison for historical solar radiation."""
from __future__ import annotations
import json
import time
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from astral import Observer
from astral.sun import elevation
from sklearn.base import BaseEstimator, RegressorMixin, clone
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.isotonic import IsotonicRegression
from threadpoolctl import threadpool_limits
from src.prepare_data import ROOT, sha256


class ElevationBaseline(RegressorMixin, BaseEstimator):
    """Mean radiation in 2-degree solar-elevation bins, fitted on training rows only."""
    def fit(self, X, y):
        bins = np.floor(np.asarray(X['solar_elevation_deg']) / 2) * 2 + 1
        grouped = pd.DataFrame({'elevation': bins, 'target': np.asarray(y)}).groupby('elevation').target.mean()
        self.elevations_ = grouped.index.to_numpy()
        self.means_ = grouped.to_numpy()
        return self

    def predict(self, X):
        return np.interp(np.asarray(X['solar_elevation_deg']), self.elevations_, self.means_)


class DawnDuskHybrid(RegressorMixin, BaseEstimator):
    """Random Forest with separate monotone dawn/dusk curves learned from training data.

    Low-sun radiation should increase with elevation within each transition. Isotonic
    regression expresses this simple relationship without a neural network. Blend to
    the forest between 10 and 20 degrees; no validation/test labels enter fit().
    """
    def fit(self, X, y):
        self.forest_ = RandomForestRegressor(n_estimators=150,max_depth=12,
            min_samples_leaf=10,n_jobs=2,random_state=42).fit(X,y)
        self.curves_ = {}
        elev=np.asarray(X['solar_elevation_deg'])
        morning=np.asarray(X['minute_of_day'])<720
        y=np.asarray(y)
        for key,phase in [('dawn',morning),('dusk',~morning)]:
            mask=phase & (elev>=-6) & (elev<=20)
            self.curves_[key]=IsotonicRegression(increasing=True,y_min=0,out_of_bounds='clip').fit(elev[mask],y[mask])
        return self

    def predict(self, X):
        elev=np.asarray(X['solar_elevation_deg'])
        morning=np.asarray(X['minute_of_day'])<720
        curve=np.where(morning,self.curves_['dawn'].predict(elev),self.curves_['dusk'].predict(elev))
        weight=np.clip((20-elev)/10,0,1)
        result=weight*curve+(1-weight)*self.forest_.predict(X)
        return np.where(elev < -6,0,result)


def predict_nonnegative(model, X):
    """Clip impossible negative radiation; no labels or future readings used."""
    with threadpool_limits(limits=2):
        return np.maximum(model.predict(X), 0)


def make_features(timestamps, project_config):
    """Same calendar/geometry definitions as preparation, usable at inference."""
    timestamps = pd.DatetimeIndex(timestamps)
    if timestamps.tz is None:
        raise ValueError('Inference timestamps must be timezone-aware.')
    timestamps = timestamps.tz_convert(project_config['timezone'])
    proxy = project_config['campus_proxy']
    observer = Observer(proxy['latitude'], proxy['longitude'], proxy['elevation_m'])
    minute = timestamps.hour * 60 + timestamps.minute
    day = timestamps.dayofyear
    length = np.where(timestamps.is_leap_year, 366, 365)
    return pd.DataFrame({'minute_of_day': minute, 'day_of_year': day, 'month': timestamps.month,
        'time_sin': np.sin(2*np.pi*minute/1440), 'time_cos': np.cos(2*np.pi*minute/1440),
        'year_sin': np.sin(2*np.pi*(day-1)/length), 'year_cos': np.cos(2*np.pi*(day-1)/length),
        'solar_elevation_deg': [elevation(observer, t.to_pydatetime(), with_refraction=False) for t in timestamps]})


def segment_masks(frame):
    e = frame.solar_elevation_deg.to_numpy()
    minute = frame.minute_of_day.to_numpy()
    low = (e >= -6) & (e <= 15)
    return {'all': np.ones(len(frame), dtype=bool), 'daytime': e > 0,
            'low_sun': low, 'dawn': low & (minute < 720),
            'dusk': low & (minute >= 720), 'night': e < -6}


def metrics(frame, predicted):
    y = frame.solar_radiation_w_m2.to_numpy()
    rows = []
    for segment, mask in segment_masks(frame).items():
        n = int(mask.sum())
        rows.append({'segment': segment, 'n': n,
            'mae_w_m2': float(mean_absolute_error(y[mask], predicted[mask])) if n else None,
            'rmse_w_m2': float(np.sqrt(mean_squared_error(y[mask], predicted[mask]))) if n else None,
            'r2': float(r2_score(y[mask], predicted[mask])) if n > 1 and np.var(y[mask]) > 0 else None,
            'bias_w_m2': float(np.mean(predicted[mask]-y[mask])) if n else None})
    return rows


def train_models(root=ROOT):
    root = Path(root)
    out = root / 'reports/modeling'
    out.mkdir(parents=True, exist_ok=True)
    (root/'models').mkdir(exist_ok=True)
    source = root/'data/processed/solar_model_input.parquet'
    data = pd.read_parquet(source)
    config = json.loads((root/'config/model_features.json').read_text())
    features = config['features']
    train, val, test = [data.loc[data.split.eq(s)].copy() for s in ['train','validation','test']]
    if min(len(train), len(val), len(test)) == 0:
        raise ValueError('All chronological partitions must contain valid targets.')
    assert train.timestamp_local.max() < val.timestamp_local.min() < test.timestamp_local.min()
    candidates = {
        'Elevation baseline': ElevationBaseline(),
        'Random Forest': RandomForestRegressor(n_estimators=150, max_depth=12,
            min_samples_leaf=10, max_features=1.0, n_jobs=2, random_state=42),
        'Random Forest + dawn/dusk curves': DawnDuskHybrid(),
        'HistGradientBoosting 15 leaves': HistGradientBoostingRegressor(max_iter=200,
            max_leaf_nodes=15, learning_rate=.05, min_samples_leaf=30, l2_regularization=1,
            early_stopping=False, random_state=42),
        'HistGradientBoosting 31 leaves': HistGradientBoostingRegressor(max_iter=200,
            max_leaf_nodes=31, learning_rate=.05, min_samples_leaf=30, l2_regularization=1,
            early_stopping=False, random_state=42)}
    fitted, validation_rows, scores = {}, [], []
    for name, candidate in candidates.items():
        start = time.perf_counter()
        with threadpool_limits(limits=2):
            candidate.fit(train[features], train.solar_radiation_w_m2)
        seconds = time.perf_counter()-start
        fitted[name] = candidate
        prediction = predict_nonnegative(candidate, val[features])
        rows = metrics(val, prediction)
        by_segment = {r['segment']: r for r in rows}
        if by_segment['low_sun']['n'] < 30 or by_segment['daytime']['n'] < 30:
            raise ValueError('Not enough daytime/low-sun validation samples for the chosen selection rule.')
        # Fixed before inspecting test outcomes: emphasise lighting-transition conditions.
        score = .7*by_segment['low_sun']['mae_w_m2'] + .3*by_segment['daytime']['mae_w_m2']
        scores.append({'model': name, 'validation_score_w_m2': score,
                       'validation_daytime_mae_w_m2': by_segment['daytime']['mae_w_m2'],
                       'validation_low_sun_mae_w_m2': by_segment['low_sun']['mae_w_m2'],
                       'training_seconds': seconds})
        validation_rows.extend([{'model': name, **r} for r in rows])
    leaderboard = pd.DataFrame(scores).sort_values('validation_score_w_m2').reset_index(drop=True)
    selected = leaderboard.iloc[0]['model']
    # Lock selection first. Test results are reporting-only; never used to choose a candidate.
    test_rows, prediction_frames = [], []
    for name, model in fitted.items():
        prediction = predict_nonnegative(model, test[features])
        test_rows.extend([{'model': name, **r} for r in metrics(test, prediction)])
        pred = test[['timestamp_local', 'solar_radiation_w_m2', 'solar_elevation_deg', 'minute_of_day']].copy()
        pred['predicted_radiation_w_m2'] = prediction
        pred['model'] = name
        prediction_frames.append(pred)
    leaderboard['selected'] = leaderboard.model.eq(selected)
    leaderboard.to_csv(out/'validation_leaderboard.csv', index=False)
    pd.DataFrame(validation_rows).to_csv(out/'validation_metrics.csv', index=False)
    test_metrics = pd.DataFrame(test_rows)
    test_metrics.to_csv(out/'test_metrics.csv', index=False)
    pd.concat(prediction_frames, ignore_index=True).to_parquet(out/'test_predictions.parquet', index=False)
    joblib.dump({'model': fitted[selected], 'features': features, 'name': selected,
        'fit_scope': 'train_only', 'source_sha256': sha256(source)}, root/'models/evaluation_model.joblib')
    # After evaluation, refit the already-selected specification on all historical labels.
    demo_model = clone(candidates[selected])
    with threadpool_limits(limits=2):
        demo_model.fit(data[features], data.solar_radiation_w_m2)
    joblib.dump({'model': demo_model, 'features': features, 'name': selected,
        'fit_scope': 'all_historical_valid_targets_for_demo', 'source_sha256': sha256(source)},
        root/'models/demo_radiation_model.joblib')
    selected_test = test_metrics[test_metrics.model.eq(selected)]
    metadata = {'selected_model': selected,
        'selection_rule': 'Lowest 0.7 * validation low-sun MAE + 0.3 * validation daytime MAE; baseline eligible.',
        'low_sun_definition': '-6 <= geometric solar elevation <= 15 degrees',
        'random_seed': 42, 'train_rows': len(train), 'validation_rows': len(val), 'test_rows': len(test),
        'source_sha256': sha256(source), 'feature_names': features,
        'evaluation_fit_scope': 'March-August 2024 only',
        'demo_fit_scope': 'All valid historical targets; test metrics do not evaluate this refit.',
        'prediction_mode': 'historical_seasonal_profile_no_live_weather',
        'test_status': 'Reused historical test benchmark after prototype iteration; not a new unseen field test.',
        'parameters': candidates[selected].get_params(),
        'selected_test_metrics': json.loads(selected_test.to_json(orient='records')),
        'limitations': ['No independent 2026 weather or lux validation.',
            'One station and less than a complete year of valid targets.',
            'September validation is sparse; no guaranteed switching-time accuracy.',
            'Model predicts radiation, not illuminance or lamp state.']}
    (out/'model_card.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    (out/'model_card.md').write_text('# Radiation model card\n\n' +
        f"Selected: **{selected}**.\n\n" + metadata['selection_rule'] + '\n\n' +
        'The test is held out during selection. The separate demo artifact is subsequently refitted on all historical targets. '
        'Test scores describe the train-only evaluation artifact, not the all-data refit.\n\n' +
        '\n'.join('- '+s for s in metadata['limitations']) + '\n', encoding='utf-8')
    return leaderboard, test_metrics, metadata


if __name__ == '__main__':
    board, test, card = train_models()
    print(board.to_string(index=False))
    print(test[test.model.eq(card['selected_model'])].to_string(index=False))
