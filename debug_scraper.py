import requests
from bs4 import BeautifulSoup

def debug_fetch(url, name):
    print(f"\n--- Debugging {name} ---")
    print(f"URL: {url}")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        print(f"Status Code: {response.status_code}")
        print(f"Apparent Encoding: {response.apparent_encoding}")
        
        # The site says utf-8 but often it is cp874 (Windows-874) for Thai gov sites
        response.encoding = 'cp874' 
        print(f"Snippet (CP874): {response.text[:500]}...") 
        
        if "ระดับน้ำ" in response.text:
             print("SUCCESS: Found 'ระดับน้ำ' with CP874")
        
        soup = BeautifulSoup(response.text, 'html.parser')
        rows = soup.find_all('tr')
        print(f"Found {len(rows)} rows.")
        
        found_data = False
        for i, row in enumerate(rows):
            text = row.text.strip()
            if "ระดับน้ำ" in text or "Water Level" in text:
                print(f"Row {i} MATCH: {text}")
                cols = row.find_all('td')
                print(f"  Columns: {[c.text.strip() for c in cols]}")
                found_data = True
            
        if not found_data:
            print("No row contained 'ระดับน้ำ'. Dumping all row text for inspection:")
            for i, row in enumerate(rows[:10]): # Dump first 10 rows
                print(f"Row {i}: {row.text.strip().replace('\n', ' ')}")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    stations = {
        "HatYai": "http://119.110.213.190/rid/stations.php?IdCode=08:STN04",
        "Sadao": "http://119.110.213.190/rid/stations.php?IdCode=08:STN13" 
    }
    for name, url in stations.items():
        debug_fetch(url, name)
