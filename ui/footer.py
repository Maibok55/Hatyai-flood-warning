import streamlit as st

def render_footer(t, lang_key):
    """Renders a professional multi-column footer."""
    
    # Professional footer
    quick_links_title = "ลิงก์ด่วน" if lang_key == 'th' else "Quick Links"
    data_sources_title = "แหล่งข้อมูลภายนอก" if lang_key == 'th' else "External Data Sources"
    contact_title = "ช่องทางติดต่อช่วยเหลือฉุกเฉิน" if lang_key == 'th' else "Emergency Contact"
    about_title = "เกี่ยวกับระบบ" if lang_key == 'th' else "About"
    
    _footer_html = (
        '<div class="hyfi-footer">'
        '<div style="display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:28px;">'
        # Column 1: About
        f'<div>'
        f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:14px;">'
        f'<span style="font-size:1.5rem;">🌊</span>'
        f'<div><div style="color:white;font-weight:800;font-size:1rem;">HYFI</div>'
        f'<div style="font-size:0.68rem;color:#64748b;">Intelligence v2.0</div></div></div>'
        f'<div style="font-size:0.78rem;line-height:1.7;color:#94a3b8;">'
        + (
            'ระบบเฝ้าระวังและคาดการณ์น้ำท่วมอัจฉริยะ '
            'สำหรับพื้นที่ลุ่มน้ำคลองอู่ตะเภา อ.หาดใหญ่'
        if lang_key == 'th' else
            'Intelligent flood monitoring & prediction system '
            'for U-Tapao Canal basin, Hat Yai district'
        ) +
        '</div></div>'
        # Column 2: Quick Links
        f'<div><h4>{quick_links_title}</h4>'
        f'<div style="font-size:0.78rem;line-height:2;">'
        f'<a href="https://www.ثnationalflood.go.th" target="_blank">NDWC</a><br>'
        f'<a href="https://www.rid.go.th" target="_blank">RID (กรมชลประทาน)</a><br>'
        f'<a href="https://www.tmd.go.th" target="_blank">TMD (กรมอุตุนิยมวิทยา)</a><br>'
        f'<a href="https://hatyaicityclimate.org" target="_blank">HatyaiCityClimate</a>'
        f'</div></div>'
        # Column 3: Data Sources
        f'<div><h4>{data_sources_title}</h4>'
        f'<div style="font-size:0.78rem;line-height:2;color:#94a3b8;">'
        + (
            'กรมอุตุนิยมวิทยา (TMD)<br>'
            'กรมชลประทาน (RID)<br>'
            'สำนักงานทรัพยากรน้ำแห่งชาติ (ONWR)<br>'
            'กรุงเทพมหานคร'
        if lang_key == 'th' else
            'Thai Meteorological Dept. (TMD)<br>'
            'Royal Irrigation Dept. (RID)<br>'
            'Office of Natl. Water Resources (ONWR)<br>'
            'Bangkok Metropolitan Admin.'
        ) +
        '</div></div>'
        # Column 4: Contact
        f'<div><h4>{contact_title}</h4>'
        f'<div style="font-size:0.78rem;line-height:2;color:#94a3b8;">'
        + (
            '📞 เทศบาลนครหาดใหญ่: 074-200-000<br>'
            '🚑 กู้ภัยท่งเซียเซี่ยงตึ๊ง: 074-350-955<br>'
            '🪖 ศูนย์บรรเทาสาธารณภัย มทบ.42 (ค่ายเสนาณรงค์): 098-223-3364<br>'
            '⚡ แจ้งตัดไฟ (PEA): 1129<br>'
            '🚨 ปภ. (ส่วนกลาง): 1784<br>'
            '🏥 เจ็บป่วยฉุกเฉิน: 1669'
        if lang_key == 'th' else
            '📞 Hatyai Municipality: 074-200-000<br>'
            '🚑 Tongzia Searn-Tung Rescue: 074-350-955<br>'
            '🪖 Disaster Relief Center (Camp Senanarong): 098-223-3364<br>'
            '⚡ Power Outage (PEA): 1129<br>'
            '🚨 Dept of Disaster Prevention (NDWC): 1784<br>'
            '🏥 Emergency Medical: 1669'
        ) +
        '</div></div>'
        '</div>'  # close grid
        '<div class="footer-divider"></div>'
        '<div class="footer-bottom">'
        f'© 2025 HYFI Intelligence | Built with Streamlit'
        '</div></div>'
    )
    st.markdown(_footer_html, unsafe_allow_html=True)
