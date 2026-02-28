import streamlit as st
import pandas as pd
from datetime import datetime
import pytz
from models.flood_predictor import clean_value, get_bangkok_time
from constants import STATION_METADATA
from utils import fmt, dot, CRITICAL_LEVEL, WARNING_LEVEL

def get_station_info(station_name, msl_value, bank_info):
    """Convert MSL to depth + bank distance using official RID/ONWR thresholds."""
    meta = STATION_METADATA.get(station_name, {})
    ground = meta.get('ground_level', 0)
    bank = meta.get('bank_full_capacity', 0)
    
    if msl_value is not None:
        depth = round(msl_value - ground, 2)
        left_to_bank = round(bank - msl_value, 2)
        is_overtopping = msl_value > bank
        return {'depth': depth, 'left_to_bank': abs(left_to_bank), 'msl': msl_value, 'overtopping': is_overtopping}
    return {'depth': None, 'left_to_bank': None, 'msl': None, 'overtopping': False}


def _status_class(val, station_key):
    """Return CSS class suffix based on sensor value."""
    if val is None:
        return "gray"
    meta = STATION_METADATA.get(station_key, {})
    crit = meta.get('critical_threshold', CRITICAL_LEVEL)
    warn = meta.get('warning_threshold', WARNING_LEVEL)
    if val > crit:
        return "red"
    if val > warn:
        return "yellow"
    return "green"


def _render_card(col, name, info, color_dot, station_key, t, last_update_ts=None, roc=None, delay_idx=0):
    with col:
        val = info['msl']
        depth = info['depth']
        ltb = info['left_to_bank']
        delta = roc.get(station_key, 0.0) if roc else 0.0
        status = _status_class(val, station_key)
        
        # Bank text
        bank_color = '#64748b'
        bank_text = ''
        
        if val is not None and ltb is not None:
            if info['overtopping']:
                bank_text = f"น้ำสูงกว่าตลิ่ง {ltb:.1f} ม." if "น้ำ" in t['subtitle'] else f"Water {ltb:.1f}m above bank"
                bank_color = '#ef4444'
            else:
                bank_text = f"อีก {ltb:.1f} ม. ถึงระดับตลิ่ง" if "น้ำ" in t['subtitle'] else f"{ltb:.1f}m to bank level"
                bank_color = '#22c55e' if ltb > 3 else ('#eab308' if ltb > 1 else '#ef4444')
        
        # Value color
        val_color = "#0f172a"
        if val is not None:
            meta = STATION_METADATA.get(station_key, {})
            crit = meta.get('critical_threshold', CRITICAL_LEVEL)
            warn = meta.get('warning_threshold', WARNING_LEVEL)
            if val > crit:
                val_color = "#ef4444"
            elif val > warn:
                val_color = "#eab308"

        # Timestamp age
        age_text = ""
        if last_update_ts:
            if last_update_ts.tzinfo is None:
                last_update_ts = pytz.timezone('Asia/Bangkok').localize(last_update_ts)
            now = get_bangkok_time()
            diff = abs((now - last_update_ts).total_seconds() / 60)
            if diff < 2:
                age_text = "เพิ่งอัปเดต" if "น้ำ" in t['subtitle'] else "Just now"
            elif diff < 60:
                age_text = f"{int(diff)} นาทีที่แล้ว" if "น้ำ" in t['subtitle'] else f"{int(diff)} min ago"
            else:
                age_text = f"{int(diff/60)} ชม.ก่อน" if "น้ำ" in t['subtitle'] else f"{int(diff/60)}h ago"
        
        delta_color = '#ef4444' if delta > 0 else '#22c55e'
        delta_html = f'<div style="font-size:0.82rem;color:{delta_color};font-weight:600;margin-top:2px;">{delta:+.2f} m/h</div>' if delta != 0 else ""

        depth_display = f'{depth:.1f}' if depth is not None else '—'

        _html = (
            f'<div class="station-card status-{status} fade-in fade-in-delay-{delay_idx}" style="margin-bottom:24px;">'
            f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">'
            f'<div style="font-weight:700;font-size:0.92rem;color:#0f172a;letter-spacing:-0.2px;" title="{name}">{color_dot} {name}</div>'
            f'<div style="font-size:0.65rem;color:#94a3b8;display:flex;align-items:center;gap:4px;">⏱ {age_text}</div>'
            f'</div>'
            f'<div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:2px;">'
            f'<div><span style="font-size:2.4rem;font-weight:800;color:{val_color};line-height:1;">{depth_display}</span> <span style="font-size:0.85rem;color:#64748b;font-weight:500;">m</span></div>'
            f'{delta_html}'
            f'</div>'
            f'<div style="font-size:0.75rem;color:{bank_color};font-weight:600;margin-top:6px;">{bank_text}</div>'
            f'</div>'
        )
        st.markdown(_html, unsafe_allow_html=True)


def render_pipeline(sensor_data, eta, t, lang_key, roc=None):
    """
    Renders the Station Pipeline (Sadao -> Bang Sala -> Hat Yai) with modern cards.
    """
    pipeline_title = t['pipeline_title']
    warning_text = " • แจ้งเตือนล่วงหน้า 15-20 ชม." if lang_key == "th" else " • 15-20 hrs advance warning"
    st.markdown(
        f'<div class="fade-in" style="margin-bottom: 20px;">'
        f'<span class="section-header">{pipeline_title}</span>'
        f'<span style="font-size: 0.95rem; color: #ef4444; font-weight: 600; margin-left: 8px;">{warning_text}</span>'
        f'</div>',
        unsafe_allow_html=True
    )
    all_data = sensor_data.get("all_data", {})
    bank_info = sensor_data.get("bank_info", {})
    timestamp = sensor_data.get("timestamp")
    
    sadao_v = clean_value(all_data.get("Sadao"))
    hatyai_v = clean_value(all_data.get("HatYai"))
    kalla_v = clean_value(all_data.get("Kallayanamit"))
    
    def get_info(name, val):
        return get_station_info(name, val, bank_info)

    sadao_info = get_info('Sadao', sadao_v)
    hatyai_info = get_info('HatYai', hatyai_v)
    kalla_info = get_info('Kallayanamit', kalla_v)
    
    # Flow layout: Card → Arrow → Card → Arrow → Card
    c1, a1, c2, a2, c3 = st.columns([5, 1, 5, 1, 5])
    
    _render_card(c1, t['sadao_unit'], sadao_info, dot(sadao_v, 'Sadao'), 'Sadao', t, timestamp, roc, delay_idx=1)
    
    with a1:
        st.markdown(
            '<div class="flow-arrow" style="height:100%;min-height:120px;display:flex;align-items:center;justify-content:center;">'
            '<span style="font-size:1.6rem;color:#cbd5e1;">→</span></div>',
            unsafe_allow_html=True
        )
    
    _render_card(c2, "Bang Sala (X.90)", kalla_info, dot(kalla_v, 'Kallayanamit'), 'Kallayanamit', t, timestamp, roc, delay_idx=2)
    
    with a2:
        st.markdown(
            '<div class="flow-arrow" style="height:100%;min-height:120px;display:flex;align-items:center;justify-content:center;">'
            '<span style="font-size:1.6rem;color:#cbd5e1;">→</span></div>',
            unsafe_allow_html=True
        )
    
    _render_card(c3, t['hatyai_unit'], hatyai_info, dot(hatyai_v, 'HatYai'), 'HatYai', t, timestamp, roc, delay_idx=3)
