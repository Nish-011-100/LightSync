"""Interactive campus what-if inputs; never overwrite collected observations."""
import datetime as dt
import json
import numpy as np
import pandas as pd
import streamlit as st
from src.lighting import propose_interval, interval_impact


def render_custom_plan(root, profile, selected, night, scenario, tariff, carbon):
    policy=json.loads((root/'config/lighting_policy.json').read_text())
    st.subheader('Build your lighting plan')
    st.write('Enter another IITG lighting zone, or test changes to an existing one. This uses the selected night and active campus radiation source; the location name is a label, not automatic geocoding.')
    st.caption(f'Night: {night} · Scenario: {scenario} · Times in IST; OFF is the next morning. Your original dataset stays unchanged.')
    inventory=pd.read_parquet(root/'data/processed/locations.parquet')
    starter=st.selectbox('Start from a location',['New campus zone']+inventory.location_name.tolist())
    existing=None if starter=='New campus zone' else inventory.loc[inventory.location_name.eq(starter)].iloc[0]
    defaults=None
    if existing is not None:
        schedules=pd.read_parquet(root/'data/scenarios/recommended_schedules.parquet')
        defaults=schedules.loc[schedules.location_id.eq(existing.location_id)&schedules.night_start_date.eq(night if night in set(schedules.night_start_date) else max(schedules.night_start_date))&schedules.scenario.eq(scenario)].iloc[0]
    fixture=st.selectbox('Fixture type',['Street light','Floodlight','Tube light'],index=0 if existing is None else {'streetlight':0,'floodlight':1,'tube_light':2}[existing.fixture_type])
    default_watts={'Street light':90.,'Floodlight':200.,'Tube light':20.}[fixture]
    st.caption('Choose a starting location and fixture first, then edit the form. Existing locations load assumed fixture counts and observed manual times. Fault counts remain editable scenarios.')
    with st.form('custom_plan_'+starter+'_'+fixture+'_'+str(night)):
        st.markdown('**01 · Location & daylight access**')
        name=st.text_input('Your location name',value='My campus lighting zone' if existing is None else starter,max_chars=120)
        a,b=st.columns(2)
        site=a.selectbox('Area type',['outdoor_road','corridor'],index=1 if (existing is not None and existing.site_type=='corridor') or (existing is None and fixture=='Tube light') else 0,format_func=lambda x:x.replace('_',' ').title())
        obstruction=b.selectbox('Main obstruction',list(policy['daylight_transfer']),index=list(policy['daylight_transfer']).index(existing.main_obstruction if existing is not None else ('Roof / covered' if fixture=='Tube light' else 'Open sky / none')))
        st.markdown('**02 · Fixtures & working count**')
        a,b,c=st.columns(3)
        count=a.number_input('Installed lights',min_value=1,max_value=100000,value=30 if existing is None else int(existing.installed_lights),step=1)
        broken=b.number_input('Non-working lights',min_value=0,max_value=100000,value=0 if existing is None else int(existing.installed_lights-existing.working_lights_min),step=1)
        watts=c.number_input('Power per light · W',min_value=0.1,max_value=5000.,value=default_watts,step=1.)
        a,b=st.columns(2)
        on_time=a.time_input('Manual ON time',value=dt.time(16,45) if defaults is None else defaults.manual_on_local.time())
        off_time=b.time_input('Manual OFF time · next morning',value=dt.time(5,30) if defaults is None else defaults.manual_off_local.time())
        st.caption('Set wattage from your fixture information. The starting wattage is a published product example for the chosen fixture type. Area type selects the prototype daylight thresholds.')
        submitted=st.form_submit_button('Generate my lighting plan',type='primary')
    context=(night,scenario,tariff,carbon,starter,fixture)
    if submitted:
        if not name.strip() or broken>count:
            st.error('Enter a location name and ensure non-working lights do not exceed installed lights.')
            st.session_state.pop('custom_plan_result',None)
            return
        if on_time.hour<12 or off_time.hour>=12:
            st.error('This overnight prototype requires ON from noon onward and OFF before noon the next day.')
            st.session_state.pop('custom_plan_result',None)
            return
        p=profile[['timestamp_local','solar_elevation_deg','radiation_prediction_w_m2']].copy()
        transfer=policy['daylight_transfer'][obstruction][scenario]
        p['lux_proxy']=np.where(p.solar_elevation_deg.gt(-6),p.radiation_prediction_w_m2,0)*transfer*policy['luminous_efficacy_lm_per_w'][scenario]
        threshold=policy['thresholds_lux'][site]
        on,off,review=propose_interval(p,selected.sunset_local,selected.sunrise_local,threshold['on'],threshold['off'],policy)
        day=pd.Timestamp(night)
        manual_on=pd.Timestamp.combine(day.date(),on_time).tz_localize('Asia/Kolkata')
        manual_off=pd.Timestamp.combine((day+pd.Timedelta(days=1)).date(),off_time).tz_localize('Asia/Kolkata')
        result=dict(radiation_source=selected.get("radiation_source","historical_random_forest"),fixture_type=fixture,location_name=name.strip(),night=night,scenario=scenario,site_type=site,obstruction=obstruction,
                    installed_lights=count,working_lights=count-broken,power_w=watts,manual_on=manual_on,manual_off=manual_off,
                    proposed_on=on,proposed_off=off,review=review,
                    **interval_impact(manual_on,manual_off,on,off,watts,count-broken))
        st.session_state.custom_plan_result=(context,result)
    saved=st.session_state.get('custom_plan_result')
    if not saved or saved[0]!=context:
        return
    r=saved[1]
    st.subheader(r['location_name'])
    a,b,c=st.columns(3)
    a.metric('Your proposed ON',r['proposed_on'].strftime('%H:%M'))
    b.metric('Your proposed OFF',r['proposed_off'].strftime('%H:%M'))
    c.metric('Your net saving',f"{r['net_savings_kwh']:+.2f} kWh")
    st.write(f"{r['working_lights']} working lights · {r['power_w']:g} W each. Manual: {r['manual_kwh']:.2f} kWh → proposed: {r['recommended_kwh']:.2f} kWh.")
    st.write(f"Excess ON energy removed: {r['excess_kwh']:.2f} kWh. Added lighting energy: {r['additional_kwh']:.2f} kWh ({r['additional_on_hours']*60:.0f} minutes).")
    if r['review']:st.warning('Daylight never reaches the OFF criterion before noon. The endpoint is an analysis boundary and requires inspection.')
    if r['net_savings_kwh']<0:st.info('This scenario requests more lighting. Additional energy remains visible instead of being counted as savings.')
    if r['working_lights']==0:st.warning('All fixtures are marked non-working. Timing changes cannot restore illumination; repair is needed.')
    if tariff is not None:
        st.write(f"Using your sidebar factors: INR {r['net_savings_kwh']*tariff:+.2f} and {r['net_savings_kwh']*carbon:+.2f} kg CO₂ net avoided per night.")
    st.caption('Conditional scenario using the active radiation source shown above, not measured lux. One-minute timing interpolates 15-minute ML predictions or hourly weather forecasts. Validate locally before operation.')
    st.download_button('Download my plan',pd.DataFrame([r]).to_csv(index=False),'lightsync_custom_plan.csv','text/csv')
