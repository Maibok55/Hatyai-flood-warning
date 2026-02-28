import streamlit as st
import plotly.graph_objects as go
from utils import icon_b64

def render_hero(risk_report, lang_key, t):
    """Hero Section matching user's mockup: Gauge left, Situation bullets right."""
    
    # Status line above columns
    risk_val = risk_report['primary_risk']
    risk_color = risk_report['color']
    main_msg = risk_report.get(f"main_message_{lang_key}", risk_report['main_message_en'])
    
    # Determine status dot color
    if risk_val >= 70:
        dot_color = '#ef4444'
    elif risk_val >= 30:
        dot_color = '#eab308'
    else:
        dot_color = '#22c55e'
    
    # Status line: "สถานการณ์ล่าสุด: date" + green dot + summary
    last_ts = risk_report.get('sensor_timestamp', '')
    summary_report = risk_report.get('summary_report', {})
    headline = summary_report.get(f'headline_{lang_key}', summary_report.get('headline_en', ''))
    
    _status_label = 'สถานการณ์ล่าสุด:' if lang_key == 'th' else 'Latest status:'
    _summary_label = 'สรุปโดยรวม' if lang_key == 'th' else 'Summary'
    
    _status_html = (
        f'<div style="margin-bottom:16px;font-size:0.85rem;color:{dot_color};font-weight:500;">'
        f'{_status_label} {last_ts}'
        f'</div>'
        f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:20px;">'
        f'<span style="display:inline-block;width:12px;height:12px;border-radius:50%;background:{dot_color};"></span>'
        f'<span style="font-size:0.88rem;color:var(--text-sub);font-weight:500;">{_summary_label}: {headline}</span>'
        f'</div>'
    )
    st.markdown(_status_html, unsafe_allow_html=True)
    
    # Two columns: Gauge left, Situation Report right
    col_left, col_right = st.columns([5, 5], gap="large")

    with col_left:
        # Gauge title
        _flood_icon = icon_b64('flood_monitoring.png')
        gauge_title = "ความเสี่ยงภาพรวม" if lang_key == 'th' else "Overall Risk"
        _icon_img = f'<img src="{_flood_icon}" style="width:22px;height:22px;vertical-align:middle;margin-right:6px;">' if _flood_icon else ''
        st.markdown(
            f'<div style="text-align:center;margin-bottom:-10px;font-size:0.85rem;color:#64748b;font-weight:500;">'
            f'{_icon_img}{gauge_title}</div>',
            unsafe_allow_html=True
        )
        
        # Gauge chart
        fig_gauge = go.Figure(go.Indicator(
            mode="gauge+number",
            value=risk_val,
            number={'suffix': "%", 'font': {'size': 44, 'color': risk_color, 'family': 'Inter', 'weight': 700}},
            domain={'x': [0, 1], 'y': [0, 1]},
            gauge={
                'axis': {'range': [0, 100], 'tickwidth': 1, 'tickcolor': '#e5e7eb', 'tickfont': {'size': 9, 'color': '#94a3b8'}},
                'bar': {'color': risk_color, 'thickness': 0.2},
                'bgcolor': '#f9fafb',
                'borderwidth': 0,
                'steps': [
                    {'range': [0, 30],  'color': '#f0fdf4'},
                    {'range': [30, 70], 'color': '#fefce8'},
                    {'range': [70, 100],'color': '#fef2f2'}
                ],
                'threshold': {'line': {'color': risk_color, 'width': 3}, 'thickness': 0.8, 'value': risk_val}
            }
        ))
        fig_gauge.update_layout(
            height=200, margin=dict(l=16, r=16, t=8, b=8),
            paper_bgcolor='rgba(0,0,0,0)', font={'family': 'Inter'}
        )
        st.plotly_chart(fig_gauge, use_container_width=True)

        # Status label under gauge
        if risk_val >= 70:
            status_text = 'วิกฤต: ดำเนินการทันที' if lang_key == 'th' else 'Critical: Take action now'
            status_bg = '#fef2f2'; status_color = '#991b1b'; status_border = '#fecaca'
        elif risk_val >= 30:
            status_text = 'เฝ้าระวัง: ติดตามสถานการณ์' if lang_key == 'th' else 'Watch: Monitor situation'
            status_bg = '#fefce8'; status_color = '#854d0e'; status_border = '#fde047'
        else:
            status_text = 'ปกติ: สถานการณ์ทั่วไป' if lang_key == 'th' else 'Normal: General conditions'
            status_bg = '#f0fdf4'; status_color = '#166534'; status_border = '#86efac'
        
        st.markdown(
            f'<div style="background:{status_bg};color:{status_color};border:1px solid {status_border};'
            f'border-radius:10px;padding:8px 16px;text-align:center;font-size:0.82rem;font-weight:600;">'
            f'{status_text}</div>',
            unsafe_allow_html=True
        )

        # ETA card
        eta = risk_report.get('eta', {})
        vel = eta.get('velocity_ms', 0)
        sadao_rising = eta.get('sadao_rising', False)
        if sadao_rising or eta.get('bank_full_ratio', 0) > 0.7:
            eta_display = eta.get('eta_label', '--')
        else:
            eta_display = "ปกติ" if lang_key == 'th' else "Normal"
        
        _eta_title = 'ระยะเวลาเดินทางของน้ำ (โดยประมาณ)' if lang_key == 'th' else 'Estimated Travel Time'
        _flow_label = 'กระแสน้ำ' if lang_key == 'th' else 'Flow'
        st.markdown(
            f'<div style="background:white;border:1px solid #e5e7eb;border-radius:12px;padding:14px 18px;margin-top:12px;">'
            f'<div style="display:flex;justify-content:space-between;align-items:center;">'
            f'<span style="color:#64748b;font-size:0.82rem;font-weight:500;">⏱ {_eta_title}</span>'
            f'<span style="color:#1a1a2e;font-size:1rem;font-weight:700;">{eta_display}</span>'
            f'</div>'
            f'<div style="font-size:0.75rem;color:#94a3b8;margin-top:4px;">{_flow_label}: {vel} m/s</div>'
            f'</div>',
            unsafe_allow_html=True
        )

    with col_right:
        # Huge blue header like user requested (~2.5x larger), using CSS class to avoid Streamlit inline strippers
        _title = "ภาพรวมสถานการณ์น้ำ" if lang_key == "th" else "Flood Situation Overview"
        st.markdown(f'<div class="overview-header-massive">{_title}</div>', unsafe_allow_html=True)
        
        summary = risk_report.get('summary_report', {})
        if not summary:
            st.info("Processing...")
        else:
            rain = summary.get(f"rain_context_{lang_key}", "N/A")
            upstream = summary.get(f"upstream_{lang_key}", "N/A")
            action = summary.get(f"action_{lang_key}", "N/A")
            
            # Clean bullet list, scaled up to 1.4rem as user requested with generous spacing
            _head = summary.get(f"headline_{lang_key}", "")
            _items = [
                f'<b>{_head}</b>',
                rain,
                upstream,
                action,
            ]
            _list_html = '<ul style="margin:0;padding-left:20px;font-size:1.4rem;line-height:2.2;color:#334155;">'
            for item in _items:
                if item:
                    _list_html += f'<li style="margin-bottom:12px;">{item}</li>'
            _list_html += '</ul>'
            
            st.markdown(
                f'<div style="background:white;border:1px solid #e5e7eb;border-radius:16px;padding:24px;">'
                f'{_list_html}</div>',
                unsafe_allow_html=True
            )
