import time
import asyncio
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
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
        self.notified_theatres = {}  # {theatre_name: [showtimes]}
        self.last_summary_time = time.time()
        self.start_time = datetime.now()
        self.movie_url = None
        self.check_count = 0
        self.is_monitoring = True
        self.last_scan_time = None
        self.monitoring_task = None
        
  def setup_driver(self):
    """Initialize Selenium WebDriver with headless Chrome"""
    print("🔧 Setting up Chrome WebDriver...")
    chrome_options = Options()
    chrome_options.add_argument('--headless=new')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.binary_location = '/usr/bin/chromium'
    
    try:
        self.driver = webdriver.Chrome(options=chrome_options)
        print("✅ Browser initialized successfully")
        return True
    except Exception as e:
        print(f"❌ Failed: {e}")
        return False
        
    def setup_telegram(self):
        """Initialize Telegram Bot with handlers"""
        try:
            self.app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()
            self.bot = self.app.bot
            
            # Add command handlers
            self.app.add_handler(CommandHandler("start", self.cmd_start))
            self.app.add_handler(CommandHandler("help", self.cmd_help))
            self.app.add_handler(CommandHandler("status", self.cmd_status))
            self.app.add_handler(CommandHandler("theatres", self.cmd_theatres))
            self.app.add_handler(CommandHandler("refresh", self.cmd_refresh))
            self.app.add_handler(CommandHandler("stop", self.cmd_stop))
            self.app.add_handler(CommandHandler("resume", self.cmd_resume))
            
            # Add callback handler for inline buttons
            self.app.add_handler(CallbackQueryHandler(self.button_callback))
            
            print(f"✅ Telegram bot initialized for {len(config.TELEGRAM_CHAT_IDS)} chat(s)")
            return True
        except Exception as e:
            print(f"❌ Failed to initialize Telegram bot: {e}")
            return False
    
    def get_main_keyboard(self):
        """Get main inline keyboard with all buttons"""
        keyboard = [
            [
                InlineKeyboardButton("🔄 Refresh Now", callback_data="refresh"),
                InlineKeyboardButton("📊 Current Status", callback_data="status")
            ],
            [
                InlineKeyboardButton("🎭 Theatres Open", callback_data="theatres"),
                InlineKeyboardButton("📈 Statistics", callback_data="stats")
            ],
            [
                InlineKeyboardButton("⏸️ Pause Monitor", callback_data="pause"),
                InlineKeyboardButton("▶️ Resume Monitor", callback_data="resume")
            ],
            [
                InlineKeyboardButton("ℹ️ Help", callback_data="help"),
                InlineKeyboardButton("🔗 BookMyShow", url=f"{config.BOOKMYSHOW_BASE_URL}/chennai")
            ]
        ]
        return InlineKeyboardMarkup(keyboard)
    
    async def send_telegram_message(self, message, parse_mode=ParseMode.MARKDOWN, reply_markup=None):
        """Send message to all configured Telegram chats"""
        success_count = 0
        for chat_id in config.TELEGRAM_CHAT_IDS:
            try:
                await self.bot.send_message(
                    chat_id=chat_id,
                    text=message,
                    parse_mode=parse_mode,
                    reply_markup=reply_markup
                )
                success_count += 1
            except TelegramError as e:
                print(f"❌ Failed to send message to chat {chat_id}: {e}")
            except Exception as e:
                print(f"❌ Unexpected error sending to chat {chat_id}: {e}")
        
        if success_count > 0:
            print(f"📤 Message sent to {success_count}/{len(config.TELEGRAM_CHAT_IDS)} chat(s)")
        return success_count > 0
    
    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        message = f"""
👋 *Welcome to BookMyShow Monitor Bot!*

━━━━━━━━━━━━━━━━━━━━
🎬 *Currently Monitoring:*
📽️ Movie: {config.MOVIE_NAME}
📍 City: {config.CITY}
📅 Date: {config.FULL_DATE}
━━━━━━━━━━━━━━━━━━━━

✨ *Quick Actions:*
Use the buttons below to control the bot!

🔔 You'll receive instant alerts when theatres open bookings.

Type /help for more information.
"""
        await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN, reply_markup=self.get_main_keyboard())
    
    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        message = f"""
📚 *Bot Commands & Features*

━━━━━━━━━━━━━━━━━━━━
*Available Commands:*

/start - Show welcome message
/help - Show this help message
/status - Current monitoring status
/theatres - List all opened theatres
/refresh - Force refresh data now
/stop - Pause monitoring
/resume - Resume monitoring

━━━━━━━━━━━━━━━━━━━━
*Inline Buttons:*

🔄 *Refresh Now* - Get latest data
📊 *Current Status* - Bot status info
🎭 *Theatres Open* - See all theatres
📈 *Statistics* - View bot stats
⏸️ *Pause/Resume* - Control monitoring

━━━━━━━━━━━━━━━━━━━━
*Automatic Features:*

✅ Checks every {config.POLL_INTERVAL} seconds
✅ Instant alerts for new theatres
✅ Summary every 30 minutes
✅ No duplicate notifications

━━━━━━━━━━━━━━━━━━━━
*Movie Details:*
📽️ {config.MOVIE_NAME}
📍 {config.CITY}
📅 {config.FULL_DATE}
"""
        await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN, reply_markup=self.get_main_keyboard())
    
    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command"""
        await self.send_status_message(update.effective_chat.id)
    
    async def cmd_theatres(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /theatres command"""
        await self.send_theatres_list(update.effective_chat.id)
    
    async def cmd_refresh(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /refresh command"""
        await update.message.reply_text("🔄 Refreshing data... Please wait...")
        await self.perform_refresh(update.effective_chat.id)
    
    async def cmd_stop(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /stop command"""
        if str(update.effective_chat.id) not in config.ADMIN_CHAT_IDS:
            await update.message.reply_text("❌ You don't have permission to stop the monitor.")
            return
        
        self.is_monitoring = False
        await update.message.reply_text("⏸️ *Monitoring Paused*\n\nUse /resume to continue.", parse_mode=ParseMode.MARKDOWN)
    
    async def cmd_resume(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /resume command"""
        if str(update.effective_chat.id) not in config.ADMIN_CHAT_IDS:
            await update.message.reply_text("❌ You don't have permission to resume the monitor.")
            return
        
        self.is_monitoring = True
        await update.message.reply_text("▶️ *Monitoring Resumed*\n\nBot is now actively checking again.", parse_mode=ParseMode.MARKDOWN)
    
    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle inline button callbacks"""
        query = update.callback_query
        await query.answer()
        
        chat_id = query.message.chat_id
        action = query.data
        
        if action == "refresh":
            await query.edit_message_text("🔄 Refreshing data... Please wait...")
            await self.perform_refresh(chat_id)
            
        elif action == "status":
            await self.send_status_message(chat_id)
            
        elif action == "theatres":
            await self.send_theatres_list(chat_id)
            
        elif action == "stats":
            await self.send_statistics(chat_id)
            
        elif action == "pause":
            if str(chat_id) in config.ADMIN_CHAT_IDS:
                self.is_monitoring = False
                await query.edit_message_text(
                    "⏸️ *Monitoring Paused*\n\nClick Resume to continue.",
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=self.get_main_keyboard()
                )
            else:
                await query.edit_message_text("❌ You don't have permission to pause the monitor.")
                
        elif action == "resume":
            if str(chat_id) in config.ADMIN_CHAT_IDS:
                self.is_monitoring = True
                await query.edit_message_text(
                    "▶️ *Monitoring Resumed*\n\nBot is actively checking again.",
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=self.get_main_keyboard()
                )
            else:
                await query.edit_message_text("❌ You don't have permission to resume the monitor.")
                
        elif action == "help":
            message = f"""
📚 *Quick Help*

🔄 *Refresh* - Get latest theatre data
📊 *Status* - Check if bot is running
🎭 *Theatres* - See opened theatres
📈 *Stats* - View statistics

Bot checks every {config.POLL_INTERVAL}s automatically!
"""
            await query.edit_message_text(message, parse_mode=ParseMode.MARKDOWN, reply_markup=self.get_main_keyboard())
    
    async def send_status_message(self, chat_id):
        """Send current status to a specific chat"""
        uptime = datetime.now() - self.start_time
        hours = int(uptime.total_seconds() // 3600)
        minutes = int((uptime.total_seconds() % 3600) // 60)
        
        status_emoji = "✅" if self.is_monitoring else "⏸️"
        status_text = "Active" if self.is_monitoring else "Paused"
        
        last_check = "Never" if not self.last_scan_time else self.last_scan_time.strftime('%I:%M:%S %p')
        
        message = f"""
📊 *Current Monitor Status*

━━━━━━━━━━━━━━━━━━━━
{status_emoji} *Status:* {status_text}
🕐 *Uptime:* {hours}h {minutes}m
🔍 *Total Checks:* {self.check_count}
🎭 *Theatres Found:* {len(self.notified_theatres)}
⏰ *Last Check:* {last_check}

━━━━━━━━━━━━━━━━━━━━
📽️ *Monitoring:*
Movie: {config.MOVIE_NAME}
City: {config.CITY}
Date: {config.FULL_DATE}

━━━━━━━━━━━━━━━━━━━━
⚙️ *Settings:*
Check Interval: {config.POLL_INTERVAL}s
Summary Interval: {config.SUMMARY_INTERVAL // 60}m

{'✅ Bot is running normally!' if self.is_monitoring else '⏸️ Monitoring is paused.'}
"""
        
        try:
            await self.bot.send_message(
                chat_id=chat_id,
                text=message,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=self.get_main_keyboard()
            )
        except Exception as e:
            print(f"❌ Error sending status: {e}")
    
    async def send_theatres_list(self, chat_id):
        """Send list of opened theatres to a specific chat"""
        if not self.notified_theatres:
            message = f"""
🎭 *Theatres Status*

━━━━━━━━━━━━━━━━━━━━
📽️ Movie: {config.MOVIE_NAME}
📅 Date: {config.FULL_DATE}
📍 City: {config.CITY}

━━━━━━━━━━━━━━━━━━━━
⏳ *No theatres have opened bookings yet.*

✅ Bot is monitoring and will alert you immediately when bookings open!

🔄 Use the Refresh button to check manually.
"""
        else:
            theatres_list = []
            for idx, (theatre_name, showtimes) in enumerate(self.notified_theatres.items(), 1):
                times_str = ', '.join(sorted(showtimes)[:6])
                if len(showtimes) > 6:
                    times_str += f' +{len(showtimes)-6} more'
                theatres_list.append(f"{idx}. *{theatre_name}*\n   ⏰ {times_str}")
            
            theatres_text = '\n\n'.join(theatres_list)
            
            message = f"""
🎭 *Opened Theatres ({len(self.notified_theatres)})*

━━━━━━━━━━━━━━━━━━━━
📽️ {config.MOVIE_NAME}
📅 {config.FULL_DATE}
📍 {config.CITY}

━━━━━━━━━━━━━━━━━━━━

{theatres_text}

━━━━━━━━━━━━━━━━━━━━
🔗 Book now on BookMyShow!
"""
        
        try:
            await self.bot.send_message(
                chat_id=chat_id,
                text=message,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=self.get_main_keyboard()
            )
        except Exception as e:
            print(f"❌ Error sending theatres list: {e}")
    
    async def send_statistics(self, chat_id):
        """Send bot statistics"""
        uptime = datetime.now() - self.start_time
        hours = int(uptime.total_seconds() // 3600)
        minutes = int((uptime.total_seconds() % 3600) // 60)
        
        avg_check_time = f"{(uptime.total_seconds() / max(self.check_count, 1)):.1f}s" if self.check_count > 0 else "N/A"
        
        message = f"""
📈 *Bot Statistics*

━━━━━━━━━━━━━━━━━━━━
🕐 *Uptime:* {hours}h {minutes}m
📅 *Started:* {self.start_time.strftime('%d %b, %I:%M %p')}

━━━━━━━━━━━━━━━━━━━━
🔍 *Monitoring Stats:*
Total Checks: {self.check_count}
Theatres Found: {len(self.notified_theatres)}
Avg Check Time: {avg_check_time}

━━━━━━━━━━━━━━━━━━━━
🎬 *Show Details:*
Total Shows: {sum(len(times) for times in self.notified_theatres.values())}
Theatres with Shows: {len(self.notified_theatres)}

━━━━━━━━━━━━━━━━━━━━
⚙️ *Configuration:*
Poll Interval: {config.POLL_INTERVAL}s
Summary Interval: {config.SUMMARY_INTERVAL // 60}m
Active Users: {len(config.TELEGRAM_CHAT_IDS)}
"""
        
        try:
            await self.bot.send_message(
                chat_id=chat_id,
                text=message,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=self.get_main_keyboard()
            )
        except Exception as e:
            print(f"❌ Error sending statistics: {e}")
    
    async def perform_refresh(self, chat_id):
        """Manually refresh and scan theatres"""
        try:
            if not self.driver or not self.movie_url:
                await self.bot.send_message(
                    chat_id=chat_id,
                    text="❌ Bot not fully initialized. Please wait...",
                    reply_markup=self.get_main_keyboard()
                )
                return
            
            print("🔄 Manual refresh triggered")
            self.driver.refresh()
            time.sleep(4)
            self.select_date()
            
            current_theatres = self.scan_theatres()
            self.last_scan_time = datetime.now()
            
            if current_theatres:
                new_count = len([t for t in current_theatres if t not in self.notified_theatres])
                
                message = f"""
✅ *Refresh Complete!*

━━━━━━━━━━━━━━━━━━━━
🎭 Theatres Found: {len(current_theatres)}
🆕 New Theatres: {new_count}
🕐 Time: {datetime.now().strftime('%I:%M:%S %p')}

━━━━━━━━━━━━━━━━━━━━

{'🎉 New theatres found! Check "Theatres Open" for details.' if new_count > 0 else '✅ No new theatres since last check.'}
"""
                
                # Check for new theatres
                await self.check_new_theatres(current_theatres)
            else:
                message = f"""
✅ *Refresh Complete!*

━━━━━━━━━━━━━━━━━━━━
⏳ No theatres with bookings yet.
🕐 Time: {datetime.now().strftime('%I:%M:%S %p')}

━━━━━━━━━━━━━━━━━━━━
✅ Bot will alert you when bookings open!
"""
            
            await self.bot.send_message(
                chat_id=chat_id,
                text=message,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=self.get_main_keyboard()
            )
            
        except Exception as e:
            print(f"❌ Error in manual refresh: {e}")
            await self.bot.send_message(
                chat_id=chat_id,
                text=f"❌ Refresh failed: {str(e)}",
                reply_markup=self.get_main_keyboard()
            )
    
    async def send_welcome_message(self):
        """Send startup welcome message"""
        message = f"""
🎬 *BookMyShow Monitor Started Successfully!*

━━━━━━━━━━━━━━━━━━━━
📽️ *Movie:* {config.MOVIE_NAME}
📍 *City:* {config.CITY}
📅 *Date:* {config.FULL_DATE}
━━━━━━━━━━━━━━━━━━━━

⚙️ *Configuration:*
⏱️ Poll Frequency: {config.POLL_INTERVAL} seconds
📊 Summary Interval: {config.SUMMARY_INTERVAL // 60} minutes
🕐 Started: {self.start_time.strftime('%d %b %Y, %I:%M:%S %p')}

━━━━━━━━━━━━━━━━━━━━

✅ *Bot is now actively monitoring!*

🔔 You'll receive instant alerts when theatres open bookings.

📱 *Use the buttons below for quick actions!*

👥 Active users: {len(config.TELEGRAM_CHAT_IDS)}
"""
        await self.send_telegram_message(message, reply_markup=self.get_main_keyboard())
        
    def find_movie_url(self):
        """Find the movie URL from BookMyShow Chennai"""
        try:
            print(f"🔍 Searching for '{config.MOVIE_NAME}' in {config.CITY}...")
            self.driver.get(config.BOOKMYSHOW_CHENNAI_MOVIES)
            time.sleep(5)
            
            search_text = config.MOVIE_NAME.lower()
            movie_links = self.driver.find_elements(By.XPATH, 
                f"//a[contains(@href, '/movies/') and contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{search_text}')]")
            
            if movie_links:
                movie_url = movie_links[0].get_attribute('href')
                print(f"✅ Found movie URL: {movie_url}")
                return movie_url
            
            print("🔍 Trying alternative search method...")
            all_movie_elements = self.driver.find_elements(By.XPATH, 
                "//a[contains(@href, '/movies/')]")
            
            for element in all_movie_elements:
                try:
                    text_content = element.text.lower()
                    if search_text in text_content:
                        movie_url = element.get_attribute('href')
                        print(f"✅ Found movie URL (alternative): {movie_url}")
                        return movie_url
                except:
                    continue
            
            print("⚠️ Could not find movie in listings, trying direct URL patterns...")
            movie_slug = config.MOVIE_NAME.lower().replace(' ', '-')
            possible_urls = [
                f"{config.BOOKMYSHOW_BASE_URL}/chennai/movies/{movie_slug}/ET00388929",
                f"{config.BOOKMYSHOW_BASE_URL}/movies/{movie_slug}/ET00388929",
                f"{config.BOOKMYSHOW_BASE_URL}/chennai/movies/{movie_slug}",
            ]
            
            for url in possible_urls:
                try:
                    print(f"🔗 Testing URL: {url}")
                    self.driver.get(url)
                    time.sleep(3)
                    
                    if self.driver.find_elements(By.XPATH, "//div[contains(@class, 'date') or contains(text(), 'Jan') or contains(text(), 'Book')]"):
                        print(f"✅ Valid movie page found: {url}")
                        return url
                except:
                    continue
            
            print("❌ Could not find movie URL")
            return None
                
        except Exception as e:
            print(f"❌ Error finding movie: {e}")
            return None
            
    def select_date(self):
        """Select the monitoring date (09 Jan)"""
        try:
            print(f"📅 Attempting to select date: {config.MONITOR_DATE}")
            time.sleep(2)
            
            date_xpaths = [
                f"//div[contains(@class, 'date') or contains(@class, 'DatePicker')]//span[contains(text(), '{config.MONITOR_DATE}')]",
                f"//button[contains(text(), '{config.MONITOR_DATE}')]",
                f"//a[contains(text(), '{config.MONITOR_DATE}')]",
                f"//*[contains(text(), '09') and contains(text(), 'Jan')]",
                f"//div[contains(@class, 'showDate')]//span[text()='09']",
            ]
            
            for xpath in date_xpaths:
                try:
                    date_elements = self.driver.find_elements(By.XPATH, xpath)
                    if date_elements:
                        element = date_elements[0]
                        self.driver.execute_script("arguments[0].scrollIntoView(true);", element)
                        time.sleep(1)
                        
                        try:
                            element.click()
                        except:
                            self.driver.execute_script("arguments[0].click();", element)
                        
                        time.sleep(3)
                        print(f"✅ Successfully selected date: {config.MONITOR_DATE}")
                        return True
                except Exception as e:
                    continue
            
            print(f"⚠️ Could not click date selector, may already be on {config.MONITOR_DATE}")
            return True
                
        except Exception as e:
            print(f"⚠️ Date selection error: {e}")
            return True
            
    def scan_theatres(self):
        """Scan all theatres and extract show timings"""
        theatres_data = {}
        
        try:
            time.sleep(3)
            
            theatre_container_xpaths = [
                "//div[contains(@class, 'venue-')]",
                "//li[contains(@class, '__venue')]",
                "//div[contains(@class, '__cinema')]",
                "//div[contains(@class, 'VenueList')]//li",
                "//ul[contains(@class, 'cinemas')]//li",
            ]
            
            theatre_elements = []
            for xpath in theatre_container_xpaths:
                elements = self.driver.find_elements(By.XPATH, xpath)
                if elements:
                    theatre_elements = elements
                    print(f"✅ Found {len(theatre_elements)} theatre containers")
                    break
            
            if not theatre_elements:
                print("⚠️ No theatre elements found")
                return theatres_data
            
            for idx, theatre_elem in enumerate(theatre_elements):
                try:
                    theatre_name = None
                    name_xpaths = [
                        ".//a[contains(@class, 'name') or contains(@class, '__name')]",
                        ".//strong",
                        ".//h3",
                        ".//h4",
                        ".//div[contains(@class, 'venue-name')]",
                        ".//span[contains(@class, '__name')]",
                    ]
                    
                    for name_xpath in name_xpaths:
                        name_elements = theatre_elem.find_elements(By.XPATH, name_xpath)
                        if name_elements and name_elements[0].text.strip():
                            theatre_name = name_elements[0].text.strip()
                            break
                    
                    if not theatre_name:
                        continue
                    
                    showtime_xpaths = [
                        ".//a[contains(@class, 'showtime') or contains(@class, '__showtime')]",
                        ".//button[contains(@class, 'session')]",
                        ".//span[contains(@class, 'session-time')]",
                        ".//div[contains(@class, '__time')]",
                    ]
                    
                    showtimes = []
                    for showtime_xpath in showtime_xpaths:
                        showtime_elements = theatre_elem.find_elements(By.XPATH, showtime_xpath)
                        if showtime_elements:
                            for showtime_elem in showtime_elements:
                                showtime_text = showtime_elem.text.strip()
                                if showtime_text and showtime_text not in ['', 'SOLD OUT', 'FILLING FAST', 'BOOK']:
                                    if any(char.isdigit() for char in showtime_text):
                                        showtimes.append(showtime_text)
                            
                            if showtimes:
                                break
                    
                    if showtimes:
                        theatres_data[theatre_name] = list(set(showtimes))
                        print(f"  🎬 {theatre_name}: {len(showtimes)} shows")
                        
                except Exception as e:
                    continue
            
            print(f"📊 Total theatres with shows: {len(theatres_data)}")
                    
        except Exception as e:
            print(f"❌ Error scanning theatres: {e}")
            
        return theatres_data
        
    async def check_new_theatres(self, current_theatres):
        """Check for newly opened theatres and send instant notifications"""
        new_theatres = []
        
        for theatre_name, showtimes in current_theatres.items():
            if theatre_name not in self.notified_theatres:
                new_theatres.append((theatre_name, showtimes))
                self.notified_theatres[theatre_name] = showtimes
                
                formatted_times = '\n'.join([f"  ⏰ {time}" for time in sorted(showtimes)])
                
                message = f"""
🎉 *NEW THEATRE BOOKING OPENED!*

━━━━━━━━━━━━━━━━━━━━
🎭 *Theatre:* {theatre_name}
📅 *Date:* {config.FULL_DATE}
📍 *City:* {config.CITY}
🎬 *Movie:* {config.MOVIE_NAME}
━━━━━━━━━━━━━━━━━━━━

🕐 *Available Shows ({len(showtimes)}):*
{formatted_times}

━━━━━━━━━━━━━━━━━━━━
🔗 *Book now on BookMyShow!*
🏃 Hurry! Limited seats available.
"""
                await self.send_telegram_message(message, reply_markup=self.get_main_keyboard())
                print(f"🔔 NEW THEATRE ALERT: {theatre_name} ({len(showtimes)} shows)")
                
        return new_theatres
        
    async def send_summary(self):
        """Send 30-minute summary update"""
        current_time = datetime.now().strftime('%d %b %Y, %I:%M:%S %p')
        
        if not self.notified_theatres:
            message = f"""
📊 *30-Minute Summary Report*

━━━━━━━━━━━━━━━━━━━━
🕐 *Time:* {current_time}
📽️ *Movie:* {config.MOVIE_NAME}
📅 *Date:* {config.FULL_DATE}
📍 *City:* {config.CITY}
━━━━━━━━━━━━━━━━━━━━

⏳ *Status:* Still monitoring...
❌ No theatres have opened bookings yet.

✅ Bot is active and checking every {config.POLL_INTERVAL} seconds.
🔍 Total checks performed: {self.check_count}

💡 You'll be notified immediately when bookings open!
"""
        else:
            theatres_list = []
            for idx, (theatre_name, showtimes) in enumerate(self.notified_theatres.items(), 1):
                times_str = ', '.join(sorted(showtimes)[:5])
                if len(showtimes) > 5:
                    times_str += f' +{len(showtimes)-5} more'
                theatres_list.append(f"{idx}. *{theatre_name}*\n   Shows: {times_str}")
            
            theatres_text = '\n\n'.join(theatres_list)
            
            message = f"""
📊 *30-Minute Summary Report*

━━━━━━━━━━━━━━━━━━━━
🕐 *Time:* {current_time}
📽️ *Movie:* {config.MOVIE_NAME}
📅 *Date:* {config.FULL_DATE}
📍 *City:* {config.CITY}
━━━━━━━━━━━━━━━━━━━━

✅ *Theatres with Bookings:* {len(self.notified_theatres)}

{theatres_text}

━━━━━━━━━━━━━━━━━━━━
🔄 Continuing to monitor for more theatres...
🔍 Total checks: {self.check_count}
"""
        
        await self.send_telegram_message(message, reply_markup=self.get_main_keyboard())
        print(f"📊 Summary sent - {len(self.notified_theatres)} theatres tracked")
        
    async def monitor_loop(self):
        """Main monitoring loop"""
        self.movie_url = self.find_movie_url()
        
        if not self.movie_url:
            await self.send_telegram_message(
                f"❌ *Error: Could not find movie page*\n\n"
                f"Movie: {config.MOVIE_NAME}\n"
                f"City: {config.CITY}\n\n"
                f"Please check if the movie name is correct and available in {config.CITY}."
            )
            return
        
        print(f"🌐 Opening movie page: {self.movie_url}")
        self.driver.get(self.movie_url)
        time.sleep(4)
        
        self.select_date()
        
        last_refresh_time = time.time()
        
        while True:
            try:
                if not self.is_monitoring:
                    print("⏸️ Monitoring paused, waiting...")
                    await asyncio.sleep(5)
                    continue
                
                self.check_count += 1
                print(f"\n{'='*50}")
                print(f"🔄 Check #{self.check_count} at {datetime.now().strftime('%H:%M:%S')}")
                print(f"{'='*50}")
                
                current_theatres = self.scan_theatres()
                self.last_scan_time = datetime.now()
                
                if current_theatres:
                    print(f"✅ Found {len(current_theatres)} theatres with available shows")
                    new = await self.check_new_theatres(current_theatres)
                    if new:
                        print(f"🎉 {len(new)} new theatre(s) found!")
                else:
                    print("⏳ No theatres with shows found yet")
                
                current_time = time.time()
                if current_time - self.last_summary_time >= config.SUMMARY_INTERVAL:
                    await self.send_summary()
                    self.last_summary_time = current_time
                
                if current_time - last_refresh_time >= config.PAGE_REFRESH_INTERVAL:
                    print("🔄 Refreshing page to get latest data...")
                    self.driver.refresh()
                    time.sleep(4)
                    self.select_date()
                    last_refresh_time = current_time
                
                print(f"⏸️  Waiting {config.POLL_INTERVAL} seconds before next check...")
                await asyncio.sleep(config.POLL_INTERVAL)
                    
            except KeyboardInterrupt:
                print("\n⚠️ Monitoring stopped by user")
                await self.send_telegram_message("⚠️ *Bot Stopped*\n\nMonitoring has been stopped by user.")
                break
            except WebDriverException as e:
                print(f"❌ Browser error: {e}")
                print("🔄 Attempting to recover...")
                try:
                    self.driver.quit()
                except:
                    pass
                if self.setup_driver():
                    self.driver.get(self.movie_url)
                    time.sleep(4)
                    self.select_date()
                else:
                    await self.send_telegram_message("❌ *Critical Error*\n\nBrowser crashed and could not recover.")
                    break
            except Exception as e:
                print(f"❌ Error in monitoring loop: {e}")
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
            print(f"👥 Broadcasting to: {len(config.TELEGRAM_CHAT_IDS)} user(s)")
            print("="*60 + "\n")
            
            if not self.setup_driver():
                return
                
            if not self.setup_telegram():
                return
            
            # Start the bot polling in background
            print("🤖 Starting Telegram bot polling...")
            asyncio.create_task(self.app.initialize())
            asyncio.create_task(self.app.start())
            asyncio.create_task(self.app.updater.start_polling())
            
            await asyncio.sleep(2)
            
            await self.send_welcome_message()
            
            await self.monitor_loop()
            
        except Exception as e:
            print(f"❌ Fatal error: {e}")
            if self.bot:
                await self.send_telegram_message(f"❌ *Bot Fatal Error*\n\n```\n{str(e)}\n```")
        finally:
            if self.driver:
                try:
                    self.driver.quit()
                    print("🛑 Browser closed")
                except:
                    pass
            
            if self.app:
                try:
                    await self.app.updater.stop()
                    await self.app.stop()
                    await self.app.shutdown()
                except:
                    pass

def main():
    """Entry point"""
    if not config.TELEGRAM_BOT_TOKEN:
        print("❌ Error: TELEGRAM_BOT_TOKEN not set in .env file")
        print("   Get token from @BotFather on Telegram")
        return
    
    if not config.TELEGRAM_CHAT_IDS:
        print("❌ Error: No chat IDs configured")
        print("   Set TELEGRAM_CHAT_ID or TELEGRAM_CHAT_IDS in .env file")
        print("   Get your chat ID from @userinfobot on Telegram")
        return
    
    print(f"✅ Configuration validated")
    print(f"   Bot Token: {config.TELEGRAM_BOT_TOKEN[:10]}...")
    print(f"   Chat IDs: {len(config.TELEGRAM_CHAT_IDS)} configured\n")
    
    monitor = BookMyShowMonitor()
    asyncio.run(monitor.run())

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Bot stopped")
    except Exception as e:
        print(f"Error: {e}")
        # Keep container alive even on error
        import time
        while True:
            time.sleep(60)
            print("Container still running...")
