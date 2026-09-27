"""Open-Meteo forecast retrieval; failures never become invented weather."""
import json
from urllib.parse import urlencode
from urllib.request import urlopen
import numpy as np
import pandas as pd


def fetch_forecast(day, cfg):
    today=pd.Timestamp.now(tz=cfg['timezone']).normalize()
    start=pd.Timestamp(day).tz_localize(cfg['timezone'])
    if not 0 <= (start-today).days <= 14:
        return {'status':'outside_window','message':'Full overnight forecast requires a start within today through the next 14 days.'}
    geo=cfg['campus_proxy']
    params=dict(latitude=geo['latitude'],longitude=geo['longitude'],timezone=cfg['timezone'],forecast_days=16,
        hourly='shortwave_radiation_instant,cloud_cover,temperature_2m,precipitation_probability',daily='sunrise,sunset')
    url='https://api.open-meteo.com/v1/forecast?'+urlencode(params)
    try:
        with urlopen(url,timeout=12) as response: data=json.load(response)
        hourly=pd.DataFrame(data['hourly']);hourly['time']=pd.to_datetime(hourly.time).dt.tz_localize(cfg['timezone'])
        window=hourly.loc[hourly.time.between(start+pd.Timedelta(hours=12),start+pd.Timedelta(days=1,hours=12))].copy()
        if len(window)!=25 or window.shortwave_radiation_instant.isna().any() or not np.isfinite(window.shortwave_radiation_instant).all():
            raise ValueError('Incomplete overnight radiation forecast')
        daily=pd.DataFrame(data['daily']).set_index('time')
        setting=pd.Timestamp(daily.loc[day,'sunset']).tz_localize(cfg['timezone'])
        rising=pd.Timestamp(daily.loc[(start+pd.Timedelta(days=1)).strftime('%Y-%m-%d'),'sunrise']).tz_localize(cfg['timezone'])
        return dict(status='ok',hourly=window,sunset=setting,sunrise=rising,retrieved_at=pd.Timestamp.now(tz='UTC').isoformat(),source_url=url)
    except Exception as exc:
        return dict(status='unavailable',message='Forecast unavailable or incomplete; historical ML fallback is active.',error_type=type(exc).__name__)
