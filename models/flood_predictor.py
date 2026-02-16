import sqlite3
import pandas as pd
import numpy as np
import requests
from datetime import datetime, timedelta
from sklearn.linear_model import LinearRegression
import functools
import pytz
from constants import (
    STATION_METADATA, RIVER_HYDRAULICS, RAINFALL_THRESHOLDS,
    HISTORICAL_EVENTS, RISK_CALCULATION, API_CONFIG,
    SYSTEM_CONFIG, calculate_flow_velocity, sigmoid_risk,
    calculate_eta_hours, calculate_actual_distance
)

# =============================================================
# UTILITY: Error Shielding Decorator
# =============================================================
def safe_value(func):
    """Decorator that sanitizes sensor values using station-specific thresholds."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        result = func(*args, **kwargs)
        if isinstance(result, dict):
            for key in ['level', 'value']:
                if key in result and result[key] is not None:
                    try:
                        val = float(result[key])
                        # Use station-specific validation
                        station_id = result.get('station_id', 'Unknown')
                        min_threshold = STATION_METADATA.get(station_id, {}).get('min_valid_level', -5.0)
                        if val <= min_threshold:
                            result[key] = None
                    except (ValueError, TypeError):
                        result[key] = None
        return result
    return wrapper

def clean_value(val, station_id=None):
    """Inline sanitizer for any sensor reading with station-specific logic."""
    if val is None:
        return None
    try:
        v = float(val)
        # Use station-specific minimum threshold
        min_threshold = STATION_METADATA.get(station_id, {}).get('min_valid_level', -5.0)
        return v if v > min_threshold else None
    except (ValueError, TypeError):
        return None

def get_bangkok_time():
    """Get current time in Asia/Bangkok timezone."""
    bangkok_tz = pytz.timezone(SYSTEM_CONFIG['timezone'])
    return datetime.now(bangkok_tz)

def parse_timestamp(ts_str, assume_timezone=None):
    """Parse timestamp string with timezone awareness."""
    if not ts_str:
        return get_bangkok_time()
    
    bangkok_tz = pytz.timezone(SYSTEM_CONFIG['timezone'])
    
    # Try different formats
    formats = ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%dT%H:%M:%S']
    
    for fmt in formats:
        try:
            dt = datetime.strptime(ts_str.strip(), fmt)
            if assume_timezone:
                dt = pytz.timezone(assume_timezone).localize(dt)
            elif dt.tzinfo is None:
                dt = bangkok_tz.localize(dt)
            return dt
        except ValueError:
            continue
    
    # Fallback to current time
    return get_bangkok_time()

# =============================================================
# CONSTANTS (Legacy - kept for compatibility)
# =============================================================
# These are now imported from constants.py for better organization
SADAO_TO_HATYAI_KM = RIVER_HYDRAULICS['straight_distance_km']
BASE_VELOCITY_MS = RIVER_HYDRAULICS['base_velocity_normal']


class FloodPredictor:
    """
    HYFI v2 — Hatyai Flood Intelligence Engine
    
    Features:
    - Hybrid Risk Analysis (Sensor + Rain Forecast)
    - Time-to-Impact ETA (Sadao → Hatyai)
    - Historical Flood Comparison
    - 24-Hour Hourly Rain Intensity
    - Smart Error Shielding
    """
    
    def __init__(self, db_path="data/flood_data.db"):
        self.db_path = db_path
        self._cached_model = None
        self._cached_model_lag = 0
        self._cached_model_time = None
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS water_levels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                station_id TEXT NOT NULL,
                level REAL,
                created_at TEXT DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now')),
                UNIQUE(timestamp, station_id)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS risk_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now')),
                rain_forecast_3d REAL,
                sensor_level REAL,
                risk_score REAL,
                alert_level TEXT,
                data_source TEXT,
                created_at TEXT DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now'))
            )
        """)
        # Add indexes for better performance
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_water_levels_timestamp ON water_levels(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_water_levels_station ON water_levels(station_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_risk_logs_timestamp ON risk_logs(timestamp)")
        conn.commit()
        conn.close()

    # =========================================================
    # DATA ACQUISITION
    # =========================================================
    def fetch_and_store_data(self):
        """
        Fetch water levels with atomic operations and proper timezone handling.
        Smart Cache: Checks DB first. If data < cache minutes old, returns DB data.
        Otherwise fetches from ThaiWater API with timeout.
        """
        api_config = API_CONFIG['thaiwater']
        cache_minutes = api_config['cache_minutes']
        
        # Use station metadata from constants
        station_mapping = {info['id']: name for name, info in STATION_METADATA.items()}
        primary_station_id = STATION_METADATA['HatYai']['id']
        
        result = {
            "level": None,
            "station_code": None,
            "station_name": None,
            "timestamp": None,
            "is_fallback": True,
            "all_data": {}
        }

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            # Atomic check for recent data
            cursor.execute("""
                SELECT timestamp, station_id, level 
                FROM water_levels 
                WHERE timestamp >= datetime('now', '-{} minutes')
                ORDER BY timestamp DESC
            """.format(cache_minutes))
            rows = cursor.fetchall()
            
            if rows:
                # Process cached data
                latest_ts_str = rows[0][0]
                latest_ts = parse_timestamp(latest_ts_str)
                
                # Build result from cached data
                for ts_str, station_id, level in rows:
                    station_name = station_mapping.get(station_id, station_id)
                    if ts_str == latest_ts_str:
                        result["all_data"][station_name] = level
                
                result["timestamp"] = latest_ts
                
                # Set primary reading (prefer HatYai)
                if "HatYai" in result["all_data"]:
                    result["level"] = result["all_data"]["HatYai"]
                    result["station_code"] = f"ID:{primary_station_id}"
                    result["station_name"] = "HatYai"
                    result["is_fallback"] = False
                elif "Sadao" in result["all_data"]:
                    result["level"] = result["all_data"]["Sadao"]
                    result["station_code"] = f"ID:{STATION_METADATA['Sadao']['id']}"
                    result["station_name"] = "Sadao"
                    result["is_fallback"] = True
                
                print(f"[INFO] Using cached DB data from {latest_ts_str}")
                return result
                
        except Exception as e:
            print(f"[WARN] DB Cache check failed: {e}")
        finally:
            conn.close()

        # Fetch from API if no recent data
        try:
            response = requests.get(
                api_config['url'], 
                headers={'User-Agent': 'Mozilla/5.0'}, 
                timeout=api_config['timeout']
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # Navigate API structure
                entries = []
                if isinstance(data, dict):
                    wd = data.get('waterlevel_data', {})
                    if isinstance(wd, dict):
                        entries = wd.get('data', [])
                    elif isinstance(wd, list):
                        entries = wd
                    else:
                        entries = data.get('data', [])
                elif isinstance(data, list):
                    entries = data
                
                if not isinstance(entries, list):
                    entries = []
                
                # Atomic database operation
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                try:
                    for entry in entries:
                        if not isinstance(entry, dict):
                            continue
                            
                        st_info = entry.get('station', {})
                        if not isinstance(st_info, dict):
                            continue
                        
                        station_id = st_info.get('id')
                        if station_id not in station_mapping:
                            continue
                        
                        station_name = station_mapping[station_id]
                        raw_val = entry.get('waterlevel_msl') or entry.get('waterlevel') or entry.get('value')
                        val_float = clean_value(raw_val, station_name)
                        
                        if val_float is not None:
                            timestamp_str = entry.get('waterlevel_datetime') or entry.get('datetime')
                            ts = parse_timestamp(timestamp_str) if timestamp_str else get_bangkok_time()
                            ts_str = ts.strftime('%Y-%m-%d %H:%M:%S')
                            
                            # Atomic insert with ignore for duplicates
                            cursor.execute(
                                "INSERT OR IGNORE INTO water_levels (timestamp, station_id, level) VALUES (?, ?, ?)",
                                (ts_str, station_name, val_float)
                            )
                            
                            result["all_data"][station_name] = val_float
                            
                            # Set primary reading
                            if result["level"] is None or station_id == primary_station_id:
                                result["level"] = val_float
                                result["station_code"] = f"ID:{station_id}"
                                result["station_name"] = station_name
                                result["timestamp"] = ts
                                result["is_fallback"] = (station_id != primary_station_id)
                    
                    conn.commit()
                    
                except Exception as e:
                    print(f"[ERROR] Database operation failed: {e}")
                    conn.rollback()
                finally:
                    conn.close()
                    
            else:
                print(f"[ERROR] API returned {response.status_code}")
                
        except Exception as e:
            print(f"[ERROR] Fetch Failed: {e}")
            
        return result

    def fetch_rain_forecast(self):
        """
        Fetch rain forecast from Open-Meteo with proper timezone handling.
        Returns both daily (3-day) and hourly (24h) data.
        """
        try:
            api_config = API_CONFIG['openmeteo']
            hatyai_coords = STATION_METADATA['HatYai']
            
            params = {
                "latitude": hatyai_coords['lat'],
                "longitude": hatyai_coords['lon'],
                "daily": "precipitation_sum",
                "hourly": "precipitation",
                "timezone": SYSTEM_CONFIG['timezone'],
                "forecast_days": 3
            }
            
            response = requests.get(
                api_config['url'], 
                params=params, 
                timeout=api_config['timeout']
            )
            
            if response.status_code == 200:
                data = response.json()
                daily = data.get("daily", {})
                hourly = data.get("hourly", {})
                
                daily_rain = daily.get("precipitation_sum", [])
                rain_sum = sum(daily_rain)
                
                # Extract hourly data (next 24 hours)
                hourly_times = hourly.get("time", [])[:24]
                hourly_rain = hourly.get("precipitation", [])[:24]
                
                # Convert hourly times to Bangkok timezone
                bangkok_tz = pytz.timezone(SYSTEM_CONFIG['timezone'])
                formatted_times = []
                for time_str in hourly_times:
                    try:
                        dt = datetime.fromisoformat(time_str.replace('Z', '+00:00'))
                        bangkok_dt = dt.astimezone(bangkok_tz)
                        formatted_times.append(bangkok_dt)
                    except:
                        formatted_times.append(get_bangkok_time())
                
                return {
                    "rain_sum_3d": rain_sum,
                    "raw_daily": daily_rain,
                    "daily_dates": daily.get("time", []),
                    "hourly_times": formatted_times,
                    "hourly_rain": hourly_rain,
                    "update_time": get_bangkok_time()
                }
                
        except Exception as e:
            print(f"[ERROR] Open-Meteo Failed: {e}")
        
        return {
            "rain_sum_3d": 0.0, 
            "raw_daily": [], 
            "hourly_times": [], 
            "hourly_rain": [], 
            "error": True,
            "update_time": get_bangkok_time()
        }

    # =========================================================
    # INTELLIGENCE ENGINE
    # =========================================================
    def analyze_flood_risk(self, sensor_data, rain_data):
        """
        Advanced Risk Intelligence Engine v3:
        - Smooth Sigmoid-based Risk Assessment
        - Hydraulic-aware ETA calculation
        - Historical Comparison with 2010 benchmark
        - Physical reality-based logic
        """
        rain_sum = rain_data.get("rain_sum_3d", 0.0)
        current_level = sensor_data.get("level")
        
        # 1. Calculate Rain Risk (0-100%)
        rain_risk_pc = min((rain_sum / RAINFALL_THRESHOLDS['catastrophic_24h']) * 100, 100)
        
        # 2. Calculate Water Level Risk using Sigmoid Function
        if current_level is not None:
            water_risk_pc = sigmoid_risk(
                current_level, 
                RISK_CALCULATION['sigmoid_k'], 
                RISK_CALCULATION['sigmoid_x0']
            )
        else:
            water_risk_pc = 0.0
        
        # 3. Combined Risk Assessment (Smooth Weighted Average)
        if current_level is not None:
            # Use weighted average for smooth transitions
            final_risk = (
                rain_risk_pc * RISK_CALCULATION['rainfall_weight'] + 
                water_risk_pc * RISK_CALCULATION['water_level_weight']
            )
            confidence = 90
            source = f"Hybrid ({sensor_data.get('station_code')})"
        else:
            # No sensor data - rely on rain only
            final_risk = rain_risk_pc
            confidence = 65
            source = "Virtual (Rain Only)"
        
        # 4. Enhanced Alert Logic
        if final_risk > RISK_CALCULATION['critical_min']:
            alert_level = "CRITICAL"
            color = "#ff5252"
            msg_th = "วิกฤต: ความเสี่ยงน้ำท่วมสูงมาก"
            msg_en = "CRITICAL: High flood probability"
            checklist_en = [
                "Move vehicles to high ground immediately",
                "Cut ground-floor electricity",
                "Prepare emergency kit & medicine",
                "Evacuate elderly/disabled persons"
            ]
            checklist_th = [
                "ย้ายรถไปที่สูงทันที (เช่น ตึกฟักทอง)",
                "ตัดไฟชั้นล่าง",
                "เตรียมชุดฉุกเฉินและยา",
                "อพยพผู้สูงอายุ/ผู้พิการ"
            ]
        elif final_risk > RISK_CALCULATION['warning_max']:
            alert_level = "WARNING"
            color = "#ffa726"
            msg_th = "เฝ้าระวัง: ฝนตกหนัก / ดินชุ่มน้ำ"
            msg_en = "WARNING: Elevated rain accumulation"
            checklist_en = [
                "Move belongings to 2nd floor",
                "Check ground-floor power outlets",
                "Fill vehicle fuel tank",
                "Monitor updates every hour"
            ]
            checklist_th = [
                "ยกของขึ้นชั้น 2",
                "ตรวจสอบปลั๊กไฟชั้นล่าง",
                "เติมน้ำมันรถให้เต็ม",
                "ติดตามข่าวทุกชั่วโมง"
            ]
        else:
            alert_level = "NORMAL"
            color = "#66bb6a"
            msg_th = "ปกติ: สถานการณ์ทั่วไป"
            msg_en = "NORMAL: All systems green"
            checklist_en = [
                "Monitor daily news",
                "Check drains around home",
                "Keep flashlight & batteries ready"
            ]
            checklist_th = [
                "ติดตามข่าวสารประจำวัน",
                "ดูแลรางระบายน้ำรอบบ้าน",
                "เตรียมไฟฉายและถ่านสำรอง"
            ]

        # 5. Enhanced Outlook Logic
        daily_rain = rain_data.get("raw_daily", [])
        outlook = {
            "trend": "Analyzing...",
            "trend_en": "Analyzing...", "trend_th": "กำลังวิเคราะห์...",
            "max_rain_day_label_en": "N/A", "max_rain_day_label_th": "N/A",
            "max_rain_val": 0,
            "summary_en": "Waiting for data...", "summary_th": "รอข้อมูล...",
            "daily_vals": [],
            "daily_labels_en": [], "daily_labels_th": []
        }
        
        if daily_rain and len(daily_rain) >= 3:
            d1, d2, d3 = daily_rain[:3]
            
            # Enhanced trend analysis
            if d2 > d1 + RAINFALL_THRESHOLDS['light_daily']:
                trend = "Rising"
            elif d2 < d1 - RAINFALL_THRESHOLDS['light_daily']:
                trend = "Falling"
            else:
                trend = "Stable"
            
            max_val = max(d1, d2, d3)
            max_idx = [d1, d2, d3].index(max_val)
            
            # Localization
            days_labels_th = ["พรุ่งนี้", "อีก 2 วัน", "อีก 3 วัน"]
            days_labels_en = ["Tomorrow", "Day 2", "Day 3"]
            
            # Enhanced summary based on rainfall thresholds
            if rain_sum < RAINFALL_THRESHOLDS['light_daily']:
                summary_en = "Dry spell, no flood risk."
                summary_th = "ฝนทิ้งช่วง ไม่มีความเสี่ยงน้ำท่วม"
            elif rain_sum < RAINFALL_THRESHOLDS['moderate_daily']:
                summary_en = "Light scattered rain."
                summary_th = "มีฝนเล็กน้อยกระจายทั่วไป"
            elif rain_sum < RAINFALL_THRESHOLDS['heavy_daily']:
                summary_en = "Moderate rain, drains should cope."
                summary_th = "ฝนปานกลาง การระบายน้ำยังรับได้"
            elif rain_sum < RAINFALL_THRESHOLDS['extreme_daily']:
                summary_en = "Heavy rain ahead! Stay alert."
                summary_th = "ฝนตกหนัก! โปรดระมัดระวัง"
            else:
                summary_en = "EXTREME RAIN. FLOOD LIKELY."
                summary_th = "ฝนตกหนักมาก! เสี่ยงน้ำท่วมสูง"
            
            # Trend localization
            trend_th = {
                "Rising": "แนวโน้มเพิ่มขึ้น",
                "Falling": "แนวโน้มลดลง",
                "Stable": "ทรงตัว"
            }.get(trend, "ทรงตัว")
            
            outlook = {
                "trend": trend,
                "trend_en": trend,
                "trend_th": trend_th,
                "max_rain_day_label_en": days_labels_en[max_idx],
                "max_rain_day_label_th": days_labels_th[max_idx],
                "max_rain_val": round(max_val, 1),
                "summary_en": summary_en,
                "summary_th": summary_th,
                "daily_vals": [round(d1, 1), round(d2, 1), round(d3, 1)],
                "daily_labels_en": days_labels_en,
                "daily_labels_th": days_labels_th
            }

        # 6. Advanced Time-to-Impact with Hydraulic Logic
        eta = self.estimate_time_to_impact_hydraulic(sensor_data)
        
        # 7. Historical Comparison with Correct 2010 Benchmark
        history = self.get_historical_comparison_enhanced(rain_sum)

        # 8. Log Assessment
        self._log_risk_assessment(rain_sum, current_level, final_risk, alert_level, source)

        # 9. Generate Situation Summary
        summary_report = self.generate_situation_summary(rain_sum, sensor_data, final_risk, eta)

        return {
            "primary_risk": round(final_risk, 1),
            "alert_level": alert_level,
            "main_message_en": msg_en,
            "main_message_th": msg_th,
            "action_checklist_en": checklist_en,
            "action_checklist_th": checklist_th,
            "data_source": source,
            "confidence_score": confidence,
            "is_sensor_active": (sensor_data.get("level") is not None),
            "rain_sum": round(rain_sum, 1),
            "current_level": current_level,
            "color": color,
            "outlook": outlook,
            "eta": eta,
            "history": history,
            "summary_report": summary_report
        }

    def generate_situation_summary(self, rain_sum, sensor_data, risk_score, eta):
        """
        Generates a 4-line dynamic situation report (TH/EN).
        """
        # 1. Headline
        if risk_score > 70:
            head_th = "🔴 วิกฤต: น้ำท่วมสูงมาก เตรียมรับมือทันที"
            head_en = "🔴 CRITICAL: High flood risk. Immediate action."
        elif risk_score > 30:
            head_th = "🟡 เฝ้าระวัง: ฝนเริ่มสะสม ดินชุ่มน้ำ"
            head_en = "🟡 WATCH: Accumulating rain. Soil saturated."
        else:
            head_th = "🟢 สถานการณ์ปกติ: ไม่มีฝนหนักใน 3 วันนี้"
            head_en = "🟢 NORMAL: No heavy rain forecast in 3 days."
            
        # 2. Rain Context (Compare to 2010)
        rain_2010 = 350.0 # Approx 2010 storm
        rain_pct_2010 = (rain_sum / rain_2010) * 100
        if rain_pct_2010 < 10:
            rain_th = f"ฝนสะสม {rain_sum:.1f} มม. (น้อยมากเมื่อเทียบกับปี 2010)"
            rain_en = f"Rain {rain_sum:.1f} mm (Low compared to 2010)"
        elif rain_pct_2010 < 50:
            rain_th = f"ฝนสะสม {rain_sum:.1f} มม. (ปานกลาง ต้องติดตาม)"
            rain_en = f"Rain {rain_sum:.1f} mm (Moderate, monitoring required)"
        else:
            rain_th = f"ฝนสะสม {rain_sum:.1f} มม. (สูง! ใกล้เคียงปีน้ำท่วมใหญ่)"
            rain_en = f"Rain {rain_sum:.1f} mm (HIGH! Approaching historic flood)"
            
        # 3. Upstream Analysis
        all_d = sensor_data.get('all_data', {})
        sadao = all_d.get('Sadao')
        if sadao is None:
            up_th = "ไม่สามารถอ่านค่าระดับน้ำต้นน้ำ (สะเดา) ได้"
            up_en = "Upstream sensor (Sadao) offline."
        elif sadao < 9.0:
            # Normal condition - reassure user
            up_th = f"ระดับน้ำสะเดาปกติ ({sadao:.2f} ม.) การไหลระบายดี"
            up_en = f"Upstream flow normal at Sadao ({sadao:.2f} m). Good drainage."
        else:
            # Critical condition - warn user
            eta_h = eta.get('eta_hours', 20)
            up_th = f"⚠️ มวลน้ำก้อนใหญ่จากสะเดา ({sadao:.2f} ม.) จะถึงเมืองใน {int(eta_h)} ชม."
            up_en = f"⚠️ CRITICAL: High water mass from Sadao ({sadao:.2f} m) arriving in {int(eta_h)} hrs."
            
        # 4. Action
        if risk_score > 70 or (sadao is not None and sadao > 9.0):
            act_th = "ยกของขึ้นที่สูงและเตรียมย้ายรถทันที"
            act_en = "Move assets to high ground immediately."
        elif risk_score > 30:
            act_th = "ติดตามระดับน้ำทุกชั่วโมง เตรียมไฟฉาย"
            act_en = "Monitor hourly updates. Check emergency kit."
        else:
            act_th = "ติดตามข่าวสารพยากรณ์อากาศตามปกติ"
            act_en = "Monitor daily weather news."
            
        return {
            "headline_th": head_th, "headline_en": head_en,
            "rain_context_th": rain_th, "rain_context_en": rain_en,
            "upstream_th": up_th, "upstream_en": up_en,
            "action_th": act_th, "action_en": act_en
        }


    # =========================================================
    # TIME-TO-IMPACT ENGINE
    # =========================================================
    def estimate_time_to_impact_hydraulic(self, sensor_data):
        """
        Advanced ETA calculation using hydraulic principles:
        - River sinuosity factor for actual distance
        - Flow velocity based on water height relative to bank full capacity
        - Realistic lag time accounting for runoff delay
        """
        all_data = sensor_data.get('all_data', {})
        sadao_level = all_data.get('Sadao')
        hatyai_level = all_data.get('HatYai')
        
        if sadao_level is None:
            return {
                "eta_hours": 0,
                "eta_label": "No Data",
                "velocity_ms": 0,
                "confidence": "Low (No upstream data)",
                "sadao_rising": False
            }
        
        # Calculate actual river distance with sinuosity
        actual_distance_km = calculate_actual_distance(
            RIVER_HYDRAULICS['straight_distance_km'],
            RIVER_HYDRAULICS['sinuosity_factor']
        )
        
        # Determine base velocity based on water level
        sadao_bank_full = STATION_METADATA['Sadao']['bank_full_capacity']
        
        if sadao_level <= sadao_bank_full * 0.5:
            # Dry season - very low flow
            base_velocity = RIVER_HYDRAULICS['base_velocity_dry']
        elif sadao_level <= sadao_bank_full:
            # Normal conditions
            base_velocity = RIVER_HYDRAULICS['base_velocity_normal']
        else:
            # Wet season - higher flow
            base_velocity = RIVER_HYDRAULICS['base_velocity_wet']
        
        # Calculate flow velocity using hydraulic principles
        velocity = calculate_flow_velocity(
            sadao_level, 
            sadao_bank_full, 
            base_velocity
        )
        
        # Get rate of change for dynamic adjustment
        roc = self.calculate_rate_of_change()
        sadao_roc = roc.get("Sadao", 0.0)
        
        # Adjust velocity based on rate of change (momentum factor)
        if sadao_roc > 0.5:  # Rapidly rising
            velocity *= 1.3
        elif sadao_roc > 0.2:  # Moderately rising
            velocity *= 1.1
        elif sadao_roc < -0.1:  # Falling
            velocity *= 0.8
        
        # Ensure velocity stays within realistic bounds
        velocity = max(0.1, min(velocity, RIVER_HYDRAULICS['max_velocity']))
        
        # Calculate ETA with lag time
        eta_hours = calculate_eta_hours(
            actual_distance_km, 
            velocity, 
            RIVER_HYDRAULICS['runoff_delay_hours']
        )
        
        # Confidence assessment
        if sadao_level > sadao_bank_full and sadao_roc > 0:
            conf = "High"
        elif sadao_level > sadao_bank_full * 0.8:
            conf = "Medium"
        else:
            conf = "Low"
        
        return {
            "eta_hours": round(eta_hours, 1),
            "eta_label": f"~{int(eta_hours)} hrs",
            "velocity_ms": round(velocity, 2),
            "confidence": conf,
            "sadao_rising": sadao_roc > 0,
            "actual_distance_km": actual_distance_km,
            "sadao_level": sadao_level,
            "bank_full_ratio": sadao_level / sadao_bank_full
        }

    def get_historical_comparison_enhanced(self, current_rain_3d):
        """
        Enhanced historical comparison using correct 2010 benchmark (520mm).
        Provides context against major flood events.
        """
        if current_rain_3d <= 0:
            return {
                "nearest_event": None,
                "percentage": 0,
                "message": "No significant rainfall.",
                "severity": "NONE"
            }
        
        # Use correct 2010 benchmark
        benchmark_2010 = HISTORICAL_EVENTS[2010]['rain_mm_3d']
        
        # Find nearest historical event
        nearest = None
        min_diff = float('inf')
        for year, event in HISTORICAL_EVENTS.items():
            diff = abs(event['rain_mm_3d'] - current_rain_3d)
            if diff < min_diff:
                min_diff = diff
                nearest = {"year": year, **event}
        
        # Calculate percentage of 2010 catastrophe
        pct_of_2010 = round((current_rain_3d / benchmark_2010) * 100, 1)
        
        # Enhanced messaging based on severity
        if current_rain_3d < 50:
            msg = "Well below any historical flood event."
            severity = "LOW"
        elif current_rain_3d < 150:
            msg = f"~{pct_of_2010}% of 2010 event intensity. Minor risk."
            severity = "MINOR"
        elif current_rain_3d < 300:
            msg = f"Approaching {nearest['label']} levels ({pct_of_2010}% of 2010)."
            severity = "MODERATE"
        elif current_rain_3d < 450:
            msg = f"HIGH RISK: Similar to {nearest['label']} ({pct_of_2010}% of 2010)."
            severity = "HIGH"
        else:
            msg = f"DANGER: Exceeding {nearest['label']}! ({pct_of_2010}% of 2010 catastrophe)"
            severity = "CRITICAL"
        
        return {
            "nearest_event": nearest,
            "percentage": pct_of_2010,
            "message": msg,
            "severity": severity,
            "benchmark_2010_mm": benchmark_2010
        }

    # =========================================================
    # LOGGING & DATA ACCESS
    # =========================================================
    def _log_risk_assessment(self, rain, level, risk, alert, source):
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO risk_logs (rain_forecast_3d, sensor_level, risk_score, alert_level, data_source)
                VALUES (?, ?, ?, ?, ?)
            """, (rain, level, risk, alert, source))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[WARN] Failed to log risk: {e}")

    def get_latest_data(self, hours=24):
        """
        Get latest water level data with proper timezone handling.
        """
        conn = sqlite3.connect(self.db_path)
        query = f"""
            SELECT timestamp, station_id, level 
            FROM water_levels 
            WHERE timestamp >= datetime('now', '-{hours} hours')
            ORDER BY timestamp ASC
        """
        df = pd.read_sql_query(query, conn)
        conn.close()
        
        if not df.empty:
            # Convert timestamps with timezone awareness
            df['timestamp'] = df['timestamp'].apply(lambda x: parse_timestamp(x))
            df = df.dropna(subset=['timestamp'])
            
            # Apply station-specific validation
            valid_rows = []
            for _, row in df.iterrows():
                station_id = row['station_id']
                level = row['level']
                min_threshold = STATION_METADATA.get(station_id, {}).get('min_valid_level', -5.0)
                if level > min_threshold:
                    valid_rows.append(row)
            
            if valid_rows:
                df = pd.DataFrame(valid_rows)
            else:
                df = pd.DataFrame(columns=['timestamp', 'station_id', 'level'])
        
        return df

    def calculate_rate_of_change(self):
        """
        Calculate rate of change for each station over the last 2 hours.
        Uses proper timezone-aware calculations.
        """
        df = self.get_latest_data(hours=2)
        rates = {}
        
        if df.empty:
            return rates
            
        # Use Bangkok time for consistent calculations
        bangkok_tz = pytz.timezone(SYSTEM_CONFIG['timezone'])
        now = get_bangkok_time()
        start_time_limit = now - timedelta(hours=1.5)
        
        unique_stations = df['station_id'].unique()
        
        for station in unique_stations:
            station_df = df[df['station_id'] == station].sort_values('timestamp')
            recent_df = station_df[station_df['timestamp'] >= start_time_limit]
            
            if len(recent_df) >= 2:
                last_row = recent_df.iloc[-1]
                first_row = recent_df.iloc[0]
                level_diff = last_row['level'] - first_row['level']
                time_diff_hours = (last_row['timestamp'] - first_row['timestamp']).total_seconds() / 3600
                
                if time_diff_hours > 0.1:
                    rates[station] = level_diff / time_diff_hours
                else:
                    rates[station] = 0.0
            else:
                rates[station] = 0.0
                
        return rates

    # =========================================================
    # PREDICTION MODEL
    # =========================================================
    def train_prediction_model(self):
        """
        Enhanced prediction model with proper caching and timezone handling.
        """
        # Cache model for 30 minutes
        now = get_bangkok_time()
        if (self._cached_model is not None 
            and self._cached_model_time is not None
            and (now - self._cached_model_time).total_seconds() < 1800):
            return self._cached_model, self._cached_model_lag
        
        df = self.get_latest_data(hours=168)  # 7 days
        
        if df.empty:
            return None, 0

        # Create pivot table with proper timezone handling
        df_pivot = df.pivot_table(index='timestamp', columns='station_id', values='level').dropna()
        df_hourly = df_pivot.resample('1h').mean().interpolate()
        
        if 'HatYai' not in df_hourly.columns or 'Sadao' not in df_hourly.columns:
            return None, 0
            
        # Find optimal lag with correlation analysis
        max_corr = -1
        best_lag = 0
        
        for lag in range(1, 13):  # 1-12 hours lag
            sadao_shifted = df_hourly['Sadao'].shift(lag)
            corr = df_hourly['HatYai'].corr(sadao_shifted)
            if corr > max_corr:
                max_corr = corr
                best_lag = lag
                
        # Prepare training data
        data = pd.concat([df_hourly['HatYai'], df_hourly['Sadao'].shift(best_lag)], axis=1).dropna()
        data.columns = ['HatYai', 'Sadao_Lagged']
        
        if len(data) < 5:
            return None, 0
            
        X = data[['Sadao_Lagged']]
        y = data['HatYai']
        
        # Train model
        model = LinearRegression()
        model.fit(X, y)
        
        # Cache the model
        self._cached_model = model
        self._cached_model_lag = best_lag
        self._cached_model_time = now
        
        return model, best_lag

    def predict_next_hours(self, hours=3):
        """
        Enhanced prediction with proper timezone handling.
        """
        model, lag = self.train_prediction_model()
        
        if model is None:
            return []
        
        predictions = []
        current_time = get_bangkok_time()
        
        # Get more historical data for better predictions
        df = self.get_latest_data(hours=lag+hours+24)
        if df.empty:
            return []
            
        # Prepare Sadao data
        df_sadao = df[df['station_id'] == 'Sadao'].set_index('timestamp')[['level']].resample('1h').mean().interpolate()
        
        for h in range(1, hours + 1):
            future_time = current_time + timedelta(hours=h)
            target_sadao_time = future_time - timedelta(hours=lag)
            
            try:
                # Find nearest Sadao data
                if len(df_sadao) > 0:
                    time_diffs = abs(df_sadao.index - target_sadao_time)
                    nearest_idx = time_diffs.idxmin()
                    sadao_val = df_sadao.loc[nearest_idx, 'level']
                    
                    # Make prediction
                    pred_level = model.predict([[sadao_val]])[0]
                    predictions.append({
                        "time": future_time, 
                        "level": pred_level,
                        "confidence": "Medium" if lag <= 6 else "Low"
                    })
            except Exception as e:
                print(f"[WARN] Prediction failed for hour {h}: {e}")
                pass
                
        return predictions

    # =========================================================
    # NOTIFICATIONS
    # =========================================================
    def _send_line_notify(self, message, token):
        url = 'https://notify-api.line.me/api/notify'
        headers = {'Authorization': f'Bearer {token}'}
        data = {'message': message}
        try:
            requests.post(url, headers=headers, data=data)
        except Exception as e:
            print(f"[ERROR] Failed to send Line Notify: {e}")


if __name__ == "__main__":
    print("Testing FloodPredictor v2...")
    predictor = FloodPredictor()
    print("Fetching data...")
    data = predictor.fetch_and_store_data()
    print("Sensor:", data.get("station_code"), data.get("level"))
    rain = predictor.fetch_rain_forecast()
    print("Rain 3D:", rain.get("rain_sum_3d"), "Hourly pts:", len(rain.get("hourly_rain", [])))
    risk = predictor.analyze_flood_risk(data, rain)
    print("Risk:", risk.get("primary_risk"), "ETA:", risk.get("eta", {}).get("eta_label"))
    print("History:", risk.get("history", {}).get("message"))
