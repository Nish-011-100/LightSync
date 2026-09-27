"""Offline interactive campus map from attributed OpenStreetMap geometry."""
import html
import json
from pathlib import Path
import numpy as np
import pandas as pd
from src.prepare_data import ROOT


def location_matches(root=ROOT):
    data=json.loads((Path(root)/'data/map/campus_osm.json').read_text())
    by_name={e['tags'].get('name'):e for e in data['elements'] if e.get('geometry')}
    loc=pd.read_parquet(Path(root)/'data/processed/locations.parquet')
    proxies={'LOC006':'Umiam Hostel','LOC008':'Disang Hostel','LOC009':'Lohit Hostel','LOC010':'Disang Hostel'}
    rows=[]
    for site in loc.itertuples():
        landmark=proxies.get(site.location_id)
        e=by_name.get(landmark)
        lat=lon=None
        kind='Road name not resolved'
        if e:
            geometry=e['geometry']
            lat=float(np.mean([v['lat'] for v in geometry]))
            lon=float(np.mean([v['lon'] for v in geometry]))
            kind='Named building footprint' if site.site_type=='corridor' else 'Hostel landmark proxy; road extent unverified'
        rows.append({'location_id':site.location_id,'location_name':site.location_name,'map_latitude':lat,
            'map_longitude':lon,'map_match':kind,'map_landmark':landmark,
            'source_url':f"https://www.openstreetmap.org/way/{e['id']}" if e else None,
            'fixture_gps_verified':False})
    return pd.DataFrame(rows)


def map_html(summary,selected_id,root=ROOT):
    root=Path(root)
    elements=json.loads((root/'data/map/campus_osm.json').read_text())['elements']
    matches=location_matches(root)
    # North-up equirectangular projection. No invented location jitter or lamp points.
    west,east,south,north=91.683,91.7075,26.180,26.1948
    w,h=900,600
    def xy(lon,lat):return ((lon-west)/(east-west)*w,(north-lat)/(north-south)*h)
    def path(e):
        coords=[xy(p['lon'],p['lat']) for p in e['geometry']]
        return 'M'+' L'.join(f'{x:.1f},{y:.1f}' for x,y in coords)
    shapes=[]
    for e in elements:
        if not e.get('geometry'):continue
        tags=e['tags']
        if tags.get('natural')=='water':
            shapes.append(f'<path d="{path(e)} Z" fill="#124e5a" stroke="#287381" stroke-width="1"/>')
        elif 'building' in tags:
            target=tags.get('name') in ['Lohit Hostel','Disang Hostel','Umiam Hostel']
            shapes.append(f'<path d="{path(e)} Z" fill="{"#5c7950" if target else "#304e36"}" stroke="#8c9864" stroke-width=".7"/>')
    roads=[e for e in elements if e.get('geometry') and 'highway' in e['tags']]
    for e in roads:
        small=e['tags']['highway'] in ['footway','path','steps','cycleway']
        shapes.append(f'<path d="{path(e)}" fill="none" stroke="#756e4b" stroke-width="{2 if small else 7}" stroke-linejoin="round"/>')
    for e in roads:
        small=e['tags']['highway'] in ['footway','path','steps','cycleway']
        shapes.append(f'<path d="{path(e)}" fill="none" stroke="#c2b387" stroke-width="{1 if small else 4}" stroke-linejoin="round"/>')
    for e in elements:
        name=e['tags'].get('name','')
        if name in ['Academic Complex','Administrative Block','IITG lake','Brahmaputra Hostel'] and e.get('geometry'):
            x,y=xy(np.mean([p['lon'] for p in e['geometry']]),np.mean([p['lat'] for p in e['geometry']]))
            shapes.append(f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="middle" font-size="12" fill="#a7c9b0" font-weight="600">{html.escape(name)}</text>')
    points=[]
    # Disang road and hostel deliberately share a landmark rather than false precise pins.
    for landmark,group in matches.dropna(subset=['map_latitude']).groupby('map_landmark'):
        first=group.iloc[0]
        x,y=xy(first.map_longitude,first.map_latitude)
        ids=group.location_id.tolist()
        active=selected_id in ids
        key=ids[0]
        r=summary.loc[summary.location_id.eq(key)].iloc[0]
        obstruction='Mixed obstructions' if len(ids)>1 else r.main_obstruction
        color={'Roof / covered':'#b18af5','Dense trees':'#ffab67','Sparse trees':'#8fd7ee','Open sky / none':'#b7f783'}.get(obstruction,'#c4c9bc')
        title='Disang Road + Hostel' if len(ids)>1 else r.location_name
        short={'Roof / covered':'Covered','Sparse trees':'Sparse trees','Dense trees':'Dense trees'}.get(obstruction,obstruction)
        short='Open road / covered hostel' if len(ids)>1 else short
        edge='#efffce' if active else color
        shapes.append(f'<g class="pin" tabindex="0" role="button" aria-label="{html.escape(landmark)}" data-key="{key}"><path d="M {x:.1f} {y:.1f} c -5 -10 -18 -21 -18 -33 a 18 18 0 1 1 36 0 c 0 12 -13 23 -18 33 Z" fill="{color}" stroke="{edge}" stroke-width="2"/><circle cx="{x:.1f}" cy="{y-33:.1f}" r="8" fill="#092f25"/><rect x="{x+23:.1f}" y="{y-57:.1f}" width="165" height="50" rx="7" fill="#062b22" stroke="{edge}"/><text x="{x+31:.1f}" y="{y-38:.1f}" font-size="12" fill="#f1f8e9" font-weight="700">{html.escape(title)}</text><text x="{x+31:.1f}" y="{y-20:.1f}" font-size="11" fill="{color}">{html.escape(short)}</text></g>')
        info=[]
        for ident in ids:
            r=summary.loc[summary.location_id.eq(ident)].iloc[0]
            info.append(f"<b>{html.escape(r.location_name)}</b><br>ON {r.recommended_on_local:%H:%M} · OFF {r.recommended_off_local:%H:%M}<br>{r.net_savings_kwh:+.2f} kWh net saving<br><small>{html.escape(group.loc[group.location_id.eq(ident),'map_match'].iloc[0])}</small>")
        points.append((key,'<hr>'.join(info)))
    popup_data=json.dumps(dict(points)).replace('</','<\\/')
    return '''<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><style>
*{box-sizing:border-box}body{margin:0;font-family:Inter,Arial,sans-serif;color:#e6f5e6}.map{height:445px;border:1px solid #72b85b;border-radius:18px;overflow:hidden;background:#092f25;position:relative}svg{width:100%;height:100%;touch-action:none;cursor:grab}.pin{cursor:pointer}.pin:hover circle{fill:#d09138}.top{position:absolute;top:16px;left:16px;background:#062b22ed;padding:10px 14px;border-radius:10px;font-size:12px;box-shadow:0 3px 12px #183c2410}.top b{display:block;font-size:15px;margin-bottom:4px}.controls{position:absolute;top:16px;right:16px;display:grid;gap:5px}button{border:1px solid #79ab64;background:#062b22;color:#b7f783;border-radius:7px;width:32px;height:32px;font-size:19px;cursor:pointer}.credit{position:absolute;bottom:0;right:0;background:#062b22ed;font-size:10px;padding:5px 8px}.credit a{color:#aed7b6}.legend{position:absolute;bottom:27px;left:12px;background:#062b22ed;border:1px solid #79ab64;border-radius:9px;padding:10px 13px;font-size:11px;line-height:1.8}.north{position:absolute;right:22px;top:139px;font-size:12px;text-align:center}.popup{display:none;position:absolute;bottom:24px;left:50%;transform:translateX(-50%);background:#062b22;border:1px solid #79ab64;box-shadow:0 8px 30px #163c3020;border-radius:12px;padding:14px 18px;font-size:13px;line-height:1.65;min-width:240px}.popup small{color:#b5cbb5;font-size:11px}.popup hr{border:0;border-top:1px solid #326849;margin:9px 0}.popup .close{float:right;cursor:pointer;margin-left:14px}
</style></head><body><div class="map"><svg id="map" viewBox="0 0 900 600" role="img" aria-label="IIT Guwahati campus roads and buildings"><rect width="900" height="600" fill="#092f25"/>'''+''.join(shapes)+'''</svg>
<div class="top"><b>IIT Guwahati</b>DAYLIGHT & OBSTRUCTION · tap a pin</div><div class="controls"><button id="plus" aria-label="Zoom in">+</button><button id="minus" aria-label="Zoom out">−</button><button id="reset" aria-label="Reset map">↺</button></div><div class="north">N<br>↑</div><div class="legend"><b>Location conditions</b><br><span style="color:#b7f783">●</span> Open sky &nbsp; <span style="color:#c4c9bc">●</span> Mixed<br><span style="color:#ffab67">●</span> Dense trees &nbsp; <span style="color:#b18af5">●</span> Covered<br><span style="color:#8fd7ee">●</span> Sparse trees</div><div class="popup" id="popup"></div><div class="credit">© <a href="https://www.openstreetmap.org/copyright" target="_blank">OpenStreetMap contributors</a> · landmark positions, not lamp GPS</div></div>
<script>const popups='''+popup_data+''';const svg=document.getElementById('map');let box=[0,0,900,600],drag=null;function draw(){svg.setAttribute('viewBox',box.join(' '))}function zoom(k){let nw=box[2]*k,nh=box[3]*k;if(nw<220||nw>1800)return;box=[box[0]+(box[2]-nw)/2,box[1]+(box[3]-nh)/2,nw,nh];draw()}document.getElementById('plus').onclick=()=>zoom(.8);document.getElementById('minus').onclick=()=>zoom(1.25);document.getElementById('reset').onclick=()=>{box=[0,0,900,600];draw()};svg.onpointerdown=e=>{if(e.target.closest('.pin'))return;drag=[e.clientX,e.clientY,...box];svg.setPointerCapture(e.pointerId)};svg.onpointermove=e=>{if(!drag)return;box[0]=drag[2]-(e.clientX-drag[0])*box[2]/svg.clientWidth;box[1]=drag[3]-(e.clientY-drag[1])*box[3]/svg.clientHeight;draw()};svg.onpointerup=()=>drag=null;function popup(pin){let p=document.getElementById('popup');p.innerHTML='<span class="close" onclick="this.parentElement.style.display=\'none\'">×</span>'+popups[pin.dataset.key];p.style.display='block'}document.querySelectorAll('.pin').forEach(pin=>{pin.onclick=()=>popup(pin);pin.onkeydown=e=>{if(e.key==='Enter')popup(pin)}});</script></body></html>'''


if __name__=='__main__':
    matches=location_matches()
    matches.to_csv(ROOT/'data/map/location_matches.csv',index=False)
    print(matches[['location_name','map_match']].to_string(index=False))
