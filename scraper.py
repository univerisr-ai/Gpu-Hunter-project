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
TARGET_URL = "https://www.sahibinden.com/ekran-karti?sorting=date_desc"
JSON_FILE = "ilanlar.json"

BANNED_WORDS = [
    "bozuk", "arızalı", "çalışmıyor", "kırık", "defolu", "hatalı", "parçalık", 
    "tamirli", "tamir görmüş", "revizyon", "sadece kutusu", "sadece kutu", 
    "kutu satışı", "mining", "rig sökümü", "görüntü vermiyor"
]

def get_html():
    if not API_KEY:
        print("HATA: SCRAPERAPI_KEY bulunamadı!")
        sys.exit(1)

    base_api_url = "https://api.scraperapi.com/"
    
    # TR kısıtlaması kaldırıldı, render ve keep_headers eklendi (Hayalet Modu)
    params = {
        "api_key": API_KEY,
        "url": TARGET_URL,
        "premium": "true",
        "render": "true",
        "keep_headers": "true"
    }

    # Gerçek insan kimliği
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7"
    }

    max_retries = 3 
    
    for attempt in range(1, max_retries + 1):
        try:
            print(f"Deneme {attempt}/{max_retries} - Hayalet modunda istek atılıyor...")
            response = requests.get(base_api_url, params=params, headers=headers, timeout=90)
            
            if response.status_code == 200 and "searchResultsItem" in response.text:
                print("BAŞARILI! Duvar aşıldı ve veriler çekildi.")
                return response.text
                
            print(f"Uyarı: Duvar aşılamadı. HTTP Durumu: {response.status_code}. Sayfa Boyutu: {len(response.text)} byte")
            
        except Exception as e:
            print(f"Hata: İletişim koptu ({e})")
            
        if attempt < max_retries:
            print("10 saniye dinlenip yepyeni bir kimlikle tekrar denenecek...\n")
            time.sleep(10)

    print("KRİTİK HATA: Sahibinden koruması bu seferlik aşılamadı.")
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
        
    print(f"BÜYÜK BAŞARI: Toplam {len(new_items)} yeni ilan yakalandı ve siteye gönderildi!")

if __name__ == "__main__":
    html = get_html()
    if html:
        scraped_items = parse_html(html)
        update_json(scraped_items)
    else:
        sys.exit(1)
