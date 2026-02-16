import sqlite3
import pandas as pd
import numpy as np
import requests
from datetime import datetime, timedelta
from sklearn.linear_model import LinearRegression
import functools

# =============================================================
# UTILITY: Error Shielding Decorator
# =============================================================
def safe_value(func):
    """Decorator that sanitizes sensor values. Kills -9.99 ghosts."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        result = func(*args, **kwargs)
        if isinstance(result, dict):
            for key in ['level', 'value']:
                if key in result and result[key] is not None:
                    try:
                        if float(result[key]) <= -5.0:
                            result[key] = None
                    except (ValueError, TypeError):
                        result[key] = None
        return result
    return wrapper

def clean_value(val):
    """Inline sanitizer for any sensor reading."""
    if val is None:
        return None
    try:
        v = float(val)
        return v if v > -5.0 else None
    except (ValueError, TypeError):
        return None

# =============================================================
# CONSTANTS
# =============================================================
# Distance from Sadao (X.173) to Hat Yai (X.90) via U-Tapao Canal
SADAO_TO_HATYAI_KM = 60.0
# Base flow velocity in m/s (adjustable)
BASE_VELOCITY_MS = 0.8
# Historical flood events for comparison (3-day rain mm)
HISTORICAL_EVENTS = {
    2010: {"rain_mm": 500, "label": "2010 Great Flood", "severity": "CATASTROPHIC"},
    2012: {"rain_mm": 350, "label": "2012 Severe Flood", "severity": "SEVERE"},
    2017: {"rain_mm": 200, "label": "2017 Moderate Flood", "severity": "MODERATE"},
    2022: {"rain_mm": 250, "label": "2022 Flash Flood", "severity": "MODERATE"},
}


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
                timestamp TEXT,
                station_id TEXT,
                level REAL,
                UNIQUE(timestamp, station_id)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS risk_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now', 'localtime')),
                rain_forecast_3d REAL,
                sensor_level REAL,
                risk_score REAL,
                alert_level TEXT,
                data_source TEXT
            )
        """)
        conn.commit()
        conn.close()

    # =========================================================
    # DATA ACQUISITION
    # =========================================================
    def fetch_and_store_data(self):
        """
        Fetch water levels.
        Smart Cache: Checks DB first. If data < 15 mins old, returns DB data (0ms).
        Otherwise fetches from ThaiWater API (timeout 5s).
        """
        api_url = "https://api-v3.thaiwater.net/api/v1/thaiwater30/public/waterlevel_load"
        headers = {'User-Agent': "Mozilla/5.0"}
        
        # Station IDs from ThaiWater API
        STATION_IDS = {
            2585: "HatYai",       # Kuan Nong Hong — main Hatyai station
            2590: "Sadao",        # Upstream station
            2589: "Kallayanamit", # Ban Bang Sala — midstream
        }
        PRIMARY_STATION_ID = 2585
        
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

        # 1. SMART CHECK: Do we have recent data?
        try:
            cursor.execute("""
                SELECT timestamp, station_id, level 
                FROM water_levels 
                WHERE timestamp >= datetime('now', '-15 minutes', 'localtime')
            """)
            rows = cursor.fetchall()
            
            if rows:
                # We have recent data! Construct result without API call.
                # Find latest timestamp across all rows
                latest_ts_str = max(r[0] for r in rows)
                latest_ts = datetime.strptime(latest_ts_str, '%Y-%m-%d %H:%M:%S')
                
                start_fresh_data = {}
                for r_ts, r_id, r_lvl in rows:
                    if r_ts == latest_ts_str:
                        start_fresh_data[r_id] = r_lvl
                
                result["all_data"] = start_fresh_data
                result["timestamp"] = latest_ts
                
                # Set primary (HatYai) if available
                if "HatYai" in start_fresh_data:
                    result["level"] = start_fresh_data["HatYai"]
                    result["station_code"] = f"ID:{PRIMARY_STATION_ID}"
                    result["station_name"] = "HatYai"
                    result["is_fallback"] = False
                elif "Sadao" in start_fresh_data:
                    result["level"] = start_fresh_data["Sadao"]
                    result["station_code"] = f"ID:2590"
                    result["station_name"] = "Sadao"
                    result["is_fallback"] = True
                
                print(f"[INFO] Using cached DB data from {latest_ts_str}")
                conn.close()
                return result
        except Exception as e:
            print(f"[WARN] DB Cache check failed: {e}")

        # 2. API FETCH (Fail-fast: 5s timeout)
        try:
            response = requests.get(api_url, headers=headers, timeout=5)
            if response.status_code == 200:
                data = response.json()
                
                # Navigate the nested API structure:
                # data["waterlevel_data"]["data"] -> list of entries
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
                
                # Match by station ID
                for entry in entries:
                    if not isinstance(entry, dict):
                        continue
                    st_info = entry.get('station', {})
                    if not isinstance(st_info, dict):
                        continue
                    
                    station_id = st_info.get('id')
                    if station_id not in STATION_IDS:
                        continue
                    
                    name = STATION_IDS[station_id]
                    raw_val = entry.get('waterlevel_msl') or entry.get('waterlevel') or entry.get('value')
                    val_float = clean_value(raw_val)
                    
                    if val_float is not None:
                        timestamp_str = entry.get('waterlevel_datetime') or entry.get('datetime')
                        ts = datetime.now()
                        if timestamp_str:
                            try:
                                ts = datetime.strptime(timestamp_str.strip(), '%Y-%m-%d %H:%M:%S')
                            except ValueError:
                                try:
                                    ts = datetime.strptime(timestamp_str.strip(), '%Y-%m-%d %H:%M')
                                except ValueError:
                                    pass
                        
                        ts_str = ts.strftime('%Y-%m-%d %H:%M:%S')
                        cursor.execute(
                            "INSERT OR IGNORE INTO water_levels (timestamp, station_id, level) VALUES (?, ?, ?)",
                            (ts_str, name, val_float)
                        )
                        result["all_data"][name] = val_float
                        
                        # Set primary reading (prefer HatYai)
                        if result["level"] is None or station_id == PRIMARY_STATION_ID:
                            result["level"] = val_float
                            result["station_code"] = f"ID:{station_id}"
                            result["station_name"] = name
                            result["timestamp"] = ts
                            result["is_fallback"] = (station_id != PRIMARY_STATION_ID)
            else:
                print(f"[ERROR] API returned {response.status_code}")

        except Exception as e:
            print(f"[ERROR] Fetch Failed: {e}")
            
        conn.commit()
        conn.close()
        return result

    def fetch_rain_forecast(self):
        """
        Fetch rain forecast from Open-Meteo.
        Returns BOTH daily (3-day) and hourly (24h) data.
        """
        try:
            url = "https://api.open-meteo.com/v1/forecast"
            params = {
                "latitude": 7.0084,
                "longitude": 100.4767,
                "daily": "precipitation_sum",
                "hourly": "precipitation",
                "timezone": "Asia/Bangkok",
                "forecast_days": 3
            }
            res = requests.get(url, params=params, timeout=3)
            if res.status_code == 200:
                data = res.json()
                daily = data.get("daily", {})
                hourly = data.get("hourly", {})
                
                daily_rain = daily.get("precipitation_sum", [])
                rain_sum = sum(daily_rain)
                
                # Extract hourly data (next 24 hours)
                hourly_times = hourly.get("time", [])[:24]
                hourly_rain = hourly.get("precipitation", [])[:24]
                
                return {
                    "rain_sum_3d": rain_sum,
                    "raw_daily": daily_rain,
                    "daily_dates": daily.get("time", []),
                    "hourly_times": hourly_times,
                    "hourly_rain": hourly_rain,
                    "update_time": datetime.now()
                }
        except Exception as e:
            print(f"[ERROR] Open-Meteo Failed: {e}")
        
        return {"rain_sum_3d": 0.0, "raw_daily": [], "hourly_times": [], "hourly_rain": [], "error": True}

    # =========================================================
    # INTELLIGENCE ENGINE
    # =========================================================
    def analyze_flood_risk(self, sensor_data, rain_data):
        """
        Risk Intelligence Engine v2:
        - Weighted Risk: (Rain% * 0.6) + (Sensor% * 0.4)
        - Time-to-Impact ETA
        - Historical Comparison
        - Enhanced Outlook with daily breakdown
        """
        rain_sum = rain_data.get("rain_sum_3d", 0.0)
        current_level = sensor_data.get("level")
        
        # 1. Normalize Rain Risk (0-100%)
        rain_risk_pc = min((rain_sum / 150.0) * 100, 100)
        
        # 2. Normalize Sensor Risk (0-100%)
        sensor_risk_pc = 0.0
        if current_level is not None:
            if current_level < 9.0:
                sensor_risk_pc = (current_level / 9.0) * 30
            elif current_level < 10.5:
                sensor_risk_pc = 30 + ((current_level - 9.0) / 1.5) * 40
            else:
                sensor_risk_pc = 70 + ((current_level - 10.5) / 0.5) * 30
            sensor_risk_pc = min(sensor_risk_pc, 100)

        # 3. Weighted Calculation
        if sensor_data.get("level") is None:
            final_risk = rain_risk_pc
            confidence = 65
            source = "Virtual (Rain Only)"
        else:
            final_risk = (rain_risk_pc * 0.6) + (sensor_risk_pc * 0.4)
            confidence = 90
            source = f"Hybrid ({sensor_data.get('station_code')})"

        # 4. Alert Level & Color
        if final_risk > 70:
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
        elif final_risk > 30:
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

        # 5. Outlook Logic
        daily_rain = rain_data.get("raw_daily", [])
        outlook = {
            "trend": "Analyzing...",
            "max_rain_day": "N/A",
            "summary": "Waiting for data...",
            "daily_vals": [],
            "daily_labels": []
        }
        
        if daily_rain and len(daily_rain) >= 3:
            d1, d2, d3 = daily_rain[:3]
            
            if d2 > d1 + 5:
                trend = "Rising"
            elif d2 < d1 - 5:
                trend = "Falling"
            else:
                trend = "Stable"
            
            max_val = max(d1, d2, d3)
            max_idx = [d1, d2, d3].index(max_val)
            days_labels = ["Tomorrow", "Day 2", "Day 3"]
            
            if rain_sum < 10:
                summary = "Dry spell, no flood risk."
            elif rain_sum < 30:
                summary = "Light scattered rain."
            elif rain_sum < 60:
                summary = "Moderate rain, drains should cope."
            elif rain_sum < 120:
                summary = "Heavy rain ahead! Stay alert."
            else:
                summary = "EXTREME RAIN. FLOOD LIKELY."
            
            outlook = {
                "trend": trend,
                "max_rain_day": f"{days_labels[max_idx]} ({max_val:.1f}mm)",
                "summary": summary,
                "daily_vals": [round(d1, 1), round(d2, 1), round(d3, 1)],
                "daily_labels": days_labels
            }

        # 6. Time-to-Impact
        eta = self.estimate_time_to_impact(sensor_data)
        
        # 7. Historical Comparison
        history = self.get_historical_comparison(rain_sum)

        # 8. Log
        self._log_risk_assessment(rain_sum, current_level, final_risk, alert_level, source)

        # 9. Summary Generation (New Feature)
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
    def estimate_time_to_impact(self, sensor_data):
        """
        Estimate how long until upstream water peaks reach Hatyai.
        Uses distance (60km) / velocity with dynamic adjustment.
        """
        roc = self.calculate_rate_of_change()
        sadao_roc = roc.get("Sadao", 0.0)
        
        # Adjust velocity based on rate of change
        # Faster rise = faster flow (more momentum)
        velocity = BASE_VELOCITY_MS
        if sadao_roc > 0.5:
            velocity = 1.2  # Fast flow
        elif sadao_roc > 0.2:
            velocity = 1.0  # Moderate flow
        elif sadao_roc > 0:
            velocity = 0.8  # Normal flow
        else:
            velocity = 0.5  # Slow/receding
        
        # ETA in hours
        distance_m = SADAO_TO_HATYAI_KM * 1000
        eta_seconds = distance_m / velocity
        eta_hours = eta_seconds / 3600
        
        # Confidence
        sadao_val = sensor_data.get("all_data", {}).get("Sadao")
        if sadao_val is not None and sadao_roc > 0:
            conf = "High"
        elif sadao_val is not None:
            conf = "Medium"
        else:
            conf = "Low (No upstream data)"
        
        return {
            "eta_hours": round(eta_hours, 1),
            "eta_label": f"~{int(eta_hours)} hrs",
            "velocity_ms": round(velocity, 1),
            "confidence": conf,
            "sadao_rising": sadao_roc > 0
        }

    # =========================================================
    # HISTORICAL COMPARISON
    # =========================================================
    def get_historical_comparison(self, current_rain_3d):
        """
        Compare current conditions to historical flood events.
        """
        if current_rain_3d <= 0:
            return {
                "nearest_event": None,
                "percentage": 0,
                "message": "No significant rainfall."
            }
        
        # Find nearest historical event
        nearest = None
        min_diff = float('inf')
        for year, event in HISTORICAL_EVENTS.items():
            diff = abs(event["rain_mm"] - current_rain_3d)
            if diff < min_diff:
                min_diff = diff
                nearest = {"year": year, **event}
        
        # Calculate percentage of worst event (2010)
        pct_of_worst = round((current_rain_3d / 500) * 100, 1)
        
        if current_rain_3d < 50:
            msg = "Well below any historical flood event."
        elif current_rain_3d < 150:
            msg = f"~{pct_of_worst}% of 2010 event intensity."
        elif current_rain_3d < 300:
            msg = f"Approaching {nearest['label']} levels ({pct_of_worst}% of 2010)."
        else:
            msg = f"DANGER: Exceeding {nearest['label']}! ({pct_of_worst}% of 2010 catastrophe)"
        
        return {
            "nearest_event": nearest,
            "percentage": pct_of_worst,
            "message": msg
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
            df['timestamp'] = pd.to_datetime(df['timestamp'], format='%Y-%m-%d %H:%M:%S', errors='coerce')
            df = df.dropna(subset=['timestamp'])
            df = df[df['level'] > -5.0]
        return df

    def calculate_rate_of_change(self):
        df = self.get_latest_data(hours=2)
        rates = {}
        
        if df.empty:
            return rates
            
        start_time_limit = df['timestamp'].max() - timedelta(hours=1.5)
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
        # Cache model for 30 minutes to avoid retraining on every page load
        now = datetime.now()
        if (self._cached_model is not None 
            and self._cached_model_time is not None
            and (now - self._cached_model_time).total_seconds() < 1800):
            return self._cached_model, self._cached_model_lag
        
        df = self.get_latest_data(hours=168)
        
        if df.empty:
            return None, 0

        df_pivot = df.pivot_table(index='timestamp', columns='station_id', values='level').dropna()
        df_hourly = df_pivot.resample('1h').mean().interpolate()
        
        if 'HatYai' not in df_hourly.columns or 'Sadao' not in df_hourly.columns:
            return None, 0
            
        max_corr = -1
        best_lag = 0
        
        for lag in range(1, 13):
            sadao_shifted = df_hourly['Sadao'].shift(lag)
            corr = df_hourly['HatYai'].corr(sadao_shifted)
            if corr > max_corr:
                max_corr = corr
                best_lag = lag
                
        data = pd.concat([df_hourly['HatYai'], df_hourly['Sadao'].shift(best_lag)], axis=1).dropna()
        data.columns = ['HatYai', 'Sadao_Lagged']
        
        if len(data) < 5:
            return None, 0
            
        X = data[['Sadao_Lagged']]
        y = data['HatYai']
        
        model = LinearRegression()
        model.fit(X, y)
        
        self._cached_model = model
        self._cached_model_lag = best_lag
        self._cached_model_time = now
        
        return model, best_lag

    def predict_next_hours(self, hours=3):
        model, lag = self.train_prediction_model()
        
        if model is None:
            return []
        
        predictions = []
        current_time = datetime.now()
        
        df = self.get_latest_data(hours=lag+hours+5)
        if df.empty:
            return []
            
        df_sadao = df[df['station_id'] == 'Sadao'].set_index('timestamp')[['level']].resample('1h').mean().interpolate()
        
        for h in range(1, hours + 1):
            future_time = current_time + timedelta(hours=h)
            target_sadao_time = future_time - timedelta(hours=lag)
            
            try:
                idx = df_sadao.index.get_indexer([target_sadao_time], method='nearest')[0]
                sadao_val = df_sadao.iloc[idx]['level']
                pred_level = model.predict([[sadao_val]])[0]
                predictions.append({"time": future_time, "level": pred_level})
            except Exception:
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
