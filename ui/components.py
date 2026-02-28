
import streamlit as st
from constants import STATION_METADATA
from utils import icon_b64

def render_sidebar(t, predictor):
    """Render the sidebar with modern styling, language toggle and refresh button."""
    with st.sidebar:
        # Branding header with logo
        _logo = icon_b64('logo.png')
        if _logo:
            _brand = (
                '<div style="text-align:center;padding:8px 0 16px;border-bottom:1px solid #e2e8f0;margin-bottom:16px;">'
                f'<img src="{_logo}" style="width:56px;height:56px;border-radius:50%;margin-bottom:6px;">'
                '<div style="font-size:1.2rem;font-weight:900;color:#0f172a;letter-spacing:-0.5px;">HYFI</div>'
                '<div style="display:inline-block;font-size:0.62rem;font-weight:600;color:#64748b;background:#eff6ff;border:1px solid #bfdbfe;padding:2px 10px;border-radius:999px;margin-top:4px;">INTELLIGENCE v2.0</div>'
                '</div>'
            )
        else:
            _brand = (
                '<div style="text-align:center;padding:8px 0 16px;border-bottom:1px solid #e2e8f0;margin-bottom:16px;">'
                '<div style="font-size:1.4rem;font-weight:900;color:#0f172a;">HYFI</div>'
                '<div style="display:inline-block;font-size:0.62rem;font-weight:600;color:#64748b;background:#eff6ff;border:1px solid #bfdbfe;padding:2px 10px;border-radius:999px;margin-top:4px;">INTELLIGENCE v2.0</div>'
                '</div>'
            )
        st.markdown(_brand, unsafe_allow_html=True)

        lang_choice = st.radio("Language / ภาษา", ["ไทย", "English"],
                               index=0 if st.session_state.lang == "TH" else 1,
                               horizontal=True)
        st.session_state.lang = "EN" if lang_choice == "English" else "TH"
        
        st.divider()
        if st.button(t["refresh_btn"], use_container_width=True, type="primary"):
            st.cache_data.clear()
            st.rerun()

        with st.expander(f"⚙ {t['settings']}"):
            line_token = st.text_input(t["token_label"], type="password")
            if st.button(t["test_btn"]):
                if line_token:
                    predictor._send_line_notify(t["test_msg"], line_token)
                    st.success(t["sent"])
                else:
                    st.error(t["no_token"])
        
        st.markdown("---")
        st.markdown(f"#### {t['guide_title']}")
        st.markdown(t["guide_text"])

def render_action_banner(risk_pct, lang_key):
    """Render the contextual action banner based on risk percentage."""
    _evac_icon = icon_b64('evacuation.png')
    _warn_icon = icon_b64('warning_alert.png')
    
    if risk_pct >= 70:
        _ab_cls = 'critical'
        _icon = f'<img src="{_evac_icon}" style="width:24px;height:24px;">' if _evac_icon else ''
        _ab_msg = 'วิกฤต — ย้ายรถขึ้นที่สูง, ยกของขึ้นที่สูง, ตัดไฟชั้นล่าง พิจารณาอพยพ!' if lang_key == 'th' else 'CRITICAL — Move vehicles to high ground, elevate belongings, cut ground-floor power.'
    elif risk_pct >= 30:
        _ab_cls = 'watch'
        _icon = f'<img src="{_warn_icon}" style="width:24px;height:24px;">' if _warn_icon else ''
        _ab_msg = 'เฝ้าระวัง — ติดตามระดับน้ำ, เช็คท่อระบายน้ำ, เตรียมแบตสำรอง/น้ำมัน' if lang_key == 'th' else 'WATCH — Monitor water levels, check drainage, prepare batteries/fuel'
    else:
        _ab_cls = 'normal'
        _icon = ''
        _ab_msg = 'สถานการณ์ปกติ — ไม่ต้องดำเนินการ' if lang_key == 'th' else 'Normal conditions — no action required'
    
    st.markdown(f'<div class="action-banner {_ab_cls}">{_icon} {_ab_msg}</div>', unsafe_allow_html=True)

def render_qa_strip(qa_result, lang_key):
    """Render the QA warning strip as a modern pill if data quality is degraded."""
    qa_status = qa_result.get('overall_status', 'ok')
    if qa_status != 'ok':
        from models.qa import qa_summary_text
        qa_msg = qa_summary_text(qa_result, lang_key)
        if qa_status == 'degraded':
            st.markdown(f'<div class="qa-pill" style="margin-bottom:8px;">⚠ {qa_msg}</div>', unsafe_allow_html=True)
        else:
            st.markdown(
                f'<div class="qa-pill" style="background:#fee2e2;color:#991b1b;border-color:#fecaca;margin-bottom:8px;">⚠ {qa_msg}</div>',
                unsafe_allow_html=True
            )

def render_zombie_warning(zombie_report, lang_key):
    """Render warning if zombie data is detected."""
    if zombie_report:
        for station, info in zombie_report.items():
            if station == '_scraper':
                continue
            zombie_val = info.get('zombie_value', '?')
            reason = info.get('reason', 'Unknown')
            if lang_key == "th":
                st.error(
                    f"**ตรวจพบข้อมูลผี (Zombie Data)** — สถานี **{station}** "
                    f"ส่งค่า **{zombie_val}m** แต่เซนเซอร์มีปัญหา: _{reason}_\n\n"
                    f"→ ระบบ **ละเว้นค่านี้** และใช้ข้อมูลสำรองแทน"
                )
            else:
                st.error(
                    f"**Zombie Data Detected** — Station **{station}** "
                    f"reports **{zombie_val}m** but sensor is suspect: _{reason}_\n\n"
                    f"→ System **ignored this value** and used fallback."
                )

def render_inline_qa_badges(qa_result):
    """Render compact inline QA badges for each station."""
    from models.qa import qa_badge
    
    qa_stations = qa_result.get('stations', {})
    badge_parts = []
    
    for sname, sqa in qa_stations.items():
        badge = qa_badge(sqa['flags'])
        badge_parts.append(f"{badge} {sname} ({sqa['confidence']}%)")
    
    if badge_parts:
        st.caption("QA: " + "  ·  ".join(badge_parts))
