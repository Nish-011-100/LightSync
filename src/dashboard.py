"""Campus dashboard, executed afresh by the Streamlit entry point."""
from pathlib import Path
import html
import json
import altair as alt
import pandas as pd
import streamlit as st
import runpy
_map_module=runpy.run_module("src.campus_map")
map_html,location_matches=_map_module["map_html"],_map_module["location_matches"]

ROOT=Path(__file__).resolve().parents[1]
st.set_page_config(page_title='LightSync · Campus lighting',page_icon='💡',layout='wide')
st.markdown('''<style>
.stApp{background:#062b22;color:#f2f7ef}.block-container{padding-top:3.5rem;padding-bottom:3rem;max-width:1550px}
h1,h2,h3{letter-spacing:-.035em;color:#f5fff0}h1{font-size:2.8rem!important;line-height:1.13!important}h3{font-size:1.3rem!important}
header[data-testid="stHeader"]{background:#062b22e8}[data-testid="stSidebar"]{background:#032219}
[data-testid="stSidebar"] h1,[data-testid="stSidebar"] h2,[data-testid="stSidebar"] h3,[data-testid="stSidebar"] p,[data-testid="stSidebar"] label{color:#e4eee3}
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] p{color:#a5b9a7;font-size:.78rem}[data-testid="stSidebar"] hr{border-color:#416051}
[data-testid="stMetric"]{background:#0a3429;border:1px solid #326849;border-radius:14px;padding:18px 20px;min-height:115px}
[data-testid="stMetricLabel"] p{color:#bfd0bd;font-size:.8rem!important}[data-testid="stMetricValue"]{font-size:1.9rem!important;color:#b7f783;letter-spacing:-.04em}
[data-baseweb="tab-list"]{gap:24px;border-bottom:1px solid #326849;margin-top:8px;margin-bottom:12px}[data-baseweb="tab"]{background:transparent!important;font-weight:600;height:48px}
[aria-selected="true"][data-baseweb="tab"]{color:#b7f783!important}.eyebrow{font-size:11px;letter-spacing:.18em;color:#b7f783;font-weight:700;margin:7px 0 10px}
.hero-sub{color:#c5d9c5;font-size:15px;line-height:1.6;margin:12px 0 20px;max-width:660px}.brand{font-size:28px;font-weight:750;color:#eaf7df;letter-spacing:-1px;margin-bottom:5px}.brand b{color:#bef181}.brand-sub{color:#a7bda8;font-size:11px;letter-spacing:2px;margin-bottom:32px}
.panel{background:#0a3429;border:1px solid #326849;border-radius:16px;padding:20px 23px;margin-bottom:12px}.panel h4{margin:0 0 13px;color:#c2ff95;font-size:15px}.panel p{margin:7px 0;color:#c5d9c5;font-size:13px;line-height:1.7}
.badge{display:inline-block;background:#194a32;color:#c2ff95;border-radius:20px;padding:5px 10px;font-size:11px;font-weight:650;margin-right:6px}.badge.amber{background:#433e20;color:#f4d487}
.times{display:flex;justify-content:space-between;gap:22px;margin:19px 0}.times small{color:#c5d9c5;font-size:10px;letter-spacing:1.4px}.times strong{display:block;font-size:35px;font-weight:600;letter-spacing:-2px;color:#c2ff95}.times span{font-size:12px;color:#b3c8b3}
.recommend{border-left:3px solid #95b975;padding:9px 0 9px 14px;font-size:13px;color:#e3efdc;line-height:1.7}.mini{font-size:11px;color:#b3c8b3;line-height:1.7}.section-title{font-size:19px;font-weight:650;letter-spacing:-.5px;color:#f5fff0;margin:18px 0 4px}.section-sub{font-size:12px;color:#b3c8b3;margin-bottom:17px}
.metric-strip{display:flex;gap:15px;border-top:1px solid #326849;padding-top:13px;margin-top:17px}.metric-strip b{color:#c2ff95;font-size:17px}.metric-strip span{display:block;font-size:10px;color:#b3c8b3}.kicker{color:#b7f783;font-size:11px;letter-spacing:1.4px}.footnote{border-top:1px solid #326849;margin-top:28px;padding-top:15px;color:#b3c8b3;font-size:11px}
@media(max-width:800px){h1{font-size:2.1rem!important}.block-container{padding:3.5rem 1rem 1rem}.times strong{font-size:28px}[data-testid="stMetric"]{padding:12px}}
[data-testid="stBaseButton-primary"],[data-testid="stBaseButton-primaryFormSubmit"]{color:#062b22!important;font-weight:700!important}[data-testid="stBaseButton-primary"] p,[data-testid="stBaseButton-primaryFormSubmit"] p{color:#062b22!important}
</style>''',unsafe_allow_html=True)


@st.cache_data
def read_data(signature):
    return (pd.read_parquet(ROOT/'data/processed/locations.parquet'),
            pd.read_parquet(ROOT/'data/scenarios/recommended_schedules.parquet'),
            pd.read_parquet(ROOT/'data/scenarios/lighting_profiles.parquet'),
            pd.read_parquet(ROOT/'data/scenarios/energy_impact.parquet'),
            pd.read_csv(ROOT/'reports/modeling/validation_leaderboard.csv'),
            pd.read_csv(ROOT/'reports/modeling/test_metrics.csv'),
            json.loads((ROOT/'reports/modeling/model_card.json').read_text()))


if not (ROOT/'data/scenarios/energy_impact.parquet').exists():
    st.info('Run the model and lighting notebooks to populate the campus dashboard.')
    st.stop()
signature=tuple((ROOT/p).stat().st_mtime_ns for p in ['data/scenarios/energy_impact.parquet','data/scenarios/recommended_schedules.parquet','data/scenarios/lighting_profiles.parquet','models/demo_radiation_model.joblib','data/processed/locations.parquet'])
locations,schedules,profiles,impacts,leaderboard,test_metrics,card=read_data(signature)
names=dict(zip(locations.location_name,locations.location_id))
with st.sidebar:
    st.markdown('<div class="brand">◒ Light<b>Sync</b></div><div class="brand-sub">CAMPUS INTELLIGENCE</div>',unsafe_allow_html=True)
    name=st.selectbox('Location',list(names))
    night=st.date_input('Night starting',value=pd.Timestamp(max(schedules.night_start_date)).date(),min_value=pd.Timestamp('2024-01-01').date(),max_value=pd.Timestamp('2100-12-30').date()).isoformat()
    scenario=st.selectbox('Daylight scenario',['central','lower_daylight','higher_daylight'],format_func=lambda s:{'central':'Balanced daylight','lower_daylight':'Less daylight reaches the area','higher_daylight':'More daylight reaches the area'}[s])
    count_case=st.radio('Working-light count',['min','max'],format_func=lambda s:'Lower estimate' if s=='min' else 'Upper estimate',horizontal=True)
    st.divider()
    use_rates=st.checkbox('Include cost & carbon factors')
    tariff=carbon=None
    if use_rates:
        tariff=st.number_input('Electricity tariff · INR/kWh',min_value=0.,value=8.,step=.1)
        carbon=st.number_input('Grid emissions · kg CO₂/kWh',min_value=0.,value=.7,step=.01)
        st.caption('Starting values are illustrative. Replace with documented local factors for your pitch.')
    use_weather=st.checkbox('Use weather forecast when available',value=True)
    st.caption('Open-Meteo: up to 16 days including the next morning. Other dates use historical ML.')
    st.markdown('<br>',unsafe_allow_html=True)
    st.caption('IIT GUWAHATI · ASSAM')
    st.caption('10 locations · 2 observed nights. Optional weather forecast with historical ML fallback.')
    st.link_button('Official IITG campus map ↗','https://www.iitg.ac.in/campusmap/')

weather=None
if use_weather:
    @st.cache_data(ttl=1800,show_spinner='Checking campus weather forecast…')
    def campus_forecast(day):
        from src.weather import fetch_forecast
        return fetch_forecast(day,json.loads((ROOT/'config/project_config.json').read_text()))
    weather=campus_forecast(night)
    if weather['status']=='ok':
        st.success('Weather-aware mode: Open-Meteo forecast radiation drives the schedule; historical ML remains the offline fallback. Sunrise/sunset also come from the API.')
        with st.expander('Forecast details and source'):
            st.caption('Retrieved '+weather['retrieved_at']+' · Hourly forecasts, not measurements. Cloud cover is already reflected in forecast radiation; no second cloud multiplier is applied.')
            st.dataframe(weather['hourly'],hide_index=True)
            st.link_button('Weather source · Open-Meteo','https://open-meteo.com/')
    else:st.caption(weather['message']+' Sunrise/sunset are calculated locally with Astral.')
is_predicted_date=night not in set(schedules.night_start_date)
if is_predicted_date or (weather and weather["status"]=="ok"):
    @st.cache_data(show_spinner='Predicting daylight and schedules for your date…')
    def selected_date_prediction(day, data_signature, forecast):
        from src.date_prediction import predict_date
        return predict_date(ROOT,day,locations,schedules,impacts,weather=forecast)
    schedules,profiles,impacts=selected_date_prediction(night,signature,weather)
    st.info('Selected-date ML prediction: sunrise/sunset and solar features are recalculated. Manual timings reuse the latest observed schedule as a comparison baseline; they are not observations for this date. The source banner identifies forecast radiation versus historical ML.')
location_id=names[name]
night_schedules=schedules[(schedules.night_start_date==night)&(schedules.scenario==scenario)]
night_impacts=impacts[(impacts.night_start_date==night)&(impacts.scenario==scenario)&(impacts.working_count_case==count_case)]
summary=night_schedules.merge(night_impacts,on=['observation_id','location_id','night_start_date','scenario'],validate='one_to_one')
summary=summary.merge(locations[['location_id','fixture_type','main_obstruction','installed_lights']],on='location_id').sort_values('location_id')
selected=summary[summary.location_id==location_id].iloc[0]
profile=profiles[(profiles.observation_id==selected.observation_id)&(profiles.scenario==scenario)].copy()
all_cases=schedules[schedules.night_start_date==night].groupby('location_id').agg(on_early=('recommended_on_local','min'),on_late=('recommended_on_local','max'),off_early=('recommended_off_local','min'),off_late=('recommended_off_local','max'))


def reason(row):
    if row.off_not_reached_within_window:
        return 'Daylight never reaches the OFF requirement in this window. Inspect the location before switching off.'
    on_shift=round((row.recommended_on_local-row.manual_on_local).total_seconds()/60)
    off_shift=round((row.recommended_off_local-row.manual_off_local).total_seconds()/60)
    parts=[f"Switch ON {abs(on_shift)} min {'later' if on_shift>0 else 'earlier'}" if on_shift else 'Keep the observed ON time',
           f"OFF {abs(off_shift)} min {'later' if off_shift>0 else 'earlier'}" if off_shift else 'keep the observed OFF time']
    if row.fixture_type=='tube_light':
        rationale='Covered-area daylight is the limiting factor.'
    elif abs((row.recommended_on_local-row.sunset_local).total_seconds())<=60:
        rationale='Sunset limits the evening time; shade affects morning daylight.'
    else:
        rationale='Local daylight reaches the selected threshold before the sunset limit.'
    return '; '.join(parts)+'. '+rationale


summary['recommendation']=summary.apply(reason,axis=1)
manual=summary.manual_kwh.sum();proposed=summary.recommended_kwh.sum();net=summary.net_savings_kwh.sum()
added=summary.additional_kwh.sum();excess=summary.excess_kwh.sum()
st.markdown('<div class="eyebrow">LATENT48 / IIT GUWAHATI / LIGHTING INTELLIGENCE</div>',unsafe_allow_html=True)
st.markdown('<h1>Predict the right time.<br><span style="color:#b7f783">Illuminate only when needed.</span></h1>',unsafe_allow_html=True)
st.markdown('<div class="hero-sub">A daylight-aware plan for every road and corridor. Compare observed switching with the shortest lighting interval that meets the modelled daylight constraints.</div>',unsafe_allow_html=True)
st.markdown(f'<span class="badge">{pd.Timestamp(night):%d %b %Y} · overnight</span><span class="badge">1-minute decisions</span><span class="badge amber">Conditional daylight estimate</span>',unsafe_allow_html=True)
st.caption('Minute-level scheduling is interpolated from 15-minute ML inputs or hourly API forecasts; it is not minute-level measured accuracy. Local lux settings need field validation.')
c=st.columns(4)
c[0].metric('Campus · net energy saving',f'{net:+.1f} kWh',f'{100*net/manual:.2f}% of manual consumption')
c[1].metric('Unnecessary ON energy removed',f'{excess:.1f} kWh')
c[2].metric('Extra lighting energy requested',f'{added:.1f} kWh')
c[3].metric('Working lights · assumed-count case',f'{summary.working_lights.sum():,}',f'{locations.installed_lights.sum():,} installed',delta_color='off')
st.caption('Installed light counts are user-assumed. Energy, cost and carbon estimates depend on these counts; manual switching times were observed.')
tabs=st.tabs(['Campus overview','Location insight','Try your location','Observation log','Model & evidence'])

with tabs[0]:
    left,right=st.columns([1.65,1],gap='large')
    with left:
        st.markdown('<div class="section-title">Your campus, in context</div><div class="section-sub">Real roads and building footprints · zoom, drag, or tap a landmark</div>',unsafe_allow_html=True)
        if (ROOT/'data/map/campus_osm.json').exists():
            st.iframe(map_html(summary,location_id),height=451)
            st.caption('Pins: 6 Umiam Road landmark · 8/10 Disang Road & Hostel landmark · 9 Lohit Hostel. Other road names are unresolved; no lamp coordinates are invented.')
        else:
            st.link_button('View IIT Guwahati map','https://www.iitg.ac.in/campusmap/')
    with right:
        st.markdown('<div class="section-title">Selected location</div><div class="section-sub">Change the location in the sidebar</div>',unsafe_allow_html=True)
        delta='net saving' if selected.net_savings_kwh>=0 else 'additional energy'
        spread=all_cases.loc[location_id]
        st.markdown(f'''<div class="panel"><span class="kicker">{location_id} · {html.escape(selected.fixture_type.replace('_',' ').upper())}</span><h3>{html.escape(name)}</h3><span class="badge">{html.escape(selected.main_obstruction)}</span>
<div class="times"><div><small>PROPOSED ON</small><strong>{selected.recommended_on_local:%H:%M}</strong><span>Manual baseline {selected.manual_on_local:%H:%M}</span></div><div><small>PROPOSED OFF</small><strong>{selected.recommended_off_local:%H:%M}</strong><span>Manual baseline {selected.manual_off_local:%H:%M}</span></div></div>
<div class="recommend">{html.escape(reason(selected))}</div><div class="metric-strip"><div><b>{abs(selected.net_savings_kwh):.2f} kWh</b><span>{delta}</span></div><div><b>{int(selected.working_lights)}</b><span>working fixtures</span></div><div><b>{int(selected.rated_power_w)} W</b><span>per fixture</span></div></div>
<p>Across daylight scenarios: ON {spread.on_early:%H:%M}–{spread.on_late:%H:%M}; OFF {spread.off_early:%H:%M}–{spread.off_late:%H:%M}.</p><div class="mini">Sensitivity range, not a confidence interval. Times in IST; OFF is the next morning.</div></div>''',unsafe_allow_html=True)
        st.markdown(f'<div class="panel"><h4>☀ Sun & daylight</h4><p>Sunset <b>{selected.sunset_local:%H:%M}</b> · next sunrise <b>{selected.sunrise_local:%H:%M}</b><br>Short stability checks replace fixed 15-minute waiting blocks.</p></div>',unsafe_allow_html=True)
    st.markdown('<div class="section-title">A plan for all 10 locations</div><div class="section-sub">Every location has its own schedule comparison and energy answer. Values below cover the selected night only.</div>',unsafe_allow_html=True)
    display=pd.DataFrame({'Location':summary.location_name,'Obstruction':summary.main_obstruction,
        'Manual ON':summary.manual_on_local.dt.strftime('%H:%M'),'Proposed ON':summary.recommended_on_local.dt.strftime('%H:%M'),
        'Manual OFF':summary.manual_off_local.dt.strftime('%H:%M'),'Proposed OFF':summary.recommended_off_local.dt.strftime('%H:%M'),
        'Net saved (kWh)':summary.net_savings_kwh.round(2),'Extra light (min)':(summary.additional_on_hours*60).round().astype(int)})
    st.dataframe(display,hide_index=True,width='stretch',height=390)
    st.download_button('↓ Download all location recommendations',summary.to_csv(index=False),'lightsync_all_locations.csv','text/csv')
    with st.expander('Why these times? A plain-language answer for each location'):
        for row in summary.itertuples():st.markdown(f'**{row.location_name}** — {row.recommendation}')
    if use_rates:
        a,b=st.columns(2)
        a.metric('Campus cost saved · entered tariff',f'INR {net*tariff:+.2f}')
        b.metric('Campus avoided CO₂ · entered factor',f'{net*carbon:+.2f} kg')
    else:
        st.caption('Cost and carbon: enter documented factors in the sidebar, or explore the clearly labelled illustrative values.')

with tabs[1]:
    st.subheader(name)
    st.write(reason(selected))
    a,b,c,d=st.columns(4)
    a.metric('Manual consumption',f'{selected.manual_kwh:.2f} kWh')
    b.metric('Proposed consumption',f'{selected.recommended_kwh:.2f} kWh')
    c.metric('Net energy saving',f'{selected.net_savings_kwh:+.2f} kWh')
    d.metric('Extra light requested',f'{selected.additional_on_hours*60:.0f} min')
    st.markdown('<div class="section-title">See the daylight transition</div>',unsafe_allow_html=True)
    period=st.radio('Daylight view',['Evening','Morning'],horizontal=True)
    mask=profile.timestamp_local.dt.hour.between(15,19) if period=='Evening' else profile.timestamp_local.dt.hour.between(4,8)
    q=profile.loc[mask].copy();q['Time (IST)']=q.timestamp_local.dt.tz_localize(None);q['Modelled daylight']=q.lux_proxy
    threshold=selected.on_threshold_lux if period=='Evening' else selected.off_threshold_lux
    line=alt.Chart(q).mark_line(color='#b7f783',strokeWidth=3).encode(x=alt.X('Time (IST):T',axis=alt.Axis(format='%H:%M',title='Local time (IST)')),
        y=alt.Y('Modelled daylight:Q',title='Daylight proxy (lux)'),tooltip=[alt.Tooltip('Time (IST):T',format='%H:%M'),alt.Tooltip('Modelled daylight:Q',format='.1f')])
    rule=alt.Chart(pd.DataFrame({'threshold':[threshold]})).mark_rule(color='#c09145',strokeDash=[5,4]).encode(y='threshold:Q')
    switch=selected.recommended_on_local if period=='Evening' else selected.recommended_off_local
    vertical=alt.Chart(pd.DataFrame({'switch':[switch.tz_localize(None)]})).mark_rule(color='#67dca3',strokeDash=[2,3]).encode(x='switch:T')
    st.altair_chart((line+rule+vertical).properties(height=275).configure_view(stroke=None),width='stretch')
    st.caption(f'Dashed amber: {threshold:g} lux decision setting. Dotted green: proposed switch. The lux curve is uncalibrated; extra samples come from interpolation.')
    timeline=pd.DataFrame({'Schedule':['Manual baseline','Proposed'],'Start':[selected.manual_on_local.tz_localize(None),selected.recommended_on_local.tz_localize(None)],'End':[selected.manual_off_local.tz_localize(None),selected.recommended_off_local.tz_localize(None)]})
    st.altair_chart(alt.Chart(timeline).mark_bar(cornerRadius=6,size=24).encode(x=alt.X('Start:T',title='ON interval · IST',axis=alt.Axis(format='%H:%M')),x2='End:T',y=alt.Y('Schedule:N',title=None),color=alt.Color('Schedule:N',scale=alt.Scale(domain=['Manual baseline','Proposed'],range=['#b3bbac','#a9ef7b']),legend=None),tooltip=['Schedule',alt.Tooltip('Start:T',format='%d %b %H:%M'),alt.Tooltip('End:T',format='%d %b %H:%M')]).properties(height=120).configure_view(stroke=None),width='stretch')
    st.markdown('<div class="section-title">Energy without hidden trade-offs</div>',unsafe_allow_html=True)
    st.dataframe(pd.DataFrame({'Component':['Excess ON energy removed','Added energy for the requested light','Net energy saving'],'kWh':[selected.excess_kwh,selected.additional_kwh,selected.net_savings_kwh]}).round(3),hide_index=True,width='stretch')
    if selected.net_savings_kwh<0:st.info('This location needs more lighting in this scenario. Its negative saving remains visible in the campus total.')
    if selected.off_not_reached_within_window:st.warning('No OFF criterion was reached before noon. The displayed endpoint is the analysis boundary, not a verified OFF instruction.')
    with st.expander('Compare all daylight scenarios for this location'):
        st.dataframe(schedules[(schedules.location_id==location_id)&(schedules.night_start_date==night)][['scenario','recommended_on_local','recommended_off_local','daylight_transfer']],hide_index=True)

with tabs[2]:
    render_custom_plan=runpy.run_module("src.custom_plan")["render_custom_plan"]
    render_custom_plan(ROOT,profile,selected,night,scenario,tariff,carbon)

with tabs[3]:
    render_log=runpy.run_module('src.observation_log')['render']
    render_log(ROOT,locations)

with tabs[4]:
    st.subheader('Simple models. Visible evidence.')
    if (ROOT/'reports/modeling/rolling_leaderboard.csv').exists():
        st.write('Rolling validation: train on earlier months, validate on June, July, August and September separately. Equal dawn/dusk emphasis; previously inspected development data, not a fresh test.')
        st.dataframe(pd.read_csv(ROOT/'reports/modeling/rolling_leaderboard.csv').round(3),hide_index=True) 
    st.write(f"**{card['selected_model']}** remains the validation winner. The extra dawn/dusk curve candidate is shown even though it did not improve the selection score.")
    st.dataframe(leaderboard.round(3),hide_index=True,width='stretch')
    st.write('Selection uses September validation; the historical test benchmark is reported separately. It has already been inspected during development, so this is not a new unseen field test.')
    st.dataframe(test_metrics[test_metrics.model==card['selected_model']].round(3),hide_index=True,width='stretch')
    st.caption('Radiation errors are W/m². Dusk R² is negative: operational switching still needs current weather and local validation. The demo model is refitted on all historical targets. Optional forecast mode uses API radiation instead of the local ML radiation profile.')
    with st.expander('How the energy-minimising interval works'):
        st.write('Within one overnight interval, choose the latest ON that covers every modelled evening deficit, and the earliest OFF after which the remaining morning profile stays above the OFF threshold. Add two-minute transition margins and sunset/sunrise bounds. Interpolate coarse predictions with a shape-preserving curve; evaluate on a one-minute decision grid.')
        st.write('This minimises unnecessary run time for the specified daylight proxy and constraints. It is not a guarantee of globally optimal or physically safe lighting. Shade categories cannot establish true illuminance; lamp output, glare, faults and occupancy require separate assessment.')
        st.json(json.loads((ROOT/'config/lighting_policy.json').read_text()))
    with st.expander('Map matches and data provenance'):
        st.dataframe(location_matches(),hide_index=True,width='stretch')
        st.write('Matched buildings and hostel-based road proxies are for map context only. Unresolved roads stay unpinned. Astronomical calculations still use the documented campus reference point.')
        st.dataframe(locations[['location_name','rated_power_w','power_basis','power_source_url']],hide_index=True)
st.markdown('<div class="footnote">LIGHTSYNC · IIT GUWAHATI PROTOTYPE &nbsp; / &nbsp; 10 locations · 20 observed intervals · historical solar data 2024–2025 · schedules are proposals for field review</div>',unsafe_allow_html=True)
