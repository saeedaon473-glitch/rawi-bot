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
from collections import Counter
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, LabeledPrice
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, PreCheckoutQueryHandler, filters, ContextTypes

# ==================== إعدادات البوت ====================
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    logger.error("❌ BOT_TOKEN غير موجود.")
    exit(1)

admin_ids_str = os.environ.get("ADMIN_IDS", "")
ADMIN_IDS = [int(x) for x in admin_ids_str.split(",") if x.strip().isdigit()]

BOT_NAME = "راوِي"
BOT_USERNAME = "@G4bGN_bot"

# توقيت الأردن UTC+3
import datetime as _dt
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
    conn.execute("""CREATE TABLE IF NOT EXISTS share_counts (
        hadith_text TEXT PRIMARY KEY,
        count INTEGER DEFAULT 0
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS bot_settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS user_sessions (
        user_id INTEGER PRIMARY KEY,
        results_json TEXT,
        page INTEGER DEFAULT 0,
        grade_filter TEXT DEFAULT 'all',
        search_id TEXT,
        updated_at TEXT
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS quiz_sessions (
        user_id INTEGER PRIMARY KEY,
        questions_json TEXT,
        quiz_index INTEGER DEFAULT 0,
        quiz_score INTEGER DEFAULT 0,
        quiz_date TEXT
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS asma_progress (
        user_id INTEGER PRIMARY KEY,
        last_index INTEGER DEFAULT 0,
        last_date TEXT
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS sahaba_quiz (
        user_id INTEGER,
        date TEXT,
        sahabi TEXT,
        correct INTEGER DEFAULT 0,
        PRIMARY KEY (user_id, date)
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS daily_question (
        user_id INTEGER,
        date TEXT,
        q_index INTEGER,
        answered INTEGER DEFAULT 0,
        correct INTEGER DEFAULT 0,
        PRIMARY KEY (user_id, date)
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS weekly_challenge (
        week TEXT PRIMARY KEY,
        q_index INTEGER,
        question TEXT,
        answer TEXT,
        hint TEXT
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS weekly_answers (
        user_id INTEGER,
        week TEXT,
        correct INTEGER DEFAULT 0,
        answer_text TEXT,
        PRIMARY KEY (user_id, week)
    )""")
    try:
        conn.execute("ALTER TABLE favorites ADD COLUMN note TEXT DEFAULT ''")
    except:
        pass
    # جدول Premium
    conn.execute("""CREATE TABLE IF NOT EXISTS premium (
        user_id INTEGER PRIMARY KEY,
        stars_total INTEGER DEFAULT 0,
        is_premium INTEGER DEFAULT 0,
        notif_hour INTEGER DEFAULT 7,
        notif_minute INTEGER DEFAULT 0,
        activated_at TEXT
    )""")
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
    conn.execute("""CREATE TABLE IF NOT EXISTS daily_challenge (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT UNIQUE,
        hadith_text TEXT,
        answer TEXT,
        full_text TEXT
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS challenge_answers (
        user_id INTEGER,
        date TEXT,
        correct INTEGER DEFAULT 0,
        answered_at TEXT DEFAULT (datetime('now')),
        PRIMARY KEY (user_id, date)
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS duels (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        challenger_id INTEGER,
        opponent_id INTEGER,
        status TEXT DEFAULT 'pending',
        start_date TEXT,
        challenger_streak INTEGER DEFAULT 0,
        opponent_streak INTEGER DEFAULT 0,
        challenger_last TEXT DEFAULT '',
        opponent_last TEXT DEFAULT ''
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS mood_log (
        user_id INTEGER,
        mood TEXT,
        date TEXT,
        PRIMARY KEY (user_id, date)
    )""")
    conn.commit()
    conn.close()
    logger.info("✅ تم إنشاء قاعدة البيانات.")

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

def get_donation(user_id, charge_id):
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
    """استخراج الأحاديث من HTML الدرر — يرجع الكتب الستة فقط"""
    import re as _re

    SITTA = [
        "صحيح البخاري", "صحيح مسلم",
        "سنن أبي داود", "سنن الترمذي",
        "سنن النسائي", "سنن ابن ماجه",
    ]

    def extract_field(chunk, label):
        """استخراج قيمة حقل معين بشكل مباشر"""
        m = _re.search(
            r'<span class="info-subtitle">' + _re.escape(label) + r'[^<]*</span>(.*?)(?=<span class="info-subtitle"|</div>)',
            chunk, _re.DOTALL
        )
        if m:
            return _re.sub(r'<[^>]+>', '', m.group(1)).strip()
        return ""

    results = []
    chunks = _re.split(r'(?=<div class="hadith" )', html)
    chunks = [c for c in chunks if '<div class="hadith" ' in c]

    for i, chunk in enumerate(chunks[:30]):
        # نص الحديث - نأخذ كل النص داخل div class="hadith" حتى لو في divs داخلية
        m = _re.search(r'<div class="hadith" [^>]*>(.*)', chunk, _re.DOTALL)
        if not m:
            continue
        raw_full = m.group(1)
        # أزل كل الـ HTML tags وخذ النص الكامل قبل div التالية
        raw_text = _re.sub(r'<[^>]+>', ' ', raw_full)
        # نظّف الأرقام والمسافات الزائدة
        raw_text = _re.sub(r'^\s*\d+\s*[-–]\s*', '', raw_text.strip())
        raw_text = _re.sub(r'\s+', ' ', raw_text)
        text = raw_text.strip().strip('.').strip()
        # أزل أي نص بعد خط الراوي (يبدأ عادة بالراوي:)
        if 'الراوي:' in text:
            text = text[:text.find('الراوي:')].strip()
        if not text or len(text) < 10:
            continue

        # استخراج كل حقل بشكل مباشر حسب التسمية
        rawi    = extract_field(chunk, "الراوي:")
        mohdith = extract_field(chunk, "المحدث:")
        source  = extract_field(chunk, "المصدر:")
        grade   = extract_field(chunk, "خلاصة حكم المحدث:")

        # فحص في حقل المصدر فقط (الفحص في الـ chunk كاملاً يعطي نتائج غلط)
        in_sitta = any(k in source for k in SITTA)
        # لو المصدر فارغ نفحص في منطقة الـ info فقط بدل الـ chunk كله
        if not in_sitta and not source:
            info_m = _re.search(r'class="info"[^>]*>(.*?)(?=<div class="hadith"|$)', chunk, _re.DOTALL)
            if info_m:
                info_text = info_m.group(1)
                in_sitta = any(k in info_text for k in SITTA)

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

    # فلتر: الكتب الستة فقط
    sitta = [r for r in results if r["_in_sitta"]]
    final = sitta if sitta else results  # لو ما في نتائج من الستة خذ كل شي

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
    "أبو هريرة", "ابن عمر", "ابن عباس", "عائشة", "أنس بن مالك",
    "جابر بن عبدالله", "أبو سعيد الخدري", "ابن مسعود", "علي بن أبي طالب",
    "عمر بن الخطاب", "أبو بكر الصديق", "عثمان بن عفان", "معاذ بن جبل",
    "أبو موسى الأشعري", "البراء بن عازب", "حذيفة بن اليمان",
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
    """هل يبحث المستخدم باسم راوٍ؟ يرجع اسم الراوي أو فارغ"""
    q = query.strip()
    for rawi in KNOWN_RAWIS:
        if rawi in q or q in rawi:
            return rawi
    return ""

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
        logger.info(f"[DORAR] {len(results)} نتيجة لـ: {clean_q[:30]}")
        cache_set(clean_q, results)
        return results

    # fallback: cache قديم
    old = _search_cache.get(clean_q.strip().lower())
    return old[0] if old else []





def get_random_hadith():
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
TIER1_STARS = 1
TIER2_STARS = 5
TIER3_STARS = 25

def get_tier(user_id: int) -> int:
    """يرجع مستوى الداعم: 0=مجاني 1=تير1 2=تير2 3=تير3 | الأدمن دايماً تير 3"""
    if user_id in ADMIN_IDS:
        return 3
    stars = get_premium_stars(user_id)
    if stars >= TIER3_STARS:
        return 3
    elif stars >= TIER2_STARS:
        return 2
    elif stars >= TIER1_STARS:
        return 1
    return 0

def is_premium(user_id: int) -> bool:
    return get_tier(user_id) >= 1

def has_topics(user_id: int) -> bool:
    return get_tier(user_id) >= 1

def has_favorites(user_id: int) -> bool:
    return get_tier(user_id) >= 2

def has_custom_time(user_id: int) -> bool:
    return get_tier(user_id) >= 3

def get_premium_stars(user_id: int) -> int:
    """إجمالي نجوم المستخدم"""
    try:
        conn = sqlite3.connect("bot.db")
        cur = conn.cursor()
        cur.execute("SELECT SUM(amount) FROM donations WHERE user_id=?", (user_id,))
        row = cur.fetchone()
        conn.close()
        return row[0] or 0 if row else 0
    except:
        return 0

def activate_premium(user_id: int, stars: int):
    """حدّث بيانات الداعم في جدول premium"""
    conn = sqlite3.connect("bot.db")
    conn.execute("""
        INSERT INTO premium (user_id, stars_total, is_premium, activated_at)
        VALUES (?,?,1,datetime('now'))
        ON CONFLICT(user_id) DO UPDATE SET
            stars_total=stars_total+excluded.stars_total,
            is_premium=1,
            activated_at=COALESCE(activated_at, datetime('now'))
    """, (user_id, stars))
    conn.commit()
    conn.close()

def get_tier_label(tier: int) -> str:
    labels = {0: "👤 مستخدم عادي", 1: "⭐ داعم - تير 1", 2: "⭐⭐ داعم - تير 2", 3: "🌟 داعم مميز - تير 3"}
    return labels.get(tier, "👤 مستخدم عادي")

def get_tier_features(tier: int) -> str:
    if tier == 0:
        return (
            "المزايا المتاحة لك بالدعم:\n"
            f"  ⭐ {TIER1_STARS}+ نجمة → 🔎 بحث بالموضوع\n"
            f"  ⭐ {TIER2_STARS}+ نجوم → 💾 المفضلة\n"
            f"  ⭐ {TIER3_STARS}+ نجمة → 🕐 تخصيص وقت الإشعار\n"
        )
    elif tier == 1:
        return (
            "مزاياك الحالية:\n  ✅ 🔎 بحث بالموضوع\n\n"
            "لفتح المزيد:\n"
            f"  ⭐ {TIER2_STARS}+ نجوم → 💾 المفضلة\n"
            f"  ⭐ {TIER3_STARS}+ نجمة → 🕐 تخصيص وقت الإشعار\n"
        )
    elif tier == 2:
        return (
            "مزاياك الحالية:\n  ✅ 🔎 بحث بالموضوع\n  ✅ 💾 المفضلة\n\n"
            "لفتح المزيد:\n"
            f"  ⭐ {TIER3_STARS}+ نجمة → 🕐 تخصيص وقت الإشعار\n"
        )
    else:
        return "مزاياك الحالية:\n  ✅ 🔎 بحث بالموضوع\n  ✅ 💾 المفضلة\n  ✅ 🕐 تخصيص وقت الإشعار\n"

def get_notif_time(user_id: int) -> tuple:
    """جلب وقت الإشعار المخصص للمستخدم"""
    try:
        conn = sqlite3.connect("bot.db")
        cur = conn.cursor()
        cur.execute("SELECT notif_hour, notif_minute FROM premium WHERE user_id=?", (user_id,))
        row = cur.fetchone()
        conn.close()
        return (row[0], row[1]) if row else (7, 0)
    except:
        return (7, 0)

def set_notif_time(user_id: int, hour: int, minute: int):
    """حفظ وقت الإشعار المخصص"""
    conn = sqlite3.connect("bot.db")
    conn.execute("""
        INSERT INTO premium (user_id, notif_hour, notif_minute, is_premium)
        VALUES (?,?,?,1)
        ON CONFLICT(user_id) DO UPDATE SET notif_hour=?, notif_minute=?
    """, (user_id, hour, minute, hour, minute))
    conn.commit()
    conn.close()

# ==================== المفضلة ====================
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

def get_search_history(user_id: int) -> list:
    """جلب آخر 20 بحث للمستخدم"""
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute("""SELECT query, results_count, date FROM search_history
                   WHERE user_id=? ORDER BY date DESC LIMIT 20""", (user_id,))
    rows = cur.fetchall()
    conn.close()
    return rows

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

def increment_share(hadith_text: str):
    """زيادة عداد المشاركات"""
    try:
        conn = sqlite3.connect("bot.db")
        conn.execute("""
            INSERT INTO share_counts (hadith_text, count) VALUES (?,1)
            ON CONFLICT(hadith_text) DO UPDATE SET count=count+1
        """, (hadith_text[:500],))
        conn.commit()
        conn.close()
    except:
        pass

def get_top_shared(limit=10) -> list:
    """أكثر الأحاديث مشاركةً"""
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute("SELECT hadith_text, count FROM share_counts ORDER BY count DESC LIMIT ?", (limit,))
    rows = cur.fetchall()
    conn.close()
    return rows

def save_favorite_note(user_id: int, hadith_text: str, note: str):
    """حفظ ملاحظة على حديث في المفضلة"""
    conn = sqlite3.connect("bot.db")
    conn.execute("UPDATE favorites SET note=? WHERE user_id=? AND hadith_text=?",
                 (note[:300], user_id, hadith_text))
    conn.commit()
    conn.close()

def get_subscribers(col: str) -> list:
    """جلب المشتركين في خدمة معينة"""
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

# ===== وظائف الجدولة الإضافية =====

async def scheduled_notification(context: ContextTypes.DEFAULT_TYPE):
    """حديث اليوم - يُرسل كل يوم 7 الصبح من الـ API"""
    h = None
    topic = _random.choice(DAILY_TOPICS)
    try:
        results = await search_dorar_api(topic)
        if results:
            h = _random.choice(results[:10])
    except:
        pass
    if not h:
        conn = sqlite3.connect("bot.db")
        cur = conn.cursor()
        cur.execute("SELECT text, rawi, source, grade FROM ahadith ORDER BY RANDOM() LIMIT 1")
        row = cur.fetchone()
        conn.close()
        if row:
            h = {"text": row[0], "rawi": row[1], "source": row[2], "grade": row[3]}
    if h:
        msg = (
            "🌅 *حديث اليوم*\n"
            "━━━━━━━━━━━━━━━\n\n"
            f"📌 {h['text']}\n\n"
            f"👤 *الراوي:* {h.get('rawi') or 'غير محدد'}\n"
            f"📚 *المصدر:* {h.get('source') or 'غير محدد'}\n"
            f"⚖️ *الدرجة:* {h.get('grade') or 'غير محدد'}\n\n"
            "━━━━━━━━━━━━━━━\n"
            f"🤖 *{BOT_NAME}* | {BOT_USERNAME}"
        )
    else:
        msg = (
            "🌅 *حديث اليوم*\n\n"
            "ابدأ يومك بذكر الله 🤍\n\n"
            f"🤖 *{BOT_NAME}* | {BOT_USERNAME}"
        )
    streak_kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ قرأت", callback_data="streak_read")
    ]])
    for uid in get_subscribers("daily_hadith"):
        try:
            await context.bot.send_message(uid, msg, parse_mode="Markdown", reply_markup=streak_kb)
            await asyncio.sleep(0.05)
        except:
            pass

async def send_adhkar_sabah(context: ContextTypes.DEFAULT_TYPE):
    """أذكار الصباح - 6:00 صباحاً"""
    dhikr, fadl, source = _random.choice(ADHKAR_SABAH)
    msg = (
        "🌄 *أذكار الصباح*\n"
        "━━━━━━━━━━━━━━━\n\n"
        f"✨ {dhikr}\n\n"
        f"💡 *الفضل:* {fadl}\n"
        f"📚 *المصدر:* {source}\n\n"
        "━━━━━━━━━━━━━━━\n"
        f"🤖 *راوِي* | @G4bGN_bot"
    )
    for uid in get_subscribers("adhkar_sub"):
        try:
            await context.bot.send_message(uid, msg, parse_mode="Markdown")
            await asyncio.sleep(0.05)
        except:
            pass


async def send_adhkar_masaa(context: ContextTypes.DEFAULT_TYPE):
    """أذكار المساء - 4:00 مساءً"""
    dhikr, fadl, source = _random.choice(ADHKAR_MASAA)
    msg = (
        "🌆 *أذكار المساء*\n"
        "━━━━━━━━━━━━━━━\n\n"
        f"✨ {dhikr}\n\n"
        f"💡 *الفضل:* {fadl}\n"
        f"📚 *المصدر:* {source}\n\n"
        "━━━━━━━━━━━━━━━\n"
        f"🤖 *راوِي* | @G4bGN_bot"
    )
    for uid in get_subscribers("adhkar_sub"):
        try:
            await context.bot.send_message(uid, msg, parse_mode="Markdown")
            await asyncio.sleep(0.05)
        except:
            pass


# ==================== Streak ====================
def get_streak(user_id: int) -> dict:
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute("SELECT streak, max_streak, last_date FROM streaks WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    conn.close()
    if row:
        return {"streak": row[0], "max": row[1], "last": row[2]}
    return {"streak": 0, "max": 0, "last": ""}

def update_streak(user_id: int):
    """يحدّث السلسلة عند قراءة حديث اليوم"""
    today = _dt.datetime.now(AMMAN_TZ).strftime("%Y-%m-%d")
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute("SELECT streak, max_streak, last_date FROM streaks WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    if row:
        streak, max_streak, last_date = row
        yesterday = (_dt.datetime.now(AMMAN_TZ) - _dt.timedelta(days=1)).strftime("%Y-%m-%d")
        if last_date == today:
            conn.close()
            return streak  # قرأ اليوم بالفعل
        elif last_date == yesterday:
            streak += 1  # يوم متتالي
        else:
            streak = 1  # انكسرت السلسلة
        max_streak = max(streak, max_streak)
        cur.execute("UPDATE streaks SET streak=?, max_streak=?, last_date=? WHERE user_id=?",
                    (streak, max_streak, today, user_id))
    else:
        streak = 1
        cur.execute("INSERT INTO streaks (user_id, streak, max_streak, last_date) VALUES (?,1,1,?)",
                    (user_id, today))
    conn.commit()
    conn.close()
    return streak

def streak_emoji(streak: int) -> str:
    if streak >= 30: return "🔥🔥🔥"
    elif streak >= 7: return "🔥🔥"
    elif streak >= 1: return "🔥"
    return ""

# ==================== Daily Challenge ====================
def get_asma_of_day(user_id: int) -> dict:
    """جلب اسم الله لهذا اليوم"""
    today = _dt.datetime.now(AMMAN_TZ).strftime("%Y-%m-%d")
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute("SELECT last_index, last_date FROM asma_progress WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    if row and row[1] == today:
        idx = row[0]
    else:
        idx = (row[0] + 1) % len(ASMA_ALLAH) if row else 0
        conn.execute("INSERT OR REPLACE INTO asma_progress (user_id, last_index, last_date) VALUES (?,?,?)",
                     (user_id, idx, today))
        conn.commit()
    conn.close()
    return ASMA_ALLAH[idx]

def get_sahaba_of_day() -> dict:
    """جلب صحابي اليوم"""
    today = _dt.datetime.now(AMMAN_TZ).strftime("%Y-%m-%d")
    day_num = sum(int(c) for c in today.replace("-","")) % len(SAHABA_QUIZ)
    return SAHABA_QUIZ[day_num]

def get_question_of_day() -> dict:
    """جلب سؤال اليوم"""
    today = _dt.datetime.now(AMMAN_TZ).strftime("%Y-%m-%d")
    day_num = sum(int(c) for c in today.replace("-","")) % len(DAILY_QUESTIONS)
    return DAILY_QUESTIONS[day_num]

def get_weekly_challenge() -> dict:
    """جلب تحدي الأسبوع"""
    today = _dt.datetime.now(AMMAN_TZ)
    week = today.strftime("%Y-W%W")
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute("SELECT question, answer, hint FROM weekly_challenge WHERE week=?", (week,))
    row = cur.fetchone()
    conn.close()
    if row:
        return {"question": row[0], "answer": row[1], "hint": row[2], "week": week}
    # اختر تحدي الأسبوع تلقائياً
    week_num = int(today.strftime("%W")) % len(WEEKLY_CHALLENGES)
    ch = WEEKLY_CHALLENGES[week_num]
    conn = sqlite3.connect("bot.db")
    conn.execute("INSERT OR IGNORE INTO weekly_challenge (week, q_index, question, answer, hint) VALUES (?,?,?,?,?)",
                 (week, week_num, ch["q"], ch["answer"], ch["hint"]))
    conn.commit()
    conn.close()
    return {"question": ch["q"], "answer": ch["answer"], "hint": ch["hint"], "week": week}

def save_weekly_answer(user_id: int, week: str, answer: str, correct: bool):
    conn = sqlite3.connect("bot.db")
    conn.execute("INSERT OR IGNORE INTO weekly_answers (user_id, week, correct, answer_text) VALUES (?,?,?,?)",
                 (user_id, week, 1 if correct else 0, answer))
    conn.commit()
    conn.close()

def has_answered_weekly(user_id: int, week: str) -> bool:
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM weekly_answers WHERE user_id=? AND week=?", (user_id, week))
    row = cur.fetchone()
    conn.close()
    return bool(row)

def get_weekly_scores(week: str) -> list:
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute("""SELECT u.full_name, u.username, wa.correct, wa.answer_text
                   FROM weekly_answers wa JOIN users u ON wa.user_id=u.user_id
                   WHERE wa.week=? ORDER BY wa.correct DESC, wa.user_id ASC LIMIT 20""", (week,))
    rows = cur.fetchall()
    conn.close()
    return rows

def save_quiz_session(user_id: int, questions: list, idx: int, score: int, date: str):
    import json as _j
    conn = sqlite3.connect("bot.db")
    conn.execute("INSERT OR REPLACE INTO quiz_sessions (user_id, questions_json, quiz_index, quiz_score, quiz_date) VALUES (?,?,?,?,?)",
        (user_id, _j.dumps(questions, ensure_ascii=False), idx, score, date))
    conn.commit()
    conn.close()

def load_quiz_session(user_id: int) -> dict:
    import json as _j
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute("SELECT questions_json, quiz_index, quiz_score, quiz_date FROM quiz_sessions WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    conn.close()
    if not row: return {}
    try:
        return {"questions": _j.loads(row[0]), "index": row[1], "score": row[2], "date": row[3]}
    except: return {}

def clear_quiz_session(user_id: int):
    conn = sqlite3.connect("bot.db")
    conn.execute("DELETE FROM quiz_sessions WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()

def save_user_session(user_id: int, results: list, page: int, grade_filter: str, search_id: str):
    """حفظ نتائج البحث في قاعدة البيانات"""
    import json as _json
    now = _dt.datetime.now(AMMAN_TZ).strftime("%Y-%m-%d %H:%M:%S")
    # خزن أول 50 نتيجة فقط عشان ما يكبر الـ DB
    trimmed = results[:50]
    conn = sqlite3.connect("bot.db")
    conn.execute("""INSERT OR REPLACE INTO user_sessions
        (user_id, results_json, page, grade_filter, search_id, updated_at)
        VALUES (?,?,?,?,?,?)""",
        (user_id, _json.dumps(trimmed, ensure_ascii=False), page, grade_filter, search_id, now))
    conn.commit()
    conn.close()

def load_user_session(user_id: int) -> dict:
    """استرجاع جلسة المستخدم من قاعدة البيانات"""
    import json as _json
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute("SELECT results_json, page, grade_filter, search_id FROM user_sessions WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    conn.close()
    if not row or not row[0]:
        return {}
    try:
        results = _json.loads(row[0])
        return {"results": results, "page": row[1], "grade_filter": row[2], "search_id": row[3]}
    except:
        return {}

def get_today_challenge() -> dict:
    today = _dt.datetime.now(AMMAN_TZ).strftime("%Y-%m-%d")
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute("SELECT hadith_text, answer, full_text FROM daily_challenge WHERE date=?", (today,))
    row = cur.fetchone()
    conn.close()
    if row:
        return {"text": row[0], "answer": row[1], "full": row[2]}
    return {}

def save_today_challenge(hadith_text: str, answer: str, full_text: str):
    today = _dt.datetime.now(AMMAN_TZ).strftime("%Y-%m-%d")
    conn = sqlite3.connect("bot.db")
    conn.execute("INSERT OR IGNORE INTO daily_challenge (date, hadith_text, answer, full_text) VALUES (?,?,?,?)",
                 (today, hadith_text, answer, full_text))
    conn.commit()
    conn.close()

def has_answered_today(user_id: int) -> bool:
    today = _dt.datetime.now(AMMAN_TZ).strftime("%Y-%m-%d")
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM challenge_answers WHERE user_id=? AND date=?", (user_id, today))
    row = cur.fetchone()
    conn.close()
    return bool(row)

def save_challenge_answer(user_id: int, correct: bool):
    today = _dt.datetime.now(AMMAN_TZ).strftime("%Y-%m-%d")
    conn = sqlite3.connect("bot.db")
    conn.execute("INSERT OR IGNORE INTO challenge_answers (user_id, date, correct) VALUES (?,?,?)",
                 (user_id, today, int(correct)))
    conn.commit()
    conn.close()

STATIC_CHALLENGE_HADITHS = [
    'إنما الأعمال بالنيات وإنما لكل امرئ ما نوى فمن كانت هجرته إلى الله ورسوله فهجرته إلى الله ورسوله',
    'المسلم من سلم المسلمون من لسانه ويده والمهاجر من هجر ما نهى الله عنه',
    'لا يؤمن أحدكم حتى يحب لأخيه ما يحب لنفسه من الخير',
    'من كان يؤمن بالله واليوم الآخر فليقل خيراً أو ليصمت ومن كان يؤمن بالله واليوم الآخر فليكرم جاره',
    'الدين النصيحة قلنا لمن قال لله ولكتابه ولرسوله ولأئمة المسلمين وعامتهم',
    'اتق الله حيثما كنت وأتبع السيئة الحسنة تمحها وخالق الناس بخلق حسن',
    'من سلك طريقاً يلتمس فيه علماً سهل الله له به طريقاً إلى الجنة',
    'الطهور شطر الإيمان والحمد لله تملأ الميزان وسبحان الله والحمد لله تملآن ما بين السماء والأرض',
    'بينما رجل يمشي بطريق وجد غصن شوك على الطريق فأخره فشكر الله له فغفر له',
    'كل سلامى من الناس عليه صدقة كل يوم تطلع فيه الشمس',
    'أحب الأعمال إلى الله أدومها وإن قل',
    'من نفس عن مؤمن كربة من كرب الدنيا نفس الله عنه كربة من كرب يوم القيامة',
]


# ==================== أسماء الله الحسنى ====================
ASMA_ALLAH = [
    {"name": "الرَّحْمَن", "meaning": "ذو الرحمة الواسعة الشاملة لجميع الخلق في الدنيا، مؤمنهم وكافرهم", "benefit": "من داوم على قراءته رقّ قلبه", "dhikr": "يا رحمن ارحمني برحمتك الواسعة"},
    {"name": "الرَّحِيم", "meaning": "دائم الرحمة بعباده المؤمنين خاصةً في الآخرة، رحمته خاصة بهم", "benefit": "من قرأه كثيراً نال رحمة الله في الدارين", "dhikr": "يا رحيم ارحمني برحمتك الخاصة"},
    {"name": "الْمَلِك", "meaning": "المالك لكل شيء، الملك الحق الذي لا يزول ملكه ولا يشاركه فيه أحد", "benefit": "تذكره يزهّد في الدنيا ويعلي الهمة", "dhikr": "يا ملك الملوك أصلح لي شأني"},
    {"name": "الْقُدُّوس", "meaning": "المنزّه عن كل نقص وعيب وشريك، البالغ في الطهارة والكمال", "benefit": "يطهّر القلب من الأدران والذنوب", "dhikr": "يا قدوس طهّر قلبي من الغفلة"},
    {"name": "السَّلَام", "meaning": "السالم من كل نقص وآفة، ومنه يصدر السلام والأمان لعباده", "benefit": "يورث الطمأنينة والسكينة في القلب", "dhikr": "يا سلام سلّمني في ديني ودنياي وآخرتي"},
    {"name": "الْمُؤْمِن", "meaning": "يمنح الأمن لعباده، يصدّق وعده، ويؤمّن الخائفين يوم القيامة", "benefit": "الأمان من الخوف والقلق", "dhikr": "يا مؤمن آمن روعتي وأمّن خوفي"},
    {"name": "الْمُهَيْمِن", "meaning": "الرقيب الحافظ على كل شيء، المسيطر على الخلق بعلمه وقدرته", "benefit": "يحفظ صاحبه من المكاره", "dhikr": "يا مهيمن احفظني بحفظك"},
    {"name": "الْعَزِيز", "meaning": "الغالب الذي لا يُقهر ولا يُغلب، المنيع الذي لا مثيل له", "benefit": "يُعزّ من أحبّه ويذلّ أعداءه", "dhikr": "يا عزيز أعزّني بطاعتك"},
    {"name": "الْجَبَّار", "meaning": "الذي يجبر الكسير ويغني الفقير ويقهر الجبابرة، لا يُكرَه على شيء", "benefit": "يجبر القلوب المكسورة", "dhikr": "يا جبار اجبر كسري وقوّ ضعفي"},
    {"name": "الْمُتَكَبِّر", "meaning": "المتعالي بذاته عن كل نقص، الكبير الذي لا يليق الكبر إلا له", "benefit": "تذكره يكسر الكبر في النفس", "dhikr": "يا متكبر أذلّ نفسي لعظمتك"},
    {"name": "الْخَالِق", "meaning": "الموجِد للأشياء من العدم على غير مثال سابق، مخترع الأشياء", "benefit": "يفتح باب التفكر في بديع الخلق", "dhikr": "يا خالق اخلق في قلبي الإيمان"},
    {"name": "الْبَارِئ", "meaning": "الذي خلق الخلق بريئاً من التفاوت والعيوب، المميّز لكل مخلوق", "benefit": "شفاء من الأمراض بإذن الله", "dhikr": "يا بارئ بَرِّئني من كل سوء"},
    {"name": "الْمُصَوِّر", "meaning": "الذي يصوّر الخلق كيف يشاء ويعطي كل شيء صورته الخاصة", "benefit": "يُحسّن الأحوال ويُجمّلها", "dhikr": "يا مصوّر صوّر أحوالي على ما تحب"},
    {"name": "الْغَفَّار", "meaning": "كثير المغفرة لعباده، يغفر الذنب مرة بعد مرة ولا يمل من العفو", "benefit": "يفتح باب التوبة ويمحو الذنوب", "dhikr": "يا غفار اغفر لي ذنوبي كلها"},
    {"name": "الْقَهَّار", "meaning": "الغالب فوق عباده، يقهر كل شيء ويخضع له كل مخلوق قسراً", "benefit": "يُعين على قهر الهوى والشيطان", "dhikr": "يا قهار اقهر نفسي الأمارة بالسوء"},
    {"name": "الْوَهَّاب", "meaning": "كثير العطاء بلا مقابل ولا منّ، يهب لمن يشاء ما يشاء بلا حساب", "benefit": "يفتح أبواب العطاء والرزق", "dhikr": "يا وهاب هب لي من عندك رحمة ويسراً"},
    {"name": "الرَّزَّاق", "meaning": "الذي يرزق جميع الخلق، لا يُنسى أحد عنده، وسع رزقه كل حي", "benefit": "يفتح أبواب الرزق من حيث لا يُحتسب", "dhikr": "يا رزاق ارزقني من حيث لا أحتسب"},
    {"name": "الْفَتَّاح", "meaning": "يفتح أبواب الرحمة والرزق والفرج وينصر المظلوم على الظالم", "benefit": "يُفرج الكروب ويفتح المغلقات", "dhikr": "يا فتاح افتح لي أبواب الخير"},
    {"name": "الْعَلِيم", "meaning": "المحيط علمه بكل شيء ظاهراً وباطناً، ماضياً وحاضراً ومستقبلاً", "benefit": "يُنير القلب بالعلم النافع", "dhikr": "يا عليم علّمني ما ينفعني"},
    {"name": "الْقَابِض", "meaning": "يقبض الأرواح وينقص الأرزاق بحكمته وعدله لمن يشاء", "benefit": "التسليم لله في الشدائد والضيق", "dhikr": "يا قابض سهّل عليّ ما قبضت"},
    {"name": "الْبَاسِط", "meaning": "يبسط الرزق ويوسّعه لمن يشاء، يبسط القلوب بالسعادة", "benefit": "يوسّع الرزق والصدر والأمل", "dhikr": "يا باسط ابسط علينا من رزقك وفضلك"},
    {"name": "الْخَافِض", "meaning": "يخفض الجبارين والطغاة ويذل من يستحق الخفض والذل", "benefit": "الحفظ من تكبّر الظالمين", "dhikr": "يا خافض اخفض كل جبار عنيد"},
    {"name": "الرَّافِع", "meaning": "يرفع المؤمنين بالطاعة ويعلي أولياءه فوق أعدائهم", "benefit": "رفع الدرجات والمكانة", "dhikr": "يا رافع ارفع درجتي في الدنيا والآخرة"},
    {"name": "الْمُعِز", "meaning": "يُعزّ من يشاء من عباده بالنصر والتمكين والطاعة", "benefit": "نيل العزة الحقيقية بطاعة الله", "dhikr": "يا معز أعزّني بعزّك"},
    {"name": "الْمُذِل", "meaning": "يذل من يشاء ممن عصاه، لا عزة لمن أذلّه الله", "benefit": "الحذر من الذنوب وموجبات الذل", "dhikr": "يا مذل لا تذلّني بمعصيتك"},
    {"name": "السَّمِيع", "meaning": "يسمع كل صوت دقيقاً كان أم جلياً، لا يغيب عنه شيء", "benefit": "يستجيب الدعاء ويُقرّب من الله", "dhikr": "يا سميع اسمع دعائي وشكواي"},
    {"name": "الْبَصِير", "meaning": "يرى كل شيء ظاهراً وخفياً، يرى دبيب النملة في الظلام", "benefit": "يُصلح السلوك ويُحسّن الأعمال", "dhikr": "يا بصير انظر إليّ بعين رحمتك"},
    {"name": "الْحَكَم", "meaning": "الحاكم العدل الذي يحكم بين خلقه بالحق ولا يجور", "benefit": "الرضا بقضاء الله وعدله", "dhikr": "يا حكم احكم بيني وبين من ظلمني"},
    {"name": "الْعَدْل", "meaning": "المتصف بالعدل التام، يعطي كل ذي حق حقه لا يظلم أحداً", "benefit": "الطمأنينة بأن الله ينصف المظلوم", "dhikr": "يا عدل أعدل في أمري"},
    {"name": "اللَّطِيف", "meaning": "يعلم دقائق الأمور ويوصل الخير لعباده بطرق لا يتوقعونها", "benefit": "يُيسّر الأمور ويُفرّج الكروب بلطفه", "dhikr": "يا لطيف الطف بي في أموري"},
    {"name": "الْخَبِير", "meaning": "المطلع على خفايا الأمور وبواطنها، لا يغيب عنه خافية", "benefit": "يُصلح السرائر ويُحسّن النوايا", "dhikr": "يا خبير أعلم بحالي وأصلح شأني"},
    {"name": "الْحَلِيم", "meaning": "لا يعجل بالعقوبة رغم القدرة، يمهل عباده ليتوبوا", "benefit": "يمنح الصبر والأناة في التعامل مع الناس", "dhikr": "يا حليم لا تعاجلني بذنوبي"},
    {"name": "الْعَظِيم", "meaning": "الموصوف بالعظمة المطلقة في ذاته وصفاته وأفعاله", "benefit": "يُعظّم الله في القلب فيصغر ما سواه", "dhikr": "يا عظيم عظّم قدرك في قلبي"},
    {"name": "الْغَفُور", "meaning": "يغفر الذنوب مهما عظمت ما دام العبد تائباً مستغفراً", "benefit": "يفتح باب الأمل في رحمة الله", "dhikr": "يا غفور اغفر لي ما علمت وما لم أعلم"},
    {"name": "الشَّكُور", "meaning": "يشكر القليل من العمل ويجازي عليه بالكثير من الأجر", "benefit": "يُضاعف الأعمال الصالحة", "dhikr": "يا شكور اجعلني من الشاكرين لنعمتك"},
    {"name": "الْعَلِيّ", "meaning": "المتعالي بذاته فوق جميع خلقه علواً مطلقاً", "benefit": "يُعلي همة العبد نحو الآخرة", "dhikr": "يا علي ارفعني بطاعتك"},
    {"name": "الْكَبِير", "meaning": "الكبير بذاته المتكبر على كل شيء، كبرياؤه لا يشبهه كبرياء", "benefit": "يُصغّر الدنيا في العين ويعظّم الآخرة", "dhikr": "يا كبير كبّرك في قلبي"},
    {"name": "الْحَفِيظ", "meaning": "يحفظ عباده من المهالك ويحصي أعمالهم بدقة تامة", "benefit": "الحفظ من المكاره والأعداء", "dhikr": "يا حفيظ احفظني بحفظك"},
    {"name": "الْمُقِيت", "meaning": "الحافظ للأشياء، يُوصل إلى كل نفس قوتها وما يُصلحها", "benefit": "يُيسّر أسباب القوت والمعاش", "dhikr": "يا مقيت أقت لي قوتي وأهلي"},
    {"name": "الْحَسِيب", "meaning": "الكافي لعباده، يُحاسب الخلق على أعمالهم يوم القيامة", "benefit": "يكفي صاحبه من كل ما يخشاه", "dhikr": "يا حسيب حاسبني حساباً يسيراً"},
    {"name": "الْجَلِيل", "meaning": "ذو الجلال والعظمة المطلقة التي تملأ القلوب هيبةً وإجلالاً", "benefit": "يملأ القلب هيبةً وتعظيماً لله", "dhikr": "يا جليل أجلّك في قلبي"},
    {"name": "الْكَرِيم", "meaning": "كثير الخير والعطاء، يعطي بلا سؤال ويزيد على ما طُلب", "benefit": "يفتح أبواب الكرم والعطاء", "dhikr": "يا كريم أكرمني بعفوك وجودك"},
    {"name": "الرَّقِيب", "meaning": "يراقب جميع الأعمال والنيات ولا يغفل عن شيء طرفة عين", "benefit": "يُصلح الأعمال ويُحسّن النيات", "dhikr": "يا رقيب راقبني برحمتك لا بعقوبتك"},
    {"name": "الْمُجِيب", "meaning": "يجيب دعاء كل داعٍ ويقضي حاجة كل سائل بحسب ما يعلم", "benefit": "يفتح باب الدعاء والرجاء", "dhikr": "يا مجيب أجب دعائي وحقق رجائي"},
    {"name": "الْوَاسِع", "meaning": "واسع الرحمة والعلم والقدرة والرزق، لا تحدّه حدود", "benefit": "يوسّع الرزق والصدر والفكر", "dhikr": "يا واسع وسّع علينا رزقك ورحمتك"},
    {"name": "الْحَكِيم", "meaning": "ذو الحكمة البالغة في كل قضاء وقدر وتشريع وخلق", "benefit": "يُرضّي بقضاء الله ويُحسّن القرارات", "dhikr": "يا حكيم أحكم أموري وسدّد رأيي"},
    {"name": "الْوَدُود", "meaning": "يحب عباده المؤمنين ويودّهم ويُحبّب إليهم الإيمان", "benefit": "يُكسب محبة الناس والقبول", "dhikr": "يا ودود حبّبني إلى عبادك الصالحين"},
    {"name": "الْمَجِيد", "meaning": "الواسع الكرم العظيم الشأن، الموصوف بكمال الشرف والعلو", "benefit": "يُشرّف العبد ويرفع قدره", "dhikr": "يا مجيد أجدّد إيماني بك"},
    {"name": "الْبَاعِث", "meaning": "يبعث الخلق يوم القيامة بعد موتهم للحساب والجزاء", "benefit": "يُجدّد اليقين بالبعث والحساب", "dhikr": "يا باعث ابعثني يوم القيامة في زمرة الصالحين"},
    {"name": "الشَّهِيد", "meaning": "يشهد على كل شيء في كل وقت ومكان لا يغيب عنه شيء", "benefit": "يُصلح السر والعلن والباطن والظاهر", "dhikr": "يا شهيد أصلح سري وعلانيتي"},
    {"name": "الْحَقّ", "meaning": "الثابت الوجود الدائم الذي لا يزول، وجوده ضروري حتمي", "benefit": "يُثبّت القلب على الحق والصواب", "dhikr": "يا حق اهدني للحق وثبّتني عليه"},
    {"name": "الْوَكِيل", "meaning": "الكافي لمن توكل عليه، يتولى أمور عباده المتوكلين", "benefit": "يُريح القلب من الهموم بالتوكل", "dhikr": "يا وكيل عليك توكلت فاكفني"},
    {"name": "الْقَوِيّ", "meaning": "الكامل القوة الذي لا يعجزه شيء ولا تنقص قوته أبداً", "benefit": "يُقوّي الضعيف ويُعين على الطاعة", "dhikr": "يا قوي قوّني على طاعتك"},
    {"name": "الْمَتِين", "meaning": "الشديد القوة الذي لا يلحقه تعب ولا نصب ولا عجز", "benefit": "يمنح الثبات والصمود في الشدائد", "dhikr": "يا متين أمدّني بقوة من عندك"},
    {"name": "الْوَلِيّ", "meaning": "يتولى عباده المؤمنين بالنصر والحفظ والتوفيق والمحبة", "benefit": "يجعل الله تعالى وليّه وناصره", "dhikr": "يا وليّ تولّني بوليّتك"},
    {"name": "الْحَمِيد", "meaning": "المحمود في ذاته وصفاته وأفعاله، يستحق الحمد مطلقاً", "benefit": "يُكثّر من حمد الله وشكره", "dhikr": "يا حميد لك الحمد كما ينبغي لجلالك"},
    {"name": "الْمُحْصِي", "meaning": "يحصي كل شيء دقيقاً وجليلاً ولا يفوته شيء مهما صغر", "benefit": "يُدقّق في الأعمال ويتحرى الإخلاص", "dhikr": "يا محصي لا تحصِ عليّ ذنوبي"},
    {"name": "الْمُبْدِئ", "meaning": "أوجد الخلق من العدم ابتداءً بلا مثال سابق", "benefit": "التفكر في بديع الخلق يزيد الإيمان", "dhikr": "يا مبدئ ابدأ بي بالخير"},
    {"name": "الْمُعِيد", "meaning": "يُعيد الخلق بعد فنائهم كما بدأهم يوم الحشر", "benefit": "يُجدّد اليقين بالبعث والنشور", "dhikr": "يا معيد أعد علينا أيام الخير"},
    {"name": "الْمُحْيِي", "meaning": "يُحيي الأجساد وكذلك يُحيي القلوب بالهداية والنور", "benefit": "إحياء القلب بالإيمان والذكر", "dhikr": "يا محيي أحيِ قلبي بذكرك"},
    {"name": "الْمُمِيت", "meaning": "يُميت من يشاء وقت يشاء، كل نفس ذائقة الموت", "benefit": "يُجدّد استعداد القلب للآخرة", "dhikr": "يا مميت اجعل خير أعمالي خواتيمها"},
    {"name": "الْحَيّ", "meaning": "الحي الدائم الذي لا يموت، حياته كاملة لا تشبه حياة المخلوقين", "benefit": "اليقين بأن الله حيّ يسمع ويرى دائماً", "dhikr": "يا حي يا قيوم برحمتك أستغيث"},
    {"name": "الْقَيُّوم", "meaning": "القائم بنفسه الذي يقوم بأمر كل مخلوق ويمسك السماوات والأرض", "benefit": "يمنح الاستقرار والثبات في كل أمر", "dhikr": "يا قيوم أقم حياتي على طاعتك"},
    {"name": "الْوَاجِد", "meaning": "الغني الذي لا يفتقر لشيء، يجد ما يشاء متى يشاء", "benefit": "الرضا بما أعطاه الله والقناعة", "dhikr": "يا واجد أغنني بفضلك"},
    {"name": "الْمَاجِد", "meaning": "الواسع الكرم الشريف الذات، متكامل في الشرف والكرم", "benefit": "التعلق بالله وحده طلباً للشرف", "dhikr": "يا ماجد أكرمني من فضلك"},
    {"name": "الْوَاحِد", "meaning": "المتفرد في ذاته وصفاته لا شريك له ولا نظير ولا مثيل", "benefit": "ترسيخ التوحيد وإخلاص العبادة لله", "dhikr": "يا واحد اجعلني لك وحدك"},
    {"name": "الصَّمَد", "meaning": "الذي يصمد إليه الخلق في حوائجهم، الكامل الذي لا يحتاج أحداً", "benefit": "الاعتماد على الله وحده في كل أمر", "dhikr": "يا صمد إليك أصمد في كل حاجتي"},
    {"name": "الْقَادِر", "meaning": "القادر على كل شيء، لا يعجزه شيء في السماوات ولا في الأرض", "benefit": "يُعين على الأمور الصعبة بالتوكل", "dhikr": "يا قادر اقدر لي الخير حيث كان"},
    {"name": "الْمُقْتَدِر", "meaning": "البالغ في القدرة، نافذ الحكم بكل شيء لا يمانعه شيء", "benefit": "يمنح الثقة بقدرة الله على نصرته", "dhikr": "يا مقتدر اقتدر لي على من ظلمني"},
    {"name": "الْمُقَدِّم", "meaning": "يُقدّم من يشاء بالرتبة والشرف والنصر والهداية", "benefit": "الطلب من الله التقدم في الخير", "dhikr": "يا مقدم قدّمني في الخيرات"},
    {"name": "الْمُؤَخِّر", "meaning": "يُؤخّر من يشاء، يُأخّر الأجل والعقوبة بحكمته وعدله", "benefit": "الرضا بقدر الله وتوقيته الحكيم", "dhikr": "يا مؤخر أخّر عنّي كل ضر وأذى"},
    {"name": "الْأَوَّل", "meaning": "الأول الذي ليس قبله شيء، وجوده بلا بداية", "benefit": "يُرسّخ عقيدة أزلية الله وسبقه لكل شيء", "dhikr": "يا أول أنت المبتدأ وإليك المرجع"},
    {"name": "الْآخِر", "meaning": "الآخر الذي ليس بعده شيء، يبقى بعد فناء الكون كله", "benefit": "يُجعل الله الغاية والمآل لا الدنيا", "dhikr": "يا آخر اجعل آخر أعمالي خيرها"},
    {"name": "الظَّاهِر", "meaning": "الظاهر بآياته ودلائله على وجوده في كل مخلوق", "benefit": "يزيد اليقين برؤية آثار الله في الكون", "dhikr": "يا ظاهر أظهر لي الحق وانصرني"},
    {"name": "الْبَاطِن", "meaning": "المحتجب بعظمته عن إدراك الأبصار، الخبير بكل خفية", "benefit": "يُصلح السر والباطن", "dhikr": "يا باطن اطّلع على ما أخفيه فأصلحه"},
    {"name": "الْوَالِي", "meaning": "يتولى تدبير أمور الخلق وحده لا شريك له في الولاية", "benefit": "التسليم لله في تدبير الأمور", "dhikr": "يا والي تولّ أمري بخير"},
    {"name": "الْمُتَعَالِ", "meaning": "المتعالي بجلاله وعظمته فوق كل شيء وكل وصف", "benefit": "يُعلّم القلب التواضع لله وحده", "dhikr": "يا متعال تعاليت عن كل نقص"},
    {"name": "الْبَرّ", "meaning": "الكثير الإحسان والعطاء، يُحسن لعباده أكثر مما يستحقون", "benefit": "يُكثّر من الإحسان للناس", "dhikr": "يا برّ برّ بي وبأهلي"},
    {"name": "التَّوَّاب", "meaning": "يقبل توبة عباده ويرجع إليهم برحمته مهما أذنبوا", "benefit": "يفتح باب الأمل في التوبة دائماً", "dhikr": "يا تواب تب عليّ وتقبّل توبتي"},
    {"name": "الْمُنْتَقِم", "meaning": "ينتقم من أعدائه الذين عصوه وأصرّوا على الكفر والظلم", "benefit": "الحذر من الذنوب والظلم والطغيان", "dhikr": "يا منتقم انتقم لي من الظالمين"},
    {"name": "الْعَفُوّ", "meaning": "يمحو الذنوب ويتجاوز عن السيئات ويُسقطها كأنها لم تكن", "benefit": "يُيسّر العفو وترك الأحقاد", "dhikr": "يا عفو عفو عني واعف عن ذنوبي"},
    {"name": "الرَّؤُوف", "meaning": "شديد الرحمة بعباده، رأفته تُدفع بها المحن والبلايا", "benefit": "يُليّن القلب القسي ويجلب الرحمة", "dhikr": "يا رؤوف أنعم عليّ برأفتك"},
    {"name": "مَالِكُ الْمُلْك", "meaning": "يتصرف في ملكه كيف يشاء يُعطي ويمنع ويعزّ ويذل", "benefit": "الزهد في الدنيا والتوجه لمالكها الحقيقي", "dhikr": "يا مالك الملك اجعلني في ملكك راضياً"},
    {"name": "ذُو الْجَلَالِ وَالْإِكْرَام", "meaning": "الجامع لصفات الجلال والجمال والإكرام لعباده", "benefit": "يُعظّم الله في القلب ويملؤه هيبةً ومحبةً", "dhikr": "يا ذا الجلال والإكرام أكرمني بعفوك"},
    {"name": "الْمُقْسِط", "meaning": "العادل في حكمه وقضائه لا يظلم أحداً مثقال ذرة", "benefit": "يُعين على العدل في التعامل مع الناس", "dhikr": "يا مقسط اقسط بيني وبين خصومي"},
    {"name": "الْجَامِع", "meaning": "يجمع الخلق ليوم الحساب، ويجمع بين المتفرقين", "benefit": "الأمل في جمع الأحبة في الآخرة", "dhikr": "يا جامع اجمعني بأحبتي في الجنة"},
    {"name": "الْغَنِيّ", "meaning": "الغني الذي لا يحتاج لأحد وكل الخلق محتاجون إليه", "benefit": "يُغني القلب عن التعلق بالدنيا والناس", "dhikr": "يا غني أغنني بفضلك عمن سواك"},
    {"name": "الْمُغْنِي", "meaning": "يُغني من يشاء من عباده بالمال والقناعة والرضا", "benefit": "يُفتح به باب الغنى الحقيقي وهو القناعة", "dhikr": "يا مغني أغنني بالقناعة والرضا"},
    {"name": "الْمَانِع", "meaning": "يمنع عن عباده ما يضرهم بحكمته وما يمنعه خير لهم", "benefit": "الرضا بما منعه الله لأنه خير", "dhikr": "يا مانع امنع عني كل ضر وشر"},
    {"name": "الضَّارّ", "meaning": "يضر من يشاء بعدله وحكمته، الضر والنفع بيده وحده", "benefit": "الحذر من أسباب الضر والبعد عن المعاصي", "dhikr": "يا ضار اصرف عني كل ضر"},
    {"name": "النَّافِع", "meaning": "ينفع من يشاء كيف يشاء، كل نفع في الكون مصدره الله", "benefit": "يُسبّب النفع ويُيسّر الخير", "dhikr": "يا نافع انفعني بما علّمتني"},
    {"name": "النُّور", "meaning": "نور السماوات والأرض، يهدي من يشاء لنوره ويُنير القلوب", "benefit": "يُنير القلب والبصيرة والطريق", "dhikr": "يا نور نوّر قلبي وبصيرتي"},
    {"name": "الْهَادِي", "meaning": "يهدي من يشاء للحق والصواب والصراط المستقيم", "benefit": "يُثبّت على الهداية ويزيد منها", "dhikr": "يا هادي اهدني وثبّتني على الهدى"},
    {"name": "الْبَدِيع", "meaning": "مبتكر الأشياء بلا مثال سابق، بديع في خلقه وتدبيره", "benefit": "يُبدع الحلول والأفكار في القلب", "dhikr": "يا بديع ابدع لي من حيث لا أعلم"},
    {"name": "الْبَاقِي", "meaning": "الدائم الوجود الذي لا يفنى، يبقى بعد فناء كل مخلوق", "benefit": "الزهد في الفاني والتعلق بالباقي", "dhikr": "يا باقي اجعل عملي خالصاً لوجهك الباقي"},
    {"name": "الْوَارِث", "meaning": "يرث الأرض وما عليها بعد فناء الخلق، له الملك وحده", "benefit": "الزهد في المال وتذكر الفناء", "dhikr": "يا وارث أورثني الجنة"},
    {"name": "الرَّشِيد", "meaning": "يُدبّر أمور خلقه بحكمة بالغة وصواب تام بلا خطأ", "benefit": "يُسدّد الرأي ويُقوّم السلوك", "dhikr": "يا رشيد أرشدني إلى ما تحب وترضى"},
    {"name": "الصَّبُور", "meaning": "لا يعجل بالعقوبة لمن عصاه، يُمهل ولا يُهمل", "benefit": "يمنح الصبر على الأذى وعلى الطاعة", "dhikr": "يا صبور اجعلني من الصابرين المحتسبين"},
]

# ==================== من هو؟ (تخمين الصحابي) ====================
SAHABA_QUIZ = [
    {"name": "أبو بكر الصديق", "hints": ["أول الخلفاء الراشدين", "رفيق النبي ﷺ في الهجرة", "لقّبه النبي ﷺ بالصديق"], "fact": "قال النبي ﷺ: لو كنت متخذاً خليلاً لاتخذت أبا بكر خليلاً", "bio": "عبدالله بن عثمان القرشي، أقرب الناس للنبي ﷺ وأول الخلفاء. أعتق بلالاً وغيره من المستضعفين. أنفق ماله كله في سبيل الله. حكم سنتين وثلاثة أشهر وتوفي عام 13هـ."},
    {"name": "عمر بن الخطاب", "hints": ["لقبه الفاروق", "ثاني الخلفاء الراشدين", "في عهده فُتحت القدس"], "fact": "قال النبي ﷺ: لو كان بعدي نبي لكان عمر", "bio": "عمر بن الخطاب العدوي، الفاروق الذي فرّق بين الحق والباطل. أسلم فأعزّ الله به الإسلام. فتح في عهده العراق والشام ومصر وفارس. اشتُهر بعدله حتى قال: متى استعبدتم الناس وقد ولدتهم أمهاتهم أحراراً."},
    {"name": "عثمان بن عفان", "hints": ["لُقّب بذي النورين", "ثالث الخلفاء الراشدين", "جمع القرآن في مصحف واحد"], "fact": "قال النبي ﷺ: ما ضرّ عثمان ما عمل بعد اليوم", "bio": "عثمان بن عفان الأموي، ذو النورين لتزوجه ابنتي النبي ﷺ. جهّز جيش العسرة بنفسه. جمع المسلمين على مصحف موحد. اشتُهر بالحياء والكرم. استُشهد وهو يقرأ القرآن عام 35هـ."},
    {"name": "علي بن أبي طالب", "hints": ["ابن عم النبي ﷺ", "رابع الخلفاء الراشدين", "أول من أسلم من الصبيان"], "fact": "قال النبي ﷺ: أنت مني وأنا منك", "bio": "علي بن أبي طالب الهاشمي، ابن عم النبي ﷺ وزوج ابنته فاطمة. أسلم وهو صغير ونام في فراش النبي ﷺ ليلة الهجرة. اشتُهر بالشجاعة والعلم والزهد. استُشهد عام 40هـ."},
    {"name": "أبو هريرة", "hints": ["أكثر الصحابة رواية للحديث", "أسلم عام خيبر", "كان يُلازم النبي ﷺ دائماً"], "fact": "روى أكثر من 5000 حديث عن النبي ﷺ", "bio": "عبدالرحمن بن صخر الدوسي، كنّاه النبي ﷺ أبا هريرة لهرّة صغيرة كان يحملها. أسلم عام 7هـ ولازم النبي ﷺ 3 سنوات فحفظ أكثر حديث. كان فقيراً متواضعاً من أهل الصُّفّة."},
    {"name": "بلال بن رباح", "hints": ["أول مؤذن في الإسلام", "كان عبداً فأعتقه أبو بكر", "صبر على التعذيب يقول: أحد أحد"], "fact": "قال النبي ﷺ: سمعت خشخشة نعليك في الجنة يا بلال", "bio": "بلال الحبشي، أسلم مبكراً فعذّبه سيده أمية بن خلف على الرمضاء يقول: أحد أحد. فاشتراه أبو بكر وأعتقه. أصبح أول مؤذن في الإسلام. رفض الأذان بعد وفاة النبي ﷺ من شدة حزنه."},
    {"name": "خالد بن الوليد", "hints": ["لُقّب بسيف الله المسلول", "لم يُهزم في معركة قط", "أسلم قبل فتح مكة"], "fact": "قال النبي ﷺ: نعم عبدالله وأخو العشيرة وسيف من سيوف الله", "bio": "خالد بن الوليد المخزومي، قائد فذّ قاد أكثر من 100 معركة ولم يُهزم. أسلم عام 8هـ. قاد المسلمين في اليرموك وفتوح الشام والعراق. توفي في فراشه عام 21هـ ولم يكن في جسده موضع إلا وفيه أثر سيف أو رمح."},
    {"name": "عائشة بنت أبي بكر", "hints": ["أم المؤمنين وابنة أبي بكر", "روت آلاف الأحاديث", "لقّبها النبي ﷺ بالحميراء"], "fact": "قال النبي ﷺ: فضل عائشة على النساء كفضل الثريد على سائر الطعام", "bio": "عائشة الصديقة بنت أبي بكر، أم المؤمنين وأعلم نساء الأمة. روت 2210 حديثاً. كانت مرجعاً للصحابة في الفقه والطب والشعر والتاريخ. توفيت عام 58هـ ودُفنت في البقيع."},
    {"name": "سلمان الفارسي", "hints": ["أصله من فارس وبحث عن الحق", "صاحب فكرة حفر الخندق", "قال عنه النبي ﷺ: سلمان منا آل البيت"], "fact": "رحل من فارس عبر الشام والعراق بحثاً عن الدين الحق حتى وجد النبي ﷺ", "bio": "سلمان الفارسي الإصبهاني، رحل من فارس طويلاً يبحث عن النبي الأخير حتى وجده في المدينة. هو صاحب فكرة الخندق. اشتُهر بالعلم والزهد. عاش طويلاً وتوفي في المدائن والياً عليها."},
    {"name": "معاذ بن جبل", "hints": ["أعلم الصحابة بالحلال والحرام", "بعثه النبي ﷺ معلماً لليمن", "توفي في طاعون عمواس شاباً"], "fact": "قال النبي ﷺ: أعلم أمتي بالحلال والحرام معاذ بن جبل", "bio": "معاذ بن جبل الأنصاري الخزرجي، أسلم شاباً وصار أعلم الصحابة بالفقه. بعثه النبي ﷺ إلى اليمن معلماً وقاضياً. توفي في طاعون عمواس عام 18هـ وعمره 33 سنة. قال عند موته: مرحباً بالموت زائراً حبيباً جاء على فاقة."},
    {"name": "خديجة بنت خويلد", "hints": ["أول زوجات النبي ﷺ", "أول من آمن برسالة النبي ﷺ", "دعمت الإسلام بمالها"], "fact": "قال النبي ﷺ: آمنت بي إذ كفر بي الناس وصدّقتني إذ كذّبني الناس", "bio": "خديجة الكبرى بنت خويلد القرشية، أم المؤمنين وأول من أسلم. كانت تاجرةً ثريةً زوّجت النبي ﷺ نفسها. أنفقت كل مالها في سبيل الله. ولدت للنبي ﷺ ستة أبناء. توفيت قبل الهجرة وحزن عليها النبي ﷺ كثيراً."},
    {"name": "عبدالله بن مسعود", "hints": ["أول من جهر بتلاوة القرآن في مكة", "يشبه النبي ﷺ في هديه وسمته", "من أعلم الصحابة بالقرآن والتفسير"], "fact": "قال النبي ﷺ: من أحب أن يقرأ القرآن غضاً فليقرأه على قراءة ابن أم عبد", "bio": "عبدالله بن مسعود الهذلي، رعى غنم ابن مسعود ثم أسلم مبكراً. كان يشبه النبي ﷺ في هديه. أجاز له النبي ﷺ دخول بيته متى شاء. من أعلم الصحابة بالقرآن والفقه. توفي بالمدينة عام 32هـ."},
    {"name": "عبدالرحمن بن عوف", "hints": ["من العشرة المبشرين بالجنة", "هاجر مرتين إلى الحبشة والمدينة", "آثر الأنصار على نفسه في أموالهم"], "fact": "قال النبي ﷺ له: بشّرك الله بالجنة", "bio": "عبدالرحمن بن عوف الزهري، من أوائل المسلمين والعشرة المبشرين بالجنة. جاء المدينة لا يملك شيئاً فصار من أغنى أهلها. تصدّق بأموال طائلة في سبيل الله. قال النبي ﷺ إنه يدخل الجنة حبواً لكثرة ماله."},
    {"name": "أبو ذر الغفاري", "hints": ["من أوائل المسلمين الأربعة أو الخمسة", "اشتُهر بشدة الزهد والصدق", "لقّبه النبي ﷺ بصادق اللهجة"], "fact": "قال النبي ﷺ: ما أظلّت الخضراء ولا أقلّت الغبراء من رجل أصدق لهجةً من أبي ذر", "bio": "جندب بن جنادة الغفاري، أسلم مبكراً قبل الهجرة. اشتُهر بالزهد الشديد في الدنيا والصراحة. قاتل الظلم الاجتماعي بشدة. توفي منفياً في الربذة عام 32هـ وحده تقريباً بوصيته."},
    {"name": "طلحة بن عبيدالله", "hints": ["من العشرة المبشرين بالجنة", "وقى النبي ﷺ بجسده في أُحد", "لُقّب بطلحة الجود"], "fact": "قال النبي ﷺ: من أراد أن ينظر إلى شهيد يمشي على الأرض فلينظر إلى طلحة", "bio": "طلحة بن عبيدالله التيمي، من السابقين للإسلام والعشرة المبشرين. في يوم أُحد وقى النبي ﷺ بيده فشُلّت أصابعه. اشتُهر بالكرم الشديد حتى لُقّب طلحة الجود وطلحة الفيّاض. استُشهد في موقعة الجمل."},
    {"name": "الزبير بن العوام", "hints": ["حواري النبي ﷺ", "ابن عمة النبي ﷺ وأول من سلّ سيفاً في الإسلام", "من العشرة المبشرين بالجنة"], "fact": "قال النبي ﷺ: لكل نبي حواري وحواريّ الزبير", "bio": "الزبير بن العوام الأسدي، ابن عمة النبي ﷺ صفية. أسلم وعمره 15 سنة وهو أول من سلّ السيف في الإسلام. شارك في كل الغزوات. استُشهد في موقعة الجمل عام 36هـ."},
    {"name": "سعد بن أبي وقاص", "hints": ["أول من رمى بسهم في الإسلام", "خال النبي ﷺ", "من العشرة المبشرين بالجنة"], "fact": "قال النبي ﷺ: ارمِ سعد فداك أبي وأمي", "bio": "سعد بن أبي وقاص الزهري، من السابقين للإسلام والعشرة المبشرين. قائد فتح العراق وموقعة القادسية. اشتُهر بإجابة الدعاء. عاش طويلاً وتوفي آخر المبشرين بالجنة عام 55هـ."},
    {"name": "أبو عبيدة بن الجراح", "hints": ["أمين هذه الأمة", "قائد فتوح الشام", "توفي في طاعون عمواس"], "fact": "قال النبي ﷺ: لكل أمة أمين وأمين هذه الأمة أبو عبيدة بن الجراح", "bio": "عامر بن عبدالله الفهري، من السابقين والعشرة المبشرين. قاد فتوح الشام وفتح دمشق. كان متواضعاً زاهداً يعيش كالفقراء رغم منصبه. توفي في طاعون عمواس عام 18هـ بعد دعائه أن يموت مع جنده."},
    {"name": "حمزة بن عبدالمطلب", "hints": ["عم النبي ﷺ ورضيعه", "لُقّب بأسد الله", "استُشهد في أُحد"], "fact": "قال النبي ﷺ: سيد الشهداء حمزة بن عبدالمطلب", "bio": "حمزة بن عبدالمطلب الهاشمي، عم النبي ﷺ وأخوه من الرضاعة. كان من أشجع العرب. أسلم في السنة الثانية للبعثة. اشتُهر بالشجاعة الفائقة في المعارك. استُشهد في أُحد ومثّل به المشركون فحزن عليه النبي ﷺ كثيراً."},
    {"name": "أنس بن مالك", "hints": ["خادم النبي ﷺ عشر سنين", "آخر من مات من الصحابة", "روى آلاف الأحاديث"], "fact": "قال النبي ﷺ: اللهم أكثر ماله وولده وأدخله الجنة", "bio": "أنس بن مالك الأنصاري، خدم النبي ﷺ عشر سنوات من سن 10 سنوات. روى 2286 حديثاً. استُجيبت فيه دعوة النبي ﷺ فعاش 100 سنة وكثر ماله وولده. توفي عام 93هـ وهو آخر الصحابة وفاةً في البصرة."},
    {"name": "عبدالله بن عمر", "hints": ["ابن عمر بن الخطاب", "اشتُهر باتباع سنة النبي ﷺ بدقة", "روى كثيراً من الأحاديث"], "fact": "كان يقف في كل مكان وقف فيه النبي ﷺ ويفعل ما فعله حتى في التفاصيل الصغيرة", "bio": "عبدالله بن عمر القرشي، من أكثر الصحابة اتباعاً للسنة. أسلم صغيراً ورُدّ عن بدر لصغر سنه. اشتُهر بالورع الشديد والزهد. روى 2630 حديثاً. توفي بمكة عام 73هـ آخر من مات من مشاهير الصحابة."},
    {"name": "أبو موسى الأشعري", "hints": ["من اليمن وهاجر إلى الحبشة", "اشتُهر بحسن صوته بالقرآن", "قال النبي ﷺ: أُعطي مزماراً من مزامير داود"], "fact": "قال النبي ﷺ لما سمع صوته: لو رأيتني وأنا أستمع لقراءتك البارحة", "bio": "عبدالله بن قيس الأشعري، هاجر إلى الحبشة ثم قدم مع جعفر بن أبي طالب. اشتُهر بجمال الصوت في القرآن. ولّاه عمر على البصرة وعلي على الكوفة. توفي عام 44هـ."},
    {"name": "جعفر بن أبي طالب", "hints": ["ابن عم النبي ﷺ", "لقّبه النبي ﷺ بذي الجناحين", "قاد المسلمين في مؤتة حتى استُشهد"], "fact": "قال النبي ﷺ: أشبهت خَلقي وخُلُقي", "bio": "جعفر بن أبي طالب الهاشمي، ابن عم النبي ﷺ. قاد الهجرة الأولى للحبشة وأدهش النجاشي بتلاوة سورة مريم. استُشهد في مؤتة وقد قُطعت يداه فحمل الراية بعضديه، فسُمّي ذا الجناحين."},
    {"name": "أبو الدرداء", "hints": ["تأخّر إسلامه ثم صار عالماً", "اشتُهر بالحكمة والزهد", "قاضي دمشق في عهد عثمان"], "fact": "قال: كنت تاجراً فلما جاء الإسلام جمعت بين التجارة والعبادة فلم يتم لي", "bio": "عويمر بن زيد الأنصاري، أسلم متأخراً لكنه صار من أعلم الصحابة. اشتُهر بالحكمة والزهد. قاضي دمشق. من أقواله: تعلموا العلم قبل أن يُرفع ورفعه موت العلماء."},
    {"name": "حذيفة بن اليمان", "hints": ["صاحب سر النبي ﷺ في المنافقين", "عرف المنافقين بأسمائهم", "اشتُهر بالفراسة والذكاء"], "fact": "كان الصحابة يسألون النبي ﷺ عن الخير وكان حذيفة يسأله عن الشر ليتجنبه", "bio": "حذيفة بن اليمان العبسي، صاحب سر النبي ﷺ في المنافقين. أسرّ إليه النبي ﷺ بأسماء المنافقين. فتح المدائن وهمدان. توفي عام 36هـ بعد مقتل عثمان بأيام وقد كان ينتظر موته."},
    {"name": "عمرو بن العاص", "hints": ["فاتح مصر", "كان من ألمع العرب ذكاءً", "أسلم قبل فتح مكة مع خالد بن الوليد"], "fact": "قال عمر: ما ينبغي لأبي عبدالله أن يُعصى", "bio": "عمرو بن العاص السهمي، من أذكى الصحابة وأمهرهم في الحرب والسياسة. أسلم عام 8هـ. فتح مصر بجيش 4000 فقط. بنى الفسطاط أول مدينة إسلامية في مصر. توفي والياً على مصر عام 43هـ."},
    {"name": "عمار بن ياسر", "hints": ["من أوائل المعذّبين في الإسلام", "أُمّه سُمية أول شهيدة في الإسلام", "بشّره النبي ﷺ بالجنة"], "fact": "قال النبي ﷺ: تقتلك الفئة الباغية وآخر زادك من الدنيا ضياح لبن", "bio": "عمار بن ياسر العنسي، من أوائل المسلمين. عُذّب هو وأبوه وأمه حتى استُشهدت أمه سُمية أول شهيدة. صبر وصبر والنبي ﷺ يقول لهم: صبراً آل ياسر. استُشهد في صفين عام 37هـ."},
    {"name": "المقداد بن الأسود", "hints": ["أول فارس قاتل في سبيل الله في الإسلام", "من السابقين للإسلام", "موقفه في بدر رفع معنويات المسلمين"], "fact": "قال في بدر للنبي ﷺ: امضِ لأمر الله فنحن معك لن نقول كما قالت بنو إسرائيل لموسى", "bio": "المقداد بن عمرو الكندي، أول فارس في الإسلام. من السابقين المجاهدين. موقفه الشجاع في بدر حين طمأن النبي ﷺ بأنهم سيقاتلون معه أثّر أثراً بالغاً. توفي عام 33هـ."},
    {"name": "صهيب الرومي", "hints": ["لُقّب بالرومي لأسره في الروم صغيراً", "فدى نفسه بماله ليهاجر", "قال النبي ﷺ عنه: ربح البيع أبا يحيى"], "fact": "قال النبي ﷺ لما هاجر وترك ماله لقريش: ربح البيع أبا يحيى", "bio": "صهيب بن سنان النمري، وُلد لأب عربي لكن أُسر صغيراً في بلاد الروم فنشأ فيها. أسلم مبكراً. أراد المهاجرة فمنعته قريش من ماله فتركه لهم وهاجر بلا شيء. اشتُهر بالكرم والشجاعة."},
]
# ==================== الأسئلة الدينية اليومية ====================
DAILY_QUESTIONS = [
    {"q": "كم عدد أركان الإسلام؟", "options": ["3", "4", "5", "6"], "answer": "5", "explain": "الشهادتان، الصلاة، الزكاة، الصوم، الحج"},
    {"q": "ما هي أطول سورة في القرآن؟", "options": ["آل عمران", "النساء", "البقرة", "المائدة"], "answer": "البقرة", "explain": "سورة البقرة هي أطول سور القرآن بـ 286 آية"},
    {"q": "في أي شهر نزل القرآن الكريم؟", "options": ["رجب", "شعبان", "رمضان", "محرم"], "answer": "رمضان", "explain": "قال تعالى: شهر رمضان الذي أنزل فيه القرآن"},
    {"q": "كم عدد أنبياء الله المذكورين في القرآن؟", "options": ["20", "25", "30", "35"], "answer": "25", "explain": "ذكر الله 25 نبياً في القرآن الكريم"},
    {"q": "ما هو اسم والد النبي إبراهيم عليه السلام؟", "options": ["آزر", "تارح", "ناحور", "لاوي"], "answer": "آزر", "explain": "ذكر الله تعالى: وإذ قال إبراهيم لأبيه آزر"},
    {"q": "كم عدد سور القرآن الكريم؟", "options": ["110", "112", "114", "116"], "answer": "114", "explain": "القرآن الكريم يتكون من 114 سورة"},
    {"q": "ما هي أقصر سورة في القرآن؟", "options": ["الفلق", "الناس", "الكوثر", "الإخلاص"], "answer": "الكوثر", "explain": "سورة الكوثر هي أقصر سور القرآن بـ 3 آيات"},
    {"q": "في أي عام هاجر النبي ﷺ إلى المدينة؟", "options": ["620م", "622م", "624م", "626م"], "answer": "622م", "explain": "الهجرة النبوية كانت عام 622 ميلادية"},
    {"q": "ما هو أول مسجد بُني في الإسلام؟", "options": ["مسجد قباء", "المسجد النبوي", "المسجد الحرام", "مسجد الفتح"], "answer": "مسجد قباء", "explain": "مسجد قباء هو أول مسجد بُني في الإسلام عند هجرة النبي ﷺ"},
    {"q": "كم عدد ركعات صلاة الفجر؟", "options": ["2", "3", "4", "1"], "answer": "2", "explain": "صلاة الفجر ركعتان فريضة"},
    {"q": "ما معنى كلمة قرآن؟", "options": ["النور", "الهدى", "القراءة والتلاوة", "الحكمة"], "answer": "القراءة والتلاوة", "explain": "القرآن مشتق من القراءة والتلاوة"},
    {"q": "ما هو آخر نبي أُرسل للبشرية؟", "options": ["عيسى", "موسى", "إبراهيم", "محمد ﷺ"], "answer": "محمد ﷺ", "explain": "محمد ﷺ خاتم الأنبياء والمرسلين"},
    {"q": "أي سورة تُسمى قلب القرآن؟", "options": ["الفاتحة", "يس", "الكهف", "البقرة"], "answer": "يس", "explain": "قال النبي ﷺ: إن لكل شيء قلباً وقلب القرآن يس"},
    {"q": "كم عدد أركان الإيمان؟", "options": ["4", "5", "6", "7"], "answer": "6", "explain": "الإيمان بالله وملائكته وكتبه ورسله واليوم الآخر والقدر"},
    {"q": "ما هي الصلاة التي لها أذانان؟", "options": ["الفجر", "الظهر", "العصر", "المغرب"], "answer": "الفجر", "explain": "صلاة الفجر لها أذانان: الأول للتنبيه والثاني لوقت الصلاة"},
    {"q": "ما هو الركن الأول في الكعبة الذي يبدأ منه الطواف؟", "options": ["الركن الشامي", "الركن اليماني", "الحجر الأسود", "باب الكعبة"], "answer": "الحجر الأسود", "explain": "يبدأ الطواف من الحجر الأسود ويُحاذى في كل شوط"},
    {"q": "كم عدد الأشهر الحُرُم في الإسلام؟", "options": ["2", "3", "4", "5"], "answer": "4", "explain": "ذو القعدة وذو الحجة والمحرم ورجب"},
    {"q": "من هو النبي الذي بنى الكعبة مع ابنه؟", "options": ["نوح", "إبراهيم", "إسماعيل", "إبراهيم وإسماعيل معاً"], "answer": "إبراهيم وإسماعيل معاً", "explain": "قال تعالى: وإذ يرفع إبراهيم القواعد من البيت وإسماعيل"},
    {"q": "ما هي الليلة التي يُقال إن القرآن نزل فيها؟", "options": ["ليلة الإسراء", "ليلة القدر", "ليلة المعراج", "ليلة النصف من شعبان"], "answer": "ليلة القدر", "explain": "قال تعالى: إنا أنزلناه في ليلة القدر"},
    {"q": "كم مرة ذُكر اسم النبي محمد ﷺ في القرآن؟", "options": ["2", "3", "4", "5"], "answer": "4", "explain": "ذُكر اسم محمد ﷺ 4 مرات في القرآن الكريم"},
    {"q": "ما هي السورة التي تبدأ بالبسملة مرتين؟", "options": ["النمل", "الفاتحة", "الأعراف", "يوسف"], "answer": "النمل", "explain": "سورة النمل فيها البسملة في أولها وفي وسطها ضمن قصة سليمان"},
    {"q": "كم عدد سجدات التلاوة في القرآن؟", "options": ["12", "14", "15", "16"], "answer": "15", "explain": "في القرآن 15 موضع سجدة تلاوة"},
    {"q": "من هو الصحابي الذي جمع القرآن في عهد عثمان؟", "options": ["زيد بن ثابت", "ابن مسعود", "أبي بن كعب", "علي بن أبي طالب"], "answer": "زيد بن ثابت", "explain": "أشرف زيد بن ثابت على جمع المصحف العثماني"},
    {"q": "ما هي السورة التي تُقرأ في كل ركعة صلاة؟", "options": ["البقرة", "الإخلاص", "الفاتحة", "الكوثر"], "answer": "الفاتحة", "explain": "قال النبي ﷺ: لا صلاة لمن لم يقرأ بفاتحة الكتاب"},
    {"q": "في أي مدينة وُلد النبي محمد ﷺ؟", "options": ["المدينة", "الطائف", "مكة المكرمة", "القدس"], "answer": "مكة المكرمة", "explain": "وُلد النبي ﷺ في مكة المكرمة عام الفيل"},
    {"q": "كم سنة استغرقت نزول القرآن الكريم؟", "options": ["20 سنة", "23 سنة", "25 سنة", "30 سنة"], "answer": "23 سنة", "explain": "نزل القرآن منجماً على مدى 23 سنة"},
    {"q": "ما هي السورة التي تعدل ثلث القرآن؟", "options": ["الفاتحة", "يس", "الإخلاص", "الملك"], "answer": "الإخلاص", "explain": "قال النبي ﷺ: قل هو الله أحد تعدل ثلث القرآن"},
    {"q": "كم ركعة في صلاة التراويح في رمضان؟", "options": ["8", "11", "20", "كل هذه واردة"], "answer": "كل هذه واردة", "explain": "8 و11 و20 ركعة كلها واردة عن السلف"},
    {"q": "ما هو المسجد الذي يُقال إن الصلاة فيه بألف صلاة؟", "options": ["المسجد الأقصى", "المسجد النبوي", "المسجد الحرام", "مسجد قباء"], "answer": "المسجد النبوي", "explain": "صلاة في المسجد النبوي بألف صلاة فيما سواه"},
    {"q": "من هو أول من أسلم من الرجال؟", "options": ["عمر بن الخطاب", "علي بن أبي طالب", "أبو بكر الصديق", "عثمان بن عفان"], "answer": "أبو بكر الصديق", "explain": "أبو بكر الصديق أول من أسلم من الرجال البالغين"},
    {"q": "ما هي عقوبة المرتد في الفقه الإسلامي؟", "options": ["السجن", "الغرامة", "الإعدام بعد الاستتابة", "النفي"], "answer": "الإعدام بعد الاستتابة", "explain": "من بدّل دينه فاقتلوه، مع إمهاله للتوبة"},
    {"q": "كم مرة تُصلى صلاة الجمعة في الأسبوع؟", "options": ["مرة", "مرتين", "ثلاث مرات", "يومياً"], "answer": "مرة", "explain": "صلاة الجمعة فرض عين على الرجال مرة أسبوعياً"},
    {"q": "ما هو نصاب الذهب للزكاة؟", "options": ["70 جراماً", "85 جراماً", "100 جرام", "50 جراماً"], "answer": "85 جراماً", "explain": "نصاب الذهب 85 جراماً تقريباً أي 20 مثقالاً"},
    {"q": "ما معنى كلمة الجهاد؟", "options": ["القتال فقط", "بذل الجهد في سبيل الله", "الصبر", "الصلاة"], "answer": "بذل الجهد في سبيل الله", "explain": "الجهاد يشمل جهاد النفس والشيطان والكفر"},
    {"q": "كم عدد أيام عيد الأضحى؟", "options": ["يومان", "ثلاثة أيام", "أربعة أيام", "خمسة أيام"], "answer": "أربعة أيام", "explain": "عيد الأضحى يوم النحر وثلاثة أيام التشريق"},
    {"q": "ما هي السنة التي بُعث فيها النبي ﷺ؟", "options": ["600م", "610م", "615م", "620م"], "answer": "610م", "explain": "بُعث النبي ﷺ عام 610م وعمره 40 سنة"},
    {"q": "من هو الملك الذي أنزل الوحي على النبي ﷺ؟", "options": ["إسرافيل", "ميكائيل", "جبريل", "عزرائيل"], "answer": "جبريل", "explain": "جبريل عليه السلام هو الملك الموكل بالوحي"},
    {"q": "ما هي السورة التي نزلت كاملة دفعة واحدة؟", "options": ["الفاتحة", "يوسف", "البقرة", "الأنعام"], "answer": "الأنعام", "explain": "سورة الأنعام نزلت كاملة دفعة واحدة ومعها سبعون ألف ملك"},
    {"q": "كم سنة دامت الدعوة السرية للإسلام؟", "options": ["سنتين", "ثلاث سنوات", "خمس سنوات", "سبع سنوات"], "answer": "ثلاث سنوات", "explain": "استمرت الدعوة السرية ثلاث سنوات قبل الجهر"},
    {"q": "ما هو المسجد الذي تُضاعف فيه الصلاة بمئة ألف صلاة؟", "options": ["المسجد النبوي", "المسجد الأقصى", "مسجد قباء", "المسجد الحرام"], "answer": "المسجد الحرام", "explain": "الصلاة في المسجد الحرام بمئة ألف صلاة فيما سواه"},
    {"q": "ما هي أول غزوة في الإسلام؟", "options": ["غزوة بدر", "غزوة الأبواء", "غزوة أُحد", "غزوة الخندق"], "answer": "غزوة الأبواء", "explain": "غزوة الأبواء أو ودان هي أول غزوة قادها النبي ﷺ بنفسه"},
    {"q": "كم مرة ذُكر اسم عيسى عليه السلام في القرآن؟", "options": ["15", "25", "33", "50"], "answer": "25", "explain": "ذُكر اسم عيسى عليه السلام 25 مرة في القرآن"},
    {"q": "ما هو الحد الأدنى لصيام رمضان يومياً؟", "options": ["من الفجر للمغرب", "من الشروق للمغرب", "من الفجر للعشاء", "من السحور للإفطار"], "answer": "من الفجر للمغرب", "explain": "يبدأ الصيام من طلوع الفجر الصادق وينتهي بغروب الشمس"},
    {"q": "ما هي السورة التي تُقرأ يوم الجمعة؟", "options": ["الكهف", "يس", "الملك", "السجدة"], "answer": "الكهف", "explain": "قال النبي ﷺ: من قرأ سورة الكهف يوم الجمعة أضاء له النور"},
    {"q": "من هو النبي الذي كلّمه الله مباشرةً بلا واسطة؟", "options": ["إبراهيم", "موسى", "عيسى", "نوح"], "answer": "موسى", "explain": "لُقّب موسى عليه السلام بكليم الله لأن الله كلّمه مباشرة"},
    {"q": "ما هو عدد الآيات في الفاتحة؟", "options": ["5", "6", "7", "8"], "answer": "7", "explain": "الفاتحة سبع آيات وهي السبع المثاني"},
    {"q": "ما هي الزكاة الواجبة في الذهب والفضة؟", "options": ["2%", "2.5%", "5%", "10%"], "answer": "2.5%", "explain": "زكاة الذهب والفضة والأموال ربع العُشر أي 2.5%"},
    {"q": "كم عدد ركعات صلاة الوتر على الأقل؟", "options": ["ركعة واحدة", "ثلاث ركعات", "خمس ركعات", "سبع ركعات"], "answer": "ركعة واحدة", "explain": "أدنى الوتر ركعة واحدة وأكثره إحدى عشرة ركعة"},
    {"q": "من هو أول شهيد في الإسلام من الرجال؟", "options": ["خبّاب بن الأرت", "ياسر بن عامر", "حمزة بن عبدالمطلب", "بلال بن رباح"], "answer": "ياسر بن عامر", "explain": "ياسر بن عامر أول شهيد في الإسلام من الرجال"},
    {"q": "ما هي السورة التي تُسمى سنام القرآن؟", "options": ["الفاتحة", "البقرة", "يس", "الكهف"], "answer": "البقرة", "explain": "قال النبي ﷺ: لكل شيء سنام وسنام القرآن سورة البقرة"},
    {"q": "كم عدد الصلوات المفروضة في اليوم؟", "options": ["3", "4", "5", "6"], "answer": "5", "explain": "الصلوات المفروضة خمس: فجر وظهر وعصر ومغرب وعشاء"},
    {"q": "ما هو المسجد الثالث الذي تُشدّ إليه الرحال؟", "options": ["مسجد قباء", "المسجد الأقصى", "مسجد الخيف", "مسجد النبي في منى"], "answer": "المسجد الأقصى", "explain": "لا تُشدّ الرحال إلا إلى ثلاثة مساجد: الحرام والنبوي والأقصى"},
    {"q": "ما هي السورة المكية التي تبدأ بحروف مقطعة ألم؟", "options": ["البقرة", "آل عمران", "لقمان", "العنكبوت"], "answer": "العنكبوت", "explain": "سورة العنكبوت مكية وتبدأ بـ ألم"},
    {"q": "كم حجة حجّها النبي ﷺ؟", "options": ["حجة واحدة", "حجتان", "ثلاث حجج", "لم يحج"], "answer": "حجة واحدة", "explain": "حجّ النبي ﷺ حجة واحدة وهي حجة الوداع عام 10هـ"},
]

# ==================== تحدي الأسبوع الجماعي ====================
WEEKLY_CHALLENGES = [
    {"q": "من هو أول من أذّن في الإسلام؟", "answer": "بلال", "hint": "صحابي من الحبشة"},
    {"q": "في أي غزوة حُفر الخندق؟", "answer": "الأحزاب", "hint": "تُعرف أيضاً بغزوة الأحزاب"},
    {"q": "ما هو اسم ناقة النبي ﷺ؟", "answer": "القصواء", "hint": "اسمها يبدأ بحرف القاف"},
    {"q": "كم سنة استغرقت غزوات النبي ﷺ؟", "answer": "10", "hint": "من بعد الهجرة حتى الوفاة"},
    {"q": "ما هي أول آية نزلت من القرآن؟", "answer": "اقرأ", "hint": "أول كلمة في سورة العلق"},
]

async def send_daily_challenge(context):
    """تحدي اليوم - 5:00 مساءً بتوقيت الأردن"""
    # تحقق لو اليوم عنده تحدي مسجل ما نعيد
    today = _dt.datetime.now(AMMAN_TZ).strftime("%Y-%m-%d")
    existing = get_today_challenge()
    if existing:
        full_text = existing["full"]
    else:
        # جرب API أولاً
        full_text = None
        topic = _random.choice(DAILY_TOPICS)
        try:
            results = await search_dorar_api(topic)
            if results:
                h = _random.choice(results[:10])
                if len(h["text"].split()) >= 6:
                    full_text = h["text"].strip()
        except:
            pass
        # fallback: أحاديث ثابتة مضمونة
        if not full_text:
            full_text = _random.choice(STATIC_CHALLENGE_HADITHS)
        words = full_text.split()
        answer = words[-1].strip(".,،؟!")
        question_text = " ".join(words[:-1]) + " ..."
        save_today_challenge(question_text, answer, full_text)

    challenge = get_today_challenge()
    if not challenge:
        return
    question_text = challenge["text"]
    msg = (
        "🧩 *تحدي اليوم*\n"
        "━━━━━━━━━━━━━━━\n\n"
        f"أكمل الحديث النبوي:\n\n"
        f"📌 _{question_text}_\n\n"
        "━━━━━━━━━━━━━━━\n"
        "اضغط الزر وأرسل الكلمة الناقصة 👇"
    )
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("💡 أجب على التحدي", callback_data="challenge_answer")
    ]])
    for uid in get_subscribers("daily_hadith"):
        try:
            await context.bot.send_message(uid, msg, parse_mode="Markdown", reply_markup=kb)
            await asyncio.sleep(0.05)
        except:
            pass

# ==================== Duel (تحدي مع صديق) ====================
def create_duel(challenger_id: int, opponent_id: int) -> int:
    today = _dt.datetime.now(AMMAN_TZ).strftime("%Y-%m-%d")
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    # تحقق ما في تحدي نشط بينهم
    cur.execute("""SELECT id FROM duels WHERE status='active'
                   AND ((challenger_id=? AND opponent_id=?) OR (challenger_id=? AND opponent_id=?))""",
                (challenger_id, opponent_id, opponent_id, challenger_id))
    if cur.fetchone():
        conn.close()
        return -1
    cur.execute("""INSERT INTO duels (challenger_id, opponent_id, status, start_date)
                   VALUES (?,?,'pending',?)""", (challenger_id, opponent_id, today))
    duel_id = cur.lastrowid
    conn.commit()
    conn.close()
    return duel_id

def accept_duel(duel_id: int) -> bool:
    conn = sqlite3.connect("bot.db")
    conn.execute("UPDATE duels SET status='active' WHERE id=? AND status='pending'", (duel_id,))
    conn.commit()
    conn.close()
    return True

def reject_duel(duel_id: int):
    conn = sqlite3.connect("bot.db")
    conn.execute("UPDATE duels SET status='rejected' WHERE id=?", (duel_id,))
    conn.commit()
    conn.close()

def get_active_duel(user_id: int) -> dict:
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute("""SELECT id, challenger_id, opponent_id, challenger_streak, opponent_streak,
                          challenger_last, opponent_last, start_date
                   FROM duels WHERE status='active'
                   AND (challenger_id=? OR opponent_id=?)""", (user_id, user_id))
    row = cur.fetchone()
    conn.close()
    if not row:
        return {}
    return {
        "id": row[0], "challenger": row[1], "opponent": row[2],
        "c_streak": row[3], "o_streak": row[4],
        "c_last": row[5], "o_last": row[6], "start": row[7]
    }

def update_duel_streak(user_id: int, duel_id: int):
    """يحدّث سلسلة التحدي عند الضغط ✅ قرأت"""
    today = _dt.datetime.now(AMMAN_TZ).strftime("%Y-%m-%d")
    yesterday = (_dt.datetime.now(AMMAN_TZ) - _dt.timedelta(days=1)).strftime("%Y-%m-%d")
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute("SELECT challenger_id, opponent_id, challenger_streak, opponent_streak, challenger_last, opponent_last FROM duels WHERE id=?", (duel_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return None
    c_id, o_id, c_streak, o_streak, c_last, o_last = row
    if user_id == c_id:
        if c_last == today:
            conn.close()
            return None
        c_streak = c_streak + 1 if c_last == yesterday else 1
        conn.execute("UPDATE duels SET challenger_streak=?, challenger_last=? WHERE id=?", (c_streak, today, duel_id))
        # تحقق إذا الخصم انكسر
        broken = o_last not in (today, yesterday) and o_last != ""
    else:
        if o_last == today:
            conn.close()
            return None
        o_streak = o_streak + 1 if o_last == yesterday else 1
        conn.execute("UPDATE duels SET opponent_streak=?, opponent_last=? WHERE id=?", (o_streak, today, duel_id))
        broken = c_last not in (today, yesterday) and c_last != ""
    conn.commit()
    conn.close()
    return {"broken": broken, "streak": c_streak if user_id == c_id else o_streak}

def forfeit_duel(duel_id: int):
    conn = sqlite3.connect("bot.db")
    conn.execute("UPDATE duels SET status='finished' WHERE id=?", (duel_id,))
    conn.commit()
    conn.close()

def get_user_id_by_username(username: str):
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    uname = username.lstrip("@")
    cur.execute("SELECT user_id FROM users WHERE username=?", (uname,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None

# ==================== Mood Hadith (حديث على قدك) ====================
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

async def send_spiritual_friend(context):
    """صديقي الروحي - كل أسبوع يحلل بحوث المستخدم"""
    week_ago = (_dt.datetime.now(AMMAN_TZ) - _dt.timedelta(days=7)).strftime("%Y-%m-%d")
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM users")
    all_users = [r[0] for r in cur.fetchall()]
    conn.close()
    for uid in all_users:
        try:
            if get_tier(uid) < 3:
                continue
            # جلب آخر بحوث
            conn2 = sqlite3.connect("bot.db")
            cur2 = conn2.cursor()
            cur2.execute("SELECT query FROM search_history WHERE user_id=? AND date >= ? ORDER BY date DESC LIMIT 30",
                         (uid, week_ago))
            queries = [r[0] for r in cur2.fetchall()]
            conn2.close()
            if not queries:
                continue
            # تحليل الكلمات
            from collections import Counter
            words = []
            for q in queries:
                words.extend(q.split())
            word_counts = Counter(words)
            # ابحث عن أقرب موضوع
            topic_scores = {}
            for word, count in word_counts.items():
                for kw, topic in SPIRITUAL_KEYWORDS.items():
                    if kw in word or word in kw:
                        topic_scores[topic] = topic_scores.get(topic, 0) + count
            if not topic_scores:
                continue
            top_topic = max(topic_scores, key=topic_scores.get)
            mood_msg = MOOD_MESSAGES.get(top_topic, "هذه الأحاديث قد تفيدك 🤍")
            # جيب 3 أحاديث
            try:
                results = await search_dorar_api(top_topic)
            except:
                continue
            if not results:
                continue
            chosen = _random.sample(results[:15], min(3, len(results[:15])))
            msg = (
                f"🤖 *صديقي الروحي*\n"
                f"━━━━━━━━━━━━━━━\n\n"
                f"_{mood_msg}_\n\n"
            )
            for i, h in enumerate(chosen, 1):
                msg += f"*{i}.* {h['text'][:150]}...\n"
                msg += f"   📚 {h.get('source','')}{' | ⚖️ ' + h.get('grade','') if h.get('grade') else ''}\n\n"
            msg += f"━━━━━━━━━━━━━━━\n🤖 *{BOT_NAME}* | {BOT_USERNAME}"
            await context.bot.send_message(uid, msg, parse_mode="Markdown")
            await asyncio.sleep(0.1)
        except:
            pass

async def send_friday_hadith(context: ContextTypes.DEFAULT_TYPE):
    """حديث الجمعة - كل جمعة 12:00 ظهراً"""
    import random as _r
    h = None
    topic = _r.choice(["الجمعة", "الصلاة على النبي", "الدعاء", "ذكر الله"])
    try:
        results = await search_dorar_api(topic)
        if results:
            h = _r.choice(results[:10])
    except:
        pass
    if not h:
        conn = sqlite3.connect("bot.db")
        cur = conn.cursor()
        cur.execute("SELECT text, rawi, source, grade FROM ahadith ORDER BY RANDOM() LIMIT 1")
        row = cur.fetchone()
        conn.close()
        if row:
            h = {"text": row[0], "rawi": row[1], "source": row[2], "grade": row[3]}
    if h:
        msg = (
            "🕌 *حديث الجمعة*\n"
            "━━━━━━━━━━━━━━━\n\n"
            f"📌 {h['text']}\n\n"
            f"👤 *الراوي:* {h.get('rawi') or 'غير محدد'}\n"
            f"📚 *المصدر:* {h.get('source') or 'غير محدد'}\n"
            f"⚖️ *الدرجة:* {h.get('grade') or 'غير محدد'}\n\n"
            "━━━━━━━━━━━━━━━\n"
            f"🤖 *{BOT_NAME}* | {BOT_USERNAME}"
        )
    else:
        msg = f"🕌 *جمعة مباركة* 🤍\n\n{BOT_NAME} | {BOT_USERNAME}"
    for uid in get_subscribers("daily_hadith"):
        try:
            await context.bot.send_message(uid, msg, parse_mode="Markdown")
            await asyncio.sleep(0.05)
        except:
            pass

def main_kb(is_admin=False, daily=True, adhkar=False, tier=0):
    sub_adhkar = "🕌 الأذكار"
    keys = [
        [KeyboardButton("🔍 تحقق من حديث"), KeyboardButton("اقترح لي حديثا📜")],
        [KeyboardButton("✨ اسم الله اليوم"), KeyboardButton("❓ سؤال اليوم")],
        [KeyboardButton("🏆 تحدي الأسبوع"), KeyboardButton("💰 دعم البوت")],
        [KeyboardButton("⚠️ إبلاغ عن خطأ"), KeyboardButton("ℹ️ عن البوت")],
    ]
    # Tier 1+: بحث بالموضوع + تاريخ بحثي
    if tier >= 1:
        keys.insert(2, [KeyboardButton("🔎 بحث بالموضوع"), KeyboardButton("📋 تاريخ بحثي")])
    # Tier 2+: أضف المفضلة + حديث على قدك
    if tier >= 2:
        keys.insert(2, [KeyboardButton("🔎 بحث بالموضوع"), KeyboardButton("💾 مفضلتي"), KeyboardButton("📋 تاريخ بحثي")])
        keys.insert(3, [KeyboardButton("📖 حديث على قدك")])
    if is_admin:
        keys.append([KeyboardButton("⚙️ لوحة التحكم")])
    return ReplyKeyboardMarkup(keys, resize_keyboard=True)

def get_top_searchers(limit=10) -> list:
    """أكثر المستخدمين بحثاً"""
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute("""SELECT u.full_name, u.username, COUNT(s.id) as total
                   FROM searches s JOIN users u ON s.user_id=u.user_id
                   GROUP BY s.user_id ORDER BY total DESC LIMIT ?""", (limit,))
    rows = cur.fetchall()
    conn.close()
    return rows

def get_daily_growth() -> list:
    """معدل النمو اليومي - آخر 7 أيام"""
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    rows = []
    for i in range(6, -1, -1):
        day = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        cur.execute("SELECT COUNT(*) FROM users WHERE joined_at LIKE ?", (f"{day}%",))
        count = cur.fetchone()[0]
        rows.append((day[5:], count))
    conn.close()
    return rows

def get_peak_hours() -> list:
    """أكثر أوقات النشاط"""
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    cur.execute("""SELECT CAST(strftime('%H', date) AS INTEGER) as hour, COUNT(*) as cnt
                   FROM searches WHERE date >= ?
                   GROUP BY hour ORDER BY cnt DESC LIMIT 5""", (week_ago,))
    rows = cur.fetchall()
    conn.close()
    return rows

def get_recent_users(limit=10) -> list:
    """آخر المستخدمين المنضمين"""
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute("SELECT full_name, username, joined_at FROM users ORDER BY joined_at DESC LIMIT ?", (limit,))
    rows = cur.fetchall()
    conn.close()
    return rows

def get_setting(key: str, default: str = "") -> str:
    """جلب إعداد من قاعدة البيانات"""
    try:
        conn = sqlite3.connect("bot.db")
        cur = conn.cursor()
        cur.execute("SELECT value FROM bot_settings WHERE key=?", (key,))
        row = cur.fetchone()
        conn.close()
        return row[0] if row else default
    except:
        return default

def save_setting(key: str, value: str):
    """حفظ إعداد في قاعدة البيانات"""
    conn = sqlite3.connect("bot.db")
    conn.execute("INSERT OR REPLACE INTO bot_settings (key, value) VALUES (?,?)", (key, value))
    conn.commit()
    conn.close()

def get_weekly_stats() -> dict:
    """إحصائيات الأسبوع الماضي"""
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    today = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")

    new_users = cur.execute("SELECT COUNT(*) FROM users WHERE joined_at >= ?", (week_ago,)).fetchone()[0]
    active = cur.execute("SELECT COUNT(DISTINCT user_id) FROM searches WHERE date >= ?", (week_ago,)).fetchone()[0]
    searches = cur.execute("SELECT COUNT(*) FROM searches WHERE date >= ?", (week_ago,)).fetchone()[0]
    donations = cur.execute("SELECT COALESCE(SUM(amount),0) FROM donations WHERE date >= ?", (week_ago,)).fetchone()[0]

    cur.execute("SELECT query FROM searches WHERE date >= ?", (week_ago,))
    words = []
    for (q,) in cur.fetchall():
        words.extend(w for w in q.split() if len(w) > 2)
    from collections import Counter
    top = Counter(words).most_common(5)

    conn.close()
    return {"new_users": new_users, "active": active, "searches": searches, "donations": donations, "top": top}

def get_user_info(identifier: str) -> dict:
    """جلب معلومات مستخدم بالـ ID أو اليوزر"""
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    try:
        uid = int(identifier)
        cur.execute("SELECT user_id, username, full_name, searches, joined_at, daily_hadith, adhkar_sub FROM users WHERE user_id=?", (uid,))
    except ValueError:
        uname = identifier.lstrip("@")
        cur.execute("SELECT user_id, username, full_name, searches, joined_at, daily_hadith, adhkar_sub FROM users WHERE username=?", (uname,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return {}
    uid, username, full_name, searches, joined, daily, adhkar = row
    stars = get_premium_stars(uid)
    tier = get_tier(uid)
    return {
        "user_id": uid, "username": username, "full_name": full_name,
        "searches": searches, "joined": joined, "daily": daily, "adhkar": adhkar,
        "stars": stars, "tier": tier,
    }

def get_all_donors() -> list:
    """قائمة كل الداعمين مرتبة بالنجوم"""
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute("""
        SELECT d.user_id, u.full_name, u.username, SUM(d.amount) as total
        FROM donations d
        LEFT JOIN users u ON d.user_id = u.user_id
        GROUP BY d.user_id
        ORDER BY total DESC
    """)
    rows = cur.fetchall()
    conn.close()
    return [{"user_id": r[0], "name": r[1] or "مجهول", "username": r[2], "stars": r[3]} for r in rows]

def grant_tier(user_id: int, stars: int):
    """منح نجوم يدوياً لمستخدم"""
    conn = sqlite3.connect("bot.db")
    conn.execute(
        "INSERT INTO donations (user_id, amount, currency, charge_id) VALUES (?,?,'GRANT','manual_grant')",
        (user_id, stars)
    )
    conn.commit()
    conn.close()
    activate_premium(user_id, stars)

def admin_main_keyboard():
    keys = [
        [KeyboardButton("📊 إحصائيات"), KeyboardButton("📅 إحصائيات الأسبوع")],
        [KeyboardButton("📈 نمو يومي"), KeyboardButton("⏰ أوقات النشاط")],
        [KeyboardButton("🏆 أنشط المستخدمين"), KeyboardButton("🆕 مستخدمون جدد")],
        [KeyboardButton("🔍 بحث مستخدم"), KeyboardButton("🌟 قائمة الداعمين")],
        [KeyboardButton("🎁 منح مستوى"), KeyboardButton("💰 استرداد نجوم")],
        [KeyboardButton("📋 سجل الفواتير"), KeyboardButton("🗑️ حذف مستخدم")],
        [KeyboardButton("✉️ رسالة خاصة"), KeyboardButton("📢 إشعار لمستوى")],
        [KeyboardButton("📢 إشعار متقدم"), KeyboardButton("⚠️ سجل الأخطاء")],
        [KeyboardButton("🗑️ مسح سجل الأخطاء"), KeyboardButton("🔙 رجوع")],
    ]
    return ReplyKeyboardMarkup(keys, resize_keyboard=True)

def advanced_broadcast_keyboard():
    keys = [
        [KeyboardButton("📝 نص")],
        [KeyboardButton("🖼️ صورة"), KeyboardButton("🎤 صوت")],
        [KeyboardButton("🎥 فيديو"), KeyboardButton("📁 ملف")],
        [KeyboardButton("🔙 رجوع")],
    ]
    return ReplyKeyboardMarkup(keys, resize_keyboard=True)

def cancel_broadcast_keyboard():
    keys = [[KeyboardButton("❌ إلغاء الإشعار")]]
    return ReplyKeyboardMarkup(keys, resize_keyboard=True)

def donation_keyboard():
    keys = [
        [KeyboardButton("⭐ 1 نجمة"), KeyboardButton("⭐ 5 نجوم")],
        [KeyboardButton("⭐ 10 نجوم"), KeyboardButton("⭐ 25 نجمة")],
        [KeyboardButton("⭐ 50 نجمة")],
        [KeyboardButton("🔙 رجوع")],
    ]
    return ReplyKeyboardMarkup(keys, resize_keyboard=True)

# ==================== معالجات الإلغاء ====================
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

async def successful_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة الدفع الناجح مع حفظ charge_id"""
    payment = update.message.successful_payment
    amount = payment.total_amount
    charge_id = payment.telegram_payment_charge_id
    user_id = update.effective_user.id
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
        f"📅 التاريخ: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
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
    """أمر استرداد النجوم (للمشرفين فقط)"""
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("⛔ هذا الأمر للمشرفين فقط.")
        return

    if context.user_data.get("awaiting_refund"):
        # المستخدم في حالة انتظار إدخال بيانات الاسترداد
        try:
            parts = update.message.text.strip().split()
            if len(parts) != 2:
                await update.message.reply_text("⚠️ الصيغة غير صحيحة. أرسل معرف المستخدم ثم معرف المعاملة مفصولين بمسافة.")
                return

            user_id = int(parts[0])
            charge_id = parts[1]

            # التحقق من وجود التبرع
            donation = get_donation(user_id, charge_id)
            if not donation:
                await update.message.reply_text("⚠️ لم يتم العثور على تبرع بهذه البيانات.")
                context.user_data.pop("awaiting_refund", None)
                return

            # محاولة استرداد المبلغ
            try:
                await context.bot.refund_star_payment(
                    user_id=user_id,
                    telegram_payment_charge_id=charge_id
                )
                await update.message.reply_text(f"✅ تم استرداد {donation[0]} نجمة للمستخدم {user_id} بنجاح.")
            except Exception as e:
                await update.message.reply_text(f"❌ فشل الاسترداد: {e}")

            context.user_data.pop("awaiting_refund", None)
        except Exception as e:
            await update.message.reply_text(f"❌ خطأ: {e}")
            context.user_data.pop("awaiting_refund", None)
    else:
        # أول مرة: نطلب إدخال البيانات
        context.user_data["awaiting_refund"] = True
        await update.message.reply_text(
            "💰 *استرداد نجوم*\n\n"
            "أرسل معرف المستخدم ثم معرف المعاملة مفصولين بمسافة.\n"
            "مثال: `123456789 donation_5_abc123`\n"
            "يمكنك العثور على معرف المعاملة في إشعار التبرع الذي وصلك."
        )

# ==================== المعالجات ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    register_user(user.id, user.username or "", user.full_name)

    # deep links
    if context.args:
        arg = context.args[0]
        if arg.startswith("duel_"):
            try:
                challenger_id = int(arg.split("_")[1])
                if challenger_id == user.id:
                    await update.message.reply_text("❌ ما تقدر تتحدى نفسك 😄")
                else:
                    duel_id = create_duel(challenger_id, user.id)
                    if duel_id == -1:
                        await update.message.reply_text("⚠️ يوجد تحدٍ نشط بينكما مسبقاً!")
                    else:
                        accept_duel(duel_id)
                        conn = sqlite3.connect("bot.db")
                        cur = conn.cursor()
                        cur.execute("SELECT full_name FROM users WHERE user_id=?", (challenger_id,))
                        row = cur.fetchone()
                        conn.close()
                        name = row[0] if row else "شخص ما"
                        try:
                            await context.bot.send_message(challenger_id,
                                f"⚔️ {user.full_name} قبل تحديك! 🔥 التحدي بدأ!")
                        except:
                            pass
                        await update.message.reply_text(
                            f"⚔️ التحدي بدأ مع {name}!\n"
                            "اضغط ✅ قرأت على حديث اليوم يومياً\n"
                            "استخدم /duel لمتابعة التحدي."
                        )
            except:
                pass
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

    if is_new:
        # إشعار المشرف بمستخدم جديد
        uname = f"@{user.username}" if user.username else "بدون يوزر"
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(
                    admin_id,
                    f"👤 *مستخدم جديد!*\n\n"
                    f"الاسم: {user.full_name}\n"
                    f"اليوزر: {uname}\n"
                    f"ID: `{user.id}`",
                    parse_mode="Markdown"
                )
            except:
                pass
        # رسالة ترحيب تفاعلية للمستخدم الجديد
        tour_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔍 جرب بحث الآن", switch_inline_query_current_chat="إنما الأعمال بالنيات")],
            [InlineKeyboardButton("🌅 اشترك بحديث اليوم", callback_data="tour_daily"),
             InlineKeyboardButton("🕌 أذكار الصباح والمساء", callback_data="tour_adhkar")],
            [InlineKeyboardButton("✅ فهمت! ابدأ", callback_data="tour_done")],
        ])
        await update.message.reply_text(
            f"🕌 أهلاً وسهلاً، {user.first_name}!\n\n"
            f"أنا *راوِي* ◾️\n"
            "بوت متخصص في التحقق من صحة الأحاديث النبوية\n\n"
            "📌 *كيف تستخدمني؟*\n"
            "فقط أرسل أي حديث سمعته وسأبحث عنه في الكتب الستة فوراً\n\n"
            "مثال: أرسل «إنما الأعمال بالنيات» وسأريك نتيجة كاملة\n\n"
            "اضغط زر البحث لتجربة مباشرة 👇",
            reply_markup=tour_kb,
            parse_mode="Markdown"
        )
        await update.message.reply_text(
            "القائمة الرئيسية جاهزة 👇",
            reply_markup=main_kb(is_admin, bool(_daily), bool(_adhkar), tier=get_tier(user.id))
        )
    else:
        await update.message.reply_text(
            f"🕌 مرحباً بعودتك، {user.first_name}!\n\n"
            f"أنا *راوِي* ◾️\n"
            "بوت متخصص في التحقق من صحة الأحاديث النبوية\n\n"
            "🔍 ابحث بأي كلمة من الحديث أو باسم الراوي\n"
            "🌅 حديث اليوم — يصلك كل صبح تلقائياً\n"
            "🕌 أذكار الصباح والمساء — مع فضل كل ذكر ومصدره\n\n"
            "✨ مزايا الداعمين:\n"
            "⭐ نجمة واحدة ← 🔎 بحث بالموضوع\n"
            "⭐ 5 نجوم ← 💾 المفضلة\n"
            "⭐ 25 نجمة ← 🕐 تخصيص وقت الإشعار\n\n"
            "استخدم الأزرار للوصول السريع.",
            reply_markup=main_kb(is_admin, bool(_daily), bool(_adhkar), tier=get_tier(user.id))
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
    await update.message.reply_text("✅ النسخة: v3.2 - 2026-03-10")

async def cmd_asma(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أسماء الله الحسنى - اسم اليوم"""
    user = update.effective_user
    asma = get_asma_of_day(user.id)
    msg = build_asma_msg(asma)
    kb = build_asma_keyboard(asma['name'])
    await update.message.reply_text(msg, reply_markup=kb)

def build_asma_msg(asma: dict) -> str:
    msg = (
        "✨ *اسم الله الحسنى اليوم*\n"
        "━━━━━━━━━━━━━━━\n\n"
        f"🌟 *{asma['name']}*\n\n"
        f"📖 *المعنى:*\n{asma['meaning']}\n\n"
        f"💡 *الفائدة:*\n{asma.get('benefit', '')}\n\n"
        f"🤲 *الدعاء:*\n_{asma['dhikr']}_\n\n"
        "━━━━━━━━━━━━━━━\n"
        f"🤖 {BOT_NAME} | {BOT_USERNAME}"
    )
    return msg

def build_asma_keyboard(name: str) -> InlineKeyboardMarkup:
    share_text = urllib.parse.quote(
        f"✨ اسم الله اليوم: {name}\n\n"
        f"تعرّف على أسماء الله الحسنى الـ99 عبر بوت راوِي:\n{BOT_USERNAME}"
    )
    share_url = f"https://t.me/share/url?url=https://t.me/{BOT_USERNAME.lstrip('@')}&text={share_text}"
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✨ اسم آخر", callback_data="asma_next"),
        InlineKeyboardButton("📋 كل الأسماء", callback_data="asma_list"),
    ],[
        InlineKeyboardButton("📤 شارك", url=share_url),
    ]])

async def cmd_sahaba(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تحدي من هو؟"""
    user = update.effective_user
    sahabi = get_sahaba_of_day()
    context.user_data["sahaba_answer"] = sahabi["name"]
    context.user_data["sahaba_fact"] = sahabi["fact"]
    context.user_data["sahaba_bio"] = sahabi.get("bio", "")
    context.user_data["sahaba_hints"] = sahabi["hints"]
    context.user_data["sahaba_hint_idx"] = 0
    context.user_data["in_sahaba_quiz"] = True
    hint = sahabi["hints"][0]
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("💡 تلميح إضافي", callback_data="sahaba_hint"),
        InlineKeyboardButton("🏳️ أظهر الجواب", callback_data="sahaba_reveal"),
    ]])
    await update.message.reply_text(
        "🎯 من هو هذا الصحابي؟\n"
        "━━━━━━━━━━━━━━━\n\n"
        f"📌 التلميح: {hint}\n\n"
        "أرسل اسمه الآن 👇",
        reply_markup=kb
    )

async def send_quiz_question(msg, context, q, num):
    """إرسال سؤال في الاختبار اليومي"""
    opts = q["options"]
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(opts[0], callback_data=f"quiz_{opts[0]}"),
         InlineKeyboardButton(opts[1], callback_data=f"quiz_{opts[1]}")],
        [InlineKeyboardButton(opts[2], callback_data=f"quiz_{opts[2]}"),
         InlineKeyboardButton(opts[3], callback_data=f"quiz_{opts[3]}")],
    ])
    await msg.reply_text(
        f"❓ *اختبار اليوم — سؤال {num}/5*\n"
        "━━━━━━━━━━━━━━━\n\n"
        f"📌 {q['q']}\n\n"
        "اختر الإجابة الصحيحة 👇",
        parse_mode="Markdown",
        reply_markup=kb
    )

async def cmd_daily_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """السؤال الديني اليومي"""
    user = update.effective_user
    today = _dt.datetime.now(AMMAN_TZ).strftime("%Y-%m-%d")
    # تحقق إذا أجاب اليوم
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute("SELECT correct FROM daily_question WHERE user_id=? AND date=?", (user.id, today))
    row = cur.fetchone()
    conn.close()
    if row:
        result = "✅ أجبت صح" if row[0] else "❌ أجبت خطأ"
        await update.message.reply_text(f"📝 أجبت على سؤال اليوم مسبقاً! {result}\nتعال غداً لسؤال جديد 🌙")
        return
    q = get_question_of_day()
    context.user_data["daily_q"] = q
    context.user_data["daily_q_date"] = today
    opts = q["options"]
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(opts[0], callback_data=f"dq_{opts[0]}"),
         InlineKeyboardButton(opts[1], callback_data=f"dq_{opts[1]}")],
        [InlineKeyboardButton(opts[2], callback_data=f"dq_{opts[2]}"),
         InlineKeyboardButton(opts[3], callback_data=f"dq_{opts[3]}")],
    ])
    await update.message.reply_text(
        "❓ سؤال ديني اليوم\n"
        "━━━━━━━━━━━━━━━\n\n"
        f"📌 {q['q']}\n\n"
        "اختر الإجابة الصحيحة 👇",
        reply_markup=kb
    )

async def cmd_weekly_challenge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تحدي الأسبوع الجماعي"""
    user = update.effective_user
    ch = get_weekly_challenge()
    week = ch["week"]
    if has_answered_weekly(user.id, week):
        scores = get_weekly_scores(week)
        msg = "🏆 تحدي الأسبوع\n━━━━━━━━━━━━━━━\n\nأجبت مسبقاً! 🎉\n\n📊 نتائج هذا الأسبوع:\n"
        correct_count = sum(1 for s in scores if s[2] == 1)
        msg += f"✅ أجاب صح: {correct_count} مستخدم\n"
        msg += f"👥 إجمالي المشاركين: {len(scores)}\n"
        await update.message.reply_text(msg)
        return
    context.user_data["in_weekly_challenge"] = True
    context.user_data["weekly_answer"] = ch["answer"]
    context.user_data["weekly_week"] = week
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("💡 تلميح", callback_data="weekly_hint"),
    ]])
    await update.message.reply_text(
        "🏆 تحدي الأسبوع الجماعي\n"
        "━━━━━━━━━━━━━━━\n\n"
        f"❓ {ch['question']}\n\n"
        "أرسل إجابتك الآن 👇",
        reply_markup=kb
    )

async def version_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ النسخة: v3.2 - 2026-03-10")

async def testchallenge_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    await send_daily_challenge(context)
    await update.message.reply_text("✅ تم إرسال التحدي الآن")

async def random_hadith(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text, src, grade = get_random_hadith()
    await update.message.reply_text(f"🎁 *اقتراح حديث:*\n\n{text}\n\n📚 {src}\n⚖️ {grade}")

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

    if text == "📢 إشعار للجميع":
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
        msg = (
            f"📊 *إحصائيات البوت*\n\n"
            f"👥 إجمالي المستخدمين: {users}\n"
            f"🔎 إجمالي البحوث: {searches}\n"
            f"📚 عدد الأحاديث: {hadiths}\n"
            f"🔥 نشطين آخر 7 أيام: {w['active']}\n"
        )
        await update.message.reply_text(msg, parse_mode="Markdown")
        return

    elif text == "📅 إحصائيات الأسبوع":
        w = get_weekly_stats()
        # معدل الاحتفاظ (ميزة 10)
        conn_r = sqlite3.connect("bot.db")
        cur_r = conn_r.cursor()
        two_weeks = (datetime.now() - timedelta(days=14)).strftime("%Y-%m-%d %H:%M:%S")
        one_week = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
        cur_r.execute("SELECT COUNT(DISTINCT user_id) FROM searches WHERE date BETWEEN ? AND ?", (two_weeks, one_week))
        old_users = cur_r.fetchone()[0] or 1
        cur_r.execute("SELECT COUNT(DISTINCT user_id) FROM searches WHERE date >= ?", (one_week,))
        returned = cur_r.fetchone()[0]
        conn_r.close()
        retention = round((returned / old_users) * 100) if old_users else 0
        # أكثر الأحاديث مشاركةً (ميزة 8)
        top_shared = get_top_shared(3)
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
        if top_shared:
            msg += "\n*أكثر الأحاديث مشاركةً:*\n"
            for i, (text_h, cnt) in enumerate(top_shared, 1):
                msg += f"  {i}. {text_h[:60]}... ({cnt} مرة)\n"
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
            buttons.append([InlineKeyboardButton(
                f"↩️ استرداد {amount}⭐ — {name or uid}",
                callback_data=f"refund_{uid}_{charge_id}"
            )])
        await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(buttons) if buttons else None)
        return

    elif text == "🗑️ حذف مستخدم":
        context.user_data["admin_action"] = "delete_user"
        await update.message.reply_text("أرسل ID المستخدم الذي تريد حذفه:")
        return

    elif text == "✏️ رسالة الترحيب":
        current = get_setting("welcome_msg", "غير محددة")
        context.user_data["admin_action"] = "set_welcome"
        await update.message.reply_text(
            f"الرسالة الحالية:\n"
            "أرسل رسالة الترحيب الجديدة:"
        )
        return

    elif text == "⏸ إيقاف البحث":
        current = get_setting("search_disabled", "0")
        new_val = "0" if current == "1" else "1"
        save_setting("search_disabled", new_val)
        status = "🔴 موقوف" if new_val == "1" else "🟢 مفعّل"
        await update.message.reply_text(f"البحث الآن: {status}")
        return

    elif text == "📢 إشعار لمستوى":
        context.user_data["admin_action"] = "broadcast_tier"
        tier_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("⭐ Tier 1+", callback_data="btier_1"),
             InlineKeyboardButton("⭐⭐ Tier 2+", callback_data="btier_2"),
             InlineKeyboardButton("🌟 Tier 3", callback_data="btier_3")],
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
                InlineKeyboardButton("✅ إرسال للجميع", callback_data="confirm_adv_broadcast"),
                InlineKeyboardButton("✏️ تعديل", callback_data="edit_adv_broadcast"),
                InlineKeyboardButton("❌ إلغاء", callback_data="cancel_broadcast_cb"),
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
                    InlineKeyboardButton("✅ إرسال للجميع", callback_data="confirm_adv_broadcast"),
                    InlineKeyboardButton("❌ إلغاء", callback_data="cancel_broadcast_cb"),
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
                    InlineKeyboardButton("✅ إرسال للجميع", callback_data="confirm_adv_broadcast"),
                    InlineKeyboardButton("❌ إلغاء", callback_data="cancel_broadcast_cb"),
                ]])
                await update.message.reply_text("👁 تم استلام الصوت. هل تريد إرساله للجميع؟", reply_markup=preview_kb)
                return True
            elif broadcast_type == "🎥 فيديو" and (update.message.video or update.message.document):
                fid = update.message.video.file_id if update.message.video else update.message.document.file_id
                context.user_data["broadcast_file_id"] = fid
                context.user_data["broadcast_caption"] = update.message.caption or "📢 إشعار فيديو"
                preview_kb = InlineKeyboardMarkup([[
                    InlineKeyboardButton("✅ إرسال للجميع", callback_data="confirm_adv_broadcast"),
                    InlineKeyboardButton("❌ إلغاء", callback_data="cancel_broadcast_cb"),
                ]])
                await update.message.reply_text("👁 تم استلام الفيديو. هل تريد إرساله للجميع؟", reply_markup=preview_kb)
                return True
            elif broadcast_type == "📁 ملف" and update.message.document:
                context.user_data["broadcast_file_id"] = update.message.document.file_id
                context.user_data["broadcast_caption"] = update.message.caption or "📢 إشعار ملف"
                preview_kb = InlineKeyboardMarkup([[
                    InlineKeyboardButton("✅ إرسال للجميع", callback_data="confirm_adv_broadcast"),
                    InlineKeyboardButton("❌ إلغاء", callback_data="cancel_broadcast_cb"),
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
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text if update.message.text else ""

    register_user(user.id, user.username or "", user.full_name)

    # معالج إجابة من هو؟
    if context.user_data.get("in_sahaba_quiz") and text:
        context.user_data.pop("in_sahaba_quiz", None)
        answer = context.user_data.pop("sahaba_answer", "")
        fact = context.user_data.pop("sahaba_fact", "")
        context.user_data.pop("sahaba_hints", None)
        user_ans = text.strip()
        correct = answer.split()[0] in user_ans or user_ans in answer
        if correct:
            await update.message.reply_text(
                f"✅ إجابة صحيحة! 🎉\n\n"
                f"الصحابي: {answer}\n\n"
                f"💡 {fact}"
            )
        else:
            await update.message.reply_text(
                f"❌ إجابة خاطئة\n\n"
                f"الجواب الصحيح: {answer}\n\n"
                f"💡 {fact}"
            )
        return

    # معالج إجابة تحدي الأسبوع
    if context.user_data.get("in_weekly_challenge") and text:
        context.user_data.pop("in_weekly_challenge", None)
        correct_answer = context.user_data.pop("weekly_answer", "")
        week = context.user_data.pop("weekly_week", "")
        user_ans = text.strip()
        correct = correct_answer.lower() in user_ans.lower() or user_ans.lower() in correct_answer.lower()
        save_weekly_answer(user.id, week, user_ans, correct)
        scores = get_weekly_scores(week)
        correct_count = sum(1 for s in scores if s[2] == 1)
        if correct:
            await update.message.reply_text(
                f"✅ إجابة صحيحة! 🎉\n\n"
                f"الجواب: {correct_answer}\n\n"
                f"📊 {correct_count} مستخدم أجاب صح من {len(scores)} مشارك"
            )
        else:
            await update.message.reply_text(
                f"❌ إجابة خاطئة\n\n"
                f"الجواب الصحيح: {correct_answer}\n\n"
                f"📊 {correct_count} مستخدم أجاب صح من {len(scores)} مشارك"
            )
        return

    # معالج إجابة التحدي
    if context.user_data.get("in_challenge") and text:
        context.user_data.pop("in_challenge", None)
        correct_answer = context.user_data.pop("challenge_answer", "")
        full_text = context.user_data.pop("challenge_full", "")
        user_answer = text.strip().strip(".,،؟!")
        is_correct = correct_answer.strip(".,،؟!") in user_answer or user_answer in correct_answer.strip(".,،؟!")
        save_challenge_answer(user.id, is_correct)
        if is_correct:
            await update.message.reply_text(
                f"✅ *إجابة صحيحة!* 🎉\n\n"
                f"الحديث كاملاً:\n_{full_text}_",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(
                f"❌ *إجابة خاطئة*\n\n"
                f"الكلمة الصحيحة: *{correct_answer}*\n\n"
                f"الحديث كاملاً:\n_{full_text}_",
                parse_mode="Markdown"
            )
        return

    # معالج الملاحظة على المفضلة
    if context.user_data.get("waiting_note"):
        context.user_data.pop("waiting_note", None)
        hadith_text = context.user_data.pop("note_hadith", "")
        if hadith_text:
            save_favorite_note(user.id, hadith_text, text[:300])
            await update.message.reply_text("✅ تم حفظ ملاحظتك على الحديث 📝")
        else:
            await update.message.reply_text("⚠️ لم يُعثر على الحديث، حاول مرة أخرى.")
        return

    # معالج أوامر الأدمن التفاعلية
    admin_action = context.user_data.get("admin_action")
    if admin_action and user.id in ADMIN_IDS:
        context.user_data.pop("admin_action", None)

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
                InlineKeyboardButton("📢 إرسال للجميع", callback_data="confirm_broadcast"),
                InlineKeyboardButton("❌ إلغاء", callback_data="cancel_broadcast_cb")
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
                grant_tier(uid, stars)
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

    # أزرار VIP - تاريخ البحث وإحصائياتي
    if text == "📋 تاريخ بحثي":
        history = get_search_history(user.id)
        if not history:
            await update.message.reply_text("🔍 ما أجريت أي بحث بعد!")
        else:
            msg = "📋 *آخر بحوثك:*\n\n"
            for i, (query, count, date) in enumerate(history, 1):
                msg += f"{i}. {query} — {count} نتيجة\n"
            await update.message.reply_text(msg, parse_mode="Markdown")
        return

        # أزرار الاشتراك
    if text in ("🔔 حديث اليوم", "🔕 حديث اليوم"):
        new_val = toggle_subscription(user.id, "daily_hadith")
        status = "✅ تم تفعيل حديث اليوم! ستصلك كل يوم 7 الصبح 🌅" if new_val else "🔕 تم إيقاف حديث اليوم"
        await update.message.reply_text(status, reply_markup=main_kb(user.id in ADMIN_IDS, new_val, bool(get_subscribers("adhkar_sub") and user.id in get_subscribers("adhkar_sub")), tier=get_tier(user.id)))
        return

    if text == "🕌 الأذكار":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🌄 أذكار الصباح", callback_data="adhkar_sabah"),
             InlineKeyboardButton("🌆 أذكار المساء", callback_data="adhkar_masaa")],
        ])
        await update.message.reply_text("اختر نوع الأذكار 👇", reply_markup=kb)
        return

    if text == "✨ اسم الله اليوم":
        await cmd_asma(update, context)
        return

    if text == "🎯 من هو؟":
        await cmd_sahaba(update, context)
        return

    if text == "❓ سؤال اليوم":
        await cmd_daily_question(update, context)
        return

    if text == "🏆 تحدي الأسبوع":
        await cmd_weekly_challenge(update, context)
        return

    # أوامر Premium من لوحة المفاتيح
    if text == "💾 مفضلتي":
        await cmd_favorites(update, context)
        return
    if text == "🔎 بحث بالموضوع":
        await cmd_topics(update, context)
        return
    if text == "📖 حديث على قدك":
        await cmd_mood_hadith(update, context)
        return
    if text == "🧩 تحدي الآن":
        await cmd_challenge_now(update, context)
        return
    if text == "⚔️ تحدي مع صديق":
        await cmd_duel(update, context)
        return

    # زر الإبلاغ من لوحة المفاتيح الرئيسية
    if text == "⚠️ إبلاغ عن خطأ":
        context.user_data["reporting"] = True
        context.user_data["reporting_hadith_id"] = 0
        context.user_data["reporting_hadith_text"] = "إبلاغ عام من لوحة المفاتيح"
        cancel_kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("❌ إلغاء التقرير", callback_data="cancel_report")
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
    if user.id in ADMIN_IDS and context.user_data.get("awaiting_refund"):
        await refund_command(update, context)
        return

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
            reply_markup=main_kb(user.id in ADMIN_IDS, bool(_d3), bool(_a3), tier=get_tier(user.id))
        )
        return

    # الأزرار الرئيسية
    if text == "🔍 تحقق من حديث":
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("🔍 جرب بحث الآن", switch_inline_query_current_chat="")
        ]])
        await update.message.reply_text(
            "🔍 *كيف تبحث في راوِي؟*\n"
            "━━━━━━━━━━━━━━━\n\n"
            "✅ *طرق البحث:*\n"
            "• جزء من نص الحديث\n"
            "  مثال: `إنما الأعمال بالنيات`\n\n"
            "• اسم الراوي\n"
            "  مثال: `أبو هريرة`\n\n"
            "• موضوع عام\n"
            "  مثال: `الصبر` أو `بر الوالدين`\n\n"
            "💡 *نصائح:*\n"
            "• لا تكتب «قال النبي» — ابدأ بالنص مباشرة\n"
            "• كلمة أو كلمتان تكفيان\n"
            "• البوت يصحح الكلمات الخاطئة تلقائياً\n\n"
            "━━━━━━━━━━━━━━━\n"
            "✍️ أرسل ما تريد البحث عنه الآن 👇",
            parse_mode="Markdown"
        )
        return
    if text == "اقترح لي حديثا📜":
        await random_suggestion(update, context)
        return

    if text == "ℹ️ عن البوت":
        users, searches, hadiths, _ = get_global_stats()
        await update.message.reply_text(
            f"ℹ️ *{BOT_NAME}* - بوت أحاديث.\n"
            f"📚 يحتوي على {hadiths} حديث.\n"
            "🔍 ابحث بنص الحديث أو باسم الراوي.\n"
            "👤 للمطور: @ssss_ssss_x\n"
            "/help للمساعدة."
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

    # إذا كانت الرسالة تحتوي على وسائط ولم تكن في حالة بث، تجاهلها
    if not text:
        return

    # البحث عن حديث
    if len(text) < 3:
        await update.message.reply_text("⚠️ أرسل نصاً أطول (3 أحرف على الأقل).")
        return

    # تحقق من إيقاف البحث
    if get_setting("search_disabled") == "1" and user.id not in ADMIN_IDS:
        await update.message.reply_text("⏸ البحث متوقف مؤقتاً، يرجى المحاولة لاحقاً.")
        return

    # Rate limiting
    if is_rate_limited(user.id):
        await update.message.reply_text("⏳ أرسلت طلبات كثيرة، انتظر ثوانٍ قليلة وأعد المحاولة.")
        return

    wait = await update.message.reply_text("⏳ جاري البحث في الدرر السنية...")
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
                results = await search_dorar_api(suggestion)
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
            kb = [[InlineKeyboardButton("🔍 ابحث في الدرر السنية", url=url)]]
            if spell_hint and suggestion:
                kb.append([InlineKeyboardButton(f"✏️ ابحث عن: {suggestion}", callback_data=f"spell_{suggestion[:50]}")])
            not_found_msg = f"⚠️ لم أجد نتائج لـ «{text}».{spell_hint}"
            await wait.edit_text(not_found_msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
    except Exception as e:
        logger.error(f"خطأ في البحث: {e}")
        log_error(type(e).__name__, str(e), user.id, traceback.format_exc())
        await wait.edit_text("⚠️ حدث خطأ أثناء البحث. تم تسجيل المشكلة.")

def build_hadith_msg(h: dict, page: int, total: int) -> str:
    """بناء رسالة الحديث من dict"""
    text = h['text'].strip()
    msg = f"🔍 نتيجة البحث ({page+1}/{total}):\n\n"
    msg += f"📌 {text}\n\n"
    msg += f"👤 الراوي: {h.get('rawi') or 'غير محدد'}\n"
    if h.get('mohdith'):
        msg += f"🎓 المحدث: {h['mohdith']}\n"
    msg += f"📚 المصدر: {h.get('source') or 'غير محدد'}\n"
    msg += f"⚖️ الدرجة: {h.get('grade') or 'غير محدد'}\n"
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
            nav_row.append(InlineKeyboardButton("⬅️ السابق", callback_data="nav_prev"))
        if page < total - 1:
            nav_row.append(InlineKeyboardButton("التالي ➡️", callback_data="nav_next"))
        if nav_row:
            keyboard.append(nav_row)
    # زر المفضلة لـ Tier 2+
    if user_id and has_favorites(user_id):
        fav_btn = InlineKeyboardButton("💔 إزالة من المفضلة" if is_fav else "💾 حفظ في المفضلة", callback_data="fav_remove" if is_fav else "fav_save")
        keyboard.append([fav_btn])
    keyboard.append([
        InlineKeyboardButton("📤 شارك الحديث", callback_data="share"),
        InlineKeyboardButton("⚠️ إبلاغ", callback_data=f"report_{hid}"),
    ])
    if user_id:
        grade = context_filter if context_filter else "all"
        grade_labels = {"all": "🔘 كل الدرجات", "sahih": "✅ صحيح فقط", "hasan": "🟡 حسن فقط"}
        keyboard.append([InlineKeyboardButton(
            f"🎚 الفلتر: {grade_labels.get(grade, 'كل الدرجات')}",
            callback_data=f"grade_filter"
        )])
    keyboard.append([InlineKeyboardButton("🔄 بحث جديد", callback_data="new")])
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
    await update.message.reply_text(msg, reply_markup=keyboard)
    # حفظ الجلسة في DB لمنع فقدانها عند إعادة التشغيل
    try:
        save_user_session(user.id, results, page, cf, context.user_data.get("search_id", ""))
    except:
        pass

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    user = update.effective_user

    # إذا انتهت الجلسة أو ما في نتائج
    results = context.user_data.get("search_results", [])
    stale_actions = {"nav_prev", "nav_next", "share", "fav_save", "fav_remove", "grade_filter"}
    if q.data in stale_actions and not results:
        # حاول استرجاع الجلسة من DB
        session = load_user_session(user.id)
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
            session = load_user_session(user.id)
            if session and session.get("results"):
                results = session["results"]
                page = session["page"]
                context.user_data["search_results"] = results
                context.user_data["search_page"] = page
        if results and page < len(results):
            h = results[page]
            share_text = build_share_text(h)
            increment_share(h.get("text", ""))
            # زر مشاركة مباشر عبر Telegram
            share_url = f"https://t.me/share/url?url=https://t.me/{BOT_USERNAME.lstrip('@')}&text={urllib.parse.quote(share_text)}"
            share_kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("📤 شارك الحديث", url=share_url)
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
                InlineKeyboardButton("❌ إلغاء التقرير", callback_data="cancel_report")
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
                if get_tier(user.id) >= 2:
                    note_kb = InlineKeyboardMarkup([[
                        InlineKeyboardButton("📝 أضف ملاحظة", callback_data=f"add_note"),
                        InlineKeyboardButton("تخطي", callback_data="skip_note")
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

    elif q.data == "tour_daily":
        await toggle_subscription(user.id, "daily_hadith")
        await q.answer("✅ تم تفعيل حديث اليوم! ستصلك كل صبح 🌅", show_alert=True)

    elif q.data == "tour_adhkar":
        await toggle_subscription(user.id, "adhkar_sub")
        await q.answer("✅ تم الاشتراك بأذكار الصباح والمساء! 🕌", show_alert=True)

    elif q.data == "tour_done":
        await q.answer("بالتوفيق! 🤍")
        try:
            await q.message.delete()
        except:
            pass

    elif q.data == "add_note":
        await q.answer()
        context.user_data["waiting_note"] = True
        try:
            await q.message.delete()
        except:
            pass
        await q.message.reply_text("📝 أرسل ملاحظتك على هذا الحديث (300 حرف كحد أقصى):")

    elif q.data.startswith("btier_"):
        tier_min = int(q.data.split("_")[1])
        context.user_data["broadcast_tier_min"] = tier_min
        context.user_data["admin_action"] = "broadcast_tier_msg"
        await q.answer()
        await q.message.reply_text(f"أرسل الرسالة للمستخدمين من مستوى {tier_min} فأعلى:")

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

    elif q.data == "asma_next":
        await q.answer()
        # اسم عشوائي مختلف
        import random as _r2
        asma = _r2.choice(ASMA_ALLAH)
        msg = (
            "✨ اسم الله\n"
            "━━━━━━━━━━━━━━━\n\n"
            f"🌟 {asma['name']}\n\n"
            f"📖 المعنى: {asma['meaning']}\n\n"
            f"🤲 الدعاء: {asma['dhikr']}\n\n"
            "━━━━━━━━━━━━━━━"
        )
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("✨ اسم آخر", callback_data="asma_next"),
        ]])
        try:
            await q.message.edit_text(msg, reply_markup=kb)
        except:
            await q.message.reply_text(msg, reply_markup=kb)

    elif q.data == "asma_list":
        await q.answer()
        msg = "📋 أسماء الله الحسنى\n━━━━━━━━━━━━━━━\n\n"
        for i, a in enumerate(ASMA_ALLAH, 1):
            msg += f"{i}. {a['name']}\n"
        await q.message.reply_text(msg)

    elif q.data == "sahaba_hint":
        await q.answer()
        hints = context.user_data.get("sahaba_hints", [])
        idx = context.user_data.get("sahaba_hint_idx", 0) + 1
        if idx >= len(hints):
            await q.answer("لا يوجد تلميحات إضافية", show_alert=True)
            return
        context.user_data["sahaba_hint_idx"] = idx
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("💡 تلميح إضافي", callback_data="sahaba_hint"),
            InlineKeyboardButton("🏳️ أظهر الجواب", callback_data="sahaba_reveal"),
        ]])
        try:
            await q.message.edit_text(
                f"🎯 من هو هذا الصحابي؟\n━━━━━━━━━━━━━━━\n\n"
                + "\n".join(f"📌 {h}" for h in hints[:idx+1])
                + "\n\nأرسل اسمه الآن 👇",
                reply_markup=kb
            )
        except:
            pass

    elif q.data == "sahaba_reveal":
        await q.answer()
        answer = context.user_data.get("sahaba_answer", "")
        fact = context.user_data.get("sahaba_fact", "")
        bio = context.user_data.get("sahaba_bio", "")
        context.user_data.pop("in_sahaba_quiz", None)
        msg = (
            f"🎯 *الجواب: {answer}*\n"
            "━━━━━━━━━━━━━━━\n\n"
            f"📜 *السيرة:*\n{bio}\n\n"
            f"💎 *قال النبي ﷺ:*\n_{fact}_\n\n"
            f"━━━━━━━━━━━━━━━\n"
            f"🤖 {BOT_NAME} | {BOT_USERNAME}"
        )
        share_text = urllib.parse.quote(
            f"🎯 من هو؟\n\n{answer}\n\n{fact}\n\nتعرّف على سير الصحابة عبر بوت راوِي:\n{BOT_USERNAME}"
        )
        share_url = f"https://t.me/share/url?url=https://t.me/{BOT_USERNAME.lstrip('@')}&text={share_text}"
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("🎯 تحدٍ جديد", callback_data="sahaba_new"),
            InlineKeyboardButton("📤 شارك", url=share_url),
        ]])
        await q.message.edit_text(msg, parse_mode="Markdown", reply_markup=kb)

    elif q.data == "sahaba_new":
        await q.answer()
        sahabi = SAHABA_QUIZ[_dt.datetime.now(AMMAN_TZ).second % len(SAHABA_QUIZ)]
        context.user_data["sahaba_answer"] = sahabi["name"]
        context.user_data["sahaba_fact"] = sahabi["fact"]
        context.user_data["sahaba_bio"] = sahabi.get("bio", "")
        context.user_data["sahaba_hints"] = sahabi["hints"]
        context.user_data["sahaba_hint_idx"] = 0
        context.user_data["in_sahaba_quiz"] = True
        hint = sahabi["hints"][0]
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("💡 تلميح إضافي", callback_data="sahaba_hint"),
            InlineKeyboardButton("🏳️ أظهر الجواب", callback_data="sahaba_reveal"),
        ]])
        msg_text = "🎯 *من هو هذا الصحابي؟*\n━━━━━━━━━━━━━━━\n\n" + f"📌 التلميح: {hint}\n\nأرسل اسمه الآن 👇"
        await q.message.edit_text(
            msg_text,







            parse_mode="Markdown",
            reply_markup=kb
        )

    elif q.data.startswith("quiz_"):
        chosen = q.data[5:]
        questions = context.user_data.get("quiz_questions", [])
        idx_q = context.user_data.get("quiz_index", 0)
        score = context.user_data.get("quiz_score", 0)
        date = context.user_data.get("quiz_date", "")
        if not questions:
            # استرجع من DB
            sess = load_quiz_session(user.id)
            if sess and sess.get("questions"):
                questions = sess["questions"]
                idx_q = sess["index"]
                score = sess["score"]
                date = sess["date"]
                context.user_data["quiz_questions"] = questions
                context.user_data["quiz_index"] = idx_q
                context.user_data["quiz_score"] = score
                context.user_data["quiz_date"] = date
            else:
                await q.answer("انتهت الجلسة، ابدأ الاختبار من جديد", show_alert=True)
                return
        if idx_q >= len(questions):
            await q.answer("انتهت الجلسة", show_alert=True)
            return
        q_data = questions[idx_q]
        correct = chosen == q_data["answer"]
        if correct:
            score += 1
            context.user_data["quiz_score"] = score
            result_line = "✅ *إجابة صحيحة!* 🎉"
        else:
            result_line = f"❌ *إجابة خاطئة*\nالجواب: {q_data['answer']}"
        await q.message.edit_text(
            f"{result_line}\n\n"
            f"📖 {q_data['explain']}",
            parse_mode="Markdown"
        )
        next_idx = idx_q + 1
        context.user_data["quiz_index"] = next_idx
        save_quiz_session(user.id, questions, next_idx, score, date)
        if next_idx >= 5:
            # انتهى الاختبار
            context.user_data.pop("in_daily_quiz", None)
            clear_quiz_session(user.id)
            conn = sqlite3.connect("bot.db")
            conn.execute("INSERT OR REPLACE INTO daily_question (user_id, date, q_index, answered, correct) VALUES (?,?,?,1,?)",
                         (user.id, date, 0, score))
            conn.commit()
            conn.close()
            stars = "⭐" * score + "☆" * (5 - score)
            comment = {5: "ممتاز! 🏆", 4: "رائع! 👏", 3: "جيد 👍", 2: "تحتاج مراجعة 📚", 1: "استمر في التعلم 💪", 0: "لا تستسلم! 💪"}
            await q.message.reply_text(
                f"🎯 *انتهى اختبار اليوم!*\n"
                "━━━━━━━━━━━━━━━\n\n"
                f"نتيجتك: {stars}\n"
                f"✅ {score} من 5\n\n"
                f"💬 {comment.get(score, 'أحسنت!')}\n\n"
                "تعال غداً لاختبار جديد 🌙",
                parse_mode="Markdown"
            )
        else:
            # السؤال التالي
            await send_quiz_question(q.message, context, questions[next_idx], next_idx + 1)

    elif q.data.startswith("dq_"):
        await q.answer()

    elif q.data == "weekly_hint":
        await q.answer()
        ch = get_weekly_challenge()
        await q.answer(f"💡 تلميح: {ch['hint']}", show_alert=True)

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

    elif q.data == "streak_read":
        streak = update_streak(user.id)
        emoji = streak_emoji(streak)
        # تحديث التحدي إن وجد
        duel = get_active_duel(user.id)
        duel_msg = ""
        if duel:
            result = update_duel_streak(user.id, duel["id"])
            if result:
                other_id = duel["opponent"] if duel["challenger"] == user.id else duel["challenger"]
                duel_msg = f"\n⚔️ سلسلة التحدي: {result['streak']} يوم"
                if result["broken"]:
                    try:
                        conn = sqlite3.connect("bot.db")
                        cur = conn.cursor()
                        cur.execute("SELECT full_name FROM users WHERE user_id=?", (other_id,))
                        row = cur.fetchone()
                        conn.close()
                        other_name = row[0] if row else "منافسك"
                        await context.bot.send_message(
                            user.id,
                            f"🏆 *{other_name}* انكسرت سلسلته في التحدي!\nأنت في المقدمة 🎉",
                            parse_mode="Markdown"
                        )
                    except:
                        pass
        if streak == 1:
            msg = f"✅ بارك الله فيك! بدأت سلسلتك اليوم {emoji}{duel_msg}"
        else:
            msg = f"✅ أحسنت! سلسلتك الآن {streak} يوم {emoji}{duel_msg}"
        await q.answer(msg, show_alert=True)

    elif q.data == "challenge_answer":
        await q.answer()
        if has_answered_today(user.id):
            await q.message.reply_text("✅ أجبت على تحدي اليوم مسبقاً!")
            return
        challenge = get_today_challenge()
        if not challenge:
            await q.message.reply_text("⚠️ ما في تحدي اليوم.")
            return
        context.user_data["in_challenge"] = True
        context.user_data["challenge_answer"] = challenge["answer"]
        context.user_data["challenge_full"] = challenge["full"]
        await q.message.reply_text(
            "✍️ أرسل الكلمة الناقصة الآن:",
        )

    elif q.data.startswith("mood_"):
        mood = q.data.split("_")[1]
        await q.answer()
        if get_tier(user.id) < 2:
            await q.answer("⭐ هذه الميزة للداعمين من Tier 2+", show_alert=True)
            return
        msg = await send_mood_hadith(user.id, mood, context)
        await q.message.reply_text(msg, parse_mode="Markdown")

    elif q.data.startswith("duel_accept_"):
        duel_id = int(q.data.split("_")[2])
        accept_duel(duel_id)
        await q.answer("✅ قبلت التحدي!")
        # أعلم المتحدي
        conn = sqlite3.connect("bot.db")
        cur = conn.cursor()
        cur.execute("SELECT challenger_id FROM duels WHERE id=?", (duel_id,))
        row = cur.fetchone()
        conn.close()
        if row:
            try:
                await context.bot.send_message(
                    row[0],
                    f"⚔️ *{user.full_name}* قبل تحديك!\n🔥 ابدأ بالضغط ✅ قرأت يومياً!",
                    parse_mode="Markdown"
                )
            except:
                pass
        await q.message.edit_text(
            "⚔️ *التحدي بدأ!*\n\nاضغط ✅ قرأت على حديث اليوم يومياً للحفاظ على سلسلتك!\n"
            "استخدم /duel لمتابعة التحدي.",
            parse_mode="Markdown"
        )

    elif q.data.startswith("duel_reject_"):
        duel_id = int(q.data.split("_")[2])
        reject_duel(duel_id)
        await q.answer("تم الرفض")
        conn = sqlite3.connect("bot.db")
        cur = conn.cursor()
        cur.execute("SELECT challenger_id FROM duels WHERE id=?", (duel_id,))
        row = cur.fetchone()
        conn.close()
        if row:
            try:
                await context.bot.send_message(row[0], f"❌ *{user.full_name}* رفض التحدي.", parse_mode="Markdown")
            except:
                pass
        await q.message.edit_text("❌ رفضت التحدي.")

    elif q.data.startswith("duel_forfeit_"):
        await q.answer()
        duel_id = int(q.data.split("_")[2])
        duel = get_active_duel(user.id)
        if duel:
            other_id = duel["opponent"] if duel["challenger"] == user.id else duel["challenger"]
            forfeit_duel(duel_id)
            try:
                await context.bot.send_message(
                    other_id,
                    f"🏆 *{user.full_name}* استسلم!\nأنت الفائز في التحدي! 🎉",
                    parse_mode="Markdown"
                )
            except:
                pass
            await q.message.edit_text("🏳️ استسلمت من التحدي.")

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
        parts = q.data.split("_", 2)
        if len(parts) == 3:
            target_uid = int(parts[1])
            charge_id = parts[2]
            try:
                await context.bot.refund_star_payment(
                    user_id=target_uid,
                    telegram_payment_charge_id=charge_id
                )
                # احذف من donations
                conn = sqlite3.connect("bot.db")
                conn.execute("DELETE FROM donations WHERE user_id=? AND charge_id=?", (target_uid, charge_id))
                conn.commit()
                conn.close()
                await q.message.reply_text(f"✅ تم استرداد النجوم للمستخدم {target_uid}")
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

    elif q.data.startswith("ntime_"):
        if not has_custom_time(user.id):
            await q.answer("⭐ تحتاج 25 نجمة لتخصيص الوقت! /donate", show_alert=True)
            return
        parts = q.data.split("_")
        hour, minute = int(parts[1]), int(parts[2])
        set_notif_time(user.id, hour, minute)
        await q.answer(f"✅ تم تعيين الوقت: {hour:02d}:{minute:02d}", show_alert=True)
        try:
            await q.message.delete()
        except:
            pass

async def show_search_page_from_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    results = context.user_data.get("search_results", [])
    page = context.user_data.get("search_page", 0)
    if not results:
        # حاول استرجاع الجلسة من DB
        session = load_user_session(update.effective_user.id)
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
    await update.callback_query.message.reply_text(msg, reply_markup=keyboard)
    try:
        save_user_session(user.id, results, page, cf, context.user_data.get("search_id", ""))
    except:
        pass

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
            InlineKeyboardButton("✅ نعم، أرسل التقرير", callback_data="confirm_report"),
            InlineKeyboardButton("❌ لا، إلغاء", callback_data="cancel_report"),
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
def run_web_server():
    """سيرفر بسيط يمنع Replit من النوم"""
    from http.server import HTTPServer, BaseHTTPRequestHandler
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write("راوِي | Bot is alive ✅".encode())
        def log_message(self, *args):
            pass  # يكتم logs السيرفر
    server = HTTPServer(("0.0.0.0", 8080), Handler)
    server.serve_forever()

def self_ping():
    """يقرع البوت نفسه كل 4 دقائق لمنع النوم"""
    import urllib.request as _req
    import time as _time
    _time.sleep(30)  # انتظر يشتغل البوت أولاً
    while True:
        try:
            _req.urlopen("http://localhost:8080", timeout=5)
        except:
            pass
        _time.sleep(240)  # كل 4 دقائق

def main():
    logger.info("🚀 بدء تشغيل بوت راوِي...")
    init_db()
    # شغّل web server في thread منفصل عشان Replit ما ينام
    from threading import Thread
    Thread(target=run_web_server, daemon=True).start()
    Thread(target=self_ping, daemon=True).start()
    logger.info("🌐 Web server شغّال على port 8080 + self-ping كل 4 دقائق")
    app = Application.builder().token(BOT_TOKEN).build()

    # جدولة الإشعارات اليومية
    # حديث اليوم - 7:00 صباحاً
    app.job_queue.run_daily(scheduled_notification, time=time(hour=7, minute=0, tzinfo=AMMAN_TZ), days=(0,1,2,3,4,5,6))
    # الأذكار تُرسل عند طلب المستخدم فقط (بدون جدولة)
    # إشعار الجمعة - 12:00 ظهراً بتوقيت الأردن
    app.job_queue.run_daily(send_friday_hadith, time=time(hour=12, minute=0, tzinfo=AMMAN_TZ), days=(4,))
    # تحدي اليوم - 5:00 مساءً بتوقيت الأردن
    app.job_queue.run_daily(send_daily_challenge, time=time(hour=17, minute=0, tzinfo=AMMAN_TZ), days=(0,1,2,3,4,5,6))
    # صديقي الروحي - كل جمعة 9:00 صباحاً بتوقيت الأردن
    app.job_queue.run_daily(send_spiritual_friend, time=time(hour=9, minute=0, tzinfo=AMMAN_TZ), days=(4,))

    # إضافة المعالجات - CommandHandlers أولاً دايماً قبل MessageHandler
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("version", version_command))
    app.add_handler(CommandHandler("testchallenge", testchallenge_command))
    app.add_handler(CommandHandler("asma", cmd_asma))
    app.add_handler(CommandHandler("sahaba", cmd_sahaba))
    app.add_handler(CommandHandler("question", cmd_daily_question))
    app.add_handler(CommandHandler("weekly", cmd_weekly_challenge))
    app.add_handler(CommandHandler("random", random_hadith))
    app.add_handler(CommandHandler("donate", donate_command))
    app.add_handler(CommandHandler("balance", cmd_balance))
    app.add_handler(CommandHandler("topics", cmd_topics))
    app.add_handler(CommandHandler("favorites", cmd_favorites))
    app.add_handler(CommandHandler("favs", cmd_favorites))
    app.add_handler(CommandHandler("settime", cmd_set_notif_time))
    app.add_handler(CommandHandler("challenge", cmd_challenge_now))
    app.add_handler(CommandHandler("duel", cmd_duel))
    app.add_handler(CommandHandler("history", cmd_history))
    app.add_handler(CommandHandler("mystatus", cmd_mystatus))

    # معالجات الدفع
    app.add_handler(PreCheckoutQueryHandler(precheckout_callback))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback))

    # معالج الأزرار التفاعلية
    app.add_handler(CallbackQueryHandler(handle_callback))

    # معالج الرسائل العام - دايماً آخر شي
    app.add_handler(MessageHandler(filters.ALL, handle_message))

    logger.info("✅ البوت جاهز!")
    app.run_polling(drop_pending_updates=True)

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

async def cmd_topics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بحث بالموضوع - للداعمين فقط"""
    user = update.effective_user
    if not has_topics(user.id):
        stars = get_premium_stars(user.id)
        await update.message.reply_text(
            f"🔎 بحث بالموضوع متاح لمن تبرع بنجمة واحدة فأكثر\n\n"
            f"إجمالي تبرعاتك: {stars} نجمة\n"
            f"تحتاج {max(0, TIER1_STARS - stars)} نجمة فقط لفتح هذه الميزة!\n\n"
            f"اضغط /donate للدعم 🤍"
        )
        return
    buttons = []
    topics_list = list(TOPICS.items())
    for i in range(0, len(topics_list), 3):
        row = [InlineKeyboardButton(k, callback_data=f"topic_{v}") for k, v in topics_list[i:i+3]]
        buttons.append(row)
    await update.message.reply_text(
        "🔎 اختر موضوعاً للبحث:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def cmd_favorites(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض المفضلة - للداعمين فقط"""
    user = update.effective_user
    if not has_favorites(user.id):
        stars = get_premium_stars(user.id)
        tier = get_tier(user.id)
        if tier == 0:
            await update.message.reply_text(
                f"💾 المفضلة متاحة من 5 نجوم فأكثر\n\n"
                f"إجمالي تبرعاتك: {stars} نجمة\n"
                f"تحتاج {max(0, TIER2_STARS - stars)} نجمة لفتح هذه الميزة!\n\n"
                f"اضغط /donate للدعم 🤍"
            )
        else:
            await update.message.reply_text(
                f"💾 المفضلة متاحة من 5 نجوم فأكثر\n\n"
                f"إجمالي تبرعاتك: {stars} نجمة\n"
                f"تحتاج {max(0, TIER2_STARS - stars)} نجمة إضافية!\n\n"
                f"اضغط /donate للدعم 🤍"
            )
        return
    favs = get_favorites(user.id)
    if not favs:
        await update.message.reply_text("📭 مفضلتك فارغة. ابحث عن حديث واضغط 💾 لحفظه.")
        return
    context.user_data["search_results"] = favs
    context.user_data["search_page"] = 0
    context.user_data["from_favorites"] = True
    h = favs[0]
    msg = build_hadith_msg(h, 0, len(favs))
    kb = build_keyboard(0, len(favs), h["id"], user_id=user.id, is_fav=True, context_filter="all")
    await update.message.reply_text(f"💾 مفضلتك ({len(favs)} حديث)\n\n" + msg, reply_markup=kb)

async def cmd_set_notif_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تخصيص وقت الإشعار - للداعمين"""
    user = update.effective_user
    if not has_custom_time(user.id):
        stars = get_premium_stars(user.id)
        await update.message.reply_text(
            f"🕐 تخصيص وقت الإشعار متاح من 25 نجمة فأكثر\n\n"
            f"إجمالي تبرعاتك: {stars} نجمة\n"
            f"تحتاج {max(0, TIER3_STARS - stars)} نجمة إضافية لفتح هذه الميزة!\n\n"
            f"اضغط /donate للدعم 🤍"
        )
        return
    # أزرار الأوقات
    times = [
        [InlineKeyboardButton("🌅 5:00 صباحاً", callback_data="ntime_5_0"),
         InlineKeyboardButton("🌄 6:00 صباحاً", callback_data="ntime_6_0")],
        [InlineKeyboardButton("☀️ 7:00 صباحاً", callback_data="ntime_7_0"),
         InlineKeyboardButton("🕗 8:00 صباحاً", callback_data="ntime_8_0")],
        [InlineKeyboardButton("🕙 10:00 صباحاً", callback_data="ntime_10_0"),
         InlineKeyboardButton("🕛 12:00 ظهراً", callback_data="ntime_12_0")],
        [InlineKeyboardButton("🌆 4:00 مساءً", callback_data="ntime_16_0"),
         InlineKeyboardButton("🌇 6:00 مساءً", callback_data="ntime_18_0")],
        [InlineKeyboardButton("🌙 8:00 مساءً", callback_data="ntime_20_0"),
         InlineKeyboardButton("🌃 9:00 مساءً", callback_data="ntime_21_0")],
    ]
    h, m = get_notif_time(user.id)
    await update.message.reply_text(
        f"🕐 *تخصيص وقت حديث اليوم*\n\n"
        f"وقتك الحالي: {h:02d}:{m:02d}\n"
        f"اختر الوقت الجديد:",
        reply_markup=InlineKeyboardMarkup(times),
        parse_mode="Markdown"
    )

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

async def cmd_duel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تحدي مع صديق - /duel @username"""
    user = update.effective_user
    args = context.args
    if not args:
        duel = get_active_duel(user.id)
        if duel:
            other_id = duel["opponent"] if duel["challenger"] == user.id else duel["challenger"]
            my_streak = duel["c_streak"] if duel["challenger"] == user.id else duel["o_streak"]
            their_streak = duel["o_streak"] if duel["challenger"] == user.id else duel["c_streak"]
            conn = sqlite3.connect("bot.db")
            cur = conn.cursor()
            cur.execute("SELECT full_name FROM users WHERE user_id=?", (other_id,))
            row = cur.fetchone()
            conn.close()
            other_name = row[0] if row else "منافسك"
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("🏳️ استسلام", callback_data=f"duel_forfeit_{duel['id']}")
            ]])
            await update.message.reply_text(
                f"⚔️ *تحديك الحالي*\n\n"
                f"منافسك: *{other_name}*\n"
                f"🔥 سلسلتك: {my_streak} يوم\n"
                f"💪 سلسلته: {their_streak} يوم\n\n"
                f"استمر في الضغط ✅ قرأت يومياً!",
                parse_mode="Markdown", reply_markup=kb
            )
        else:
            await update.message.reply_text(
                "⚔️ *تحدي مع صديق*\n\n"
                "تحدّ صديقك على من يحافظ على سلسلة أحاديثه أطول!\n\n"
                "الاستخدام:\n`/duel @username`\n\n"
                "مثال: `/duel @ahmad`",
                parse_mode="Markdown"
            )
        return
    target_username = args[0].lstrip("@")
    target_id = get_user_id_by_username(target_username)
    if not target_id:
        await update.message.reply_text(
            f"❌ المستخدم @{target_username} غير موجود في البوت.\n"
            "اطلب منه يفتح البوت أولاً."
        )
        return
    if target_id == user.id:
        await update.message.reply_text("❌ ما تقدر تتحدى نفسك 😄")
        return
    duel_id = create_duel(user.id, target_id)
    if duel_id == -1:
        await update.message.reply_text("⚠️ يوجد تحدٍ نشط بينكما مسبقاً!")
        return
    # أرسل دعوة للخصم
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ قبول التحدي", callback_data=f"duel_accept_{duel_id}"),
        InlineKeyboardButton("❌ رفض", callback_data=f"duel_reject_{duel_id}")
    ]])
    try:
        await context.bot.send_message(
            target_id,
            f"⚔️ *دعوة تحدي!*\n\n"
            f"*{user.full_name}* يتحداك على من يحافظ على سلسلة أحاديثه أطول 🔥\n\n"
            f"اضغط ✅ قبول للبدء!",
            parse_mode="Markdown", reply_markup=kb
        )
        await update.message.reply_text(
            f"✅ تم إرسال الدعوة إلى @{target_username}\n"
            "انتظر حتى يقبل التحدي!"
        )
    except:
        await update.message.reply_text("❌ ما قدرت أرسل الدعوة. تأكد أن المستخدم فتح البوت.")
        forfeit_duel(duel_id)

async def cmd_mood_hadith(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """حديث على قدك - Tier 2+"""
    user = update.effective_user
    if get_tier(user.id) < 2:
        await update.message.reply_text(
            "📖 حديث على قدك متاح من 5 نجوم فأكثر\n"
            f"تحتاج {max(0, TIER2_STARS - get_premium_stars(user.id))} نجمة إضافية!\n\n"
            "اضغط /donate للدعم 🤍"
        )
        return
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("😊 بخير والحمد لله", callback_data="mood_happy")],
        [InlineKeyboardButton("😔 متعب ومحتاج دعم", callback_data="mood_tired")],
        [InlineKeyboardButton("😤 ضايقني شيء", callback_data="mood_angry")],
    ])
    await update.message.reply_text(
        "📖 *حديث على قدك*\n\nكيف حالك اليوم؟",
        parse_mode="Markdown", reply_markup=kb
    )

async def cmd_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تاريخ البحث - آخر 20 بحث"""
    user = update.effective_user
    history = get_search_history(user.id)
    if not history:
        await update.message.reply_text("🔍 ما أجريت أي بحث بعد!")
        return
    msg = "📋 *آخر بحوثك:*\n\n"
    for i, (query, count, date) in enumerate(history, 1):
        msg += f"{i}. {query} — {count} نتيجة\n"
    await update.message.reply_text(msg, parse_mode="Markdown")

async def cmd_mystatus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """حالة الداعم"""
    user = update.effective_user
    stars = get_premium_stars(user.id)
    tier = get_tier(user.id)
    tier_label = get_tier_label(tier)
    features = get_tier_features(tier)
    favs = count_favorites(user.id) if has_favorites(user.id) else 0
    h, m = get_notif_time(user.id) if has_custom_time(user.id) else (7, 0)

    streak_data = get_streak(user.id)
    streak = streak_data["streak"]
    max_s = streak_data["max"]
    msg = (
        f"👤 *{user.full_name}*\n\n"
        f"{tier_label}\n"
        f"⭐ إجمالي التبرعات: {stars} نجمة\n\n"
        f"{streak_emoji(streak)} السلسلة الحالية: {streak} يوم\n"
        f"🏆 أطول سلسلة: {max_s} يوم\n\n"
        f"{features}"
    )
    if tier >= 2:
        msg += f"\n💾 المحفوظ في المفضلة: {favs} حديث"
    if tier >= 3:
        msg += f"\n🕐 وقت الإشعار المخصص: {h:02d}:{m:02d}"

    await update.message.reply_text(msg, parse_mode="Markdown")

async def cmd_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """رصيد البوت - للأدمن فقط"""
    user = update.effective_user
    if user.id not in ADMIN_IDS:
        return
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    # إجمالي النجوم
    cur.execute("SELECT SUM(amount) FROM donations")
    total = cur.fetchone()[0] or 0
    # عدد الداعمين
    cur.execute("SELECT COUNT(DISTINCT user_id) FROM donations")
    donors = cur.fetchone()[0] or 0
    # آخر 5 تبرعات
    cur.execute("""
        SELECT u.full_name, u.username, d.amount, d.date
        FROM donations d
        LEFT JOIN users u ON d.user_id = u.user_id
        ORDER BY d.date DESC LIMIT 5
    """)
    last5 = cur.fetchall()
    # توزيع المستويات
    cur.execute("SELECT user_id FROM donations GROUP BY user_id")
    all_donors = [r[0] for r in cur.fetchall()]
    conn.close()

    t1 = sum(1 for uid in all_donors if get_tier(uid) >= 1)
    t2 = sum(1 for uid in all_donors if get_tier(uid) >= 2)
    t3 = sum(1 for uid in all_donors if get_tier(uid) >= 3)

    msg = (
        f"💰 *رصيد البوت*\n"
        f"━━━━━━━━━━━━━━\n\n"
        f"⭐ إجمالي النجوم: *{total}*\n"
        f"👥 عدد الداعمين: *{donors}*\n\n"
        f"*توزيع المستويات:*\n"
        f"⭐ المستوى الأول (1+): {t1} داعم\n"
        f"⭐⭐ المستوى الثاني (5+): {t2} داعم\n"
        f"🌟 المستوى الثالث (25+): {t3} داعم\n\n"
        f"*آخر التبرعات:*\n"
    )
    for name, username, amount, date in last5:
        uname = f"@{username}" if username else "بدون يوزر"
        msg += f"• {name or 'مجهول'} ({uname}) — {amount}⭐ — {date[:10]}\n"

    await update.message.reply_text(msg, parse_mode="Markdown")


if __name__ == "__main__":
    main()
