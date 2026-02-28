import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests
from bs4 import BeautifulSoup
import time
import numpy as np
from datetime import datetime, timedelta

# ---------------------------------------------------------
# 1. Page Config (Must be first)
# ---------------------------------------------------------
st.set_page_config(
    page_title="Hat Yai Flood Watcher",
    page_icon="🌊",
    layout="wide"
)

# ---------------------------------------------------------
# 2. Thresholds & Constants
# ---------------------------------------------------------
CRITICAL_LEVEL = 10.5
WARNING_LEVEL = 9.0

# ---------------------------------------------------------
# 3. Backend: Data Fetching with Cache
# ---------------------------------------------------------
@st.cache_data(ttl=300)
def fetch_water_data():
    """
    ดึงข้อมูลระดับน้ำจากกรมชลประทาน (สถานีหาดใหญ่ใน P.1)
    Cache ไว้ 5 นาที (300 วินาที)
    """
    url = "http://119.110.213.190/rid/stations.php?IdCode=08:STN04"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = 'utf-8'
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            rows = soup.find_all('tr')
            
            for row in rows:
                if "ระดับน้ำ" in row.text:
                    cols = row.find_all('td')
                    if len(cols) > 1:
                        # สมมติ format คือ " X.XX " -> float
                        text_val = cols[1].text.strip().replace(',', '')
                        try:
                            return float(text_val)
                        except ValueError:
                            pass
        return None
    except Exception:
        return None

def get_status(level):
    if level is None:
        return "Not Available", "gray"
    if level > CRITICAL_LEVEL:
        return "วิกฤต (ล้นตลิ่ง) 🚨", "#ff5252" # Red
    elif level > WARNING_LEVEL:
        return "เฝ้าระวัง ⚠️", "#fb8c00" # Orange
    else:
        return "ปกติ 🟢", "#4caf50" # Green

# ---------------------------------------------------------
# 4. Mock Data Generation
# ---------------------------------------------------------
def get_initial_mock_data():
    """สร้างข้อมูลจำลองย้อนหลัง 24 ชม. (รันครั้งแรกครั้งเดียว)"""
    now = datetime.now()
    times = [now - timedelta(hours=i) for i in range(24)]
    times.reverse() 
    values = np.random.uniform(8.5, 9.5, 24)
    return pd.DataFrame({"time": times, "level": values})

# ---------------------------------------------------------
# 5. Main Dashboard Logic
# ---------------------------------------------------------
def main():
    # --- Session State Initialization ---
    if 'history_data' not in st.session_state:
        st.session_state.history_data = get_initial_mock_data()
    
    if 'last_fetch_val' not in st.session_state:
        st.session_state.last_fetch_val = None

    # --- UI Header ---
    st.title("Hat Yai Flood Watcher 🌊")
    st.markdown(f"**สถานี:** บ้านหาดใหญ่ใน (P.1) | **อัปเดตล่าสุด:** {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")

    # ปุ่ม Refresh
    if st.button("🔄 Refresh ข้อมูลทันที"):
        st.cache_data.clear()
        st.rerun()

    # --- Fetch Data ---
    current_level = fetch_water_data()
    
    # Calculate Trend (Delta)
    delta_val = None
    if current_level is not None and st.session_state.last_fetch_val is not None:
        delta_val = current_level - st.session_state.last_fetch_val
        delta_val = round(delta_val, 2)
    
    # Update History & State
    if current_level is not None:
        # Update last fetched value
        st.session_state.last_fetch_val = current_level
        
        # Append to history if time has passed (simple check)
        last_time = st.session_state.history_data['time'].iloc[-1]
        if datetime.now() - last_time > timedelta(minutes=59): # Append every hour in mock, or strictly every fetch?
             # For this dashboard demo, let's append every fetch to see movement
            new_row = pd.DataFrame({"time": [datetime.now()], "level": [current_level]})
            st.session_state.history_data = pd.concat([st.session_state.history_data, new_row], ignore_index=True)
            
            # Keep only last 48 points
            if len(st.session_state.history_data) > 48:
                st.session_state.history_data = st.session_state.history_data.iloc[1:]

    # Fallback for visualization if fetch failed
    display_level = current_level if current_level is not None else st.session_state.history_data['level'].iloc[-1]
    status_text, status_color = get_status(display_level)

    # --- Top Metrics ---
    st.divider()
    m1, m2, m3 = st.columns(3)
    
    with m1:
        st.metric(
            label="ระดับน้ำปัจจุบัน", 
            value=f"{display_level:.2f} ม.", 
            delta=f"{delta_val} ม." if delta_val is not None else None,
            delta_color="inverse" # ถ้าน้ำขึ้น (บวก) เป็นสีแดง (แย่), น้ำลด (ลบ) เป็นสีเขียว (ดี)
        )
    
    with m2:
        st.markdown(f"<h3 style='color: {status_color}; margin:0;'>{status_text}</h3>", unsafe_allow_html=True)
        st.caption("สถานะความเสี่ยง")
        
    with m3:
        st.metric(label="ระดับตลิ่งวิกฤต", value=f"{CRITICAL_LEVEL:.2f} ม.")
        
    st.divider()

    # --- Main Visualization ---
    col_chart, col_gauge = st.columns([2, 1])
    
    with col_chart:
        st.subheader("📈 แนวโน้มระดับน้ำ (24 ชม.)")
        
        fig_line = go.Figure()
        
        # เส้นระดับน้ำ
        fig_line.add_trace(go.Scatter(
            x=st.session_state.history_data['time'], 
            y=st.session_state.history_data['level'],
            mode='lines+markers',
            name='ระดับน้ำ',
            line=dict(color='#29b6f6', width=3),
            fill='tozeroy', # Area chart style looks modern
            fillcolor='rgba(41, 182, 246, 0.1)'
        ))
        
        # เส้นวิกฤต
        fig_line.add_hline(
            y=CRITICAL_LEVEL, 
            line_dash="dash", 
            line_color="#ff5252", 
            annotation_text="Critical (10.5 m)", 
            annotation_position="top left"
        )
        
        # เส้นเฝ้าระวัง
        fig_line.add_hline(
            y=WARNING_LEVEL, 
            line_dash="dot", 
            line_color="#ffa726", 
            annotation_text="Warning (9.0 m)", 
            annotation_position="bottom left" 
        )
        
        fig_line.update_layout(
            margin=dict(l=20, r=20, t=30, b=20),
            xaxis_title="เวลา",
            yaxis_title="ระดับน้ำ (ม.รทก.)",
            hovermode="x unified",
            height=400,
            showlegend=True
        )
        st.plotly_chart(fig_line, width="stretch")

    with col_gauge:
        st.subheader("📊 มาตรวัดความเสี่ยง")
        
        fig_gauge = go.Figure(go.Indicator(
            mode = "gauge+number",
            value = display_level,
            domain = {'x': [0, 1], 'y': [0, 1]},
            title = {'text': "Water Level (m)", 'font': {'size': 20}},
            gauge = {
                'axis': {'range': [0, 14], 'tickwidth': 1, 'tickcolor': "darkblue"},
                'bar': {'color': "black"}, # เข็มสีดำ
                'bgcolor': "white",
                'borderwidth': 2,
                'bordercolor': "gray",
                'steps': [
                    {'range': [0, 9.0], 'color': "#66bb6a"}, # Green
                    {'range': [9.0, 10.5], 'color': "#ffa726"}, # Orange
                    {'range': [10.5, 14], 'color': "#ef5350"} # Red
                ],
                'threshold': {
                    'line': {'color': "red", 'width': 4},
                    'thickness': 0.75,
                    'value': CRITICAL_LEVEL
                }
            }
        ))
        
        fig_gauge.update_layout(height=400, margin=dict(l=20, r=20, t=50, b=20))
        st.plotly_chart(fig_gauge, width="stretch")

    # Auto-refresh logis is handled by main loop or user interaction
    # In a real deployed app, st.empty() or st.fragment is better, 
    # but for simple script simplicity we rely on manual refresh or rerun.
    # time.sleep(60)
    # st.rerun()

if __name__ == "__main__":
    # Trick to run with "python dashboard.py" instead of "streamlit run ..."
    import sys
    from streamlit.web import cli as stcli
    
    if "streamlit" not in sys.modules:
        sys.argv = ["streamlit", "run", __file__]
        sys.exit(stcli.main())
    else:
        main()
