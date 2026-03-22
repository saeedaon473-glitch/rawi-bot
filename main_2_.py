import os
import asyncio
import logging
import sqlite3
import re
import random
import urllib.parse
import json
import aiohttp
import traceback
import random as _random
import uuid as _uuid
from datetime import datetime, date, timedelta, time
import datetime as _dt
from collections import Counter
import gc
import signal
import time
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, LabeledPrice
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, PreCheckoutQueryHandler, InlineQueryHandler, filters, ContextTypes
from telegram import InlineQueryResultArticle, InputTextMessageContent

# ==================== Keep-Alive Server for Replit ====================
class KeepAliveHandler(BaseHTTPRequestHandler):
    """HTTP handler للاستجابة لـ pings من UptimeRobot"""
    def do_GET(self):
        """استجابة بسيطة لـ GET requests"""
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        
        # معلومات البوت
        uptime = time.time() - self.server.start_time if hasattr(self.server, 'start_time') else 0
        uptime_str = f"{int(uptime // 3600)}h {int((uptime % 3600) // 60)}m"
        
        response = f"""
        <html>
        <head><title>Rawi Bot - Active</title></head>
        <body style="font-family: Arial; background: #1a1a2e; color: #eee; padding: 40px; text-align: center;">
            <h1>🤖 راوِي Bot</h1>
            <p>✅ البوت يعمل بنجاح!</p>
            <p>⏱️ Uptime: {uptime_str}</p>
            <p>🔄 Last ping: {time.strftime('%Y-%m-%d %H:%M:%S')}</p>
        </body>
        </html>
        """
        self.wfile.write(response.encode())
    
    def log_message(self, format, *args):
        """تعطيل الـ logging للـ HTTP requests"""
        pass

def run_keepalive_server():
    """تشغيل HTTP server في thread منفصل"""
    try:
        server = HTTPServer(('0.0.0.0', 8080), KeepAliveHandler)
        server.start_time = time.time()
        logger.info("🌐 Keep-Alive server started on port 8080")
        server.serve_forever()
    except Exception as e:
        logger.error(f"Keep-Alive server error: {e}")

# ==================== تحسينات إضافية ====================
import time

# ==================== Constants ====================
CACHE_TTL_HADITH = 3600  # ساعة واحدة
CACHE_TTL_SHORT = 300    # 5 دقائق
POINTS_HADITH_SEARCH = 2
POINTS_QUIZ_COMPLETE = 5
POINTS_DAILY_DUAA = 1
POINTS_QUDWATI = 3
POINTS_CHALLENGE_WIN = 10

# ==================== Memory Optimization ====================
def cleanup_memory():
    """تنظيف الذاكرة دورياً"""
    try:
        # تنظيف cache قديم
        if hasattr(hadith_cache, 'cache'):
            old_size = len(hadith_cache.cache)
            # حذف العناصر القديمة (أكثر من ساعة)
            current_time = time.time()
            to_delete = [
                key for key, (_, timestamp) in hadith_cache.cache.items()
                if current_time - timestamp > 3600
            ]
            for key in to_delete:
                del hadith_cache.cache[key]
            
            if to_delete:
                logger.info(f"🧹 Cleaned {len(to_delete)} old cache entries")
        
        # تشغيل garbage collector
        gc.collect()
        
    except Exception as e:
        logger.error(f"Memory cleanup error: {e}")

# ==================== Heartbeat System ====================
async def heartbeat(context):
    """إرسال heartbeat كل 30 ثانية للتأكد من أن البوت يعمل"""
    beat_count = 0
    while True:
        try:
            await asyncio.sleep(30)
            beat_count += 1
            
            # كل 10 heartbeats (5 دقائق) نسجل
            if beat_count % 10 == 0:
                logger.info(f"💓 Heartbeat #{beat_count} - Bot is alive")
                
                # تنظيف ذاكرة خفيف
                if beat_count % 60 == 0:  # كل 30 دقيقة
                    cleanup_memory()
                    
        except Exception as e:
            logger.error(f"Heartbeat error: {e}")

# ==================== Self-Ping الداخلي ====================

# ==================== Auto-Restart عند الأخطاء ====================
class BotRestartManager:
    """مدير إعادة التشغيل التلقائية"""
    def __init__(self, max_crashes=5, reset_time=3600):
        self.crashes = []
        self.max_crashes = max_crashes
        self.reset_time = reset_time  # ساعة واحدة
    
    def record_crash(self):
        """تسجيل crash"""
        import time
        current_time = time.time()
        
        # حذف crashes القديمة
        self.crashes = [t for t in self.crashes if current_time - t < self.reset_time]
        
        # إضافة crash جديد
        self.crashes.append(current_time)
        
        # فحص إذا وصلنا للحد الأقصى
        if len(self.crashes) >= self.max_crashes:
            logger.error(f"❌ {self.max_crashes} crashes في ساعة واحدة - إيقاف البوت")
            return False
        
        return True
    
    def can_restart(self):
        """هل يمكن إعادة التشغيل؟"""
        return len(self.crashes) < self.max_crashes

restart_manager = BotRestartManager()

# ==================== Connection Management ====================

# ==================== Activity Simulator ====================

# ==================== Database Health Monitor ====================

# ==================== Error Recovery System ====================
class ErrorRecoverySystem:
    """نظام استرجاع تلقائي من الأخطاء"""
    
    def __init__(self):
        self.error_counts = {}
        self.max_errors_per_type = 10
        self.recovery_actions = {
            'DatabaseError': self.recover_database,
            'NetworkError': self.recover_network,
            'MemoryError': self.recover_memory,
        }
    
    def record_error(self, error_type: str):
        """تسجيل خطأ"""
        if error_type not in self.error_counts:
            self.error_counts[error_type] = 0
        self.error_counts[error_type] += 1
        
        # إذا وصلنا للحد، حاول الاسترجاع
        if self.error_counts[error_type] >= 3:
            self.attempt_recovery(error_type)
    
    def attempt_recovery(self, error_type: str):
        """محاولة الاسترجاع من الخطأ"""
        if error_type in self.recovery_actions:
            try:
                self.recovery_actions[error_type]()
                self.error_counts[error_type] = 0  # إعادة تعيين
                logger.info(f"✅ Recovered from {error_type}")
            except Exception as e:
                logger.error(f"Recovery failed for {error_type}: {e}")
    
    def recover_database(self):
        """استرجاع قاعدة البيانات"""
        try:
            conn = sqlite3.connect("bot.db", timeout=30)
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            conn.close()
            cleanup_memory()
        except:
            pass
    
    def recover_network(self):
        """استرجاع الشبكة"""
        try:
            gc.collect()
        except:
            pass
    
    def recover_memory(self):
        """استرجاع الذاكرة"""
        try:
            cleanup_memory()
            gc.collect()
        except:
            pass

error_recovery_system = ErrorRecoverySystem()

# ==================== Performance Monitor ====================
class PerformanceMonitor:
    """مراقبة الأداء"""
    
    def __init__(self):
        self.start_time = time.time()
        self.request_count = 0
        self.error_count = 0
        self.last_report = time.time()
    
    def record_request(self):
        """تسجيل طلب"""
        self.request_count += 1
    
    def record_error(self):
        """تسجيل خطأ"""
        self.error_count += 1
    
    def get_uptime(self):
        """الحصول على uptime"""
        uptime_seconds = time.time() - self.start_time
        hours = int(uptime_seconds // 3600)
        minutes = int((uptime_seconds % 3600) // 60)
        return f"{hours}h {minutes}m"
    
    def should_report(self):
        """هل حان وقت التقرير؟"""
        return time.time() - self.last_report > 3600  # كل ساعة
    
    def generate_report(self):
        """توليد تقرير الأداء"""
        if self.should_report():
            uptime = self.get_uptime()
            success_rate = ((self.request_count - self.error_count) / self.request_count * 100) if self.request_count > 0 else 0
            
            logger.info(f"📊 Performance Report:")
            logger.info(f"   Uptime: {uptime}")
            logger.info(f"   Requests: {self.request_count}")
            logger.info(f"   Errors: {self.error_count}")
            logger.info(f"   Success Rate: {success_rate:.1f}%")
            
            self.last_report = time.time()

perf_monitor = PerformanceMonitor()

async def monitor_database_health():
    """
    مراقبة صحة قاعدة البيانات
    يتأكد من عدم وجود corrupted data أو locks
    """
    await asyncio.sleep(180)  # انتظار 3 دقائق قبل البدء
    
    while True:
        try:
            await asyncio.sleep(900)  # كل 15 دقيقة
            
            conn = sqlite3.connect("bot.db", timeout=10)
            
            # فحص locks
            try:
                conn.execute("BEGIN IMMEDIATE")
                conn.commit()
            except sqlite3.OperationalError:
                logger.warning("⚠️ Database locked - attempting recovery")
                await asyncio.sleep(5)
                continue
            
            # فحص integrity
            result = conn.execute("PRAGMA integrity_check").fetchone()
            if result[0] != "ok":
                logger.error(f"❌ Database integrity issue: {result[0]}")
            else:
                logger.debug("✅ Database health OK")
            
            # تحسين قاعدة البيانات
            conn.execute("VACUUM")
            
            conn.close()
            
        except Exception as e:
            logger.error(f"DB health monitor error: {e}")

async def simulate_activity(app):
    """
    محاكاة نشاط داخلي للبوت
    يحافظ على Replit نشط بدون اعتماد على مستخدمين
    """
    await asyncio.sleep(120)  # انتظار دقيقتين قبل البدء
    
    activities = [
        "cleanup_cache",
        "check_stats", 
        "verify_db",
        "ping_health"
    ]
    
    activity_count = 0
    
    while True:
        try:
            await asyncio.sleep(420)  # كل 7 دقائق
            
            activity = activities[activity_count % len(activities)]
            activity_count += 1
            
            if activity == "cleanup_cache":
                # تنظيف خفيف للـ cache
                if hasattr(hadith_cache, 'cache') and len(hadith_cache.cache) > 100:
                    logger.debug("🧹 Activity: cache cleanup")
                    
            elif activity == "check_stats":
                # فحص إحصائيات بسيط
                try:
                    conn = sqlite3.connect("bot.db", timeout=5)
                    users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
                    conn.close()
                    logger.debug(f"📊 Activity: {users} users")
                except:
                    pass
                    
            elif activity == "verify_db":
                # فحص سلامة قاعدة البيانات
                try:
                    conn = sqlite3.connect("bot.db", timeout=5)
                    conn.execute("PRAGMA integrity_check").fetchone()
                    conn.close()
                    logger.debug("✅ Activity: DB verified")
                except:
                    pass
                    
            elif activity == "ping_health":
                # فحص صحة الأنظمة
                logger.debug("💓 Activity: health check")
            
        except Exception as e:
            logger.error(f"Activity simulator error: {e}")

async def keep_connections_alive():
    """
    الحفاظ على connections نشطة
    يمنع timeout في اتصالات قاعدة البيانات والشبكة
    """
    while True:
        try:
            await asyncio.sleep(600)  # كل 10 دقائق
            
            # فحص قاعدة البيانات
            try:
                conn = sqlite3.connect("bot.db", timeout=5)
                conn.execute("SELECT 1").fetchone()
                conn.close()
                logger.debug("🔌 DB connection alive")
            except Exception as e:
                logger.error(f"DB connection error: {e}")
            
            # تنظيف connections قديمة
            gc.collect()
            
        except Exception as e:
            logger.error(f"Keep connections error: {e}")

async def internal_self_ping():
    """
    إرسال طلبات داخلية للبوت كل 5 دقائق
    يحافظ على نشاط البوت في Replit بدون الحاجة لخدمات خارجية
    """
    if not REPLIT_URL:
        logger.warning("⚠️ REPLIT_URL غير موجود - self-ping معطل")
        return
    
    await asyncio.sleep(60)  # انتظار دقيقة قبل البدء
    
    while True:
        try:
            await asyncio.sleep(300)  # كل 5 دقائق
            
            # إرسال ping للـ keep-alive server
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                async with session.get(REPLIT_URL) as resp:
                    if resp.status == 200:
                        logger.info("✅ Self-ping successful")
                    else:
                        logger.warning(f"⚠️ Self-ping returned {resp.status}")
        except Exception as e:
            logger.error(f"Self-ping error: {e}")

async def periodic_cleanup(context):
    """تنظيف دوري كل 30 دقيقة"""
    while True:
        try:
            await asyncio.sleep(1800)  # 30 دقيقة
            cleanup_memory()
            logger.info("✅ Periodic cleanup completed")
        except Exception as e:
            logger.error(f"Periodic cleanup error: {e}")

import gc
import signal
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler

# ==================== إعدادات البوت ====================
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
REPLIT_URL = os.environ.get("REPLIT_URL", "")  # رابط Replit مثل https://xxxxx.replit.app
if not BOT_TOKEN:
    logger.error("❌ BOT_TOKEN غير موجود.")
    exit(1)

admin_ids_str = os.environ.get("ADMIN_IDS", "")
ADMIN_IDS = [int(x) for x in admin_ids_str.split(",") if x.strip().isdigit()]

# ═══════════════════════════════════════════════════════════════════
# نظام الاختبارات في القنوات
# ═══════════════════════════════════════════════════════════════════
ACTIVE_CHANNEL_QUIZZES = {}
CHANNEL_QUIZ_PARTICIPANTS = {}


BOT_NAME = "راوِي"
BOT_USERNAME = "@G4bGN_bot"

# ==================== إعدادات الأسئلة الدينية ====================
QA_FREE_DAILY = 3  # عدد الأسئلة المجانية يومياً
QA_EXTRA_STARS = 10  # عدد النجوم لشراء 5 أسئلة إضافية
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

# ==================== نظام Cache بسيط ====================
class SimpleCache:
    def __init__(self, ttl_seconds=CACHE_TTL_SHORT):
        self.cache = {}
        self.ttl = ttl_seconds
    
    def get(self, key):
        if key in self.cache:
            value, timestamp = self.cache[key]
            if time.time() - timestamp < self.ttl:
                return value
            else:
                del self.cache[key]
        return None
    
    def set(self, key, value):
        self.cache[key] = (value, time.time())
    
    def clear(self):
        self.cache.clear()

# Cache للبحث في الأحاديث
hadith_cache = SimpleCache(ttl_seconds=CACHE_TTL_HADITH)  # ساعة واحدة

# ==================== نظام النقاط والإنجازات ====================
def add_points(user_id: int, points: int, activity: str):
    """إضافة نقاط للمستخدم"""
    try:
        conn = sqlite3.connect("bot.db")
        # التأكد من وجود جدول points
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_points (
                user_id INTEGER PRIMARY KEY,
                total_points INTEGER DEFAULT 0,
                daily_hadith_count INTEGER DEFAULT 0,
                quiz_count INTEGER DEFAULT 0,
                search_count INTEGER DEFAULT 0,
                last_activity TEXT
            )
        """)
        
        # إضافة النقاط
        conn.execute("""
            INSERT INTO user_points (user_id, total_points, last_activity)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(user_id) DO UPDATE SET
            total_points = total_points + ?,
            last_activity = datetime('now')
        """, (user_id, points, points))
        
        conn.commit()
        conn.close()
        logger.info(f"[POINTS] User {user_id} +{points} for {activity}")
    except Exception as e:
        logger.error(f"Points error: {e}")

def get_user_points(user_id: int) -> dict:
    """الحصول على نقاط المستخدم"""
    try:
        conn = sqlite3.connect("bot.db")
        row = conn.execute("SELECT total_points, daily_hadith_count, quiz_count, search_count FROM user_points WHERE user_id=?", (user_id,)).fetchone()
        conn.close()
        if row:
            return {"points": row[0], "hadith": row[1], "quiz": row[2], "search": row[3]}
        return {"points": 0, "hadith": 0, "quiz": 0, "search": 0}
    except:
        return {"points": 0, "hadith": 0, "quiz": 0, "search": 0}

# نقاط للأنشطة
POINTS_REWARDS = {
    "hadith_search": 2,
    "quiz_complete": 5,
    "daily_duaa": 1,
    "qudwati": 3,
    "friend_challenge_win": 10,
}

# ==================== نظام Rate Limiting ====================
class RateLimiter:
    def __init__(self, max_requests=10, window_seconds=60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = {}
    
    def is_allowed(self, user_id):
        now = time.time()
        if user_id not in self.requests:
            self.requests[user_id] = []
        
        # حذف الطلبات القديمة
        self.requests[user_id] = [
            req_time for req_time in self.requests[user_id]
            if now - req_time < self.window_seconds
        ]
        
        # فحص الحد
        if len(self.requests[user_id]) >= self.max_requests:
            return False
        
        self.requests[user_id].append(now)
        return True

# Rate limiter للأسئلة الدينية
qa_rate_limiter = RateLimiter(max_requests=5, window_seconds=60)

# ==================== أزرار ملونة — Bot API 9.4 ====================
def colored_btn(text: str, callback_data: str = None, url: str = None,
                switch_inline_query: str = None, style: str = None) -> InlineKeyboardButton:
    """
    إنشاء زر ملون باستخدام Bot API 9.4
    style: 'primary' (أزرق) | 'success' (أخضر) | 'danger' (أحمر)
    """
    kwargs = {}
    if callback_data is not None:
        kwargs["callback_data"] = callback_data
    if url is not None:
        kwargs["url"] = url
    if switch_inline_query is not None:
        kwargs["switch_inline_query"] = switch_inline_query
    api_kw = {}
    if style:
        api_kw["style"] = style
    return InlineKeyboardButton(
        text=text,
        api_kwargs=api_kw if api_kw else None,
        **kwargs
    )

# توقيت الأردن UTC+3
AMMAN_TZ = _dt.timezone(_dt.timedelta(hours=3))

# ===== Cache للبحث - 5 دقائق =====
import time as _time
_search_cache = {}
CACHE_TTL = 1800  # 30 دقيقة

# ===== Rate Limiting =====
_rate_limit = {}   # {user_id: [timestamps]}
RATE_MAX = 5       # أقصى عدد طلبات
RATE_WINDOW = 10   # في ثواني

def is_rate_limited(user_id: int) -> bool:
    now = _time.time()
    timestamps = _rate_limit.get(user_id, [])
    timestamps = [t for t in timestamps if now - t < RATE_WINDOW]
    _rate_limit[user_id] = timestamps
    if len(timestamps) >= RATE_MAX:
        return True
    timestamps.append(now)
    _rate_limit[user_id] = timestamps
    return False

def cache_get(query: str):
    key = query.strip().lower()
    if key in _search_cache:
        results, ts = _search_cache[key]
        if _time.time() - ts < CACHE_TTL:
            return results
        del _search_cache[key]
    return None

def cache_set(query: str, results: list):
    key = query.strip().lower()
    _search_cache[key] = (results, _time.time())
    # أزل القديم لو تجاوز 200 مدخلة
    if len(_search_cache) > 200:
        oldest = min(_search_cache, key=lambda k: _search_cache[k][1])
        del _search_cache[oldest]

# الكتب الستة - تُعرَّف هنا عشان تكون متاحة لكل الدوال
KUTUB_SITTA_FULL = [
    "صحيح البخاري", "صحيح مسلم",
    "سنن أبي داود", "سنن الترمذي",
    "سنن النسائي", "سنن ابن ماجه",
]

# ==================== قاعدة البيانات ====================
def init_db():
    conn = sqlite3.connect("bot.db")
    conn.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        full_name TEXT,
        searches INTEGER DEFAULT 0,
        joined_at TEXT DEFAULT (datetime('now')),
        daily_hadith INTEGER DEFAULT 1,
        adhkar_sub INTEGER DEFAULT 0
    )""")
    # جدول المفضلة
    conn.execute("""CREATE TABLE IF NOT EXISTS favorites (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        hadith_text TEXT,
        rawi TEXT,
        source TEXT,
        grade TEXT,
        note TEXT DEFAULT '',
        saved_at TEXT DEFAULT (datetime('now')),
        UNIQUE(user_id, hadith_text)
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS quiz_sessions (
        user_id INTEGER PRIMARY KEY,
        questions_json TEXT,
        quiz_index INTEGER DEFAULT 0,
        quiz_score INTEGER DEFAULT 0,
        quiz_date TEXT
    )""")
    try:
        conn.execute("ALTER TABLE favorites ADD COLUMN note TEXT DEFAULT ''")
    except:
        pass
    # جدول Premium
    conn.commit()
    # أضف الأعمدة الجديدة إذا كانت قاعدة البيانات قديمة
    try:
        conn.execute("ALTER TABLE users ADD COLUMN daily_hadith INTEGER DEFAULT 1")
    except:
        pass
    try:
        conn.execute("ALTER TABLE users ADD COLUMN adhkar_sub INTEGER DEFAULT 0")
    except:
        pass
    conn.execute("""CREATE TABLE IF NOT EXISTS searches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        query TEXT,
        date TEXT DEFAULT (datetime('now'))
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS search_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        query TEXT,
        results_count INTEGER DEFAULT 0,
        date TEXT DEFAULT (datetime('now'))
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS ahadith (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        text TEXT UNIQUE,
        rawi TEXT,
        source TEXT,
        grade TEXT
    )""")

    conn.execute("""CREATE TABLE IF NOT EXISTS error_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT DEFAULT (datetime('now')),
        error_type TEXT,
        error_message TEXT,
        user_id INTEGER,
        traceback TEXT
    )""")

    # جدول لتسجيل التبرعات مع إضافة charge_id
    conn.execute("""CREATE TABLE IF NOT EXISTS donations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        amount INTEGER,
        currency TEXT,
        charge_id TEXT,
        date TEXT DEFAULT (datetime('now'))
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS streaks (
        user_id INTEGER PRIMARY KEY,
        streak INTEGER DEFAULT 0,
        max_streak INTEGER DEFAULT 0,
        last_date TEXT DEFAULT ''
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS friend_challenges (
        challenge_id TEXT PRIMARY KEY,
        creator_id INTEGER,
        creator_name TEXT,
        opponent_id INTEGER,
        opponent_name TEXT,
        questions_json TEXT,
        creator_score INTEGER DEFAULT -1,
        opponent_score INTEGER DEFAULT -1,
        created_at TEXT,
        status TEXT DEFAULT 'waiting'
    )""")
    conn.commit()
    conn.close()
    logger.info("✅ تم إنشاء قاعدة البيانات.")
    # جداول ختمة
    with sqlite3.connect("bot.db") as _c:
        _c.execute("""CREATE TABLE IF NOT EXISTS qa_usage (
            user_id INTEGER,
            date TEXT,
            count INTEGER DEFAULT 0,
            extra_questions INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, date)
        )""")
        _c.execute("""CREATE TABLE IF NOT EXISTS qa_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            question TEXT,
            answer TEXT,
            created_at TEXT
        )""")

        # جدول cache للملفات الصوتية - يحفظ file_id لتسريع الإرسال
        _c.execute("""CREATE TABLE IF NOT EXISTS audio_cache (
            surah_num INTEGER,
            reciter TEXT,
            file_id TEXT,
            file_size INTEGER DEFAULT 0,
            cached_at TEXT DEFAULT (datetime('now')),
            UNIQUE(surah_num, reciter)
        )""")

def log_donation(user_id, amount, charge_id):
    """تسجيل تبرع في قاعدة البيانات مع معرف المعاملة"""
    try:
        conn = sqlite3.connect("bot.db")
        cur = conn.cursor()
        cur.execute("INSERT INTO donations (user_id, amount, currency, charge_id) VALUES (?,?,?,?)",
                    (user_id, amount, "XTR", charge_id))
        conn.commit()
        conn.close()
        logger.info(f"💰 تبرع جديد: المستخدم {user_id} بمبلغ {amount} نجمة، charge_id: {charge_id}")
        return True
    except Exception as e:
        logger.error(f"خطأ في تسجيل التبرع: {e}")
        return False

    """البحث عن تبرع معين"""
    try:
        conn = sqlite3.connect("bot.db")
        cur = conn.cursor()
        cur.execute("SELECT amount FROM donations WHERE user_id=? AND charge_id=?", (user_id, charge_id))
        row = cur.fetchone()
        conn.close()
        return row
    except Exception as e:
        logger.error(f"خطأ في البحث عن التبرع: {e}")
        return None

def log_error(error_type, error_message, user_id=None, tb=None):
    try:
        conn = sqlite3.connect("bot.db")
        cur = conn.cursor()
        cur.execute("INSERT INTO error_logs (error_type, error_message, user_id, traceback) VALUES (?,?,?,?)",
                    (error_type, error_message[:500], user_id, tb[:1000] if tb else None))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"فشل تسجيل الخطأ: {e}")

# ==================== دوال Cache للملفات الصوتية ====================
def get_cached_audio(surah_num: int, reciter: str):
    """جلب file_id من cache لتسريع إرسال الملفات الصوتية"""
    try:
        with sqlite3.connect("bot.db") as conn:
            row = conn.execute(
                "SELECT file_id FROM audio_cache WHERE surah_num=? AND reciter=?",
                (surah_num, reciter)
            ).fetchone()
        return row[0] if row else None
    except Exception as e:
        logger.error(f"get_cached_audio error: {e}")
        return None

def save_audio_cache(surah_num: int, reciter: str, file_id: str, file_size: int = 0):
    """حفظ file_id في cache بعد أول إرسال"""
    try:
        with sqlite3.connect("bot.db") as conn:
            conn.execute(
                "INSERT OR REPLACE INTO audio_cache (surah_num, reciter, file_id, file_size) VALUES (?,?,?,?)",
                (surah_num, reciter, file_id, file_size)
            )
        logger.info(f"✅ Cached audio: سورة {surah_num} - {reciter}")
    except Exception as e:
        logger.error(f"save_audio_cache error: {e}")

def register_user(user_id, username, full_name):
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM users WHERE user_id=?", (user_id,))
    if not cur.fetchone():
        cur.execute("INSERT INTO users (user_id, username, full_name) VALUES (?,?,?)",
                    (user_id, username, full_name))
        conn.commit()
        conn.close()
        return True
    else:
        cur.execute("UPDATE users SET username=? WHERE user_id=?", (username, user_id))
        conn.commit()
        conn.close()
        return False

def log_search(user_id, query):
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute("UPDATE users SET searches = searches + 1 WHERE user_id = ?", (user_id,))
    cur.execute("INSERT INTO searches (user_id, query) VALUES (?,?)", (user_id, query[:200]))
    conn.commit()
    conn.close()

def get_global_stats():
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    users = cur.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    searches = cur.execute("SELECT COUNT(*) FROM searches").fetchone()[0]
    hadiths = cur.execute("SELECT COUNT(*) FROM ahadith").fetchone()[0]
    recent = cur.execute("SELECT full_name, username, joined_at FROM users ORDER BY joined_at DESC LIMIT 5").fetchall()
    conn.close()
    return users, searches, hadiths, recent

def get_error_logs(limit=10):
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute("SELECT timestamp, error_type, error_message, user_id FROM error_logs ORDER BY timestamp DESC LIMIT ?", (limit,))
    rows = cur.fetchall()
    conn.close()
    return rows

def clear_error_logs():
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute("DELETE FROM error_logs")
    conn.commit()
    conn.close()

def parse_dorar_html(html: str) -> list:
    """استخراج الأحاديث من HTML الدرر"""
    import re as _re

    SITTA = [
        "صحيح البخاري", "صحيح مسلم",
        "سنن أبي داود", "سنن الترمذي",
        "سنن النسائي", "سنن ابن ماجه",
    ]

    def extract_field(chunk, label):
        m = _re.search(
            r'<span class="info-subtitle">' + _re.escape(label) + r'[^<]*</span>(.*?)(?=<span class="info-subtitle"|</div>)',
            chunk, _re.DOTALL
        )
        if m:
            return _re.sub(r'<[^>]+>', '', m.group(1)).strip()
        return ""

    def clean_text(t):
        t = _re.sub(r'<[^>]+>', ' ', t)
        t = t.replace('&nbsp;', ' ').replace('&amp;', '&')
        t = t.replace('&lt;', '<').replace('&gt;', '>')
        # invisible unicode chars
        t = _re.sub(r'[\u200b-\u200f\u202a-\u202e\u2060-\u2064\ufeff]', '', t)
        t = _re.sub(r'\s+', ' ', t).strip()
        return t

    results = []
    chunks = _re.split(r'(?=<div class="hadith")', html)
    chunks = [c for c in chunks if '<div class="hadith"' in c]

    for i, chunk in enumerate(chunks[:30]):
        # استخرج النص — جرب أكثر من طريقة
        text = ""

        # طريقة 1: span hadith
        m1 = _re.search(r'<span[^>]*class=["\']hadith["\'][^>]*>(.*?)</span>', chunk, _re.DOTALL)
        if m1:
            text = clean_text(m1.group(1))

        # طريقة 2: النص بين div hadith وأول span info-subtitle
        if not text:
            m2 = _re.search(r'<div class="hadith"[^>]*>(.*?)(?=<span class="info-subtitle"|<div class="info")', chunk, _re.DOTALL)
            if m2:
                text = clean_text(m2.group(1))

        # طريقة 3: كل النص قبل الراوي
        if not text:
            full = clean_text(chunk.split('<span class="info-subtitle">')[0] if '<span class="info-subtitle">' in chunk else chunk[:500])
            if 'الراوي:' in full:
                text = full[:full.find('الراوي:')].strip()
            else:
                text = full[:300].strip()

        # تنظيف إضافي
        text = _re.sub(r'^\s*\d+\s*[-–]\s*', '', text)
        if 'الراوي:' in text:
            text = text[:text.find('الراوي:')].strip()
        text = text.strip('.')

        if not text or len(text) < 10:
            continue

        rawi    = extract_field(chunk, "الراوي:")
        mohdith = extract_field(chunk, "المحدث:")
        source  = extract_field(chunk, "المصدر:")
        grade   = extract_field(chunk, "خلاصة حكم المحدث:")

        in_sitta = any(k in source for k in SITTA)
        if not in_sitta and not source:
            info_m = _re.search(r'class="info"[^>]*>(.*?)(?=<div class="hadith"|$)', chunk, _re.DOTALL)
            if info_m:
                in_sitta = any(k in info_m.group(1) for k in SITTA)

        results.append({
            "id": f"api_{i}",
            "text": text,
            "rawi": rawi,
            "source": source,
            "grade": grade,
            "mohdith": mohdith,
            "hadith_id": str(i),
            "sharh_id": None,
            "_in_sitta": in_sitta,
        })

    # أولوية الترتيب: صحيح مسلم > البخاري > بقية الستة
    PRIORITY = {
        "صحيح مسلم": 0,
        "صحيح البخاري": 1,
        "سنن أبي داود": 2,
        "سنن الترمذي": 3,
        "سنن النسائي": 4,
        "سنن ابن ماجه": 5,
    }

    def sort_key(r):
        src = r.get("source", "")
        for name, rank in PRIORITY.items():
            if name in src:
                return rank
        return 9

    # فلتر: الكتب الستة فقط - صارم 100%
    sitta = [r for r in results if r["_in_sitta"]]
    
    # إذا ما في نتائج من الستة، نرجع قائمة فاضية (بدل إرجاع كل النتائج)
    if not sitta:
        logger.info("[DORAR] لا توجد نتائج من الكتب الستة")
        return []
    
    final = sitta

    final.sort(key=sort_key)

    for r in final:
        r.pop("_in_sitta", None)

    return final

# ==================== تحسينات البحث ====================

# كلمات تُحذف من الـ query
SEARCH_STOP_WORDS = [
    "حديث عن", "حديث", "قال النبي", "قال رسول الله",
    "قال النبي صلى الله عليه وسلم", "عن النبي", "روى",
    "ما قاله النبي عن", "ما قال النبي عن",
]

# قاموس تصحيح إملائي وتوسيع
SPELL_SUGGESTIONS = {
    "الوزغ": "الوزغة الفويسق",
    "وزغ": "الوزغة الفويسق",
    "الفأر": "الفأرة الفويسقة",
    "النملة": "النمل",
    "الغيبه": "الغيبة",
    "الصبر": "الصبر",
    "الصله": "صلة الرحم",
    "الصلة": "صلة الرحم",
    "الحسد": "الحسد",
    "التوبه": "التوبة",
    "الاستغفار": "الاستغفار",
    "النيه": "النية",
    "الامانه": "الأمانة",
    "الكذب": "الكذب",
    "الصدق": "الصدق",
    "الصلاه": "الصلاة",
    "الزكاه": "الزكاة",
    "الصيام": "الصوم",
    "الجنه": "الجنة",
    "النار": "النار",
    "الاخلاق": "الأخلاق",
    "القران": "القرآن",
    "الدعا": "الدعاء",
    "الذكر": "الذكر",
}

# أسماء رواة معروفين للبحث المباشر
KNOWN_RAWIS = [
    # الصحابة الكبار
    "أبو هريرة", "ابن عمر", "ابن عباس", "عائشة", "أنس بن مالك",
    "جابر بن عبدالله", "أبو سعيد الخدري", "ابن مسعود", "علي بن أبي طالب",
    "عمر بن الخطاب", "أبو بكر الصديق", "عثمان بن عفان", "معاذ بن جبل",
    "أبو موسى الأشعري", "البراء بن عازب", "حذيفة بن اليمان",
    # المزيد
    "سلمان الفارسي", "أبو ذر الغفاري", "أبو الدرداء", "عبادة بن الصامت",
    "أبو أيوب الأنصاري", "زيد بن ثابت", "أبو أمامة", "عقبة بن عامر",
    "النعمان بن بشير", "واثلة بن الأسقع", "معاوية بن أبي سفيان",
    "عبدالله بن عمرو", "سمرة بن جندب", "أبو مسعود الأنصاري",
    "سهل بن سعد", "رافع بن خديج", "عمران بن حصين",
]

def clean_search_query(query: str) -> str:
    """تنظيف الـ query من الكلمات غير المفيدة"""
    q = query.strip()
    for phrase in SEARCH_STOP_WORDS:
        q = q.replace(phrase, "").strip()
    # أزل علامات الترقيم من البداية والنهاية
    q = q.strip(".,،؟!؟")
    return q.strip() or query.strip()

def get_spell_suggestion(query: str) -> str:
    """هل في اقتراح إملائي أو توسيع للكلمة؟ يرجع الاقتراح أو فارغ"""
    q = query.strip()
    for word, suggestion in SPELL_SUGGESTIONS.items():
        if word in q and suggestion != q:
            return suggestion
    return ""

def is_rawi_search(query: str) -> str:
    """
    هل يبحث المستخدم باسم راوٍ؟
    يرجع query مناسب للـ API أو فارغ
    """
    q = query.strip()
    # تحقق من الرواة المعروفين
    for rawi in KNOWN_RAWIS:
        if rawi in q or q in rawi:
            return rawi
    # أي اسم يبدو راوياً (أبو، ابن، + اسم)
    import re as _re
    if _re.match(r'^(أبو|ابن|أم|عبد)\s+\w+', q):
        return q
    return ""

# ترتيب مصادر الحديث حسب الأولوية
_SOURCE_PRIORITY = {
    "مسلم": 1,
    "صحيح مسلم": 1,
    "البخاري": 2,
    "صحيح البخاري": 2,
    "أبو داود": 3,
    "سنن أبي داود": 3,
    "الترمذي": 4,
    "سنن الترمذي": 4,
    "النسائي": 5,
    "سنن النسائي": 5,
    "ابن ماجه": 6,
    "سنن ابن ماجه": 6,
}

_KUTUB_SITTA = {"مسلم", "صحيح مسلم", "البخاري", "صحيح البخاري",
                "أبو داود", "سنن أبي داود", "الترمذي", "سنن الترمذي",
                "النسائي", "سنن النسائي", "ابن ماجه", "سنن ابن ماجه"}

def _source_priority(h: dict) -> int:
    """أعطِ أولوية للمصدر — كلما قل الرقم كلما كان أولوية أعلى"""
    src = h.get("source", "") or ""
    for key, pri in _SOURCE_PRIORITY.items():
        if key in src:
            return pri
    return 99  # مصادر أخرى آخراً

def _grade_priority(h: dict) -> int:
    """صحيح أولاً ثم حسن"""
    grade = (h.get("grade") or "").strip()
    if "صحيح" in grade:
        return 1
    if "حسن" in grade:
        return 2
    return 3

def sort_results(results: list) -> list:
    """رتّب النتائج: مسلم ← البخاري ← الكتب الستة ← غيرها، ثم صحيح ← حسن"""
    return sorted(results, key=lambda h: (_source_priority(h), _grade_priority(h)))

def filter_kutub_sitta(results: list) -> list:
    """فلتر الكتب الستة فقط"""
    filtered = [h for h in results if any(k in (h.get("source") or "") for k in _KUTUB_SITTA)]
    return filtered if filtered else results  # لو ما في نتائج ارجع الكل

# ==================== تحدي الصديق ====================

import uuid as _uuid_fc
import json as _json_fc

def create_friend_challenge(creator_id: int, creator_name: str, questions: list) -> str:
    """أنشئ تحدياً جديداً وارجع challenge_id"""
    challenge_id = _uuid_fc.uuid4().hex[:10]
    with sqlite3.connect("bot.db") as conn:
        conn.execute(
            "INSERT INTO friend_challenges (challenge_id, creator_id, creator_name, questions_json, created_at, status) VALUES (?,?,?,?,?,?)",
            (challenge_id, creator_id, creator_name,
             _json_fc.dumps(questions, ensure_ascii=False),
             _dt.datetime.now(AMMAN_TZ).isoformat(), "waiting")
        )
    return challenge_id

def get_friend_challenge(challenge_id: str) -> dict | None:
    with sqlite3.connect("bot.db") as conn:
        row = conn.execute(
            "SELECT challenge_id, creator_id, creator_name, opponent_id, opponent_name, questions_json, creator_score, opponent_score, status FROM friend_challenges WHERE challenge_id=?",
            (challenge_id,)
        ).fetchone()
    if not row:
        return None
    return {
        "challenge_id": row[0], "creator_id": row[1], "creator_name": row[2],
        "opponent_id": row[3], "opponent_name": row[4],
        "questions": _json_fc.loads(row[5]),
        "creator_score": row[6], "opponent_score": row[7], "status": row[8],
    }

def save_fc_score(challenge_id: str, user_id: int, user_name: str, score: int):
    """احفظ نتيجة لاعب"""
    ch = get_friend_challenge(challenge_id)
    if not ch:
        return
    with sqlite3.connect("bot.db") as conn:
        if ch["creator_id"] == user_id:
            conn.execute(
                "UPDATE friend_challenges SET creator_score=?, status=? WHERE challenge_id=?",
                (score, "in_progress", challenge_id)
            )
        else:
            conn.execute(
                "UPDATE friend_challenges SET opponent_id=?, opponent_name=?, opponent_score=? WHERE challenge_id=?",
                (user_id, user_name, score, challenge_id)
            )
        ch2 = get_friend_challenge(challenge_id)
        if ch2 and ch2["creator_score"] >= 0 and ch2["opponent_score"] >= 0:
            conn.execute(
                "UPDATE friend_challenges SET status=? WHERE challenge_id=?",
                ("finished", challenge_id)
            )

def build_fc_result(ch: dict) -> str:
    """رسالة النتيجة النهائية للتحدي مع تقييم"""
    total = len(ch["questions"])
    c_score = ch["creator_score"]
    o_score = ch["opponent_score"]
    c_name = ch["creator_name"]
    o_name = ch["opponent_name"] or "صديقك"
    
    # حساب النسبة المئوية
    c_percent = (c_score / total) * 100
    o_percent = (o_score / total) * 100
    
    # النجوم
    c_stars = "⭐" * c_score + "☆" * (total - c_score)
    o_stars = "⭐" * o_score + "☆" * (total - o_score)
    
    # تقييم الأداء
    def get_rating(score, total):
        percent = (score / total) * 100
        if percent >= 90:
            return "ممتاز 🌟"
        elif percent >= 70:
            return "جيد جداً 👍"
        elif percent >= 50:
            return "جيد ✅"
        else:
            return "يحتاج تحسين 📚"
    
    c_rating = get_rating(c_score, total)
    o_rating = get_rating(o_score, total)
    
    # تحديد الفائز مع فارق النقاط
    if c_score > o_score:
        diff = c_score - o_score
        winner = f"🏆 *الفائز: {c_name}*"
        winner_msg = f"تفوق بـ {diff} نقطة!"
    elif o_score > c_score:
        diff = o_score - c_score
        winner = f"🏆 *الفائز: {o_name}*"
        winner_msg = f"تفوق بـ {diff} نقطة!"
    else:
        winner = "🤝 *تعادل!*"
        winner_msg = "كلاكما رائع! 🎉"
    
    return (
        "⚔️ *نتيجة التحدي النهائية*\n"
        "━━━━━━━━━━━━━━━\n\n"
        f"👤 *{c_name}*\n"
        f"├─ النتيجة: {c_score}/{total} ({c_percent:.0f}%)\n"
        f"├─ {c_stars}\n"
        f"└─ التقييم: {c_rating}\n\n"
        f"👤 *{o_name}*\n"
        f"├─ النتيجة: {o_score}/{total} ({o_percent:.0f}%)\n"
        f"├─ {o_stars}\n"
        f"└─ التقييم: {o_rating}\n\n"
        f"{winner}\n"
        f"{winner_msg}"
    )

# ==================== دوال الاستريك ====================

def get_streak(user_id: int) -> dict:
    """ارجع بيانات الاستريك كـ dict"""
    try:
        with sqlite3.connect("bot.db") as conn:
            row = conn.execute(
                "SELECT streak, max_streak FROM streaks WHERE user_id=?", (user_id,)
            ).fetchone()
        if row:
            return {"streak": row[0], "max": row[1]}
        return {"streak": 0, "max": 0}
    except Exception:
        return {"streak": 0, "max": 0}

def get_today_challenge() -> dict | None:
    """ارجع تحدي اليوم إن وُجد"""
    today = _dt.datetime.now(AMMAN_TZ).strftime("%Y-%m-%d")
    try:
        with sqlite3.connect("bot.db") as conn:
            row = conn.execute(
                "SELECT hadith_text, answer, full_text FROM daily_challenge WHERE date=?",
                (today,)
            ).fetchone()
        if row:
            return {"text": row[0], "answer": row[1], "full": row[2]}
        return None
    except Exception:
        return None

def save_today_challenge(text: str, answer: str, full_text: str):
    """احفظ تحدي اليوم"""
    today = _dt.datetime.now(AMMAN_TZ).strftime("%Y-%m-%d")
    try:
        with sqlite3.connect("bot.db") as conn:
            conn.execute(
                "INSERT OR REPLACE INTO daily_challenge (date, hadith_text, answer, full_text) VALUES (?,?,?,?)",
                (today, text, answer, full_text)
            )
    except Exception as e:
        logger.error(f"save_today_challenge error: {e}")

# ==================== دوال الاختبار ====================

def save_quiz_session(user_id: int, questions: list, index: int, score: int, date: str):
    """احفظ حالة الاختبار في قاعدة البيانات"""
    try:
        import json as _j
        with sqlite3.connect("bot.db") as conn:
            conn.execute(
                """INSERT OR REPLACE INTO quiz_sessions
                   (user_id, questions_json, quiz_index, quiz_score, quiz_date)
                   VALUES (?,?,?,?,?)""",
                (user_id, _j.dumps(questions, ensure_ascii=False), index, score, date)
            )
    except Exception as e:
        logger.error(f"save_quiz_session error: {e}")

# ══════════════════════════════════════════════
# ══════════════════════════════════════════════

# ==================== قدوتي اليوم ====================


def get_qudwati_of_day() -> dict:
    """قصة قدوتي اليوم"""
    day_num = _dt.datetime.now(AMMAN_TZ).timetuple().tm_yday
    return QUDWATI_STORIES[day_num % len(QUDWATI_STORIES)]

async def cmd_qudwati(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض قدوتي اليوم"""
    user = update.effective_user
    qudwa = get_qudwati_of_day()
    
    msg = (
        f"🌟 *قدوتي اليوم: {qudwa['name']}*\n"
        f"━━━━━━━━━━━━━━━\n\n"
        f"📖 *القصة:*\n{qudwa['story']}\n\n"
        f"📜 *الآية:*\n_{qudwa['ayah']}_\n"
        f"📍 ({qudwa['ayah_ref']})\n\n"
        f"💡 *الدروس المستفادة:*\n{qudwa['lesson']}\n\n"
        f"❓ *سؤال:* {qudwa['question']}\n"
        f"💬 أرسل إجابتك الآن!"
    )
    
    context.user_data["qudwati_waiting"] = True
    context.user_data["qudwati_answer_saved"] = qudwa['answer']
    
    keyboard = InlineKeyboardMarkup([[
        colored_btn("📤 شارك", switch_inline_query="qudwati_today", style="primary")
    ]])
    
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=keyboard)



def build_qudwati_msg(story: dict) -> str:
    type_icon = "🕌" if story["type"] == "نبي" else ("🌸" if story["type"] == "صحابية" else "⭐")

    # تحديد نوع النص: آية أو حديث
    ayah_ref = story.get("ayah_ref", "")
    ayah_text = story.get("ayah", "")
    # إذا كان المرجع يحتوي رقم سورة (مثل "البقرة: 124") فهو آية
    # وإذا كان يحتوي "رواه" أو "صحيح" أو "السيرة" فهو حديث
    hadith_keywords = ["رواه", "صحيح", "السيرة", "سنن", "مسند", "الترمذي", "البخاري", "مسلم", "أحمد", "الطبراني", "الحاكم"]
    is_hadith = any(kw in ayah_ref or kw in ayah_text for kw in hadith_keywords)

    if is_hadith:
        ref_label = "📜 *الحديث الشريف:*"
        ref_text = f'"{ayah_text}"'
        ref_line = f"{ref_label}\n{ref_text}\n_{ayah_ref}_"
    else:
        ref_label = "📖 *الآية الكريمة:*"
        ref_line = f"{ref_label}\n_{{{ayah_text}}}_ [{ayah_ref}]"

    msg = (
        f"🌟 *قدوتي اليوم: {story['name']}*\n"
        f"{type_icon} _{story['type']}_\n"
        "━━━━━━━━━━━━━━━\n\n"
        f"{story['story']}\n\n"
        f"{ref_line}\n\n"
        f"💡 *العبرة:*\n{story['lesson']}\n\n"
        f"❓ *سؤال التفاعل:*\n{story['question']}\n"
        "_أرسل إجابتك وسأخبرك إن كانت صحيحة!_ 👇\n\n"
        f"📚 *المصدر:* {story['source']}"
    )
    return msg

def main_kb(is_admin=False, **kwargs):
    from telegram import ReplyKeyboardMarkup, KeyboardButton
    buttons = [
        [KeyboardButton("🔍 تحقق من حديث"), KeyboardButton("📖 باحث القرآن")],
        [KeyboardButton("🎯 اختبر معلوماتك"), KeyboardButton("🎙️ استمع للقرآن")],
        [KeyboardButton("💬 التحدث مع راوي"), KeyboardButton("❓ سؤال ديني")],
        [KeyboardButton("💰 دعم البوت")],
        [KeyboardButton("📞 تواصل مع المطور")],
    ]
    if is_admin:
        buttons.append([KeyboardButton("⚙️ لوحة التحكم")])
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)


def rawi_kb():
    """كيبورد خاص لوضع راوي - زر خروج فقط"""
    from telegram import ReplyKeyboardMarkup, KeyboardButton
    buttons = [
        [KeyboardButton("🔙 خروج من راوي")]
    ]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)


def search_kb(search_type="قرآن"):
    """كيبورد خاص للبحث - زر خروج فقط"""
    from telegram import ReplyKeyboardMarkup, KeyboardButton
    buttons = [
        [KeyboardButton("🔙 خروج من الباحث")]
    ]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

def admin_main_keyboard():
    from telegram import ReplyKeyboardMarkup, KeyboardButton
    buttons = [
        [KeyboardButton("📢 إشعار متقدم"), KeyboardButton("📊 إحصائيات")],
        [KeyboardButton("📅 إحصائيات الأسبوع"), KeyboardButton("🏆 أنشط المستخدمين")],
        [KeyboardButton("✉️ رسالة خاصة"), KeyboardButton("🗑️ حذف مستخدم")],
        [KeyboardButton("💰 استرداد نجوم"), KeyboardButton("⚠️ سجل الأخطاء")],
        [KeyboardButton("🔙 القائمة الرئيسية")],
    ]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

def cancel_broadcast_keyboard():
    from telegram import ReplyKeyboardMarkup, KeyboardButton
    return ReplyKeyboardMarkup([[KeyboardButton("❌ إلغاء الإشعار")]], resize_keyboard=True)

def advanced_broadcast_keyboard():
    from telegram import ReplyKeyboardMarkup, KeyboardButton
    return ReplyKeyboardMarkup([
        [KeyboardButton("📝 نص"), KeyboardButton("🖼️ صورة")],
        [KeyboardButton("🎤 صوت"), KeyboardButton("🎥 فيديو")],
        [KeyboardButton("📁 ملف"), KeyboardButton("❌ إلغاء الإشعار")],
    ], resize_keyboard=True)

def donation_keyboard():
    from telegram import ReplyKeyboardMarkup, KeyboardButton
    return ReplyKeyboardMarkup([
        [KeyboardButton("⭐ 1 نجمة"), KeyboardButton("⭐ 5 نجوم")],
        [KeyboardButton("⭐ 10 نجوم"), KeyboardButton("⭐ 25 نجمة")],
        [KeyboardButton("⭐ 50 نجمة"), KeyboardButton("⭐ 100 نجمة")],
        [KeyboardButton("🔙 رجوع")],
    ], resize_keyboard=True)

def get_weekly_stats():
    try:
        week_ago = (_dt.datetime.now(AMMAN_TZ) - _dt.timedelta(days=7)).strftime("%Y-%m-%d")
        with sqlite3.connect("bot.db") as conn:
            new_users = conn.execute("SELECT COUNT(*) FROM users WHERE joined_at >= ?", (week_ago,)).fetchone()[0]
            try:
                searches = conn.execute("SELECT COUNT(*) FROM search_history WHERE searched_at >= ?", (week_ago,)).fetchone()[0]
                active = conn.execute("SELECT COUNT(DISTINCT user_id) FROM search_history WHERE searched_at >= ?", (week_ago,)).fetchone()[0]
            except Exception:
                searches = 0; active = new_users
            try:
                donations = conn.execute("SELECT COALESCE(SUM(amount),0) FROM donations WHERE date >= ?", (week_ago,)).fetchone()[0]
            except Exception:
                donations = 0
        return {"new_users": new_users, "searches": searches, "active": active, "donations": donations}
    except Exception:
        return {"new_users": 0, "searches": 0, "active": 0, "donations": 0}

def get_daily_growth():
    try:
        result = []
        with sqlite3.connect("bot.db") as conn:
            for i in range(6, -1, -1):
                day = (_dt.datetime.now(AMMAN_TZ) - _dt.timedelta(days=i)).strftime("%Y-%m-%d")
                count = conn.execute("SELECT COUNT(*) FROM users WHERE joined_at LIKE ?", (f"{day}%",)).fetchone()[0]
                result.append((day, count))
        return result
    except Exception:
        return []

def get_peak_hours():
    try:
        with sqlite3.connect("bot.db") as conn:
            rows = conn.execute(
                "SELECT strftime('%H', searched_at) as hr, COUNT(*) as cnt FROM search_history "
                "WHERE searched_at >= date('now', '-7 days') GROUP BY hr ORDER BY cnt DESC LIMIT 5"
            ).fetchall()
        return [(int(r[0]), r[1]) for r in rows]
    except Exception:
        return []

def get_top_searchers(limit=10):
    try:
        with sqlite3.connect("bot.db") as conn:
            rows = conn.execute(
                "SELECT u.full_name, u.username, COUNT(s.id) as total FROM users u "
                "JOIN search_history s ON u.user_id=s.user_id GROUP BY u.user_id ORDER BY total DESC LIMIT ?", (limit,)
            ).fetchall()
        return rows
    except Exception:
        return []

def get_recent_users(limit=10):
    try:
        with sqlite3.connect("bot.db") as conn:
            rows = conn.execute("SELECT full_name, username, joined_at FROM users ORDER BY joined_at DESC LIMIT ?", (limit,)).fetchall()
        return rows
    except Exception:
        return []

def get_user_info(query):
    try:
        with sqlite3.connect("bot.db") as conn:
            if query.startswith("@"):
                row = conn.execute("SELECT user_id, full_name, username, joined_at FROM users WHERE username=?", (query[1:],)).fetchone()
            else:
                row = conn.execute("SELECT user_id, full_name, username, joined_at FROM users WHERE user_id=?", (int(query),)).fetchone()
        if row:
            return {"id": row[0], "name": row[1], "username": row[2], "joined": row[3]}
        return None
    except Exception:
        return None

def get_all_donors():
    try:
        with sqlite3.connect("bot.db") as conn:
            rows = conn.execute(
                "SELECT u.full_name, u.username, p.stars FROM premium p JOIN users u ON p.user_id=u.user_id ORDER BY p.stars DESC"
            ).fetchall()
        return rows
    except Exception:
        return []

def streak_emoji(streak):
    if streak >= 365: return "👑"
    elif streak >= 100: return "💎"
    elif streak >= 30: return "⭐"
    elif streak >= 14: return "🔥"
    elif streak >= 7: return "✨"
    elif streak >= 3: return "🌱"
    else: return "🌟"

async def _fetch_dorar(query: str) -> list:
    """طلب واحد لـ API الدرر"""
    url = "https://dorar.net/dorar_api.json"
    params = {"skey": query}
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; HadithBot/1.0)",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://dorar.net/"
    }
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=12)) as session:
        async with session.get(url, params=params, headers=headers) as resp:
            if resp.status != 200:
                return []
            data = json.loads(await resp.text())
            ahadith = data.get("ahadith", {})
            html = ahadith.get("result", "") if isinstance(ahadith, dict) else ""
            if not html:
                return []
            return parse_dorar_html(html)

async def search_dorar_api(query: str) -> list:
    """البحث في API الدرر مع Cache و Retry"""
    # تنظيف الـ query
    clean_q = clean_search_query(query)

    # تحقق من الـ cache
    cached = cache_get(clean_q)
    if cached is not None:
        logger.info(f"[CACHE] hit: {clean_q[:30]}")
        return cached

    # حاول مرتين مع انتظار بينهما
    results = []
    for attempt in range(2):
        try:
            results = await _fetch_dorar(clean_q)
            if results:
                break
            if attempt == 0:
                logger.info(f"[DORAR] retry for: {clean_q[:30]}")
                await asyncio.sleep(2)
        except Exception as e:
            logger.warning(f"[DORAR] attempt {attempt+1} error: {e}")
            if attempt == 0:
                await asyncio.sleep(2)

    if results:
        results = sort_results(results)  # رتّب: مسلم أولاً ثم البخاري
        logger.info(f"[DORAR] {len(results)} نتيجة لـ: {clean_q[:30]}")
        cache_set(clean_q, results)
        return results

    # fallback: cache قديم
    old = _search_cache.get(clean_q.strip().lower())
    return old[0] if old else []

# ==================== بحث ذكي محسّن بالـ AI ====================
async def smart_hadith_search(query: str, use_ai_enhancement=True) -> list:
    """
    بحث ذكي في الأحاديث مع تحسين بالـ AI
    - يستخدم cache أولاً
    - يحسّن استعلام البحث بالـ AI إذا النتائج قليلة
    - يجرب محاولات متعددة ذكية
    - النتائج من الكتب الستة فقط
    """
    # فحص الـ cache أولاً (من hadith_cache الجديد)
    cache_key = f"smart_hadith:{query}"
    cached = hadith_cache.get(cache_key)
    if cached:
        logger.info(f"[SMART_CACHE] hit: {query[:30]}")
        return cached
    
    # المحاولة 1: البحث العادي
    logger.info(f"[SMART_SEARCH] محاولة 1: البحث المباشر")
    results = await search_dorar_api(query)
    
    # إذا وجدنا نتائج كافية، نرجعها مباشرة
    if len(results) >= 3:
        logger.info(f"[SMART_SEARCH] ✅ وجدنا {len(results)} نتيجة")
        hadith_cache.set(cache_key, results)
        return results
    
    # المحاولة 2: استخدام AI لتحسين الاستعلام
    if use_ai_enhancement:
        logger.info(f"[SMART_SEARCH] محاولة 2: تحسين بالـ AI")
        try:
            enhanced_query = await enhance_search_with_ai(query)
            if enhanced_query and enhanced_query != query:
                logger.info(f"[AI_ENHANCE] استعلام محسّن: '{enhanced_query}'")
                ai_results = await search_dorar_api(enhanced_query)
                
                # دمج النتائج بدون تكرار
                seen_texts = {r.get('text', '')[:100] for r in results}
                for r in ai_results:
                    if r.get('text', '')[:100] not in seen_texts:
                        results.append(r)
                        seen_texts.add(r.get('text', '')[:100])
                
                if len(results) >= 3:
                    logger.info(f"[SMART_SEARCH] ✅ AI أضاف نتائج - المجموع: {len(results)}")
                    hadith_cache.set(cache_key, results)
                    return results
        except Exception as e:
            logger.warning(f"[AI_ENHANCE] خطأ: {e}")
    
    # المحاولة 3: تبسيط الاستعلام يدوياً (حذف كلمات زائدة)
    if len(results) < 3:
        logger.info(f"[SMART_SEARCH] محاولة 3: تبسيط يدوي")
        simplified = simplify_query(query)
        if simplified != query:
            logger.info(f"[SIMPLIFY] استعلام مبسط: '{simplified}'")
            simple_results = await search_dorar_api(simplified)
            
            seen_texts = {r.get('text', '')[:100] for r in results}
            for r in simple_results:
                if r.get('text', '')[:100] not in seen_texts:
                    results.append(r)
                    seen_texts.add(r.get('text', '')[:100])
    
    # حفظ في الـ cache
    if results:
        logger.info(f"[SMART_SEARCH] ✅ نتيجة نهائية: {len(results)} حديث")
        hadith_cache.set(cache_key, results)
    else:
        logger.info(f"[SMART_SEARCH] ⚠️ لا توجد نتائج من الكتب الستة")
    
    return results

# ==================== شرح الأحاديث بالـ AI ====================
async def explain_hadith_with_ai(hadith_text: str, source: str = "", grade: str = "") -> str:
    """
    شرح الحديث بالذكاء الاصطناعي - نسخة محسّنة ومفصّلة
    """
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
    if not GEMINI_API_KEY:
        return "⚠️ ميزة الشرح بالذكاء الاصطناعي غير متوفرة حالياً"
    
    # تحذير للأحاديث الضعيفة
    grade_warning = ""
    if grade and ("ضعيف" in grade or "موضوع" in grade or "منكر" in grade):
        grade_warning = f"\n\n⚠️ **تنبيه مهم:** هذا حديث {grade}\nلا يُعمل به ويُذكر للتحذير فقط\n"
    
    prompt = f"""أنت عالم حديث متخصص ومُعلّم ماهر. مهمتك شرح الأحاديث النبوية بطريقة واضحة ومفصلة.

**الحديث:**
{hadith_text}

**المصدر:** {source if source else "غير محدد"}

---

**اشرح الحديث بالتفصيل التالي:**

**📌 المعنى الإجمالي:**
اشرح معنى الحديث بلغة بسيطة وواضحة (4-5 أسطر). وضّح السياق والمقصد العام.

**📚 شرح الكلمات:**
إذا كان هناك كلمات صعبة أو مصطلحات، اشرحها بإيجاز.

**💡 الفوائد والدروس:**
اذكر 3-4 فوائد عملية من الحديث:
• الفائدة الأولى...
• الفائدة الثانية...
• الفائدة الثالثة...

**✨ التطبيق العملي:**
كيف نطبق هذا الحديث في حياتنا اليومية؟ أعط أمثلة واقعية وعملية.

---

**شروط الشرح:**
- لغة عربية فصحى بسيطة
- فقرات قصيرة سهلة القراءة
- أمثلة واقعية من حياتنا
- الشرح بين 250-350 كلمة
- استخدم رموز: 📌 💡 ✨ ⭐ 🌟
- اجعله ملهماً وعملياً"""

    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent?key={GEMINI_API_KEY}"
        body = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "maxOutputTokens": 800,
                "temperature": 0.5,
                "topP": 0.9
            }
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=body, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if "candidates" in data and data["candidates"]:
                        explanation = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                        
                        # تنسيق جميل
                        formatted = (
                            f"━━━━━━━━━━━━━━━\n"
                            f"🤖 **شرح الحديث بالذكاء الاصطناعي**\n"
                            f"━━━━━━━━━━━━━━━\n"
                            f"{grade_warning}\n"
                            f"{explanation}\n\n"
                            f"━━━━━━━━━━━━━━━\n"
                            f"💡 هذا شرح توضيحي بالذكاء الاصطناعي"
                        )
                        
                        return formatted
        
        return "⚠️ حدث خطأ في الاتصال بخدمة الشرح"
        
    except Exception as e:
        logger.error(f"Error in explain_hadith_with_ai: {e}")
        return "⚠️ حدث خطأ في الشرح. حاول مرة أخرى."


def simplify_query(query: str) -> str:
    """
    تبسيط الاستعلام يدوياً بحذف الكلمات الزائدة
    """
    # حذف كلمات شائعة
    stop_words = [
        'حديث', 'عن', 'قال', 'النبي', 'رسول', 'الله', 'صلى الله عليه وسلم',
        'روى', 'ما', 'هل', 'كيف', 'متى', 'أين', 'لماذا', 'ماذا',
        'في', 'من', 'إلى', 'على', 'عند', 'مع', 'ب', 'ل', 'ك'
    ]
    
    # تحويل لكلمات
    words = query.split()
    
    # حذف الكلمات الزائدة
    filtered = [w for w in words if w not in stop_words and len(w) > 1]
    
    # إرجاع أول 3 كلمات
    simplified = ' '.join(filtered[:3])
    
    return simplified if simplified else query


async def chat_with_rawi(question: str, user_name: str = "أخي", user_id: int = None, context = None) -> str:
    """
    التحدث مع راوي - AI متخصص في الإجابة على الأسئلة الإسلامية
    بأسلوب دافئ وواضح ومدعوم بالأدلة - مع ذاكرة محادثة
    """
    if not GROQ_API_KEY:
        return "⚠️ ميزة التحدث مع راوي غير متوفرة حالياً. جرّب لاحقاً!"
    
    # الحصول على تاريخ المحادثة
    if context and user_id:
        if "rawi_history" not in context.user_data:
            context.user_data["rawi_history"] = []
        
        conversation_history = context.user_data["rawi_history"]
        
        # حد أقصى 10 رسائل (5 تبادلات) للحفاظ على الذاكرة
        if len(conversation_history) > 10:
            conversation_history = conversation_history[-10:]
            context.user_data["rawi_history"] = conversation_history
    else:
        conversation_history = []
    
    # Prompt مختصر
    system_prompt = f"""أنت "راوي" - مساعد إسلامي ذكي في بوت راوي.

**دورك:**
1. أجب على الأسئلة الشرعية بدليل من القرآن والسنة
2. ساعد المستخدمين في استخدام البوت
3. كن دافئاً ومختصراً

**ميزات البوت:**
• 🔍 تحقق من حديث - بحث الأحاديث
• 📖 باحث القرآن - بحث في القرآن
• 🤲 دعاء اليوم - دعاء يومي
• 🎯 اختبر معلوماتك - اختبار إسلامي
• 🌟 قدوتي اليوم - قصص الأنبياء والصحابة
• 🎙️ استمع للقرآن - تلاوات القراء

**قواعد:**
- لا تفتي في: الطلاق، الميراث، القضايا المعقدة
- لا تخترع أحاديث
- كن مختصراً وواضحاً
- **أجب بالعربية فقط - ممنوع أي لغة ثانية**

**أسلوب الرد:**
- للأسئلة الشرعية: السلام عليكم {user_name} 🌙 + إجابة مختصرة + دليل
- لأسئلة البوت: شرح بسيط + كيفية الاستخدام
- للمحادثة: رد طبيعي ودافئ

كن مختصراً ومفيداً. **رد بالعربية فقط.**"""
    
    try:
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        }
        
        # بناء الرسائل مع التاريخ
        messages = [{"role": "system", "content": system_prompt}]
        
        # إضافة تاريخ المحادثة
        for msg in conversation_history:
            messages.append(msg)
        
        # إضافة السؤال الحالي
        messages.append({"role": "user", "content": question})
        
        body = {
            "model": "llama-3.3-70b-versatile",
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 1000,
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=body, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    answer = data["choices"][0]["message"]["content"].strip()
                    
                    # حفظ في التاريخ
                    if context and user_id:
                        context.user_data["rawi_history"].append({"role": "user", "content": question})
                        context.user_data["rawi_history"].append({"role": "assistant", "content": answer})
                    
                    return answer
                else:
                    return "⚠️ عذراً، حدث خطأ في الاتصال. حاول مرة أخرى."
        
    except Exception as e:
        logger.error(f"Error in chat_with_rawi: {e}")
        return "⚠️ عذراً، حدث خطأ. حاول مرة أخرى."


async def enhance_search_with_ai(query: str) -> str:
    """
    استخدام AI لتحسين استعلام البحث
    يحوّل الأسئلة المعقدة لكلمات مفتاحية أفضل
    """
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
    if not GEMINI_API_KEY:
        return query
    
    prompt = f"""أنت خبير في البحث عن الأحاديث النبوية من الكتب الستة فقط.

المستخدم يبحث عن: "{query}"

مهمتك: استخرج الكلمات المفتاحية الأساسية للبحث (1-3 كلمات فقط).

قواعد مهمة:
1. احذف: "حديث"، "قال النبي"، "روى"، "عن"، أدوات الاستفهام
2. ركّز على الموضوع الأساسي فقط
3. استخدم كلمات بسيطة بدون تشكيل
4. إذا كان سؤال، حوّله لموضوع

أمثلة:
- "ما حكم الصلاة في البيت؟" → "صلاة البيت"
- "حديث عن فضل الصدقة" → "فضل الصدقة"
- "قال النبي عن الوزغ" → "الوزغ"
- "روى أبو هريرة عن الجنة" → "الجنة"
- "هل يجوز قتل الوزغة؟" → "الوزغ"

الجواب (كلمات مفتاحية فقط):"""

    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite-preview:generateContent?key={GEMINI_API_KEY}"
        body = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "maxOutputTokens": 20,  # أقصر للدقة
                "temperature": 0.05,    # أقل للدقة
                "topP": 0.7
            }
        }
        
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as session:
            async with session.post(url, json=body) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    enhanced = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                    # تنظيف النتيجة
                    enhanced = enhanced.replace('\n', ' ').strip()
                    # حذف علامات الترقيم والتشكيل
                    enhanced = re.sub(r'[.,،؛:؟!«»""(){}[\]]', '', enhanced)
                    # حذف كلمات زائدة
                    stop_words = ['حديث', 'قال', 'النبي', 'روى', 'عن', 'في', 'من', 'إلى']
                    words = enhanced.split()
                    words = [w for w in words if w not in stop_words]
                    enhanced = ' '.join(words[:3])  # أقصى 3 كلمات
                    
                    if len(enhanced) > 50 or not enhanced:  # طويل جداً أو فاضي
                        return query
                    return enhanced if enhanced else query
    except Exception as e:
        logger.warning(f"[AI_ENHANCE] خطأ في التحسين: {e}")
    
    return query

def get_random_hadith(book_name: str = None):
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute("SELECT text, source, grade FROM ahadith ORDER BY RANDOM() LIMIT 1")
    row = cur.fetchone()
    conn.close()
    if row:
        return row
    return ("إنما الأعمال بالنيات", "صحيح البخاري (1)", "صحيح")

# ==================== الإشعارات المجدولة ====================

ADHKAR_SABAH = [
    ("سُبْحَانَ اللهِ وَبِحَمْدِهِ", "100 مرة صباحاً تحط الخطايا وإن كانت مثل زبد البحر", "صحيح مسلم"),
    ("اللَّهُمَّ أَنْتَ رَبِّي لَا إِلَهَ إِلَّا أَنْتَ، خَلَقْتَنِي وَأَنَا عَبْدُكَ", "سيد الاستغفار - من قاله موقناً فمات من يومه دخل الجنة", "صحيح البخاري"),
    ("اللَّهُمَّ بِكَ أَصْبَحْنَا وَبِكَ أَمْسَيْنَا وَبِكَ نَحْيَا وَبِكَ نَمُوتُ وَإِلَيْكَ النُّشُورُ", "يقال صباحاً", "سنن الترمذي"),
    ("أَصْبَحْنَا وَأَصْبَحَ الْمُلْكُ لِلَّهِ وَالْحَمْدُ لِلَّهِ", "يقال صباحاً", "صحيح مسلم"),
    ("اللَّهُمَّ إِنِّي أَسْأَلُكَ الْعَفْوَ وَالْعَافِيَةَ فِي الدُّنْيَا وَالْآخِرَةِ", "من الأذكار المأثورة صباحاً ومساءً", "سنن أبي داود"),
    ("بِسْمِ اللهِ الَّذِي لَا يَضُرُّ مَعَ اسْمِهِ شَيْءٌ فِي الْأَرْضِ وَلَا فِي السَّمَاءِ وَهُوَ السَّمِيعُ الْعَلِيمُ", "3 مرات - لم يضره شيء", "سنن أبي داود"),
    ("رَضِيتُ بِاللهِ رَبَّاً، وَبِالإِسْلَامِ دِيناً، وَبِمُحَمَّدٍ ﷺ نَبِيَّاً", "3 مرات - حق على الله أن يرضيه", "سنن أبي داود"),
    ("اللَّهُمَّ عَافِنِي فِي بَدَنِي، اللَّهُمَّ عَافِنِي فِي سَمْعِي، اللَّهُمَّ عَافِنِي فِي بَصَرِي", "3 مرات", "سنن أبي داود"),
]

ADHKAR_MASAA = [
    ("سُبْحَانَ اللهِ وَبِحَمْدِهِ", "100 مرة مساءً تحط الخطايا وإن كانت مثل زبد البحر", "صحيح مسلم"),
    ("اللَّهُمَّ بِكَ أَمْسَيْنَا وَبِكَ أَصْبَحْنَا وَبِكَ نَحْيَا وَبِكَ نَمُوتُ وَإِلَيْكَ الْمَصِيرُ", "يقال مساءً", "سنن الترمذي"),
    ("أَمْسَيْنَا وَأَمْسَى الْمُلْكُ لِلَّهِ وَالْحَمْدُ لِلَّهِ", "يقال مساءً", "صحيح مسلم"),
    ("اللَّهُمَّ إِنِّي أَمْسَيْتُ أُشْهِدُكَ وَأُشْهِدُ حَمَلَةَ عَرْشِكَ وَمَلَائِكَتَكَ وَجَمِيعَ خَلْقِكَ أَنَّكَ أَنْتَ اللهُ لَا إِلَهَ إِلَّا أَنْتَ", "4 مرات - أعتقه الله من النار", "سنن أبي داود"),
    ("اللَّهُمَّ إِنِّي أَسْأَلُكَ الْعَفْوَ وَالْعَافِيَةَ فِي الدُّنْيَا وَالْآخِرَةِ", "من الأذكار المأثورة صباحاً ومساءً", "سنن أبي داود"),
    ("بِسْمِ اللهِ الَّذِي لَا يَضُرُّ مَعَ اسْمِهِ شَيْءٌ فِي الْأَرْضِ وَلَا فِي السَّمَاءِ وَهُوَ السَّمِيعُ الْعَلِيمُ", "3 مرات - لم يضره شيء", "سنن أبي داود"),
    ("أَعُوذُ بِكَلِمَاتِ اللهِ التَّامَّاتِ مِنْ شَرِّ مَا خَلَقَ", "3 مرات مساءً - لا يضره لدغة", "صحيح مسلم"),
    ("اللَّهُمَّ عَافِنِي فِي بَدَنِي، اللَّهُمَّ عَافِنِي فِي سَمْعِي، اللَّهُمَّ عَافِنِي فِي بَصَرِي", "3 مرات", "سنن أبي داود"),
]

# ==================== نظام Premium ====================
# ===== نظام التيرات =====
# ⭐ Tier 1: 1+ نجمة  → بحث بالموضوع
# ⭐ Tier 2: 5+ نجوم  → المفضلة
# ⭐ Tier 3: 25+ نجمة → تخصيص وقت الإشعار + كل المزايا
TIER2_STARS = 5

def save_favorite(user_id: int, h: dict) -> bool:
    """حفظ حديث في المفضلة - يرجع True لو نجح"""
    try:
        conn = sqlite3.connect("bot.db")
        conn.execute("""
            INSERT OR IGNORE INTO favorites (user_id, hadith_text, rawi, source, grade)
            VALUES (?,?,?,?,?)
        """, (user_id, h["text"], h.get("rawi",""), h.get("source",""), h.get("grade","")))
        changed = conn.total_changes
        conn.commit()
        conn.close()
        return changed > 0
    except:
        return False

def remove_favorite(user_id: int, hadith_text: str):
    conn = sqlite3.connect("bot.db")
    conn.execute("DELETE FROM favorites WHERE user_id=? AND hadith_text=?", (user_id, hadith_text))
    conn.commit()
    conn.close()

def get_favorites(user_id: int) -> list:
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute("SELECT hadith_text, rawi, source, grade, saved_at FROM favorites WHERE user_id=? ORDER BY saved_at DESC", (user_id,))
    rows = cur.fetchall()
    conn.close()
    return [{"text":r[0],"rawi":r[1],"source":r[2],"grade":r[3],"id":f"fav_{i}","hadith_id":str(i),"mohdith":"","sharh_id":None} for i,r in enumerate(rows)]

def count_favorites(user_id: int) -> int:
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM favorites WHERE user_id=?", (user_id,))
    count = cur.fetchone()[0]
    conn.close()
    return count

def log_search_history(user_id: int, query: str, count: int):
    """تسجيل البحث في تاريخ المستخدم"""
    try:
        conn = sqlite3.connect("bot.db")
        conn.execute("INSERT INTO search_history (user_id, query, results_count) VALUES (?,?,?)",
                     (user_id, query[:200], count))
        conn.commit()
        conn.close()
    except:
        pass

def get_user_stats(user_id: int) -> dict:
    """إحصائيات شخصية للمستخدم"""
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM searches WHERE user_id=?", (user_id,))
    total = cur.fetchone()[0]
    cur.execute("SELECT query FROM searches WHERE user_id=? ORDER BY id DESC LIMIT 100", (user_id,))
    words = []
    for (q,) in cur.fetchall():
        words.extend(w for w in q.split() if len(w) > 2)
    from collections import Counter
    top = Counter(words).most_common(3)
    cur.execute("SELECT joined_at FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    joined = row[0][:10] if row else "غير محدد"
    fav_count = count_favorites(user_id)
    conn.close()
    return {"total": total, "top": top, "joined": joined, "favs": fav_count}

def save_favorite_note(user_id: int, hadith_text: str, note: str):
    """حفظ ملاحظة على حديث في المفضلة"""
    conn = sqlite3.connect("bot.db")
    conn.execute("UPDATE favorites SET note=? WHERE user_id=? AND hadith_text=?",
                 (note[:300], user_id, hadith_text))
    conn.commit()
    conn.close()

def get_subscribers(col: str) -> list:
    """جلب المشتركين في خدمة معينة"""
    # Whitelist للأمان - فقط أعمدة معينة مسموحة
    allowed_cols = ['daily_hadith', 'weekly_hadith', 'quiz_reminders']
    if col not in allowed_cols:
        return []
    
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute(f"SELECT user_id FROM users WHERE {col} = 1")
    rows = cur.fetchall()
    conn.close()
    return [r[0] for r in rows]

def toggle_subscription(user_id: int, col: str) -> bool:
    """تبديل الاشتراك - يرجع القيمة الجديدة"""
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute(f"SELECT {col} FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    current = row[0] if row else 0
    new_val = 0 if current else 1
    cur.execute(f"UPDATE users SET {col}=? WHERE user_id=?", (new_val, user_id))
    conn.commit()
    conn.close()
    return bool(new_val)

    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    uname = username.lstrip("@")
    cur.execute("SELECT user_id FROM users WHERE username=?", (uname,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None

# ==================== Mood Hadith (حديث على قدك) ====================
DAILY_QUESTIONS = [
    {"q": 'كم عدد أركان الإسلام؟', "options": ['5', '4', '3', '6'], "answer": '5', "explain": 'الشهادتان، الصلاة، الزكاة، الصوم، الحج'},
    {"q": 'ما هي أطول سورة في القرآن؟', "options": ['آل عمران', 'النساء', 'البقرة', 'المائدة'], "answer": 'البقرة', "explain": 'سورة البقرة هي أطول سورة في القرآن الكريم'},
    {"q": 'كم عدد أنبياء الله المذكورين في القرآن؟', "options": ['20', '35', '30', '25'], "answer": '25', "explain": 'ذُكر 25 نبياً بالاسم في القرآن الكريم'},
    {"q": 'ما هو اسم والد النبي إبراهيم عليه السلام؟', "options": ['تارح', 'عمران', 'يشكر', 'آزر'], "answer": 'آزر', "explain": 'ذكر القرآن اسم والد إبراهيم آزر'},
    {"q": 'في أي شهر نزل القرآن الكريم؟', "options": ['رجب', 'شعبان', 'محرم', 'رمضان'], "answer": 'رمضان', "explain": 'قال تعالى: شهر رمضان الذي أنزل فيه القرآن'},
    {"q": 'كم عدد سور القرآن الكريم؟', "options": ['110', '114', '112', '116'], "answer": '114', "explain": 'يتكون القرآن الكريم من 114 سورة'},
    {"q": 'ما هي السورة التي تعدل ثلث القرآن؟', "options": ['الفلق', 'الفاتحة', 'الكوثر', 'الإخلاص'], "answer": 'الإخلاص', "explain": 'قال النبي ﷺ إن سورة الإخلاص تعدل ثلث القرآن'},
    {"q": 'كم عدد أركان الإيمان؟', "options": ['4', '5', '6', '7'], "answer": '6', "explain": 'الإيمان بالله وملائكته وكتبه ورسله واليوم الآخر والقدر'},
    {"q": 'ما هو أول مسجد بُني في الإسلام؟', "options": ['المسجد الحرام', 'المسجد الأقصى', 'مسجد النبي', 'مسجد قباء'], "answer": 'مسجد قباء', "explain": 'مسجد قباء هو أول مسجد بُني في الإسلام عند هجرة النبي ﷺ'},
    {"q": 'كم سنة استغرق نزول القرآن الكريم؟', "options": ['20 سنة', '30 سنة', '25 سنة', '23 سنة'], "answer": '23 سنة', "explain": 'نزل القرآن الكريم على مدى 23 سنة'},
    {"q": 'ما هو اسم جبل النور الذي نزل فيه الوحي؟', "options": ['جبل عرفات', 'جبل حراء', 'جبل ثور', 'جبل أبي قبيس'], "answer": 'جبل حراء', "explain": 'في غار حراء بجبل النور نزل أول وحي على النبي ﷺ'},
    {"q": 'ما هي أول آية نزلت من القرآن؟', "options": ['بسم الله', 'الحمد لله', 'اقرأ باسم ربك', 'يا أيها المدثر'], "answer": 'اقرأ باسم ربك', "explain": 'أول ما نزل: اقرأ باسم ربك الذي خلق'},
    {"q": 'كم سنة بقي أصحاب الكهف في نومهم؟', "options": ['100 سنة', '200 سنة', '309 سنوات', '400 سنة'], "answer": '309 سنوات', "explain": 'قال تعالى: ولبثوا في كهفهم ثلاث مئة سنين وازدادوا تسعاً'},
    {"q": 'ما هي السورة الوحيدة التي ليس فيها بسملة في أولها؟', "options": ['الفيل', 'التوبة', 'الإخلاص', 'المعوذتان'], "answer": 'التوبة', "explain": 'سورة التوبة لم يُكتب في أولها بسملة'},
    {"q": 'ما هي السورة التي تُسمى عروس القرآن؟', "options": ['الرحمن', 'يس', 'الواقعة', 'الكهف'], "answer": 'الرحمن', "explain": 'سورة الرحمن تُسمى عروس القرآن'},
    {"q": 'من هو النبي الذي ابتلعه الحوت؟', "options": ['إلياس', 'إدريس', 'يونس', 'أيوب'], "answer": 'يونس', "explain": 'يونس عليه السلام ذو النون التقمه الحوت'},
    {"q": 'ما هي مدة نوح عليه السلام في قومه؟', "options": ['300 سنة', '500 سنة', '950 سنة', '1000 سنة'], "answer": '950 سنة', "explain": 'قال تعالى: فلبث فيهم ألف سنة إلا خمسين عاماً'},
    {"q": 'ما هي السورة التي تحتوي على آية الكرسي؟', "options": ['آل عمران', 'النساء', 'المائدة', 'البقرة'], "answer": 'البقرة', "explain": 'آية الكرسي هي الآية 255 من سورة البقرة'},
    {"q": 'أي نبي سكن في مصر وأصبح عزيزها؟', "options": ['موسى', 'يوسف', 'إبراهيم', 'إسحاق'], "answer": 'يوسف', "explain": 'يوسف عليه السلام أصبح عزيز مصر'},
    {"q": 'من هو أول من جمع القرآن في مصحف واحد؟', "options": ['زيد بن ثابت', 'عمر بن الخطاب', 'أبو بكر الصديق', 'علي بن أبي طالب'], "answer": 'أبو بكر الصديق', "explain": 'أبو بكر أمر بجمع القرآن في مصحف واحد'},
    {"q": 'كم ركعة تُصلى صلاة العيد؟', "options": ['ركعتان', 'أربع ركعات', 'ثلاث ركعات', 'ست ركعات'], "answer": 'ركعتان', "explain": 'صلاة العيد ركعتان مع تكبيرات زائدة'},
    {"q": 'ما هي الصلاة الوسطى المذكورة في القرآن؟', "options": ['الفجر', 'الظهر', 'العصر', 'المغرب'], "answer": 'العصر', "explain": 'قال تعالى: حافظوا على الصلوات والصلاة الوسطى — وهي العصر'},
    {"q": 'كم حجة حجّها النبي ﷺ؟', "options": ['ثلاث حجج', 'حجتان', 'لم يحج', 'حجة واحدة'], "answer": 'حجة واحدة', "explain": 'حجّ النبي ﷺ حجة واحدة وهي حجة الوداع عام 10هـ'},
    {"q": 'من هو الصحابي الملقب بـ أمين الأمة؟', "options": ['علي', 'عمر', 'أبو بكر', 'أبو عبيدة'], "answer": 'أبو عبيدة', "explain": 'لقّب النبي ﷺ أبا عبيدة بن الجراح بأمين هذه الأمة'},
    {"q": 'ما هو الفرق بين الزكاة والصدقة؟', "options": ['الزكاة واجبة والصدقة تطوع', 'الصدقة واجبة والزكاة تطوع', 'لا فرق', 'الزكاة للفقراء فقط'], "answer": 'الزكاة واجبة والصدقة تطوع', "explain": 'الزكاة ركن من أركان الإسلام واجبة، والصدقة تطوع مستحب'},
    {"q": 'ما هو أول ما خلق الله؟', "options": ['القلم', 'الماء', 'العرش', 'النور'], "answer": 'القلم', "explain": 'قال النبي ﷺ: أول ما خلق الله القلم فقال له اكتب'},
    {"q": 'ما هي آخر آية نزلت من القرآن؟', "options": ['إذا جاء نصر الله', 'اليوم أكملت لكم دينكم', 'واتقوا يوماً ترجعون', 'قل أعوذ برب الناس'], "answer": 'واتقوا يوماً ترجعون', "explain": 'قيل إن آخر آية نزلت: واتقوا يوماً ترجعون فيه إلى الله'},
    {"q": 'ما هي اسم زوجة فرعون المؤمنة؟', "options": ['هاجر', 'بلقيس', 'آسية', 'مريم'], "answer": 'آسية', "explain": 'آسية بنت مزاحم زوجة فرعون آمنت بالله'},
    {"q": 'من هو النبي الذي كان نجاراً؟', "options": ['زكريا', 'داود', 'سليمان', 'يوسف'], "answer": 'زكريا', "explain": 'كان زكريا عليه السلام نجاراً يعمل بيده'},
    {"q": 'ما هي الآية الأطول في القرآن؟', "options": ['آية الكرسي', 'أول البقرة', 'آية الدَّين', 'آية النكاح'], "answer": 'آية الدَّين', "explain": 'آية الدَّين (البقرة 282) هي الأطول في القرآن'},
    {"q": 'في أي عام وُلد النبي محمد ﷺ؟', "options": ['570م', '568م', '572م', '575م'], "answer": '570م', "explain": 'وُلد النبي ﷺ عام الفيل الموافق 570م'},
    {"q": 'كم عمر النبي ﷺ حين تُوفّي؟', "options": ['60 سنة', '63 سنة', '61 سنة', '65 سنة'], "answer": '63 سنة', "explain": 'تُوفّي النبي ﷺ وعمره 63 سنة'},
    {"q": 'ما هو اسم أم النبي ﷺ؟', "options": ['فاطمة بنت أسد', 'آمنة بنت وهب', 'هالة بنت وهب', 'خديجة بنت خويلد'], "answer": 'آمنة بنت وهب', "explain": 'أم النبي ﷺ هي آمنة بنت وهب'},
    {"q": 'من هو أول من أسلم من الرجال؟', "options": ['علي بن أبي طالب', 'أبو بكر الصديق', 'عمر بن الخطاب', 'زيد بن حارثة'], "answer": 'أبو بكر الصديق', "explain": 'أبو بكر أول من أسلم من الرجال الأحرار'},
    {"q": 'في أي سنة كانت الهجرة النبوية؟', "options": ['620م', '621م', '622م', '623م'], "answer": '622م', "explain": 'الهجرة النبوية كانت عام 622م الموافق 1هـ'},
    {"q": 'كم غزوة غزاها النبي ﷺ بنفسه؟', "options": ['20', '27', '30', '23'], "answer": '27', "explain": 'غزا النبي ﷺ 27 غزوة بنفسه'},
    {"q": 'ما هو اسم ناقة النبي ﷺ؟', "options": ['العضباء فقط', 'القصواء فقط', 'كلها أسماء لها', 'الجدعاء فقط'], "answer": 'كلها أسماء لها', "explain": 'القصواء والعضباء والجدعاء كلها أسماء لناقة النبي ﷺ'},
    {"q": 'في أي معركة كُسرت رَباعيّة النبي ﷺ؟', "options": ['بدر', 'أُحد', 'حنين', 'الخندق'], "answer": 'أُحد', "explain": 'في غزوة أُحد شُجّ وجه النبي ﷺ وكُسرت رَباعيّته'},
    {"q": 'من هي أول زوجات النبي ﷺ؟', "options": ['عائشة', 'حفصة', 'خديجة بنت خويلد', 'زينب بنت جحش'], "answer": 'خديجة بنت خويلد', "explain": 'خديجة رضي الله عنها أول زوجات النبي ﷺ'},
    {"q": 'ما اسم جدّ النبي ﷺ الذي رعاه؟', "options": ['عبدالله', 'عبدالمطلب', 'أبو طالب', 'الزبير'], "answer": 'عبدالمطلب', "explain": 'عبدالمطلب رعى النبي ﷺ بعد وفاة أمه'},
    {"q": 'من هو الصحابي الملقب بسيف الله المسلول؟', "options": ['عمرو بن العاص', 'خالد بن الوليد', 'سعد بن أبي وقاص', 'أبو عبيدة'], "answer": 'خالد بن الوليد', "explain": 'لقّبه النبي ﷺ بسيف الله المسلول'},
    {"q": 'من هو أول مؤذن في الإسلام؟', "options": ['عبدالله بن زيد', 'بلال بن رباح', 'أبو محذورة', 'سعد القرظ'], "answer": 'بلال بن رباح', "explain": 'بلال بن رباح رضي الله عنه هو أول مؤذن في الإسلام'},
    {"q": 'من هو الصحابي الملقب بالفاروق؟', "options": ['أبو بكر', 'علي', 'عمر بن الخطاب', 'عثمان'], "answer": 'عمر بن الخطاب', "explain": 'لُقّب عمر بالفاروق لأن الله فرّق به بين الحق والباطل'},
    {"q": 'من هو الصحابي الملقب بذي النورين؟', "options": ['عثمان بن عفان', 'أبو بكر', 'علي بن أبي طالب', 'طلحة'], "answer": 'عثمان بن عفان', "explain": 'لُقّب بذي النورين لأنه تزوج بنتين للنبي ﷺ'},
    {"q": 'من هو الصحابي الذي بكى النبي ﷺ حين سمع قراءته؟', "options": ['أبو موسى الأشعري', 'معاذ بن جبل', 'عبدالله بن مسعود', 'أبي بن كعب'], "answer": 'عبدالله بن مسعود', "explain": 'بكى النبي ﷺ حين سمع قراءة ابن مسعود للقرآن'},
    {"q": 'من هو الصحابي الملقب بحواري رسول الله؟', "options": ['أبو بكر', 'سعد بن أبي وقاص', 'الزبير بن العوام', 'طلحة بن عبيدالله'], "answer": 'الزبير بن العوام', "explain": 'قال النبي ﷺ: إن لكل نبي حوارياً وحواريّ الزبير'},
    {"q": 'أكمل الحديث: إنما الأعمال...', "options": ['بالنيات', 'بالإخلاص', 'بالقلوب', 'بالإيمان'], "answer": 'بالنيات', "explain": 'الحديث: إنما الأعمال بالنيات وإنما لكل امرئ ما نوى'},
    {"q": 'أكمل الحديث: لا يؤمن أحدكم حتى يحب لأخيه...', "options": ['الخير والهدى', 'ما يحب لنفسه', 'ما يحب لربه', 'الجنة والنعيم'], "answer": 'ما يحب لنفسه', "explain": 'رواه البخاري ومسلم — من أصول الإيمان'},
    {"q": 'أكمل الحديث: المسلم من سلم المسلمون من...', "options": ['قلبه ونيته', 'ظلمه وجوره', 'كلامه وفعله', 'لسانه ويده'], "answer": 'لسانه ويده', "explain": 'رواه البخاري — من جوامع كلمه ﷺ'},
    {"q": 'أكمل الحديث: من كان يؤمن بالله واليوم الآخر فليقل...', "options": ['لا إله إلا الله', 'سبحان الله', 'الحمد لله', 'خيراً أو ليصمت'], "answer": 'خيراً أو ليصمت', "explain": 'رواه البخاري ومسلم — حثّ على صون اللسان'},
    {"q": 'أكمل الحديث: بُني الإسلام على خمس شهادة أن لا إله إلا الله...', "options": ['وإقام الصلاة وإيتاء الزكاة وصوم رمضان وحج البيت', 'والجهاد والصبر والتوكل', 'والصلاة والزكاة والصبر والحج', 'والصوم والحج والصدق والأمانة'], "answer": 'وإقام الصلاة وإيتاء الزكاة وصوم رمضان وحج البيت', "explain": 'حديث ابن عمر رضي الله عنهما في الصحيحين'},
    {"q": 'أكمل الآية: إن مع العسر...', "options": ['يُسرا', 'نصراً مبيناً', 'فرجاً قريباً', 'رحمةً واسعة'], "answer": 'يُسرا', "explain": 'سورة الشرح آية 6 — بُشرى بأن مع العسر يُسراً'},
    {"q": 'أكمل الآية: وما توفيقي إلا...', "options": ['بالصبر', 'بالله', 'بالإيمان', 'من عند الله'], "answer": 'بالله', "explain": 'سورة هود آية 88 — قالها شعيب عليه السلام'},
    {"q": 'أكمل الآية: ألا بذكر الله تطمئن...', "options": ['الأرواح', 'النفوس', 'العقول', 'القلوب'], "answer": 'القلوب', "explain": 'سورة الرعد آية 28 — من أعظم آيات القرآن'},
    {"q": 'أكمل الآية: فإذا عزمت فتوكل على...', "options": ['الله', 'ربك وحده', 'نفسك', 'العقل والحكمة'], "answer": 'الله', "explain": 'سورة آل عمران آية 159'},
    {"q": 'ما معنى كلمة الفلاح في القرآن؟', "options": ['الرزق الوفير', 'النجاح والفوز', 'الصبر والتحمل', 'العبادة الدائمة'], "answer": 'النجاح والفوز', "explain": 'الفلاح يعني النجاح والفوز بالجنة والنجاة من النار'},
    {"q": 'ما معنى كلمة القنوت في القرآن؟', "options": ['الدعاء فقط', 'الصمت التام', 'الصيام', 'الطاعة والخشوع'], "answer": 'الطاعة والخشوع', "explain": 'القنوت يعني الطاعة الكاملة والخشوع لله'},
    {"q": 'كم عدد تكبيرات صلاة الجنازة؟', "options": ['3', '4', '5', '6'], "answer": '4', "explain": 'صلاة الجنازة أربع تكبيرات بلا ركوع ولا سجود'},
    {"q": 'ما حكم صيام يوم العيدين؟', "options": ['حرام', 'مكروه', 'جائز', 'مستحب'], "answer": 'حرام', "explain": 'نهى النبي ﷺ عن صيام يوم الفطر ويوم الأضحى'},
    {"q": 'ما نصاب زكاة الذهب بالجرامات تقريباً؟', "options": ['50 جرام', '70 جرام', '100 جرام', '85 جرام'], "answer": '85 جرام', "explain": 'نصاب زكاة الذهب 85 جراماً إذا حال عليها الحول'},
    {"q": 'كم مرة تُطاف الكعبة في الطواف؟', "options": ['5 أشواط', '6 أشواط', '7 أشواط', '8 أشواط'], "answer": '7 أشواط', "explain": 'الطواف حول الكعبة سبعة أشواط'},
    {"q": 'ما الذي ينقض الوضوء باتفاق الفقهاء؟', "options": ['الضحك', 'الأكل', 'خروج الريح', 'النوم جالساً'], "answer": 'خروج الريح', "explain": 'خروج شيء من السبيلين ينقض الوضوء باتفاق'},
    {"q": 'من هو أول خليفة في الإسلام؟', "options": ['عمر بن الخطاب', 'أبو بكر الصديق', 'علي بن أبي طالب', 'عثمان بن عفان'], "answer": 'أبو بكر الصديق', "explain": 'أبو بكر الصديق أول خليفة للمسلمين بعد وفاة النبي ﷺ'},
    {"q": 'من هو الخليفة الذي فتح بيت المقدس؟', "options": ['أبو بكر', 'عمر بن الخطاب', 'علي', 'عثمان'], "answer": 'عمر بن الخطاب', "explain": 'فتح عمر رضي الله عنه بيت المقدس عام 637م'},
    {"q": 'في أي عام فُتحت مكة المكرمة هجرياً؟', "options": ['6هـ', '8هـ', '7هـ', '9هـ'], "answer": '8هـ', "explain": 'فُتحت مكة في رمضان السنة الثامنة للهجرة'},
    {"q": 'من هو أول شهيد في الإسلام؟', "options": ['سمية بنت خياط', 'ياسر بن عامر', 'عمار بن ياسر', 'بلال بن رباح'], "answer": 'سمية بنت خياط', "explain": 'سمية بنت خياط أم عمار — أول شهيدة في الإسلام'},
    {"q": 'من هو باني الكعبة المشرفة؟', "options": ['نوح وإدريس', 'محمد ﷺ وصحابته', 'إبراهيم وإسماعيل', 'آدم وحده'], "answer": 'إبراهيم وإسماعيل', "explain": 'قال تعالى: وإذ يرفع إبراهيم القواعد من البيت وإسماعيل'},
    {"q": 'ما لقب النبي إبراهيم عليه السلام؟', "options": ['خليل الله', 'كليم الله', 'نبي الله', 'روح الله'], "answer": 'خليل الله', "explain": 'قال تعالى: واتخذ الله إبراهيم خليلاً'},
    {"q": 'ما لقب النبي موسى عليه السلام؟', "options": ['خليل الله', 'كليم الله', 'روح الله', 'نجي الله'], "answer": 'كليم الله', "explain": 'كلّم الله موسى تكليماً مباشراً فلُقّب بكليم الله'},
    {"q": 'ما لقب النبي عيسى عليه السلام في القرآن؟', "options": ['روح الله وكلمته', 'كليم الله', 'صفي الله', 'خليل الله'], "answer": 'روح الله وكلمته', "explain": 'قال تعالى: إنما المسيح عيسى ابن مريم رسول الله وكلمته وروح منه'},
    {"q": 'من هو النبي الملقب بأبي البشر؟', "options": ['إبراهيم', 'آدم', 'نوح', 'محمد ﷺ'], "answer": 'آدم', "explain": 'آدم عليه السلام أبو البشرية كلها'},
    {"q": 'كم جزءاً في القرآن الكريم؟', "options": ['25', '30', '28', '32'], "answer": '30', "explain": 'القرآن الكريم مقسّم إلى 30 جزءاً'},
    {"q": 'ما هي أقصر سورة في القرآن؟', "options": ['الفاتحة', 'الكوثر', 'الفلق', 'الناس'], "answer": 'الكوثر', "explain": 'سورة الكوثر أقصر سورة في القرآن بثلاث آيات فقط'},
    {"q": 'كم مرة ذُكر اسم محمد ﷺ في القرآن؟', "options": ['4', '3', '2', '5'], "answer": '4', "explain": 'ذُكر اسم محمد ﷺ أربع مرات في القرآن الكريم'},
    {"q": 'في أي يوم خُلق آدم عليه السلام؟', "options": ['الاثنين', 'الجمعة', 'الأربعاء', 'السبت'], "answer": 'الجمعة', "explain": 'قال النبي ﷺ: خُلق آدم يوم الجمعة'},
    {"q": 'كم باباً للجنة؟', "options": ['9', '7', '6', '8'], "answer": '8', "explain": 'للجنة ثمانية أبواب منها باب الريّان لأهل الصيام'},
    {"q": 'كم باباً للنار؟', "options": ['8', '6', '5', '7'], "answer": '7', "explain": 'قال تعالى: لها سبعة أبواب لكل باب منهم جزء مقسوم'},
    {"q": 'ما هو الذكر الأثقل في الميزان؟', "options": ['لا إله إلا الله', 'الله أكبر كبيراً', 'الحمد لله رب العالمين', 'سبحان الله وبحمده سبحان الله العظيم'], "answer": 'سبحان الله وبحمده سبحان الله العظيم', "explain": 'قال النبي ﷺ: كلمتان خفيفتان على اللسان ثقيلتان في الميزان'},
    {"q": 'من هو الملك الموكّل بالوحي؟', "options": ['ميكائيل', 'إسرافيل', 'عزرائيل', 'جبريل'], "answer": 'جبريل', "explain": 'جبريل عليه السلام هو أمين الوحي'},
    {"q": 'ما هي السورة التي تُقرأ على المحتضر؟', "options": ['يس', 'البقرة', 'الرحمن', 'الفاتحة'], "answer": 'يس', "explain": 'قال النبي ﷺ: اقرأوا على موتاكم يس'},
    {"q": 'في أي سنة وقعت غزوة بدر الكبرى؟', "options": ['3هـ', '1هـ', '2هـ', '4هـ'], "answer": '2هـ', "explain": 'غزوة بدر كانت في 17 رمضان السنة الثانية للهجرة'},
    {"q": 'كم كان عدد المسلمين في غزوة بدر تقريباً؟', "options": ['100', '313', '213', '500'], "answer": '313', "explain": 'كان المسلمون 313 رجلاً في مقابل نحو 1000 من المشركين'},
    {"q": 'من هو الصحابي الذي سمّاه النبي ﷺ حب الله ورسوله؟', "options": ['عمر', 'علي بن أبي طالب', 'أبو بكر', 'أسامة بن زيد'], "answer": 'أسامة بن زيد', "explain": 'قال النبي ﷺ لأسامة: إنك لحبي وابن حبي'},
    {"q": 'ما اسم أول ولد وُلد للمهاجرين في المدينة؟', "options": ['عبدالله بن الزبير', 'عبدالله بن عمر', 'محمد بن علي', 'سالم بن أبي حذيفة'], "answer": 'عبدالله بن الزبير', "explain": 'كان المشركون يقولون لن يولد لهم فجاء عبدالله بن الزبير'},
    {"q": 'كم دامت دعوة النبي ﷺ في مكة قبل الهجرة؟', "options": ['13 سنة', '10 سنوات', '8 سنوات', '15 سنة'], "answer": '13 سنة', "explain": 'مكث النبي ﷺ في مكة يدعو 13 سنة قبل الهجرة'},
    {"q": 'ما هي السورة التي تُسمى قلب القرآن؟', "options": ['الفاتحة', 'البقرة', 'الكهف', 'يس'], "answer": 'يس', "explain": 'قال النبي ﷺ: إن لكل شيء قلباً وقلب القرآن يس'},
    {"q": 'كم آية في سورة الفاتحة؟', "options": ['5', '6', '8', '7'], "answer": '7', "explain": 'سورة الفاتحة سبع آيات وهي السبع المثاني'},
    {"q": 'ما هي السورة التي من قرأها حُفظ من الدجال؟', "options": ['يس', 'الكهف', 'البقرة', 'الإخلاص'], "answer": 'الكهف', "explain": 'قال النبي ﷺ: من قرأ عشر آيات من سورة الكهف عُصم من الدجال'},
    {"q": 'كم حرفاً في البسملة؟', "options": ['17', '20', '18', '19'], "answer": '19', "explain": 'بسم الله الرحمن الرحيم تتكون من 19 حرفاً'},
    {"q": 'ما هو آخر ما نزل من القرآن كاملاً من السور؟', "options": ['المائدة', 'النصر', 'التوبة', 'البقرة'], "answer": 'النصر', "explain": 'سورة النصر آخر ما نزل كاملاً وفيها إشارة لوفاة النبي ﷺ'},
    {"q": 'أكمل الآية: وقل رب زدني...', "options": ['رزقاً', 'صبراً', 'هدىً', 'علماً'], "answer": 'علماً', "explain": 'سورة طه آية 114 — الدعاء بالعلم'},
    {"q": 'أكمل الآية: حسبنا الله ونعم...', "options": ['الرحيم', 'المولى', 'الوكيل', 'الحفيظ'], "answer": 'الوكيل', "explain": 'سورة آل عمران — قالها إبراهيم حين أُلقي في النار وقالها النبي ﷺ'},
    {"q": 'معنى كلمة التوكل في القرآن؟', "options": ['التسليم للقضاء فقط', 'ترك العمل', 'الاعتماد على الله مع الأخذ بالأسباب', 'الصبر على البلاء'], "answer": 'الاعتماد على الله مع الأخذ بالأسباب', "explain": 'التوكل هو صدق الاعتماد على الله مع بذل الأسباب'},
    {"q": 'معنى كلمة الصراط في القرآن؟', "options": ['الجسر', 'الميزان', 'السبيل الضيق', 'الطريق'], "answer": 'الطريق', "explain": 'الصراط يعني الطريق الواضح المستقيم'},
    {"q": 'أكمل الحديث: خير الناس أنفعهم...', "options": ['للناس', 'لأهلهم', 'لدينهم', 'لربهم'], "answer": 'للناس', "explain": 'قال النبي ﷺ: خير الناس أنفعهم للناس — رواه الطبراني'},
    {"q": 'أكمل الحديث: الدنيا سجن المؤمن وجنة...', "options": ['العاصي', 'المنافق', 'الكافر', 'الجاحد'], "answer": 'الكافر', "explain": 'رواه مسلم — يعني المؤمن يصبر في الدنيا وينعم في الآخرة'},
    {"q": 'أكمل الحديث: من صام رمضان إيماناً واحتساباً غُفر له...', "options": ['ذنبه كله', 'ذنوب يوم وليلة', 'كبائر ذنبه', 'ما تقدم من ذنبه'], "answer": 'ما تقدم من ذنبه', "explain": 'متفق عليه — فضل صيام رمضان'},
    {"q": 'أكمل الحديث: تبسّمك في وجه أخيك...', "options": ['من الإحسان', 'من الإيمان', 'صدقة', 'نور'], "answer": 'صدقة', "explain": 'رواه الترمذي — حثّ على إظهار البشاشة'},
    {"q": 'أكمل الحديث: كل ابن آدم خطّاء وخير الخطّائين...', "options": ['من استغفر', 'من تاب', 'التوّابون', 'الصابرون'], "answer": 'التوّابون', "explain": 'رواه الترمذي وابن ماجه — حثّ على التوبة'},
    {"q": 'ما شروط قبول العبادة؟', "options": ['الإخلاص لله والمتابعة للنبي ﷺ', 'المتابعة فقط', 'النية والخشوع', 'الإخلاص فقط'], "answer": 'الإخلاص لله والمتابعة للنبي ﷺ', "explain": 'لا تُقبل العبادة إلا بشرطين: الإخلاص والمتابعة'},
    {"q": 'ما حكم صلاة الجمعة؟', "options": ['فرض عين على الرجال', 'سنة مؤكدة', 'فرض كفاية', 'مستحبة'], "answer": 'فرض عين على الرجال', "explain": 'صلاة الجمعة فرض عين على كل مسلم بالغ حر مقيم'},
    {"q": 'ما هي أركان الصلاة؟', "options": ['النية والتكبير فقط', 'القيام والركوع والسجود فقط', 'خمسة أركان فقط', 'النية والتكبير والقراءة والركوع والسجود والتشهد والتسليم'], "answer": 'النية والتكبير والقراءة والركوع والسجود والتشهد والتسليم', "explain": 'أركان الصلاة سبعة وبدونها لا تصح'},
    {"q": 'ما الفرق بين الركن والواجب في الصلاة؟', "options": ['الركن يُقضى والواجب لا', 'لا فرق', 'الواجب أهم من الركن', 'ترك الركن يُبطل الصلاة وترك الواجب يُوجب سجود السهو'], "answer": 'ترك الركن يُبطل الصلاة وترك الواجب يُوجب سجود السهو', "explain": 'الركن لا تصح الصلاة بدونه والواجب يُجبر بسجود السهو'},
    {"q": 'ما هي النجاسة التي لا تطهر بالغسل؟', "options": ['الكلب في الملاقاة', 'البول', 'الدم', 'المني'], "answer": 'الكلب في الملاقاة', "explain": 'يُغسل الإناء من ولوغ الكلب سبعاً إحداهن بالتراب'},
    {"q": 'من هو المعروف بـ ذي القرنين في التاريخ الإسلامي؟', "options": ['الإسكندر المقدوني', 'رجل صالح ذكره القرآن', 'نبي من الأنبياء', 'كورش الكبير'], "answer": 'رجل صالح ذكره القرآن', "explain": 'ذو القرنين مذكور في سورة الكهف وهو رجل صالح ملّكه الله في الأرض'},
    {"q": 'ما هي أول دولة إسلامية تعترف بالإسلام رسمياً؟', "options": ['فارس', 'الروم', 'الحبشة', 'اليمن'], "answer": 'الحبشة', "explain": 'آوى النجاشي ملك الحبشة المسلمين وعدل بينهم واعترف بالإسلام'},
    {"q": 'من أول من هاجر إلى الحبشة؟', "options": ['عثمان بن عفان', 'جعفر بن أبي طالب', 'الزبير بن العوام', 'عبدالرحمن بن عوف'], "answer": 'عثمان بن عفان', "explain": 'هاجر عثمان وزوجته رقية بنت النبي ﷺ في أول هجرة للحبشة'},
    {"q": 'ما اسم قائد جيش المسلمين في معركة اليرموك؟', "options": ['سعد بن أبي وقاص', 'عمرو بن العاص', 'خالد بن الوليد', 'أبو عبيدة بن الجراح'], "answer": 'خالد بن الوليد', "explain": 'قاد خالد بن الوليد المسلمين في معركة اليرموك الفاصلة'},
    {"q": 'كم سنة كان يوسف عليه السلام في السجن؟', "options": ['3 سنوات', '10 سنوات', '5 سنوات', '7 سنوات'], "answer": '7 سنوات', "explain": 'قيل إن يوسف مكث في السجن سبع سنوات بعد إغواء امرأة العزيز'},
    {"q": 'ما هو المعجزة الكبرى التي أُعطيها موسى عليه السلام؟', "options": ['إحياء الموتى', 'شفاء الأكمه', 'العصا التي تنقلب حية', 'الكلام مع الله مباشرة'], "answer": 'العصا التي تنقلب حية', "explain": 'من أعظم معجزات موسى العصا التي تنقلب ثعباناً وتلقف سحر السحرة'},
    {"q": 'ما هو الجبل الذي كلّم الله عليه موسى؟', "options": ['جبل الطور', 'جبل حراء', 'جبل عرفات', 'جبل أُحد'], "answer": 'جبل الطور', "explain": 'قال تعالى: وناديناه من جانب الطور الأيمن — على جبل الطور'},
    {"q": 'من هو النبي الذي أُوتي الزبور؟', "options": ['إبراهيم', 'موسى', 'سليمان', 'داود'], "answer": 'داود', "explain": 'قال تعالى: وآتينا داود زبوراً'},
    {"q": 'كم نبياً ذُكر في سورة الأنبياء؟', "options": ['16', '14', '18', '10'], "answer": '16', "explain": 'ذُكر في سورة الأنبياء ستة عشر نبياً من الأنبياء الكرام'},
    {"q": 'ما هو الدعاء المستجاب بين الأذان والإقامة؟', "options": ['الدعاء في هذا الوقت لا يُرد', 'اللهم رب هذه الدعوة التامة', 'لا إله إلا الله وحده', 'ربنا لك الحمد'], "answer": 'الدعاء في هذا الوقت لا يُرد', "explain": 'قال النبي ﷺ: الدعاء لا يُرد بين الأذان والإقامة'},
    {"q": 'ما هي ليلة القدر؟', "options": ['ليلة 27 رمضان فقط', 'إحدى ليالي العشر الأخيرة من رمضان', 'أول ليلة رمضان', 'ليلة النصف من شعبان'], "answer": 'إحدى ليالي العشر الأخيرة من رمضان', "explain": 'قال النبي ﷺ: التمسوا ليلة القدر في العشر الأواخر من رمضان'},
    {"q": 'ما هو أفضل الذكر؟', "options": ['الحمد لله', 'لا إله إلا الله', 'سبحان الله', 'الله أكبر'], "answer": 'لا إله إلا الله', "explain": 'قال النبي ﷺ: أفضل الذكر لا إله إلا الله'},
    {"q": 'كم عدد الصلوات المفروضة في اليوم؟', "options": ['6', '4', '3', '5'], "answer": '5', "explain": 'فُرضت خمس صلوات ليلة المعراج وهي الفريضة اليومية'},
    {"q": 'ما هو الوضوء الكامل كم مرة لكل عضو؟', "options": ['ثلاث مرات', 'مرة واحدة', 'مرتان', 'حسب العضو'], "answer": 'ثلاث مرات', "explain": 'السنة غسل كل عضو ثلاث مرات والواجب مرة واحدة'},
    {"q": 'ما هو اسم صلاة الاستسقاء؟', "options": ['صلاة طلب المطر', 'صلاة الحاجة', 'صلاة الاستخارة', 'صلاة التهجد'], "answer": 'صلاة طلب المطر', "explain": 'صلاة الاستسقاء صلاة مشروعة لطلب المطر من الله'},
    {"q": 'ما هو الفرق بين النبي والرسول؟', "options": ['لا فرق بينهما', 'الرسول بشر فقط والنبي قد يكون ملكاً', 'الرسول أُوحي إليه بشريعة جديدة والنبي يتبع شريعة من قبله', 'النبي أفضل من الرسول'], "answer": 'الرسول أُوحي إليه بشريعة جديدة والنبي يتبع شريعة من قبله', "explain": 'الرسول أُرسل بشريعة جديدة وكتاب، والنبي يُبلّغ شريعة من قبله'},
]


def get_duaa_of_day() -> dict:
    """ارجع دعاء اليوم بناءً على رقم اليوم في السنة"""
    day_num = _dt.datetime.now(AMMAN_TZ).timetuple().tm_yday
    return DAILY_DUAA[day_num % len(DAILY_DUAA)]

DAILY_TOPICS = [
    "الصبر", "الصدق", "الأمانة", "الدعاء", "التوبة",
    "الصلاة", "الزكاة", "الرحمة", "الأخلاق", "العلم",
    "الجنة", "الجهاد", "الذكر", "الشكر", "البر",
]

MOOD_TOPICS = {
    "happy":   ["الشكر", "الحمد", "النعمة"],
    "tired":   ["الصبر", "الراحة", "الرحمة"],
    "angry":   ["الغضب", "الحلم", "العفو"],
}

async def send_mood_hadith(user_id: int, mood: str, context) -> str:
    topics = MOOD_TOPICS.get(mood, ["الصبر"])
    topic = _random.choice(topics)
    try:
        results = await search_dorar_api(topic)
        if results:
            h = _random.choice(results[:10])
            return (
                f"📖 *حديث على قدك*\n"
                f"━━━━━━━━━━━━━━━\n\n"
                f"📌 {h['text']}\n\n"
                f"👤 *الراوي:* {h.get('rawi') or 'غير محدد'}\n"
                f"📚 *المصدر:* {h.get('source') or 'غير محدد'}\n"
                f"⚖️ *الدرجة:* {h.get('grade') or 'غير محدد'}"
            )
    except:
        pass
    return "⚠️ ما قدرت أجيب حديثاً الآن، حاول مرة ثانية."

# ==================== صديقي الروحي (Tier 3) ====================
SPIRITUAL_KEYWORDS = {
    "الصبر": "الصبر والشدة",
    "الحزن": "الصبر والشدة",
    "الضيق": "الصبر والشدة",
    "الدعاء": "الدعاء والتضرع",
    "الرزق": "الرزق والتوكل",
    "الأسرة": "الأسرة والوالدين",
    "الوالدين": "الأسرة والوالدين",
    "التوبة": "التوبة والاستغفار",
    "الاستغفار": "التوبة والاستغفار",
    "الصلاة": "الصلاة",
    "الأخلاق": "الأخلاق والمعاملة",
    "العلم": "العلم والتعلم",
    "الجنة": "الآخرة والجنة",
    "الموت": "الآخرة والجنة",
}

MOOD_MESSAGES = {
    "الصبر والشدة": "يبدو إنك تمر بوقت صعب 🤍 هذه الأحاديث قد تعينك",
    "الدعاء والتضرع": "يظهر إنك تبحث عن القرب من الله 🤲 هذه الأحاديث لك",
    "الرزق والتوكل": "في أمور الرزق توكّل على الله 🌿 هذه الأحاديث تذكّرك",
    "الأسرة والوالدين": "العائلة تهمك كثيراً 🏠 هذه الأحاديث تقربك منهم",
    "التوبة والاستغفار": "باب التوبة مفتوح دائماً 🌸 هذه الأحاديث تبشّرك",
    "الصلاة": "الصلاة عماد الدين 🕌 هذه الأحاديث تذكّرك بفضلها",
    "الأخلاق والمعاملة": "الأخلاق الحسنة من أثقل الموازين ⚖️ هذه الأحاديث لك",
    "العلم والتعلم": "طلب العلم عبادة 📖 هذه الأحاديث تشجّعك",
    "الآخرة والجنة": "ذكر الآخرة يهوّن الدنيا 🌟 هذه الأحاديث تذكّرك",
}

async def cancel_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id in ADMIN_IDS and context.user_data.get("broadcast"):
        context.user_data.pop("broadcast", None)
        context.user_data.pop("broadcast_type", None)
        await update.message.reply_text("✅ تم إلغاء الإشعار.", reply_markup=admin_main_keyboard())
        return True
    return False

# ==================== معالجات الدعم (التبرع) ====================
async def donate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إظهار خيارات التبرع"""
    await update.message.reply_text(
        "💰 دعم بوت راوِي\n\n"
        "يمكنك دعم البوت عن طريق التبرع بالنجوم (Telegram Stars).\n"
        "اختر المبلغ الذي تريد التبرع به:",
        reply_markup=donation_keyboard()
    )

async def handle_donation_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة اختيار المبلغ وإرسال الفاتورة"""
    text = update.message.text
    amount_map = {
        "⭐ 1 نجمة": 1,
        "⭐ 5 نجوم": 5,
        "⭐ 10 نجوم": 10,
        "⭐ 25 نجمة": 25,
        "⭐ 50 نجمة": 50,
        "⭐ 100 نجمة": 100,
    }
    if text not in amount_map:
        return False

    amount = amount_map[text]
    title = "دعم بوت راوِي"
    description = f"تبرع بمبلغ {amount} نجمة لدعم استمرارية البوت وتطويره. شكراً لك!"
    payload = f"donation_{amount}"
    currency = "XTR"
    # ✅ التصحيح: استخدام LabeledPrice بدلاً من tuple
    prices = [LabeledPrice(f"{amount} نجمة", amount)]

    await context.bot.send_invoice(
        chat_id=update.effective_chat.id,
        title=title,
        description=description,
        payload=payload,
        provider_token="",
        currency=currency,
        prices=prices
    )
    return True

async def precheckout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """التحقق من عملية الدفع (يتم قبولها دائماً)"""
    query = update.pre_checkout_query
    await query.answer(ok=True)

def get_tier(user_id: int) -> int:
    """مستوى المستخدم — الكل مجاني"""
    return 0

def get_tier_label(tier: int) -> str:
    return "👤 مستخدم"

def get_tier_features(tier: int) -> str:
    return "✅ جميع الميزات متاحة للجميع"

def has_favorites(user_id: int) -> bool:
    """هل للمستخدم مفضلة — متاح للجميع"""
    return True

def has_topics(user_id: int) -> bool:
    """بحث بالموضوع — متاح للجميع"""
    return True

def activate_premium(user_id: int, amount: int):
    """تسجيل الدعم — بدون tier"""
    pass

def get_premium_stars(user_id: int) -> int:
    """إجمالي النجوم المتبرع بها"""
    try:
        with sqlite3.connect("bot.db") as conn:
            row = conn.execute(
                "SELECT SUM(amount) FROM donations WHERE user_id=?", (user_id,)
            ).fetchone()
        return row[0] or 0 if row else 0
    except Exception:
        return 0

TIER1_STARS = 1
TIER2_STARS = 5
TIER3_STARS = 25

async def successful_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة الدفع الناجح مع حفظ charge_id"""
    payment = update.message.successful_payment
    amount = payment.total_amount
    charge_id = payment.telegram_payment_charge_id
    user_id = update.effective_user.id
    payload = payment.invoice_payload

    # لو كان دفع أسئلة إضافية
    if payload.startswith("qa_extra_"):
        log_donation(user_id, amount, charge_id)
        add_qa_extra(user_id, QA_EXTRA_BONUS)
        _, remaining, _ = can_ask_question(user_id)
        # إشعار الأدمن
        username = update.effective_user.username or "لا يوجد"
        full_name = update.effective_user.full_name
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(
                    admin_id,
                    f"❓ *شراء أسئلة دينية*\n"
                    f"👤 {full_name} (@{username}) — ID: {user_id}\n"
                    f"⭐ {amount} نجمة مقابل {QA_EXTRA_BONUS} أسئلة إضافية",
                    parse_mode="Markdown"
                )
            except Exception:
                pass
        await update.message.reply_text(
            f"✅ *شكراً! تم إضافة {QA_EXTRA_BONUS} أسئلة*\n\n"
            f"📊 رصيدك الآن: *{remaining} سؤال* متاح اليوم\n\n"
            "اضغط ❓ سؤال ديني للبدء 👇",
            parse_mode="Markdown"
        )
        return
    username = update.effective_user.username or "لا يوجد"
    full_name = update.effective_user.full_name

    # تسجيل التبرع في قاعدة البيانات مع charge_id
    log_donation(user_id, amount, charge_id)

    # إشعار المشرفين
    admin_msg = (
        f"💰 *تبرع جديد*\n"
        f"👤 المستخدم: {full_name} (@{username}) (ID: {user_id})\n"
        f"⭐ المبلغ: {amount} نجمة\n"
        f"🆔 معرف المعاملة: {charge_id}\n"
        f"📅 التاريخ: {_dt.datetime.now(AMMAN_TZ).strftime('%Y-%m-%d %H:%M:%S')}"
    )
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(admin_id, admin_msg)
        except:
            pass

    # حدّث بيانات الداعم
    activate_premium(user_id, amount)
    total_stars = get_premium_stars(user_id)
    tier = get_tier(user_id)
    tier_label = get_tier_label(tier)
    features = get_tier_features(tier)

    new_features = ""
    if tier == 1 and total_stars - amount < TIER1_STARS:
        new_features = "\n🎉 *تم فتح مزايا جديدة:*\n✅ 🔎 بحث بالموضوع\n"
    elif tier == 2 and total_stars - amount < TIER2_STARS:
        new_features = "\n🎉 *تم فتح مزايا جديدة:*\n✅ 💾 المفضلة\n"
    elif tier == 3 and total_stars - amount < TIER3_STARS:
        new_features = "\n🎉 *تم فتح جميع المزايا:*\n✅ 🕐 تخصيص وقت الإشعار\n"

    await update.message.reply_text(
        f"✅ شكراً جزيلاً على دعمك!\n"
        f"تبرعت بـ {amount} نجمة | إجمالي: {total_stars} نجمة\n\n"
        f"{tier_label}\n"
        f"{new_features}\n"
        f"{features}\n"
        f"جزاك الله خيراً 🤍",
        parse_mode="Markdown"
    )

# ==================== أمر استرداد النجوم ====================
async def refund_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """استرداد النجوم — قائمة بأزرار"""
    if update.effective_user.id not in ADMIN_IDS:
        return
    with sqlite3.connect("bot.db") as _c:
        donations = _c.execute(
            "SELECT d.user_id, u.full_name, d.amount, d.charge_id "
            "FROM donations d LEFT JOIN users u ON d.user_id=u.user_id "
            "ORDER BY d.date DESC LIMIT 20"
        ).fetchall()
    if not donations:
        await update.message.reply_text("لا توجد تبرعات مسجلة.")
        return
    msg = "💰 *التبرعات الأخيرة*\n━━━━━━━━━━━━━━━"
    rows = []
    dm = {}
    for uid, name, amount, charge_id in donations:
        key = f"{uid}_{charge_id[:15]}"
        dm[key] = {"uid": uid, "charge_id": charge_id, "amount": amount}
        msg += f"\n👤 {name or uid} — ⭐{amount}"
        rows.append([colored_btn(f"↩️ {name or str(uid)[:10]} ({amount}⭐)", callback_data=f"do_refund_{key}")])
    context.user_data["donations_map"] = dm
    await update.message.reply_text(msg, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(rows) if rows else None)

# ==================== المعالجات ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    register_user(user.id, user.username or "", user.full_name)

    # deep links
    if context.args:
        arg = context.args[0]
        if arg.startswith("fc_"):
            # تحدي صديق — الخصم يفتح الرابط
            challenge_id = arg[3:]
            ch = get_friend_challenge(challenge_id)
            if not ch:
                await update.message.reply_text("⚠️ هذا التحدي غير موجود أو انتهت صلاحيته.")
                return
            if ch["status"] == "finished":
                await update.message.reply_text("⚠️ هذا التحدي انتهى بالفعل.")
                return
            if ch["creator_id"] == user.id:
                await update.message.reply_text("😄 ما تقدر تتحدى نفسك!")
                return
            if ch["opponent_score"] >= 0:
                await update.message.reply_text("⚠️ التحدي مشغول بلاعب آخر!")
                return
            # ابدأ التحدي للخصم
            context.user_data["fc_id"] = challenge_id
            context.user_data["fc_role"] = "opponent"
            context.user_data["fc_index"] = 0
            context.user_data["fc_score"] = 0
            context.user_data["fc_questions"] = ch["questions"]
            try:
                await context.bot.send_message(
                    ch["creator_id"],
                    f"🎯 *{user.full_name}* قبل تحديك! بدأ الاختبار الآن 🔥",
                    parse_mode="Markdown"
                )
            except Exception:
                pass
            await update.message.reply_text(
                f"⚔️ *تحدي من {ch['creator_name']}*\n"
                "━━━━━━━━━━━━━━━\n\n"
                "📋 10 أسئلة إسلامية\n"
                "⭐ كل إجابة صحيحة = نقطة\n\n"
                "استعد... السؤال الأول 👇",
                parse_mode="Markdown"
            )
            await _send_fc_question(update, context)
            return

        elif arg == "challenge":
            challenge = get_today_challenge()
            if not challenge:
                await cmd_challenge_now(update, context)
            else:
                context.user_data["in_challenge"] = True
                context.user_data["challenge_answer"] = challenge["answer"]
                context.user_data["challenge_full"] = challenge["full"]
                await update.message.reply_text(
                    "🧩 تحدي اليوم\n━━━━━━━━━━━━━━━\n\n"
                    f"📌 {challenge['text']}\n\nأرسل الكلمة الناقصة 👇"
                )
            return

    is_new = register_user(user.id, user.username or "", user.full_name)
    is_admin = user.id in ADMIN_IDS
    users, _, hadiths, _ = get_global_stats()
    conn2 = sqlite3.connect("bot.db")
    cur2 = conn2.cursor()
    cur2.execute("SELECT daily_hadith, adhkar_sub FROM users WHERE user_id=?", (user.id,))
    sub_row = cur2.fetchone()
    conn2.close()
    _daily = sub_row[0] if sub_row else 1
    _adhkar = sub_row[1] if sub_row else 0

    # إشعار الأدمن بكل دخول
    _uname = f"@{user.username}" if user.username else "بدون يوزر"
    _label = "🆕 مستخدم جديد!" if is_new else "👋 عودة مستخدم"
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(
                admin_id,
                f"{_label}\n\n"
                f"الاسم: {user.full_name}\n"
                f"اليوزر: {_uname}\n"
                f"ID: `{user.id}`",
                parse_mode="Markdown"
            )
        except:
            pass

    if is_new:
        # رسالة ترحيب تفاعلية للمستخدم الجديد
        tour_kb = None  # لا يوجد tour في الرسالة الجديدة
        await update.message.reply_text(
            f"🌙 أهلاً {user.first_name}، أنا *راوِي*\n"
            "━━━━━━━━━━━━━━━\n\n"
            "🔍 *باحث الحديث*\n"
            "اضغط الزر ← اكتب الحديث أو اسم الراوي\n\n"
            "📖 *باحث القرآن*\n"
            "اضغط الزر ← اكتب كلمات من الآية أو السورة:الآية\n\n"
            "وفيه كمان:\n"
            "🌟 قصة يومية من سير الأنبياء والصحابة\n"
            "🎯 اختبار إسلامي يومي\n"
            "📿 عداد تسبيح وختم القرآن\n"
            "❓ سؤال ديني بالذكاء الاصطناعي\n\n"
            "🤍 _إن نفعك البوت فادعُ للمطور بظهر الغيب_",
            parse_mode="Markdown"
        )
        await update.message.reply_text(
            "اختر من القائمة 👇",
            reply_markup=main_kb(is_admin)
        )
    else:
        await update.message.reply_text(
            f"🌙 أهلاً بك {user.first_name}\n"
            "━━━━━━━━━━━━━━━\n\n"
            "🔍 *باحث الحديث* — اضغط الزر واكتب\n"
            "📖 *باحث القرآن* — اضغط الزر واكتب\n\n"
            "🤍 _إن نفعك البوت فادعُ للمطور بظهر الغيب_",
            parse_mode="Markdown",
            reply_markup=main_kb(is_admin)
        )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"🆘 مساعدة بوت {BOT_NAME}:\n\n"
        "• أرسل أي حديث وسأبحث عنه.\n"
        "• أرسل اسم راوي (مثل 'أبو هريرة') لترى أحاديثه.\n"
        "• الأزرار:\n"
        "/random - حديث عشوائي\n"
        "/donate - دعم البوت"
    )

async def version_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض معلومات الإصدار والمزايا الجديدة"""
    msg = (
        "╔══════════════════╗\n"
        "   🕌 بوت راوِي\n"
        "   الإصدار v5.0\n"
        "╚══════════════════╝\n\n"
        "📅 مارس 2026\n\n\n"
        "🆕 *ما الجديد؟*\n\n"
        "  ⚔️  *تحدي الصديق*\n"
        "  تحدّ من تشاء في 10 أسئلة\n"
        "  واكتشف من الأذكى منكم!\n\n"
        "  ━━━━━━━\n\n"
        "  🎯  *اختبار أقوى من قبل*\n"
        "  120 سؤالاً في القرآن والسيرة\n"
        "  والفقه والصحابة الكرام\n\n"
        "  ━━━━━━━\n\n"
        "  🤲  *دعاء اليوم*\n"
        "  50 دعاءً نبوياً وقرآنياً\n"
        "  يتجدد معك كل يوم\n\n"
        "  ━━━━━━━\n\n"
        "  🌟  *قدوتي اليوم*\n"
        "  قصص الأنبياء والصحابة\n"
        "  16 قصة موثقة بالمصادر\n\n"
        "  ━━━━━━━\n\n"
        "  🤖  *شرح الأحاديث بالذكاء الاصطناعي*\n"
        "  فهم أعمق للأحاديث النبوية\n"
        "  مع الفوائد والدروس المستفادة\n\n\n"
        "✦ ✦ ✦\n\n"
        "       👨‍💻 @ssss_ssss_x\n"
        "  ضمّوني بين دعواتكم 💙"
    )
    
    await update.message.reply_text(msg, parse_mode="Markdown")



async def _quiz_timeout(context):
    """ينتهي وقت السؤال تلقائياً بعد 30 ثانية"""
    user_id = context.job.data["user_id"]
    chat_id = context.job.data["chat_id"]
    msg_id = context.job.data["msg_id"]
    q_data = context.job.data["q_data"]
    next_idx = context.job.data["next_idx"]
    total_q = context.job.data["total_q"]
    score = context.job.data["score"]
    questions = context.job.data["questions"]
    date = context.job.data["date"]

    # تحقق إذا المستخدم أجاب مسبقاً
    answered_idx = context.job.data.get("answered_idx")
    if answered_idx is not None:
        return  # أجاب، مش محتاج نعمل شيء

    # انتهى الوقت — أغلق الأزرار
    try:
        await context.bot.edit_message_reply_markup(
            chat_id=chat_id,
            message_id=msg_id,
            reply_markup=None
        )
    except Exception:
        pass

    # أرسل رسالة انتهاء الوقت
    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"⏰ *انتهى الوقت!*\n\n✅ الجواب الصحيح: *{q_data['answer']}*\n\n📖 {q_data['explain']}",
            parse_mode="Markdown"
        )
    except Exception:
        pass

    save_quiz_session(user_id, questions, next_idx, score, date)

    if next_idx >= total_q:
        stars = "⭐" * score + "☆" * (total_q - score)
        pct = round(score / total_q * 100)
        if pct == 100: comment = "ممتاز! أنت نجم! 🏆"
        elif pct >= 80: comment = "رائع جداً! 👏"
        elif pct >= 60: comment = "جيد! استمر 👍"
        elif pct >= 40: comment = "تحتاج مراجعة 📚"
        else: comment = "لا تستسلم، استمر في التعلم 💪"
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    f"🎯 *انتهى الاختبار!*\n"
                    "━━━━━━━━━━━━━━━\n\n"
                    f"نتيجتك: *{score}/{total_q}* {stars}\n"
                    f"💬 {comment}\n\n"
                    "تعال غداً لاختبار جديد 🌙"
                ),
                parse_mode="Markdown"
            )
        except Exception:
            pass
    else:
        # السؤال التالي بعد ثانية
        await asyncio.sleep(1)
        try:
            await _send_timed_question(context.bot, chat_id, user_id, context, questions, next_idx, score, date)
        except Exception:
            pass

async def _send_timed_question(bot, chat_id, user_id, context, questions, idx, score, date):
    """إرسال سؤال مع عداد 30 ثانية"""
    q = questions[idx]
    total_q = len(questions)
    opts = q["options"]
    num = idx + 1

    kb = InlineKeyboardMarkup([
        [colored_btn(opts[0], callback_data="quiz_0", style="primary"),
         colored_btn(opts[1], callback_data="quiz_1", style="primary")],
        [colored_btn(opts[2], callback_data="quiz_2", style="primary"),
         colored_btn(opts[3], callback_data="quiz_3", style="primary")],
    ])
    sent = await bot.send_message(
        chat_id=chat_id,
        text=(
            f"❓ *سؤال {num}/{total_q}*\n"
            "━━━━━━━━━━━━━━━\n\n"
            f"📌 {q['q']}\n\n"
            f"1️⃣ {opts[0]}\n"
            f"2️⃣ {opts[1]}\n"
            f"3️⃣ {opts[2]}\n"
            f"4️⃣ {opts[3]}\n\n"
            "⏳ *الوقت: 30 ثانية*"
        ),
        parse_mode="Markdown",
        reply_markup=kb
    )

    # حفظ بيانات السؤال الحالي
    context.user_data["quiz_index"] = idx
    context.user_data["quiz_score"] = score
    context.user_data["quiz_current_msg_id"] = sent.message_id
    context.user_data["quiz_answered"] = False

    # جدول مؤقت 30 ثانية
    job_name = f"quiz_timeout_{user_id}"
    # إلغاء أي مؤقت سابق
    current_jobs = context.job_queue.get_jobs_by_name(job_name)
    for j in current_jobs:
        j.schedule_removal()

    context.job_queue.run_once(
        _quiz_timeout,
        when=30,
        name=job_name,
        data={
            "user_id": user_id,
            "chat_id": chat_id,
            "msg_id": sent.message_id,
            "q_data": q,
            "next_idx": idx + 1,
            "total_q": total_q,
            "score": score,
            "questions": questions,
            "date": date,
            "answered_idx": None,
        }
    )

async def send_quiz_question(msg, context, q, num):
    """إرسال سؤال في الاختبار اليومي مع عداد 30 ثانية"""
    opts = q["options"]
    total_q = len(context.user_data.get("quiz_questions", [q]))
    kb = InlineKeyboardMarkup([
        [colored_btn(opts[0], callback_data="quiz_0", style="primary"),
         colored_btn(opts[1], callback_data="quiz_1", style="primary")],
        [colored_btn(opts[2], callback_data="quiz_2", style="primary"),
         colored_btn(opts[3], callback_data="quiz_3", style="primary")],
    ])
    sent = await msg.reply_text(
        f"❓ *سؤال {num}/{total_q}*\n"
        "━━━━━━━━━━━━━━━\n\n"
        f"📌 {q['q']}\n\n"
        f"1️⃣ {opts[0]}\n"
        f"2️⃣ {opts[1]}\n"
        f"3️⃣ {opts[2]}\n"
        f"4️⃣ {opts[3]}\n\n"
        "⏳ *الوقت: 30 ثانية*",
        parse_mode="Markdown",
        reply_markup=kb
    )

    user_id = msg.chat.id
    context.user_data["quiz_current_msg_id"] = sent.message_id
    context.user_data["quiz_answered"] = False

    # جدول مؤقت 30 ثانية
    job_name = f"quiz_timeout_{user_id}"
    current_jobs = context.job_queue.get_jobs_by_name(job_name)
    for j in current_jobs:
        j.schedule_removal()

    questions = context.user_data.get("quiz_questions", [])
    idx = num - 1
    date = context.user_data.get("quiz_date", "")
    score = context.user_data.get("quiz_score", 0)

    context.job_queue.run_once(
        _quiz_timeout,
        when=30,
        name=job_name,
        data={
            "user_id": user_id,
            "chat_id": msg.chat.id,
            "msg_id": sent.message_id,
            "q_data": q,
            "next_idx": idx + 1,
            "total_q": total_q,
            "score": score,
            "questions": questions,
            "date": date,
            "answered_idx": None,
        }
    )

async def random_suggestion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """اقتراح حديث عشوائي"""
    await random_hadith(update, context)

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("⛔ هذه الصفحة للمشرفين فقط.")
        return
    await update.message.reply_text("⚙️ لوحة تحكم المشرف", reply_markup=admin_main_keyboard())

async def handle_admin_actions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id not in ADMIN_IDS:
        return
    text = update.message.text

    if text in ("📢 إشعار للجميع", "📢 إشعار عام"):
        context.user_data["broadcast"] = True
        context.user_data["broadcast_type"] = "📝 نص"
        await update.message.reply_text("📢 أرسل الرسالة التي تريد نشرها لجميع المستخدمين:", reply_markup=cancel_broadcast_keyboard())

    elif text == "📢 إشعار متقدم":
        await update.message.reply_text(
            "📢 اختر نوع الوسائط للإشعار:",
            reply_markup=advanced_broadcast_keyboard()
        )
        return

    elif text in ["📝 نص", "🖼️ صورة", "🎤 صوت", "🎥 فيديو", "📁 ملف"]:
        context.user_data["broadcast_type"] = text
        context.user_data["broadcast"] = True
        msg = f"📢 أرسل {'الرسالة النصية' if text == '📝 نص' else 'الوسائط'} التي تريد نشرها لجميع المستخدمين:"
        await update.message.reply_text(msg, reply_markup=cancel_broadcast_keyboard())
        return

    elif text == "📊 إحصائيات":
        users, searches, hadiths, recent = get_global_stats()
        w = get_weekly_stats()
        # إحصائيات الأسئلة الدينية
        with sqlite3.connect("bot.db") as _qa_c:
            qa_today = _qa_c.execute(
                "SELECT COUNT(*), SUM(count) FROM qa_usage WHERE date=?",
                (_dt.datetime.now(AMMAN_TZ).strftime("%Y-%m-%d"),)
            ).fetchone()
            qa_paid = _qa_c.execute(
                "SELECT COUNT(*), SUM(extra_questions) FROM qa_usage WHERE extra_questions > 0"
            ).fetchone()
        today_str = _dt.datetime.now(AMMAN_TZ).strftime("%Y-%m-%d")
        with sqlite3.connect("bot.db") as _sc:
            new_today = _sc.execute("SELECT COUNT(*) FROM users WHERE DATE(joined_at)=?", (today_str,)).fetchone()[0] or 0
            try:
                qa_total = _sc.execute("SELECT COUNT(*) FROM qa_history").fetchone()[0] or 0
            except Exception:
                qa_total = 0
        msg = (
            f"📊 *إحصائيات البوت*\n━━━━━━━━━━━━━━━\n\n"
            f"👥 إجمالي المستخدمين: *{users}*\n"
            f"🆕 جدد اليوم: *{new_today}*\n"
            f"🔥 نشطين آخر 7 أيام: *{w.get('active', 0)}*\n"
            f"🔎 إجمالي البحوث: *{searches}*\n\n"
            f"❓ أسئلة اليوم: *{qa_today[1] or 0}*\n"
            f"❓ إجمالي الأسئلة: *{qa_total}*\n"
            f"⭐ مشترو أسئلة: *{qa_paid[0] or 0}*"
        )
        await update.message.reply_text(msg, parse_mode="Markdown")
        return

    elif text == "📅 إحصائيات الأسبوع":
        w = get_weekly_stats()
        # معدل الاحتفاظ (ميزة 10)
        conn_r = sqlite3.connect("bot.db")
        cur_r = conn_r.cursor()
        two_weeks = (_dt.datetime.now(AMMAN_TZ) - timedelta(days=14)).strftime("%Y-%m-%d %H:%M:%S")
        one_week = (_dt.datetime.now(AMMAN_TZ) - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
        cur_r.execute("SELECT COUNT(DISTINCT user_id) FROM searches WHERE date BETWEEN ? AND ?", (two_weeks, one_week))
        old_users = cur_r.fetchone()[0] or 1
        cur_r.execute("SELECT COUNT(DISTINCT user_id) FROM searches WHERE date >= ?", (one_week,))
        returned = cur_r.fetchone()[0]
        conn_r.close()
        retention = round((returned / old_users) * 100) if old_users else 0
        # أكثر الأحاديث مشاركةً (ميزة 8)
        msg = (
            f"📅 *إحصائيات آخر 7 أيام*\n\n"
            f"🆕 مستخدمين جدد: {w['new_users']}\n"
            f"🔥 مستخدمين نشطين: {w['active']}\n"
            f"🔍 إجمالي البحوث: {w['searches']}\n"
            f"⭐ نجوم مستلمة: {w['donations']}\n"
            f"🔄 معدل الاحتفاظ: {retention}%\n\n"
            f"*أكثر المواضيع بحثاً:*\n"
        )
        for word, count in w['top']:
            msg += f"  • {word}: {count} مرة\n"

        await update.message.reply_text(msg, parse_mode="Markdown")
        return

    elif text == "📈 نمو يومي":
        growth = get_daily_growth()
        msg = "📈 *نمو المستخدمين - آخر 7 أيام*\n\n"
        for day, count in growth:
            bar = "█" * min(count, 20) if count > 0 else "—"
            msg += f"{day}: {bar} ({count})\n"
        await update.message.reply_text(msg, parse_mode="Markdown")
        return

    elif text == "⏰ أوقات النشاط":
        hours = get_peak_hours()
        msg = "⏰ *أكثر أوقات النشاط (آخر أسبوع)*\n\n"
        for hour, cnt in hours:
            msg += f"الساعة {hour:02d}:00 — {cnt} بحث\n"
        await update.message.reply_text(msg, parse_mode="Markdown")
        return

    elif text == "🏆 أنشط المستخدمين":
        top = get_top_searchers(10)
        msg = "🏆 *أكثر المستخدمين بحثاً*\n\n"
        for i, (name, uname, total) in enumerate(top, 1):
            u = f"@{uname}" if uname else "بدون يوزر"
            msg += f"{i}. {name or 'مجهول'} ({u}) — {total} بحث\n"
        await update.message.reply_text(msg, parse_mode="Markdown")
        return

    elif text == "🆕 مستخدمون جدد":
        recent = get_recent_users(10)
        msg = "🆕 *آخر 10 مستخدمين انضموا*\n\n"
        for name, uname, joined in recent:
            u = f"@{uname}" if uname else "بدون يوزر"
            msg += f"• {name or 'مجهول'} ({u}) — {joined[:10]}\n"
        await update.message.reply_text(msg, parse_mode="Markdown")
        return

    elif text == "📋 سجل الفواتير":
        conn = sqlite3.connect("bot.db")
        cur = conn.cursor()
        cur.execute("""
            SELECT d.user_id, u.full_name, u.username, d.amount, d.charge_id, d.date
            FROM donations d
            LEFT JOIN users u ON d.user_id = u.user_id
            ORDER BY d.date DESC LIMIT 10
        """)
        rows = cur.fetchall()
        conn.close()
        if not rows:
            await update.message.reply_text("📋 لا توجد فواتير بعد.")
            return
        msg = "📋 آخر 10 فواتير:\n\n"
        buttons = []
        for i, (uid, name, uname, amount, charge_id, date) in enumerate(rows, 1):
            u = f"@{uname}" if uname else str(uid)
            msg += f"{i}. {name or 'مجهول'} ({u})\n   ⭐ {amount} نجمة | 🗓 {date[:10]}\n   🔑 {charge_id}\n\n"
            # charge_id قد يكون طويل - نخزنه في context
            refund_key = f"refund_{i}"
            if not context.user_data.get("refund_map"):
                context.user_data["refund_map"] = {}
            context.user_data["refund_map"][refund_key] = {"uid": uid, "charge_id": charge_id, "amount": amount}
            buttons.append([colored_btn(
                f"↩️ استرداد {amount}⭐ — {name or uid}",
                callback_data=refund_key,
                style="danger"
            )])
        await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(buttons) if buttons else None)
        return

    elif text == "🗑️ حذف مستخدم":
        context.user_data["admin_action"] = "delete_user"
        await update.message.reply_text("أرسل ID المستخدم الذي تريد حذفه:")
        return

    elif text == "📢 إشعار لمستوى":
        context.user_data["admin_action"] = "broadcast_tier"
        tier_kb = InlineKeyboardMarkup([
            [colored_btn("⭐ Tier 1+", callback_data="btier_1", style="primary"),
             colored_btn("⭐⭐ Tier 2+", callback_data="btier_2", style="primary"),
             colored_btn("🌟 Tier 3", callback_data="btier_3", style="primary")],
        ])
        await update.message.reply_text("اختر المستوى:", reply_markup=tier_kb)
        return

    elif text == "👁 معاينة إشعار":
        context.user_data["admin_action"] = "preview_broadcast"
        await update.message.reply_text("أرسل نص الإشعار للمعاينة:")
        return

    elif text == "🔍 بحث مستخدم":
        context.user_data["admin_action"] = "search_user"
        await update.message.reply_text("أرسل ID المستخدم أو @يوزره:")
        return

    elif text == "🌟 قائمة الداعمين":
        donors = get_all_donors()
        if not donors:
            await update.message.reply_text("لا يوجد داعمون حتى الآن.")
            return
        msg = f"🌟 *قائمة الداعمين* ({len(donors)})\n\n"
        for i, d in enumerate(donors[:20], 1):
            tier = get_tier(d["user_id"])
            tier_emoji = ["👤","⭐","⭐⭐","🌟"][tier]
            uname = f"@{d['username']}" if d['username'] else "بدون يوزر"
            msg += f"{i}. {d['name']} ({uname})\n   {tier_emoji} {d['stars']} نجمة\n"
        await update.message.reply_text(msg, parse_mode="Markdown")
        return

    elif text == "🎁 منح مستوى":
        context.user_data["admin_action"] = "grant_tier"
        await update.message.reply_text(
            "أرسل البيانات بهذا الشكل:\n`ID عدد_النجوم`\n\nمثال: `123456789 25`",
            parse_mode="Markdown"
        )
        return

    elif text == "💰 استرداد نجوم":
        await refund_command(update, context)
        return

    elif text == "❌ إلغاء الإشعار":
        await cancel_broadcast(update, context)
        return

    elif text == "🔙 رجوع":
        await update.message.reply_text("تم العودة", reply_markup=admin_main_keyboard())
        return

    elif text == "✉️ رسالة خاصة":
        context.user_data["private_msg"] = True
        await update.message.reply_text(
            "✉️ أرسل معرف المستخدم (رقم ID) ثم الرسالة في سطر جديد.\n"
            "مثال:\n123456789\nمرحباً بك"
        )

    elif text == "⚠️ سجل الأخطاء":
        errors = get_error_logs(10)
        if not errors:
            await update.message.reply_text("✅ لا توجد أخطاء مسجلة.")
            return
        msg = "⚠️ *آخر 10 أخطاء:*\n\n"
        for ts, etype, emsg, uid in errors:
            user_info = f" (مستخدم: {uid})" if uid else ""
            msg += f"• [{ts}] {etype}: {emsg}{user_info}\n"
        await update.message.reply_text(msg)

    elif text == "🗑️ مسح سجل الأخطاء":
        clear_error_logs()
        await update.message.reply_text("✅ تم مسح سجل الأخطاء.")

async def handle_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("broadcast"):
        return False

    broadcast_type = context.user_data.get("broadcast_type", "📝 نص")

    # مرحلة التأكيد - لو وصلنا محتوى جديد نعرض معاينة أولاً
    if not context.user_data.get("broadcast_confirmed"):
        if broadcast_type == "📝 نص":
            if not update.message.text or update.message.text == "❌ إلغاء الإشعار":
                return False
            context.user_data["broadcast_content_text"] = update.message.text
            preview_kb = InlineKeyboardMarkup([[
                colored_btn("✅ إرسال للجميع", callback_data="confirm_adv_broadcast", style="success"),
                colored_btn("✏️ تعديل", callback_data="edit_adv_broadcast", style="primary"),
                colored_btn("❌ إلغاء", callback_data="cancel_broadcast_cb", style="danger"),
            ]])
            await update.message.reply_text(
                f"👁 معاينة الإشعار:\n\n📢 إشعار من الإدارة:\n{update.message.text}",
                reply_markup=preview_kb
            )
            return True
        elif broadcast_type in ["🖼️ صورة", "🎤 صوت", "🎥 فيديو", "📁 ملف"]:
            # تخزين file_id للمعاينة
            if broadcast_type == "🖼️ صورة" and update.message.photo:
                context.user_data["broadcast_file_id"] = update.message.photo[-1].file_id
                context.user_data["broadcast_caption"] = update.message.caption or "📢 إشعار من الإدارة"
                preview_kb = InlineKeyboardMarkup([[
                    colored_btn("✅ إرسال للجميع", callback_data="confirm_adv_broadcast", style="success"),
                    colored_btn("❌ إلغاء", callback_data="cancel_broadcast_cb", style="danger"),
                ]])
                await update.message.reply_photo(
                    update.message.photo[-1].file_id,
                    caption=f"👁 معاينة:\n{context.user_data['broadcast_caption']}",
                    reply_markup=preview_kb
                )
                return True
            elif broadcast_type == "🎤 صوت" and update.message.voice:
                context.user_data["broadcast_file_id"] = update.message.voice.file_id
                context.user_data["broadcast_caption"] = update.message.caption or "📢 إشعار صوتي"
                preview_kb = InlineKeyboardMarkup([[
                    colored_btn("✅ إرسال للجميع", callback_data="confirm_adv_broadcast", style="success"),
                    colored_btn("❌ إلغاء", callback_data="cancel_broadcast_cb", style="danger"),
                ]])
                await update.message.reply_text("👁 تم استلام الصوت. هل تريد إرساله للجميع؟", reply_markup=preview_kb)
                return True
            elif broadcast_type == "🎥 فيديو" and (update.message.video or update.message.document):
                fid = update.message.video.file_id if update.message.video else update.message.document.file_id
                context.user_data["broadcast_file_id"] = fid
                context.user_data["broadcast_caption"] = update.message.caption or "📢 إشعار فيديو"
                preview_kb = InlineKeyboardMarkup([[
                    colored_btn("✅ إرسال للجميع", callback_data="confirm_adv_broadcast", style="success"),
                    colored_btn("❌ إلغاء", callback_data="cancel_broadcast_cb", style="danger"),
                ]])
                await update.message.reply_text("👁 تم استلام الفيديو. هل تريد إرساله للجميع؟", reply_markup=preview_kb)
                return True
            elif broadcast_type == "📁 ملف" and update.message.document:
                context.user_data["broadcast_file_id"] = update.message.document.file_id
                context.user_data["broadcast_caption"] = update.message.caption or "📢 إشعار ملف"
                preview_kb = InlineKeyboardMarkup([[
                    colored_btn("✅ إرسال للجميع", callback_data="confirm_adv_broadcast", style="success"),
                    colored_btn("❌ إلغاء", callback_data="cancel_broadcast_cb", style="danger"),
                ]])
                await update.message.reply_text("👁 تم استلام الملف. هل تريد إرساله للجميع؟", reply_markup=preview_kb)
                return True
            else:
                await update.message.reply_text(f"⚠️ يرجى إرسال {broadcast_type} صالح.", reply_markup=cancel_broadcast_keyboard())
                return True

    # مرحلة الإرسال الفعلي (بعد التأكيد)
    conn = sqlite3.connect("bot.db")
    users = conn.execute("SELECT user_id FROM users").fetchall()
    conn.close()
    success = fail = 0
    context.user_data.pop("broadcast_confirmed", None)

    try:
        if broadcast_type == "📝 نص":
            if not update.message.text or update.message.text == "❌ إلغاء الإشعار":
                return False
            text = context.user_data.pop("broadcast_content_text", update.message.text)
            for (uid,) in users:
                try:
                    await context.bot.send_message(uid, f"📢 إشعار من الإدارة:\n{text}")
                    success += 1
                except:
                    fail += 1
                    await asyncio.sleep(0.05)

        elif broadcast_type == "🖼️ صورة":
            if not update.message.photo:
                await update.message.reply_text("⚠️ يرجى إرسال صورة صالحة.", reply_markup=cancel_broadcast_keyboard())
                return True
            caption = update.message.caption or "📢 إشعار من الإدارة"
            photo = update.message.photo[-1].file_id
            for (uid,) in users:
                try:
                    await context.bot.send_photo(uid, photo=photo, caption=caption)
                    success += 1
                except:
                    fail += 1
                    await asyncio.sleep(0.05)

        elif broadcast_type == "🎤 صوت":
            if not update.message.voice:
                await update.message.reply_text("⚠️ يرجى إرسال ملف صوتي صالح.", reply_markup=cancel_broadcast_keyboard())
                return True
            caption = update.message.caption or "📢 إشعار صوتي"
            voice = update.message.voice.file_id
            for (uid,) in users:
                try:
                    await context.bot.send_voice(uid, voice=voice, caption=caption)
                    success += 1
                except:
                    fail += 1
                    await asyncio.sleep(0.05)

        elif broadcast_type == "🎥 فيديو":
            video_id = None
            if update.message.video:
                video_id = update.message.video.file_id
            elif update.message.document and update.message.document.mime_type and 'video' in update.message.document.mime_type:
                video_id = update.message.document.file_id
            else:
                await update.message.reply_text("⚠️ يرجى إرسال ملف فيديو صالح.", reply_markup=cancel_broadcast_keyboard())
                return True
            caption = update.message.caption or "📢 إشعار فيديو"
            for (uid,) in users:
                try:
                    await context.bot.send_video(uid, video=video_id, caption=caption)
                    success += 1
                except:
                    try:
                        await context.bot.send_document(uid, document=video_id, caption=caption)
                        success += 1
                    except:
                        fail += 1
                        await asyncio.sleep(0.05)

        elif broadcast_type == "📁 ملف":
            if not update.message.document:
                await update.message.reply_text("⚠️ يرجى إرسال ملف صالح.", reply_markup=cancel_broadcast_keyboard())
                return True
            caption = update.message.caption or "📢 إشعار ملف"
            document = update.message.document.file_id
            for (uid,) in users:
                try:
                    await context.bot.send_document(uid, document=document, caption=caption)
                    success += 1
                except:
                    fail += 1
                    await asyncio.sleep(0.05)

    except Exception as e:
        logger.error(f"خطأ في handle_broadcast: {e}")
        await update.message.reply_text("❌ حدث خطأ أثناء الإرسال.")
        context.user_data.pop("broadcast", None)
        context.user_data.pop("broadcast_type", None)
        return True

    await update.message.reply_text(f"✅ تم الإرسال: {success} نجح، {fail} فشل", reply_markup=admin_main_keyboard())
    context.user_data.pop("broadcast", None)
    context.user_data.pop("broadcast_type", None)
    return True

async def handle_private_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("private_msg"):
        parts = update.message.text.strip().split('\n', 1)
        if len(parts) == 2:
            try:
                target_id = int(parts[0].strip())
                msg_text = parts[1].strip()
                await context.bot.send_message(target_id, f"✉️ رسالة خاصة من الإدارة:\n{msg_text}")
                await update.message.reply_text(f"✅ تم إرسال الرسالة إلى {target_id}.")
            except Exception as e:
                await update.message.reply_text(f"❌ خطأ: {e}")
        else:
            await update.message.reply_text("⚠️ الصيغة غير صحيحة. أرسل ID ثم سطر جديد ثم الرسالة.")
        context.user_data["private_msg"] = False
        return True
    return False

# ==================== المعالج الرئيسي للرسائل (يدعم جميع أنواع الوسائط) ====================
# ==================== صوت القرآن — mp3quran API ====================
_QURAN_SERVERS_CACHE = {}  # cache لتجنب طلبات متكررة

async def get_quran_servers() -> dict:
    """يجيب server URLs من mp3quran - نسخة ثابتة ومجربة"""
    global _QURAN_SERVERS_CACHE
    if _QURAN_SERVERS_CACHE:
        return _QURAN_SERVERS_CACHE
    
    # سيرفرات ثابتة ومجربة - بدل API
    SERVERS = {
        "عبد الباسط عبد الصمد": {"server": "https://server6.mp3quran.net/basit/",   "surahs": set(range(1,115))},
        "سعود الشريم":           {"server": "https://server7.mp3quran.net/shuraym/", "surahs": set(range(1,115))},
        "أبو بكر الشاطري":       {"server": "https://server11.mp3quran.net/shatri/", "surahs": set(range(1,115))},
        "ناصر القطامي":          {"server": "https://server6.mp3quran.net/qtm/",     "surahs": set(range(1,115))},
        "مشاري العفاسي":         {"server": "https://server8.mp3quran.net/afs/",     "surahs": set(range(1,115))},
        "ماهر المعيقلي":         {"server": "https://server12.mp3quran.net/maher/",  "surahs": set(range(1,115))},
        "علي الحذيفي":           {"server": "https://server8.mp3quran.net/hthfi/",   "surahs": set(range(1,115))},
        "سعد الغامدي":           {"server": "https://server7.mp3quran.net/s_gmd/",   "surahs": set(range(1,115))},
        "محمد اللحيدان":         {"server": "https://server8.mp3quran.net/lhdan/",   "surahs": set(range(1,115))},
        "عمر بن ضياء الدين":     {"server": "https://server11.mp3quran.net/omar_aldayatin/", "surahs": set(range(1,115))},
    }
    
    _QURAN_SERVERS_CACHE = SERVERS
    return SERVERS

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text if update.message.text else ""

    register_user(user.id, user.username or "", user.full_name)

    # ===== أزرار الكيبورد — تأتي أولاً دائماً =====
    _KB_BTNS = {
        "🔍 تحقق من حديث","📖 باحث القرآن",
        "🎯 اختبر معلوماتك",
        "💰 دعم البوت","ℹ️ عن البوت",
        "🕌 الأذكار","🔙 رجوع","⚙️ لوحة التحكم","❓ سؤال ديني",
        "💬 التحدث مع راوي","🎙️ استمع للقرآن",
        "🔙 خروج من راوي","🔙 خروج من الباحث",
    }

    # عند ضغط زر كيبورد — أوقف أوضاع النص السابقة
    if text in _KB_BTNS:
        for _k in ["quran_search_mode","hadith_search_mode","contact_dev_mode"]:
            context.user_data.pop(_k, None)
        if text != "🌟 قدوتي اليوم":
            context.user_data["qudwati_waiting"] = False
        if text != "❓ سؤال ديني":
            context.user_data.pop("islamic_qa_mode", None)
        if text != "💬 التحدث مع راوي":
            context.user_data.pop("waiting_for_rawi", None)

    # ===== الأدمن =====

    # معالج الملاحظة على المفضلة
    if context.user_data.get("waiting_note"):
        context.user_data.pop("waiting_note", None)

    # ===== معالج راوي AI - المحادثة الشاملة =====
    # معالج راوي - تجاهل أزرار الخروج مباشرة في الشرط
    if context.user_data.get("waiting_for_rawi") and text not in ["🔙 خروج من راوي", "🔙 خروج من الباحث"]:
        is_admin = user.id in ADMIN_IDS
        
        # رسالة انتظار
        wait_msg = await update.message.reply_text("💬 راوي يفكر في إجابتك...")
        
        # الحصول على الإجابة مع الذاكرة
        user_name = user.first_name or "أخي"
        answer = await chat_with_rawi(text, user_name, user_id=user.id, context=context)
        
        # حذف رسالة الانتظار
        await wait_msg.delete()
        
        # إرسال الإجابة مع الإبقاء على كيبورد راوي
        await update.message.reply_text(
            answer,
            parse_mode="Markdown",
            reply_markup=rawi_kb()
        )
        # لا نغير waiting_for_rawi - نبقيه True ليستمر الوضع
        return


    # معالج رسائل التواصل مع المطور
    if context.user_data.get("contact_dev_mode"):
        context.user_data.pop("contact_dev_mode", None)
        # جمع معلومات المرسل
        sender_name = user.full_name
        sender_id = user.id
        sender_username = f"@{user.username}" if user.username else "بدون يوزر"
        # أرسل الرسالة لكل الأدمن
        header = (
            f"📩 *رسالة جديدة من مستخدم*\n"
            f"━━━━━━━━━━━━━━━\n"
            f"👤 {sender_name} ({sender_username})\n"
            f"🆔 `{sender_id}`\n"
            f"━━━━━━━━━━━━━━━\n\n"
        )
        sent_to_admin = False
        for admin_id in ADMIN_IDS:
            try:
                # لو في نص
                if update.message.text:
                    await context.bot.send_message(
                        admin_id,
                        header + update.message.text,
                        parse_mode="Markdown",
                        reply_markup=InlineKeyboardMarkup([[
                            colored_btn(f"↩️ رد على {sender_name}", callback_data=f"reply_user_{sender_id}", style="primary")
                        ]])
                    )
                # لو في صورة
                elif update.message.photo:
                    await context.bot.send_photo(
                        admin_id,
                        update.message.photo[-1].file_id,
                        caption=header + (update.message.caption or ""),
                        parse_mode="Markdown",
                    )
                # لو في صوت
                elif update.message.voice:
                    await context.bot.send_voice(
                        admin_id,
                        update.message.voice.file_id,
                        caption=header,
                        parse_mode="Markdown",
                    )
                # لو في مستند
                elif update.message.document:
                    await context.bot.send_document(
                        admin_id,
                        update.message.document.file_id,
                        caption=header + (update.message.caption or ""),
                        parse_mode="Markdown",
                    )
                sent_to_admin = True
            except Exception as e:
                logger.error(f"contact_dev send error: {e}")

        if sent_to_admin:
            await update.message.reply_text(
                "✅ *تم إرسال رسالتك للمطور*\n\n"
                "سيتم الرد عليك في أقرب وقت ممكن 🤍",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text("⚠️ حدث خطأ في الإرسال، حاول لاحقاً.")
        return

    # معالج أوامر الأدمن التفاعلية
    admin_action = context.user_data.get("admin_action")
    if admin_action and user.id in ADMIN_IDS:
        context.user_data.pop("admin_action", None)

        if admin_action == "reply_user":
            target_id = context.user_data.pop("reply_to_user_id", None)
            if target_id and text:
                try:
                    await context.bot.send_message(
                        target_id,
                        f"📩 *رد من المطور:*\n\n{text}",
                        parse_mode="Markdown"
                    )
                    await update.message.reply_text(f"✅ تم إرسال ردك للمستخدم `{target_id}`", parse_mode="Markdown")
                except Exception as e:
                    await update.message.reply_text(f"❌ فشل الإرسال: {e}")
            else:
                await update.message.reply_text("⚠️ حدث خطأ، حاول مرة ثانية.")
            return

        if admin_action == "search_user":
            info = get_user_info(text.strip())
            if not info:
                await update.message.reply_text("❌ لم يُعثر على المستخدم.")
            else:
                tier_label = get_tier_label(info["tier"])
                msg = (
                    f"👤 *{info['full_name']}*\n"
                    f"🆔 ID: `{info['user_id']}`\n"
                    f"@{info['username'] or 'بدون يوزر'}\n\n"
                    f"{tier_label}\n"
                    f"⭐ النجوم: {info['stars']}\n"
                    f"🔍 البحوث: {info['searches']}\n"
                    f"📅 انضم: {(info['joined'] or '')[:10]}\n"
                    f"🌅 حديث اليوم: {'مفعّل' if info['daily'] else 'موقوف'}\n"
                    f"🕌 الأذكار: {'مفعّلة' if info['adhkar'] else 'موقوفة'}\n"
                )
                await update.message.reply_text(msg, parse_mode="Markdown")
            return

        elif admin_action == "delete_user":
            try:
                uid = int(text.strip())
                conn = sqlite3.connect("bot.db")
                for tbl in ["users", "favorites", "searches", "premium", "donations", "search_history"]:
                    conn.execute(f"DELETE FROM {tbl} WHERE user_id=?", (uid,))
                conn.commit()
                conn.close()
                await update.message.reply_text(f"✅ تم حذف المستخدم {uid} من قاعدة البيانات.")
            except ValueError:
                await update.message.reply_text("❌ أرسل ID رقمي صحيح.")
            except Exception as e:
                await update.message.reply_text(f"❌ خطأ: {e}")
            return

        elif admin_action == "set_welcome":
            save_setting("welcome_msg", text[:1000])
            await update.message.reply_text("✅ تم حفظ رسالة الترحيب الجديدة!")
            return

        elif admin_action == "broadcast_tier_msg":
            tier_min = context.user_data.pop("broadcast_tier_min", 1)
            conn = sqlite3.connect("bot.db")
            cur = conn.cursor()
            cur.execute("SELECT user_id FROM users")
            all_users = [r[0] for r in cur.fetchall()]
            conn.close()
            targets = [uid for uid in all_users if get_tier(uid) >= tier_min]
            sent, failed = 0, 0
            for uid in targets:
                try:
                    await context.bot.send_message(uid, text, parse_mode="Markdown")
                    sent += 1
                    await asyncio.sleep(0.05)
                except:
                    failed += 1
            await update.message.reply_text(
                f"✅ أُرسل إلى {sent} مستخدم (مستوى {tier_min}+)\n❌ فشل: {failed}"
            )
            return

        elif admin_action == "preview_broadcast":
            await update.message.reply_text(
                f"👁 *معاينة الإشعار:*\n{text}",
                parse_mode="Markdown"
            )
            broadcast_kb = InlineKeyboardMarkup([[
                colored_btn("📢 إرسال للجميع", callback_data="confirm_broadcast", style="success"),
                colored_btn("❌ إلغاء", callback_data="cancel_broadcast_cb", style="danger")
            ]])
            context.user_data["pending_broadcast"] = text
            await update.message.reply_text("هل تريد إرساله؟", reply_markup=broadcast_kb)
            return

        elif admin_action == "grant_tier":
            parts = text.strip().split()
            if len(parts) != 2:
                await update.message.reply_text("❌ الصيغة غير صحيحة. مثال: `123456789 25`", parse_mode="Markdown")
                return
            try:
                uid, stars = int(parts[0]), int(parts[1])
                with sqlite3.connect("bot.db") as _gc:
                    _gc.execute(
                        "INSERT INTO premium (user_id, stars, donated_at) VALUES (?,?,datetime('now')) "
                        "ON CONFLICT(user_id) DO UPDATE SET stars=stars+?, donated_at=datetime('now')",
                        (uid, stars, stars)
                    )
                tier = get_tier(uid)
                await update.message.reply_text(
                    f"✅ تم منح {stars} نجمة للمستخدم {uid}\n"
                    f"مستواه الآن: {get_tier_label(tier)}"
                )
            except (ValueError, Exception) as e:
                await update.message.reply_text(f"❌ خطأ: {e}")
            return

    # التحقق من الإبلاغ

    if context.user_data.get("reporting") and update.message.text:
        await handle_report_message(update, context)
        return

        # أزرار الاشتراك

    if text == "🕌 الأذكار":
        kb = InlineKeyboardMarkup([
            [colored_btn("🌄 أذكار الصباح", callback_data="adhkar_sabah", style="primary"),
             colored_btn("🌆 أذكار المساء", callback_data="adhkar_masaa", style="primary")],
        ])
        await update.message.reply_text("اختر نوع الأذكار 👇", reply_markup=kb)
        return

    
    if text == "📖 باحث القرآن":
        for _k in ["hadith_search_mode","islamic_qa_mode","qudwati_waiting"]:
            context.user_data.pop(_k, None)
        context.user_data["hadith_search_mode"] = False
        await cmd_quran_search(update, context)
        return

    if text == "🎯 اختبر معلوماتك":
        # تحقق لو أكمل اليوم
        today = _dt.datetime.now(AMMAN_TZ).strftime("%Y-%m-%d")
        with sqlite3.connect("bot.db") as _c:
            row = _c.execute(
                "SELECT quiz_score FROM quiz_sessions WHERE user_id=? AND quiz_date=? AND quiz_index=10",
                (user.id, today)
            ).fetchone()
        if row:
            await update.message.reply_text(
                f"✅ أكملت اختبار اليوم بنتيجة {row[0]}/10\n\nتعال غداً لاختبار جديد 🌙"
            )
            return
        # سؤال تأكيد
        kb = InlineKeyboardMarkup([
            [colored_btn("✅ نعم، ابدأ الاختبار", callback_data="quiz_confirm", style="success"),
             colored_btn("❌ لا، لاحقاً", callback_data="quiz_cancel", style="danger")],
        ])
        await update.message.reply_text(
            "🎯 *اختبر معلوماتك*\n"
            "━━━━━━━━━━━━━━━\n\n"
            "10 أسئلة في الفقه والتفسير والسيرة\n"
            "⏱ 30 ثانية لكل سؤال\n\n"
            "هل أنت مستعد؟",
            parse_mode="Markdown",
            reply_markup=kb
        )
        return

    
    if text == "💬 التحدث مع راوي":
        if not GROQ_API_KEY:
            await update.message.reply_text(
                "⚠️ ميزة التحدث مع راوي غير متوفرة حالياً.\n"
                "يرجى المحاولة لاحقاً.",
                reply_markup=main_kb(is_admin)
            )
            return
        
        await update.message.reply_text(
            "💬 **مرحباً بك في راوي!**\n"
            "━━━━━━━━━━━━━━━\n\n"
            "🤖 أنا مساعدك الإسلامي الذكي\n"
            "📚 أجيب على أسئلتك الشرعية بأدلة واضحة\n"
            "💡 أساعدك على فهم الإسلام وميزات البوت\n\n"
            "**اسألني أي شيء:**\n"
            "• أسئلة إسلامية: ما حكم...؟ ما فضل...؟\n"
            "• عن البوت: كيف أستخدم...؟ ما هي...؟\n"
            "• محادثة عامة: أي شيء آخر!\n\n"
            "🌟 _ابدأ الكتابة الآن..._\n\n"
            "💡 للخروج: اضغط زر 🔙 خروج من راوي",
            parse_mode="Markdown",
            reply_markup=rawi_kb()
        )
        
        # تفعيل وضع الانتظار
        context.user_data["waiting_for_rawi"] = True
        return
    
    if text == "🔙 خروج من راوي":
        # إيقاف وضع راوي ومسح الذاكرة
        context.user_data["waiting_for_rawi"] = False
        context.user_data.pop("rawi_history", None)  # مسح تاريخ المحادثة
        
        await update.message.reply_text(
            "👋 تم الخروج من راوي\n\n"
            "يمكنك العودة في أي وقت! 😊",
            reply_markup=main_kb(is_admin)
        )
        return
    
    if text == "🔙 خروج من الباحث":
        # إيقاف أوضاع البحث
        context.user_data["quran_search_mode"] = False
        context.user_data["hadith_search_mode"] = False
        
        await update.message.reply_text(
            "👋 تم الخروج من الباحث\n\n"
            "يمكنك العودة للبحث في أي وقت! 😊",
            reply_markup=main_kb(is_admin)
        )
        return
    
    if text == "❓ سؤال ديني":
        for _k in ["quran_search_mode","hadith_search_mode","qudwati_waiting"]:
            context.user_data.pop(_k, None)
        can_ask, remaining, is_free = can_ask_question(user.id)
        if can_ask:
            # فحص rate limit
            if not qa_rate_limiter.is_allowed(user.id):
                await update.message.reply_text(
                    "⏳ الرجاء الانتظار قليلاً قبل إرسال سؤال آخر\n"
                    "الحد الأقصى: 5 أسئلة في الدقيقة"
                )
                return
        
            context.user_data["islamic_qa_mode"] = True
            used = get_qa_usage(user.id)["count"]
            # رسالة واضحة
            if used == 0:
                status_line = f"لديك {QA_FREE_DAILY} أسئلة مجانية اليوم 🆓"
            elif remaining > 0:
                status_line = f"متبقي {remaining} سؤال من أصل {QA_FREE_DAILY} اليوم"
            else:
                status_line = f"متبقي {remaining} سؤال (إضافي مدفوع)"

            await update.message.reply_text(
                f"❓ *سؤال ديني*\n"
                "━━━━━━━━━━━━━━━\n\n"
                f"📊 {status_line}\n\n"
                "اكتب سؤالك الديني وسأجيبك من مصادر أهل السنة 👇\n\n"
                "_مثال: ما حكم صيام يوم السبت منفرداً؟_",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(
                "❓ *سؤال ديني*\n"
                "━━━━━━━━━━━━━━━\n\n"
                f"⚠️ استنفدت أسئلتك المجانية اليوم ({QA_FREE_DAILY}/{QA_FREE_DAILY})\n\n"
                f"يتجدد رصيدك غداً صباحاً 🌅\n\n"
                f"أو أضف {QA_EXTRA_STARS} نجوم للحصول على 5 أسئلة إضافية 👇",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[
                    colored_btn(f"⭐ {QA_EXTRA_STARS} نجوم ← 5 أسئلة", callback_data="qa_buy", style="success")
                ]])
            )
        return

    if text == "🎙️ استمع للقرآن":
        for _k in ["hadith_search_mode","quran_search_mode","islamic_qa_mode"]:
            context.user_data.pop(_k, None)
        context.user_data["quran_listen_mode"] = True
        await update.message.reply_text(
            "🎙️ *استمع للقرآن*\n━━━━━━━━━━━━━━━\n\n"
            "اكتب اسم السورة 👇\n_مثال: الكهف، يس، البقرة_",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[colored_btn("❌ إلغاء", callback_data="listen_cancel")]])
        )
        return

    
    if text == "📜 اقترح لي حديثاً":
        kb = InlineKeyboardMarkup([
            [colored_btn("📗 البخاري", callback_data="suggest_bukhari", style="primary"),
             colored_btn("📘 مسلم", callback_data="suggest_muslim", style="primary")],
            [colored_btn("📙 أبو داود", callback_data="suggest_dawud", style="primary"),
             colored_btn("📕 الترمذي", callback_data="suggest_tirmidhi", style="primary")],
            [colored_btn("📒 ابن ماجه", callback_data="suggest_majah", style="primary")],
        ])
        await update.message.reply_text(
            "📜 *اقترح لي حديثاً*\n\nاختر الكتاب 👇",
            parse_mode="Markdown",
            reply_markup=kb
        )
        return

    # أوامر Premium من لوحة المفاتيح

    # زر الإبلاغ من لوحة المفاتيح الرئيسية
    if text == "⚠️ إبلاغ عن خطأ":
        context.user_data["reporting"] = True
        context.user_data["reporting_hadith_id"] = 0
        context.user_data["reporting_hadith_text"] = "إبلاغ عام من لوحة المفاتيح"
        cancel_kb = InlineKeyboardMarkup([[
            colored_btn("❌ إلغاء التقرير", callback_data="cancel_report", style="danger")
        ]])
        await update.message.reply_text(
            "📝 إبلاغ عن خطأ\n\n"
            "اكتب وصف المشكلة أو الخطأ الذي وجدته:\n"
            "(مثال: خطأ في حديث، معلومات غلط، مشكلة في البوت...)\n\n"
            "أو ابحث عن الحديث أولاً واضغط زر ⚠️ إبلاغ تحته لتحديد الحديث المقصود.",
            reply_markup=cancel_kb
        )
        return

    # معالجة البث الجماعي أولاً للمشرفين
    if user.id in ADMIN_IDS and context.user_data.get("broadcast"):
        if text == "❌ إلغاء الإشعار":
            await cancel_broadcast(update, context)
            return
        if await handle_broadcast(update, context):
            return

    if user.id in ADMIN_IDS:
        if await handle_private_message(update, context):
            return

    # معالجة حالة انتظار الاسترداد
    # معالجة اختيارات التبرع
    if text in ["💰 دعم البوت", "/donate"]:
        await donate_command(update, context)
        return
    if text in ["⭐ 1 نجمة", "⭐ 5 نجوم", "⭐ 10 نجوم", "⭐ 25 نجمة", "⭐ 50 نجمة"]:
        if await handle_donation_choice(update, context):
            return
    if text == "🔙 رجوع":
        with sqlite3.connect("bot.db") as _c3:
            _row3 = _c3.execute("SELECT daily_hadith, adhkar_sub FROM users WHERE user_id=?", (user.id,)).fetchone()
        _d3 = _row3[0] if _row3 else 1
        _a3 = _row3[1] if _row3 else 0
        await update.message.reply_text(
            "تم العودة للقائمة الرئيسية.",
            reply_markup=main_kb(user.id in ADMIN_IDS)
        )
        return

    # الأزرار الرئيسية
    if text == "🔍 تحقق من حديث":
        # أوقف كل الأوضاع الأخرى صراحةً
        for _k in ["quran_search_mode","islamic_qa_mode","qudwati_waiting"]:
            context.user_data.pop(_k, None)
        context.user_data["hadith_search_mode"] = True
        await update.message.reply_text(
            "🔍 *باحث الحديث الذكي*\n"
            "━━━━━━━━━━━━━━━\n\n"
            "📚 *البحث من الكتب الستة فقط:*\n"
            "✓ صحيح البخاري\n"
            "✓ صحيح مسلم\n"
            "✓ سنن أبي داود\n"
            "✓ سنن الترمذي\n"
            "✓ سنن النسائي\n"
            "✓ سنن ابن ماجه\n\n"
            "*طرق البحث:*\n\n"
            "🔹 جزء من نص الحديث\n"
            "  ← `إنما الأعمال بالنيات`\n\n"
            "🔹 اسم الراوي\n"
            "  ← `أبو هريرة`\n\n"
            "🔹 موضوع الحديث\n"
            "  ← `فضل الصدقة`\n\n"
            "✍️ اكتب الآن 👇\n\n"
            "💡 للخروج: اضغط 🔙 خروج من الباحث",
            parse_mode="Markdown",
            reply_markup=search_kb("حديث")
        )
        return
    # ===== معالج البحث القرآني =====

    # معالج قدوتي — فقط لو لا يوجد وضع نص آخر نشط
    _active_mode = (
        context.user_data.get("islamic_qa_mode") or
        context.user_data.get("quran_search_mode") or
        context.user_data.get("hadith_search_mode")
    )
    if context.user_data.get("qudwati_waiting") and text and not _active_mode and text not in _KB_BTNS and not text.startswith("/"):
        context.user_data["qudwati_waiting"] = False
        correct_answer = context.user_data.get("qudwati_answer_saved", "")
        user_ans = text.strip()
        # مرادفات الأرقام
        _NUM_MAP = {
            "٩٦٠":"960","٩٥٠":"950","٩٠٠":"900","٨٠":"80","٣٨":"38","٦٣":"63",
            "عشر":"10","عشرة":"10","مئة":"100","ألف":"1000","مئتين":"200",
            "تسعمئة":"900","تسعة وخمسين":"950","ستين":"60",
        }
        def _normalize(t):
            for ar, en in _NUM_MAP.items():
                t = t.replace(ar, en)
            return t
        user_ans_n = _normalize(user_ans)
        correct_n = _normalize(correct_answer)

        stop_words = {"رضي","الله","عنه","عليه","السلام","عنها","عليها","صلى","وسلم","بن","أبو","ابن","من","في","على","إلى","عن","هو","هي","كان","قال"}
        important_words = [w for w in correct_n.split() if len(w) > 2 and w not in stop_words]
        import re as _cmp
        user_nums = set(_cmp.findall(r'\d+', user_ans_n))
        ans_nums  = set(_cmp.findall(r'\d+', correct_n))
        num_match  = bool(user_nums & ans_nums)
        word_match = any(word in user_ans_n for word in important_words)
        is_correct = num_match or word_match
        if is_correct:
            await update.message.reply_text(
                f"✅ *إجابة صحيحة!* أحسنت 🌟\n\n"
                f"📝 الإجابة الكاملة:\n{correct_answer}",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(
                f"❌ *إجابة خاطئة*\n\n"
                f"✅ الإجابة الصحيحة:\n{correct_answer}",
                parse_mode="Markdown"
            )
        return

    # معالج السؤال الديني
    if context.user_data.get("islamic_qa_mode") and text and text not in _KB_BTNS and not text.startswith("/"):
        context.user_data["islamic_qa_mode"] = False
        # تحقق من الرصيد
        can_ask, remaining, _ = can_ask_question(user.id)
        if not can_ask:
            await update.message.reply_text(
                f"⚠️ *انتهت أسئلتك اليوم!*\n\n"
                f"استخدمت {QA_FREE_DAILY}/{QA_FREE_DAILY} أسئلة مجانية.\n"
                f"يتجدد رصيدك غداً 🌅\n\n"
                f"أو ادفع {QA_EXTRA_STARS} نجوم للحصول على 5 أسئلة إضافية 👇",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[
                    colored_btn(f"⭐ {QA_EXTRA_STARS} نجوم ← 5 أسئلة", callback_data="qa_buy", style="success")
                ]])
            )
            return
        # خصم سؤال أولاً
        increment_qa_usage(user.id)
        _, remaining_after, _ = can_ask_question(user.id)
        wait = await update.message.reply_text(f"⏳ جاري البحث... (متبقي: {remaining_after} سؤال)")
        system = (
            "أنت عالم إسلامي على منهج أهل السنة والجماعة. "
            "أجب بشكل واضح مختصر لا يتجاوز 300 كلمة مع ذكر المصدر. "
            "إذا كان السؤال خارج الدين اعتذر بلطف. أجب بالعربية فقط."
        )
        answer = await call_gemini(f"{system}\n\nالسؤال: {text}")
        # لو فشل الـ API أعِد الخصم
        if answer.startswith("⚠️"):
            decrement_qa_usage(user.id)
            remaining_after = remaining
        try:
            await wait.delete()
        except Exception:
            pass
        rows = []
        if remaining_after > 0:
            rows.append([colored_btn(f"❓ سؤال آخر ({remaining_after} متبقٍ)", callback_data="qa_new", style="primary")])
        else:
            rows.append([colored_btn(f"⭐ {QA_EXTRA_STARS} نجوم ← 5 أسئلة إضافية", callback_data="qa_buy", style="success")])
        rows.append([colored_btn("📋 سجل أسئلتي", callback_data="qa_history", style="primary")])
        await update.message.reply_text(
            f"❓ *{text}*\n"
            "━━━━━━━━━━━━━━━\n\n"
            f"{answer}\n\n"
            "━━━━━━━━━━━━━━━\n"
            "_⚠️ للتحقق راجع أهل العلم_",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(rows)
        )
        return

    # ===== معالج البحث القرآني =====

    if context.user_data.get("quran_listen_mode") and text and text not in _KB_BTNS:
        context.user_data.pop("quran_listen_mode", None)
        import re as _rl
        t = _rl.sub(r'^سورة\s*', '', text.strip())
        surah_num = QURAN_SURAHS.get(t, 0)
        if not surah_num:
            for sn, snum in QURAN_SURAHS.items():
                if t in sn or sn in t:
                    surah_num = snum; t = sn; break
        if not surah_num:
            await update.message.reply_text(f"⚠️ ما عرفت «{text}»\nجرب: الكهف، يس، البقرة")
            return
        # جيب القراء من API
        servers = await get_quran_servers()
        reciters = [(name, info) for name, info in servers.items() if surah_num in info.get("surahs", set())]
        if not reciters:
            reciters = list(servers.items())
        rows = []
        for i in range(0, len(reciters), 2):
            row = []
            for j in [i, i+1]:
                if j < len(reciters):
                    row.append(colored_btn(f"🎙️ {reciters[j][0]}", callback_data=f"ls_{surah_num}_{j}"))
            rows.append(row)
        rows.append([colored_btn("❌ إلغاء", callback_data="listen_cancel")])
        # حفظ السيرفر + اسم القارئ للـ cache
        context.user_data["lp"] = [info["server"] for _, info in reciters]
        context.user_data["lp_names"] = [name for name, _ in reciters]
        await update.message.reply_text(
            f"🎙️ *{t}*\n━━━━━━━━━━━━━━━\nاختر القارئ 👇",
            parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(rows)
        )
        return

    if context.user_data.get("quran_search_mode") and text and not text.startswith("/") and text != "🔙 خروج من الباحث":
        # تجاهل زر الخروج - دعه يمر للمعالج الخاص
        if text == "🔙 خروج من الباحث":
            # لا تعالجه هنا - دعه يمر للأسفل
            pass
        else:
            # لا نغلق الوضع - نبقيه مفتوح
            wait = await update.message.reply_text("🔍 جاري البحث في القرآن الكريم...")
        try:
            results = []
            import re as _re
            t = text.strip()

            # الحالة 1: رقم:رقم مثل 2:255
            num_ref = _re.match(r'^(\d+):(\d+)$', t)
            # الحالة 2: اسم سورة:رقم مثل الكهف:10
            name_ref = _re.match(r'^([^\d:]+):(\d+)$', t)
            # الحالة 3: اسم سورة فقط — ينظف ويبحث بمطابقة جزئية
            import re as _re2
            t_clean = _re2.sub(r'^سورة\s*', '', t).strip()  # يحذف "سورة " من البداية
            name_only = t_clean in QURAN_SURAHS
            # لو ما لقى — جرب مطابقة جزئية
            if not name_only and not num_ref and not name_ref:
                for sn in QURAN_SURAHS:
                    if t_clean in sn or sn in t_clean:
                        t_clean = sn
                        name_only = True
                        break

            if num_ref:
                s, a = int(num_ref.group(1)), int(num_ref.group(2))
                ayah = await fetch_ayah_by_ref(s, a)
                if ayah:
                    results = [ayah]

            elif name_ref:
                sname = name_ref.group(1).strip()
                a = int(name_ref.group(2))
                # تصحيح اسم السورة — جرب مطابقة جزئية
                s = QURAN_SURAHS.get(sname, 0)
                if not s:
                    for sn, snum in QURAN_SURAHS.items():
                        if sname in sn or sn in sname:
                            s = snum
                            break
                if s:
                    ayah = await fetch_ayah_by_ref(s, a)
                    if ayah:
                        results = [ayah]
                else:
                    await wait.edit_text(
                        f"⚠️ لم أعثر على سورة «{sname}»\n"
                        "تأكد من الاسم مثل: `الكهف:10` أو `يس:1`"
                    )
                    return

            elif name_only:
                # اسم سورة فقط — جيب أول 5 آيات
                s = QURAN_SURAHS.get(t_clean, 0)
                for a in range(1, 6):
                    ayah = await fetch_ayah_by_ref(s, a)
                    if ayah:
                        results.append(ayah)

            else:
                # بحث نصي حر — يشمل الأخطاء الإملائية
                results = await fetch_quran_search(t)

            if not results:
                kb = InlineKeyboardMarkup([[
                    colored_btn("🔄 بحث جديد", callback_data="qr_new", style="primary")
                ]])
                await wait.edit_text(
                    f"⚠️ ما لقيت نتائج لـ «{text}»\n\n"
                    "جرّب بطريقة ثانية:\n"
                    "• كلمات من الآية: `واصبر وما صبرك`\n"
                    "• اسم السورة:الآية: `الكهف:10`\n"
                    "• اسم السورة فقط: `يس`",
                    reply_markup=kb
                )
                return

            context.user_data["quran_results"] = results
            context.user_data["quran_page"] = 0
            context.user_data["quran_tafsir"] = {}

            h = results[0]
            msg = build_ayah_msg(h, page=0, total=len(results))
            kb = build_ayah_keyboard(h, 0, len(results))
            await wait.delete()
            await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=kb)
        except Exception as e:
            logger.error(f"Quran search handler error: {e}")
            await wait.edit_text("⚠️ حدث خطأ، حاول مرة ثانية.")
            return

    # ===== معالج البحث عن حديث =====
    if context.user_data.get("hadith_search_mode") and text and not text.startswith("/") and text not in _KB_BTNS and text != "🔙 خروج من الباحث":
        # تجاهل زر الخروج - دعه يمر للمعالج الخاص
        if text == "🔙 خروج من الباحث":
            # لا تعالجه هنا - دعه يمر للأسفل
            pass
        else:
            # لا نغلق الوضع - نبقيه مفتوح

            if len(text) < 3:
                await update.message.reply_text("⚠️ أرسل نصاً أطول (3 أحرف على الأقل).")
                return
            if is_rate_limited(user.id):
                await update.message.reply_text("⏳ أرسلت طلبات كثيرة، انتظر ثوانٍ قليلة.")
                return

            wait = await update.message.reply_text("⏳ جاري البحث في الدرر السنية...")
        try:
            rawi_match = is_rawi_search(text)
            search_query = rawi_match if rawi_match else text
            logger.info(f"[HADITH SEARCH] user={user.id} query={search_query[:50]}")
            results = await search_dorar_api(search_query)
            logger.info(f"[HADITH SEARCH] results={len(results)}")

            if not results:
                suggestion = get_spell_suggestion(text)
                if suggestion and suggestion != text:
                    results = await smart_hadith_search(suggestion)
                    if results:
                        await wait.edit_text(f"🔍 لم أجد نتائج لـ «{text}»، أبحث عن «{suggestion}»...")

            if results:
                log_search(user.id, text)
                log_search_history(user.id, text, len(results))
                context.user_data["search_results"] = results
                context.user_data["search_results_all"] = results
                context.user_data["search_page"] = 0
                context.user_data["grade_filter"] = "all"
                context.user_data["search_id"] = _uuid.uuid4().hex[:8]
                await show_search_page(update, context, wait)
            else:
                url = f"https://dorar.net/hadith/search?q={urllib.parse.quote(text)}"
                suggestion = get_spell_suggestion(text)
                kb = [[colored_btn("🔍 ابحث في الدرر السنية", url=url, style="primary")]]
                if suggestion:
                    kb.append([colored_btn(f"✏️ ابحث عن: {suggestion}", callback_data=f"spell_{suggestion[:50]}", style="primary")])
                spell_hint = f"\n\n💡 هل تقصد: *{suggestion}*؟" if suggestion else ""
                await wait.edit_text(
                    f"⚠️ لم أجد نتائج لـ «{text}»{spell_hint}\n\n"
                    "💡 جرّب كلمة أو كلمتان من نص الحديث",
                    reply_markup=InlineKeyboardMarkup(kb),
                    parse_mode="Markdown"
                )
        except Exception as e:
            logger.error(f"[HADITH SEARCH ERROR] {e}", exc_info=True)
            try:
                await wait.edit_text(
                    "⚠️ تعذّر الاتصال بقاعدة البيانات\n"
                    "انتظر ثوانٍ وحاول مجدداً 🔄"
                )
            except Exception:
                pass
            return

    if text == "اقترح لي حديثا📜":
        await random_suggestion(update, context)
        return

    if text == "📞 تواصل مع المطور":
        context.user_data["contact_dev_mode"] = True
        for _k in ["quran_search_mode","hadith_search_mode","islamic_qa_mode","qudwati_waiting"]:
            context.user_data.pop(_k, None)
        await update.message.reply_text(
            "📞 *تواصل مع المطور*\n"
            "━━━━━━━━━━━━━━━\n\n"
            "اكتب رسالتك وسأوصلها للمطور مباشرة 👇\n\n"
            "_يمكنك إرسال نص أو صورة أو صوت_",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                colored_btn("❌ إلغاء", callback_data="contact_cancel", style="danger")
            ]])
        )
        return

    if text == "ℹ️ عن البوت":
        users, searches, hadiths, _ = get_global_stats()
        await update.message.reply_text(
            f"ℹ️ *{BOT_NAME}* — بوت الأحاديث النبوية\n\n"
            f"📚 يحتوي على {hadiths} حديث من كتب السنة\n"
            "🎯 اختبر معلوماتك يومياً\n"
            "🤲 أدعية يومية من القرآن والسنة\n"
            "🌟 قصص الأنبياء والصحابة يومياً\n"
            "🔍 تحقق من صحة أي حديث\n\n"
            "👤 المطور: @ssss_ssss_x\n"
            "/help للمساعدة"
        )
        return
    if text == "⚙️ لوحة التحكم" and user.id in ADMIN_IDS:
        await admin_panel(update, context)
        return

    # أوامر الأدمن النصية - كل أزرار لوحة التحكم
    ADMIN_BUTTONS = {
        "📊 إحصائيات", "📅 إحصائيات الأسبوع",
        "📈 نمو يومي", "⏰ أوقات النشاط",
        "🏆 أنشط المستخدمين", "🆕 مستخدمون جدد",
        "📊 إحصائيات متقدمة",
        "🔍 بحث مستخدم", "🌟 قائمة الداعمين", "🎁 منح مستوى",
        "🗑️ حذف مستخدم", "✉️ رسالة خاصة",
        "📢 إشعار متقدم", "📢 إشعار لمستوى",
        "📋 سجل الفواتير",
        "📝 نص", "🖼️ صورة", "🎤 صوت", "🎥 فيديو", "📁 ملف",
        "⚠️ سجل الأخطاء", "🗑️ مسح سجل الأخطاء",
        "💰 استرداد نجوم", "❌ إلغاء الإشعار",
    }
    if user.id in ADMIN_IDS and text in ADMIN_BUTTONS:
        await handle_admin_actions(update, context)
        return

    # إذا كانت الرسالة تحتوي على وسائط، تجاهلها
    if not text:
        return

    # أي نص لا يتوافق مع الأوضاع النشطة — تجاهله بهدوء
    # الباحثان يشتغلان فقط بعد ضغط الزر
    return
    try:
        # تحقق من بحث بالراوي
        rawi_match = is_rawi_search(text)
        search_query = rawi_match if rawi_match else text
        results = await search_dorar_api(search_query)

        # لو ما ردّ - جرب الاقتراح الإملائي تلقائياً
        if not results:
            suggestion = get_spell_suggestion(text)
            if suggestion and suggestion != text:
                logger.info(f"[SPELL] trying suggestion: {suggestion}")
                results = await smart_hadith_search(suggestion)
                if results:
                    await wait.edit_text(f"🔍 لم أجد نتائج لـ «{text}»، أبحث عن «{suggestion}»...")

        if not results:
            await wait.edit_text("⏳ جاري البحث في قاعدة البيانات...")
        if results:
            log_search(user.id, text)
            log_search_history(user.id, text, len(results))
            context.user_data["search_results"] = results
            context.user_data["search_results_all"] = results
            context.user_data["search_page"] = 0
            context.user_data["grade_filter"] = "all"
            context.user_data["search_id"] = _uuid.uuid4().hex[:8]
            await show_search_page(update, context, wait)
        else:
            # اقتراح إملائي في رسالة النتيجة
            suggestion = get_spell_suggestion(text)
            spell_hint = ""
            if suggestion:
                spell_hint = f"\n\n💡 هل تقصد: *{suggestion}*؟\nاضغط الزر للبحث به 👇"
            url = f"https://dorar.net/hadith/search?q={urllib.parse.quote(text)}"
            kb = [[colored_btn("🔍 ابحث في الدرر السنية", url=url, style="primary")]]
            if spell_hint and suggestion:
                kb.append([colored_btn(f"✏️ ابحث عن: {suggestion}", callback_data=f"spell_{suggestion[:50]}", style="primary")])
            not_found_msg = (
                f"⚠️ لم أجد نتائج لـ «{text}»"
                f"{spell_hint}\n\n"
                "💡 جرّب:\n"
                "• كلمة أو كلمتان من نص الحديث\n"
                "• اسم الراوي مثل: أبو هريرة\n"
                "• بدون «قال النبي» أو «روى»"
            )
            await wait.edit_text(not_found_msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
    except Exception as e:
        logger.error(f"خطأ في البحث: {e}")
        log_error(type(e).__name__, str(e), user.id, traceback.format_exc())
        await wait.edit_text("⚠️ حدث خطأ أثناء البحث. تم تسجيل المشكلة.")

def build_hadith_msg(h: dict, page: int, total: int) -> str:
    """بناء رسالة الحديث من dict"""
    text = h['text'].strip()
    source = h.get('source') or 'غير محدد'
    grade = h.get('grade') or 'غير محدد'
    # أيقونة الدرجة
    if "صحيح" in grade:
        grade_icon = "✅"
    elif "حسن" in grade:
        grade_icon = "🟡"
    elif "ضعيف" in grade:
        grade_icon = "🔴"
    else:
        grade_icon = "⚪"
    # هل من الكتب الستة؟
    is_sitta = any(k in source for k in _KUTUB_SITTA)
    sitta_badge = " 📗" if is_sitta else ""
    # escape HTML
    def _e(s): return str(s).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
    msg = f"🔍 <b>نتيجة البحث ({page+1}/{total})</b>\n"
    msg += "━━━━━━━━━━━━━━━\n\n"
    msg += f"📌 {_e(text)}\n\n"
    msg += f"👤 الراوي: {_e(h.get('rawi') or 'غير محدد')}\n"
    if h.get('mohdith'):
        msg += f"🎓 المحدث: {_e(h['mohdith'])}\n"
    msg += f"📚 المصدر: <b>{_e(source)}</b>{sitta_badge}\n"
    msg += f"{grade_icon} الدرجة: {_e(grade)}\n"
    return msg

def build_share_text(h: dict) -> str:
    """بناء نص المشاركة"""
    txt = f"📖 حديث نبوي شريف\n\n"
    txt += f"📌 {h['text']}\n\n"
    txt += f"👤 الراوي: {h['rawi']}\n"
    if h.get('mohdith'):
        txt += f"🎓 المحدث: {h['mohdith']}\n"
    txt += f"📚 المصدر: {h['source']}\n"
    txt += f"⚖️ الدرجة: {h['grade']}\n\n"
    txt += "🤖 بوت راوِي للتحقق من الأحاديث"
    return txt

def build_keyboard(page: int, total: int, hid, has_sharh: bool = False, user_id: int = 0, is_fav: bool = False, context_filter: str = "all") -> InlineKeyboardMarkup:
    """بناء لوحة الأزرار"""
    keyboard = []
    if total > 1:
        nav_row = []
        if page > 0:
            nav_row.append(colored_btn("⬅️ السابق", callback_data="nav_prev", style="primary"))
        if page < total - 1:
            nav_row.append(colored_btn("التالي ➡️", callback_data="nav_next", style="primary"))
        if nav_row:
            keyboard.append(nav_row)
    
    # زر شرح الحديث بالـ AI
    keyboard.append([colored_btn("🤖 شرح بالذكاء الاصطناعي", callback_data=f"explain_{page}", style="success")])
    
    # زر المفضلة لـ Tier 2+
    if user_id and has_favorites(user_id):
        fav_btn = colored_btn("💔 إزالة من المفضلة", callback_data="fav_remove" if is_fav else "fav_save", style="danger")
        keyboard.append([fav_btn])
    keyboard.append([
        colored_btn("📤 شارك الحديث", callback_data="share", style="primary"),
        colored_btn("⚠️ إبلاغ", callback_data=f"report_{hid}", style="danger"),
    ])
    if user_id:
        grade = context_filter if context_filter else "all"
        grade_labels = {"all": "🔘 كل الدرجات", "sahih": "✅ صحيح فقط", "hasan": "🟡 حسن فقط"}
        keyboard.append([colored_btn(
            f"🎚 الفلتر: {grade_labels.get(grade, 'كل الدرجات')}",
            callback_data=f"grade_filter"
        )])
    # زر فلتر الكتب الستة
    sitta_filter = context_filter == "sitta"
    keyboard.append([colored_btn(
        "📗 الكتب الستة فقط ✓" if sitta_filter else "📗 الكتب الستة فقط",
        callback_data="filter_sitta", style="success" if sitta_filter else "primary"
    )])
    keyboard.append([colored_btn("🔄 بحث جديد", callback_data="new", style="primary")])
    return InlineKeyboardMarkup(keyboard)

async def show_search_page(update: Update, context: ContextTypes.DEFAULT_TYPE, wait_message):
    results = context.user_data.get("search_results", [])
    page = context.user_data.get("search_page", 0)
    if not results:
        await wait_message.edit_text("⚠️ لا توجد نتائج.")
        return

    total_pages = len(results)
    if page >= total_pages:
        page = total_pages - 1
        context.user_data["search_page"] = page

    user = update.effective_user
    h = results[page]
    msg = build_hadith_msg(h, page, total_pages)
    favs = get_favorites(user.id) if has_favorites(user.id) else []
    is_fav = any(f["text"] == h["text"] for f in favs)
    cf = context.user_data.get("grade_filter", "all")
    keyboard = build_keyboard(page, total_pages, h["id"], user_id=user.id, is_fav=is_fav, context_filter=cf)

    await wait_message.delete()
    await update.message.reply_text(msg, parse_mode="HTML", reply_markup=keyboard)

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    user = update.effective_user

    # إذا انتهت الجلسة أو ما في نتائج
    results = context.user_data.get("search_results", [])
    stale_actions = {"nav_prev", "nav_next", "share", "fav_save", "fav_remove", "grade_filter"}
    if q.data in stale_actions and not results:
        # حاول استرجاع الجلسة من DB
        if session and session.get("results"):
            context.user_data["search_results"] = session["results"]
            context.user_data["search_results_all"] = session["results"]
            context.user_data["search_page"] = session["page"]
            context.user_data["grade_filter"] = session.get("grade_filter", "all")
            context.user_data["search_id"] = session.get("search_id", "")
            results = session["results"]
        else:
            await q.answer("⚠️ انتهت الجلسة، ابحث من جديد.", show_alert=True)
            return

    if q.data == "new":
        await q.answer()
        await q.message.reply_text("✍️ أرسل الحديث الجديد أو اسم الراوي:")
        await q.message.delete()
    elif q.data == "share":
        await q.answer()
        results = context.user_data.get("search_results", [])
        page = context.user_data.get("search_page", 0)
        if not results:
            if session and session.get("results"):
                results = session["results"]
                page = session["page"]
                context.user_data["search_results"] = results
                context.user_data["search_page"] = page
        if results and page < len(results):
            h = results[page]
            share_text = build_share_text(h)
            # زر مشاركة مباشر عبر Telegram
            share_url = f"https://t.me/share/url?url=https://t.me/{BOT_USERNAME.lstrip('@')}&text={urllib.parse.quote(share_text)}"
            share_kb = InlineKeyboardMarkup([[
                colored_btn("📤 شارك الحديث", switch_inline_query="hadith_share", style="primary")
            ]])
            await q.message.reply_text(share_text, reply_markup=share_kb)
        else:
            await q.answer("⚠️ لا يوجد حديث للمشاركة", show_alert=True)
    elif q.data.startswith("report_"):
        await q.answer()
        context.user_data["reporting"] = True
        results = context.user_data.get("search_results", [])
        page = context.user_data.get("search_page", 0)
        if results and page < len(results):
            h = results[page]
            context.user_data["reporting_hadith_id"] = h["id"]
            context.user_data["reporting_hadith_text"] = h["text"]
            cancel_kb = InlineKeyboardMarkup([[
                colored_btn("❌ إلغاء التقرير", callback_data="cancel_report", style="danger")
            ]])
            await q.message.reply_text(
                "📝 الإبلاغ عن خطأ في الحديث\n\n"
                "اكتب وصف الخطأ الذي وجدته (مثلاً: خطأ في النص، الراوي، المصدر، الدرجة).\n"
                "سيتم إرسال تقريرك إلى المطور للنظر فيه.\n\n"
                "أو اضغط إلغاء لو ضغطت بالخطأ 👇",
                reply_markup=cancel_kb
            )
        else:
            await q.message.reply_text("⚠️ حدث خطأ، يرجى إعادة البحث والمحاولة.")

    elif q.data == "nav_prev":
        results = context.user_data.get("search_results", [])
        if not results:
            await q.answer("⚠️ انتهت الجلسة، ابحث من جديد.", show_alert=True)
            return
        page = context.user_data.get("search_page", 0)
        if page > 0:
            await q.answer()
            context.user_data["search_page"] = page - 1
            await q.message.delete()
            await show_search_page_from_callback(update, context)
        else:
            await q.answer("أنت في الصفحة الأولى", show_alert=True)
    elif q.data == "nav_next":
        results = context.user_data.get("search_results", [])
        if not results:
            await q.answer("⚠️ انتهت الجلسة، ابحث من جديد.", show_alert=True)
            return
        page = context.user_data.get("search_page", 0)
        if page < len(results) - 1:
            await q.answer()
            context.user_data["search_page"] = page + 1
            await q.message.delete()
            await show_search_page_from_callback(update, context)
        else:
            await q.answer("أنت في الصفحة الأخيرة", show_alert=True)

    # ===== مزايا Premium =====
    elif q.data == "fav_save":
        if not has_favorites(user.id):
            stars = get_premium_stars(user.id)
            await q.answer(f"⭐ تحتاج {max(0,TIER2_STARS-stars)} نجمة إضافية لفتح المفضلة! /donate", show_alert=True)
            return
        results = context.user_data.get("search_results", [])
        page = context.user_data.get("search_page", 0)
        if results and page < len(results):
            h = results[page]
            saved = save_favorite(user.id, h)
            if saved:
                await q.answer("✅ تم الحفظ في المفضلة!")
                cf = context.user_data.get("grade_filter", "all")
                kb = build_keyboard(page, len(results), h["id"], user_id=user.id, is_fav=True, context_filter=cf)
                try:
                    await q.message.edit_reply_markup(reply_markup=kb)
                except:
                    pass
                # عرض خيار إضافة ملاحظة للـ VIP tier 3+
                if True:  # all users
                    note_kb = InlineKeyboardMarkup([[
                        colored_btn("📝 أضف ملاحظة", callback_data=f"add_note", style="success"),
                        colored_btn("تخطي", callback_data="skip_note", style="danger")
                    ]])
                    context.user_data["note_hadith"] = h.get("text","")
                    await q.message.reply_text("هل تريد إضافة ملاحظة على هذا الحديث؟", reply_markup=note_kb)
            else:
                await q.answer("📌 موجود في المفضلة مسبقاً")

    elif q.data == "fav_remove":
        if not has_favorites(user.id):
            await q.answer("⭐ هذه الميزة للداعمين فقط", show_alert=True)
            return
        results = context.user_data.get("search_results", [])
        page = context.user_data.get("search_page", 0)
        if results and page < len(results):
            h = results[page]
            remove_favorite(user.id, h["text"])
            await q.answer("🗑️ تم الإزالة من المفضلة")
            cf = context.user_data.get("grade_filter", "all")
            kb = build_keyboard(page, len(results), h["id"], user_id=user.id, is_fav=False, context_filter=cf)
            try:
                await q.message.edit_reply_markup(reply_markup=kb)
            except:
                pass

    elif q.data.startswith("topic_"):
        if not has_topics(user.id):
            await q.answer("⭐ تحتاج نجمة واحدة فقط لفتح هذه الميزة! اضغط دعم البوت", show_alert=True)
            return
        topic = q.data[6:]
        await q.answer("🔍 جاري البحث...")
        loading = await q.message.reply_text(f"🔍 جاري البحث في موضوع: *{topic}*...", parse_mode="Markdown")
        results = await search_dorar_api(topic)

        try:
            await loading.delete()
        except:
            pass
        if not results:
            await q.message.reply_text(f"⚠️ ما وجدت نتائج عن موضوع: {topic}")
            return
        context.user_data["search_results"] = results
        context.user_data["search_results_all"] = results
        context.user_data["search_page"] = 0
        context.user_data["grade_filter"] = "all"
        context.user_data["from_favorites"] = False
        h = results[0]
        msg = build_hadith_msg(h, 0, len(results))
        # تحقق إذا الحديث محفوظ في المفضلة
        favs = get_favorites(user.id) if has_favorites(user.id) else []
        is_fav = any(f["text"] == h["text"] for f in favs)
        kb = build_keyboard(0, len(results), h["id"], user_id=user.id, is_fav=is_fav, context_filter="all")
        await q.message.reply_text(msg, reply_markup=kb)

    elif q.data == "confirm_broadcast":
        await q.answer()
        msg = context.user_data.pop("pending_broadcast", "")
        if not msg:
            await q.message.reply_text("❌ لا توجد رسالة للإرسال.")
            return
        conn = sqlite3.connect("bot.db")
        cur = conn.cursor()
        cur.execute("SELECT user_id FROM users")
        all_users = [r[0] for r in cur.fetchall()]
        conn.close()
        sent, failed = 0, 0
        for uid in all_users:
            try:
                await context.bot.send_message(uid, msg, parse_mode="Markdown")
                sent += 1
                await asyncio.sleep(0.05)
            except:
                failed += 1
        await q.message.reply_text(f"✅ أُرسل إلى {sent} مستخدم\n❌ فشل: {failed}")

    elif q.data == "confirm_adv_broadcast":
        await q.answer()
        broadcast_type = context.user_data.get("broadcast_type", "📝 نص")
        conn2 = sqlite3.connect("bot.db")
        all_users2 = [r[0] for r in conn2.execute("SELECT user_id FROM users").fetchall()]
        conn2.close()
        sent2, failed2 = 0, 0
        try:
            if broadcast_type == "📝 نص":
                text2 = context.user_data.pop("broadcast_content_text", "")
                for uid2 in all_users2:
                    try:
                        await context.bot.send_message(uid2, f"📢 إشعار من الإدارة:\n{text2}")
                        sent2 += 1
                        await asyncio.sleep(0.05)
                    except:
                        failed2 += 1
            elif broadcast_type == "🖼️ صورة":
                fid2 = context.user_data.pop("broadcast_file_id", "")
                cap2 = context.user_data.pop("broadcast_caption", "")
                for uid2 in all_users2:
                    try:
                        await context.bot.send_photo(uid2, photo=fid2, caption=cap2)
                        sent2 += 1
                        await asyncio.sleep(0.05)
                    except:
                        failed2 += 1
            elif broadcast_type == "🎤 صوت":
                fid2 = context.user_data.pop("broadcast_file_id", "")
                cap2 = context.user_data.pop("broadcast_caption", "")
                for uid2 in all_users2:
                    try:
                        await context.bot.send_voice(uid2, voice=fid2, caption=cap2)
                        sent2 += 1
                        await asyncio.sleep(0.05)
                    except:
                        failed2 += 1
            elif broadcast_type in ["🎥 فيديو", "📁 ملف"]:
                fid2 = context.user_data.pop("broadcast_file_id", "")
                cap2 = context.user_data.pop("broadcast_caption", "")
                for uid2 in all_users2:
                    try:
                        await context.bot.send_document(uid2, document=fid2, caption=cap2)
                        sent2 += 1
                        await asyncio.sleep(0.05)
                    except:
                        failed2 += 1
        except Exception as e2:
            logger.error(f"confirm_adv_broadcast: {e2}")
        context.user_data.pop("broadcast", None)
        context.user_data.pop("broadcast_type", None)
        context.user_data.pop("broadcast_confirmed", None)
        await q.message.edit_text(f"✅ تم الإرسال: {sent2} نجح، {failed2} فشل")

    elif q.data == "edit_adv_broadcast":
        await q.answer()
        context.user_data.pop("broadcast_content_text", None)
        await q.message.edit_text("✏️ أرسل النص الجديد للإشعار:", reply_markup=None)

    elif q.data.startswith("quiz_") and q.data not in ("quiz_confirm", "quiz_cancel"):
        chosen_idx = int(q.data[5:]) if q.data[5:].isdigit() else -1
        questions = context.user_data.get("quiz_questions", [])
        idx_q = context.user_data.get("quiz_index", 0)
        score = context.user_data.get("quiz_score", 0)
        date = context.user_data.get("quiz_date", "")

        if not questions:
            await q.answer("انتهت الجلسة، ابدأ الاختبار من جديد", show_alert=True)
            return
        if idx_q >= len(questions):
            await q.answer("انتهت الجلسة", show_alert=True)
            return
        # تحقق إذا أجاب مسبقاً على هذا السؤال
        if context.user_data.get("quiz_answered"):
            await q.answer("✅ أجبت على هذا السؤال مسبقاً!", show_alert=True)
            return

        context.user_data["quiz_answered"] = True

        # إلغاء المؤقت
        job_name = f"quiz_timeout_{user.id}"
        for job in context.job_queue.get_jobs_by_name(job_name):
            job.schedule_removal()

        q_data = questions[idx_q]
        if chosen_idx < 0 or chosen_idx >= len(q_data["options"]):
            await q.answer("خطأ في الإجابة", show_alert=True)
            return
        chosen = q_data["options"][chosen_idx]
        correct = chosen == q_data["answer"]
        if correct:
            score += 1
            context.user_data["quiz_score"] = score
            result_line = f"✅ *إجابة صحيحة!* 🎉\n\n💡 {q_data['explain']}"
        else:
            result_line = (
                f"❌ *إجابة خاطئة*\n"
                f"الجواب الصحيح: *{q_data['answer']}*\n\n"
                f"💡 {q_data['explain']}"
            )

        try:
            await q.message.edit_text(
                result_line,
                parse_mode="Markdown"
            )
        except Exception:
            pass

        next_idx = idx_q + 1
        context.user_data["quiz_index"] = next_idx
        save_quiz_session(user.id, questions, next_idx, score, date)
        total_q = len(questions)

        if next_idx >= total_q:
            context.user_data.pop("in_daily_quiz", None)
            save_quiz_session(user.id, questions, 10, score, date)
            stars = "⭐" * score + "☆" * (total_q - score)
            pct = round(score / total_q * 100)
            if pct == 100: comment = "ممتاز! أنت نجم! 🏆"
            elif pct >= 80: comment = "رائع جداً! 👏"
            elif pct >= 60: comment = "جيد! استمر 👍"
            elif pct >= 40: comment = "تحتاج مراجعة 📚"
            else: comment = "لا تستسلم، استمر في التعلم 💪"
            # إحصائيات الشهر
            this_month = _dt.datetime.now(AMMAN_TZ).strftime("%Y-%m")
            with sqlite3.connect("bot.db") as _qdb:
                rows = _qdb.execute(
                    "SELECT quiz_score FROM quiz_sessions WHERE user_id=? AND quiz_date LIKE ?",
                    (user.id, f"{this_month}%")
                ).fetchall()
            month_count = len(rows)
            month_avg = round(sum(r[0] for r in rows) / month_count, 1) if rows else 0
            # أقوى موضوع
            questions_done = context.user_data.get("quiz_questions", [])
            topic_scores = {}
            for qi, qobj in enumerate(questions_done):
                topic = qobj.get("topic", "عام")
                if topic not in topic_scores:
                    topic_scores[topic] = {"right": 0, "total": 0}
                topic_scores[topic]["total"] += 1
            # (تبسيط — نعرض الموضوع من اسم السؤال)
            share_text = (
                f"🎯 نتيجتي في اختبار راوِي\n"
                f"━━━━━━━━━━━━━━━\n"
                f"النتيجة: {score}/{total_q} {stars}\n"
                f"━━━━━━━━━━━━━━━\n"
                f"جرّب أنت: @G4bGN_bot"
            )
            share_kb = InlineKeyboardMarkup([[
                colored_btn("📤 شارك نتيجتك", switch_inline_query=share_text[:100], style="primary")
            ]])
            await q.message.reply_text(
                f"🎯 *انتهى الاختبار!*\n"
                "━━━━━━━━━━━━━━━\n\n"
                f"نتيجتك: *{score}/{total_q}* {stars}\n"
                f"💬 {comment}\n\n"
                f"📊 *هذا الشهر:*\n"
                f"اختبارات: {month_count} | متوسطك: {month_avg}/10\n\n"
                "تعال غداً لاختبار جديد 🌙",
                parse_mode="Markdown",
                reply_markup=share_kb
            )
        else:
            await asyncio.sleep(1)
            context.user_data["quiz_answered"] = False
            await send_quiz_question(q.message, context, questions[next_idx], next_idx + 1)

    elif q.data == "cancel_broadcast_cb":
        await q.answer("تم الإلغاء")
        context.user_data.pop("pending_broadcast", None)
        context.user_data.pop("broadcast", None)
        context.user_data.pop("broadcast_type", None)
        context.user_data.pop("broadcast_confirmed", None)
        context.user_data.pop("broadcast_content_text", None)
        context.user_data.pop("broadcast_file_id", None)
        try:
            await q.message.delete()
        except:
            pass

    elif q.data.startswith("suggest_"):
        await q.answer("⏳ جاري البحث...")
        book_key = q.data.replace("suggest_", "")
        books = {
            "bukhari": "البخاري",
            "muslim": "مسلم",
            "dawud": "أبو داود",
            "tirmidhi": "الترمذي",
            "majah": "ابن ماجه",
        }
        book_name = books.get(book_key, "البخاري")
        # موضوعات عشوائية للبحث
        import random as _rs
        topics = ["الصبر", "الصلاة", "الإخلاص", "الأخلاق", "الدعاء", "التوبة", "الرحمة", "العلم", "الصدق", "الكرم"]
        topic = _rs.choice(topics)
        loading = await q.message.reply_text(f"⏳ جاري اقتراح حديث من {book_name}...")
        try:
            results = await search_dorar_api(topic)
            # فلتر الكتاب المطلوب
            filtered = [h for h in results if book_name in (h.get("source") or "")]
            if not filtered:
                filtered = results  # لو ما في من الكتاب خذ أي نتيجة
            if filtered:
                h = _rs.choice(filtered[:10])
                msg = build_hadith_msg(h, 0, 1)
                kb = InlineKeyboardMarkup([
                    [colored_btn("📤 شارك الحديث", callback_data="share", style="primary"),
                     ],
                    [colored_btn("📜 اقتراح آخر", callback_data=f"suggest_{book_key}", style="primary")],
                ])
                await loading.delete()
                await q.message.reply_text(msg, parse_mode="Markdown", reply_markup=kb)
            else:
                await loading.edit_text(f"⚠️ لم أجد حديثاً من {book_name} الآن، حاول مرة ثانية.")
        except Exception as e:
            logger.error(f"suggest callback error: {e}")
            await loading.edit_text("⚠️ حدث خطأ، حاول مرة ثانية.")

            
            hadith_index = int(parts[1])
            
            # الحصول على الحديث من context
            results = context.user_data.get("last_search_results", [])
            if hadith_index >= len(results):
                await q.message.reply_text("⚠️ الحديث غير موجود")
                return
            
            hadith = results[hadith_index]
            hadith_text = hadith.get("text", "")
            source = hadith.get("source", "")
            
            # إظهار رسالة انتظار
            wait_msg = await q.message.reply_text("🤖 جاري شرح الحديث بالذكاء الاصطناعي...\n⏳ الرجاء الانتظار...")
            
            # الحصول على الشرح
            explanation = await explain_hadith_with_ai(hadith_text, source)
            
            # حذف رسالة الانتظار
            try:
                await wait_msg.delete()
            except:
                pass
            
            # إرسال الشرح
            msg = (
            )
            
            await q.message.reply_text(
                msg,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[
                    colored_btn("🔙 رجوع", callback_data=f"back_to_results", style="primary")
                ]])
            )
        except Exception as e:
            logger.error(f"Explain hadith error: {e}")
            await q.message.reply_text("⚠️ حدث خطأ في شرح الحديث، حاول مرة أخرى")
        return

    # ===== شرح الحديث بالـ AI =====
    elif q.data.startswith("explain_"):
        await q.answer()
        try:
            parts = q.data.split("_")
            if len(parts) < 2:
                await q.message.reply_text("⚠️ خطأ في البيانات")
                return
            
            hadith_index = int(parts[1])
            # استخدام search_results بدل last_search_results
            results = context.user_data.get("search_results", [])
            if not results or hadith_index >= len(results):
                await q.message.reply_text("⚠️ الحديث غير موجود")
                return
            
            hadith = results[hadith_index]
            hadith_text = hadith.get("text", "")
            source = hadith.get("source", "")
            
            wait_msg = await q.message.reply_text("🤖 جاري الشرح...\n⏳ انتظر قليلاً...")
            explanation = await explain_hadith_with_ai(hadith_text, source)
            
            try:
                await wait_msg.delete()
            except:
                pass
            
            short_text = hadith_text[:150] + "..." if len(hadith_text) > 150 else hadith_text
            msg = f"📚 *شرح الحديث*\n━━━━━━━━━━━━━━━\n\n*الحديث:*\n{short_text}\n\n*المصدر:* {source}\n\n━━━━━━━━━━━━━━━\n*الشرح:*\n{explanation}"
            
            await q.message.reply_text(msg, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Explain error: {e}")
            await q.message.reply_text("⚠️ حدث خطأ في الشرح")
        return

    elif q.data == "fc_start":
        # المنشئ يبدأ اختباره
        await q.answer()
        questions = context.user_data.get("fc_questions", [])
        if not questions:
            await q.message.reply_text("⚠️ انتهت الجلسة، ابدأ تحدياً جديداً.")
            return
        context.user_data["fc_index"] = 0
        context.user_data["fc_score"] = 0
        await q.message.reply_text("🚀 البداية! استعد للسؤال الأول 👇")
        await _send_fc_question(q.message, context)

    elif q.data.startswith("fc_ans_"):
        await q.answer()
        challenge_id = context.user_data.get("fc_id")
        if not challenge_id:
            await q.message.reply_text("⚠️ انتهت الجلسة.")
            return
        ans_idx = int(q.data.split("_")[2])
        questions = context.user_data.get("fc_questions", [])
        idx = context.user_data.get("fc_index", 0)
        score = context.user_data.get("fc_score", 0)
        if idx >= len(questions):
            return
        q_data = questions[idx]
        chosen = q_data["options"][ans_idx]
        correct = chosen == q_data["answer"]
        if correct:
            score += 1
            context.user_data["fc_score"] = score
            result_line = "✅ *صحيح!* 🎉"
        else:
            result_line = f"❌ *خطأ* — الجواب: {q_data['answer']}"
        try:
            await q.message.edit_text(
                f"{result_line}\n\n📖 {q_data.get('explain', '')}",
                parse_mode="Markdown"
            )
        except Exception:
            pass
        next_idx = idx + 1
        context.user_data["fc_index"] = next_idx
        if next_idx >= len(questions):
            # انتهى الاختبار — احفظ النتيجة
            role = context.user_data.get("fc_role", "creator")
            save_fc_score(challenge_id, user.id, user.full_name, score)
            ch = get_friend_challenge(challenge_id)
            total = len(questions)
            stars = "⭐" * score + "☆" * (total - score)
            if ch and ch["status"] == "finished":
                # الاثنين خلّصوا — أرسل النتيجة لكليهما مع زر مشاركة
                result_msg = build_fc_result(ch)
                # أرسل النتيجة للمستخدم الحالي
                await q.message.reply_text(
                    result_msg + "\n\n🎉 *انتهى التحدي!*",
                    parse_mode="Markdown"
                )
                
                # أرسل النتيجة للطرف الآخر
                other_id = ch["opponent_id"] if role == "creator" else ch["creator_id"]
                try:
                    await context.bot.send_message(
                        other_id,
                        result_msg + "\n\n🎉 *انتهى التحدي!*",
                        parse_mode="Markdown"
                    )
                    logger.info(f"✅ Challenge result sent to user {other_id}")
                except Exception as e:
                    logger.error(f"❌ Error sending challenge result to {other_id}: {e}")
            else:
                # الطرف الأول خلّص — انتظر الآخر
                await q.message.reply_text(
                    f"✅ *أنهيت الاختبار!*\n\n"
                    f"نتيجتك: {score}/{total} {stars}\n\n"
                    "⏳ ننتظر صديقك ليكمل التحدي...\n"
                    "سيصلك الإشعار فور انتهائه 🔔",
                    parse_mode="Markdown"
                )
        else:
            await _send_fc_question(q.message, context)

    elif q.data == "filter_sitta":
        await q.answer()
        cur = context.user_data.get("grade_filter", "all")
        if cur == "sitta":
            context.user_data["grade_filter"] = "all"
        else:
            context.user_data["grade_filter"] = "sitta"
        # أعد ترتيب النتائج مع الفلتر
        all_results = context.user_data.get("search_results_all", context.user_data.get("search_results", []))
        context.user_data["search_results_all"] = all_results
        if context.user_data["grade_filter"] == "sitta":
            context.user_data["search_results"] = filter_kutub_sitta(all_results)
        else:
            context.user_data["search_results"] = all_results
        context.user_data["search_page"] = 0
        await show_search_page_from_callback(q, context)

    elif q.data == "grade_filter":
        await q.answer()
        cur_filter = context.user_data.get("grade_filter", "all")
        nxt = {"all": "sahih", "sahih": "hasan", "hasan": "all"}
        context.user_data["grade_filter"] = nxt.get(cur_filter, "all")
        results_all = context.user_data.get("search_results_all", context.user_data.get("search_results", []))
        context.user_data["search_results_all"] = results_all
        grade_map = {"sahih": "صحيح", "hasan": "حسن", "all": None}
        gf = grade_map.get(context.user_data["grade_filter"])
        if gf:
            filtered = [r for r in results_all if gf in r.get("grade", "")]
            context.user_data["search_results"] = filtered if filtered else results_all
        else:
            context.user_data["search_results"] = results_all
        context.user_data["search_page"] = 0
        await show_search_page_from_callback(update, context)

    elif q.data == "fc_start":
        # المنشئ يبدأ اختباره
        await q.answer()
        questions = context.user_data.get("fc_questions", [])
        if not questions:
            await q.message.reply_text("⚠️ انتهت الجلسة، ابدأ تحدياً جديداً.")
            return
        context.user_data["fc_index"] = 0
        context.user_data["fc_score"] = 0
        await q.message.reply_text("🚀 البداية! استعد للسؤال الأول 👇")
        await _send_fc_question(q.message, context)

    elif q.data.startswith("fc_ans_"):
        await q.answer()
        challenge_id = context.user_data.get("fc_id")
        if not challenge_id:
            await q.message.reply_text("⚠️ انتهت الجلسة.")
            return
        ans_idx = int(q.data.split("_")[2])
        questions = context.user_data.get("fc_questions", [])
        idx = context.user_data.get("fc_index", 0)
        score = context.user_data.get("fc_score", 0)
        if idx >= len(questions):
            return
        q_data = questions[idx]
        chosen = q_data["options"][ans_idx]
        correct = chosen == q_data["answer"]
        if correct:
            score += 1
            context.user_data["fc_score"] = score
            result_line = "✅ *صحيح!* 🎉"
        else:
            result_line = f"❌ *خطأ* — الجواب: {q_data['answer']}"
        try:
            await q.message.edit_text(
                f"{result_line}\n\n📖 {q_data.get('explain', '')}",
                parse_mode="Markdown"
            )
        except Exception:
            pass
        next_idx = idx + 1
        context.user_data["fc_index"] = next_idx
        if next_idx >= len(questions):
            # انتهى الاختبار — احفظ النتيجة
            role = context.user_data.get("fc_role", "creator")
            save_fc_score(challenge_id, user.id, user.full_name, score)
            ch = get_friend_challenge(challenge_id)
            total = len(questions)
            stars = "⭐" * score + "☆" * (total - score)
            if ch and ch["status"] == "finished":
                # الاثنين خلّصوا — أرسل النتيجة لكليهما مع زر مشاركة
                result_msg = build_fc_result(ch)
                # أرسل النتيجة للمستخدم الحالي
                await q.message.reply_text(
                    result_msg + "\n\n🎉 *انتهى التحدي!*",
                    parse_mode="Markdown"
                )
                
                # أرسل النتيجة للطرف الآخر
                other_id = ch["opponent_id"] if role == "creator" else ch["creator_id"]
                try:
                    await context.bot.send_message(
                        other_id,
                        result_msg + "\n\n🎉 *انتهى التحدي!*",
                        parse_mode="Markdown"
                    )
                    logger.info(f"✅ Challenge result sent to user {other_id}")
                except Exception as e:
                    logger.error(f"❌ Error sending challenge result to {other_id}: {e}")
            else:
                # الطرف الأول خلّص — انتظر الآخر
                await q.message.reply_text(
                    f"✅ *أنهيت الاختبار!*\n\n"
                    f"نتيجتك: {score}/{total} {stars}\n\n"
                    "⏳ ننتظر صديقك ليكمل التحدي...\n"
                    "سيصلك الإشعار فور انتهائه 🔔",
                    parse_mode="Markdown"
                )
        else:
            await _send_fc_question(q.message, context)

    elif q.data == "adhkar_sabah":
        try:
            dhikr, fadl, source = _random.choice(ADHKAR_SABAH)
            msg = (
                f"🌄 أذكار الصباح\n"
                f"━━━━━━━━━━━━━━━\n\n"
                f"✨ {dhikr}\n\n"
                f"💡 الفضل: {fadl}\n"
                f"📚 المصدر: {source}\n\n"
                f"━━━━━━━━━━━━━━━\n"
                f"🤖 {BOT_NAME} | {BOT_USERNAME}"
            )
            await q.answer()
            await q.message.reply_text(msg)
        except Exception as e:
            logger.error(f"adhkar_sabah: {e}")
            await q.answer("⚠️ خطأ، حاول مرة أخرى", show_alert=True)

    elif q.data == "adhkar_masaa":
        try:
            dhikr, fadl, source = _random.choice(ADHKAR_MASAA)
            msg = (
                f"🌆 أذكار المساء\n"
                f"━━━━━━━━━━━━━━━\n\n"
                f"✨ {dhikr}\n\n"
                f"💡 الفضل: {fadl}\n"
                f"📚 المصدر: {source}\n\n"
                f"━━━━━━━━━━━━━━━\n"
                f"🤖 {BOT_NAME} | {BOT_USERNAME}"
            )
            await q.answer()
            await q.message.reply_text(msg)
        except Exception as e:
            logger.error(f"adhkar_masaa: {e}")
            await q.answer("⚠️ خطأ، حاول مرة أخرى", show_alert=True)

    elif q.data.startswith("spell_"):
        suggested = q.data[6:]
        await q.answer()
        wait2 = await q.message.reply_text(f"🔍 جاري البحث عن «{suggested}»...")
        try:
            results = await search_dorar_api(suggested)
            if results:
                log_search(user.id, suggested)
                log_search_history(user.id, suggested, len(results))
                context.user_data["search_results"] = results
                context.user_data["search_results_all"] = results
                context.user_data["search_page"] = 0
                context.user_data["grade_filter"] = "all"
                await show_search_page(update, context, wait2)
            else:
                await wait2.edit_text(f"⚠️ لم أجد نتائج لـ «{suggested}» أيضاً.")
        except Exception as e:
            logger.error(f"spell callback: {e}")
            await wait2.edit_text("⚠️ خطأ في البحث، حاول لاحقاً.")

    elif q.data.startswith("refund_") and user.id in ADMIN_IDS:
        await q.answer()
        refund_map = context.user_data.get("refund_map", {})
        info = refund_map.get(q.data)
        if not info:
            await q.message.reply_text("❌ انتهت الجلسة، افتح سجل الفواتير من جديد")
            return
        target_uid = info["uid"]
        charge_id = info["charge_id"]
        amount = info["amount"]
        try:
            await context.bot.refund_star_payment(
                user_id=target_uid,
                telegram_payment_charge_id=charge_id
            )
            conn = sqlite3.connect("bot.db")
            conn.execute("DELETE FROM donations WHERE user_id=? AND charge_id=?", (target_uid, charge_id))
            conn.commit()
            conn.close()
            await q.message.reply_text(f"✅ تم استرداد {amount}⭐ للمستخدم {target_uid}")
        except Exception as e:
            await q.message.reply_text(f"❌ فشل الاسترداد: {e}")

    elif q.data == "confirm_report":
        await q.answer()
        report_text = context.user_data.pop("pending_report_text", "")
        hadith_text = context.user_data.get("reporting_hadith_text", "")
        tier = get_tier(user.id)
        badge = "🌟" if tier >= 3 else "⭐" if tier >= 1 else ""
        user_info = f"@{user.username}" if user.username else user.full_name
        if badge:
            user_info = f"{badge} {user_info}"
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(
                    admin_id,
                    f"⚠️ *تقرير خطأ في حديث*\n\n"
                    f"👤 المستخدم: {user_info} (ID: {user.id})\n"
                    f"📌 الحديث: {hadith_text[:200]}...\n"
                    f"📝 التقرير: {report_text}",
                    parse_mode="Markdown"
                )
            except:
                pass
        context.user_data.pop("reporting_hadith_id", None)
        context.user_data.pop("reporting_hadith_text", None)
        try:
            await q.message.edit_text("✅ تم إرسال تقريرك إلى المطور. شكراً لمساعدتك في تحسين البوت!")
        except:
            await q.message.reply_text("✅ تم إرسال تقريرك إلى المطور. شكراً!")

    elif q.data == "cancel_report":
        await q.answer("✅ تم إلغاء التقرير")
        context.user_data.pop("reporting", None)
        context.user_data.pop("reporting_hadith_id", None)
        context.user_data.pop("reporting_hadith_text", None)
        context.user_data.pop("pending_report_text", None)
        try:
            await q.message.delete()
        except:
            pass

    elif q.data == "skip_note":
        await q.answer()
        context.user_data.pop("note_hadith", None)
        try:
            await q.message.delete()
        except:
            pass

    elif q.data == "qudwati_next":
        await q.answer()
        import random as _rq
        story = get_qudwati_of_day()
        msg = build_qudwati_msg(story)
        context.user_data["qudwati_question"] = story["question"]
        context.user_data["qudwati_answer"] = story["answer"]
        context.user_data["qudwati_answer_saved"] = story["answer"]
        context.user_data["qudwati_waiting"] = True
        context.user_data["current_qudwati"] = story
        bot_link = f"https://t.me/{BOT_USERNAME.lstrip('@')}"
        share_text = urllib.parse.quote(
            f"🌟 قدوتي اليوم: {story['name']}\n\n"
            f"{story['story'][:200]}...\n\n"
            f"💡 العبرة: {story['lesson']}\n\n"
            f"تعرّف على قصص الأنبياء والصحابة يومياً عبر بوت راوِي:\n{bot_link}"
        )
        share_url = f"https://t.me/share/url?url={bot_link}&text={share_text}"
        kb = InlineKeyboardMarkup([
            [colored_btn("🔄 قدوة أخرى", callback_data="qudwati_next", style="primary"),
             colored_btn("📤 شارك القصة", switch_inline_query=f"qudwati_{story['name'][:30]}", style="primary")],
            [colored_btn("🔄 قدوة أخرى", callback_data="qudwati_next", style="primary"),
             colored_btn("✅ أظهر الإجابة", callback_data="qudwati_reveal", style="success")],
        ])
        try:
            await q.message.edit_text(msg, parse_mode="Markdown", reply_markup=kb)
        except:
            await q.message.reply_text(msg, parse_mode="Markdown", reply_markup=kb)

    # ===== الباحث القرآني =====
    # ===== ختم القرآن =====

    elif q.data == "contact_cancel":
        await q.answer()
        context.user_data.pop("contact_dev_mode", None)
        try:
            await q.message.edit_text("❌ تم إلغاء التواصل.")
        except Exception:
            pass

    elif q.data.startswith("reply_user_"):
        await q.answer()
        target_id = int(q.data.split("_")[2])
        context.user_data["reply_to_user_id"] = target_id
        context.user_data["admin_action"] = "reply_user"
        await q.message.reply_text(
            f"✏️ اكتب ردك على المستخدم `{target_id}`:",
            parse_mode="Markdown"
        )

    elif q.data == "quiz_confirm":
        await q.answer()
        try:
            await q.message.delete()
        except Exception:
            pass
        await cmd_quiz_new(q, context)

    elif q.data == "quiz_cancel":
        await q.answer("تم الإلغاء ✅")
        try:
            await q.message.delete()
        except Exception:
            pass

    elif q.data == "qa_new":
        await q.answer()
        can_ask, remaining, _ = can_ask_question(user.id)
        if can_ask:
            context.user_data["islamic_qa_mode"] = True
            await q.message.reply_text(
                f"❓ اكتب سؤالك الديني 👇\n_({remaining} سؤال متبقي اليوم)_",
                parse_mode="Markdown"
            )
        else:
            kb = InlineKeyboardMarkup([[
                colored_btn(f"⭐ أضف 5 أسئلة مقابل {QA_EXTRA_STARS} نجوم", callback_data="qa_buy", style="success")
            ]])
            await q.message.reply_text(
                f"⚠️ انتهت أسئلتك اليوم!\nيتجدد رصيدك غداً 🌅",
                reply_markup=kb
            )

    elif q.data == "qa_history":
        await q.answer()
        with sqlite3.connect("bot.db") as _qhdb:
            rows_h = _qhdb.execute(
                "SELECT question, created_at FROM qa_history WHERE user_id=? ORDER BY id DESC LIMIT 5",
                (user.id,)
            ).fetchall()
        if not rows_h:
            await q.message.reply_text("📋 ما سألت أي سؤال بعد.")
            return
        msg_h = "📋 *آخر 5 أسئلة:*\n━━━━━━━━━━━━━━━\n\n"
        for i, (question, created_at) in enumerate(rows_h, 1):
            date_str = created_at[:10] if created_at else ""
            msg_h += f"{i}. {question[:80]}\n   📅 {date_str}\n\n"
        await q.message.reply_text(msg_h, parse_mode="Markdown")

    elif q.data == "listen_cancel":
        await q.answer()
        context.user_data.pop("quran_listen_mode", None)
        context.user_data.pop("lp", None)
        try: await q.message.delete()
        except: pass

    elif q.data.startswith("ls_"):
        """معالج اختيار القارئ - يرسل ملف صوتي مع cache ذكي"""
        await q.answer("⏳")
        try:
            parts = q.data.split("_")
            s, idx = int(parts[1]), int(parts[2])
        except:
            await q.answer("⚠️ خطأ في البيانات", show_alert=True)
            return
        
        servers_list = context.user_data.get("lp", [])
        reciters_names = context.user_data.get("lp_names", [])
        
        if idx >= len(servers_list):
            await q.answer("⚠️ القارئ غير متاح", show_alert=True)
            return
        
        server = servers_list[idx]
        surah_name = QURAN_SURAHS_REV.get(s, f"سورة {s}")
        
        # استخدم اسم القارئ كمفتاح للـ cache (بدل الرقم)
        reciter_name = reciters_names[idx] if idx < len(reciters_names) else f"r{idx}"
        reciter_key = reciter_name  # المفتاح الفريد لكل قارئ
        
        # ==================== تحقق من الـ Cache أولاً ====================
        cached_file_id = get_cached_audio(s, reciter_key)
        
        if cached_file_id:
            # الملف موجود في الـ cache → أرسله مباشرة!
            logger.info(f"✅ Cache HIT: {surah_name} - {reciter_key}")
            try:
                await q.message.reply_audio(
                    audio=cached_file_id,
                    caption=f"📖 {surah_name}\n🎙️ {reciter_name}",
                    title=surah_name,
                    performer=reciter_name
                )
                try:
                    await q.message.delete()
                except:
                    pass
                return
            except Exception as e:
                # لو الـ file_id منتهي → احذفه من الـ cache
                logger.warning(f"⚠️ Cached file_id expired: {e}")
                with sqlite3.connect("bot.db") as conn:
                    conn.execute(
                        "DELETE FROM audio_cache WHERE surah_num=? AND reciter=?",
                        (s, reciter_key)
                    )
        
        # ==================== الملف مش موجود → حمّله ====================
        url = f"{server}{s:03d}.mp3"
        wait_msg = await q.message.reply_text(
            f"⏳ جاري تحميل *{surah_name}*...\n"
            f"_قد يستغرق دقيقة للسور الطويلة_ ⏱️",
            parse_mode="Markdown"
        )
        
        import io as _io
        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=300),  # 5 دقائق
                headers={"User-Agent": "Mozilla/5.0 (compatible; QuranBot/1.0)"}
            ) as sess:
                async with sess.get(url) as resp:
                    if resp.status == 200:
                        # جلب حجم الملف
                        content_length = resp.headers.get('Content-Length')
                        file_size = int(content_length) if content_length else 0
                        
                        # تحقق من حد Telegram (50 ميجا)
                        if file_size > 50 * 1024 * 1024:
                            await wait_msg.edit_text(
                                f"⚠️ *{surah_name}* كبيرة جداً\n"
                                f"الحجم: {file_size // (1024*1024)} ميجا\n\n"
                                f"🔗 [استمع مباشرة]({url})\n\n"
                                f"_حد Telegram: 50 ميجا_",
                                parse_mode="Markdown",
                                reply_markup=InlineKeyboardMarkup([[
                                    colored_btn("🎧 استمع مباشرة", url=url, style="primary")
                                ]])
                            )
                            return
                        
                        # تحميل الملف
                        logger.info(f"📥 Downloading: {surah_name} ({file_size // 1024} KB)")
                        data = await resp.read()
                        
                        if len(data) > 10000:  # على الأقل 10KB
                            # إنشاء ملف BytesIO
                            audio_file = _io.BytesIO(data)
                            audio_file.name = f"{surah_name}.mp3"
                            
                            # تحديث رسالة الانتظار
                            await wait_msg.edit_text(f"📤 جاري إرسال {surah_name}...")
                            
                            # إرسال الملف
                            sent_msg = await q.message.reply_audio(
                                audio=audio_file,
                                caption=f"📖 {surah_name}\n🎙️ {reciter_name}",
                                title=surah_name,
                                performer=reciter_name
                            )
                            
                            # ==================== حفظ file_id في الـ cache ====================
                            if sent_msg and sent_msg.audio:
                                file_id = sent_msg.audio.file_id
                                save_audio_cache(s, reciter_key, file_id, len(data))
                                logger.info(f"💾 Saved to cache: {surah_name}")
                            
                            # حذف رسائل الانتظار
                            try:
                                await wait_msg.delete()
                                await q.message.delete()
                            except:
                                pass
                        else:
                            await wait_msg.edit_text("⚠️ الملف تالف أو غير متاح")
                    
                    elif resp.status == 404:
                        await wait_msg.edit_text(
                            f"⚠️ السورة غير متاحة لهذا القارئ\n"
                            f"جرب قارئ آخر 🎙️"
                        )
                    else:
                        await wait_msg.edit_text(f"⚠️ خطأ في التحميل ({resp.status})")
        
        except asyncio.TimeoutError:
            logger.error(f"⏱️ Timeout downloading: {surah_name}")
            await wait_msg.edit_text(
                f"⏱️ *انتهت مهلة التحميل*\n\n"
                f"السورة كبيرة جداً، جرب:\n"
                f"• قارئ آخر\n"
                f"• سورة أصغر\n"
                f"• [استماع مباشر]({url})",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[
                    colored_btn("🎧 استمع مباشرة", url=url, style="primary")
                ]])
            )
        
        except Exception as e:
            logger.error(f"❌ ls_audio error: {e}")
            import traceback
            logger.error(traceback.format_exc())
            
            try:
                await wait_msg.edit_text(
                    f"❌ حدث خطأ في التحميل\n\n"
                    f"جرب:\n"
                    f"• قارئ آخر\n"
                    f"• [استماع مباشر]({url})",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([[
                        colored_btn("🎧 استمع مباشرة", url=url, style="primary")
                    ]])
                )
            except:
                await q.answer("❌ حدث خطأ", show_alert=True)

    elif q.data == "listen_cancel":
        await q.answer()
        context.user_data.pop("quran_listen_mode", None)
        try: await q.message.delete()
        except: pass

    elif q.data.startswith("lc_"):
        # lc_{surah}_{reciter}
        await q.answer("⏳")
        try:
            parts = q.data.split("_", 2)
            s = int(parts[1])
            reciter = parts[2]
        except Exception:
            await q.answer("⚠️ خطأ", show_alert=True)
            return
        surah_name = QURAN_SURAHS_REV.get(s, f"سورة {s}")
        wait_msg = await q.message.reply_text(f"⏳ جاري تحضير {surah_name}...")
        try:
            file_id = await upload_surah_to_channel(context.bot, reciter, s)
            await wait_msg.delete()
            if file_id:
                await q.message.reply_audio(
                    audio=file_id,
                    caption=f"📖 {surah_name} — 🎙️ {reciter}",
                    title=surah_name,
                    performer=reciter,
                )
                try: await q.message.delete()
                except: pass
            else:
                await q.answer("⚠️ السورة غير متاحة حالياً", show_alert=True)
        except Exception as e:
            logger.error(f"lc_ error: {e}")
            try: await wait_msg.delete()
            except: pass
            await q.answer("⚠️ تعذّر التحميل", show_alert=True)

    elif q.data == "qa_buy":
        await q.answer()
        await context.bot.send_invoice(
            chat_id=user.id,
            title="⭐ 5 أسئلة دينية إضافية",
            description=f"أضف {QA_EXTRA_BONUS} أسئلة إضافية لسؤالك الديني اليوم",
            payload=f"qa_extra_{user.id}",
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice(f"{QA_EXTRA_STARS} نجوم", QA_EXTRA_STARS)]
        )

    # ===== التسبيح =====

    elif q.data.startswith("qr_page_"):
        await q.answer("⏳ جاري جلب الصفحة...")
        parts = q.data.split("_")
        s, a = int(parts[2]), int(parts[3])
        # جلب رقم الصفحة من الـ API
        ayah_data = await fetch_ayah_by_ref(s, a)
        if not ayah_data:
            await q.answer("⚠️ لم أتمكن من جلب الصفحة", show_alert=True)
            return
        # الصفحة في API تكون في field "page"
        # نجيب من API مباشرة
        url = f"https://api.alquran.cloud/v1/ayah/{s}:{a}/ar"
        page_num = 1
        try:
            async with __import__('aiohttp').ClientSession() as sess:
                async with sess.get(url) as r:
                    d = await r.json()
                    page_num = d.get("data",{}).get("page", 1)
        except Exception:
            pass
        ayahs = await fetch_quran_page(page_num)
        if not ayahs:
            await q.answer("⚠️ لم أتمكن من جلب الصفحة", show_alert=True)
            return
        msg = build_page_msg(page_num, ayahs)
        # كيبورد الصفحة مع أزرار الصوت
        page_kb = InlineKeyboardMarkup([
            [colored_btn("◀️ السابقة", callback_data=f"qr_pageno_{page_num-1}", style="primary"),
             colored_btn("التالية ▶️", callback_data=f"qr_pageno_{page_num+1}", style="primary")],
            *[
                [colored_btn(f"🎙️ {QURAN_RECITERS[i]['name']}", callback_data=f"qrpa_{page_num}_{i}", style="primary"),
                 colored_btn(f"🎙️ {QURAN_RECITERS[i+1]['name']}", callback_data=f"qrpa_{page_num}_{i+1}", style="primary")]
                if i+1 < len(QURAN_RECITERS) else
                [colored_btn(f"🎙️ {QURAN_RECITERS[i]['name']}", callback_data=f"qrpa_{page_num}_{i}", style="primary")]
                for i in range(0, len(QURAN_RECITERS), 2)
                if QURAN_RECITERS[i].get("page_id")
            ],
            [colored_btn("🔄 بحث جديد", callback_data="qr_new", style="primary")],
        ])
        await q.message.reply_text(msg, parse_mode="Markdown", reply_markup=page_kb)

    elif q.data.startswith("qr_pageno_"):
        await q.answer()
        page_num = int(q.data.split("_")[2])
        if page_num < 1: page_num = 1
        if page_num > 604: page_num = 604
        ayahs = await fetch_quran_page(page_num)
        if not ayahs:
            await q.answer("⚠️ لم أتمكن من جلب الصفحة", show_alert=True)
            return
        msg = build_page_msg(page_num, ayahs)
        page_kb = InlineKeyboardMarkup([
            [colored_btn("◀️ السابقة", callback_data=f"qr_pageno_{page_num-1}", style="primary"),
             colored_btn("التالية ▶️", callback_data=f"qr_pageno_{page_num+1}", style="primary")],
            *[
                [colored_btn(f"🎙️ {QURAN_RECITERS[i]['name']}", callback_data=f"qrpa_{page_num}_{i}", style="primary"),
                 colored_btn(f"🎙️ {QURAN_RECITERS[i+1]['name']}", callback_data=f"qrpa_{page_num}_{i+1}", style="primary")]
                if i+1 < len(QURAN_RECITERS) else
                [colored_btn(f"🎙️ {QURAN_RECITERS[i]['name']}", callback_data=f"qrpa_{page_num}_{i}", style="primary")]
                for i in range(0, len(QURAN_RECITERS), 2)
                if QURAN_RECITERS[i].get("page_id")
            ],
            [colored_btn("🔄 بحث جديد", callback_data="qr_new", style="primary")],
        ])
        try:
            await q.message.edit_text(msg, parse_mode="Markdown", reply_markup=page_kb)
        except Exception:
            await q.message.reply_text(msg, parse_mode="Markdown", reply_markup=page_kb)

    elif q.data.startswith("qrpa_"):
        # qrpa_{page_num}_{reciter_idx} — صوت صفحة كاملة
        await q.answer("⏳ جاري تحضير الصوت...")
        try:
            parts = q.data.split("_")
            page_num = int(parts[1])
            idx = int(parts[2])
        except Exception:
            await q.answer("⚠️ خطأ", show_alert=True)
            return
        if idx >= len(QURAN_RECITERS):
            await q.answer("⚠️ قارئ غير موجود", show_alert=True)
            return
        reciter = QURAN_RECITERS[idx]
        audio_url = get_page_audio_url(page_num, reciter["page_id"])
        try:
            import io as _io
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60)) as session:
                async with session.get(audio_url) as resp:
                    if resp.status == 200:
                        audio_bytes = await resp.read()
                        audio_file = _io.BytesIO(audio_bytes)
                        audio_file.name = f"page{page_num:03d}.mp3"
                        await q.message.reply_audio(
                            audio=audio_file,
                            caption=f"🎙️ {reciter['name']} — الصفحة {page_num}",
                            title=f"الصفحة {page_num}",
                            performer=reciter["name"],
                        )
                    else:
                        await q.answer(f"⚠️ الصوت غير متاح (خطأ {resp.status})", show_alert=True)
        except Exception as e:
            logger.error(f"page audio error: {e}")
            await q.answer("⚠️ تعذّر تحميل الصوت", show_alert=True)

    elif q.data.startswith("qr_listen_") and q.data != "qr_listen_cancel":
        await q.answer()
        parts = q.data.split("_")
        try:
            s, a = int(parts[2]), int(parts[3])
        except Exception:
            await q.answer("⚠️ خطأ", show_alert=True)
            return
        # قارئان فقط
        rows = [
            *[
                [colored_btn(f"🎙️ {QURAN_RECITERS[i]['name']}", callback_data=f"qra_{s}_{a}_{i}", style="primary"),
                 colored_btn(f"🎙️ {QURAN_RECITERS[i+1]['name']}", callback_data=f"qra_{s}_{a}_{i+1}", style="primary")]
                if i+1 < len(QURAN_RECITERS) else
                [colored_btn(f"🎙️ {QURAN_RECITERS[i]['name']}", callback_data=f"qra_{s}_{a}_{i}", style="primary")]
                for i in range(0, len(QURAN_RECITERS), 2)
            ],
            [colored_btn("❌ إلغاء", callback_data="qr_listen_cancel", style="danger")],
        ]
        await q.message.reply_text(
            "🎙️ *اختر القارئ*\n━━━━━━━━━━━━━━━",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(rows)
        )

    elif q.data == "qr_listen_cancel":
        await q.answer()
        try:
            await q.message.delete()
        except Exception:
            pass

    elif q.data.startswith("qra_"):
        # qra_{s}_{a}_{idx} — اختار قارئ لآية، يسأل: آية أو سورة كاملة؟
        await q.answer()
        try:
            parts = q.data.split("_")
            s, a, idx = int(parts[1]), int(parts[2]), int(parts[3])
        except Exception:
            await q.answer("⚠️ خطأ", show_alert=True)
            return
        if idx >= len(QURAN_RECITERS):
            await q.answer("⚠️ قارئ غير موجود", show_alert=True)
            return
        reciter = QURAN_RECITERS[idx]
        surah_num = s
        # خيار: آية واحدة أو سورة كاملة
        kb = InlineKeyboardMarkup([
            [colored_btn("🎵 هذه الآية فقط", callback_data=f"qra1_{s}_{a}_{idx}", style="primary"),
             colored_btn("📖 السورة كاملة", callback_data=f"qras_{s}_{idx}", style="success")],
            [colored_btn("❌ إلغاء", callback_data="qr_listen_cancel", style="danger")],
        ])
        await q.message.reply_text(
            f"🎙️ *{reciter['name']}*\n"
            "━━━━━━━━━━━━━━━\n\n"
            "تريد تسمع:",
            parse_mode="Markdown",
            reply_markup=kb
        )

    elif q.data.startswith("qra1_"):
        # آية واحدة فقط
        await q.answer("⏳ جاري تحضير الصوت...")
        try:
            parts = q.data.split("_")
            s, a, idx = int(parts[1]), int(parts[2]), int(parts[3])
        except Exception:
            await q.answer("⚠️ خطأ", show_alert=True)
            return
        reciter = QURAN_RECITERS[idx]
        audio_url = get_ayah_audio_url(s, a, reciter["id"])
        import io as _io
        # جرب everyayah أولاً ثم cdn.islamic.network احتياطياً
        urls_to_try = [
            audio_url,
            get_ayah_audio_url_cdn(s, a, reciter["name"]),
        ]
        sent = False
        for try_url in urls_to_try:
            try:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=25)) as session:
                    async with session.get(try_url) as resp:
                        if resp.status == 200:
                            audio_bytes = await resp.read()
                            audio_file = _io.BytesIO(audio_bytes)
                            audio_file.name = "ayah.mp3"
                            await q.message.reply_voice(
                                voice=audio_file,
                                caption=f"🎙️ {reciter['name']}"
                            )
                            try:
                                await q.message.delete()
                            except Exception:
                                pass
                            sent = True
                            break
            except Exception as e:
                logger.error(f"ayah audio try {try_url[:40]}: {e}")
        if not sent:
            await q.answer("⚠️ تعذّر تحميل الصوت، حاول لاحقاً", show_alert=True)

    elif q.data.startswith("qras_"):
        # سورة كاملة من mp3quran.net
        await q.answer("⏳ جاري تحضير صوت السورة...")
        try:
            parts = q.data.split("_")
            s, idx = int(parts[1]), int(parts[2])
        except Exception:
            await q.answer("⚠️ خطأ", show_alert=True)
            return
        reciter = QURAN_RECITERS[idx]
        # معرفات mp3quran.net لكل قارئ
        MP3QURAN_IDS = {
            "عبد الباسط عبد الصمد": "1",
            "سعود الشريم":           "6",
            "أبو بكر الشاطري":       "7",
            "ناصر القطامي":          "69",
            "مشاري العفاسي":         "10",
            "ماهر المعيقلي":         "62",
            "علي الحذيفي":           "4",
            "سعد الغامدي":           "9",
            "محمد اللحيدان":         "145",
        }
        surah_name = QURAN_SURAHS_REV.get(s, f"سورة {s}")
        # روابط السور — محققة من mp3quran API v3
        SURAH_URLS = {
            "عبد الباسط عبد الصمد": f"https://server6.mp3quran.net/basit/{s:03d}.mp3",
            "سعود الشريم":          f"https://server7.mp3quran.net/shuraym/{s:03d}.mp3",
            "أبو بكر الشاطري":      f"https://server11.mp3quran.net/shatri/{s:03d}.mp3",
            "ناصر القطامي":         f"https://server6.mp3quran.net/qtm/{s:03d}.mp3",
            "مشاري العفاسي":        f"https://server8.mp3quran.net/afs/{s:03d}.mp3",
            "ماهر المعيقلي":        f"https://server12.mp3quran.net/maher/{s:03d}.mp3",
            "علي الحذيفي":          f"https://server8.mp3quran.net/hthfi/{s:03d}.mp3",
            "سعد الغامدي":          f"https://server7.mp3quran.net/s_gmd/{s:03d}.mp3",
            "محمد اللحيدان":        f"https://server8.mp3quran.net/lhdan/{s:03d}.mp3",
        }
        audio_url = SURAH_URLS.get(reciter["name"])
        if not audio_url:
            await q.answer("⚠️ هذا القارئ لا يدعم السورة الكاملة", show_alert=True)
            return
        try:
            import io as _io
            wait_msg = await q.message.reply_text(f"⏳ جاري تحميل {surah_name}...")
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120)) as session:
                async with session.get(audio_url) as resp:
                    if resp.status == 200:
                        audio_bytes = await resp.read()
                        audio_file = _io.BytesIO(audio_bytes)
                        audio_file.name = f"surah_{s:03d}.mp3"
                        await wait_msg.delete()
                        await q.message.reply_audio(
                            audio=audio_file,
                            caption=f"📖 {surah_name} — 🎙️ {reciter['name']}",
                            title=surah_name,
                            performer=reciter["name"],
                        )
                        try:
                            await q.message.delete()
                        except Exception:
                            pass
                    else:
                        await wait_msg.delete()
                        await q.answer(f"⚠️ الصوت غير متاح ({resp.status})", show_alert=True)
        except Exception as e:
            logger.error(f"surah full audio error: {e}")
            await q.answer("⚠️ تعذّر تحميل السورة، حاول لاحقاً", show_alert=True)

    elif q.data == "qr_new":
        await q.answer()
        context.user_data["quran_search_mode"] = True
        await q.message.reply_text(
            "📖 أرسل كلمة أو رقم السورة:الآية للبحث 👇\n"
            "مثال: `الصبر` أو `2:255` أو `الكهف:10`",
            parse_mode="Markdown"
        )

    elif q.data in ("qr_prev", "qr_next"):
        await q.answer()
        results = context.user_data.get("quran_results", [])
        page = context.user_data.get("quran_page", 0)
        if not results:
            await q.answer("⚠️ انتهت الجلسة، ابحث من جديد", show_alert=True)
            return
        page = page - 1 if q.data == "qr_prev" else page + 1
        page = max(0, min(page, len(results) - 1))
        context.user_data["quran_page"] = page
        context.user_data["quran_tafsir"] = {}
        h = results[page]
        msg = build_ayah_msg(h, page=page, total=len(results))
        kb = build_ayah_keyboard(h, page, len(results))
        try:
            await q.message.edit_text(msg, parse_mode="Markdown", reply_markup=kb)
        except Exception:
            await q.message.reply_text(msg, parse_mode="Markdown", reply_markup=kb)

    elif q.data.startswith("qr_tafsir_"):
        await q.answer("⏳ جاري جلب التفسير...")
        parts = q.data.split("_")
        s, a = int(parts[2]), int(parts[3])
        tafsir = await fetch_tafsir(s, a)
        results = context.user_data.get("quran_results", [])
        page = context.user_data.get("quran_page", 0)
        if not results:
            await q.answer("⚠️ انتهت الجلسة", show_alert=True)
            return
        h = results[page]
        if not tafsir:
            tafsir = "⚠️ التفسير غير متاح لهذه الآية حالياً"
        msg = build_ayah_msg(h, tafsir=tafsir, page=page, total=len(results))
        kb = build_ayah_keyboard(h, page, len(results), show_tafsir=True)
        try:
            await q.message.edit_text(msg, parse_mode="Markdown", reply_markup=kb)
        except Exception:
            await q.message.reply_text(msg, parse_mode="Markdown", reply_markup=kb)

    elif q.data.startswith("qr_hide_tafsir_"):
        await q.answer()
        results = context.user_data.get("quran_results", [])
        page = context.user_data.get("quran_page", 0)
        if not results:
            return
        h = results[page]
        msg = build_ayah_msg(h, page=page, total=len(results))
        kb = build_ayah_keyboard(h, page, len(results), show_tafsir=False)
        try:
            await q.message.edit_text(msg, parse_mode="Markdown", reply_markup=kb)
        except Exception:
            pass

    elif q.data.startswith("qr_ayah_"):
        await q.answer()
        parts = q.data.split("_")
        s, a = int(parts[2]), int(parts[3])
        loading = await q.message.reply_text("⏳ جاري جلب الآية...")
        ayah = await fetch_ayah_by_ref(s, a)
        if not ayah:
            await loading.edit_text("⚠️ الآية غير موجودة")
            return
        # أضف للنتائج
        results = context.user_data.get("quran_results", [])
        # تحقق إذا موجودة
        exists = any(r.get("surah_num") == s and r.get("ayah_num") == a for r in results)
        if not exists:
            results = [ayah]
            context.user_data["quran_results"] = results
            context.user_data["quran_page"] = 0
        page = 0
        context.user_data["quran_tafsir"] = {}
        msg = build_ayah_msg(ayah, page=page, total=len(results))
        kb = build_ayah_keyboard(ayah, page, len(results))
        await loading.delete()
        await q.message.reply_text(msg, parse_mode="Markdown", reply_markup=kb)

    # ===== 🔊 تحويل النص لصوت =====

    elif q.data.startswith("duaa_next_"):
        await q.answer()
        idx = int(q.data.split("_")[2])
        await _send_duaa(q, context, duaa_idx=idx)

    elif q.data == "qudwati_full":
        await q.answer()
        story = context.user_data.get("current_qudwati")
        if not story:
            _base = _dt.date(2025, 1, 1)
            _cur = _dt.datetime.now(AMMAN_TZ).date()
            story = get_qudwati_of_day()
        full_text = (
            f"📖 *{story['name']}*\n"
            f"━━━━━━━━━━━━━━━\n\n"
            f"{story['story']}\n\n"
            f"📚 المصدر: {story['source']}"
        )
        if len(full_text) > 4000:
            full_text = full_text[:4000] + "..."
        await q.message.reply_text(full_text, parse_mode="Markdown")

    elif q.data == "qudwati_reveal":
        await q.answer()
        # جلب الجواب من current_qudwati أو من saved
        story = context.user_data.get("current_qudwati")
        answer = ""
        if story:
            answer = story.get("answer", "")
        if not answer:
            answer = context.user_data.get("qudwati_answer_saved","") or context.user_data.get("qudwati_answer","")
        context.user_data["qudwati_waiting"] = False
        if answer:
            await q.message.reply_text(
                f"✅ *الإجابة الصحيحة:*\n\n{answer}",
                parse_mode="Markdown"
            )
        else:
            # جلب القصة من QUDWATI_STORIES مباشرة
            _base = _dt.date(2025, 1, 1)
            _cur = _dt.datetime.now(AMMAN_TZ).date()
            _story = get_qudwati_of_day()
            await q.message.reply_text(
                f"✅ *الإجابة الصحيحة:*\n\n{_story.get('answer','')}",
                parse_mode="Markdown"
            )

async def show_search_page_from_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    results = context.user_data.get("search_results", [])
    page = context.user_data.get("search_page", 0)
    if not results:
        # حاول استرجاع الجلسة من DB
        if session and session.get("results"):
            results = session["results"]
            page = session["page"]
            context.user_data["search_results"] = results
            context.user_data["search_results_all"] = results
            context.user_data["search_page"] = page
            context.user_data["grade_filter"] = session.get("grade_filter", "all")
            context.user_data["search_id"] = session.get("search_id", "")
        else:
            await update.callback_query.answer("⚠️ انتهت الجلسة، ابحث من جديد.", show_alert=True)
            return

    total_pages = len(results)
    if page >= total_pages:
        page = total_pages - 1
        context.user_data["search_page"] = page

    user = update.effective_user
    h = results[page]
    msg = build_hadith_msg(h, page, total_pages)
    # تحقق إذا الحديث في المفضلة
    favs = get_favorites(user.id) if has_favorites(user.id) else []
    is_fav = any(f["text"] == h["text"] for f in favs)
    cf = context.user_data.get("grade_filter", "all")
    keyboard = build_keyboard(page, total_pages, h["id"], user_id=user.id, is_fav=is_fav, context_filter=cf)

    try:
        await update.callback_query.message.delete()
    except:
        pass
    await update.callback_query.message.reply_text(msg, parse_mode="HTML", reply_markup=keyboard)

async def handle_report_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    report_text = update.message.text.strip()

    hadith_id = context.user_data.get("reporting_hadith_id")
    hadith_text = context.user_data.get("reporting_hadith_text")

    if hadith_id is not None and hadith_text:
        # احفظ نص التقرير وانتظر التأكيد
        context.user_data["pending_report_text"] = report_text
        context.user_data["reporting"] = False  # أوقف الاستقبال مؤقتاً

        confirm_kb = InlineKeyboardMarkup([[
            colored_btn("✅ نعم، أرسل التقرير", callback_data="confirm_report", style="success"),
            colored_btn("❌ لا، إلغاء", callback_data="cancel_report", style="danger"),
        ]])
        await update.message.reply_text(
            f"📝 تقريرك:\n\n{report_text}\n\n"
            "هل تريد إرسال هذا التقرير إلى المطور؟",
            reply_markup=confirm_kb
        )
    else:
        await update.message.reply_text("⚠️ حدث خطأ، يرجى إعادة المحاولة.")
        context.user_data.pop("reporting", None)
        context.user_data.pop("reporting_hadith_id", None)
        context.user_data.pop("reporting_hadith_text", None)

# ==================== التشغيل ====================
# ==================== نظام الاستقرار المتقدم ====================

import signal as _signal
import sys as _sys

def _handle_sigterm(signum, frame):
    """معالج SIGTERM — يُرسل إشعار ويُغلق بشكل نظيف"""
    if BOT_TOKEN and ADMIN_IDS:
        import urllib.request as _req
        import urllib.parse as _up
        msg = "⚠️ بوت راوِي توقف (SIGTERM) — سيُعاد تشغيله تلقائياً"
        for admin_id in ADMIN_IDS:
            try:
                url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
                data = _up.urlencode({"chat_id": admin_id, "text": msg}).encode()
                _req.urlopen(url, data=data, timeout=3)
            except Exception:
                pass
    _sys.exit(0)

def _handle_sigint(signum, frame):
    """معالج SIGINT (Ctrl+C)"""
    logger.info("⛔ إيقاف يدوي...")
    _sys.exit(0)

# تسجيل معالجات الإشارات
try:
    _signal.signal(_signal.SIGTERM, _handle_sigterm)
    _signal.signal(_signal.SIGINT, _handle_sigint)
except Exception:
    pass

def memory_cleanup():
    """تنظيف الذاكرة كل 30 دقيقة"""
    import gc
    import time as _time
    while True:
        _time.sleep(1800)  # 30 دقيقة
        before = __import__('os').getpid()
        gc.collect()
        logger.info("🧹 تنظيف الذاكرة")

    """يسجل في الـ log كل 10 دقائق لإثبات أن البوت حي"""
    import time as _time
    while True:
        _time.sleep(600)
        uptime = int(_time.time() - _start_time)
        h, m = uptime // 3600, (uptime % 3600) // 60
        logger.info(f"💓 Heartbeat — uptime: {h}h {m}m")

    """سيرفر بسيط يمنع Replit من النوم"""
    from http.server import HTTPServer, BaseHTTPRequestHandler
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-type", "text/plain; charset=utf-8")
            self.end_headers()
            uptime = int(__import__('time').time() - _start_time)
            h, m, s = uptime//3600, (uptime%3600)//60, uptime%60
            self.wfile.write(
                f"راوِي Bot is alive ✅ | uptime: {h}h {m}m {s}s".encode("utf-8")
            )
        def log_message(self, *args):
            pass
    server = HTTPServer(("0.0.0.0", 8080), Handler)
    server.serve_forever()

_start_time = __import__('time').time()

def watchdog():
    """يراقب البوت — يُعيد التشغيل ويُخطر الأدمن لو توقف"""
    import time as _time
    import os as _os
    import urllib.request as _req
    import urllib.parse as _up

    _time.sleep(30)
    fails = 0
    while True:
        try:
            _req.urlopen("http://localhost:8080", timeout=10)
            fails = 0
        except Exception as e:
            fails += 1
            logger.warning(f"⚠️ Watchdog: لا استجابة ({fails}/3)")
            if fails >= 3:
                logger.error("🔴 Watchdog: إعادة تشغيل البوت...")
                # أرسل إشعار للأدمن عبر Telegram API مباشرة
                if BOT_TOKEN and ADMIN_IDS:
                    now = __import__('datetime').datetime.now().strftime("%H:%M:%S")
                    msg = f"🔴 بوت راوِي أُعيد تشغيله تلقائياً\n⏰ {now}\nالسبب: عدم الاستجابة 3 مرات"
                    for admin_id in ADMIN_IDS:
                        try:
                            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
                            data = _up.urlencode({"chat_id": admin_id, "text": msg}).encode()
                            _req.urlopen(url, data=data, timeout=5)
                        except Exception:
                            pass
                _os.execv(__import__('sys').executable,
                         [__import__('sys').executable] + __import__('sys').argv)
        _time.sleep(60)

    """يقرع البوت نفسه كل 4 دقائق"""
    import urllib.request as _req
    import time as _time
    _time.sleep(20)
    while True:
        try:
            _req.urlopen("http://localhost:8080", timeout=5)
        except Exception:
            pass
        _time.sleep(30)  # كل 30 ثانية

def external_ping():
    """يقرع الرابط الخارجي كل 4 دقائق"""
    import urllib.request as _req
    import time as _time
    _time.sleep(30)
    while True:
        if REPLIT_URL:
            try:
                _req.urlopen(REPLIT_URL, timeout=10)
            except Exception:
                pass
        _time.sleep(30)  # كل 30 ثانية

async def scheduled_daily_hadith(context):
    """إرسال حديث اليوم لجميع المشتركين"""
    try:
        topics = ["الصبر", "الصلاة", "الإخلاص", "الأخلاق", "الدعاء", "التوبة", "الرحمة", "العلم"]
        import random as _rsch
        topic = _rsch.choice(topics)
        results = await search_dorar_api(topic)
        if not results:
            return
        h = _rsch.choice(results[:5])
        msg = (
            "🌅 *حديث اليوم*\n"
            "━━━━━━━━━━━━━━━\n\n"
            f"📌 {h['text']}\n\n"
            f"👤 الراوي: {h.get('rawi') or 'غير محدد'}\n"
            f"📚 المصدر: {h.get('source') or 'غير محدد'}\n"
            f"⚖️ الدرجة: {h.get('grade') or 'غير محدد'}\n\n"
            "━━━━━━━━━━━━━━━\n"
            f"🤖 {BOT_NAME} | {BOT_USERNAME}"
        )
        subscribers = get_subscribers("daily_hadith")
        success = fail = 0
        for uid in subscribers:
            try:
                kb = InlineKeyboardMarkup([[
                    colored_btn("✅ قرأت", callback_data="streak_read", style="success")
                ]])
                await context.bot.send_message(uid, msg, parse_mode="Markdown", reply_markup=kb)
                success += 1
                await asyncio.sleep(0.05)
            except:
                fail += 1
        logger.info(f"✅ حديث اليوم أُرسل لـ {success} مشترك، فشل: {fail}")
    except Exception as e:
        logger.error(f"scheduled_daily_hadith error: {e}")

async def scheduled_monday_hadith(context):
    """إشعار خاص كل يوم اثنين - حديث مميز"""
    try:
        now = _dt.datetime.now(AMMAN_TZ)
        if now.weekday() != 0:  # 0 = Monday
            return
        results = await search_dorar_api("الاثنين")
        import random as _rmon
        if results:
            h = _rmon.choice(results[:5])
        else:
            return
        msg = (
            "🌟 *حديث يوم الاثنين*\n"
            "━━━━━━━━━━━━━━━\n\n"
            f"📌 {h['text']}\n\n"
            f"👤 الراوي: {h.get('rawi') or 'غير محدد'}\n"
            f"📚 المصدر: {h.get('source') or 'غير محدد'}\n"
            f"⚖️ الدرجة: {h.get('grade') or 'غير محدد'}\n\n"
            "💡 _كان النبي ﷺ يصوم الاثنين ويقول: ذلك يوم وُلدت فيه_\n\n"
            "━━━━━━━━━━━━━━━\n"
            f"🤖 {BOT_NAME} | {BOT_USERNAME}"
        )
        subscribers = get_subscribers("daily_hadith")
        success = 0
        for uid in subscribers:
            try:
                await context.bot.send_message(uid, msg, parse_mode="Markdown")
                success += 1
                await asyncio.sleep(0.05)
            except:
                pass
        logger.info(f"✅ حديث الاثنين أُرسل لـ {success} مشترك")
    except Exception as e:
        logger.error(f"scheduled_monday_hadith error: {e}")

async def startup_notify(app):
    """يُرسل إشعار للأدمن عند بدء تشغيل البوت"""
    now = _dt.datetime.now(AMMAN_TZ).strftime("%Y-%m-%d %H:%M:%S")
    # جلب عدد المستخدمين
    try:
        with sqlite3.connect("bot.db") as _c:
            user_count = _c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    except Exception:
        user_count = "؟"
    msg = (
        "🟢 *بوت راوِي يعمل الآن*\n"
        "━━━━━━━━━━━━━━━\n\n"
        f"⏰ وقت التشغيل: `{now}`\n"
        f"👥 إجمالي المستخدمين: {user_count}\n"
        f"📦 الإصدار: راوِي v5.0\n\n"
        "_إذا وصلك هذا الإشعار فالبوت أُعيد تشغيله_ 🔄"
    )
    for admin_id in ADMIN_IDS:
        try:
            await app.bot.send_message(admin_id, msg, parse_mode="Markdown")
        except Exception:
            pass

async def cache_audio(reciter: str, surah: int, file_id: str):
    """احفظ file_id في الكاش"""
    with sqlite3.connect("bot.db") as c:
        c.execute(
            "INSERT OR REPLACE INTO audio_cache (reciter, surah, file_id) VALUES (?,?,?)",
            (reciter, surah, file_id)
        )

async def upload_surah_to_channel(bot, reciter: str, surah: int) -> str | None:
    """ارفع سورة على القناة واحفظ الـ file_id"""
    # تحقق من الكاش أولاً
    cached = await get_cached_audio(reciter, surah)
    if cached:
        return cached
    
    surah_name = QURAN_SURAHS_REV.get(surah, f"سورة {surah}")
    
    # جرب cdn.islamic.network أولاً
    edition = CDN_EDITIONS.get(reciter, "ar.alafasy")
    url = f"https://cdn.islamic.network/quran/audio-surah/128/{edition}/{surah}.mp3"
    
    try:
        msg = await bot.send_audio(
            chat_id=AUDIO_CHANNEL_ID,
            audio=url,
            title=surah_name,
            performer=reciter,
            caption=f"📖 {surah_name} — {reciter}"
        )
        file_id = msg.audio.file_id
        await cache_audio(reciter, surah, file_id)
        logger.info(f"✅ رُفع: {reciter} — {surah_name}")
        return file_id
    except Exception as e:
        logger.error(f"upload_surah error {reciter} {surah}: {e}")
        return None

# ═══════════════════════════════════════════════════════════════════
# نظام الاختبارات في القنوات - Channel Quiz System
# ═══════════════════════════════════════════════════════════════════

import asyncio
from datetime import datetime, timedelta

# متغيرات عامة لتتبع الاختبارات النشطة
ACTIVE_CHANNEL_QUIZZES = {}  # {channel_id: quiz_data}
CHANNEL_QUIZ_PARTICIPANTS = {}  # {quiz_id: {user_id: {lives, score, answered}}}

# ═══════════════════════════════════════════════════════════════════
# دالة: إنشاء اختبار جديد (للأدمن فقط)
# ═══════════════════════════════════════════════════════════════════

async def cmd_create_channel_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    إنشاء اختبار جديد في القناة
    الأدمن يختار: أسئلة جاهزة أو كتابة يدوية
    """
    user = update.effective_user
    
    # التحقق من أن المستخدم أدمن
    if user.id not in ADMIN_IDS:
        await update.message.reply_text("⚠️ هذا الأمر للمشرفين فقط!")
        return
    
    # الكيبورد: اختيار نوع الأسئلة
    keyboard = [
        [colored_btn("📚 أسئلة جاهزة (من البوت)", callback_data="cq_ready", style="primary")],
        [colored_btn("✍️ كتابة أسئلة يدوية", callback_data="cq_manual", style="secondary")],
        [colored_btn("❌ إلغاء", callback_data="cq_cancel", style="danger")]
    ]
    
    await update.message.reply_text(
        "🎯 *إنشاء اختبار في القناة*\n"
        "━━━━━━━━━━━━━━━\n\n"
        "اختر نوع الأسئلة:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    # حفظ الحالة
    context.user_data["creating_channel_quiz"] = True


# ═══════════════════════════════════════════════════════════════════
# دالة: معالج اختيار الأسئلة
# ═══════════════════════════════════════════════════════════════════

async def handle_quiz_type_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج اختيار نوع الأسئلة"""
    query = update.callback_query
    await query.answer()
    
    data = query.data

    # نظام الاختبارات في القنوات
    if data.startswith("cq_"):
        await handle_quiz_type_selection(update, context)
        return
    
    if data.startswith("cqj_"):
        await handle_quiz_join(update, context)
        return
    
    if data.startswith("cqs_"):
        await handle_quiz_start(update, context)
        return
    
    if data.startswith("cqa_"):
        await handle_quiz_answer(update, context)
        return
    
    
    if data == "cq_ready":
        # أسئلة جاهزة
        await query.edit_message_text(
            "📚 *أسئلة جاهزة*\n"
            "━━━━━━━━━━━━━━━\n\n"
            "كم عدد الأسئلة؟\n"
            "أرسل رقم من 5 إلى 20:",
            parse_mode="Markdown"
        )
        context.user_data["quiz_type"] = "ready"
        context.user_data["waiting_quiz_count"] = True
        
    elif data == "cq_manual":
        # أسئلة يدوية
        await query.edit_message_text(
            "✍️ *كتابة أسئلة يدوية*\n"
            "━━━━━━━━━━━━━━━\n\n"
            "أرسل الأسئلة بهذا الشكل:\n\n"
            "```\n"
            "السؤال: من هو أول من أسلم؟\n"
            "أ. عمر\n"
            "ب. أبو بكر\n"
            "ج. علي\n"
            "د. عثمان\n"
            "الإجابة: ب\n"
            "```\n\n"
            "افصل كل سؤال بـ `---`",
            parse_mode="Markdown"
        )
        context.user_data["quiz_type"] = "manual"
        context.user_data["waiting_manual_questions"] = True
        
    elif data == "cq_cancel":
        await query.edit_message_text("❌ تم الإلغاء")
        context.user_data.clear()


# ═══════════════════════════════════════════════════════════════════
# دالة: نشر الاختبار في القناة
# ═══════════════════════════════════════════════════════════════════

async def publish_channel_quiz(context: ContextTypes.DEFAULT_TYPE, channel_id: str, questions: list, admin_id: int):
    """
    نشر الاختبار في القناة
    """
    quiz_id = f"cq_{int(datetime.now().timestamp())}"
    
    # حفظ بيانات الاختبار
    ACTIVE_CHANNEL_QUIZZES[channel_id] = {
        "quiz_id": quiz_id,
        "questions": questions,
        "current_question": 0,
        "admin_id": admin_id,
        "status": "waiting",  # waiting, active, finished
        "started_at": None,
        "message_id": None
    }
    
    CHANNEL_QUIZ_PARTICIPANTS[quiz_id] = {}
    
    # رسالة الإعلان
    text = (
        "🎯 *اختبار إسلامي جديد!*\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📚 عدد الأسئلة: {len(questions)}\n"
        f"⏱️ مدة السؤال: 15 ثانية\n"
        f"❤️ الأرواح: 3 (3 أخطاء = خروج)\n"
        f"🏆 الفائز: أول من يكمل بدون 3 أخطاء\n\n"
        f"👥 المشاركين: 0\n\n"
        "📝 اضغط *انضم* للمشاركة!"
    )
    
    keyboard = [
        [colored_btn("🎮 انضم للاختبار", callback_data=f"cqj_{quiz_id}", style="success")],
        [colored_btn("▶️ بدء الاختبار (أدمن)", callback_data=f"cqs_{quiz_id}", style="primary")]
    ]
    
    msg = await context.bot.send_message(
        chat_id=channel_id,
        text=text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    ACTIVE_CHANNEL_QUIZZES[channel_id]["message_id"] = msg.message_id


# ═══════════════════════════════════════════════════════════════════
# دالة: الانضمام للاختبار
# ═══════════════════════════════════════════════════════════════════

async def handle_quiz_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج انضمام المستخدم للاختبار"""
    query = update.callback_query
    await query.answer()
    
    quiz_id = query.data.replace("cqj_", "")
    user_id = query.from_user.id
    user_name = query.from_user.first_name or "مشارك"
    
    # التحقق من أن الاختبار موجود
    if quiz_id not in CHANNEL_QUIZ_PARTICIPANTS:
        await query.answer("⚠️ الاختبار غير موجود!", show_alert=True)
        return
    
    # التحقق من أن الاختبار لم يبدأ
    channel_id = query.message.chat.id
    quiz_data = ACTIVE_CHANNEL_QUIZZES.get(str(channel_id))
    
    if quiz_data and quiz_data["status"] != "waiting":
        await query.answer("⚠️ الاختبار بدأ بالفعل!", show_alert=True)
        return
    
    # تسجيل المشارك
    if user_id not in CHANNEL_QUIZ_PARTICIPANTS[quiz_id]:
        CHANNEL_QUIZ_PARTICIPANTS[quiz_id][user_id] = {
            "name": user_name,
            "lives": 3,
            "score": 0,
            "answered": [],
            "active": True
        }
        
        await query.answer(f"✅ تم التسجيل! أهلاً {user_name}", show_alert=True)
        
        # تحديث عدد المشاركين في الرسالة
        count = len(CHANNEL_QUIZ_PARTICIPANTS[quiz_id])
        
        text = query.message.text.split("👥 المشاركين:")[0]
        text += f"👥 المشاركين: {count}\n\n📝 اضغط *انضم* للمشاركة!"
        
        await query.edit_message_text(
            text,
            parse_mode="Markdown",
            reply_markup=query.message.reply_markup
        )
    else:
        await query.answer("✅ أنت مسجل بالفعل!", show_alert=True)


# ═══════════════════════════════════════════════════════════════════
# دالة: بدء الاختبار (أدمن فقط)
# ═══════════════════════════════════════════════════════════════════

async def handle_quiz_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج بدء الاختبار - للأدمن فقط"""
    query = update.callback_query
    
    quiz_id = query.data.replace("cqs_", "")
    user_id = query.from_user.id
    channel_id = str(query.message.chat.id)
    
    quiz_data = ACTIVE_CHANNEL_QUIZZES.get(channel_id)
    
    if not quiz_data:
        await query.answer("⚠️ الاختبار غير موجود!", show_alert=True)
        return
    
    # التحقق من أن المستخدم هو الأدمن
    if user_id != quiz_data["admin_id"]:
        await query.answer("⚠️ هذا الأمر للمشرف فقط!", show_alert=True)
        return
    
    # التحقق من وجود مشاركين
    if len(CHANNEL_QUIZ_PARTICIPANTS[quiz_id]) == 0:
        await query.answer("⚠️ لا يوجد مشاركين!", show_alert=True)
        return
    
    await query.answer("✅ يتم بدء الاختبار...")
    
    # تحديث الحالة
    quiz_data["status"] = "active"
    quiz_data["started_at"] = datetime.now()
    
    # حذف رسالة الإعلان
    await query.message.delete()
    
    # بدء الاختبار
    asyncio.create_task(run_channel_quiz(context, channel_id, quiz_id))


# ═══════════════════════════════════════════════════════════════════
# دالة: تشغيل الاختبار (المحرك الرئيسي)
# ═══════════════════════════════════════════════════════════════════

async def run_channel_quiz(context: ContextTypes.DEFAULT_TYPE, channel_id: str, quiz_id: str):
    """
    محرك الاختبار - يعرض الأسئلة واحد تلو الآخر
    """
    quiz_data = ACTIVE_CHANNEL_QUIZZES[channel_id]
    questions = quiz_data["questions"]
    participants = CHANNEL_QUIZ_PARTICIPANTS[quiz_id]
    
    for idx, q in enumerate(questions):
        quiz_data["current_question"] = idx
        
        # عرض السؤال
        text = (
            f"📝 *السؤال {idx + 1}/{len(questions)}*\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{q['q']}\n\n"
        )
        
        keyboard = []
        labels = ['أ', 'ب', 'ج', 'د']
        
        for i, opt in enumerate(q['options']):
            keyboard.append([
                colored_btn(
                    f"{labels[i]}. {opt}",
                    callback_data=f"cqa_{quiz_id}_{idx}_{i}",
                    style="primary"
                )
            ])
        
        text += f"\n⏱️ الوقت المتبقي: 15 ثانية"
        
        msg = await context.bot.send_message(
            chat_id=channel_id,
            text=text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        quiz_data["current_message_id"] = msg.message_id
        
        # انتظار 15 ثانية أو حتى يجاوب الجميع
        await wait_for_answers(context, channel_id, quiz_id, idx, 15)
        
        # حذف السؤال
        try:
            await context.bot.delete_message(channel_id, msg.message_id)
        except:
            pass
        
        # التحقق من وجود فائز
        winner = check_for_winner(quiz_id, len(questions))
        if winner:
            await announce_winner(context, channel_id, quiz_id, winner)
            return
    
    # انتهى الاختبار - إعلان النتائج
    await announce_results(context, channel_id, quiz_id)


# ═══════════════════════════════════════════════════════════════════
# دالة: انتظار الإجابات
# ═══════════════════════════════════════════════════════════════════

async def wait_for_answers(context, channel_id, quiz_id, question_idx, max_seconds):
    """
    انتظار الإجابات - 15 ثانية أو حتى يجاوب الجميع
    """
    participants = CHANNEL_QUIZ_PARTICIPANTS[quiz_id]
    active_count = len([p for p in participants.values() if p["active"]])
    
    for _ in range(max_seconds):
        await asyncio.sleep(1)
        
        # عدد اللي جاوبوا
        answered_count = len([
            p for p in participants.values() 
            if p["active"] and question_idx in p["answered"]
        ])
        
        # لو كل الناس جاوبوا
        if answered_count >= active_count:
            break


# ═══════════════════════════════════════════════════════════════════
# دالة: معالج الإجابة
# ═══════════════════════════════════════════════════════════════════

async def handle_quiz_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج إجابة المستخدم"""
    query = update.callback_query
    
    parts = query.data.split("_")
    quiz_id = parts[1]
    question_idx = int(parts[2])
    answer_idx = int(parts[3])
    
    user_id = query.from_user.id
    
    # التحقق من أن المستخدم مشارك
    if quiz_id not in CHANNEL_QUIZ_PARTICIPANTS or user_id not in CHANNEL_QUIZ_PARTICIPANTS[quiz_id]:
        await query.answer("⚠️ أنت لست مشاركاً!", show_alert=True)
        return
    
    participant = CHANNEL_QUIZ_PARTICIPANTS[quiz_id][user_id]
    
    # التحقق من أنه لم يجب بعد
    if question_idx in participant["answered"]:
        await query.answer("⚠️ لقد أجبت بالفعل!", show_alert=True)
        return
    
    # التحقق من أنه ما زال نشط
    if not participant["active"]:
        await query.answer("⚠️ لقد خرجت من الاختبار!", show_alert=True)
        return
    
    # الحصول على السؤال
    channel_id = str(query.message.chat.id)
    quiz_data = ACTIVE_CHANNEL_QUIZZES[channel_id]
    question = quiz_data["questions"][question_idx]
    
    # التحقق من الإجابة
    correct_answer = question["answer"]
    user_answer = question["options"][answer_idx]
    
    is_correct = (user_answer == correct_answer)
    
    # تسجيل الإجابة
    participant["answered"].append(question_idx)
    
    if is_correct:
        participant["score"] += 1
        await query.answer("✅ إجابة صحيحة!", show_alert=True)
    else:
        participant["lives"] -= 1
        await query.answer(f"❌ خطأ! الإجابة: {correct_answer}\n❤️ الأرواح: {participant['lives']}", show_alert=True)
        
        # لو خلصت أرواحه
        if participant["lives"] <= 0:
            participant["active"] = False
            await context.bot.send_message(
                chat_id=user_id,
                text=f"💔 للأسف خرجت من الاختبار!\n"
                     f"حصلت على {participant['score']} نقطة."
            )


# ═══════════════════════════════════════════════════════════════════
# دالة: التحقق من وجود فائز
# ═══════════════════════════════════════════════════════════════════

def check_for_winner(quiz_id, total_questions):
    """
    التحقق من وجود فائز
    الفائز: أول من أجاب على كل الأسئلة بدون خسارة 3 أرواح
    """
    participants = CHANNEL_QUIZ_PARTICIPANTS[quiz_id]
    
    for user_id, data in participants.items():
        if data["active"] and data["score"] == total_questions:
            return user_id
    
    return None


# ═══════════════════════════════════════════════════════════════════
# دالة: إعلان الفائز
# ═══════════════════════════════════════════════════════════════════

async def announce_winner(context, channel_id, quiz_id, winner_id):
    """إعلان الفائز في القناة"""
    participant = CHANNEL_QUIZ_PARTICIPANTS[quiz_id][winner_id]
    
    text = (
        "🎉🏆 *تهانينا!* 🏆🎉\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👑 الفائز: {participant['name']}\n"
        f"⭐ النقاط: {participant['score']}\n"
        f"❤️ الأرواح المتبقية: {participant['lives']}\n\n"
        "🎊 مبروك! 🎊"
    )
    
    await context.bot.send_message(
        chat_id=channel_id,
        text=text,
        parse_mode="Markdown"
    )
    
    # حفظ النقاط في قاعدة البيانات
    save_quiz_points(winner_id, participant['score'])
    
    # تنظيف
    cleanup_quiz(channel_id, quiz_id)


# ═══════════════════════════════════════════════════════════════════
# دالة: إعلان النتائج (بدون فائز)
# ═══════════════════════════════════════════════════════════════════

async def announce_results(context, channel_id, quiz_id):
    """إعلان النتائج النهائية"""
    participants = CHANNEL_QUIZ_PARTICIPANTS[quiz_id]
    
    # ترتيب حسب النقاط
    sorted_participants = sorted(
        participants.items(),
        key=lambda x: x[1]["score"],
        reverse=True
    )
    
    text = (
        "📊 *النتائج النهائية*\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
    )
    
    medals = ["🥇", "🥈", "🥉"]
    
    for idx, (user_id, data) in enumerate(sorted_participants[:10]):
        medal = medals[idx] if idx < 3 else f"{idx+1}."
        text += f"{medal} {data['name']} - {data['score']} نقطة\n"
    
    text += f"\n✅ عدد المشاركين: {len(participants)}"
    
    await context.bot.send_message(
        chat_id=channel_id,
        text=text,
        parse_mode="Markdown"
    )
    
    # حفظ النقاط للجميع
    for user_id, data in participants.items():
        if data["score"] > 0:
            save_quiz_points(user_id, data["score"])
    
    # تنظيف
    cleanup_quiz(channel_id, quiz_id)


# ═══════════════════════════════════════════════════════════════════
# دوال مساعدة
# ═══════════════════════════════════════════════════════════════════

def save_quiz_points(user_id, points):
    """حفظ النقاط في قاعدة البيانات"""
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("""
            INSERT INTO user_points (user_id, points, earned_at, source)
            VALUES (?, ?, datetime('now'), 'channel_quiz')
        """, (user_id, points))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Error saving quiz points: {e}")


def cleanup_quiz(channel_id, quiz_id):
    """تنظيف بيانات الاختبار"""
    if channel_id in ACTIVE_CHANNEL_QUIZZES:
        del ACTIVE_CHANNEL_QUIZZES[channel_id]
    
    if quiz_id in CHANNEL_QUIZ_PARTICIPANTS:
        del CHANNEL_QUIZ_PARTICIPANTS[quiz_id]



def main():
    logger.info("🚀 بدء تشغيل بوت راوِي...")
    init_db()
    
    # تشغيل Keep-Alive HTTP server
    from threading import Thread
    Thread(target=run_keepalive_server, daemon=True).start()
    logger.info("🌐 Keep-Alive server started on port 8080")
    
    # بناء التطبيق
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(startup_notify)
        .build()
    )
    
    # تشغيل Heartbeat في الخلفية
    asyncio.create_task(heartbeat(app))
    
    # تشغيل Self-Ping الداخلي
    asyncio.create_task(internal_self_ping())
    logger.info("🔄 Internal self-ping started")
    
    # تشغيل Connection Management
    asyncio.create_task(keep_connections_alive())
    logger.info("🔌 Connection management started")
    
    # تشغيل Activity Simulator
    asyncio.create_task(simulate_activity(app))
    logger.info("🎯 Activity simulator started")
    
    # تشغيل Database Health Monitor
    asyncio.create_task(monitor_database_health())
    logger.info("💚 Database health monitor started")
    logger.info("💓 Heartbeat system started")
    
    # تشغيل Memory Cleanup الدوري
    asyncio.create_task(periodic_cleanup(app))
    logger.info("🧹 Periodic cleanup started")

    # ===== جدولة الإشعارات اليومية =====
    jq = app.job_queue
    if jq:
        # حديث اليوم كل يوم الساعة 7 صباحاً بتوقيت عمّان
        jq.run_daily(
            scheduled_daily_hadith,
            time=_dt.time(7, 0, 0, tzinfo=AMMAN_TZ),
            name="daily_hadith"
        )
        # حديث الاثنين — يُرسل كل يوم الاثنين الساعة 8 صباحاً
        jq.run_daily(
            scheduled_monday_hadith,
            time=_dt.time(8, 0, 0, tzinfo=AMMAN_TZ),
            days=(0,),  # الاثنين
            name="monday_hadith"
        )
        logger.info("✅ الإشعارات اليومية مجدولة")

    # إضافة المعالجات - CommandHandlers أولاً دايماً قبل MessageHandler
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("اختبار_قناة", cmd_create_channel_quiz))
    app.add_handler(CommandHandler("create_channel_quiz", cmd_create_channel_quiz))

    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("version", version_command))
    app.add_handler(CommandHandler("donate", donate_command))

    # Inline Mode — للمشاركة بزر شفاف
    app.add_handler(InlineQueryHandler(handle_inline_query))

    # معالجات الدفع
    app.add_handler(PreCheckoutQueryHandler(precheckout_callback))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback))

    # معالج الأزرار التفاعلية
    app.add_handler(CallbackQueryHandler(handle_callback))

    # معالج الأخطاء العام — يمنع البوت من الموت
    async def global_error_handler(update, context):
        err = context.error
        logger.error(f"خطأ غير متوقع: {err}", exc_info=True)
        log_error(type(err).__name__, str(err), 0, traceback.format_exc())
        # لا نوقف البوت — فقط نسجّل الخطأ
    app.add_error_handler(global_error_handler)

    # معالج الرسائل العام - دايماً آخر شي
    app.add_handler(MessageHandler(filters.ALL, handle_message))

    logger.info("✅ البوت جاهز!")

    app.run_polling(
        drop_pending_updates=True,
        close_loop=False,
        read_timeout=30,
        write_timeout=30,
        connect_timeout=30,
        pool_timeout=30,
    )

# ==================== أوامر Premium ====================

TOPICS = {
    "الصلاة": "الصلاة",
    "🌙 الصيام": "الصيام والصوم",
    "💰 الزكاة": "الزكاة",
    "🤲 الدعاء": "الدعاء",
    "💪 الصبر": "الصبر",
    "🤝 الأخلاق": "الأخلاق والمعاملة",
    "📖 العلم": "العلم والتعلم",
    "❤️ الرحمة": "الرحمة والرفق",
    "🏠 الأسرة": "الأسرة والوالدين",
    "💼 الرزق": "الرزق والعمل",
    "🔄 توبة": "التوبة والاستغفار",
    "🌍 الآخرة": "الآخرة والجنة",
}

async def cmd_challenge_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تحدي في أي وقت - أحاديث ثابتة"""
    user = update.effective_user
    if has_answered_today(user.id):
        await update.message.reply_text("✅ أجبت على تحدي اليوم! تعال غداً 🌙")
        return
    challenge = get_today_challenge()
    if not challenge:
        static = [('إنما الأعمال بالنيات وإنما لكل امرئ ما نوى فمن كانت هجرته إلى الله ورسوله فهجرته إلى الله ورسوله ومن كانت هجرته لدنيا يصيبها أو امرأة ينكحها فهجرته إلى ما هاجر إليه', 'صحيح البخاري', 'صحيح'), ('المسلم من سلم المسلمون من لسانه ويده والمهاجر من هجر ما نهى الله عنه', 'صحيح البخاري', 'صحيح'), ('لا يؤمن أحدكم حتى يحب لأخيه ما يحب لنفسه من الخير', 'صحيح البخاري', 'صحيح'), ('من كان يؤمن بالله واليوم الآخر فليقل خيراً أو ليصمت ومن كان يؤمن بالله واليوم الآخر فليكرم جاره ومن كان يؤمن بالله واليوم الآخر فليكرم ضيفه', 'صحيح البخاري', 'صحيح'), ('الدين النصيحة قلنا لمن قال لله ولكتابه ولرسوله ولأئمة المسلمين وعامتهم', 'صحيح مسلم', 'صحيح'), ('خير الناس أنفعهم للناس', 'صحيح الجامع', 'صحيح'), ('اتق الله حيثما كنت وأتبع السيئة الحسنة تمحها وخالق الناس بخلق حسن', 'صحيح الترمذي', 'صحيح'), ('كل أمتي يدخلون الجنة إلا من أبى قيل ومن يأبى قال من أطاعني دخل الجنة ومن عصاني فقد أبى', 'صحيح البخاري', 'صحيح'), ('بينما رجل يمشي بطريق وجد غصن شوك على الطريق فأخره فشكر الله له فغفر له', 'صحيح البخاري', 'صحيح'), ('لو كان الدنيا تعدل عند الله جناح بعوضة ما سقى كافراً منها شربة ماء', 'صحيح الترمذي', 'صحيح')]
        full_text = _random.choice(static)[0]
        words = full_text.split()
        if len(words) < 6:
            full_text = static[0][0]
            words = full_text.split()
        answer = words[-1].strip(".,،؟!")
        question_text = " ".join(words[:-1]) + " ..."
        save_today_challenge(question_text, answer, full_text)
        challenge = {"text": question_text, "answer": answer, "full": full_text}
    context.user_data["in_challenge"] = True
    context.user_data["challenge_answer"] = challenge["answer"]
    context.user_data["challenge_full"] = challenge["full"]
    await update.message.reply_text(
        "🧩 تحدي اليوم\n"
        "━━━━━━━━━━━━━━━\n\n"
        "أكمل الحديث النبوي:\n\n"
        f"📌 {challenge['text']}\n\n"
        "أرسل الكلمة الناقصة 👇"
    )

async def _send_fc_question(update_or_msg, context: ContextTypes.DEFAULT_TYPE):
    """أرسل سؤال تحدي الصديق"""
    questions = context.user_data.get("fc_questions", [])
    idx = context.user_data.get("fc_index", 0)
    if idx >= len(questions):
        return
    q = questions[idx]
    opts = q["options"]
    kb = InlineKeyboardMarkup([
        [colored_btn(opts[0], callback_data="fc_ans_0", style="primary"),
         colored_btn(opts[1], callback_data="fc_ans_1", style="primary")],
        [colored_btn(opts[2], callback_data="fc_ans_2", style="primary"),
         colored_btn(opts[3], callback_data="fc_ans_3", style="primary")],
    ])
    msg = (
        f"❓ *سؤال {idx+1}/{len(questions)}*\n"
        "━━━━━━━━━━━━━━━\n\n"
        f"*{q['q']}*"
    )
    if hasattr(update_or_msg, 'message') and update_or_msg.message:
        await update_or_msg.message.reply_text(msg, parse_mode="Markdown", reply_markup=kb)
    else:
        await update_or_msg.reply_text(msg, parse_mode="Markdown", reply_markup=kb)

async def cmd_friend_challenge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """زر تحدي صديق من الكيبورد"""
    user = update.effective_user
    import random as _rand_fc
    questions = _rand_fc.sample(DAILY_QUESTIONS, min(10, len(DAILY_QUESTIONS)))
    challenge_id = create_friend_challenge(user.id, user.full_name, questions)
    context.user_data["fc_id"] = challenge_id
    context.user_data["fc_role"] = "creator"
    context.user_data["fc_index"] = 0
    context.user_data["fc_score"] = 0
    context.user_data["fc_questions"] = questions
    link = f"https://t.me/{BOT_USERNAME.lstrip('@')}?start=fc_{challenge_id}"
    share_text = urllib.parse.quote(
        f"⚔️ تحداني {user.full_name} في بوت راوِي الإسلامي!\n\n"
        f"هل تقدر تتفوق عليّ؟ 10 أسئلة إسلامية 🎯\n\n"
        f"👇 اضغط هنا لقبول التحدي:\n{link}"
    )
    tg_share_url = f"https://t.me/share/url?url={link}&text={share_text}"
    kb = InlineKeyboardMarkup([
        [colored_btn("📤 شارك التحدي مع صديق", switch_inline_query=f"challenge_{challenge_id}", style="primary")],
        [colored_btn("🚀 ابدأ الاختبار الآن", callback_data="fc_start", style="success")],
    ])
    await update.message.reply_text(
        "⚔️ *تحدي الصديق*\n"
        "━━━━━━━━━━━━━━━\n\n"
        "📋 10 أسئلة إسلامية\n"
        "⭐ كل إجابة صحيحة = نقطة\n\n"
        "1️⃣ شارك الرابط مع صديقك\n"
        "2️⃣ ابدأ الاختبار أنت أيضاً\n"
        "3️⃣ تقارن النتيجة في النهاية 🏆",
        parse_mode="Markdown",
        reply_markup=kb
    )

# ==================== الباحث القرآني ====================

QURAN_SURAHS = {
    "الفاتحة":1,"البقرة":2,"آل عمران":3,"النساء":4,"المائدة":5,
    "الأنعام":6,"الأعراف":7,"الأنفال":8,"التوبة":9,"يونس":10,
    "هود":11,"يوسف":12,"الرعد":13,"إبراهيم":14,"الحجر":15,
    "النحل":16,"الإسراء":17,"الكهف":18,"مريم":19,"طه":20,
    "الأنبياء":21,"الحج":22,"المؤمنون":23,"النور":24,"الفرقان":25,
    "الشعراء":26,"النمل":27,"القصص":28,"العنكبوت":29,"الروم":30,
    "لقمان":31,"السجدة":32,"الأحزاب":33,"سبأ":34,"فاطر":35,
    "يس":36,"الصافات":37,"ص":38,"الزمر":39,"غافر":40,
    "فصلت":41,"الشورى":42,"الزخرف":43,"الدخان":44,"الجاثية":45,
    "الأحقاف":46,"محمد":47,"الفتح":48,"الحجرات":49,"ق":50,
    "الذاريات":51,"الطور":52,"النجم":53,"القمر":54,"الرحمن":55,
    "الواقعة":56,"الحديد":57,"المجادلة":58,"الحشر":59,"الممتحنة":60,
    "الصف":61,"الجمعة":62,"المنافقون":63,"التغابن":64,"الطلاق":65,
    "التحريم":66,"الملك":67,"القلم":68,"الحاقة":69,"المعارج":70,
    "نوح":71,"الجن":72,"المزمل":73,"المدثر":74,"القيامة":75,
    "الإنسان":76,"المرسلات":77,"النبأ":78,"النازعات":79,"عبس":80,
    "التكوير":81,"الانفطار":82,"المطففين":83,"الانشقاق":84,"البروج":85,
    "الطارق":86,"الأعلى":87,"الغاشية":88,"الفجر":89,"البلد":90,
    "الشمس":91,"الليل":92,"الضحى":93,"الشرح":94,"التين":95,
    "العلق":96,"القدر":97,"البينة":98,"الزلزلة":99,"العاديات":100,
    "القارعة":101,"التكاثر":102,"العصر":103,"الهمزة":104,"الفيل":105,
    "قريش":106,"الماعون":107,"الكوثر":108,"الكافرون":109,"النصر":110,
    "المسد":111,"الإخلاص":112,"الفلق":113,"الناس":114,
}

# عكس القاموس: رقم السورة → اسم السورة
QURAN_SURAHS_REV = {v: k for k, v in QURAN_SURAHS.items()}

# ==================== قراء القرآن الكريم ====================
# المصدر: everyayah.com — CDN مجاني بدون API key
# الصيغة: https://everyayah.com/data/{folder}/SSSAAA.mp3
# SSS = رقم السورة 3 أرقام، AAA = رقم الآية 3 أرقام

QURAN_RECITERS = [
    # قراء مشهورون - جودة عالية 128kbps و 192kbps
    # مرتبون حسب الشهرة والجودة
    
    # الأكثر شهرة - جودة عالية
    {"id": "Alafasy_128kbps",               "page_id": "Alafasy_128kbps",              "name": "مشاري العفاسي"},
    {"id": "Abdul_Basit_Murattal_192kbps",  "page_id": "Abdul_Basit_Murattal_192kbps","name": "عبد الباسط عبد الصمد"},
    {"id": "Abdurrahmaan_As-Sudais_192kbps","page_id": "Abdurrahmaan_As-Sudais_192kbps","name": "عبد الرحمن السديس"},
    {"id": "Maher_AlMuaiqly_128kbps",       "page_id": "Maher_AlMuaiqly_128kbps",     "name": "ماهر المعيقلي"},
    
    # قراء الحرم - صوت واضح
    {"id": "Saood_ash-Shuraym_128kbps",     "page_id": "Saood_ash-Shuraym_128kbps",   "name": "سعود الشريم"},
    {"id": "Hudhaify_128kbps",              "page_id": "Hudhaify_128kbps",            "name": "علي الحذيفي"},
    {"id": "Yasser_Ad-Dussary_128kbps",     "page_id": "Yasser_Ad-Dussary_128kbps",   "name": "ياسر الدوسري"},
    
    # أصوات مميزة ومشهورة
    {"id": "Abu_Bakr_Ash-Shaatree_128kbps", "page_id": "Abu_Bakr_Ash-Shaatree_128kbps","name": "أبو بكر الشاطري"},
    {"id": "Ahmed_ibn_Ali_al-Ajamy_128kbps","page_id": "Ahmed_ibn_Ali_al-Ajamy_128kbps","name": "أحمد العجمي"},
    {"id": "Ghamadi_40kbps",                "page_id": "Ghamadi_40kbps",              "name": "سعد الغامدي"},
    {"id": "Nasser_Alqatami_128kbps",       "page_id": "Nasser_Alqatami_128kbps",     "name": "ناصر القطامي"},
    {"id": "Muhammad_Jibreel_128kbps",      "page_id": "Muhammad_Jibreel_128kbps",    "name": "محمد جبريل"},
    {"id": "Omar_Aldayatin_128kbps",        "page_id": "Omar_Aldayatin_128kbps",      "name": "عمر بن ضياء الدين"},
]

# ربط اسم القارئ بـ edition في cdn.islamic.network
RECITER_EDITIONS = {
    "مشاري العفاسي":        "ar.alafasy",
    "عبد الباسط عبد الصمد": "ar.abdulbasitmurattal",
    "عبد الرحمن السديس":    "ar.abdurrahmaansudais",
    "ماهر المعيقلي":        "ar.mahermuaiqly",
    "سعود الشريم":          "ar.saoodshuraym",
    "علي الحذيفي":          "ar.hudhaify",
    "ياسر الدوسري":         "ar.yasserdossary",
    "أبو بكر الشاطري":      "ar.shaatree",
    "أحمد العجمي":          "ar.ahmedajamy",
    "سعد الغامدي":          "ar.alghamdi",
    "ناصر القطامي":         "ar.alqatami",
    "محمد جبريل":           "ar.muhammadjibril",
    "عمر بن ضياء الدين":    "ar.omardayatin",
}

def get_ayah_audio_url(surah: int, ayah: int, reciter_id: str) -> str:
    """رابط صوت آية — يحاول everyayah أولاً"""
    return f"https://everyayah.com/data/{reciter_id}/{surah:03d}{ayah:03d}.mp3"

def get_ayah_audio_url_cdn(surah: int, ayah: int, reciter_name: str) -> str:
    """رابط صوت آية من cdn.islamic.network — احتياطي مجاني"""
    edition = RECITER_EDITIONS.get(reciter_name, "ar.alafasy")
    # رقم الآية المطلق
    return f"https://cdn.islamic.network/quran/audio/128/{edition}/{surah}:{ayah}.mp3"

def get_page_audio_url(page_num: int, page_id: str) -> str:
    """رابط صوت صفحة كاملة من everyayah.com — PageNNN.mp3"""
    return f"https://everyayah.com/data/{page_id}/PageMp3s/Page{page_num:03d}.mp3"

async def fetch_quran_search(query: str) -> list:
    """
    بحث محسّن في القرآن - يدعم عدة صيغ:
    1. نص الآية فقط
    2. نص الآية مع السورة والرقم
    3. سورة:آية (مثل: محمد:7)
    """
    try:
        # تنظيف النص من علامات الآيات والزخرفة
        clean_query = query.strip()
        clean_query = clean_query.replace('﴿', '').replace('﴾', '')
        clean_query = clean_query.replace('﴾', '').replace('﴿', '')
        clean_query = clean_query.strip()
        
        # فحص إذا في صيغة "سورة:آية" أو "— سورة X، الآية Y"
        surah_name = None
        ayah_number = None
        
        # نمط: "— سورة محمد، الآية 7"
        pattern1 = r'—\s*سورة\s+(\w+)،?\s*الآية\s+(\d+)'
        match1 = re.search(pattern1, clean_query)
        if match1:
            surah_name = match1.group(1)
            ayah_number = int(match1.group(2))
            # حذف هذا الجزء من النص
            clean_query = re.sub(pattern1, '', clean_query).strip()
        
        # نمط: "محمد:7" أو "محمد : 7"
        pattern2 = r'(\w+)\s*:\s*(\d+)'
        match2 = re.search(pattern2, clean_query)
        if match2 and not match1:
            surah_name = match2.group(1)
            ayah_number = int(match2.group(2))
            # استخدم هذا للبحث المباشر
            clean_query = ""
        
        results = []
        
        # إذا عندنا سورة ورقم، ابحث مباشرة
        if surah_name and ayah_number:
            # البحث في القرآن بالسورة والرقم
            url = f"https://api.alquran.cloud/v1/ayah/{surah_name}:{ayah_number}/ar.alafasy"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get('code') == 200:
                            ayah_data = data['data']
                            results.append({
                                'text': ayah_data['text'],
                                'surah': ayah_data['surah']['name'],
                                'number': ayah_data['numberInSurah'],
                                'surah_number': ayah_data['surah']['number']
                            })
                            return results
        
        # بحث عادي في النص
        if clean_query:
            # استخدام API بحث القرآن
            search_url = f"https://api.alquran.cloud/v1/search/{urllib.parse.quote(clean_query)}/all/ar"
            async with aiohttp.ClientSession() as session:
                async with session.get(search_url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get('code') == 200 and 'matches' in data['data']:
                            for match in data['data']['matches'][:10]:
                                results.append({
                                    'text': match['text'],
                                    'surah': match['surah']['name'],
                                    'number': match['numberInSurah'],
                                    'surah_number': match['surah']['number']
                                })
        
        return results
        
    except Exception as e:
        logger.error(f"Error in fetch_quran_search: {e}")
        return []

async def cmd_quran_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج باحث القرآن"""
    await update.message.reply_text(
        "📖 **باحث القرآن الكريم**\n"
        "━━━━━━━━━━━━━━━\n\n"
        "🔍 ابحث في القرآن بعدة طرق:\n\n"
        "**1️⃣ نص الآية:**\n"
        "`﴿قُلْ هُوَ اللَّهُ أَحَدٌ﴾`\n\n"
        "**2️⃣ سورة:آية:**\n"
        "`الإخلاص:1`\n"
        "`112:1`\n\n"
        "**3️⃣ كلمة أو عبارة:**\n"
        "`التوكل`\n"
        "`يا أيها الذين آمنوا`\n\n"
        "📝 _أرسل بحثك الآن..._\n\n"
        "💡 للخروج: اضغط 🔙 خروج من الباحث",
        parse_mode="Markdown",
        reply_markup=search_kb("قرآن")
    )
    # تفعيل وضع البحث
    context.user_data["quran_search_mode"] = True


async def fetch_quran_page(page_num: int) -> list:
    """جلب صفحة كاملة من القرآن — quran.foundation API"""
    if page_num < 1: page_num = 1
    if page_num > 604: page_num = 604

    # quran.foundation: verses by page number مع نص عثماني
    url = f"https://api.quran.com/api/v4/verses/by_page/{page_num}?fields=text_uthmani,verse_key&per_page=50"
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
                verses = data.get("verses", [])
                results = []
                for v in verses:
                    key = v.get("verse_key", "1:1")
                    parts = key.split(":")
                    s_num = int(parts[0]) if len(parts) == 2 else 1
                    a_num = int(parts[1]) if len(parts) == 2 else 1
                    # اسم السورة
                    s_name = QURAN_SURAHS_REV.get(s_num, f"سورة {s_num}")
                    results.append({
                        "text": v.get("text_uthmani", ""),
                        "surah_name": s_name,
                        "surah_num": s_num,
                        "ayah_num": a_num,
                        "ref": f"{s_name}:{a_num}",
                        "page": page_num,
                    })
                return results
    except Exception as e:
        logger.error(f"fetch_quran_page error: {e}")

    # احتياطي: alquran.cloud
    try:
        url2 = f"https://api.alquran.cloud/v1/page/{page_num}/ar"
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
            async with session.get(url2, headers={"User-Agent": "Mozilla/5.0"}) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
                if data.get("status") != "OK":
                    return []
                ayahs = data.get("data", {}).get("ayahs", [])
                return [{
                    "text": a.get("text",""),
                    "surah_name": a.get("surah",{}).get("name",""),
                    "surah_num": a.get("surah",{}).get("number",0),
                    "ayah_num": a.get("numberInSurah",0),
                    "ref": f"{a.get('surah',{}).get('name','')}:{a.get('numberInSurah','')}",
                    "page": page_num,
                } for a in ayahs]
    except Exception as e:
        logger.error(f"fetch_quran_page fallback error: {e}")
        return []

def build_page_msg(page_num: int, ayahs: list) -> str:
    """بناء رسالة صفحة قرآنية مع أرقام الآيات وفصل السور"""
    if not ayahs:
        return "⚠️ لا توجد آيات"

    surahs = list(dict.fromkeys(a["surah_name"] for a in ayahs))
    surahs_str = " | ".join(surahs)

    # بناء النص مع رقم كل آية وفصل السور
    lines = []
    current_surah = None
    for a in ayahs:
        # لو بدأت سورة جديدة
        if a["surah_name"] != current_surah:
            current_surah = a["surah_name"]
            if lines:
                lines.append("")  # سطر فاصل
            lines.append(f"── *{current_surah}* ──")
        # الآية مع رقمها
        num = a.get('ayah_num', '')
        lines.append(f"{a['text']} ﴿{num}﴾")

    full_text = "\n".join(lines)
    # قصّر لو تجاوز حد تيليغرام
    if len(full_text) > 3800:
        full_text = full_text[:3800] + "\n..."

    msg = (
        f"📖 *الصفحة {page_num}/604*\n"
        f"━━━━━━━━━━━━━━━\n"
        f"📚 {surahs_str}\n\n"
        f"{full_text}"
    )
    return msg

async def fetch_tafsir(surah: int, ayah: int) -> str:
    """
    جلب تفسير ابن كثير بالعربي.
    المصدر: quran.com API — id=16 (ar-tafsir-ibn-kathir)
    الاحتياطي: التفسير الميسر — id=16 التفسير الميسر
    """
    import re as _re

    def _clean(text: str) -> str:
        text = _re.sub(r'<[^>]+>', '', text)
        text = _re.sub(r'&amp;', '&', text)
        text = _re.sub(r'&lt;', '<', text)
        text = _re.sub(r'&gt;', '>', text)
        text = _re.sub(r'&[a-z]+;', ' ', text)
        text = _re.sub(r'\s+', ' ', text).strip()
        return text

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
    }

    # ===== ابن كثير عربي — quran.com id=169 =====
    try:
        # id=14 = ابن كثير عربي | id=169 = ابن كثير انجليزي
        url = f"https://api.quran.com/api/v4/tafsirs/14/by_ayah/{surah}:{ayah}"
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=12)) as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    text = data.get("tafsir", {}).get("text", "")
                    if text and len(text) > 20:
                        return _clean(text)
    except Exception as e:
        logger.error(f"tafsir 169 error: {e}")

    # ===== الاحتياطي: tafsir_api — ابن كثير id=2 =====
    try:
        url2 = f"https://tafsir.app/ibn-kathir/{surah}/{ayah}"
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.get(url2, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    text = data.get("text", "") or data.get("content", "")
                    if text and len(text) > 20:
                        return _clean(text)
    except Exception as e:
        logger.error(f"tafsir.app error: {e}")

    # ===== الاحتياطي الثاني: التفسير الميسر =====
    try:
        url3 = f"https://api.quran-tafseer.com/tafseer/1/{surah}/{ayah}"
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.get(url3, headers={"User-Agent": "Mozilla/5.0"}) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    text = data.get("text", "")
                    if text:
                        return "[التفسير الميسر]: " + _clean(text)
    except Exception as e:
        logger.error(f"muyassar error: {e}")

    return ""

async def fetch_ayah_by_ref(surah: int, ayah: int) -> dict:
    """جلب آية بالرقم مع نصها"""
    url = f"https://api.alquran.cloud/v1/ayah/{surah}:{ayah}/ar"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status != 200:
                    return {}
                data = await resp.json()
                if data.get("status") != "OK":
                    return {}
                d = data.get("data", {})
                return {
                    "text": d.get("text", ""),
                    "surah_name": d.get("surah", {}).get("name", ""),
                    "surah_num": d.get("surah", {}).get("number", 0),
                    "ayah_num": d.get("numberInSurah", 0),
                    "ref": f"{d.get('surah', {}).get('name', '')}:{d.get('numberInSurah', '')}",
                }
    except Exception as e:
        logger.error(f"fetch_ayah error: {e}")
        return {}

def build_ayah_msg(ayah: dict, tafsir: str = "", page: int = 0, total: int = 1) -> str:
    """بناء رسالة الآية"""
    ref = ayah.get("ref", "")
    msg = (
        f"📖 *نتيجة ({page+1}/{total})*\n"
        "━━━━━━━━━━━━━━━\n\n"
        f"🌿 *{ayah['text']}*\n\n"
        f"📚 السورة: *{ayah['surah_name']}* — الآية: *{ayah['ayah_num']}*\n"
    )
    if tafsir:
        import re as _re2
        t = _re2.sub(r'<[^>]+>', '', tafsir).strip()
        # تيليغرام يسمح بـ 4096 حرف، نتحكم بالطول
        max_t = 3000 - len(msg)
        if len(t) > max_t:
            t = t[:max_t] + "..."
        msg += f"\n💡 *التفسير (ابن كثير):*\n{t}\n"
    return msg

def build_ayah_keyboard(ayah: dict, page: int, total: int,
                        show_tafsir: bool = False) -> InlineKeyboardMarkup:
    s = ayah.get("surah_num", 0)
    a = ayah.get("ayah_num", 0)
    rows = []
    # تنقل
    nav = []
    if page > 0:
        nav.append(colored_btn("⬅️ السابق", callback_data="qr_prev", style="primary"))
    if page < total - 1:
        nav.append(colored_btn("التالي ➡️", callback_data="qr_next", style="primary"))
    if nav:
        rows.append(nav)
    # تفسير / إخفاء تفسير
    if not show_tafsir:
        rows.append([colored_btn("💡 عرض التفسير", callback_data=f"qr_tafsir_{s}_{a}", style="success")])
    else:
        rows.append([colored_btn("🔼 إخفاء التفسير", callback_data=f"qr_hide_tafsir_{s}_{a}", style="primary")])
    # آية سابقة / تالية
    rows.append([
        colored_btn("◀️ الآية السابقة", callback_data=f"qr_ayah_{s}_{max(1,a-1)}", style="primary"),
        colored_btn("الآية التالية ▶️", callback_data=f"qr_ayah_{s}_{a+1}", style="primary"),
    ])
    # زر الاستماع — يفتح قائمة القراء
    rows.append([
        colored_btn("🎙️ استمع للآية", callback_data=f"qr_listen_{s}_{a}", style="primary"),
        colored_btn("📄 الصفحة كاملة", callback_data=f"qr_page_{s}_{a}", style="primary"),
    ])
    rows.append([
        colored_btn("📤 شارك الآية", switch_inline_query=f"ayah_{s}_{a}", style="primary"),
        colored_btn("🔄 بحث جديد", callback_data="qr_new", style="primary"),
    ])
    return InlineKeyboardMarkup(rows)

def get_qa_usage(user_id: int) -> dict:
    """جلب استخدام اليوم — المستخدم الجديد يبدأ بـ 0"""
    today = _dt.datetime.now(AMMAN_TZ).strftime("%Y-%m-%d")
    try:
        with sqlite3.connect("bot.db") as conn:
            row = conn.execute(
                "SELECT count, extra_questions FROM qa_usage WHERE user_id=? AND date=?",
                (user_id, today)
            ).fetchone()
        if row:
            return {"count": row[0], "extra": row[1], "date": today}
        # مستخدم جديد أو يوم جديد — يبدأ من الصفر
        return {"count": 0, "extra": 0, "date": today}
    except Exception:
        return {"count": 0, "extra": 0, "date": today}

def increment_qa_usage(user_id: int):
    """زيادة عداد الأسئلة"""
    today = _dt.datetime.now(AMMAN_TZ).strftime("%Y-%m-%d")
    with sqlite3.connect("bot.db") as conn:
        conn.execute(
            "INSERT INTO qa_usage (user_id, date, count) VALUES (?,?,1) "
            "ON CONFLICT(user_id, date) DO UPDATE SET count=count+1",
            (user_id, today)
        )

def add_qa_extra(user_id: int, bonus: int):
    """إضافة أسئلة إضافية بعد الدفع"""
    today = _dt.datetime.now(AMMAN_TZ).strftime("%Y-%m-%d")
    with sqlite3.connect("bot.db") as conn:
        conn.execute(
            "INSERT INTO qa_usage (user_id, date, count, extra_questions) VALUES (?,?,0,?) "
            "ON CONFLICT(user_id, date) DO UPDATE SET extra_questions=extra_questions+?",
            (user_id, today, bonus, bonus)
        )

def decrement_qa_usage(user_id: int):
    """إلغاء خصم سؤال لو فشل الـ API"""
    today = _dt.datetime.now(AMMAN_TZ).strftime("%Y-%m-%d")
    with sqlite3.connect("bot.db") as conn:
        conn.execute(
            "UPDATE qa_usage SET count=MAX(0,count-1) WHERE user_id=? AND date=?",
            (user_id, today)
        )

def can_ask_question(user_id: int) -> tuple:
    """
    هل يمكن للمستخدم أن يسأل؟
    returns: (can_ask: bool, remaining: int, is_free: bool)
    """
    usage = get_qa_usage(user_id)
    used = usage["count"]
    extra = usage["extra"]
    total_allowed = QA_FREE_DAILY + extra
    remaining = max(0, total_allowed - used)
    return remaining > 0, remaining, used < QA_FREE_DAILY

# ==================== تحويل النص لصوت ====================

async def get_quran_audio(surah: int, ayah: int, reciter_name: str = "مشاري العفاسي") -> bytes | None:
    """
    جلب صوت آية مباشرة من CDN مجاني — بديل AI للقرآن.
    cdn.islamic.network — مجاني بدون مفتاح.
    """
    edition = RECITER_EDITIONS.get(reciter_name, "ar.alafasy")
    urls = [
        f"https://cdn.islamic.network/quran/audio/128/{edition}/{surah}:{ayah}.mp3",
        f"https://everyayah.com/data/Alafasy_128kbps/{surah:03d}{ayah:03d}.mp3",
    ]
    for url in urls:
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        return await resp.read()
        except Exception:
            pass
    return None

async def text_to_voice(text: str) -> bytes | None:
    """
    تحويل النص لصوت.
    يحاول ElevenLabs أولاً، ثم gTTS احتياطياً.
    """
    if not text:
        return None

    # ElevenLabs أولاً
    audio = None  # TTS disabled
    if audio:
        return audio

    # gTTS احتياطي
    logger.info("TTS: ElevenLabs فشل أو غير مفعّل — جاري استخدام gTTS")
    audio = await asyncio.get_event_loop().run_in_executor(
        None, lambda: None  # TTS disabled
    )
    # run_in_executor مع async — نستخدم ThreadPoolExecutor
    if audio is None:
        try:
            import io
            from gtts import gTTS
            import concurrent.futures
            def _sync_gtts():
                tts = gTTS(text=text[:1500], lang='ar', slow=False)
                buf = io.BytesIO()
                tts.write_to_fp(buf)
                buf.seek(0)
                return buf.read()
            loop = asyncio.get_event_loop()
            with concurrent.futures.ThreadPoolExecutor() as pool:
                audio = await loop.run_in_executor(pool, _sync_gtts)
        except Exception as e:
            logger.error(f"gTTS fallback error: {e}")
            return None
    return audio

async def send_voice_reply(update_or_msg, text: str, caption: str = "") -> bool:
    """إرسال رد صوتي"""
    import io
    audio = await text_to_voice(text)
    if not audio:
        return False
    audio_file = io.BytesIO(audio)
    audio_file.name = "voice.mp3"
    msg = update_or_msg.message if hasattr(update_or_msg, 'message') else update_or_msg
    try:
        await msg.reply_voice(voice=audio_file, caption=caption or None)
        return True
    except Exception as e:
        logger.error(f"send_voice error: {e}")
        return False

async def call_gemini(prompt: str) -> str:
    """استدعاء Gemini 3.1 Flash-Lite Preview API"""
    if not GEMINI_API_KEY:
        return "⚠️ لم يتم تكوين مفتاح Gemini API. أضف GEMINI_API_KEY في متغيرات البيئة."
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite-preview:generateContent?key={GEMINI_API_KEY}"
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": 600, "temperature": 0.3}
    }
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as session:
            async with session.post(url, json=body) as resp:
                if resp.status != 200:
                    err = await resp.text()
                    logger.error(f"Gemini API error {resp.status}: {err[:200]}")
                    return "⚠️ لم أتمكن من الإجابة الآن، حاول مرة أخرى."
                data = await resp.json()
                return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception as e:
        logger.error(f"Gemini error: {e}")
        return "⚠️ حدث خطأ، حاول مرة أخرى."

# ===== التسبيح =====
TASBIH_OPTIONS = [
    ("سُبْحَانَ اللهِ", "سبحان الله"),
    ("الحَمْدُ للهِ", "الحمد لله"),
    ("اللهُ أَكْبَرُ", "الله أكبر"),
    ("لَا إِلَهَ إِلَّا اللهُ", "لا إله إلا الله"),
    ("سُبْحَانَ اللهِ وَبِحَمْدِهِ", "سبحان الله وبحمده"),
    ("أَسْتَغْفِرُ اللهَ", "أستغفر الله"),
]

async def _send_duaa(target, context, duaa_idx: int = -1):
    """إرسال دعاء — يقبل message أو callback query"""
    if duaa_idx < 0:
        day_num = _dt.datetime.now(AMMAN_TZ).timetuple().tm_yday
        duaa_idx = day_num % len(DAILY_DUAA)
    d = DAILY_DUAA[duaa_idx]
    context.application.bot_data["duaa_today"] = d
    context.application.bot_data["duaa_idx"] = duaa_idx
    next_idx = (duaa_idx + 1) % len(DAILY_DUAA)
    msg_text = (
        "🤲 *دعاء اليوم*\n"
        "━━━━━━━━━━━━━━━\n\n"
        f"*{d['text']}*\n\n"
        f"📚 المصدر: {d['source']}\n"
        f"💡 المعنى: {d['meaning']}"
    )
    kb = InlineKeyboardMarkup([
        [colored_btn("🔄 دعاء آخر", callback_data=f"duaa_next_{next_idx}", style="primary"),
         colored_btn("📤 شارك", switch_inline_query="duaa_today", style="primary")],

    ])
    if hasattr(target, 'reply_text'):
        await target.reply_text(msg_text, parse_mode="Markdown", reply_markup=kb)
    else:
        try:
            await target.message.edit_text(msg_text, parse_mode="Markdown", reply_markup=kb)
        except Exception:
            await target.message.reply_text(msg_text, parse_mode="Markdown", reply_markup=kb)

async def cmd_duaa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _send_duaa(update.message, context)

async def cmd_quiz_new(update, context: ContextTypes.DEFAULT_TYPE):
    """يعمل مع Update أو CallbackQuery"""
    from telegram import CallbackQuery as _CQ
    if isinstance(update, _CQ):
        msg_obj = update.message
        user = update.from_user
    else:
        msg_obj = update.message
        user = update.effective_user

    import random as _rand
    today = _dt.datetime.now(AMMAN_TZ).strftime("%Y-%m-%d")
    with sqlite3.connect("bot.db") as _c:
        row = _c.execute(
            "SELECT quiz_score FROM quiz_sessions WHERE user_id=? AND quiz_date=? AND quiz_index=10",
            (user.id, today)
        ).fetchone()
    if row:
        await msg_obj.reply_text(
            f"✅ أكملت اختبار اليوم!\nنتيجتك: {row[0]}/10 ⭐\n\nتعال غداً لاختبار جديد 🌙"
        )
        return
    questions = _rand.sample(DAILY_QUESTIONS, min(10, len(DAILY_QUESTIONS)))
    context.user_data["quiz_questions"] = questions
    context.user_data["quiz_index"] = 0
    context.user_data["quiz_score"] = 0
    context.user_data["quiz_date"] = today
    save_quiz_session(user.id, questions, 0, 0, today)
    await msg_obj.reply_text(
        "🎯 *اختبر معلوماتك*\n━━━━━━━━━━━━━━━\n\n"
        "10 أسئلة متنوعة في الفقه والتفسير والسيرة\n"
        "ستظهر النتيجة الكاملة في النهاية 📊\n\n"
        "هيا نبدأ! 💪",
        parse_mode="Markdown"
    )
    await send_quiz_question(msg_obj, context, questions[0], 1)

async def handle_inline_query(update, context):
    """معالج Inline Query الموحد — يدعم مشاركة البوت، الحديث، القدوة، التحدي"""
    query = update.inline_query
    if query is None:
        return

    q_data = query.query.strip()
    bot_link = f"https://t.me/{BOT_USERNAME.lstrip('@')}"
    results = []

    # ===== تحدي الصديق =====
    # ===== مشاركة آية قرآنية =====
    if q_data.startswith("ayah_"):
        parts = q_data.split("_")
        if len(parts) >= 3:
            try:
                s, a = int(parts[1]), int(parts[2])
                ayah = await fetch_ayah_by_ref(s, a)
                if ayah:
                    msg_text = (
                        f"🌿 *{ayah['text']}*\n\n"
                        f"📚 {ayah['surah_name']} — الآية {ayah['ayah_num']}\n\n"
                        "_من بوت راوِي للقرآن والأحاديث النبوية_ 🌙"
                    )
                    kb = InlineKeyboardMarkup([[
                        colored_btn("📲 افتح راوِي", url=bot_link, style="primary")
                    ]])
                    results.append(InlineQueryResultArticle(
                        id="ayah_share",
                        title=f"📖 {ayah['surah_name']}:{ayah['ayah_num']}",
                        description=ayah['text'][:80],
                        input_message_content=InputTextMessageContent(
                            message_text=msg_text,
                            parse_mode="Markdown"
                        ),
                        reply_markup=kb,
                    ))
            except Exception:
                pass

    if q_data.startswith("challenge_"):
        challenge_id = q_data.replace("challenge_", "")
        link = f"https://t.me/{BOT_USERNAME.lstrip('@')}?start=fc_{challenge_id}"
        msg_text = (
            "⚔️ تحداني في بوت راوِي الإسلامي!\n\n"
            "🎯 هل تقدر تتفوق عليّ في 10 أسئلة إسلامية؟\n\n"
            "👇 اضغط الزر وابدأ التحدي الآن!"
        )
        kb = InlineKeyboardMarkup([[
            colored_btn("⚔️ اقبل التحدي", url=link, style="success")
        ]])
        results.append(InlineQueryResultArticle(
            id="challenge",
            title="⚔️ شارك تحدي الصديق",
            description="أرسل دعوة تحدي لصديقك",
            input_message_content=InputTextMessageContent(message_text=msg_text),
            reply_markup=kb,
        ))

    # ===== مشاركة قدوتي اليوم =====
    elif q_data.startswith("qudwati_"):
        name = q_data.replace("qudwati_", "")
        # ابحث عن القصة بالاسم
        story = get_qudwati_of_day()
        msg_text = (
            f"🌟 قدوتي اليوم: {story['name']}\n\n"
            f"{story['story'][:300]}...\n\n"
            f"💡 العبرة: {story['lesson']}\n\n"
            f"تعرّف على قصص الأنبياء والصحابة يومياً 👇"
        )
        kb = InlineKeyboardMarkup([[
            colored_btn("📲 افتح راوِي", url=bot_link, style="primary")
        ]])
        results.append(InlineQueryResultArticle(
            id="qudwati",
            title=f"🌟 قدوتي: {story['name']}",
            description=story['lesson'],
            input_message_content=InputTextMessageContent(message_text=msg_text),
            reply_markup=kb,
        ))

    # ===== مشاركة نتيجة التحدي =====
    elif q_data.startswith("fc_result_"):
        uid_key = q_data  # fc_result_{user_id}
        result_msg = context.bot_data.get(uid_key, "")
        if not result_msg:
            result_msg = "🎯 انتهى التحدي!\n\nشاركنا نتيجتك في بوت راوِي 🌙"
        kb = InlineKeyboardMarkup([[
            colored_btn("⚔️ تحدّني أنت أيضاً!", url=bot_link, style="success")
        ]])
        results.append(InlineQueryResultArticle(
            id="fc_result",
            title="🎯 شارك نتيجة التحدي",
            description="أرسل نتيجة التحدي لأصدقائك",
            input_message_content=InputTextMessageContent(
                message_text=result_msg,
                parse_mode="Markdown"
            ),
            reply_markup=kb,
        ))

    # ===== مشاركة دعاء =====
    elif q_data.startswith("duaa_"):
        # جلب الدعاء الكامل من bot_data
        d_full = context.bot_data.get("duaa_today") or {}
        duaa_text = d_full.get("text", "")
        duaa_source = d_full.get("source", "")
        duaa_meaning = d_full.get("meaning", "")
        if not duaa_text:
            # fallback
            from datetime import date as _date
            _base = _dt.date(2025, 1, 1)
            _cur = _dt.datetime.now(AMMAN_TZ).date()
            _day = (_cur - _base).days
            import importlib
            _d = DAILY_DUAA[_day % len(DAILY_DUAA)]
            duaa_text = _d.get("text", "")
            duaa_source = _d.get("source", "")
            duaa_meaning = _d.get("meaning", "")
        msg_text = (
            f"🤲 *دعاء اليوم*\n"
            f"━━━━━━━━━━━━━━━\n\n"
            f"*{duaa_text}*\n\n"
            f"📚 المصدر: {duaa_source}\n"
            f"💡 المعنى: {duaa_meaning}\n\n"
            f"_من بوت راوِي للأحاديث النبوية_ 🌙"
        )
        kb = InlineKeyboardMarkup([[
            colored_btn("📲 افتح راوِي", url=bot_link, style="primary")
        ]])
        results.append(InlineQueryResultArticle(
            id="duaa",
            title="🤲 شارك دعاء اليوم",
            description=duaa_text[:80] if duaa_text else "دعاء اليوم",
            input_message_content=InputTextMessageContent(
                message_text=msg_text,
                parse_mode="Markdown"
            ),
            reply_markup=kb,
        ))

    # ===== مشاركة حديث أو مشاركة عامة =====
    else:
        msg_text = (
            "🌙 بوت راوِي للأحاديث النبوية\n\n"
            "• تحقق من صحة الأحاديث\n"
            "• اختبر معلوماتك يومياً\n"
            "• قصص الأنبياء والصحابة كل يوم\n"
            "• أدعية من القرآن والسنة"
        )
        kb = InlineKeyboardMarkup([[
            colored_btn("📲 افتح راوِي", url=bot_link, style="primary")
        ]])
        results.append(InlineQueryResultArticle(
            id="share_bot",
            title="📤 شارك بوت راوِي",
            description="أرسل دعوة لصديقك لاستخدام البوت",
            input_message_content=InputTextMessageContent(message_text=msg_text),
            reply_markup=kb,
        ))

    await query.answer(results, cache_time=60)

async def cmd_share(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """زر المشاركة — يفتح نافذة اختيار المحادثة مع زر شفاف"""
    kb = InlineKeyboardMarkup([[
        colored_btn("📤 دعوة صديق", switch_inline_query="", style="primary")
    ]])
    await update.message.reply_text(
        "📤 *شارك راوِي مع أصدقائك*\n\n"
        "اضغط الزر أدناه، اختر المحادثة أو الصديق\n"
        "سيصله زر شفاف يفتح البوت مباشرة 👇",
        parse_mode="Markdown",
        reply_markup=kb
    )

if __name__ == "__main__":
    main()
