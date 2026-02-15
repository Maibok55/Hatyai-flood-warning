#!C:\Python314\python.exe
import requests
from bs4 import BeautifulSoup

def get_rid_water():
    # URL สถานีหาดใหญ่ใน (P.1)
    url = "http://119.110.213.190/rid/stations.php?IdCode=08:STN04"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }

    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.encoding = 'utf-8' # ป้องกันภาษาไทยเพี้ยน
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # ค้นหาตัวเลขระดับน้ำ (ปกติจะอยู่ในตาราง หรือ <td>)
            # ในที่นี้เราจะหาจากข้อความ "ระดับน้ำ"
            rows = soup.find_all('tr')
            for row in rows:
                if "ระดับน้ำ" in row.text:
                    cols = row.find_all('td')
                    if len(cols) > 1:
                        water_level = cols[1].text.strip()
                        print(f"[SUCCESS] ดึงข้อมูลสำเร็จ!")
                        print(f"[STATION] สถานี: บ้านหาดใหญ่ใน (P.1)")
                        print(f"[LEVEL] ระดับน้ำปัจจุบัน: {water_level} เมตร (รทก.)")
                        return water_level
        else:
            print(f"[FAILED] ดึงข้อมูลไม่สำเร็จ Status: {response.status_code}")
            
    except Exception as e:
        print(f"[ERROR] Error: {e}")

if __name__ == "__main__":
    get_rid_water()