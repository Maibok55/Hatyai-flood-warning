import streamlit as st
import plotly.graph_objects as go
import folium
from streamlit_folium import st_folium
import requests
from datetime import datetime
from models.flood_predictor import FloodPredictor, clean_value, get_bangkok_time
from models.ingest import read_provenance
from models.qa import compute_qa_flags, qa_badge
from constants import EMERGENCY_CONTACTS, EVACUATION_ZONES, STATION_METADATA
from hatyai_scraper import scrape_hatyai_climate, check_zombie_data
from utils import fmt, dot, icon_b64, CRITICAL_LEVEL, WARNING_LEVEL
from ui.components import render_sidebar, render_action_banner, render_qa_strip, render_zombie_warning
from ui import render_hero, render_pipeline, render_footer, render_inline_qa_badges

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
# 2. TRANSLATIONS — loaded from locales/{en,th}.json
# =============================================================
import json as _json
import os as _os

_LOCALE_DIR = _os.path.join(_os.path.dirname(__file__), "locales")

@st.cache_data
def _load_translations():
    out = {}
    for code, filename in [("EN", "en.json"), ("TH", "th.json")]:
        path = _os.path.join(_LOCALE_DIR, filename)
        try:
            with open(path, "r", encoding="utf-8") as f:
                out[code] = _json.load(f)
        except Exception as e:
            st.error(f"Locale load error ({filename}): {e}")
            out[code] = {}
    return out

TRANSLATIONS = _load_translations()

# =============================================================
# 3. CSS INJECTION — loaded from static/style.css
# =============================================================
_CSS_PATH = _os.path.join(_os.path.dirname(__file__), "static", "style.css")

def _css_hash():
    """Return file mod time as cache buster."""
    try:
        return str(_os.path.getmtime(_CSS_PATH))
    except Exception:
        return "0"

@st.cache_data
def _load_css(_hash):
    try:
        with open(_CSS_PATH, "r", encoding="utf-8") as f:
            return f"<style>{f.read()}</style>"
    except Exception:
        return ""

_font_fix = """
<style>
@import url('https://fonts.googleapis.com/icon?family=Material+Icons|Material+Icons+Outlined|Material+Icons+Round|Material+Icons+Sharp|Material+Icons+Two+Tone');
@import url('https://fonts.googleapis.com/css2?family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200&display=swap');

/* Aggressively hide icon text if font fails to load completely */
[data-testid="stIconMaterial"], 
[data-testid="stExpanderToggleIcon"],
.stIcon {
    color: transparent !important;
}
</style>
"""
st.markdown(_load_css(_css_hash()) + _font_fix, unsafe_allow_html=True)

# =============================================================
# 4. INITIALIZATION
# =============================================================
# Removed cache_resource to ensure latest code is used
# @st.cache_resource
def get_predictor():
    return FloodPredictor()

predictor = get_predictor()

@st.dialog("ℹ️ เกี่ยวกับระบบนี้ (About HYFI Intelligence)")
def show_about_dialog(lang_key):
    # Depending on language, show either Thai or English. The user provided exhaustive Thai docs.
    if lang_key == 'th':
        st.markdown("""
**ยินดีต้อนรับสู่ HYFI Intelligence ระบบวิเคราะห์ความเสี่ยงน้ำท่วมอัจฉริยะสำหรับพื้นที่หาดใหญ่**

**📡 1. ระบบนี้ทำงานอย่างไร?**
ระบบของเราประเมินความเสี่ยงโดยผสานข้อมูลหลายแหล่งเข้าด้วยกัน (Hybrid Intelligence) เพื่อความแม่นยำสูงสุด:
- **ข้อมูลจริงจากพื้นที่:** ดึงข้อมูลระดับน้ำแบบเรียลไทม์จากสถานีวัดน้ำ (X.44, X.90, X.173)
- **ข้อมูลพยากรณ์ล่วงหน้า:** คาดการณ์ปริมาณฝนสะสมล่วงหน้า 3 วัน โดยอ้างอิงจาก Open-Meteo API
- **ระบบสำรองอัตโนมัติ (Virtual Mode):** หากเซนเซอร์วัดระดับน้ำในพื้นที่ขัดข้อง ระบบจะสลับไปใช้ข้อมูลปริมาณฝนเพื่อประเมินความเสี่ยงแทนทันที
- **การประเมินทิศทางน้ำ:** มีการคำนวณความเร็วกระแสน้ำและลักษณะความคดเคี้ยวของคลองอู่ตะเภา เพื่อกะเวลาที่มวลน้ำจะเดินทางมาถึง (ETA) ได้อย่างใกล้เคียงความเป็นจริง

**📍 2. สถานีเฝ้าระวังหลัก**
- **ต้นน้ำ (อ.สะเดา):** สถานี X.173 - ด่านหน้าคอยรับมวลน้ำจากทางทิศใต้
- **กลางน้ำ (บ้านบางศาลา):** สถานี X.90 - จุดยุทธศาสตร์สำคัญในการเตือนภัยก่อนมวลน้ำเข้าสู่ตัวเมือง
- **ปลายน้ำ (เทศบาลนครหาดใหญ่):** สถานี X.44 - เขตพื้นที่เศรษฐกิจและใจกลางเมือง

**🚦 3. การอ่านค่าหน้าปัดความเสี่ยง**
- 🟢 **0-30% (ปกติ):** สถานการณ์ปลอดภัย การระบายน้ำทำได้ดี
- 🟡 **31-70% (เฝ้าระวัง):** ฝนเริ่มตกสะสม ควรเริ่มติดตามข่าวสารอย่างใกล้ชิด
- 🔴 **71-100% (วิกฤต):** เสี่ยงน้ำท่วมสูง ควรเตรียมพร้อมรับมือหรือพิจารณาอพยพ

**🚰 4. เกณฑ์ระดับน้ำ (สำหรับเฝ้าระวัง)**
- 🟢 **ปกติ:** ต่ำกว่า 5.90 ม. รทก.
- ⚠️ **เฝ้าระวัง:** 5.90 – 7.40 ม. รทก. (น้ำเริ่มใกล้ตลิ่ง)
- 🚨 **วิกฤต:** ตั้งแต่ 7.40 ม. รทก. ขึ้นไป (น้ำล้นตลิ่ง)

**✅ 5. ข้อแนะนำในการเตรียมรับมือ**
- **สถานะสีเขียว:** ติดตามพยากรณ์อากาศและตรวจสอบไม่ให้มีขยะอุดตันท่อระบายน้ำรอบบ้าน
- **สถานะสีเหลือง:** ขนย้ายสิ่งของขึ้นที่สูง เตรียมแบตเตอรี่สำรอง ไฟฉาย และเช็กสภาพรถยนต์
- **สถานะสีแดง:** นำรถไปจอดในพื้นที่สูง (เช่น ตึกฟักทอง ม.อ.) สับคัตเอาต์ตัดไฟชั้นล่าง และเตรียมตัวอพยพ

**🆘 6. ฟีเจอร์ช่วยเหลือยามฉุกเฉิน**
- **โหมดวิกฤต (Critical Mode):** ระบบจะแสดงเบอร์โทรติดต่อฉุกเฉินของหน่วยงานในหาดใหญ่ พร้อมแนะนำเส้นทางอพยพโดยอัตโนมัติ
- **กะเวลาน้ำมาถึง (Real-time ETA):** ช่วยประเมินระยะเวลาที่มวลน้ำจะเดินทางมาถึงพื้นที่เป้าหมาย
- **เทียบสถิติในอดีต:** นำสถานการณ์ปัจจุบันไปเทียบกับข้อมูลเหตุการณ์น้ำท่วมใหญ่ (เช่น ปี 2553) เพื่อให้เห็นภาพความรุนแรงได้ชัดเจนขึ้น

⚠️ **หมายเหตุ:** ข้อมูลในระบบนี้มาจากการวิเคราะห์ทางสถิติและแบบจำลองทางอุทกวิทยา โปรดใช้เพื่อประกอบการตัดสินใจควบคู่กับการติดตามประกาศเตือนภัยจากหน่วยงานราชการ

💻 *พัฒนาโดย Mongkhonphat*
        """)
    else:
        # Fallback to English using the existing dictionary or a simplified version
        st.markdown("""
**Welcome to HYFI Intelligence — Intelligent Flood Risk Analysis System for Hatyai**

**📡 1. How does it work?**
Our system uses Hybrid Intelligence to evaluate risks:
- Live Local Sensors (X.44, X.90, X.173)
- 3-day Rainfall Forecasts (Open-Meteo)
- Virtual Flow modeling if sensors fail.

**📍 2. Monitoring Stations**
- Upstream: Sadao (X.173)
- Midstream: Bang Sala (X.90)
- Downstream: Hatyai City (X.44)

**🚦 3. Interpreting the Gauge**
- 🟢 0-30% (Normal): Safe operations.
- 🟡 31-70% (Watch): Rising water, stay alert.
- 🔴 71-100% (Critical): High risk, consider evacuation.

**🚰 4. Water Thresholds (Station X.44)**
- 🟢 Normal: < 5.90 m MSL
- ⚠️ Watch: 5.90 – 7.40 m MSL
- 🚨 Critical: ≥ 7.40 m MSL

⚠️ **Note:** Driven by statistical modeling and hydraulics. Follow official announcements.

💻 *Developed by Mongkhonphat*
        """)

# =============================================================
# 5. MAIN APP
# =============================================================
def main():
    if 'lang' not in st.session_state:
        st.session_state.lang = "TH"
    
    lang_key = st.session_state.lang.lower()

    # --- SIDEBAR ---
    # T update handled by state change, main rerun picks it up at top
    t = TRANSLATIONS[st.session_state.lang]
    render_sidebar(t, predictor)

    # --- DATA FETCH (cached 10 min to avoid redundant API calls) ---
    @st.cache_data(ttl=600, show_spinner=False)
    def _fetch_sensor():
        return predictor.fetch_and_store_data()
    
    @st.cache_data(ttl=600, show_spinner=False)
    def _fetch_rain():
        return predictor.fetch_rain_forecast()
    
    with st.spinner("กำลังโหลดข้อมูล..." if st.session_state.lang == "TH" else "Loading data..."):
        sensor_data = _fetch_sensor()
        rain_data = _fetch_rain()
    
    # --- HYBRID INTELLIGENCE: Zombie Data Detection ---
    @st.cache_data(ttl=600, show_spinner=False)
    def _fetch_local_intel():
        return scrape_hatyai_climate()
    
    local_intel = _fetch_local_intel()
    zombie_report = {}
    
    if local_intel.get('success') and local_intel.get('outage_stations'):
        sensor_data, zombie_report = check_zombie_data(sensor_data, local_intel)
    
    # === FAILSAFE: Detect total data loss ===
    _no_sensor = sensor_data.get('level') is None and not sensor_data.get('all_data')
    _no_rain = rain_data.get('rain_sum_3d', 0) == 0 and not rain_data.get('raw_daily')
    if _no_sensor and _no_rain:
        st.error(
            "🚫 **" + ("ไม่สามารถเชื่อมต่อแหล่งข้อมูลใดได้" if st.session_state.lang == 'TH'
            else "All data sources unavailable") + "**\n\n" +
            ("ระบบไม่สามารถแสดงความเสี่ยงที่แม่นยำได้ กรุณาตรวจสอบประกาศจากเทศบาลนครหาดใหญ่โดยตรง"
            if st.session_state.lang == 'TH'
            else "System cannot display accurate risk. Please check Hatyai Municipality announcements directly.")
        )
    
    risk_report = predictor.analyze_flood_risk(sensor_data, rain_data)
    
    latest_df = predictor.get_latest_data(hours=24)
    roc = predictor.calculate_rate_of_change()
    preds = predictor.predict_next_hours(3)
    
    # QA/QC flags
    qa_result = compute_qa_flags(sensor_data, roc, sensor_data.get('timestamp'))
    
    # Timezone handling with proper Bangkok time
    last_update = sensor_data.get("timestamp") or get_bangkok_time()
    last_update_str = last_update.strftime('%d/%m/%Y %H:%M')

    # === HEADER — Centered Title (matching user's mockup) ===
    source_display = risk_report['data_source']
    _logo = icon_b64('logo.png')
    # Logo size 2.5x via CSS class
    _logo_img = f'<img src="{_logo}" class="hero-logo-massive">' if _logo else ''
    _header_html = (
        '<div style="position:relative;text-align:center;margin-bottom:20px;padding-bottom:12px;border-bottom:4px solid #60a5fa;">'
        '<div style="position:absolute;top:0;right:0;text-align:right;font-size:0.82rem;color:#64748b;line-height:1.7;">'
        f'<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:#22c55e;margin-right:5px;animation:pulse-dot 2s ease-in-out infinite;"></span> <b style="color:#1a1a2e;">LIVE</b><br>'
        f'{t["last_update"]}: <b style="color:#1a1a2e;">{last_update_str}</b><br>'
        f'{t["source"]}: {source_display}'
        '</div>'
        '<div style="display:inline-flex;align-items:center;gap:30px;justify-content:center;">'
        f'{_logo_img}'
        '<div style="text-align:left;">'
        # Title 2.5x larger (104px), Subtitle 2x larger (35px) via CSS classes
        f'<div class="hero-title-massive">{t["title"]}</div>'
        f'<div class="hero-subtitle-massive">{t["subtitle"]}</div>'
        '</div></div></div>'
    )
    st.markdown(_header_html, unsafe_allow_html=True)

    # === ABOUT MODAL MENU BUTTON ===
    bt1, bt2, bt3 = st.columns([1, 2, 1])
    with bt2:
        btn_label = "ℹ️ เกี่ยวกับระบบนี้" if lang_key == 'th' else "ℹ️ About This System"
        if st.button(btn_label, use_container_width=True):
            show_about_dialog(lang_key)


    # === DISCLAIMER — right under title ===
    _disc = t.get('disclaimer', '')
    if _disc:
        st.markdown(
            f'<div style="background:#fefce8;border:1px solid #fde047;border-radius:10px;padding:12px 18px;margin-bottom:16px;font-size:0.82rem;color:#854d0e;line-height:1.7;">{_disc}</div>',
            unsafe_allow_html=True
        )

    if sensor_data['is_fallback']:
        st.warning(f"⚠️ Sensor data unavailable. Using **{source_display}** ({risk_report['confidence_score']}%)")
    
    # --- QA STATUS STRIP ---
    render_qa_strip(qa_result, lang_key)
    
    # QA badges inline (compact)
    render_inline_qa_badges(qa_result)

    # --- ACTION BANNER (always visible, risk-appropriate) ---
    risk_pct = risk_report.get('primary_risk', 0)

    # --- ZOMBIE DATA WARNING ---
    render_zombie_warning(zombie_report, lang_key)

    # ==========================================================
    # SECTION 1: HERO — Risk Gauge + ETA + Situation Report
    # ==========================================================
    render_hero(risk_report, lang_key, t)

    # ==========================================================
    # EMERGENCY RESPONSE SECTION (Critical Mode)
    # ==========================================================
    if risk_report['alert_level'] == 'CRITICAL':
        st.markdown("---")
        st.markdown("### 🆘 EMERGENCY RESPONSE ACTIVATED")
        
        # Emergency alert banner
        _emerg_html = (
            '<div class="fade-in" style="background:linear-gradient(135deg,#ef4444,#b91c1c);'
            'color:white;padding:24px;border-radius:16px;margin-bottom:20px;text-align:center;'
            'box-shadow:0 8px 32px rgba(239,68,68,0.25);">'
            '<h2 style="margin:0;color:white;font-size:1.6rem;font-weight:800;letter-spacing:-0.3px;">🚨 CRITICAL FLOOD WARNING 🚨</h2>'
            f'<p style="margin:10px 0 0 0;font-size:1rem;opacity:0.85;font-weight:500;">Immediate action required. Risk Level: {risk_report["primary_risk"]}%</p>'
            '</div>'
        )
        st.markdown(_emerg_html, unsafe_allow_html=True)
        
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
                    <div class="emergency-card">
                        <div style="font-weight:600;color:#0f172a;font-size:0.9rem;">{service}</div>
                        <div style="font-size:1.2rem;color:#ef4444;font-weight:800;letter-spacing:-0.3px;">{number}</div>
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
    st.markdown('<div style="margin-top: 32px;"></div>', unsafe_allow_html=True)
    st.markdown(
        f'<div class="fade-in"><span class="section-header">📋 {t["checklist_title"]}</span></div>',
        unsafe_allow_html=True
    )
    
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
    eta = risk_report.get('eta', {})
    render_pipeline(sensor_data, eta, t, lang_key, roc)

    # ==========================================================
    # SECTION 3: METRIC CARDS (Overview — no duplicate station data)
    # ==========================================================
    st.markdown('<div style="margin-top: 24px;"></div>', unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)

    with c1:
        st.metric(
            label=f"🌧️ {t['rain_card']}", 
            value=f"{risk_report['rain_sum']} mm",
            help=t['rain_unit']
        )

    with c2:
        # Rate of Change for HatYai (primary monitoring station)
        hy_roc = roc.get('HatYai', 0)
        roc_label = "📈 อัตราเปลี่ยนแปลง" if lang_key == 'th' else "📈 Rate of Change"
        roc_color = '#ef4444' if hy_roc > 0 else '#22c55e'
        _roc_sub = 'หาดใหญ่ (X.44)' if lang_key == 'th' else 'HatYai Station (X.44)'
        _roc_html = (
            '<div class="info-card fade-in fade-in-delay-1">'
            f'<div style="font-weight:600;font-size:0.72rem;color:#64748b;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:6px;">{roc_label}</div>'
            f'<div style="font-weight:800;font-size:1.8rem;color:{roc_color};line-height:1.3;letter-spacing:-0.5px;">{hy_roc:+.2f} <span style="font-size:0.85rem;color:#94a3b8;font-weight:500;">m/h</span></div>'
            f'<div style="font-size:0.72rem;color:#94a3b8;font-weight:500;margin-top:4px;">{_roc_sub}</div>'
            '</div>'
        )
        # 1. Load Custom CSS
        st.markdown(_roc_html, unsafe_allow_html=True)

    with c3:
        # ETA — Time for flood water to reach HatYai
        eta_hours = eta.get('eta_hours', 0)
        eta_label_key = eta.get('eta_label', '--')
        eta_title = "⏱️ เวลาน้ำถึง" if lang_key == 'th' else "⏱️ ETA to HatYai"
        sadao_rising = eta.get('sadao_rising', False)
        if sadao_rising or eta.get('bank_full_ratio', 0) > 0.7:
            eta_bg = 'linear-gradient(135deg, #fef2f2, #fee2e2)' if eta_hours < 6 else 'linear-gradient(135deg, #eff6ff, #dbeafe)'
            eta_border = '#fecaca' if eta_hours < 6 else '#bfdbfe'
            eta_val = eta_label_key
        else:
            eta_bg = 'linear-gradient(135deg, #f0fdf4, #dcfce7)'
            eta_border = '#bbf7d0'
            eta_val = 'ปกติ' if lang_key == 'th' else 'Normal'
        
        _eta_sub = 'จาก อ.สะเดา → หาดใหญ่' if lang_key == 'th' else 'Sadao → HatYai'
        _eta_html = (
            f'<div class="fade-in fade-in-delay-2" style="background:{eta_bg};border:1px solid {eta_border};border-radius:14px;padding:16px 20px;transition:all 0.25s cubic-bezier(.4,0,.2,1);">'
            f'<div style="font-weight:600;font-size:0.72rem;color:#64748b;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:6px;">{eta_title}</div>'
            f'<div style="font-weight:800;font-size:1.8rem;color:#0f172a;line-height:1.3;letter-spacing:-0.5px;">{eta_val}</div>'
            f'<div style="font-size:0.72rem;color:#94a3b8;font-weight:500;margin-top:4px;">{_eta_sub}</div>'
            '</div>'
        )
        st.markdown(_eta_html, unsafe_allow_html=True)

    # ==========================================================
    # SECTION 4: OUTLOOK & RAIN RADAR
    # ==========================================================
    st.markdown('<div style="margin-top: 32px;"></div>', unsafe_allow_html=True)
    
    col_out, col_map = st.columns(2)
    
    outlook = risk_report.get('outlook', {})
    with col_out:
        st.markdown(
            f'<div class="fade-in"><span class="section-header">📅 {t["outlook_title"]}</span></div>',
            unsafe_allow_html=True
        )
        
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
    
    with col_map:
        st.markdown(
            f'<div class="fade-in"><span class="section-header">📡 เรดาร์กลุ่มฝน (Rain Radar)</span></div>',
            unsafe_allow_html=True
        )
        
        @st.cache_data(ttl=600)
        def fetch_rainviewer_data():
            try:
                resp = requests.get("https://api.rainviewer.com/public/weather-maps.json", timeout=5)
                if resp.status_code == 200:
                    return resp.json()
            except Exception:
                pass
            return None
        
        rv_data = fetch_rainviewer_data()
        
        if rv_data and 'radar' in rv_data and 'past' in rv_data['radar']:
            # Combine past and nowcast frames
            frames = rv_data['radar'].get('past', []) + rv_data['radar'].get('nowcast', [])
            if frames:
                # Build dict for slider: formatted time string -> timestamp details
                import pytz
                bkk_tz = pytz.timezone('Asia/Bangkok')
                
                frame_options = {}
                for f in frames:
                    ts = f['time']
                    dt = datetime.fromtimestamp(ts, tz=bkk_tz)
                    label = dt.strftime("%H:%M")
                    frame_options[label] = f
                
                labels = list(frame_options.keys())
                
                # Default to the 'now' frame or the last past frame
                default_idx = len(rv_data['radar'].get('past', [])) - 1
                if default_idx < 0: default_idx = len(labels) - 1
                default_label = labels[default_idx] if labels else None
                
                selected_label = st.select_slider(
                    "📅 เลือกเวลา (เวลาไทย):",
                    options=labels,
                    value=default_label
                )
                
                selected_frame = frame_options[selected_label]
                path = selected_frame['path'] # e.g. /v2/radar/1614777000
                
                # Create Folium Map
                # Center on Songkhla (Lat: 7.0048, Lon: 100.4730)
                m = folium.Map(location=[7.0048, 100.4730], zoom_start=9, max_zoom=18)
                
                # Add RainViewer TileLayer
                tile_url = f"https://tilecache.rainviewer.com{path}/256/{{z}}/{{x}}/{{y}}/2/1_1.png"
                folium.TileLayer(
                    tiles=tile_url,
                    attr="RainViewer",
                    name="Rain Radar",
                    overlay=True,
                    control=True,
                    opacity=0.7,
                    max_native_zoom=13,
                    maxNativeZoom=13,
                    max_zoom=18,
                    maxZoom=18
                ).add_to(m)
                
                folium.LayerControl().add_to(m)
                
                # Render using streamlit_folium
                st_folium(m, height=450, use_container_width=True, returned_objects=[])
                
                # Radar Color Legend
                st.markdown("""
                <div style="display: flex; justify-content: center; gap: 15px; font-size: 14px; margin-top: 10px;">
                    <div style="display: flex; align-items: center; gap: 5px;"><span style="width: 15px; height: 15px; background-color: #87CEFA; border-radius: 3px; display: inline-block;"></span> ฝนเล็กน้อย</div>
                    <div style="display: flex; align-items: center; gap: 5px;"><span style="width: 15px; height: 15px; background-color: #32CD32; border-radius: 3px; display: inline-block;"></span> ฝนปานกลาง</div>
                    <div style="display: flex; align-items: center; gap: 5px;"><span style="width: 15px; height: 15px; background-color: #FFD700; border-radius: 3px; display: inline-block;"></span> ฝนตกหนัก</div>
                    <div style="display: flex; align-items: center; gap: 5px;"><span style="width: 15px; height: 15px; background-color: #FF4500; border-radius: 3px; display: inline-block;"></span> ฝนรุนแรง</div>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.warning("ไม่พบข้อมูลเรดาร์ (No radar frames available)")
        else:
            st.error("ไม่สามารถโหลดข้อมูล RainViewer ได้ (Failed to fetch radar data)")

    # ==========================================================
    # SECTION 5: CHARTS
    # ==========================================================
    
    # 5A — RAIN INTENSITY (24h)
    hourly_rain = rain_data.get("hourly_rain", [])
    hourly_times = rain_data.get("hourly_times", [])
    if hourly_rain and hourly_times:
        st.markdown(
            f'<div class="fade-in"><span class="section-header">🌧️ {t["chart_rain_hourly"]}</span></div>',
            unsafe_allow_html=True
        )
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
        st.markdown(
            f'<div class="fade-in"><span class="section-header">📈 {t["chart_water"]}</span></div>',
            unsafe_allow_html=True
        )
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
        
        # Forecast line removed as requested

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
    # SECTION: HYBRID INTELLIGENCE (Local News + Sensor Health)
    # ==========================================================
    st.markdown("---")
    
    section_title = "🌐 ข่าวสารและสถานะจากศูนย์หาดใหญ่" if st.session_state.lang == "TH" else "🌐 Local Intelligence (HatyaiCityClimate)"
    st.markdown(
        f'<div class="fade-in"><span class="section-header">{section_title}</span></div>',
        unsafe_allow_html=True
    )
    
    if not local_intel.get('success'):
        err = local_intel.get('error', 'Unknown')
        st.warning(f"⚠️ ไม่สามารถเชื่อมต่อ hatyaicityclimate.org ได้: {err}")
    else:
        col_news, col_health = st.columns([3, 2], gap="large")
        
        with col_news:
            news_title = "📢 ประกาศล่าสุด" if st.session_state.lang == "TH" else "📢 Latest Announcements"
            st.markdown(f"#### {news_title}")
            
            news_items = local_intel.get('news', [])
            if news_items:
                for i, news in enumerate(news_items[:5]):
                    is_alert = news.get('is_alert', False)
                    icon = "🚨" if is_alert else "📰"
                    border_color = "#ef4444" if is_alert else "#2563eb"
                    
                    st.markdown(
                        f"""
                        <a href="{news['link']}" target="_blank" style="text-decoration:none;">
                            <div class="news-item" style="border-left:4px solid {border_color};">
                                <span style="color:#0f172a;font-size:0.9rem;font-weight:500;">
                                    {icon} {news['title']}
                                </span>
                            </div>
                        </a>
                        """,
                        unsafe_allow_html=True
                    )
            else:
                no_news = "✅ ยังไม่มีประกาศเตือนภัยใหม่" if st.session_state.lang == "TH" else "✅ No new alerts"
                st.success(no_news)
        
        with col_health:
            health_title = "🛠️ สถานะเซนเซอร์" if st.session_state.lang == "TH" else "🛠️ Sensor Health"
            st.markdown(f"#### {health_title}")
            
            station_health = local_intel.get('station_health', {})
            for station, status in station_health.items():
                if status == "online":
                    icon = "🟢"
                    color = "#22c55e"
                    label = "ปกติ" if st.session_state.lang == "TH" else "Online"
                else:
                    icon = "🔴"
                    color = "#ef4444"
                    label = "ขัดข้อง" if st.session_state.lang == "TH" else "Outage"
                
                detail = local_intel.get('outage_details', {}).get(station, '')
                
                health_bg = 'offline' if status != 'online' else 'online'
                st.markdown(
                    f"""
                    <div class="info-card" style="
                        padding:10px 16px;
                        margin-bottom:6px;
                        display:flex;
                        justify-content:space-between;
                        align-items:center;
                    ">
                        <span style="font-weight:600;color:#0f172a;font-size:0.9rem;">{icon} {station}</span>
                        <span class="health-badge {health_bg}">{label}</span>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
                if detail and status != "online":
                    st.caption(f"📋 {detail[:80]}")
            
            # Camera count
            cam_count = len(local_intel.get('cameras', []))
            if cam_count > 0:
                cam_label = f"📷 กล้อง CCTV ที่ตรวจพบ: **{cam_count} จุด**" if st.session_state.lang == "TH" else f"📷 CCTV cameras detected: **{cam_count} feeds**"
                st.markdown(f"\n{cam_label}")
        
        # Source attribution
        st.caption(
            f"ℹ️ ข้อมูลจาก [hatyaicityclimate.org]({local_intel.get('source_url', 'https://www.hatyaicityclimate.org')}) "
            f"• ดึงเมื่อ {local_intel.get('scrape_time', datetime.now()).strftime('%H:%M')}"
            if st.session_state.lang == "TH" else
            f"ℹ️ Source: [hatyaicityclimate.org]({local_intel.get('source_url', 'https://www.hatyaicityclimate.org')}) "
            f"• Fetched at {local_intel.get('scrape_time', datetime.now()).strftime('%H:%M')}"
        )

    # ==========================================================
    # DATA PROVENANCE & SENSOR METADATA (Transparency)
    # ==========================================================
    st.markdown("---")
    
    prov_col, meta_col = st.columns(2)
    
    with prov_col:
        with st.expander("📊 แหล่งข้อมูล (Data Provenance)", expanded=False):
            prov = read_provenance()
            if prov:
                for src, info in prov.items():
                    status_icon = "🟢" if info.get('status') == 'ok' else ('🔵' if info.get('status') == 'cached' else '🔴')
                    st.markdown(
                        f"**{status_icon} {src.upper()}**\n"
                        f"- Endpoint: `{info.get('endpoint', '?')}`\n"
                        f"- Station IDs: `{info.get('station_ids', [])}`\n"
                        f"- Fetched: `{info.get('fetched_utc', '?')}` UTC\n"
                        f"- Status: `{info.get('status', '?')}`\n"
                        f"- Fingerprint: `{info.get('fingerprint', '-')}`"
                    )
            else:
                st.info("ยังไม่มีข้อมูล provenance — จะปรากฏหลังดึงข้อมูลครั้งแรก")
    
    with meta_col:
        with st.expander("🔧 ข้อมูลเซ็นเซอร์ (Sensor Metadata)", expanded=False):
            meta_rows = []
            for name, meta in STATION_METADATA.items():
                meta_rows.append({
                    "Station": name,
                    "ID": meta.get('id'),
                    "Lat": meta.get('lat'),
                    "Lon": meta.get('lon'),
                    "Datum": "MSL",
                    "Ground (m)": meta.get('ground_level'),
                    "Bank (m)": meta.get('bank_full_capacity'),
                    "Warning (m)": meta.get('warning_threshold'),
                    "Critical (m)": meta.get('critical_threshold'),
                })
            import pandas as _pd
            st.dataframe(_pd.DataFrame(meta_rows), use_container_width=True, hide_index=True)
            st.caption(
                "Datum: ทุกค่าอ้างอิง MSL (Mean Sea Level) จาก ThaiWater API\n\n"
                "Bank = min_bank (ระดับตลิ่งต่ำสุด), Warning = bank − 1.5m"
            )

    # ==========================================================
    # FOOTER
    # ==========================================================
    render_footer(t, lang_key)

if __name__ == "__main__":
    main()