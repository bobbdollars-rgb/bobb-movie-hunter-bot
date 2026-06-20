import os
import requests
import logging
from datetime import datetime, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TMDB_API_KEY = os.environ["TMDB_API_KEY"]
TMDB_BASE = "https://api.themoviedb.org/3"
TMDB_IMG = "https://image.tmdb.org/t/p/w500"
JUSTWATCH_BASE = "https://www.justwatch.com/id/search?q="

EXCLUDED_COUNTRIES = ["ID"]  # Skip Indonesia
OWNER_CHAT_ID = 680378702  # Bobb chat ID

# ── HELPERS ──────────────────────────────────────────────────────────────────

def tmdb_get(endpoint, params={}):
    params["api_key"] = TMDB_API_KEY
    params["language"] = "id-ID"
    r = requests.get(f"{TMDB_BASE}{endpoint}", params=params, timeout=10)
    return r.json()

def get_release_info(movie_id, media_type="movie"):
    """Get digital & bluray release dates"""
    data = tmdb_get(f"/{media_type}/{movie_id}/release_dates")
    results = data.get("results", [])
    
    theatrical = digital = bluray = None
    for country in results:
        if country["iso_3166_1"] == "US":
            for rel in country.get("release_dates", []):
                rtype = rel.get("type")
                date = rel.get("release_date", "")[:10]
                if rtype == 3 and not theatrical:
                    theatrical = date
                elif rtype in [4, 5] and not digital:
                    digital = date
                elif rtype == 6 and not bluray:
                    bluray = date
    return theatrical, digital, bluray

def get_status_emoji(theatrical, digital, bluray):
    if bluray:
        return "💿 Sudah Bluray (Kualitas MAX!)"
    elif digital:
        return "📺 Sudah Digital/VOD (Kualitas Bening!)"
    elif theatrical:
        return "🎬 Masih di Bioskop"
    return "⏳ Belum Rilis"

def format_movie_card(item, media_type="movie"):
    title = item.get("title") or item.get("name", "Unknown")
    year = (item.get("release_date") or item.get("first_air_date") or "")[:4]
    rating = item.get("vote_average", 0)
    overview = item.get("overview", "Tidak ada sinopsis.")[:300]
    if len(item.get("overview", "")) > 300:
        overview += "..."
    
    stars = "⭐" * min(int(rating / 2), 5)
    
    return (
        f"🎬 *{title}* ({year})\n"
        f"{stars} *{rating:.1f}/10*\n\n"
        f"📖 {overview}"
    )

def format_series_card(item):
    title = item.get("name", "Unknown")
    year = (item.get("first_air_date") or "")[:4]
    rating = item.get("vote_average", 0)
    overview = item.get("overview", "Tidak ada sinopsis.")[:300]
    if len(item.get("overview", "")) > 300:
        overview += "..."
    
    stars = "⭐" * min(int(rating / 2), 5)
    
    return (
        f"📺 *{title}* ({year})\n"
        f"{stars} *{rating:.1f}/10*\n\n"
        f"📖 {overview}"
    )

# ── COMMANDS ──────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🎬 *Selamat datang di Bobb MovieHunter!*\n\n"
        "🔍 Cari film & drama favoritmu:\n\n"
        "📌 *Perintah:*\n"
        "/search `<judul>` — Cari film\n"
        "/drama `<judul>` — Cari series/drama\n"
        "/trending — Film trending minggu ini\n"
        "/korea — Drama Korea terpopuler\n"
        "/china — Drama China terpopuler\n"
        "/japan — Drama Jepang terpopuler\n"
        "/help — Bantuan\n\n"
        "💡 Atau langsung ketik judul film!"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)

async def trending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔄 Mencari film trending...")
    data = tmdb_get("/trending/movie/week")
    results = data.get("results", [])[:5]
    
    if not results:
        await update.message.reply_text("❌ Tidak ada data trending.")
        return
    
    text = "🔥 *Film Trending Minggu Ini:*\n\n"
    keyboard = []
    for i, m in enumerate(results, 1):
        title = m.get("title", "?")
        year = (m.get("release_date") or "")[:4]
        rating = m.get("vote_average", 0)
        text += f"{i}. *{title}* ({year}) ⭐{rating:.1f}\n"
        keyboard.append([InlineKeyboardButton(
            f"📋 {title}", callback_data=f"movie_{m['id']}"
        )])
    
    await update.message.reply_text(
        text, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def search_movie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args)
    if not query:
        await update.message.reply_text("❌ Ketik: /search <judul film>")
        return
    
    await update.message.reply_text(f"🔍 Mencari *{query}*...", parse_mode="Markdown")
    data = tmdb_get("/search/movie", {"query": query})
    results = [r for r in data.get("results", [])
               if r.get("original_language") != "id"][:5]
    
    if not results:
        await update.message.reply_text("❌ Film tidak ditemukan.")
        return
    
    keyboard = []
    text = f"🎬 *Hasil pencarian: {query}*\n\n"
    for i, m in enumerate(results, 1):
        title = m.get("title", "?")
        year = (m.get("release_date") or "")[:4]
        rating = m.get("vote_average", 0)
        text += f"{i}. *{title}* ({year}) ⭐{rating:.1f}\n"
        keyboard.append([InlineKeyboardButton(
            f"📋 {title} ({year})", callback_data=f"movie_{m['id']}"
        )])
    
    await update.message.reply_text(
        text, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def search_drama(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args)
    if not query:
        await update.message.reply_text("❌ Ketik: /drama <judul series>")
        return
    
    await update.message.reply_text(f"🔍 Mencari drama *{query}*...", parse_mode="Markdown")
    data = tmdb_get("/search/tv", {"query": query})
    results = [r for r in data.get("results", [])
               if r.get("original_language") != "id"][:5]
    
    if not results:
        await update.message.reply_text("❌ Drama tidak ditemukan.")
        return
    
    keyboard = []
    text = f"📺 *Hasil pencarian: {query}*\n\n"
    for i, m in enumerate(results, 1):
        title = m.get("name", "?")
        year = (m.get("first_air_date") or "")[:4]
        rating = m.get("vote_average", 0)
        text += f"{i}. *{title}* ({year}) ⭐{rating:.1f}\n"
        keyboard.append([InlineKeyboardButton(
            f"📋 {title} ({year})", callback_data=f"tv_{m['id']}"
        )])
    
    await update.message.reply_text(
        text, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def browse_country_drama(update: Update, context: ContextTypes.DEFAULT_TYPE, country_code: str, label: str):
    await update.message.reply_text(f"🔍 Mencari drama {label} terpopuler...")
    data = tmdb_get("/discover/tv", {
        "with_origin_country": country_code,
        "sort_by": "popularity.desc",
        "page": 1
    })
    results = data.get("results", [])[:8]
    
    if not results:
        await update.message.reply_text("❌ Tidak ada data.")
        return
    
    text = f"📺 *Drama {label} Terpopuler:*\n\n"
    keyboard = []
    for i, m in enumerate(results, 1):
        title = m.get("name", "?")
        year = (m.get("first_air_date") or "")[:4]
        rating = m.get("vote_average", 0)
        text += f"{i}. *{title}* ({year}) ⭐{rating:.1f}\n"
        keyboard.append([InlineKeyboardButton(
            f"📋 {title}", callback_data=f"tv_{m['id']}"
        )])
    
    await update.message.reply_text(
        text, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def korea(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await browse_country_drama(update, context, "KR", "Korea 🇰🇷")

async def china(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await browse_country_drama(update, context, "CN", "China 🇨🇳")

async def japan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await browse_country_drama(update, context, "JP", "Jepang 🇯🇵")

async def text_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip()
    if len(query) < 2:
        return
    
    await update.message.reply_text(f"🔍 Mencari *{query}*...", parse_mode="Markdown")
    
    movie_data = tmdb_get("/search/movie", {"query": query})
    tv_data = tmdb_get("/search/tv", {"query": query})
    
    movies = [r for r in movie_data.get("results", [])
              if r.get("original_language") != "id"][:3]
    tvs = [r for r in tv_data.get("results", [])
           if r.get("original_language") != "id"][:3]
    
    if not movies and not tvs:
        await update.message.reply_text("❌ Tidak ditemukan. Coba judul lain.")
        return
    
    keyboard = []
    text = f"🎬 *Hasil: {query}*\n\n"
    
    if movies:
        text += "🎬 *Film:*\n"
        for m in movies:
            title = m.get("title", "?")
            year = (m.get("release_date") or "")[:4]
            rating = m.get("vote_average", 0)
            text += f"• {title} ({year}) ⭐{rating:.1f}\n"
            keyboard.append([InlineKeyboardButton(
                f"🎬 {title} ({year})", callback_data=f"movie_{m['id']}"
            )])
    
    if tvs:
        text += "\n📺 *Series/Drama:*\n"
        for m in tvs:
            title = m.get("name", "?")
            year = (m.get("first_air_date") or "")[:4]
            rating = m.get("vote_average", 0)
            text += f"• {title} ({year}) ⭐{rating:.1f}\n"
            keyboard.append([InlineKeyboardButton(
                f"📺 {title} ({year})", callback_data=f"tv_{m['id']}"
            )])
    
    await update.message.reply_text(
        text, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ── CALLBACKS ─────────────────────────────────────────────────────────────────

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data.startswith("movie_"):
        movie_id = data.split("_")[1]
        await show_movie_detail(query, movie_id)
    elif data.startswith("tv_"):
        tv_id = data.split("_")[1]
        await show_tv_detail(query, tv_id)
    elif data == "notif_coming":
        await query.message.reply_text("⏳ Mengambil data coming soon...")
        await send_coming_soon(context)
    elif data == "notif_playing":
        await query.message.reply_text("⏳ Mengambil data now playing...")
        await send_now_playing(context)
    elif data == "notif_trending":
        await query.message.reply_text("⏳ Mengambil data trending...")
        await send_trending_daily(context)

async def show_movie_detail(query, movie_id):
    item = tmdb_get(f"/movie/{movie_id}", {"append_to_response": "credits"})
    
    title = item.get("title", "?")
    year = (item.get("release_date") or "")[:4]
    rating = item.get("vote_average", 0)
    runtime = item.get("runtime", 0)
    genres = ", ".join([g["name"] for g in item.get("genres", [])])
    overview = item.get("overview", "Tidak ada sinopsis.")[:400]
    status = item.get("status", "")
    
    # Cast top 5
    cast = item.get("credits", {}).get("cast", [])[:5]
    cast_str = ", ".join([c["name"] for c in cast]) if cast else "-"
    
    # Release dates
    theatrical, digital, bluray = get_release_info(movie_id, "movie")
    quality_status = get_status_emoji(theatrical, digital, bluray)
    
    hours = runtime // 60
    mins = runtime % 60
    duration = f"{hours}j {mins}m" if hours else f"{mins}m"
    
    text = (
        f"🎬 *{title}* ({year})\n"
        f"⭐ *{rating:.1f}/10*\n"
        f"⏱ {duration} | 🎭 {genres}\n\n"
        f"📖 {overview}\n\n"
        f"👥 *Cast:* {cast_str}\n\n"
        f"📅 *Rilis Bioskop:* {theatrical or '-'}\n"
        f"📺 *Rilis Digital:* {digital or '-'}\n"
        f"💿 *Rilis Bluray:* {bluray or '-'}\n\n"
        f"🎯 *Status Kualitas:*\n{quality_status}"
    )
    
    poster = item.get("poster_path")
    justwatch_url = f"{JUSTWATCH_BASE}{requests.utils.quote(title)}"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📺 Where to Watch", url=justwatch_url)],
        [InlineKeyboardButton("🎬 Trailer YouTube", url=f"https://www.youtube.com/results?search_query={requests.utils.quote(title+' '+year+' trailer')}")]
    ])
    
    if poster:
        await query.message.reply_photo(
            photo=f"{TMDB_IMG}{poster}",
            caption=text,
            parse_mode="Markdown",
            reply_markup=keyboard
        )
    else:
        await query.message.reply_text(text, parse_mode="Markdown", reply_markup=keyboard)

async def show_tv_detail(query, tv_id):
    item = tmdb_get(f"/tv/{tv_id}", {"append_to_response": "credits"})
    
    title = item.get("name", "?")
    year = (item.get("first_air_date") or "")[:4]
    rating = item.get("vote_average", 0)
    episodes = item.get("number_of_episodes", 0)
    seasons = item.get("number_of_seasons", 0)
    genres = ", ".join([g["name"] for g in item.get("genres", [])])
    overview = item.get("overview", "Tidak ada sinopsis.")[:400]
    status = item.get("status", "")
    network = ", ".join([n["name"] for n in item.get("networks", [])])
    origin = ", ".join(item.get("origin_country", []))
    
    # Cast
    cast = item.get("credits", {}).get("cast", [])[:5]
    cast_str = ", ".join([c["name"] for c in cast]) if cast else "-"
    
    status_icon = "✅ Selesai" if status == "Ended" else "🟢 Ongoing"
    
    text = (
        f"📺 *{title}* ({year})\n"
        f"⭐ *{rating:.1f}/10* | 🌏 {origin}\n"
        f"🎭 {genres}\n\n"
        f"📖 {overview}\n\n"
        f"👥 *Cast:* {cast_str}\n\n"
        f"📡 *Network:* {network or '-'}\n"
        f"🎬 *Season:* {seasons} | 📋 *Episode:* {episodes}\n"
        f"📊 *Status:* {status_icon}"
    )
    
    poster = item.get("poster_path")
    justwatch_url = f"{JUSTWATCH_BASE}{requests.utils.quote(title)}"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📺 Where to Watch", url=justwatch_url)],
        [InlineKeyboardButton("🎬 Trailer YouTube", url=f"https://www.youtube.com/results?search_query={requests.utils.quote(title+' trailer')}")]
    ])
    
    if poster:
        await query.message.reply_photo(
            photo=f"{TMDB_IMG}{poster}",
            caption=text,
            parse_mode="Markdown",
            reply_markup=keyboard
        )
    else:
        await query.message.reply_text(text, parse_mode="Markdown", reply_markup=keyboard)

# ── MAIN ──────────────────────────────────────────────────────────────────────

# ── DAILY NOTIFICATIONS ───────────────────────────────────────────────────────

async def send_coming_soon(context):
    """Kirim film yang akan segera rilis"""
    try:
        data = tmdb_get("/movie/upcoming", {"region": "US"})
        results = [r for r in data.get("results", [])
                   if r.get("original_language") != "id"][:5]
        
        if not results:
            return
        
        text = "🎬 *Film Yang Akan Segera Rilis!*\n\n"
        keyboard = []
        for i, m in enumerate(results, 1):
            title = m.get("title", "?")
            date = (m.get("release_date") or "")[:10]
            rating = m.get("vote_average", 0)
            text += f"{i}. *{title}*\n📅 {date} | ⭐{rating:.1f}\n\n"
            keyboard.append([InlineKeyboardButton(
                f"📋 {title}", callback_data=f"movie_{m['id']}"
            )])
        
        await context.bot.send_message(
            chat_id=OWNER_CHAT_ID,
            text=text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        logger.info("✅ Coming soon notification sent!")
    except Exception as e:
        logger.error(f"Error sending coming soon: {e}")

async def send_now_playing(context):
    """Kirim film yang lagi tayang di bioskop"""
    try:
        data = tmdb_get("/movie/now_playing", {"region": "US"})
        results = [r for r in data.get("results", [])
                   if r.get("original_language") != "id"][:5]
        
        if not results:
            return
        
        text = "🍿 *Film Lagi Tayang di Bioskop!*\n\n"
        keyboard = []
        for i, m in enumerate(results, 1):
            title = m.get("title", "?")
            rating = m.get("vote_average", 0)
            text += f"{i}. *{title}* ⭐{rating:.1f}\n"
            keyboard.append([InlineKeyboardButton(
                f"📋 {title}", callback_data=f"movie_{m['id']}"
            )])
        
        await context.bot.send_message(
            chat_id=OWNER_CHAT_ID,
            text=text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        logger.info("✅ Now playing notification sent!")
    except Exception as e:
        logger.error(f"Error sending now playing: {e}")

async def send_trending_daily(context):
    """Kirim trending harian"""
    try:
        data = tmdb_get("/trending/all/day")
        results = [r for r in data.get("results", [])
                   if r.get("original_language") != "id"][:5]
        
        if not results:
            return
        
        text = "🔥 *Trending Hari Ini!*\n\n"
        keyboard = []
        for i, m in enumerate(results, 1):
            title = m.get("title") or m.get("name", "?")
            media = "🎬" if m.get("media_type") == "movie" else "📺"
            rating = m.get("vote_average", 0)
            text += f"{i}. {media} *{title}* ⭐{rating:.1f}\n"
            ctype = m.get("media_type", "movie")
            keyboard.append([InlineKeyboardButton(
                f"{media} {title}", callback_data=f"{ctype}_{m['id']}"
            )])
        
        await context.bot.send_message(
            chat_id=OWNER_CHAT_ID,
            text=text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        logger.info("✅ Trending daily notification sent!")
    except Exception as e:
        logger.error(f"Error sending trending: {e}")

async def notif_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manual trigger notifikasi"""
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎬 Coming Soon", callback_data="notif_coming")],
        [InlineKeyboardButton("🍿 Now Playing", callback_data="notif_playing")],
        [InlineKeyboardButton("🔥 Trending Hari Ini", callback_data="notif_trending")],
    ])
    await update.message.reply_text(
        "📲 *Pilih notifikasi yang mau dikirim:*",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("trending", trending))
    app.add_handler(CommandHandler("search", search_movie))
    app.add_handler(CommandHandler("drama", search_drama))
    app.add_handler(CommandHandler("korea", korea))
    app.add_handler(CommandHandler("china", china))
    app.add_handler(CommandHandler("japan", japan))
    app.add_handler(CommandHandler("notif", notif_cmd))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_search))

    # ── JADWAL NOTIFIKASI OTOMATIS (UTC = WIB-7) ──
    from datetime import time as dtime
    job_queue = app
