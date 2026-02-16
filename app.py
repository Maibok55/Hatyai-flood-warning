import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
from models.flood_predictor import FloodPredictor, clean_value, get_bangkok_time
from constants import EMERGENCY_CONTACTS, EVACUATION_ZONES, STATION_METADATA

# =============================================================
# 1. PAGE CONFIG
# =============================================================
st.set_page_config(
    page_title="HYFI — Intelligent Flood Monitoring",
    page_icon="🌊",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# =============================================================
# 2. TRANSLATIONS (Enhanced with Emergency Messages)
# =============================================================
TRANSLATIONS = {
    "EN": {
        "title": "HYFI Intelligence",
        "subtitle": "Real-time Crisis Monitoring • U-Tapao Basin",
        "last_update": "Last Updated",
        "refresh_btn": "Refresh Data",
        "settings": "Settings",
        "token_label": "Line Notify Token",
        "test_btn": "Test Alert",
        "test_msg": "🔔 Test Alert from HYFI",
        "sent": "Alert Sent",
        "no_token": "Token Required",
        "guide_title": "Instructions",
        "guide_text": """
**How to use:**
1. **Line Notify**: Get your token from [notify-bot.line.me](https://notify-bot.line.me/).
2. **Thresholds**:
   - 🟢 Normal: < 9.0 m
   - ⚠️ Warning: 9.0 - 10.5 m
   - 🚨 Critical: > 10.5 m
        """,
        "risk_title": "Risk Assessment",
        "confidence": "Confidence",
        "source": "Source",
        "checklist_title": "Recommended Actions",
        "eta_title": "Estimated Travel Time",
        "eta_from": "Sadao → Hatyai City",
        "eta_speed": "Flow Velocity",
        "eta_conf": "Est. Accuracy",
        "outlook_title": "3-Day Forecast",
        "trend": "Trend",
        "peak_day": "Peak Interval",
        "history_title": "Historical Context",
        "rain_card": "Rain Accumulation",
        "rain_unit": "3-Day Total",
        "hatyai_card": "Hatyai Level",
        "hatyai_unit": "Station X.44 • Economic Zone Watch",
        "sadao_card": "Upstream Level",
        "sadao_unit": "Sadao (X.173) • Early warning 15-20 hrs",
        "forecast_card": "AI Prediction",
        "forecast_unit": "+3 Hour Model",
        "chart_water": "Water Level Analysis (24h)",
        "chart_rain_hourly": "Precipitation Intensity (Next 24h)",
        "pipeline_title": "Water Level (m)",
        "sensor_offline": "Offline",
        "processing": "Analyzing...",
        "about_title": "ℹ️ About This System",
        "about_text": """
**Welcome to HYFI**, an intelligent flood risk analysis system for the U-Tapao Canal Basin and Hatyai Municipality.

**📡 1. How the System Works**
HYFI utilizes **Hybrid Intelligence** to calculate flood risks:
- **Live Local Sensors**: Real-time water level data from Hatyai Municipality (X.44, X.90, X.173).
- **Global Rain Model**: 3-day accumulated rainfall forecasts from **Open-Meteo API**.
- **Automatic Virtual Mode**: If sensors fail, the system switches to use global rainfall data exclusively.
- **Advanced Hydraulic Logic**: River sinuosity factor and flow velocity calculations for accurate ETA.

**📍 2. Coverage Area**
- **Upstream (Sadao)**: Station X.173 - Monitoring water from the south.
- **Midstream (Bang Sala)**: Station X.44 - Strategic point for predicting urban inflow.
- **Downstream (Hatyai City)**: Station X.90 - Economic zone levels.

**🚦 3. Understanding the Risk Gauge**
- 🟢 **0-30% (Normal)**: Good weather. Drainage normal.
- 🟡 **31-70% (Watch)**: Rising accumulation. Monitor updates.
- 🔴 **71-100% (Critical)**: High flood risk. Immediate action recommended.

**✅ 4. Action Checklist**
- **Green**: Stay informed, check drains.
- **Yellow**: Move belongings up, check fuel/batteries.
- **Red**: Move vehicles to safe zones (e.g., PSU Pumpkin Bldg), cut ground-floor power.

**🆘 5. Emergency Response**
- **Critical Mode**: Automatic display of emergency contacts and evacuation routes.
- **Real-time ETA**: Advanced hydraulic calculations for water arrival time.
- **Historical Context**: Comparison with 2010 Great Flood benchmark.

**⚠️ Disclaimer & Privacy**
Data is based on statistical models and hydraulic principles. Please use as a guide alongside official municipal announcements.
*Developed by ICT Students, Faculty of Science, PSU.*
        """,
    },
    "TH": {
        "title": "HYFI Intelligence",
        "subtitle": "ระบบเฝ้าระวังวิกฤตการณ์น้ำ • ลุ่มน้ำคลองอู่ตะเภา",
        "last_update": "อัปเดตล่าสุด",
        "refresh_btn": "รีเฟรชข้อมูล",
        "settings": "ตั้งค่าการแจ้งเตือน",
        "token_label": "Line Notify Token",
        "test_btn": "ทดสอบระบบ",
        "test_msg": "🔔 ทดสอบการแจ้งเตือน HYFI",
        "sent": "ส่งข้อความแล้ว",
        "no_token": "กรุณาระบุ Token",
        "guide_title": "คู่มือการใช้งาน",
        "guide_text": """
**วิธีใช้งาน:**
1. **Line Notify**: ขอ Token ได้ที่ [notify-bot.line.me](https://notify-bot.line.me/)
2. **เกณฑ์ระดับน้ำ**:
   - 🟢 ปกติ: < 9.0 ม.
   - ⚠️ เฝ้าระวัง: 9.0 - 10.5 ม.
   - 🚨 วิกฤต: > 10.5 ม.
        """,
        "risk_title": "ประเมินความเสี่ยง",
        "confidence": "ความเชื่อมั่น",
        "source": "แหล่งข้อมูล",
        "checklist_title": "ข้อแนะนำการปฏิบัติ",
        "eta_title": "ระยะเวลาเดินทางของน้ำ (โดยประมาณ)",
        "eta_from": "อ.สะเดา → นครหาดใหญ่",
        "eta_speed": "ความเร็วกระแสน้ำ",
        "eta_conf": "ความแม่นยำ",
        "outlook_title": "แนวโน้ม 3 วันล่วงหน้า",
        "trend": "ทิศทาง",
        "peak_day": "ช่วงฝนสูงสุด",
        "history_title": "เปรียบเทียบเหตุการณ์ในอดีต",
        "rain_card": "ฝนสะสม",
        "rain_unit": "รวม 3 วัน",
        "hatyai_card": "ระดับน้ำหาดใหญ่",
        "hatyai_unit": "สถานี X.44 • จุดเฝ้าระวังเขตเมืองเศรษฐกิจ",
        "sadao_card": "ระดับน้ำต้นน้ำ",
        "sadao_unit": "อ.สะเดา (X.173) • แจ้งเตือนล่วงหน้า 15-20 ชม.",
        "forecast_card": "คาดการณ์",
        "forecast_unit": "+3 ชม.",
        "chart_water": "ระดับน้ำย้อนหลัง 24 ชม.",
        "chart_rain_hourly": "ความเข้มข้นฝนรายชั่วโมง (24 ชม.)",
        "pipeline_title": "ระดับน้ำในคลอง (ม.)",
        "sensor_offline": "ออฟไลน์",
        "processing": "กำลังวิเคราะห์...",
        "about_title": "ℹ️ เกี่ยวกับระบบนี้",
        "about_text": """
**ยินดีต้อนรับสู่ HYFI** ระบบวิเคราะห์ความเสี่ยงน้ำท่วมอัจฉริยะสำหรับหาดใหญ่

**📡 1. ระบบนี้ทำงานอย่างไร?**
เราใช้ **Hybrid Intelligence** ในการคำนวณความเสี่ยง:
- **ข้อมูลสดจากพื้นที่**: ระดับน้ำจริงจากสถานีเทศบาล (X.44, X.90, X.173)
- **ข้อมูลพยากรณ์โลก**: ปริมาณฝนสะสม 3 วันจาก **Open-Meteo API**
- **ระบบสำรองอัตโนมัติ (Virtual Mode)**: หากเซนเซอร์ล่ม ระบบจะใช้ข้อมูลฝนคำนวณแทนทันที
- **ตรรกะทางไฮดรอลิกขั้นสูง**: ปัจจัยความคดเคี้ยวของแม่น้ำและการคำนวณความเร็วกระแสน้ำสำหรับ ETA ที่แม่นยำ

**📍 2. พื้นที่การติดตาม**
- **ต้นน้ำ (อ.สะเดา)**: สถานี X.173 - ด่านหน้าทิศใต้
- **กลางน้ำ (บ้านบางศาลา)**: สถานี X.44 - จุดยุทธศาสตร์แจ้งเตือนเข้าเมือง
- **ปลายน้ำ (เทศบาลนครหาดใหญ่)**: สถานี X.90 - เขตเศรษฐกิจ

**🚦 3. การอ่านค่าหน้าปัดความเสี่ยง**
- 🟢 **0-30% (ปกติ)**: อากาศดี ระบายน้ำทัน
- 🟡 **31-70% (เฝ้าระวัง)**: ฝนเริ่มสะสมสูง ควรติดตามข่าว
- 🔴 **71-100% (วิกฤต)**: เสี่ยงน้ำท่วมสูง พิจารณาอพยพ/ย้ายรถ

**✅ 4. รายการที่ควรปฏิบัติ**
- **สีเขียว**: ติดตามข่าว, ดูท่อระบายน้ำ
- **สีเหลือง**: ยกของขึ้นที่สูง, เช็คระดับน้ำมัน/แบตสำรอง
- **สีแดง**: ย้ายรถไปที่สูง (เช่น ตึกฟักทอง), ตัดไฟชั้นล่าง

**🆘 5. การตอบสนองฉุกเฉิน**
- **โหมดวิกฤต**: แสดงข้อมูลติดต่อฉุกเฉินและเส้นทางอพยพอัตโนมัติ
- **ETA แบบเรียลไทม์**: การคำนวณทางไฮดรอลิกขั้นสูงสำหรับเวลาถึงของน้ำ
- **บริบททางประวัติศาสตร์**: เปรียบเทียบกับมาตรฐานมหาอุทกภัยปี 2010

**⚠️ หมายเหตุ**
ผลลัพธ์มาจากการคำนวณทางสถิติและหลักการทางไฮดรอลิก โปรดใช้ประกอบการตัดสินใจควบคู่กับประกาศทางการ
*พัฒนาโดย นักศึกษา ICT คณะวิทยาศาสตร์ ม.อ.*
        """,
    }
}

# =============================================================
# 3. CSS INJECTION (Non-intrusive, ID/Class-specific)
# =============================================================
CUSTOM_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=Prompt:wght@300;400;500;600;700&display=swap');

:root {
    --blue: #2563EB;
    --blue-light: #EFF6FF;
    --green: #22c55e;
    --yellow: #eab308;
    --red: #ef4444;
    --text: #1e293b;
    --muted: #64748b;
    --bg: #F8FAFC;
    --card: #FFFFFF;
    --border: #E2E8F0;
}

html, body, [class*="css"], .stApp {
    font-family: 'Inter', 'Prompt', sans-serif !important;
    color: var(--text);
}
.stApp { background-color: var(--bg) !important; }

/* Sidebar */
section[data-testid="stSidebar"] {
    background-color: white !important;
    border-right: 1px solid var(--border) !important;
}

/* Buttons */
.stButton > button {
    background-color: var(--blue) !important;
    color: white !important;
    border: none !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
    transition: all 0.2s ease !important;
}
.stButton > button:hover {
    background-color: #1d4ed8 !important;
    transform: translateY(-1px) !important;
    box-shadow: 0 4px 12px rgba(37,99,235,0.3) !important;
}

/* Expanders */
div[data-testid="stExpander"] details {
    border: 1px solid var(--border) !important;
    border-radius: 8px !important;
    background: white !important;
}

/* Headings */
h1 { color: var(--text) !important; font-weight: 800 !important; letter-spacing: -0.5px !important; }
h2, h3, h4 { color: #334155 !important; font-weight: 700 !important; }

/* Metric overrides */
div[data-testid="stMetric"] {
    background: white;
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 16px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04);
    transition: all 0.3s ease;
}
div[data-testid="stMetric"]:hover {
    transform: translateY(-3px);
    box-shadow: 0 8px 16px rgba(0,0,0,0.06);
}
div[data-testid="stMetric"] label { color: var(--muted) !important; font-weight: 600 !important; text-transform: uppercase !important; font-size: 0.78rem !important; letter-spacing: 0.05em !important; }
div[data-testid="stMetric"] div[data-testid="stMetricValue"] { font-weight: 700 !important; }
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# =============================================================
# 4. INITIALIZATION
# =============================================================
CRITICAL_LEVEL = 10.5
WARNING_LEVEL = 9.0

# Removed cache_resource to ensure latest code is used
# @st.cache_resource
def get_predictor():
    return FloodPredictor()

predictor = get_predictor()

def fmt(v):
    """Safe formatting for sensor values that may be None."""
    return f"{v:.2f}" if v is not None else "—"

def dot(v):
    """Status indicator dot for a sensor value."""
    if v is None: return "⚪"
    if v > CRITICAL_LEVEL: return "🔴"
    if v > WARNING_LEVEL: return "🟡"
    return "🟢"

# =============================================================
# 5. MAIN APP
# =============================================================
def main():
    if 'lang' not in st.session_state:
        st.session_state.lang = "TH"

    # --- SIDEBAR ---
    with st.sidebar:
        st.markdown("### 🌊 HYFI")
        lang_choice = st.radio("Language / ภาษา", ["ไทย", "English"],
                               index=0 if st.session_state.lang == "TH" else 1,
                               horizontal=True)
        st.session_state.lang = "EN" if lang_choice == "English" else "TH"
        t = TRANSLATIONS[st.session_state.lang]
        
        st.divider()
        if st.button(t["refresh_btn"], use_container_width=True, type="primary"):
            st.cache_data.clear()
            st.rerun()

        with st.expander(f"⚙️ {t['settings']}"):
            line_token = st.text_input(t["token_label"], type="password")
            if st.button(t["test_btn"]):
                if line_token:
                    predictor._send_line_notify(t["test_msg"], line_token)
                    st.success(t["sent"])
                else:
                    st.error(t["no_token"])

        st.markdown("---")
        st.markdown(f"#### 📖 {t['guide_title']}")
        st.markdown(t["guide_text"])

    # --- DATA FETCH (cached 5 min to avoid redundant API calls) ---
    @st.cache_data(ttl=300, show_spinner=False)
    def _fetch_sensor():
        return predictor.fetch_and_store_data()
    
    @st.cache_data(ttl=300, show_spinner=False)
    def _fetch_rain():
        return predictor.fetch_rain_forecast()
    
    with st.spinner("กำลังโหลดข้อมูล..." if st.session_state.lang == "TH" else "Loading data..."):
        sensor_data = _fetch_sensor()
        rain_data = _fetch_rain()
    
    risk_report = predictor.analyze_flood_risk(sensor_data, rain_data)
    
    latest_df = predictor.get_latest_data(hours=24)
    roc = predictor.calculate_rate_of_change()
    preds = predictor.predict_next_hours(3)
    
    # Timezone handling with proper Bangkok time
    last_update = sensor_data.get("timestamp") or get_bangkok_time()
    last_update_str = last_update.strftime('%d/%m/%Y %H:%M')

    # === HEADER ===
    st.markdown(f"# {t['title']}")
    # Clean up data source display (remove ID)
    source_display = risk_report['data_source']
    st.caption(f"{t['subtitle']} — {t['last_update']}: {last_update_str} | {t['source']}: {source_display}")

    if sensor_data['is_fallback']:
        st.warning(f"⚠️ Sensor data unavailable. Using **{source_display}** ({risk_report['confidence_score']}%)")

    # ==========================================================
    # SECTION 1: HERO — Risk Gauge + ETA + Situation Report
    # ==========================================================
    # Layout: Left (Gauge) wider : Right (Situation) narrower
    col_left, col_right = st.columns([4, 3], gap="large")

    # Localization Helper for this section
    lang_key = "th" if st.session_state.lang == "TH" else "en"
    
    with col_left:
        # 1. Gauge
        fig_gauge = go.Figure(go.Indicator(
            mode="gauge+number",
            value=risk_report['primary_risk'],
            number={'suffix': "%", 'font': {'size': 48, 'color': risk_report['color'], 'family': 'Inter'}},
            domain={'x': [0, 1], 'y': [0, 1]},
            gauge={
                'axis': {'range': [0, 100], 'tickwidth': 1, 'tickcolor': '#CBD5E1'},
                'bar': {'color': risk_report['color'], 'thickness': 0.2},
                'bgcolor': '#F8FAFC',
                'borderwidth': 0,
                'steps': [
                    {'range': [0, 30], 'color': '#DCFCE7'},
                    {'range': [30, 70], 'color': '#FEF9C3'},
                    {'range': [70, 100], 'color': '#FEE2E2'}
                ],
                'threshold': {
                    'line': {'color': risk_report['color'], 'width': 4},
                    'thickness': 0.8,
                    'value': risk_report['primary_risk']
                }
            }
        ))
        fig_gauge.update_layout(
            height=220, margin=dict(l=20, r=20, t=10, b=10),
            paper_bgcolor='rgba(0,0,0,0)', font={'color': '#1e293b'}
        )
        st.plotly_chart(fig_gauge, use_container_width=True)

        # 2. Alert Badge
        alert_color = risk_report['color']
        main_msg = risk_report.get(f"main_message_{lang_key}", risk_report['main_message_en'])
        
        st.markdown(
            f"<div style='background:{alert_color};padding:8px 12px;border-radius:8px;margin-bottom:12px;"
            f"color:white;font-weight:700;text-align:center;font-size:1rem;box-shadow: 0 2px 4px rgba(0,0,0,0.1);'>"
            f"{main_msg}</div>",
            unsafe_allow_html=True
        )

        # 3. ETA Card (Compact)
        eta = risk_report.get('eta', {})
        bg_eta = "#eff6ff"
        if eta.get('eta_hours', 20) < 6: bg_eta = "#fee2e2"
        
        st.markdown(
            f"""
            <div style="background:{bg_eta};padding:12px;border-radius:10px;border:1px solid #dae1e7;text-align:center;margin-top:8px;">
                <div style="display:flex;justify-content:space-between;align-items:center;">
                    <span style="color:#64748b;font-size:0.85rem;font-weight:600;">⏱️ {t['eta_title']}</span>
                    <span style="color:#1e293b;font-size:1.1rem;font-weight:800;">{eta.get('eta_label', '--')}</span>
                </div>
                <div style="font-size:0.75rem;color:#64748b;text-align:right;margin-top:2px;">
                    {t['eta_speed']}: <b>{eta.get('velocity_ms', 0.8)} m/s</b>
                </div>
            </div>
            """, 
            unsafe_allow_html=True
        )

    with col_right:
        # 4. Situation Report (New Component)
        summary = risk_report.get('summary_report', {})
        
        if not summary:
            st.info("🔄 Processing AI Summary...")
        else:
            # Data Preparation
            head = summary.get(f"headline_{lang_key}", "N/A")
            rain = summary.get(f"rain_context_{lang_key}", "N/A")
            upstream = summary.get(f"upstream_{lang_key}", "N/A")
            action = summary.get(f"action_{lang_key}", "N/A")
            
            title_txt = "📝 สรุปสถานการณ์น้ำภาพรวม" if lang_key == "th" else "📝 Situation Report"
            border_c = risk_report['color']
            
            st.markdown(
                f"""
                <div style="background:white;border-radius:12px;border:1px solid #e2e8f0;border-left:8px solid {border_c};padding:24px;height:100%;box-shadow: 0 1px 3px rgba(0,0,0,0.05);">
                    <h3 style="margin-top:0;font-size:1.25rem;font-weight:700;color:#1e293b;border-bottom:1px solid #f1f5f9;padding-bottom:12px;margin-bottom:16px;">
                        {title_txt}
                    </h3>
                    <div style="font-size:1.15rem;font-weight:700;color:{border_c};margin-bottom:20px;line-height:1.5;">
                        {head}
                    </div>
                    <ul style="list-style-type:none;padding:0;font-size:1.05rem;color:#334155;line-height:1.8;">
                        <li style="margin-bottom:12px;display:flex;align-items:start;">
                            <span style="margin-right:8px;">🌧️</span> <span>{rain}</span>
                        </li>
                        <li style="margin-bottom:8px;display:flex;align-items:start;">
                            <span style="margin-right:8px;">🌊</span> <span>{upstream}</span>
                        </li>
                        <li style="margin-bottom:0px;display:flex;align-items:start;background:#f8fafc;padding:8px;border-radius:6px;">
                            <span style="margin-right:8px;">⚡</span> <span style="font-weight:600;color:#0f172a;">{action}</span>
                        </li>
                    </ul>
                </div>
                """,
                unsafe_allow_html=True
            )
        
    st.markdown("---")

    # ==========================================================
    # EMERGENCY RESPONSE SECTION (Critical Mode)
    # ==========================================================
    if risk_report['alert_level'] == 'CRITICAL':
        st.markdown("---")
        st.markdown("### 🆘 EMERGENCY RESPONSE ACTIVATED")
        
        # Emergency alert banner
        st.markdown(
            f"""
            <div style="background:linear-gradient(135deg, #ff5252, #ff1744);color:white;padding:20px;border-radius:12px;margin-bottom:20px;text-align:center;box-shadow:0 4px 20px rgba(255,23,68,0.3);">
                <h2 style="margin:0;color:white;font-size:1.8rem;">🚨 CRITICAL FLOOD WARNING 🚨</h2>
                <p style="margin:10px 0 0 0;font-size:1.1rem;opacity:0.9;">Immediate action required. Risk Level: {risk_report['primary_risk']}%</p>
            </div>
            """, 
            unsafe_allow_html=True
        )
        
        # Emergency contacts and evacuation info
        col_emergency, col_evacuation = st.columns(2, gap="large")
        
        with col_emergency:
            st.markdown("#### 📞 Emergency Contacts")
            
            emergency_info = [
                ("🚨 Disaster Prevention", EMERGENCY_CONTACTS['disaster_prevention']),
                ("🏥 Hatyai Municipality", EMERGENCY_CONTACTS['hatyai_municipality']),
                ("💧 Water Resources", EMERGENCY_CONTACTS['water_resources']),
                ("🚑 Hospital Emergency", EMERGENCY_CONTACTS['hospital_emergency']),
                ("🛡️ PSU Security", EMERGENCY_CONTACTS['psu_security'])
            ]
            
            for service, number in emergency_info:
                st.markdown(
                    f"""
                    <div style="background:white;border:1px solid #e2e8f0;border-left:4px solid #ff5252;padding:12px;border-radius:8px;margin-bottom:8px;">
                        <div style="font-weight:600;color:#1e293b;">{service}</div>
                        <div style="font-size:1.2rem;color:#ff5252;font-weight:700;">{number}</div>
                    </div>
                    """, 
                    unsafe_allow_html=True
                )
        
        with col_evacuation:
            st.markdown("#### 🏃 Evacuation Zones")
            
            # High priority evacuation zones
            st.markdown(
                """
                <div style="background:#fee2e2;border:1px solid #fecaca;border-radius:8px;padding:15px;margin-bottom:15px;">
                    <h4 style="color:#dc2626;margin-top:0;">🔴 HIGH PRIORITY - Evacuate Immediately</h4>
                    <ul style="margin:10px 0;padding-left:20px;">
                """, 
                unsafe_allow_html=True
            )
            
            for zone in EVACUATION_ZONES['high_priority']:
                st.markdown(f"<li style='margin-bottom:5px;color:#7f1d1d;'>{zone}</li>", unsafe_allow_html=True)
            
            st.markdown("</ul></div>", unsafe_allow_html=True)
            
            # Safe zones
            st.markdown(
                """
                <div style="background:#dcfce7;border:1px solid #bbf7d0;border-radius:8px;padding:15px;">
                    <h4 style="color:#166534;margin-top:0;">🟢 SAFE ZONES</h4>
                    <ul style="margin:10px 0;padding-left:20px;">
                """, 
                unsafe_allow_html=True
            )
            
            for zone in EVACUATION_ZONES['safe_zones']:
                st.markdown(f"<li style='margin-bottom:5px;color:#166534;'>{zone}</li>", unsafe_allow_html=True)
            
            st.markdown("</ul></div>", unsafe_allow_html=True)
        
        st.markdown("---")

    # ==========================================================
    # SECTION 1.5: CHECKLIST (Full Width)
    # ==========================================================
    st.markdown(f"#### 📋 {t['checklist_title']}")
    
    # Localization logic for Checklist
    checklist_items = risk_report.get(f"action_checklist_{lang_key}", risk_report['action_checklist_en'])
    
    # Display as neat cards
    cols = st.columns(len(checklist_items))
    for idx, item in enumerate(checklist_items):
        with cols[idx % len(cols)]:
            st.info(f"**{item}**")

    # ==========================================================
    # SECTION 2: STATION PIPELINE
    # ==========================================================
    st.markdown(f"### 🔗 {t['pipeline_title']}")
    
    all_data = sensor_data.get("all_data", {})
    sadao_v = clean_value(all_data.get("Sadao"))
    hatyai_v = clean_value(all_data.get("HatYai"))
    kalla_v = clean_value(all_data.get("Kallayanamit"))
    eta_hrs = eta.get('eta_hours', 21)

    p1, a1, p2, a2, p3 = st.columns([2, 0.8, 2, 0.8, 2])
    
    # Helper for pipeline card
    def pipecard(col, name, code, val, color_dot):
        with col:
            # Put name INSIDE the label for card effect
            label = f"{color_dot} {name}"
            st.metric(label=label, value=f"{fmt(val)} m" if val is not None else t['sensor_offline'], help=code)

    pipecard(p1, "Sadao", t['sadao_unit'], sadao_v, dot(sadao_v))
    
    with a1:
        st.markdown(f"<div style='text-align:center;padding-top:28px;color:#cbd5e1;font-size:2rem;font-weight:800;'>➔</div>", unsafe_allow_html=True)
        # st.caption(f"~{int(eta_hrs * 0.4)}h") # Removed for cleaner look

    pipecard(p2, "Bang Sala", "Bang Sala (X.44)", kalla_v, dot(kalla_v))
    
    with a2:
        st.markdown(f"<div style='text-align:center;padding-top:28px;color:#cbd5e1;font-size:2rem;font-weight:800;'>➔</div>", unsafe_allow_html=True)

    pipecard(p3, "Hatyai", t['hatyai_unit'], hatyai_v, dot(hatyai_v))

    # ==========================================================
    # SECTION 3: METRIC CARDS
    # ==========================================================
    c1, c2, c3, c4 = st.columns(4)

    with c1:
        st.metric(
            label=f"🌧️ {t['rain_card']}", 
            value=f"{risk_report['rain_sum']} mm",
            help=t['rain_unit']
        )

    with c2:
        val = clean_value(sensor_data.get('level'))
        delta = roc.get(sensor_data.get('station_name'), 0)
        
        # Dynamic Color Logic
        val_color = "var(--text)"
        if val is not None:
            if val > CRITICAL_LEVEL: val_color = "#ef4444"
            elif val > WARNING_LEVEL: val_color = "#eab308"
            
        st.markdown(
            f"""
            <div style="background:white;border:1px solid #e2e8f0;border-radius:12px;padding:16px;box-shadow:0 1px 3px rgba(0,0,0,0.04);transition:all 0.3s ease;">
                <label style="color:#64748b;font-weight:600;text-transform:uppercase;font-size:0.78rem;letter-spacing:0.05em;" title="{t['hatyai_unit']}">
                    📍 {t['hatyai_card']}
                </label>
                <div style="color:{val_color};font-weight:700;font-size:1.8rem;line-height:1.4;">
                    {fmt(val)} <span style="font-size:1rem;color:#64748b;">m</span>
                </div>
                <div style="font-size:0.9rem;color:{'#ef4444' if delta > 0 else '#22c55e'};font-weight:500;">
                    {delta:+.2f} m/h
                </div>
            </div>
            """, 
            unsafe_allow_html=True
        )

    with c3:
        st.metric(
            label=f"🔼 {t['sadao_card']}",
            value=f"{fmt(sadao_v)} m" if sadao_v is not None else t['sensor_offline'],
            help=t['sadao_unit']
        )

    with c4:
        pred_val = f"{preds[-1]['level']:.2f} m" if preds else t['processing']
        # Fixed: standard font size via standard metric, but ensured label is translated
        st.metric(
            label=f"🔮 {t['forecast_card']}",
            value=pred_val,
            help=t['forecast_unit']
        )

    # ==========================================================
    # SECTION 4: OUTLOOK + HISTORY
    # ==========================================================
    col_out, col_hist = st.columns(2)
    
    outlook = risk_report.get('outlook', {})
    with col_out:
        st.markdown(f"#### 📅 {t['outlook_title']}")
        
        # Localized Trend
        trend_val = outlook.get(f'trend_{lang_key}', outlook.get('trend', 'N/A'))
        st.markdown(f"**{t['trend']}:** {trend_val}")
        
        # Localized Peak Day
        peak_day = outlook.get(f'max_rain_day_label_{lang_key}', '--')
        peak_val = outlook.get('max_rain_val', 0)
        st.markdown(f"**{t['peak_day']}:** {peak_day} ({peak_val} mm)")
        
        # Localized Summary
        summ_txt = outlook.get(f'summary_{lang_key}', 'Waiting...')
        st.info(f"💬 {summ_txt}")
        
        # Daily bars
        dv = outlook.get('daily_vals', [])
        dl = outlook.get(f'daily_labels_{lang_key}', [])
        if dv and dl:
            fig_daily = go.Figure(data=[
                go.Bar(
                    x=dl, y=dv,
                    marker_color=['#3b82f6', '#2563EB', '#1d4ed8'],
                    text=[f"{v:.1f}" for v in dv],
                    textposition='auto',
                    textfont=dict(color='white', size=13)
                )
            ])
            fig_daily.update_layout(
                height=160, margin=dict(l=0,r=0,t=5,b=20),
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                xaxis=dict(showgrid=False),
                yaxis=dict(showgrid=True, gridcolor='#e2e8f0', title="mm")
            )
            st.plotly_chart(fig_daily, use_container_width=True)
    
    with col_hist:
        history = risk_report.get('history', {})
        st.markdown(f"#### 📚 {t['history_title']}")
        st.markdown(history.get('message', 'No data.'))
        
        from models.flood_predictor import HISTORICAL_EVENTS
        current_rain = risk_report.get('rain_sum', 0)
        
        # Build comparison dataframe for Plotly
        years = []
        rains = []
        colors = []
        for year, evt in sorted(HISTORICAL_EVENTS.items()):
            years.append(str(year))
            rains.append(evt['rain_mm_3d'])
            # Color logic: Red for 2010, Blue for NOW
            if year == 2010: colors.append('#ef4444') # 2010 High Risk
            else: colors.append('#cbd5e1')
            
        years.append('NOW')
        rains.append(current_rain)
        colors.append('#22c55e') # Green for NOW (safe) or dynamic based on risk? Let's use Green for distinctness
        
        fig_hist = go.Figure(data=[
            go.Bar(x=years, y=rains, marker_color=colors,
                   text=[f"{v:.0f}" for v in rains], textposition='auto',
                   textfont=dict(size=11))
        ])
        fig_hist.update_layout(
            height=200, margin=dict(l=0,r=0,t=5,b=5),
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            xaxis=dict(showgrid=False),
            yaxis=dict(showgrid=True, gridcolor='#e2e8f0', title="mm")
        )
        st.plotly_chart(fig_hist, use_container_width=True)

    # ==========================================================
    # SECTION 5: CHARTS
    # ==========================================================
    
    # 5A — RAIN INTENSITY (24h)
    hourly_rain = rain_data.get("hourly_rain", [])
    hourly_times = rain_data.get("hourly_times", [])
    if hourly_rain and hourly_times:
        st.markdown(f"### 🌧️ {t['chart_rain_hourly']}")
        colors = []
        for v in hourly_rain:
            if v > 30: colors.append("#ef4444")
            elif v > 10: colors.append("#eab308")
            elif v > 2: colors.append("#3b82f6")
            else: colors.append("#93c5fd")
        
        fig_rain = go.Figure(go.Bar(
            x=hourly_times, y=hourly_rain,
            marker_color=colors,
            text=[f"{v:.1f}" if v > 0.5 else "" for v in hourly_rain],
            textposition='outside', textfont=dict(size=9, color='#64748b')
        ))
        
        # Thresholds
        fig_rain.add_hline(y=10, line_dash="dot", line_color="#cbd5e1")
        
        fig_rain.update_layout(
            height=280, margin=dict(l=20,r=20,t=10,b=30),
            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
            # Fixed Date format to prevent overlap (HH:MM)
            xaxis=dict(showgrid=False, tickformat="%H:%M", tickangle=-45, dtick=10800000), # 3 hours
            yaxis=dict(showgrid=True, gridcolor='#e2e8f0', title="mm/hr"),
            showlegend=False
        )
        st.plotly_chart(fig_rain, use_container_width=True)

    # 5B — WATER LEVEL TREND (24h)
    if not latest_df.empty:
        st.markdown(f"### 📈 {t['chart_water']}")
        fig_water = go.Figure()
        
        plot_df = latest_df[latest_df['level'] > -5.0]
        hatyai_plot = plot_df[plot_df['station_id'] == 'HatYai']
        sadao_plot = plot_df[plot_df['station_id'] == 'Sadao']

        # Danger zones
        fig_water.add_hrect(y0=CRITICAL_LEVEL, y1=20, fillcolor="rgba(239,68,68,0.05)", line_width=0)
        fig_water.add_hrect(y0=WARNING_LEVEL, y1=CRITICAL_LEVEL, fillcolor="rgba(234,179,8,0.05)", line_width=0)

        # Force modes line+markers for visibility
        fig_water.add_trace(go.Scatter(
            x=hatyai_plot['timestamp'], y=hatyai_plot['level'],
            name='Hat Yai', mode='lines+markers',
            line=dict(color='#2563EB', width=3),
            marker=dict(size=6),
            fill='tozeroy', fillcolor='rgba(37,99,235,0.05)'
        ))
        fig_water.add_trace(go.Scatter(
            x=sadao_plot['timestamp'], y=sadao_plot['level'],
            name='Sadao', mode='lines+markers',
            line=dict(color='#06b6d4', width=2, dash='dot'),
            marker=dict(size=5)
        ))
        
        # Forecast line
        val = clean_value(sensor_data.get('level'))
        if preds and val is not None:
            p_times = [last_update] + [p['time'] for p in preds]
            p_levels = [val] + [p['level'] for p in preds]
            fig_water.add_trace(go.Scatter(
                x=p_times, y=p_levels,
                name='Forecast', mode='lines+markers',
                line=dict(color='#ec4899', width=2, dash='dash'),
                marker=dict(size=5, symbol='diamond')
            ))

        # Threshold lines
        fig_water.add_hline(y=WARNING_LEVEL, line_dash="solid", line_color="#eab308", line_width=1,
                           annotation_text="Warning", annotation_font_color="#a16207")
        fig_water.add_hline(y=CRITICAL_LEVEL, line_dash="solid", line_color="#ef4444", line_width=1,
                           annotation_text="Critical", annotation_font_color="#dc2626")
        
        fig_water.update_layout(
            height=350, margin=dict(l=0,r=0,t=10,b=0),
            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
            hovermode="x unified",
            xaxis=dict(showgrid=False, tickformat="%H:%M\n%d/%m"),
            yaxis=dict(showgrid=True, gridcolor='#e2e8f0'),
            legend=dict(orientation="h", y=1.08, font=dict(color='#1e293b'))
        )
        st.plotly_chart(fig_water, use_container_width=True)

    # ==========================================================
    # FOOTER
    # ==========================================================
    st.markdown("---")
    with st.expander(t["about_title"]):
        st.markdown(t["about_text"])

if __name__ == "__main__":
    main()
