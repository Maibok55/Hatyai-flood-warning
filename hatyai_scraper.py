"""
HYFI Hybrid Intelligence Scraper
Scrapes hatyaicityclimate.org for:
  A) News/alerts about flood warnings
  B) Sensor health status (power outage detection)
  C) Camera feed availability
"""
import requests
from bs4 import BeautifulSoup
from datetime import datetime

# Base URL
BASE_URL = "https://www.hatyaicityclimate.org"

# Keywords that indicate sensor/station problems
OUTAGE_KEYWORDS = [
    "ไฟฟ้าขัดข้อง", "ขัดข้อง", "ชำรุด", "ไม่ทำงาน",
    "offline", "error", "ปิดปรับปรุง", "งดใช้", "ซ่อมบำรุง"
]

# Keywords that indicate flood warnings
ALERT_KEYWORDS = [
    "น้ำท่วม", "ประกาศ", "เตือนภัย", "ฉบับที่", "เฝ้าระวัง",
    "อพยพ", "วิกฤต", "ระดับน้ำ", "ฝนตก", "พายุ"
]

# Station name mapping (local names -> our system names)
STATION_NAME_MAP = {
    "ม่วงก็อง": "Sadao",
    "muangkong": "Sadao",
    "บางศาลา": "Kallayanamit",
    "bangsala": "Kallayanamit",
    "กัลยาณมิตร": "Kallayanamit",
    "kalyanamit": "Kallayanamit",
    "หาดใหญ่": "HatYai",
    "อู่ตะเภา": "HatYai",
    "utapao": "HatYai",
    "คลองเตย": "HatYai",
    "S1": "Sadao",
    "S2": "Kallayanamit",
    "X.90": "HatYai",
    "X.44": "Kallayanamit",
    "X.173": "Sadao",
}


def scrape_hatyai_climate():
    """
    Main scraper function. Returns a dictionary:
    {
        "news": [{"title": str, "link": str}, ...],
        "station_health": {"Sadao": "online"/"outage", ...},
        "outage_stations": ["Sadao", ...],  # Stations with detected problems
        "outage_details": {"Sadao": "ไฟฟ้าขัดข้อง", ...},
        "cameras": [{"name": str, "url": str}, ...],
        "scrape_time": datetime,
        "source_url": str,
        "success": bool,
        "error": str or None
    }
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    result = {
        "news": [],
        "station_health": {},
        "outage_stations": [],
        "outage_details": {},
        "cameras": [],
        "scrape_time": datetime.now(),
        "source_url": BASE_URL,
        "success": False,
        "error": None
    }
    
    try:
        response = requests.get(BASE_URL, headers=headers, timeout=10)
        response.encoding = 'utf-8'
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # =============================================
        # A) NEWS & ALERTS
        # =============================================
        seen_titles = set()
        for link in soup.find_all('a', href=True):
            text = link.get_text().strip()
            if len(text) < 15 or text in seen_titles:
                continue
            
            # Check if this link contains alert/news keywords
            is_news = any(kw in text for kw in ALERT_KEYWORDS)
            # Also check for links to /paper/ pages (news articles)
            is_paper = '/paper/' in link['href']
            
            if is_news or is_paper:
                full_link = link['href']
                if not full_link.startswith('http'):
                    full_link = f"{BASE_URL}{full_link}"
                
                seen_titles.add(text)
                result["news"].append({
                    "title": text,
                    "link": full_link,
                    "is_alert": is_news and not is_paper
                })
        
        # =============================================
        # B) SENSOR HEALTH CHECK
        # =============================================
        full_text = soup.get_text()
        lines = [line.strip() for line in full_text.split('\n') if line.strip()]
        
        # Initialize all known stations as "online"
        for sys_name in set(STATION_NAME_MAP.values()):
            result["station_health"][sys_name] = "online"
        
        # Scan every line for outage keywords near station names
        for line in lines:
            line_lower = line.lower()
            
            # Check if this line mentions any station
            for station_key, sys_name in STATION_NAME_MAP.items():
                if station_key in line or station_key in line_lower:
                    # Check if outage keyword is also present
                    for outage_kw in OUTAGE_KEYWORDS:
                        if outage_kw in line or outage_kw in line_lower:
                            result["station_health"][sys_name] = "outage"
                            if sys_name not in result["outage_stations"]:
                                result["outage_stations"].append(sys_name)
                            result["outage_details"][sys_name] = line[:100]
                            break
        
        # =============================================
        # C) CAMERA FEED DETECTION
        # =============================================
        for link in soup.find_all('a', href=True):
            href = link['href']
            if '/flood/cam/' in href and '?name=' in href:
                cam_name = href.split('?name=')[-1]
                full_url = href if href.startswith('http') else f"{BASE_URL}{href}"
                
                # Avoid duplicates
                if not any(c['name'] == cam_name for c in result["cameras"]):
                    result["cameras"].append({
                        "name": cam_name,
                        "url": full_url
                    })
        
        result["success"] = True
        
    except requests.Timeout:
        result["error"] = "Connection timed out (10s)"
    except requests.ConnectionError:
        result["error"] = "Cannot reach hatyaicityclimate.org"
    except Exception as e:
        result["error"] = f"Scraper error: {str(e)}"
    
    return result


def check_zombie_data(api_sensor_data, scraper_result):
    """
    Cross-reference API data with scraper health check.
    Returns a modified sensor_data dict with zombie values nullified.
    
    Logic:
    - If scraper detected an outage for a station, set that station's
      API value to None and mark it as 'zombie' in metadata.
    
    Args:
        api_sensor_data: dict from FloodPredictor.fetch_and_store_data()
        scraper_result: dict from scrape_hatyai_climate()
    
    Returns:
        dict: Modified sensor_data with zombie values replaced
        dict: Zombie report {station: reason}
    """
    zombie_report = {}
    modified_data = dict(api_sensor_data)  # Shallow copy
    modified_data["all_data"] = dict(api_sensor_data.get("all_data", {}))
    
    if not scraper_result.get("success"):
        # Scraper failed — can't validate, return original data with warning
        return modified_data, {"_scraper": "Scraper offline, cannot validate"}
    
    outage_stations = scraper_result.get("outage_stations", [])
    
    for station_name in outage_stations:
        detail = scraper_result.get("outage_details", {}).get(station_name, "Unknown issue")
        
        # Nullify the value in all_data
        if station_name in modified_data["all_data"]:
            old_val = modified_data["all_data"][station_name]
            modified_data["all_data"][station_name] = None
            zombie_report[station_name] = {
                "reason": detail,
                "zombie_value": old_val,
                "action": "Value ignored due to sensor outage"
            }
        
        # If primary station is affected, clear main readings too
        if modified_data.get("station_name") == station_name:
            modified_data["level"] = None
            modified_data["is_fallback"] = True
    
    return modified_data, zombie_report


if __name__ == "__main__":
    print("--- Testing HatyaiCityClimate Scraper ---")
    data = scrape_hatyai_climate()
    
    print(f"\nSuccess: {data['success']}")
    print(f"Error: {data['error']}")
    
    print(f"\n📢 News ({len(data['news'])} items):")
    for n in data['news'][:5]:
        print(f"  • {n['title']}")
    
    print(f"\n🛠️ Station Health:")
    for station, status in data['station_health'].items():
        icon = "🟢" if status == "online" else "🔴"
        print(f"  {icon} {station}: {status}")
    
    if data['outage_stations']:
        print(f"\n⚠️ Outage Detected: {data['outage_stations']}")
        for s, detail in data['outage_details'].items():
            print(f"  {s}: {detail}")
    
    print(f"\n📷 Cameras ({len(data['cameras'])} feeds)")
    for c in data['cameras'][:5]:
        print(f"  • {c['name']}")