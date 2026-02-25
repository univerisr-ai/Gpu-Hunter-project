import os
import sys
import json
import time
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from zoneinfo import ZoneInfo

# --- AYARLAR ---
API_KEY = os.environ.get("SCRAPERAPI_KEY")
TARGET_URL = "https://www.sahibinden.com/ekran-karti?sorting=date_desc" # Linki sadeleştirdik
JSON_FILE = "ilanlar.json"

BANNED_WORDS = [
    "bozuk", "arızalı", "çalışmıyor", "kırık", "defolu", "hatalı", "parçalık", 
    "tamirli", "tamir görmüş", "revizyon", "sadece kutusu", "sadece kutu", 
    "kutu satışı", "mining", "rig sökümü", "görüntü vermiyor"
]

def get_html():
    """ScraperAPI ile İnatçı (Retry) İstek Atar"""
    if not API_KEY:
        print("HATA: SCRAPERAPI_KEY bulunamadı!")
        sys.exit(1)

    base_api_url = "https://api.scraperapi.com/"
    
    # render=true kaldırdık, çünkü 500 hatasına o sebep oluyor. premium yeterli.
    params = {
        "api_key": API_KEY,
        "url": TARGET_URL,
        "premium": "true",
        "country_code": "tr",
        "device_type": "desktop"
    }

    max_retries = 3 # 3 Kere deneyecek
    
    for attempt in range(1, max_retries + 1):
        try:
            print(f"Deneme {attempt}/{max_retries} - İstek atılıyor...")
            response = requests.get(base_api_url, params=params, timeout=60)
            
            # Eğer 200 (Başarılı) dönerse ve içinde ilan varsa HTML'i ver ve çık
            if response.status_code == 200 and "searchResultsItem" in response.text:
                print("Başarılı! Veri çekildi.")
                return response.text
                
            print(f"Uyarı: İstenen sayfa tam gelmedi. HTTP Durumu: {response.status_code}. Captcha olabilir.")
            
        except Exception as e:
            print(f"Hata: {e}")
            
        # Eğer buraya geldiyse başarısız olmuştur, diğer deneme için 5 saniye bekle
        if attempt < max_retries:
            print("5 saniye beklenip farklı bir Proxy (IP) ile tekrar denenecek...\n")
            time.sleep(5)

    print("KRİTİK HATA: Tüm denemeler başarısız oldu. Sahibinden çok sıkı koruma uyguluyor.")
    return None

def is_clean_title(title):
    title_lower = title.lower()
    for word in BANNED_WORDS:
        if word in title_lower:
            return False
    return True

def parse_html(html_content):
    soup = BeautifulSoup(html_content, "lxml")
    items = soup.select("tr.searchResultsItem, ul.searchResultsList li.searchResultsItem")
    parsed_data = []
    now = datetime.now(ZoneInfo("Europe/Istanbul")).isoformat()

    for item in items:
        item_html_str = str(item).lower()
        if "param güvende" not in item_html_str and "get" not in item_html_str:
            continue
            
        try:
            item_id = item.get("data-id")
            if not item_id:
                continue

            title_elem = item.select_first("a.classifiedTitle")
            if not title_elem:
                continue
            title = title_elem.text.strip()

            if not is_clean_title(title):
                continue

            href = title_elem.get("href", "")
            link = f"https://www.sahibinden.com{href}" if href.startswith("/") else href

            price_elem = item.select_first("td.searchResultsPriceValue, div.searchResultsPriceValue")
            price = price_elem.text.strip() if price_elem else "Fiyat Yok"

            image_url = None
            img_elem = item.select_first("img")
            if img_elem:
                image_url = img_elem.get("data-src") or img_elem.get("src")
            
            if not image_url:
                noscript_elem = item.select_first("noscript img")
                if noscript_elem:
                    image_url = noscript_elem.get("src")

            if image_url and image_url.startswith("//"):
                image_url = f"https:{image_url}"

            parsed_data.append({
                "id": item_id,
                "title": title,
                "price": price,
                "link": link,
                "image": image_url,
                "scraped_at": now
            })
        except Exception as e:
            continue

    return parsed_data

def update_json(new_items):
    if len(new_items) == 0:
        print("KRİTİK: İlan bulunamadı! Mevcut veri korunuyor.")
        sys.exit(1)

    existing_items = []
    if os.path.exists(JSON_FILE):
        try:
            with open(JSON_FILE, "r", encoding="utf-8") as f:
                existing_items = json.load(f)
        except:
            existing_items = []

    items_dict = {item["id"]: item for item in existing_items}
    for item in new_items:
        items_dict[item["id"]] = item

    all_items = list(items_dict.values())
    all_items.sort(key=lambda x: x["scraped_at"], reverse=True)
    final_items = all_items[:50]

    with open(JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(final_items, f, ensure_ascii=False, indent=4)
        
    print(f"Başarı: Toplam {len(new_items)} yeni ilan yakalandı/güncellendi. Dosyaya yazıldı.")

if __name__ == "__main__":
    html = get_html()
    if html:
        scraped_items = parse_html(html)
        update_json(scraped_items)
    else:
        sys.exit(1)
