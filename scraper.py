import os
import sys
import json
import time
import requests
import urllib3
from bs4 import BeautifulSoup
from datetime import datetime
from zoneinfo import ZoneInfo

# Proxy kullanırken çıkan gereksiz SSL uyarılarını gizle
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- AYARLAR ---
API_KEY = os.environ.get("SCRAPERAPI_KEY")
TARGET_URL = "https://www.sahibinden.com/ekran-karti?sorting=date_desc"
JSON_FILE = "ilanlar.json"

BANNED_WORDS = [
    "bozuk", "arızalı", "çalışmıyor", "kırık", "defolu", "hatalı", "parçalık", 
    "tamirli", "tamir görmüş", "revizyon", "sadece kutusu", "sadece kutu", 
    "kutu satışı", "mining", "rig sökümü", "görüntü vermiyor"
]

def get_html_via_proxy():
    """ScraperAPI'yi REST API olarak değil, doğrudan Proxy (Tünel) olarak kullanır."""
    if not API_KEY:
        print("HATA: SCRAPERAPI_KEY bulunamadı!")
        sys.exit(1)

    # TR lokasyonlu ve Premium (Ev İnterneti) Proxy Ayarı
    proxy_url = f"http://scraperapi.country_code=tr.premium=true:{API_KEY}@proxy-server.scraperapi.com:8001"
    
    proxies = {
        "http": proxy_url,
        "https": proxy_url
    }

    # Sahibinden'i kandırmak için Mükemmel Başlıklar (Headers)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://www.google.com.tr/", # Sanki Google'dan gelmişiz gibi!
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "cross-site",
        "Sec-Fetch-User": "?1"
    }

    max_retries = 3 
    
    for attempt in range(1, max_retries + 1):
        try:
            print(f"Deneme {attempt}/{max_retries} - Truva Atı Modu (Tünel) ile giriliyor...")
            
            # verify=False ekledik çünkü aracı proxy sunucuları bazen SSL hatası verdirir
            response = requests.get(
                TARGET_URL, 
                proxies=proxies, 
                headers=headers, 
                timeout=60, 
                verify=False
            )
            
            # Eğer 200 dönerse ve içinde Sahibinden'e ait bir HTML etiketi varsa
            if response.status_code == 200 and "searchResultsItem" in response.text:
                print("BAŞARILI! Duvar yıkıldı, HTML verisi elimizde.")
                return response.text
                
            print(f"Uyarı: Güvenliğe takıldı. HTTP: {response.status_code}.")
            # Hatanın gerçekte ne olduğunu (208 byte meselesi) görmek için ilk 250 karakteri yazdır
            print(f"Sahibinden'in veya Proxy'nin Cevabı: {response.text[:250]}")
            
        except Exception as e:
            print(f"Bağlantı koptu veya zaman aşımı: {e}")
            
        if attempt < max_retries:
            print("8 saniye bekleniyor, IP değiştirilip tekrar denenecek...\n")
            time.sleep(8)

    print("KRİTİK HATA: Proxy havuzundaki IP'ler de engellendi.")
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
        print("KRİTİK: İlan bulunamadı! Sayfa yapısı değişmiş veya Captcha gelmiş olabilir.")
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
        
    print(f"BÜYÜK BAŞARI: Toplam {len(new_items)} yeni ilan yakalandı ve JSON'a yazıldı!")

if __name__ == "__main__":
    html = get_html_via_proxy()
    if html:
        scraped_items = parse_html(html)
        update_json(scraped_items)
    else:
        sys.exit(1)
