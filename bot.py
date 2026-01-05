import time
import asyncio
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)
from telegram.constants import ParseMode

import config


class BookMyShowMonitor:
    def __init__(self):
        self.driver = None
        self.app: Application | None = None

        self.notified_theatres = {}
        self.start_time = datetime.now()
        self.check_count = 0
        self.is_monitoring = True
        self.movie_url = None

    # --------------------------------------------------
    # SELENIUM SETUP (RAILWAY SAFE)
    # --------------------------------------------------
    def setup_driver(self) -> bool:
        print("🔧 Setting up Chrome WebDriver...")

        chrome_options = Options()
        chrome_options.binary_location = "/usr/bin/chromium"
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")

        try:
            service = Service("/usr/bin/chromedriver")
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
            print("✅ Chrome WebDriver ready")
            return True
        except Exception as e:
            print(f"❌ WebDriver failed: {e}")
            return False

    # --------------------------------------------------
    # TELEGRAM SETUP
    # --------------------------------------------------
    async def setup_telegram(self) -> bool:
        try:
            self.app = Application.builder().token(
                config.TELEGRAM_BOT_TOKEN
            ).build()

            self.app.add_handler(CommandHandler("start", self.cmd_start))
            self.app.add_handler(CommandHandler("status", self.cmd_status))
            self.app.add_handler(CallbackQueryHandler(self.button_callback))

            await self.app.initialize()
            await self.app.start()
            await self.app.bot.initialize()

            print("✅ Telegram bot initialized")
            return True
        except Exception as e:
            print(f"❌ Telegram init failed: {e}")
            return False

    # --------------------------------------------------
    # UI
    # --------------------------------------------------
    def keyboard(self):
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🔄 Refresh", callback_data="refresh"),
                InlineKeyboardButton("📊 Status", callback_data="status"),
            ],
            [
                InlineKeyboardButton("🎭 Theatres", callback_data="theatres"),
                InlineKeyboardButton("ℹ️ Help", callback_data="help"),
            ],
        ])

    async def send_all(self, text: str):
        for cid in config.TELEGRAM_CHAT_IDS:
            try:
                await self.app.bot.send_message(
                    chat_id=cid,
                    text=text,
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=self.keyboard(),
                )
            except:
                pass

    # --------------------------------------------------
    # COMMANDS
    # --------------------------------------------------
    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        msg = (
            "🎬 *BookMyShow Monitor*\n\n"
            f"📽️ Movie: {config.MOVIE_NAME}\n"
            f"📍 City: {config.CITY}\n"
            f"📅 Date: {config.FULL_DATE}\n\n"
            "✅ Monitoring started"
        )
        await update.message.reply_text(
            msg, parse_mode=ParseMode.MARKDOWN, reply_markup=self.keyboard()
        )

    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        uptime = datetime.now() - self.start_time
        msg = (
            "📊 *Bot Status*\n\n"
            f"🟢 Active: {self.is_monitoring}\n"
            f"⏱ Uptime: {uptime}\n"
            f"🔍 Checks: {self.check_count}\n"
            f"🎭 Theatres: {len(self.notified_theatres)}"
        )
        await update.message.reply_text(
            msg, parse_mode=ParseMode.MARKDOWN, reply_markup=self.keyboard()
        )

    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        q = update.callback_query
        await q.answer()

        if q.data == "refresh":
            await q.edit_message_text("🔄 Refreshing…")
            await self.scan_and_notify()

        elif q.data == "status":
            await self.cmd_status(update, context)

        elif q.data == "theatres":
            if not self.notified_theatres:
                txt = "⏳ No theatres opened yet"
            else:
                txt = "🎭 *Opened Theatres*\n\n"
                for t, times in list(self.notified_theatres.items())[:5]:
                    txt += f"🎬 {t}\n⏰ {', '.join(times[:4])}\n\n"
            await q.edit_message_text(
                txt, parse_mode=ParseMode.MARKDOWN, reply_markup=self.keyboard()
            )

        elif q.data == "help":
            await q.edit_message_text(
                "ℹ️ *Help*\n\n"
                "🔄 Refresh – Scan now\n"
                "📊 Status – Bot status\n"
                "🎭 Theatres – Opened cinemas",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=self.keyboard(),
            )

    # --------------------------------------------------
    # BOOKMYSHOW LOGIC
    # --------------------------------------------------
    def find_movie_url(self):
        print("🔍 Finding movie page…")
        self.driver.get(config.BOOKMYSHOW_CHENNAI_MOVIES)
        time.sleep(4)

        slug = config.MOVIE_NAME.lower().replace(" ", "-")
        return f"{config.BOOKMYSHOW_BASE_URL}/chennai/movies/{slug}"

    def scan_theatres(self):
        theatres = {}
        try:
            time.sleep(3)
            venues = self.driver.find_elements(By.XPATH, "//li[contains(@class,'venue')]")
            for v in venues:
                name = v.text.split("\n")[0].strip()
                times = [
                    t.text.strip()
                    for t in v.find_elements(By.XPATH, ".//a")
                    if t.text.strip() and any(c.isdigit() for c in t.text)
                ]
                if name and times:
                    theatres[name] = list(set(times))
        except Exception as e:
            print("❌ Scan error:", e)
        return theatres

    async def scan_and_notify(self):
        self.check_count += 1
        theatres = self.scan_theatres()

        for t, times in theatres.items():
            if t not in self.notified_theatres:
                self.notified_theatres[t] = times
                msg = (
                    "🎉 *NEW THEATRE OPENED!*\n\n"
                    f"🎭 {t}\n"
                    f"📅 {config.FULL_DATE}\n"
                    f"📍 {config.CITY}\n\n"
                    "🕐 Shows:\n" + "\n".join(f"• {x}" for x in times)
                )
                await self.send_all(msg)

    # --------------------------------------------------
    # MAIN LOOP
    # --------------------------------------------------
    async def run(self):
        print("🚀 BOOKMYSHOW MONITOR STARTED")

        if not self.setup_driver():
            while True:
                await asyncio.sleep(60)

        if not await self.setup_telegram():
            while True:
                await asyncio.sleep(60)

        self.movie_url = self.find_movie_url()
        self.driver.get(self.movie_url)

        await self.send_all("✅ *Monitoring started!*")

        while True:
            try:
                await self.scan_and_notify()
                self.driver.refresh()
                await asyncio.sleep(config.POLL_INTERVAL)
            except Exception as e:
                print("❌ Loop error:", e)
                await asyncio.sleep(10)


# --------------------------------------------------
# ENTRY POINT
# --------------------------------------------------
def main():
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_IDS:
        print("❌ Missing Telegram config")
        while True:
            time.sleep(60)

    asyncio.run(BookMyShowMonitor().run())


if __name__ == "__main__":
    main()
