import time
import asyncio
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.error import TelegramError
from telegram.constants import ParseMode
import config

class BookMyShowMonitor:
    def __init__(self):
        self.driver = None
        self.bot = None
        self.app = None
        self.notified_theatres = {}
        self.last_summary_time = time.time()
        self.start_time = datetime.now()
        self.movie_url = None
        self.check_count = 0
        self.is_monitoring = True
        self.last_scan_time = None
        
    def setup_driver(self):
        """Initialize Chrome WebDriver"""
        print("🔧 Setting up Chrome WebDriver...")
        chrome_options = Options()
        chrome_options.add_argument('--headless=new')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.binary_location = '/usr/bin/chromium'
        
        try:
            self.driver = webdriver.Chrome(options=chrome_options)
            print("✅ Browser initialized successfully")
            return True
        except Exception as e:
            print(f"❌ Failed: {e}")
            return False
    
    def setup_telegram(self):
        """Initialize Telegram Bot"""
        try:
            self.app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()
            self.bot = self.app.bot
            
            self.app.add_handler(CommandHandler("start", self.cmd_start))
            self.app.add_handler(CommandHandler("status", self.cmd_status))
            self.app.add_handler(CallbackQueryHandler(self.button_callback))
            
            print(f"✅ Telegram bot initialized")
            return True
        except Exception as e:
            print(f"❌ Failed: {e}")
            return False
    
    def get_main_keyboard(self):
        """Get inline keyboard"""
        keyboard = [
            [
                InlineKeyboardButton("🔄 Refresh", callback_data="refresh"),
                InlineKeyboardButton("📊 Status", callback_data="status")
            ],
            [
                InlineKeyboardButton("🎭 Theatres", callback_data="theatres"),
                InlineKeyboardButton("ℹ️ Help", callback_data="help")
            ]
        ]
        return InlineKeyboardMarkup(keyboard)
    
    async def send_telegram_message(self, message, reply_markup=None):
        """Send message to all chats"""
        for chat_id in config.TELEGRAM_CHAT_IDS:
            try:
                await self.bot.send_message(
                    chat_id=chat_id,
                    text=message,
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=reply_markup
                )
            except:
                pass
    
    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        message = f"""
🎬 *BookMyShow Monitor Bot*

📽️ Movie: {config.MOVIE_NAME}
📍 City: {config.CITY}
📅 Date: {config.FULL_DATE}

✅ Bot is monitoring!
Use buttons below for quick actions.
"""
        await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN, reply_markup=self.get_main_keyboard())
    
    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command"""
        uptime = datetime.now() - self.start_time
        hours = int(uptime.total_seconds() // 3600)
        minutes = int((uptime.total_seconds() % 3600) // 60)
        
        message = f"""
📊 *Bot Status*

✅ Status: {'Active' if self.is_monitoring else 'Paused'}
🕐 Uptime: {hours}h {minutes}m
🔍 Checks: {self.check_count}
🎭 Theatres Found: {len(self.notified_theatres)}
"""
        await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN, reply_markup=self.get_main_keyboard())
    
    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle button clicks"""
        query = update.callback_query
        await query.answer()
        
        if query.data == "status":
            uptime = datetime.now() - self.start_time
            hours = int(uptime.total_seconds() // 3600)
            minutes = int((uptime.total_seconds() % 3600) // 60)
            
            message = f"""
📊 *Bot Status*

✅ Status: {'Active' if self.is_monitoring else 'Paused'}
🕐 Uptime: {hours}h {minutes}m
🔍 Checks: {self.check_count}
🎭 Theatres: {len(self.notified_theatres)}
"""
            await query.edit_message_text(message, parse_mode=ParseMode.MARKDOWN, reply_markup=self.get_main_keyboard())
        
        elif query.data == "theatres":
            if not self.notified_theatres:
                message = "⏳ No theatres opened yet."
            else:
                theatres_list = []
                for name, times in self.notified_theatres.items():
                    theatres_list.append(f"🎭 {name}\n⏰ {', '.join(times[:3])}")
                message = "🎭 *Opened Theatres:*\n\n" + "\n\n".join(theatres_list[:5])
            
            await query.edit_message_text(message, parse_mode=ParseMode.MARKDOWN, reply_markup=self.get_main_keyboard())
        
        elif query.data == "refresh":
            await query.edit_message_text("🔄 Refreshing...", reply_markup=self.get_main_keyboard())
            await self.perform_refresh()
        
        elif query.data == "help":
            message = """
📚 *Help*

🔄 Refresh - Force check now
📊 Status - View bot status
🎭 Theatres - See opened theatres

Bot checks every 10 seconds automatically.
"""
            await query.edit_message_text(message, parse_mode=ParseMode.MARKDOWN, reply_markup=self.get_main_keyboard())
    
    async def perform_refresh(self):
        """Force refresh"""
        if self.driver and self.movie_url:
            self.driver.refresh()
            time.sleep(3)
            await self.scan_and_notify()
    
    async def send_welcome_message(self):
        """Send startup message"""
        message = f"""
🎬 *Monitor Started!*

📽️ {config.MOVIE_NAME}
📍 {config.CITY}
📅 {config.FULL_DATE}

✅ Monitoring every 10 seconds
🔔 You'll get instant alerts!
"""
        await self.send_telegram_message(message, reply_markup=self.get_main_keyboard())
    
    def find_movie_url(self):
        """Find movie URL"""
        try:
            print(f"🔍 Searching for {config.MOVIE_NAME}...")
            self.driver.get(config.BOOKMYSHOW_CHENNAI_MOVIES)
            time.sleep(5)
            
            search_text = config.MOVIE_NAME.lower()
            movie_links = self.driver.find_elements(By.XPATH, 
                f"//a[contains(@href, '/movies/') and contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{search_text}')]")
            
            if movie_links:
                url = movie_links[0].get_attribute('href')
                print(f"✅ Found: {url}")
                return url
            
            movie_slug = config.MOVIE_NAME.lower().replace(' ', '-')
            url = f"{config.BOOKMYSHOW_BASE_URL}/chennai/movies/{movie_slug}/ET00388929"
            print(f"⚠️ Using: {url}")
            return url
        except Exception as e:
            print(f"❌ Error: {e}")
            return None
    
    def select_date(self):
        """Select monitoring date"""
        try:
            time.sleep(2)
            date_elements = self.driver.find_elements(By.XPATH, 
                f"//*[contains(text(), '{config.MONITOR_DATE}')]")
            
            if date_elements:
                date_elements[0].click()
                time.sleep(2)
                print(f"✅ Selected: {config.MONITOR_DATE}")
                return True
            return True
        except:
            return True
    
    def scan_theatres(self):
        """Scan all theatres"""
        theatres_data = {}
        try:
            time.sleep(3)
            theatre_elements = self.driver.find_elements(By.XPATH, 
                "//div[contains(@class, 'venue-')] | //li[contains(@class, '__venue')]")
            
            for elem in theatre_elements:
                try:
                    name_elem = elem.find_elements(By.XPATH, 
                        ".//a[contains(@class, 'name')] | .//strong | .//h3")
                    
                    if not name_elem:
                        continue
                    
                    theatre_name = name_elem[0].text.strip()
                    if not theatre_name:
                        continue
                    
                    showtime_elements = elem.find_elements(By.XPATH, 
                        ".//a[contains(@class, 'showtime')] | .//button[contains(@class, 'session')]")
                    
                    showtimes = []
                    for st in showtime_elements:
                        text = st.text.strip()
                        if text and text not in ['', 'SOLD OUT', 'FILLING FAST']:
                            if any(c.isdigit() for c in text):
                                showtimes.append(text)
                    
                    if showtimes:
                        theatres_data[theatre_name] = list(set(showtimes))
                        print(f"  🎬 {theatre_name}: {len(showtimes)} shows")
                except:
                    continue
            
            print(f"📊 Total: {len(theatres_data)} theatres")
        except Exception as e:
            print(f"❌ Scan error: {e}")
        
        return theatres_data
    
    async def check_new_theatres(self, current_theatres):
        """Check for new theatres"""
        for theatre_name, showtimes in current_theatres.items():
            if theatre_name not in self.notified_theatres:
                self.notified_theatres[theatre_name] = showtimes
                
                times_str = '\n'.join([f"  ⏰ {t}" for t in sorted(showtimes)])
                message = f"""
🎉 *NEW THEATRE OPENED!*

🎭 {theatre_name}
📅 {config.FULL_DATE}
📍 {config.CITY}

🕐 *Shows:*
{times_str}

🔗 Book now on BookMyShow!
"""
                await self.send_telegram_message(message, reply_markup=self.get_main_keyboard())
                print(f"🔔 ALERT: {theatre_name}")
    
    async def scan_and_notify(self):
        """Scan and send notifications"""
        current_theatres = self.scan_theatres()
        self.last_scan_time = datetime.now()
        
        if current_theatres:
            await self.check_new_theatres(current_theatres)
    
    async def monitor_loop(self):
        """Main monitoring loop"""
        self.movie_url = self.find_movie_url()
        
        if not self.movie_url:
            await self.send_telegram_message("❌ Could not find movie page")
            print("⚠️ Keeping alive...")
            while True:
                await asyncio.sleep(60)
            return
        
        print(f"🌐 Opening: {self.movie_url}")
        self.driver.get(self.movie_url)
        time.sleep(4)
        self.select_date()
        
        last_refresh = time.time()
        
        while True:
            try:
                if not self.is_monitoring:
                    await asyncio.sleep(5)
                    continue
                
                self.check_count += 1
                print(f"\n{'='*50}")
                print(f"🔄 Check #{self.check_count} at {datetime.now().strftime('%H:%M:%S')}")
                print(f"{'='*50}")
                
                await self.scan_and_notify()
                
                current_time = time.time()
                if current_time - last_refresh >= config.PAGE_REFRESH_INTERVAL:
                    print("🔄 Refreshing page...")
                    self.driver.refresh()
                    time.sleep(4)
                    self.select_date()
                    last_refresh = current_time
                
                print(f"⏸️  Waiting {config.POLL_INTERVAL} seconds...")
                await asyncio.sleep(config.POLL_INTERVAL)
                
            except Exception as e:
                print(f"❌ Error: {e}")
                await asyncio.sleep(config.POLL_INTERVAL)
    
    async def run(self):
        """Start the bot"""
        try:
            print("\n" + "="*60)
            print("🚀 BOOKMYSHOW THEATRE MONITOR BOT")
            print("="*60)
            print(f"📽️  Movie: {config.MOVIE_NAME}")
            print(f"📍 City: {config.CITY}")
            print(f"📅 Date: {config.FULL_DATE}")
            print("="*60 + "\n")
            
            if not self.setup_driver():
                print("⚠️ Keeping container alive...")
                while True:
                    await asyncio.sleep(60)
                return
            
            if not self.setup_telegram():
                print("⚠️ Keeping container alive...")
                while True:
                    await asyncio.sleep(60)
                return
            
            print("🤖 Starting Telegram bot...")
            await self.app.initialize()
            await self.app.start()
            asyncio.create_task(self.app.updater.start_polling(drop_pending_updates=True))
            await asyncio.sleep(2)
            
            await self.send_welcome_message()
            await self.monitor_loop()
            
        except Exception as e:
            print(f"❌ Fatal error: {e}")
            while True:
                await asyncio.sleep(60)

def main():
    """Entry point"""
    if not config.TELEGRAM_BOT_TOKEN:
        print("❌ Error: TELEGRAM_BOT_TOKEN not set")
        while True:
            time.sleep(60)
        return
    
    if not config.TELEGRAM_CHAT_IDS:
        print("❌ Error: No chat IDs configured")
        while True:
            time.sleep(60)
        return
    
    print(f"✅ Configuration validated")
    print(f"   Bot Token: {config.TELEGRAM_BOT_TOKEN[:10]}...")
    print(f"   Chat IDs: {len(config.TELEGRAM_CHAT_IDS)} configured\n")
    
    monitor = BookMyShowMonitor()
    asyncio.run(monitor.run())

if __name__ == "__main__":
    main()
