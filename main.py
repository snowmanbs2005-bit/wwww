import asyncio
import feedparser
import aiohttp
import json
import os
from bs4 import BeautifulSoup

# ================= НАСТРОЙКИ =================
TG_TOKEN = os.environ.get("TG_TOKEN", "8508931728:AAF4b86N9R9ZwlKzMIUBLBTwSPr_VRPY6Ho")
TG_CHAT  = int(os.environ.get("TG_CHAT", "804152171"))

AUTHORS = [
    "cryptocatagency",
    "Vilarso",
    "Prizrak_Trade",
    "ViktorTrade888",
]

STATE_FILE = "last_seen.json"  # Память о просмотренных постах

# ================= ЛОГИКА =================

def load_state():
    """Загружает список уже отправленных постов"""
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {}

def save_state(state):
    """Сохраняет список отправленных постов"""
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

async def fetch_page(url):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
    async with aiohttp.ClientSession() as s:
        try:
            async with s.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as r:
                if r.status == 200:
                    return await r.text()
        except Exception as e:
            print(f"❌ Ошибка загрузки страницы: {e}")
    return None

def extract_image_from_rss(entry):
    html = entry.get("description", "") or entry.get("summary", "")
    soup = BeautifulSoup(html, "html.parser")
    for img in soup.find_all("img"):
        src = img.get("src", "")
        if src and "http" in src and not src.endswith(".gif"):
            return src
    for field in ["media_content", "media_thumbnail"]:
        media = getattr(entry, field, None) or entry.get(field)
        if media:
            for m in (media if isinstance(media, list) else [media]):
                if m.get("url"):
                    return m["url"]
    for enc in entry.get("enclosures", []):
        url = enc.get("href") or enc.get("url", "")
        if url:
            return url
    return None

async def extract_image_from_page(post_url):
    html = await fetch_page(post_url)
    if not html:
        return None
    soup = BeautifulSoup(html, "html.parser")
    og = soup.find("meta", property="og:image")
    if og:
        content = og.get("content", "")
        if content and "http" in content:
            return content
    return None

async def download_image(url):
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://ru.tradingview.com/",
    }
    async with aiohttp.ClientSession() as s:
        try:
            async with s.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=20)) as r:
                if r.status == 200:
                    return await r.read()
        except Exception as e:
            print(f"❌ Ошибка скачивания: {e}")
    return None

async def send_photo_to_tg(image_bytes, caption):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto"
    data = aiohttp.FormData()
    data.add_field("chat_id", str(TG_CHAT))
    data.add_field("caption", caption, content_type="text/plain")
    data.add_field("parse_mode", "HTML")
    data.add_field("photo", image_bytes, filename="chart.png", content_type="image/png")

    async with aiohttp.ClientSession() as s:
        try:
            async with s.post(url, data=data, timeout=aiohttp.ClientTimeout(total=20)) as r:
                result = await r.json()
                if r.status == 200:
                    print(f"✅ Отправлено в Telegram!")
                else:
                    print(f"❌ Ошибка Telegram: {result}")
        except Exception as e:
            print(f"❌ Ошибка отправки: {e}")

async def main():
    print("🤖 Запуск проверки...")
    state = load_state()

    for author in AUTHORS:
        feed_url = f"https://ru.tradingview.com/feed/?username={author}"
        try:
            feed = feedparser.parse(feed_url)
        except Exception as e:
            print(f"❌ Ошибка RSS для {author}: {e}")
            continue

        if not feed.entries:
            print(f"📭 У {author} пустая лента!")
            continue

        latest = feed.entries[0]
        post_id = latest.get("id") or latest.get("link")

        if state.get(author) == post_id:
            print(f"⏭️ {author} — новых постов нет")
            continue

        print(f"🔍 Новый пост от {author}!")
        state[author] = post_id

        # Текст и дата
        html = latest.get("description", "") or latest.get("summary", "")
        text = BeautifulSoup(html, "html.parser").get_text(separator=" ").strip()
        post_link = latest.get("link", "")

        import time
        published = latest.get("published_parsed") or latest.get("updated_parsed")
        date_str = time.strftime("%d.%m.%Y %H:%M", published) if published else "неизвестно"

        caption = f"👤 <b>{author}</b>\n🕐 {date_str}\n\n{text[:800]}\n\n🔗 <a href='{post_link}'>Открыть пост</a>"

        # Ищем картинку
        img_url = extract_image_from_rss(latest)
        if not img_url and post_link:
            print(f"   → Ищу картинку на странице...")
            img_url = await extract_image_from_page(post_link)

        if not img_url:
            print(f"⚠️ Нет графика у {author}")
            continue

        print(f"🖼️ Скачиваю график...")
        image_bytes = await download_image(img_url)

        if image_bytes:
            await send_photo_to_tg(image_bytes, caption)
        else:
            print("❌ Не смог скачать картинку.")

    save_state(state)
    print("✅ Проверка завершена!")

if __name__ == "__main__":
    asyncio.run(main())
