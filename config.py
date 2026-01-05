import os

# ==============================
# TELEGRAM
# ==============================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

TELEGRAM_CHAT_IDS = [
    int(x) for x in os.getenv("TELEGRAM_CHAT_IDS", "").split(",") if x.strip()
]

# ==============================
# MOVIE CONFIG
# ==============================
MOVIE_NAME = os.getenv("MOVIE_NAME", "Jana Nayagan")
CITY = os.getenv("CITY", "Chennai")
FULL_DATE = os.getenv("FULL_DATE", "09 January")

# ==============================
# BOOKMYSHOW URLS
# ==============================
BOOKMYSHOW_BASE_URL = "https://in.bookmyshow.com"
BOOKMYSHOW_CHENNAI_MOVIES = "https://in.bookmyshow.com/chennai/movies"

# ==============================
# BOT SETTINGS
# ==============================
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "10"))
