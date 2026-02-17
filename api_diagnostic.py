"""
HYFI API Diagnostic Tool - Probes ThaiWater + RID APIs
"""
import sys
import os
os.environ['PYTHONIOENCODING'] = 'utf-8'
sys.stdout.reconfigure(encoding='utf-8')

import requests
import json
from datetime import datetime, timedelta
from constants import STATION_METADATA, API_CONFIG

BANGKOK_OFFSET = timedelta(hours=7)

def now_ict():
    return datetime.utcnow() + BANGKOK_OFFSET

def probe_thaiwater_api():
    print("=" * 60)
    print("  HYFI API DIAGNOSTIC REPORT")
    print(f"  Run at: {now_ict().strftime('%Y-%m-%d %H:%M:%S')} (ICT)")
    print("=" * 60)
    
    api_url = API_CONFIG['thaiwater']['url']
    station_ids = {info['id']: name for name, info in STATION_METADATA.items()}
    
    print(f"\n[API] Calling: {api_url}")
    print(f"  Target station IDs: {dict(station_ids)}")
    
    try:
        response = requests.get(api_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        print(f"  HTTP Status: {response.status_code}")
        
        if response.status_code != 200:
            print(f"  [FAIL] API returned non-200!")
            return
        
        data = response.json()
        
        entries = []
        if isinstance(data, dict):
            wd = data.get('waterlevel_data', {})
            if isinstance(wd, dict):
                entries = wd.get('data', [])
            elif isinstance(wd, list):
                entries = wd
            else:
                entries = data.get('data', [])
            print(f"  API top-level keys: {list(data.keys())}")
        elif isinstance(data, list):
            entries = data
        
        print(f"  Total entries: {len(entries)}")
        
        print("\n" + "-" * 60)
        print("  STATION DATA")
        print("-" * 60)
        
        current_time = now_ict()
        found_any = False
        
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            
            st_info = entry.get('station', {})
            if not isinstance(st_info, dict):
                continue
            
            station_id = st_info.get('id')
            if station_id not in station_ids:
                continue
            
            found_any = True
            station_name = station_ids[station_id]
            
            print(f"\n--- {station_name} (ID: {station_id}) ---")
            print(f"  Code: {st_info.get('code', 'N/A')}")
            
            # Water level values
            wl_msl = entry.get('waterlevel_msl')
            wl_raw = entry.get('waterlevel')
            wl_val = entry.get('value')
            
            print(f"  waterlevel_msl = {wl_msl}")
            print(f"  waterlevel     = {wl_raw}")
            print(f"  value          = {wl_val}")
            
            # Timestamp
            ts_str = entry.get('waterlevel_datetime') or entry.get('datetime')
            print(f"  timestamp_raw  = {ts_str}")
            
            if ts_str:
                try:
                    clean_ts = ts_str.replace('+07:00','').replace('+00:00','').replace('T',' ')
                    if '.' in clean_ts:
                        clean_ts = clean_ts.split('.')[0]
                    ts = datetime.strptime(clean_ts.strip(), '%Y-%m-%d %H:%M:%S')
                    
                    age = current_time - ts
                    age_hours = age.total_seconds() / 3600
                    
                    print(f"  parsed_time    = {ts}")
                    print(f"  current_time   = {current_time.strftime('%Y-%m-%d %H:%M:%S')}")
                    print(f"  data_age       = {age_hours:.1f} hours ({age.days}d {age.seconds//3600}h)")
                    
                    if age_hours > 24:
                        print(f"  >>> ZOMBIE DATA! ({age_hours:.0f}h = {age.days} days old)")
                    elif age_hours > 6:
                        print(f"  >>> STALE ({age_hours:.1f}h old)")
                    elif age_hours > 1:
                        print(f"  >>> SLIGHTLY OLD ({age_hours:.1f}h)")
                    else:
                        print(f"  >>> FRESH ({age_hours:.1f}h)")
                        
                except Exception as e:
                    print(f"  [WARN] Cannot parse timestamp: {e}")
            
            # Threshold check
            meta = STATION_METADATA.get(station_name, {})
            bank_full = meta.get('bank_full_capacity', 0)
            critical = meta.get('critical_threshold', 0)
            
            level = wl_msl if wl_msl is not None else (wl_raw if wl_raw is not None else wl_val)
            if level is not None:
                try:
                    level = float(level)
                    print(f"  level={level:.2f}m  bank_full={bank_full}m  critical={critical}m")
                    if level >= critical:
                        print(f"  >>> CRITICAL ZONE")
                    elif level >= bank_full:
                        print(f"  >>> WARNING ZONE")
                    else:
                        pct = (level / bank_full * 100) if bank_full else 0
                        print(f"  >>> NORMAL ({pct:.0f}% of bank full)")
                except (ValueError, TypeError):
                    pass
            
            print(f"  all_keys: {list(entry.keys())}")
        
        if not found_any:
            print("\n  [FAIL] NO MATCHING STATIONS IN RESPONSE!")
            print("  Dumping first 5 station IDs from API:")
            for i, entry in enumerate(entries[:5]):
                st = entry.get('station', {}) if isinstance(entry, dict) else {}
                print(f"    [{i}] id={st.get('id')} code={st.get('code')} name={st.get('station_name')}")
        
    except requests.Timeout:
        print("  [FAIL] API TIMEOUT (10s)")
    except requests.ConnectionError:
        print("  [FAIL] CANNOT REACH API")
    except Exception as e:
        print(f"  [FAIL] ERROR: {e}")
        import traceback
        traceback.print_exc()


def probe_rid_api():
    print("\n\n" + "=" * 60)
    print("  RID API PROBE")
    print("=" * 60)
    
    rid_url = API_CONFIG['rid']['url']
    print(f"\n[API] Calling: {rid_url}")
    
    try:
        response = requests.get(rid_url, timeout=10)
        print(f"  HTTP Status: {response.status_code}")
        print(f"  Content-Type: {response.headers.get('content-type', 'N/A')}")
        print(f"  Response size: {len(response.text)} bytes")
        
        try:
            data = response.json()
            print(f"  Parsed as JSON: YES")
            if isinstance(data, dict):
                print(f"  Keys: {list(data.keys())[:10]}")
                # Print a preview
                preview = json.dumps(data, indent=2, ensure_ascii=False)[:1000]
                print(f"  Preview:\n{preview}")
            elif isinstance(data, list):
                print(f"  Array length: {len(data)}")
                if data and isinstance(data[0], dict):
                    print(f"  First item keys: {list(data[0].keys())}")
                    preview = json.dumps(data[0], indent=2, ensure_ascii=False)[:500]
                    print(f"  First item:\n{preview}")
        except json.JSONDecodeError:
            print(f"  Not JSON. First 500 chars:")
            print(f"  {response.text[:500]}")
            
    except requests.Timeout:
        print("  [FAIL] RID API TIMEOUT")
    except requests.ConnectionError:
        print("  [FAIL] CANNOT REACH RID API")
    except Exception as e:
        print(f"  [FAIL] ERROR: {e}")


if __name__ == "__main__":
    probe_thaiwater_api()
    probe_rid_api()
