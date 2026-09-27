"""Append-only local field observations, separate from modelling/scenario tables."""
import datetime as dt
import sqlite3
from contextlib import closing
import uuid
import pandas as pd
import streamlit as st

COLUMNS=['record_id','recorded_at_utc','observed_at_ist','location_id','observer_alias','light_state','check_interval_minutes','count_basis','installed_count','nonworking_count','lux','lux_method','notes']

def connect(root):
    directory=root/'data/field_logs';directory.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(directory/'observations.sqlite3',timeout=10)
    db.execute('CREATE TABLE IF NOT EXISTS observations (record_id TEXT PRIMARY KEY, recorded_at_utc TEXT, observed_at_ist TEXT, location_id TEXT, observer_alias TEXT, light_state TEXT, check_interval_minutes INTEGER, count_basis TEXT, installed_count INTEGER, nonworking_count INTEGER, lux REAL, lux_method TEXT, notes TEXT)')
    return db

def save(root,record):
    if pd.Timestamp(record['observed_at_ist'])>pd.Timestamp.now(tz='Asia/Kolkata'):
        raise ValueError('An observation cannot be in the future.')
    if record['nonworking_count'] is not None and record['installed_count'] is not None and record['nonworking_count']>record['installed_count']:
        raise ValueError('Non-working count cannot exceed installed count.')
    with closing(connect(root)) as db:
        db.execute('INSERT INTO observations VALUES ('+','.join('?' for _ in COLUMNS)+')',[record.get(c) for c in COLUMNS])
        db.commit()

def read(root):
    with closing(connect(root)) as db:return pd.read_sql_query('SELECT * FROM observations ORDER BY observed_at_ist DESC',db)

def render(root,locations):
    st.subheader('Field observation log')
    st.write('Record what you actually see. Entries are saved locally and remain separate from predictions and the original event dataset. Use an observer alias, not personal contact details.')
    st.info('Hosted demo: this log is shared by visitors on the same server. Use anonymous test entries only. Local storage may be reset during redeployment; export records you need to retain.')
    now=pd.Timestamp.now(tz='Asia/Kolkata')
    with st.form('field_observation',clear_on_submit=False):
        site=st.selectbox('Observed location',locations.location_id.tolist(),format_func=lambda k:locations.set_index('location_id').loc[k,'location_name'])
        a,b=st.columns(2);day=a.date_input('Observation date',value=now.date(),max_value=now.date());time=b.time_input('Observation time Â· IST',value=now.time().replace(second=0,microsecond=0),step=60)
        alias=st.text_input('Observer alias',max_chars=40)
        state=st.selectbox('Observed light state',['ON','OFF','Partly ON','Unable to determine'])
        interval=st.number_input('Minutes since previous check Â· 0 if unknown',min_value=0,value=0,step=1)
        basis=st.selectbox('Fixture count basis',['Not recorded','Physically counted','Estimated from length / spacing'])
        a,b=st.columns(2);count=a.number_input('Installed count Â· optional',min_value=0,value=0,step=1);broken=b.number_input('Non-working count Â· optional',min_value=0,value=0,step=1)
        method=st.selectbox('Illuminance measurement',['Not measured','Lux meter','Phone sensor (uncalibrated)'])
        lux=st.number_input('Measured lux Â· used only when a method is selected',min_value=0.,value=0.)
        notes=st.text_area('Observation notes',max_chars=1000,placeholder='Visibility, obstruction, missed check, or last OFF / first ON bracket. No identifiable people.')
        submit=st.form_submit_button('Save observation',type='primary')
    if submit:
        if not alias.strip():st.error('Enter an observer alias.')
        else:
            record=dict(record_id=str(uuid.uuid4()),recorded_at_utc=pd.Timestamp.now(tz='UTC').isoformat(),observed_at_ist=pd.Timestamp.combine(day,time).tz_localize('Asia/Kolkata').isoformat(),location_id=site,observer_alias=alias.strip(),light_state=state,check_interval_minutes=interval or None,count_basis=basis,installed_count=count if basis!='Not recorded' else None,nonworking_count=broken if basis!='Not recorded' else None,lux=lux if method!='Not measured' else None,lux_method=method,notes=notes)
            try:save(root,record);st.success('Observation saved locally.')
            except ValueError as exc:st.error(str(exc))
    data=read(root)
    st.caption(f'{len(data)} saved field checks. These are checks, not automatically verified switching intervals. Export reviewed records for sharing; local logs are Git-ignored.')
    st.dataframe(data,hide_index=True)
    # Escape spreadsheet formula prefixes in human-entered strings on CSV export.
    safe=data.copy()
    for col in ['observer_alias','notes']:
        safe[col]=safe[col].map(lambda v:"'"+v if isinstance(v,str) and v.startswith(('=','+','-','@')) else v)
    st.download_button('Export field observations',safe.to_csv(index=False),'field_observations.csv','text/csv')
