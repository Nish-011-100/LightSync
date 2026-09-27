"""On-demand historical-pattern predictions for a user-selected campus night."""
import json
import joblib
import numpy as np
import pandas as pd
from astral import Observer
from astral.sun import sunrise, sunset
from scipy.interpolate import PchipInterpolator
from src.modeling import make_features, predict_nonnegative
from src.lighting import propose_interval, interval_impact


def predict_date(root, day, locations, schedules, impacts, weather=None):
    cfg=json.loads((root/'config/project_config.json').read_text())
    policy=json.loads((root/'config/lighting_policy.json').read_text())
    bundle=joblib.load(root/'models/demo_radiation_model.joblib')
    start=pd.Timestamp(str(day)+' 12:00').tz_localize(cfg['timezone'])
    coarse=pd.date_range(start,start+pd.Timedelta(days=1),freq='15min')
    features=make_features(coarse,cfg)
    radiation=predict_nonnegative(bundle['model'],features[bundle['features']])
    times=pd.date_range(start,start+pd.Timedelta(days=1),freq='1min',inclusive='left')
    dense=make_features(times,cfg)
    base=pd.DataFrame({'timestamp_local':times,'solar_elevation_deg':dense.solar_elevation_deg,
        'radiation_prediction_w_m2':np.maximum(0,PchipInterpolator((coarse-start).total_seconds()/60,radiation)((times-start).total_seconds()/60))})
    geo=cfg['campus_proxy'];observer=Observer(geo['latitude'],geo['longitude'],geo['elevation_m'])
    setting=pd.Timestamp(sunset(observer,date=start.date(),tzinfo=cfg['timezone']))
    rising=pd.Timestamp(sunrise(observer,date=(start+pd.Timedelta(days=1)).date(),tzinfo=cfg['timezone']))
    source='historical_random_forest'
    if weather and weather.get('status')=='ok':
        forecast=weather['hourly']
        base['historical_ml_radiation_w_m2']=base.radiation_prediction_w_m2
        base['radiation_prediction_w_m2']=np.maximum(0,PchipInterpolator((forecast.time-start).dt.total_seconds()/60,forecast.shortwave_radiation_instant)((times-start).total_seconds()/60))
        setting=weather['sunset'];rising=weather['sunrise'];source='open_meteo_hourly_forecast'
    baseline_day=max(schedules.night_start_date)
    template=schedules[schedules.night_start_date.eq(baseline_day)]
    out_s=[];out_p=[];out_e=[]
    for row in template.to_dict('records'):
        site=locations.loc[locations.location_id.eq(row['location_id'])].iloc[0]
        case=row['scenario'];p=base.copy()
        p['lux_proxy']=np.where(p.solar_elevation_deg.gt(-6),p.radiation_prediction_w_m2,0)*row['daylight_transfer']*row['luminous_efficacy_lm_per_w']
        on,off,unresolved=propose_interval(p,setting,rising,row['on_threshold_lux'],row['off_threshold_lux'],policy)
        shift=start.normalize()-pd.Timestamp(baseline_day).tz_localize(cfg['timezone'])
        manual_on=row['manual_on_local']+shift;manual_off=row['manual_off_local']+shift
        ident=site.location_id+'_'+str(day).replace('-','')
        row.update(observation_id=ident,night_start_date=str(day),manual_on_local=manual_on,manual_off_local=manual_off,
            recommended_on_local=on,recommended_off_local=off,sunset_local=setting,sunrise_local=rising,
            off_not_reached_within_window=unresolved,basis='selected_date_model_prediction_with_reused_manual_baseline',baseline_source_date=baseline_day,radiation_source=source,input_cadence_minutes=60 if source.startswith('open_meteo') else 15,forecast_retrieved_at=weather.get('retrieved_at') if weather else None)
        out_s.append(row)
        p['observation_id']=ident;p['location_id']=site.location_id;p['scenario']=case
        p['manual_on_reconstructed']=(times>=manual_on)&(times<manual_off)
        p['recommended_on']=(times>=on)&(times<off)
        p['on_threshold_lux']=row['on_threshold_lux'];p['off_threshold_lux']=row['off_threshold_lux'];out_p.append(p)
        for bound in ['min','max']:
            count=int(site['working_lights_'+bound])
            energy=interval_impact(manual_on,manual_off,on,off,site.rated_power_w,count)
            out_e.append(dict(observation_id=ident,location_id=site.location_id,night_start_date=str(day),scenario=case,
                working_count_case=bound,working_lights=count,rated_power_w=site.rated_power_w,**energy))
    return pd.DataFrame(out_s),pd.concat(out_p,ignore_index=True),pd.DataFrame(out_e)
