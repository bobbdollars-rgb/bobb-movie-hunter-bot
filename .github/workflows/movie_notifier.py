"""
BobbMovieHunter - Auto Release Notifier
----------------------------------------
Cek TMDb tiap jam buat:
  - Now Playing (movie) / On The Air (series)
  - Upcoming (movie & series)
  - Digital release & Blu-ray release (movie aja - TMDb gak track ini buat series)

Exclude konten Indonesia: kalau original_language == "id" ATAU production/origin
country == "ID", movie/series itu di-skip (gak dikirim).

Kirim ke personal Telegram chat. State di posted_state.json biar gak double-post.
"""

import os
import json
import requests
from datetime import datetime

TMDB_API_KEY = os.environ["TMDB_API_KEY"]
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
REGION = os.environ.get("REGION", "ID")

TMDB_BASE = "https://api.themoviedb.org/3"
STATE_FILE = "posted_state.json"

TYPE_DIGITAL = 4
TYPE_PHYSICAL = 5

STATE_DEFAULTS = {
    "movie_now_playing": [], "movie_upcoming": [],
    "movie_digital": [], "movie_physical": [],
    "tv_on_the_air": [], "tv_upcoming": [],
}


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            data = json.load(f)
        for key, default in STATE_DEFAULTS.items():
            data.setdefault(key, default)
        return data
    return {k: list(v) for k, v in STATE_DEFAULTS.items()}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def tmdb_get(path, params=None):
    params = params or {}
    params["api_key"] = TMDB_API_KEY
    params["language"] = "id-ID"
    r = requests.get(f"{TMDB_BASE}{path}", params=params, timeout=15)
    r.raise_for_status()
    return r.json()


def fetch_all_pages(path, params=None, max_pages=10):
    """Ambil semua halaman dari endpoint TMDb (default cap 10 halaman ~200 item,
    biar gak ngabisin quota/rate limit kalau listnya kepanjangan)."""
    params = dict(params or {})
    results = []
    page = 1
    while True:
        params["page"] = page
        data = tmdb_get(path, params)
        results.extend(data.get("results", []))
        total_pages = data.get("total_pages", 1)
        if page >= total_pages or page >= max_pages:
            break
        page += 1
    return results


# ---------- Movie ----------

def get_now_playing_movies():
    return fetch_all_pages("/movie/now_playing", {"region": REGION})


def get_upcoming_movies():
    return fetch_all_pages("/movie/upcoming", {"region": REGION})


def get_movie_details(movie_id):
    return tmdb_get(f"/movie/{movie_id}")


def get_movie_release_dates(movie_id):
    return tmdb_get(f"/movie/{movie_id}/release_dates").get("results", [])


def is_indonesian_movie(movie):
    if movie.get("original_language") == "id":
        return True
    details = get_movie_details(movie["id"])
    countries = [c["iso_3166_1"] for c in details.get("production_countries", [])]
    return "ID" in countries


# ---------- TV / Series ----------

def get_on_the_air_tv():
    return fetch_all_pages("/tv/on_the_air")


def get_upcoming_tv():
    today = datetime.utcnow().date().isoformat()
    return fetch_all_pages("/discover/tv", {
        "first_air_date.gte": today,
        "sort_by": "first_air_date.asc",
    })


def get_tv_details(tv_id):
    return tmdb_get(f"/tv/{tv_id}")


def get_tv_content_ratings(tv_id):
    return tmdb_get(f"/tv/{tv_id}/content_ratings").get("results", [])


def is_indonesian_tv(show):
    if show.get("original_language") == "id":
        return True
    if "ID" in (show.get("origin_country") or []):
        return True
    details = get_tv_details(show["id"])
    countries = [c["iso_3166_1"] for c in details.get("production_countries", [])]
    return "ID" in countries


# ---------- Shared helpers ----------

def find_release_date(release_data, region, type_code):
    for entry in release_data:
        if entry["iso_3166_1"] == region:
            for rd in entry["release_dates"]:
                if rd["type"] == type_code:
                    return rd["release_date"][:10]
    return None


def find_movie_certification(release_data, region):
    for target_region in (region, "US"):
        for entry in release_data:
            if entry["iso_3166_1"] == target_region:
                for rd in entry["release_dates"]:
                    cert = rd.get("certification")
                    if cert:
                        return cert
    return None


def find_tv_certification(ratings_data, region):
    for target_region in (region, "US"):
        for entry in ratings_data:
            if entry["iso_3166_1"] == target_region and entry.get("rating"):
                return entry["rating"]
    return None


def send_telegram(text, poster_path=None):
    if poster_path:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "photo": f"https://image.tmdb.org/t/p/w500{poster_path}",
            "caption": text,
            "parse_mode": "HTML",
        }
    else:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
        }
    r = requests.post(url, data=payload, timeout=15)
    r.raise_for_status()


def format_message(item, category_label, certification=None, media_type="movie"):
    title = item.get("title") or item.get("name") or "Unknown"
    date_field = item.get("release_date") or item.get("first_air_date") or ""
    year = date_field[:4] if date_field else "----"
    rating = item.get("vote_average") or 0
    vote_count = item.get("vote_count") or 0
    synopsis = item.get("overview") or "Sinopsis belum tersedia."
    cert_line = f"🔖 Rating Usia: {certification}\n" if certification else ""
    tipe_icon = "🎬" if media_type == "movie" else "📺"

    return (
        f"{tipe_icon} <b>{category_label}</b>\n\n"
        f"<b>{title}</b> ({year})\n"
        f"⭐ {rating:.1f}/10 ({vote_count:,} votes)\n"
        f"{cert_line}"
        f"📅 Rilis: {date_field or '-'}\n\n"
        f"📖 {synopsis}"
    )


# ---------- Processing ----------

def process_movies(items, state_key, state, category_label):
    seen = state[state_key]
    for movie in items:
        movie_id = movie["id"]
        if movie_id in seen:
            continue
        if is_indonesian_movie(movie):
            seen.append(movie_id)  # mark seen biar gak dicek ulang tiap jam
            continue
        release_data = get_movie_release_dates(movie_id)
        certification = find_movie_certification(release_data, REGION)
        send_telegram(
            format_message(movie, category_label, certification, "movie"),
            movie.get("poster_path"),
        )
        seen.append(movie_id)
    state[state_key] = seen


def process_tv(items, state_key, state, category_label):
    seen = state[state_key]
    for show in items:
        tv_id = show["id"]
        if tv_id in seen:
            continue
        if is_indonesian_tv(show):
            seen.append(tv_id)
            continue
        ratings_data = get_tv_content_ratings(tv_id)
        certification = find_tv_certification(ratings_data, REGION)
        send_telegram(
            format_message(show, category_label, certification, "tv"),
            show.get("poster_path"),
        )
        seen.append(tv_id)
    state[state_key] = seen


def process_movie_format_releases(candidates, state):
    today = datetime.utcnow().date()

    for movie_id, movie in candidates.items():
        if movie_id in state["movie_digital"] and movie_id in state["movie_physical"]:
            continue
        if is_indonesian_movie(movie):
            continue

        release_data = get_movie_release_dates(movie_id)
        certification = find_movie_certification(release_data, REGION)

        digital_date = find_release_date(release_data, REGION, TYPE_DIGITAL) or \
            find_release_date(release_data, "US", TYPE_DIGITAL)
        physical_date = find_release_date(release_data, REGION, TYPE_PHYSICAL) or \
            find_release_date(release_data, "US", TYPE_PHYSICAL)

        if digital_date and movie_id not in state["movie_digital"]:
            d = datetime.strptime(digital_date, "%Y-%m-%d").date()
            if d <= today:
                send_telegram(
                    format_message(movie, "Sudah Rilis Digital", certification, "movie"),
                    movie.get("poster_path"),
                )
                state["movie_digital"].append(movie_id)

        if physical_date and movie_id not in state["movie_physical"]:
            d = datetime.strptime(physical_date, "%Y-%m-%d").date()
            if d <= today:
                send_telegram(
                    format_message(movie, "Sudah Rilis Blu-ray", certification, "movie"),
                    movie.get("poster_path"),
                )
                state["movie_physical"].append(movie_id)


def main():
    state = load_state()

    now_playing_movies = get_now_playing_movies()
    process_movies(now_playing_movies, "movie_now_playing", state, "Lagi Tayang di Bioskop")

    upcoming_movies = get_upcoming_movies()
    process_movies(upcoming_movies, "movie_upcoming", state, "Coming Soon")

    movie_candidates = {m["id"]: m for m in now_playing_movies + upcoming_movies}
    process_movie_format_releases(movie_candidates, state)

    on_the_air_tv = get_on_the_air_tv()
    process_tv(on_the_air_tv, "tv_on_the_air", state, "Series Lagi Tayang")

    upcoming_tv = get_upcoming_tv()
    process_tv(upcoming_tv, "tv_upcoming", state, "Series Coming Soon")

    save_state(state)


if __name__ == "__main__":
    main()
