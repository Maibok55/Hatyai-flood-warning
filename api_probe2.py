"""Quick probe to see extra fields from ThaiWater API"""
import sys, os
os.environ['PYTHONIOENCODING'] = 'utf-8'
sys.stdout.reconfigure(encoding='utf-8')

import requests
import json
from constants import STATION_METADATA, API_CONFIG

api_url = API_CONFIG['thaiwater']['url']
station_ids = {info['id']: name for name, info in STATION_METADATA.items()}

response = requests.get(api_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
data = response.json()
entries = data.get('waterlevel_data', {}).get('data', [])

for entry in entries:
    st = entry.get('station', {})
    sid = st.get('id')
    if sid not in station_ids:
        continue
    
    name = station_ids[sid]
    print(f"\n=== {name} (ID:{sid}) ===")
    print(f"  waterlevel_msl          = {entry.get('waterlevel_msl')}")
    print(f"  waterlevel_m            = {entry.get('waterlevel_m')}")
    print(f"  waterlevel_msl_previous = {entry.get('waterlevel_msl_previous')}")
    print(f"  diff_wl_bank            = {entry.get('diff_wl_bank')}")
    print(f"  diff_wl_bank_text       = {entry.get('diff_wl_bank_text')}")
    print(f"  situation_level         = {entry.get('situation_level')}")
    print(f"  flow_rate               = {entry.get('flow_rate')}")
    print(f"  discharge               = {entry.get('discharge')}")
    print(f"  station_type            = {entry.get('station_type')}")
    
    # Station sub-fields
    print(f"  station.code            = {st.get('code')}")
    print(f"  station.old_code        = {st.get('old_code')}")
    print(f"  station.station_name    = {json.dumps(st.get('station_name'), ensure_ascii=False)}")
    print(f"  station.station_type    = {st.get('station_type')}")
    print(f"  station.left_bank       = {st.get('left_bank')}")
    print(f"  station.right_bank      = {st.get('right_bank')}")
    print(f"  station.ground_level    = {st.get('ground_level')}")
    print(f"  station.min_bank        = {st.get('min_bank')}")
    
    # Geocode
    geo = entry.get('geocode', {})
    if isinstance(geo, dict):
        print(f"  geocode.province        = {json.dumps(geo.get('province_name'), ensure_ascii=False)}")
        print(f"  geocode.amphoe          = {json.dumps(geo.get('amphoe_name'), ensure_ascii=False)}")
