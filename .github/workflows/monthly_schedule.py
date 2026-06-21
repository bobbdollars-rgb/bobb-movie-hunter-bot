"""
BobbMovieHunter - Monthly Schedule Digest
-------------------------------------------
Kirim 1 pesan ringkas tiap tanggal 1, isinya list film & series yang
akan rilis BULAN DEPAN (judul + tanggal + rating). Exclude konten
Indonesia (original_language == "id" ATAU production/origin country == "ID").
"""

import os
import calendar
import requests
from datetime import date

TMDB_API_KEY = os.environ["TMDB_API_KEY"]
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
REGION = os.environ.get("REGION", "ID")

TMDB_BASE = "https://api.themoviedb.org/3"

BULAN_ID = [
    "Januari", "Februari", "Maret", "April", "Mei", "Juni",
    "Juli", "Agustus", "September", "Oktober", "November", "Desember",
]


def next_month_range(today=None):
    today = today or date.today()
    year, month = today.year, today.month
    month += 1
    if month > 12:
        month = 1
        year += 1
    last_day = calendar.monthrange(year, month)[1]
    start = date(year, month, 1)
    end = date(year, month, last_day)
    return start, end, BULAN_ID[month - 1], year


def tmdb_get(path, params=None):
    params = params or {}
    params["api_key"] = TMDB_API_KEY
    params["language"] = "id-ID"
    r = requests.get(f"{TMDB_BASE}{path}", params=params, timeout=15)
    r.raise_for_status()
    return r.json()


def get_movie_details(movie_id):
    return tmdb_get(f"/movie/{movie_id}")


def get_tv_details(tv_id):
    return tmdb_get(f"/tv/{tv_id}")


def is_indonesian_movie(movie):
    if movie.get("original_language") == "id":
        return True
    details = get_movie_details(movie["id"])
    countries = [c["iso_3166_1"] for c in details.get("production_countries", [])]
    return "ID" in countries


def is_indonesian_tv(show):
    if show.get("original_language") == "id":
        return True
    if "ID" in (show.get("origin_country") or []):
        return True
    details = get_tv_details(show["id"])
    countries = [c["iso_3166_1"] for c in details.get("production_countries", [])]
    return "ID" in countries


def get_movies_in_range(start, end, region):
    results = []
    page = 1
    while True:
        data = tmdb_get("/discover/movie", {
            "region": region,
            "with_release_type": "2|3",
            "primary_release_date.gte": start.isoformat(),
            "primary_release_date.lte": end.isoformat(),
            "sort_by": "primary_release_date.asc",
            "page": page,
        })
        results.extend(data.get("results", []))
        if page >= data.get("total_pages", 1) or page >= 5:
            break
        page += 1
    return [m for m in results if not is_indonesian_movie(m)]


def get_tv_in_range(start, end):
    results = []
    page = 1
    while True:
        data = tmdb_get("/discover/tv", {
            "first_air_date.gte": start.isoformat(),
            "first_air_date.lte": end.isoformat(),
            "sort_by": "first_air_date.asc",
            "page": page,
        })
        results.extend(data.get("results", []))
        if page >= data.get("total_pages", 1) or page >= 5:
            break
        page += 1
    return [s for s in results if not is_indonesian_tv(s)]


def build_digest(movies, shows, bulan_label, year):
    lines = [f"📅 <b>Jadwal Rilis {bulan_label} {year}</b>\n"]

    lines.append("🎬 <b>Film</b>")
    if movies:
        for m in movies:
            rating = m.get("vote_average") or 0
            lines.append(f"• {m.get('release_date', '-')} — {m.get('title', 'Unknown')} (⭐ {rating:.1f})")
    else:
        lines.append("Gak ada yang kedetect.")

    lines.append("\n📺 <b>Series</b>")
    if shows:
        for s in shows:
            rating = s.get("vote_average") or 0
            lines.append(f"• {s.get('first_air_date', '-')} — {s.get('name', 'Unknown')} (⭐ {rating:.1f})")
    else:
        lines.append("Gak ada yang kedetect.")

    return "\n".join(lines)


def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
    }
    r = requests.post(url, data=payload, timeout=15)
    r.raise_for_status()


def chunk_message(text, limit=4096):
    if len(text) <= limit:
        return [text]
    chunks, current = [], ""
    for line in text.split("\n"):
        if len(current) + len(line) + 1 > limit:
            chunks.append(current)
            current = line
        else:
            current = f"{current}\n{line}" if current else line
    if current:
        chunks.append(current)
    return chunks


def main():
    start, end, bulan_label, year = next_month_range()
    movies = get_movies_in_range(start, end, REGION)
    shows = get_tv_in_range(start, end)
    digest = build_digest(movies, shows, bulan_label, year)

    for chunk in chunk_message(digest):
        send_telegram(chunk)


if __name__ == "__main__":
    main()
