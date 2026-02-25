import os
import sys
import json
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from zoneinfo import ZoneInfo

# --- AYARLAR ---
API_KEY = os.environ.get("SCRAPERAPI_KEY")
TARGET_URL = "https://www.sahibinden.com/ekran-karti?sorting=date_desc&pagingOffset=0&pagingSize=50"
JSON_FILE = "ilanlar.json"

# İstenmeyen kelimeler (Case-Insensitive filtreleme için küçük harfe çevrilmiş halde)
BANNED_WORDS = [
    "bozuk", "arızalı", "çalışmıyor", "kırık", "defolu", "hatalı", "parçalık", 
    "tamirli", "tamir görmüş", "revizyon", "sadece kutusu", "sadece kutu", 
    "kutu satışı", "mining", "rig sökümü", "görüntü vermiyor"
]

def get_html():
    """ScraperAPI kullanarak Sahibinden.com'dan HTML çeker. İki kademeli hata toleransı."""
    if not API_KEY:
        print("HATA: SCRAPERAPI_KEY bulunamadı!")
        sys.exit(1)

    base_api_url = "https://api.scraperapi.com/"
    
    # 1. Kademe: Premium Proxy
    params_tier1 = {
        "api_key": API_KEY,
        "url": TARGET_URL,
        "premium": "true",
        "country_code": "tr"
    }

    # 2. Kademe: Render (JavaScript render - daha yavaş ama garantili)
    params_tier2 = params_tier1.copy()
    params_tier2["render"] = "true"

    try:
        print("Kademe 1 isteği atılıyor...")
        response = requests.get(base_api_url, params=params_tier1, timeout=60)
        
        # Eğer Captcha geldiyse veya sayfa düzgün yüklenmediyse 2. kademeye geç
        if response.status_code != 200 or "captcha" in response.text.lower() or "searchResultsItem" not in response.text:
            print("Kademe 1 başarısız veya Captcha yakalandı. Kademe 2 (Render) deneniyor...")
            response = requests.get(base_api_url, params=params_tier2, timeout=60)
            response.raise_for_status()
        
        return response.text
    except Exception as e:
        print(f"HATA: HTML çekilirken hata oluştu: {e}")
        return None

def is_clean_title(title):
    """Başlıkta yasaklı kelime geçip geçmediğini kontrol eder."""
    title_lower = title.lower()
    for word in BANNED_WORDS:
        if word in title_lower:
            return False
    return True

def parse_html(html_content):
    """HTML içeriğini ayrıştırır ve Param Güvende ilanlarını çeker."""
    soup = BeautifulSoup(html_content, "lxml")
    
    # İlan satırlarını bul (Liste görünümü veya klasik görünüm)
    items = soup.select("tr.searchResultsItem, ul.searchResultsList li.searchResultsItem")
    
    parsed_data = []
    now = datetime.now(ZoneInfo("Europe/Istanbul")).isoformat()

    for item in items:
        item_html_str = str(item).lower()
        
        # Sadece Param Güvende ilanlarını al
        if "param güvende" not in item_html_str and "get" not in item_html_str:
            continue
            
        try:
            # ID
            item_id = item.get("data-id")
            if not item_id:
                continue

            # Title
            title_elem = item.select_first("a.classifiedTitle")
            if not title_elem:
                continue
            title = title_elem.text.strip()

            # Kelime filtresi
            if not is_clean_title(title):
                continue

            # Link
            href = title_elem.get("href", "")
            link = f"https://www.sahibinden.com{href}" if href.startswith("/") else href

            # Price
            price_elem = item.select_first("td.searchResultsPriceValue, div.searchResultsPriceValue")
            price = price_elem.text.strip() if price_elem else "Fiyat Yok"

            # Image (Lazy load, data-src veya noscript içi fallback)
            image_url = None
            img_elem = item.select_first("img")
            
            if img_elem:
                image_url = img_elem.get("data-src") or img_elem.get("src")
            
            # Eğer JS yüklenmemişse <noscript> içindeki img etiketine bak
            if not image_url:
                noscript_elem = item.select_first("noscript img")
                if noscript_elem:
                    image_url = noscript_elem.get("src")

            # Resim URL'sini düzelt ("//" ile başlıyorsa)
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
            print(f"İlan parse edilirken hata atlandı: {e}")
            continue

    return parsed_data

def update_json(new_items):
    """Mevcut JSON'u okur, yenileri ekler, sıralar ve kaydeder. Self-healing içerir."""
    # Emniyet kontrolü
    if len(new_items) == 0:
        print("KRİTİK: Bu çalışmada geçerli hiçbir ilan bulunamadı! Mevcut veri korunuyor.")
        sys.exit(1)

    # Dosyayı oku (Self-healing: Bozuksa veya yoksa boş liste ile başla)
    existing_items = []
    if os.path.exists(JSON_FILE):
        try:
            with open(JSON_FILE, "r", encoding="utf-8") as f:
                existing_items = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            print("Uyarı: Mevcut JSON bozuk veya yok, sıfırdan oluşturuluyor...")
            existing_items = []

    # Mevcut veriyi ID bazlı dictionary'e çevir (Hızlı güncelleme için)
    items_dict = {item["id"]: item for item in existing_items}

    # Yeni ilanları sözlüğe yaz (Aynı ID varsa üzerine yazar / günceller)
    for item in new_items:
        items_dict[item["id"]] = item

    # Sözlüğü listeye çevir
    all_items = list(items_dict.values())

    # Tarihe göre YENİDEN ESKİYE (date_desc) sırala
    all_items.sort(key=lambda x: x["scraped_at"], reverse=True)

    # Sadece en yeni 50 ilanı tut
    final_items = all_items[:50]

    # JSON'a kaydet
    with open(JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(final_items, f, ensure_ascii=False, indent=4)
        
    print(f"Başarı: Toplam {len(new_items)} yeni ilan yakalandı/güncellendi. Dosyaya yazıldı.")

if __name__ == "__main__":
    html = get_html()
    if html:
        scraped_items = parse_html(html)
        update_json(scraped_items)
    else:
        print("HTML alınamadığı için işlem iptal edildi.")
        sys.exit(1)
