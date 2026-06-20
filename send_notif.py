import os
import requests

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TMDB_API_KEY = os.environ["TMDB_API_KEY"]
CHAT_ID = 680378702
TMDB_BASE = "https://api.themoviedb.org/3"
NOTIF_TYPE = os.environ.get("NOTIF_TYPE", "trending")

def tmdb_get(endpoint, params={}):
    p = dict(params)
    p["api_key"] = TMDB_API_KEY
    p["language"] = "id-ID"
    r = requests.get(f"{TMDB_BASE}{endpoint}", params=p, timeout=10)
    return r.json()

def send_message(text, keyboard=None):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"}
    if keyboard:
        import json
        data["reply_markup"] = json.dumps({"inline_keyboard": keyboard})
    requests.post(url, data=data, timeout=10)

def send_trending():
    data = tmdb_get("/trending/all/day")
    results = [r for r in data.get("results", []) if r.get("original_language") != "id"][:5]
    text = "🔥 *Trending Hari Ini!*\n\n"
    for i, m in enumerate(results, 1):
        title = m.get("title") or m.get("name", "?")
        media = "🎬" if m.get("media_type") == "movie" else "📺"
        rating = m.get("vote_average", 0)
        text += f"{i}. {media} *{title}* ⭐{rating:.1f}\n"
    send_message(text)
    print("✅ Trending sent!")

def send_coming_soon():
    data = tmdb_get("/movie/upcoming", {"region": "US"})
    results = [r for r in data.get("results", []) if r.get("original_language") != "id"][:5]
    text = "🎬 *Film Yang Akan Segera Rilis!*\n\n"
    for i, m in enumerate(results, 1):
        title = m.get("title", "?")
        date = (m.get("release_date") or "")[:10]
        rating = m.get("vote_average", 0)
        text += f"{i}. *{title}*\n📅 {date} | ⭐{rating:.1f}\n\n"
    send_message(text)
    print("✅ Coming soon sent!")

def send_now_playing():
    data = tmdb_get("/movie/now_playing", {"region": "US"})
    results = [r for r in data.get("results", []) if r.get("original_language") != "id"][:5]
    text = "🍿 *Film Lagi Tayang di Bioskop!*\n\n"
    for i, m in enumerate(results, 1):
        title = m.get("title", "?")
        rating = m.get("vote_average", 0)
        text += f"{i}. *{title}* ⭐{rating:.1f}\n"
    send_message(text)
    print("✅ Now playing sent!")

if NOTIF_TYPE == "trending":
    send_trending()
elif NOTIF_TYPE == "coming_soon":
    send_coming_soon()
elif NOTIF_TYPE == "now_playing":
    send_now_playing()
