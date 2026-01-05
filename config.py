import os
from dotenv import load_dotenv

load_dotenv()

# Telegram Configuration
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

# Support multiple chat IDs (comma-separated in .env)
CHAT_IDS_STR = os.getenv('TELEGRAM_CHAT_IDS', '')
TELEGRAM_CHAT_IDS = [chat_id.strip() for chat_id in CHAT_IDS_STR.split(',') if chat_id.strip()]

# Fallback to single chat ID if multiple not provided
if not TELEGRAM_CHAT_IDS:
    single_chat_id = os.getenv('TELEGRAM_CHAT_ID')
    if single_chat_id:
        TELEGRAM_CHAT_IDS = [single_chat_id.strip()]

# Movie Configuration
MOVIE_NAME = "Jana Nayagan"
CITY = "Chennai"
MONITOR_DATE = "09 Jan"
FULL_DATE = "09 January"

# BookMyShow URLs
BOOKMYSHOW_BASE_URL = "https://in.bookmyshow.com"
BOOKMYSHOW_CHENNAI_MOVIES = f"{BOOKMYSHOW_BASE_URL}/explore/movies-chennai"

# Bot Settings
POLL_INTERVAL = 10  # seconds
SUMMARY_INTERVAL = 1800  # 30 minutes in seconds
PAGE_REFRESH_INTERVAL = 300  # 5 minutes in seconds

# Admin Chat IDs (who can use control buttons)
ADMIN_CHAT_IDS = TELEGRAM_CHAT_IDS  # All users are admins by default