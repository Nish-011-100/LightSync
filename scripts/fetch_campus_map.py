"""Fetch public OpenStreetMap geometry for campus context; no fixture GPS is inferred."""
from pathlib import Path
import json
import requests
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data/map'
OUT.mkdir(parents=True,exist_ok=True)
query='''[out:json][timeout:40];(
way["highway"](26.177,91.680,26.201,91.714);
way["building"](26.177,91.680,26.201,91.714);
way["natural"="water"](26.177,91.680,26.201,91.714);
node["name"](26.177,91.680,26.201,91.714);
);out tags geom;'''
response=requests.get('https://api.openstreetmap.org/api/0.6/map',params={'bbox':'91.680,26.177,91.714,26.201'},timeout=45,
                      headers={'User-Agent':'LightSync-campus-prototype/1.0'})
response.raise_for_status()
xml=ET.fromstring(response.content)
nodes={n.attrib['id']:{'lat':float(n.attrib['lat']),'lon':float(n.attrib['lon'])} for n in xml.findall('node')}
elements=[]
for node in xml.findall('node'):
    tags={t.attrib['k']:t.attrib['v'] for t in node.findall('tag')}
    if 'name' in tags:
        elements.append({'type':'node','id':int(node.attrib['id']),**nodes[node.attrib['id']],'tags':tags})
for way in xml.findall('way'):
    tags={t.attrib['k']:t.attrib['v'] for t in way.findall('tag')}
    if 'highway' in tags or 'building' in tags or tags.get('natural')=='water':
        elements.append({'type':'way','id':int(way.attrib['id']),'tags':tags,
                         'geometry':[nodes[n.attrib['ref']] for n in way.findall('nd') if n.attrib['ref'] in nodes]})
data={'elements':elements,'source':'OpenStreetMap map API','bounds':[91.680,26.177,91.714,26.201]}
(OUT/'campus_osm.json').write_text(json.dumps(data),encoding='utf-8')
(OUT/'SOURCE.md').write_text('''# Campus map source

Public OpenStreetMap geometry retrieved through the map API for IIT Guwahati and immediate surroundings.
Bounds: 26.177, 91.680, 26.201, 91.714. Retrieved 27 September 2026.

© OpenStreetMap contributors. Open Database License (ODbL): https://www.openstreetmap.org/copyright
API: https://api.openstreetmap.org/api/0.6/map
Official campus map reference: https://www.iitg.ac.in/campusmap/

Named-road/building matches are approximate location extents, not surveyed lamp coordinates. Ambiguous names stay unpinned.
''',encoding='utf-8')
print('OSM elements:',len(data['elements']))
for element in data['elements']:
    tags=element.get('tags',{})
    if tags.get('name'):
        print(element['type'],element['id'],tags['name'])
