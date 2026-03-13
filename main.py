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
    """رسالة النتيجة النهائية للتحدي"""
    total = len(ch["questions"])
    c_score = ch["creator_score"]
    o_score = ch["opponent_score"]
    c_name = ch["creator_name"]
    o_name = ch["opponent_name"] or "صديقك"
    c_stars = "⭐" * c_score + "☆" * (total - c_score)
    o_stars = "⭐" * o_score + "☆" * (total - o_score)
    if c_score > o_score:
        winner = f"🏆 الفائز: *{c_name}*"
    elif o_score > c_score:
        winner = f"🏆 الفائز: *{o_name}*"
    else:
        winner = "🤝 *تعادل!* كلاكما رائع!"
    return (
        "🎯 *نتيجة التحدي*\n"
        "━━━━━━━━━━━━━━━\n\n"
        f"👤 {c_name}: {c_score}/{total} {c_stars}\n"
        f"👤 {o_name}: {o_score}/{total} {o_stars}\n\n"
        f"{winner}"
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


def update_streak(user_id: int):
    """حدّث الاستريك للمستخدم"""
    today = _dt.datetime.now(AMMAN_TZ).strftime("%Y-%m-%d")
    try:
        with sqlite3.connect("bot.db") as conn:
            row = conn.execute(
                "SELECT streak, max_streak, last_date FROM streaks WHERE user_id=?",
                (user_id,)
            ).fetchone()
            if not row:
                conn.execute(
                    "INSERT INTO streaks (user_id, streak, max_streak, last_date) VALUES (?,1,1,?)",
                    (user_id, today)
                )
            else:
                streak, max_s, last_date = row
                yesterday = (_dt.datetime.now(AMMAN_TZ) - _dt.timedelta(days=1)).strftime("%Y-%m-%d")
                if last_date == today:
                    return
                elif last_date == yesterday:
                    streak += 1
                else:
                    streak = 1
                max_s = max(max_s, streak)
                conn.execute(
                    "UPDATE streaks SET streak=?, max_streak=?, last_date=? WHERE user_id=?",
                    (streak, max_s, today, user_id)
                )
    except Exception as e:
        logger.error(f"update_streak error: {e}")


# ==================== دوال تحدي اليوم ====================
    return get_streak(user_id)["streak"]

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
# بيانات أسماء الله الحسنى
# ══════════════════════════════════════════════
ASMA_ALLAH = [
    {"name": "الله", "meaning": "الاسم الجامع لجميع صفات الكمال", "dua": "اللهم أنت الله لا إله إلا أنت"},
    {"name": "الرحمن", "meaning": "ذو الرحمة الواسعة التي تشمل كل شيء", "dua": "يا رحمن ارحمني برحمتك"},
    {"name": "الرحيم", "meaning": "ذو الرحمة الخاصة بالمؤمنين", "dua": "يا رحيم ارحمني"},
    {"name": "الملك", "meaning": "المالك لكل شيء والمتصرف فيه", "dua": "يا ملك الملوك أعزني بطاعتك"},
    {"name": "القدوس", "meaning": "المنزّه عن كل عيب ونقص", "dua": "يا قدوس طهر قلبي من الذنوب"},
    {"name": "السلام", "meaning": "السالم من كل نقص والمسلّم لعباده", "dua": "يا سلام سلّمنا وسلّم ديننا"},
    {"name": "المؤمن", "meaning": "المصدّق لعباده ومؤمّنهم من عذابه", "dua": "يا مؤمن آمن روعتي"},
    {"name": "المهيمن", "meaning": "الرقيب الحافظ على كل شيء", "dua": "يا مهيمن احفظني"},
    {"name": "العزيز", "meaning": "الغالب الذي لا يُغلب", "dua": "يا عزيز أعزّني"},
    {"name": "الجبار", "meaning": "الذي يجبر الكسير ويقهر العصاة", "dua": "يا جبار اجبر كسري"},
    {"name": "المتكبر", "meaning": "المتعالي عن صفات النقص", "dua": "يا متكبر تكبّر على من ظلمني"},
    {"name": "الخالق", "meaning": "المُوجِد للأشياء من العدم", "dua": "يا خالق خلق في قلبي الإيمان"},
    {"name": "البارئ", "meaning": "المُميِّز للمخلوقات بعضها عن بعض", "dua": "يا بارئ أصلح فطرتي"},
    {"name": "المصور", "meaning": "الذي يُعطي كل مخلوق صورته", "dua": "يا مصور صوّر حياتي بالخير"},
    {"name": "الغفار", "meaning": "الكثير المغفرة لذنوب عباده", "dua": "يا غفار اغفر لي"},
    {"name": "القهار", "meaning": "الغالب على كل شيء", "dua": "يا قهار اقهر أعدائي"},
    {"name": "الوهاب", "meaning": "كثير العطاء بلا مقابل", "dua": "يا وهاب هب لي من فضلك"},
    {"name": "الرزاق", "meaning": "الذي يرزق جميع خلقه", "dua": "يا رزاق ارزقني رزقاً حلالاً"},
    {"name": "الفتاح", "meaning": "الذي يفتح أبواب الرزق والرحمة", "dua": "يا فتاح افتح لي أبواب رحمتك"},
    {"name": "العليم", "meaning": "المحيط علمه بكل شيء", "dua": "يا عليم علّمني ما ينفعني"},
    {"name": "القابض", "meaning": "الذي يقبض الأرزاق بحكمته", "dua": "يا قابض لا تقبض رحمتك عني"},
    {"name": "الباسط", "meaning": "الذي يبسط الأرزاق لمن يشاء", "dua": "يا باسط ابسط لي رزقك"},
    {"name": "الخافض", "meaning": "الذي يخفض الجبابرة والطغاة", "dua": "يا خافض اخفض كل عدو لي"},
    {"name": "الرافع", "meaning": "الذي يرفع أولياءه بطاعته", "dua": "يا رافع ارفع درجتي"},
    {"name": "المعز", "meaning": "الذي يُعزّ من يشاء", "dua": "يا معز أعزّني بطاعتك"},
    {"name": "المذل", "meaning": "الذي يُذلّ من يشاء", "dua": "يا مذل أذلّ نفسي لطاعتك"},
    {"name": "السميع", "meaning": "الذي يسمع كل شيء", "dua": "يا سميع اسمع دعائي"},
    {"name": "البصير", "meaning": "الذي يرى كل شيء", "dua": "يا بصير أبصرني بعيوبي"},
    {"name": "الحكم", "meaning": "الفاصل بين الحق والباطل", "dua": "يا حكم احكم لي بالحق"},
    {"name": "العدل", "meaning": "الموصوف بالعدل في كل أحكامه", "dua": "يا عدل أعطني حقي"},
    {"name": "اللطيف", "meaning": "الرفيق بعباده الخبير بدقائق الأمور", "dua": "يا لطيف الطف بي"},
    {"name": "الخبير", "meaning": "العالم بخفايا الأمور وبواطنها", "dua": "يا خبير أرشدني لما يرضيك"},
    {"name": "الحليم", "meaning": "الذي لا يُعجّل بالعقوبة", "dua": "يا حليم تجاوز عن تقصيري"},
    {"name": "العظيم", "meaning": "الذي له العظمة المطلقة", "dua": "يا عظيم عظّم في قلبي شأنك"},
    {"name": "الغفور", "meaning": "الكثير الغفران", "dua": "يا غفور اغفر لي ذنوبي"},
    {"name": "الشكور", "meaning": "الذي يُكثر الثواب على القليل", "dua": "يا شكور اجعلني من الشاكرين"},
    {"name": "العلي", "meaning": "المتعالي فوق خلقه", "dua": "يا علي ارفع همتي"},
    {"name": "الكبير", "meaning": "الكبير في ذاته وصفاته", "dua": "يا كبير كبّر في قلبي حبك"},
    {"name": "الحفيظ", "meaning": "الحافظ لكل شيء", "dua": "يا حفيظ احفظني وأهلي"},
    {"name": "المقيت", "meaning": "الرازق لكل مخلوق قوته", "dua": "يا مقيت أقت قلبي بحبك"},
    {"name": "الحسيب", "meaning": "الكافي لعباده والمحاسب لهم", "dua": "يا حسيب حاسبني حساباً يسيراً"},
    {"name": "الجليل", "meaning": "ذو الجلال والعظمة", "dua": "يا جليل جلّل حياتي بنورك"},
    {"name": "الكريم", "meaning": "الكثير العطاء", "dua": "يا كريم أكرمني بالعفو والعافية"},
    {"name": "الرقيب", "meaning": "المطّلع على كل شيء", "dua": "يا رقيب راقبني بعينك"},
    {"name": "المجيب", "meaning": "الذي يُجيب دعاء عباده", "dua": "يا مجيب أجب دعائي"},
    {"name": "الواسع", "meaning": "الواسع العلم والرحمة والقدرة", "dua": "يا واسع وسّع رزقي وصدري"},
    {"name": "الحكيم", "meaning": "ذو الحكمة البالغة", "dua": "يا حكيم أحكم أمري"},
    {"name": "الودود", "meaning": "الذي يُحب عباده الصالحين", "dua": "يا ودود حبّب إليّ طاعتك"},
    {"name": "المجيد", "meaning": "ذو المجد والشرف", "dua": "يا مجيد مجّد ذكرك في قلبي"},
    {"name": "الباعث", "meaning": "الذي يبعث الخلق يوم القيامة", "dua": "يا باعث ابعثني مع الصالحين"},
    {"name": "الشهيد", "meaning": "الشاهد على كل شيء", "dua": "يا شهيد اشهد أني أحبك"},
    {"name": "الحق", "meaning": "الثابت الوجود الذي لا يزول", "dua": "يا حق ثبّتني على الحق"},
    {"name": "الوكيل", "meaning": "الكافي من توكّل عليه", "dua": "يا وكيل إليك أفوّض أمري"},
    {"name": "القوي", "meaning": "ذو القوة التامة", "dua": "يا قوي قوّني على طاعتك"},
    {"name": "المتين", "meaning": "ذو القوة الشديدة التي لا تنفد", "dua": "يا متين أعني على أمري"},
    {"name": "الولي", "meaning": "الناصر لعباده المؤمنين", "dua": "يا ولي كن وليي"},
    {"name": "الحميد", "meaning": "المحمود في جميع أفعاله", "dua": "يا حميد اجعلني من الحامدين"},
    {"name": "المحصي", "meaning": "الذي أحصى كل شيء", "dua": "يا محصي لا تحصِ عليّ ذنوبي"},
    {"name": "المبدئ", "meaning": "الذي ابتدأ الخلق", "dua": "يا مبدئ ابدأ بي بالخير"},
    {"name": "المعيد", "meaning": "الذي يُعيد الخلق بعد الفناء", "dua": "يا معيد أعد عليّ رحمتك"},
    {"name": "المحيي", "meaning": "الذي يُحيي الأموات", "dua": "يا محيي أحيِ قلبي بالإيمان"},
    {"name": "المميت", "meaning": "الذي يُميت الأحياء", "dua": "يا مميت أمتني وأنت راضٍ عني"},
    {"name": "الحي", "meaning": "الدائم الحياة الذي لا يموت", "dua": "يا حي أحيِ حياتي بطاعتك"},
    {"name": "القيوم", "meaning": "القائم بنفسه المُقيم لغيره", "dua": "يا قيوم لا تكلني إلى نفسي"},
    {"name": "الواجد", "meaning": "الغني الذي لا يفتقر", "dua": "يا واجد أغنني بك عمن سواك"},
    {"name": "الماجد", "meaning": "ذو المجد الواسع", "dua": "يا ماجد ارزقني حسن الخاتمة"},
    {"name": "الواحد", "meaning": "المنفرد بالوحدانية", "dua": "يا واحد وحّد قلبي عليك"},
    {"name": "الأحد", "meaning": "الواحد الفرد الذي لا شريك له", "dua": "يا أحد لا تجعل في قلبي سواك"},
    {"name": "الصمد", "meaning": "الذي يُصمد إليه في الحاجات", "dua": "يا صمد إليك أصمد في كل حاجتي"},
    {"name": "القادر", "meaning": "المتمكن من فعل كل شيء", "dua": "يا قادر قدّر لي الخير"},
    {"name": "المقتدر", "meaning": "البالغ القدرة التامة", "dua": "يا مقتدر لا يعجزك شيء فيسّر أمري"},
    {"name": "المقدم", "meaning": "الذي يُقدّم من يشاء", "dua": "يا مقدم قدّمني عندك"},
    {"name": "المؤخر", "meaning": "الذي يؤخر من يشاء", "dua": "يا مؤخر أخّر عني السوء"},
    {"name": "الأول", "meaning": "الذي لا ابتداء له", "dua": "يا أول ابتدئ حياتي بالتوبة"},
    {"name": "الآخر", "meaning": "الذي لا انتهاء له", "dua": "يا آخر اختم عمري بالصلاح"},
    {"name": "الظاهر", "meaning": "الغالب الذي دلّت عليه المخلوقات", "dua": "يا ظاهر أظهر حجتي"},
    {"name": "الباطن", "meaning": "العالم بكل خفيّ", "dua": "يا باطن أصلح باطني"},
    {"name": "الوالي", "meaning": "المالك لكل شيء المتصرف فيه", "dua": "يا والي تولَّ أمري"},
    {"name": "المتعالي", "meaning": "المتنزّه عن صفات الخلق", "dua": "يا متعالي لا حول ولا قوة إلا بك"},
    {"name": "البر", "meaning": "كثير الإحسان والبر", "dua": "يا بر أحسن إليّ"},
    {"name": "التواب", "meaning": "الذي يقبل توبة عباده", "dua": "يا تواب تب عليّ"},
    {"name": "المنتقم", "meaning": "الذي ينتقم من الظالمين", "dua": "يا منتقم انتقم لي من ظلمني"},
    {"name": "العفو", "meaning": "الذي يمحو الذنوب ويعفو عنها", "dua": "يا عفو اعف عني"},
    {"name": "الرؤوف", "meaning": "ذو الرأفة الشديدة", "dua": "يا رؤوف ارأف بي"},
    {"name": "مالك الملك", "meaning": "المالك لكل ملك", "dua": "يا مالك الملك اجعل لي نصيباً من ملكك"},
    {"name": "ذو الجلال والإكرام", "meaning": "المستحق للتعظيم والإكرام", "dua": "يا ذا الجلال والإكرام لا تحرمني"},
    {"name": "المقسط", "meaning": "العادل في حكمه", "dua": "يا مقسط أقسط لي"},
    {"name": "الجامع", "meaning": "الذي يجمع الخلائق ليوم الحساب", "dua": "يا جامع اجمع شملي"},
    {"name": "الغني", "meaning": "الذي لا يحتاج لأحد", "dua": "يا غني أغنني"},
    {"name": "المغني", "meaning": "الذي يُغني من يشاء", "dua": "يا مغني أغنني بحلالك عن حرامك"},
    {"name": "المانع", "meaning": "الذي يمنع ما يشاء", "dua": "يا مانع امنع عني السوء"},
    {"name": "الضار", "meaning": "الذي يضر من يشاء بحكمته", "dua": "يا ضار لا تسلّط عليّ من يضرني"},
    {"name": "النافع", "meaning": "الذي يُنفع من يشاء", "dua": "يا نافع انفعني"},
    {"name": "النور", "meaning": "الذي يُنير الكون بنوره", "dua": "يا نور أنر قلبي"},
    {"name": "الهادي", "meaning": "الذي يهدي من يشاء", "dua": "يا هادي اهدني صراطك المستقيم"},
    {"name": "البديع", "meaning": "الذي ابتدع الخلق على غير مثال", "dua": "يا بديع أبدع في حياتي"},
    {"name": "الباقي", "meaning": "الدائم الذي لا يفنى", "dua": "يا باقي أبقِ إيماني"},
    {"name": "الوارث", "meaning": "الذي يرث الأرض ومن عليها", "dua": "يا وارث أورثني الفردوس"},
    {"name": "الرشيد", "meaning": "الذي يُرشد خلقه", "dua": "يا رشيد أرشدني"},
    {"name": "الصبور", "meaning": "الذي لا يُعجّل بعقوبة العصاة", "dua": "يا صبور علّمني الصبر"},
]

SAHABA_QUIZ = [
    {"name": "أبو بكر الصديق", "hints": ["أول الخلفاء الراشدين", "رفيق النبي ﷺ في الهجرة", "لُقّب بالصدّيق"], "fact": "أول من أسلم من الرجال الأحرار وأعتق سبعة من المستضعفين", "bio": "عبدالله بن عثمان القرشي التيمي"},
    {"name": "عمر بن الخطاب", "hints": ["الخليفة الثاني", "لُقّب بالفاروق", "فتح بيت المقدس في عهده"], "fact": "أسلم فكان إسلامه فتحاً وهجرته نصراً وإمارته رحمة", "bio": "عمر بن الخطاب العدوي القرشي"},
    {"name": "عثمان بن عفان", "hints": ["ذو النورين", "جمع القرآن في مصحف واحد", "تزوج بنتين للنبي ﷺ"], "fact": "جمع القرآن الكريم وأرسل المصاحف إلى الأمصار", "bio": "عثمان بن عفان الأموي القرشي"},
    {"name": "علي بن أبي طالب", "hints": ["ابن عم النبي ﷺ", "الخليفة الرابع", "أسد الله الغالب"], "fact": "أول من أسلم من الصبيان وزوج فاطمة الزهراء", "bio": "علي بن أبي طالب الهاشمي"},
    {"name": "خالد بن الوليد", "hints": ["سيف الله المسلول", "لم يُهزم في معركة قط", "قائد جيوش الفتح"], "fact": "لقّبه النبي ﷺ بسيف الله المسلول وقاد مئة معركة لم يُهزم فيها", "bio": "خالد بن الوليد المخزومي"},
    {"name": "بلال بن رباح", "hints": ["أول مؤذن في الإسلام", "الحبشي الأصل", "عذّبه أمية بن خلف"], "fact": "اشتراه أبو بكر الصديق وأعتقه لما رأى تعذيبه على الإسلام", "bio": "بلال بن رباح الحبشي"},
    {"name": "عبدالله بن مسعود", "hints": ["أول من جهر بتلاوة القرآن في مكة", "بكى النبي ﷺ لقراءته", "من فقهاء الصحابة"], "fact": "قال النبي ﷺ: من أحب أن يقرأ القرآن غضاً فليقرأه على قراءة ابن مسعود", "bio": "عبدالله بن مسعود الهذلي"},
    {"name": "أبو هريرة", "hints": ["أكثر الصحابة رواية للحديث", "لُقّب بكنيته لحبه للقطط", "من أهل الصُّفّة"], "fact": "روى أكثر من 5000 حديث عن النبي ﷺ", "bio": "عبدالرحمن بن صخر الدوسي"},
    {"name": "عائشة بنت أبي بكر", "hints": ["أحب زوجات النبي إليه بعد خديجة", "الحميراء", "نزل فيها القرآن"], "fact": "قال النبي ﷺ: خذوا نصف دينكم عن الحميراء", "bio": "عائشة بنت أبي بكر الصديق"},
    {"name": "معاذ بن جبل", "hints": ["أعلم الصحابة بالحلال والحرام", "بعثه النبي ﷺ إلى اليمن", "توفي بطاعون عمواس"], "fact": "قال النبي ﷺ: أعلم أمتي بالحلال والحرام معاذ بن جبل", "bio": "معاذ بن جبل الأنصاري الخزرجي"},
    {"name": "سعد بن أبي وقاص", "hints": ["أول من رمى بسهم في الإسلام", "فاتح الفرس", "مستجاب الدعوة"], "fact": "قال له النبي ﷺ: ارمِ سعد فداك أبي وأمي", "bio": "سعد بن أبي وقاص الزهري"},
    {"name": "الزبير بن العوام", "hints": ["ابن عمة النبي ﷺ", "حواري رسول الله", "أحد العشرة المبشرين"], "fact": "قال النبي ﷺ: إن لكل نبي حوارياً وحواريّ الزبير بن العوام", "bio": "الزبير بن العوام الأسدي القرشي"},
    {"name": "طلحة بن عبيدالله", "hints": ["طلحة الخير", "ترّس النبي ﷺ بجسده يوم أُحد", "أحد العشرة المبشرين"], "fact": "شُلّت يده يوم أُحد دفاعاً عن النبي ﷺ فسمّاه النبي طلحة الخير", "bio": "طلحة بن عبيدالله التيمي"},
    {"name": "عبدالرحمن بن عوف", "hints": ["من العشرة المبشرين بالجنة", "أغنى تجار قريش", "هاجر بماله"], "fact": "قال النبي ﷺ: بارك الله فيك يا ابن عوف فإنك من الأغنياء الشاكرين", "bio": "عبدالرحمن بن عوف الزهري"},
    {"name": "أبو عبيدة بن الجراح", "hints": ["أمين هذه الأمة", "فاتح الشام", "توفي بطاعون عمواس"], "fact": "لقّبه النبي ﷺ بأمين هذه الأمة وولّاه فتح الشام", "bio": "عامر بن عبدالله الفهري القرشي"},
]

def main_kb(is_admin=False, daily_sub=False, adhkar_sub=False, tier=0):
    from telegram import ReplyKeyboardMarkup, KeyboardButton
    buttons = [
        [KeyboardButton("🔍 تحقق من حديث"), KeyboardButton("📜 اقترح لي حديثاً")],
        [KeyboardButton("✨ اسم الله اليوم"), KeyboardButton("🎯 اختبر معلوماتك")],
        [KeyboardButton("🤲 دعاء اليوم"), KeyboardButton("📤 مشاركة")],
        [KeyboardButton("⚔️ تحدي صديق"), KeyboardButton("👤 ملفي")],
        [KeyboardButton("💰 دعم البوت"), KeyboardButton("ℹ️ عن البوت")],
    ]
    if is_admin:
        buttons.append([KeyboardButton("⚙️ لوحة التحكم")])
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

def admin_main_keyboard():
    from telegram import ReplyKeyboardMarkup, KeyboardButton
    buttons = [
        [KeyboardButton("📢 إشعار عام"), KeyboardButton("📢 إشعار متقدم")],
        [KeyboardButton("📊 إحصائيات"), KeyboardButton("📅 إحصائيات الأسبوع")],
        [KeyboardButton("📈 نمو يومي"), KeyboardButton("⏰ أوقات النشاط")],
        [KeyboardButton("🏆 أنشط المستخدمين"), KeyboardButton("🆕 مستخدمون جدد")],
        [KeyboardButton("🌟 قائمة الداعمين"), KeyboardButton("🔍 بحث مستخدم")],
        [KeyboardButton("🗑️ حذف مستخدم"), KeyboardButton("🎁 منح مستوى")],
        [KeyboardButton("✏️ رسالة الترحيب"), KeyboardButton("⏸ إيقاف البحث")],
        [KeyboardButton("💰 استرداد نجوم"), KeyboardButton("🔙 القائمة الرئيسية")],
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
        [KeyboardButton("⭐ 50 نجمة")],
        [KeyboardButton("🔙 رجوع")],
    ], resize_keyboard=True)

def get_weekly_stats():
    try:
        week_ago = (_dt.datetime.now(AMMAN_TZ) - _dt.timedelta(days=7)).strftime("%Y-%m-%d")
        with sqlite3.connect("bot.db") as conn:
            new_users = conn.execute("SELECT COUNT(*) FROM users WHERE joined_at >= ?", (week_ago,)).fetchone()[0]
            searches = conn.execute("SELECT COUNT(*) FROM search_history WHERE searched_at >= ?", (week_ago,)).fetchone()[0]
        return {"new_users": new_users, "searches": searches}
    except Exception:
        return {"new_users": 0, "searches": 0}

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

def has_answered_today(user_id):
    today = _dt.datetime.now(AMMAN_TZ).strftime("%Y-%m-%d")
    try:
        with sqlite3.connect("bot.db") as conn:
            row = conn.execute("SELECT 1 FROM challenge_answers WHERE user_id=? AND date=?", (user_id, today)).fetchone()
        return bool(row)
    except Exception:
        return False

def save_challenge_answer(user_id, is_correct):
    today = _dt.datetime.now(AMMAN_TZ).strftime("%Y-%m-%d")
    try:
        with sqlite3.connect("bot.db") as conn:
            conn.execute("INSERT OR IGNORE INTO challenge_answers (user_id, date, correct) VALUES (?,?,?)", (user_id, today, int(is_correct)))
    except Exception as e:
        logger.error(f"save_challenge_answer: {e}")

def get_setting(key, default=""):
    try:
        with sqlite3.connect("bot.db") as conn:
            row = conn.execute("SELECT value FROM bot_settings WHERE key=?", (key,)).fetchone()
        return row[0] if row else default
    except Exception:
        return default

def save_setting(key, value):
    try:
        with sqlite3.connect("bot.db") as conn:
            conn.execute("INSERT OR REPLACE INTO bot_settings (key, value) VALUES (?,?)", (key, value))
    except Exception as e:
        logger.error(f"save_setting: {e}")

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

def get_sahaba_of_day():
    day = _dt.datetime.now(AMMAN_TZ).timetuple().tm_yday
    return SAHABA_QUIZ[day % len(SAHABA_QUIZ)]

def get_question_of_day():
    import random as _rnd
    day = _dt.datetime.now(AMMAN_TZ).timetuple().tm_yday
    _rnd.seed(day)
    q = _rnd.choice(DAILY_QUESTIONS)
    _rnd.seed()
    return q

def get_weekly_challenge():
    import random as _rw
    week = _dt.datetime.now(AMMAN_TZ).isocalendar()[1]
    year = _dt.datetime.now(AMMAN_TZ).year
    _rw.seed(year * 100 + week)
    ch = _rw.choice(DAILY_QUESTIONS)
    _rw.seed()
    return {"week": f"{year}-W{week:02d}", "text": ch["q"], "answer": ch["answer"], "hint": ch["explain"], "options": ch["options"]}

def has_answered_weekly(user_id, week):
    try:
        with sqlite3.connect("bot.db") as conn:
            row = conn.execute("SELECT 1 FROM weekly_answers WHERE user_id=? AND week=?", (user_id, week)).fetchone()
        return bool(row)
    except Exception:
        return False

def get_weekly_scores(week):
    try:
        with sqlite3.connect("bot.db") as conn:
            rows = conn.execute(
                "SELECT wa.user_id, u.full_name, wa.correct FROM weekly_answers wa "
                "JOIN users u ON wa.user_id=u.user_id WHERE wa.week=? ORDER BY wa.correct DESC, wa.answered_at ASC", (week,)
            ).fetchall()
        return rows
    except Exception:
        return []

def save_weekly_answer(user_id, week, answer, correct):
    try:
        with sqlite3.connect("bot.db") as conn:
            conn.execute(
                "INSERT OR IGNORE INTO weekly_answers (user_id, week, answer, correct, answered_at) VALUES (?,?,?,?,datetime('now'))",
                (user_id, week, answer, int(correct))
            )
    except Exception as e:
        logger.error(f"save_weekly_answer: {e}")

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
    return "✅ جميع المزايا متاحة للجميع مجاناً"
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

DAILY_DUAA = [
    {"text": "رَبَّنَا آتِنَا فِي الدُّنْيَا حَسَنَةً وَفِي الْآخِرَةِ حَسَنَةً وَقِنَا عَذَابَ النَّارِ", "source": "القرآن الكريم — البقرة 201", "meaning": "دعاء جامع لخيري الدنيا والآخرة"},
    {"text": "اللَّهُمَّ إِنِّي أَعُوذُ بِكَ مِنَ الْهَمِّ وَالْحَزَنِ، وَالْعَجْزِ وَالْكَسَلِ، وَالْبُخْلِ وَالْجُبْنِ، وَضَلَعِ الدَّيْنِ وَغَلَبَةِ الرِّجَالِ", "source": "صحيح البخاري", "meaning": "دعاء النبي ﷺ للاستعاذة من آفات النفس"},
    {"text": "رَبِّ اشْرَحْ لِي صَدْرِي وَيَسِّرْ لِي أَمْرِي وَاحْلُلْ عُقْدَةً مِّن لِّسَانِي يَفْقَهُوا قَوْلِي", "source": "القرآن الكريم — طه 25-28", "meaning": "دعاء موسى عليه السلام بالتوفيق والبيان"},
    {"text": "اللَّهُمَّ أَصْلِحْ لِي دِينِي الَّذِي هُوَ عِصْمَةُ أَمْرِي، وَأَصْلِحْ لِي دُنْيَايَ الَّتِي فِيهَا مَعَاشِي، وَأَصْلِحْ لِي آخِرَتِي الَّتِي فِيهَا مَعَادِي", "source": "صحيح مسلم", "meaning": "دعاء جامع لإصلاح الدين والدنيا والآخرة"},
    {"text": "رَبَّنَا لَا تُزِغْ قُلُوبَنَا بَعْدَ إِذْ هَدَيْتَنَا وَهَبْ لَنَا مِن لَّدُنكَ رَحْمَةً إِنَّكَ أَنتَ الْوَهَّابُ", "source": "القرآن الكريم — آل عمران 8", "meaning": "دعاء الثبات على الهداية"},
    {"text": "اللَّهُمَّ إِنِّي أَسْأَلُكَ الْعَفْوَ وَالْعَافِيَةَ فِي الدُّنْيَا وَالْآخِرَةِ", "source": "سنن أبي داود وابن ماجه — صحيح", "meaning": "من أجمع الأدعية وأحبها إلى النبي ﷺ"},
    {"text": "رَبِّ إِنِّي لِمَا أَنزَلْتَ إِلَيَّ مِنْ خَيْرٍ فَقِيرٌ", "source": "القرآن الكريم — القصص 24", "meaning": "دعاء موسى عليه السلام بالافتقار إلى الله"},
    {"text": "اللَّهُمَّ اغْفِرْ لِي وَارْحَمْنِي وَاهْدِنِي وَعَافِنِي وَارْزُقْنِي", "source": "صحيح مسلم", "meaning": "دعاء جامع علّمه النبي ﷺ"},
    {"text": "لَا إِلَهَ إِلَّا أَنتَ سُبْحَانَكَ إِنِّي كُنتُ مِنَ الظَّالِمِينَ", "source": "القرآن الكريم — الأنبياء 87", "meaning": "دعاء يونس عليه السلام في بطن الحوت"},
    {"text": "اللَّهُمَّ أَعِنِّي عَلَى ذِكْرِكَ وَشُكْرِكَ وَحُسْنِ عِبَادَتِكَ", "source": "سنن أبي داود — صحيح", "meaning": "دعاء علّمه النبي ﷺ لمعاذ بن جبل"},
    {"text": "رَبَّنَا ظَلَمْنَا أَنفُسَنَا وَإِن لَّمْ تَغْفِرْ لَنَا وَتَرْحَمْنَا لَنَكُونَنَّ مِنَ الْخَاسِرِينَ", "source": "القرآن الكريم — الأعراف 23", "meaning": "دعاء آدم وحواء عليهما السلام بالتوبة"},
    {"text": "اللَّهُمَّ إِنِّي أَسْأَلُكَ عِلْمًا نَافِعًا وَرِزْقًا طَيِّبًا وَعَمَلًا مُتَقَبَّلًا", "source": "سنن ابن ماجه — صحيح", "meaning": "دعاء الصباح النبوي"},
    {"text": "حَسْبِيَ اللَّهُ لَا إِلَهَ إِلَّا هُوَ عَلَيْهِ تَوَكَّلْتُ وَهُوَ رَبُّ الْعَرْشِ الْعَظِيمِ", "source": "القرآن الكريم — التوبة 129", "meaning": "دعاء التوكل على الله"},
    {"text": "اللَّهُمَّ إِنِّي أَعُوذُ بِكَ مِنْ عِلْمٍ لَا يَنْفَعُ وَمِنْ قَلْبٍ لَا يَخْشَعُ وَمِنْ نَفْسٍ لَا تَشْبَعُ وَمِنْ دَعْوَةٍ لَا يُسْتَجَابُ لَهَا", "source": "صحيح مسلم", "meaning": "دعاء النبي ﷺ من أربع آفات"},
    {"text": "رَبِّ زِدْنِي عِلْمًا", "source": "القرآن الكريم — طه 114", "meaning": "أمر الله نبيه بطلب الزيادة من العلم"},
    {"text": "اللَّهُمَّ أَلِّفْ بَيْنَ قُلُوبِنَا وَأَصْلِحْ ذَاتَ بَيْنِنَا وَاهْدِنَا سُبُلَ السَّلَامِ", "source": "مسند أحمد وسنن أبي داود — صحيح", "meaning": "دعاء الأُلفة والمحبة بين المسلمين"},
    {"text": "رَبَّنَا هَبْ لَنَا مِنْ أَزْوَاجِنَا وَذُرِّيَّاتِنَا قُرَّةَ أَعْيُنٍ وَاجْعَلْنَا لِلْمُتَّقِينَ إِمَامًا", "source": "القرآن الكريم — الفرقان 74", "meaning": "دعاء عباد الرحمن للذرية الصالحة"},
    {"text": "اللَّهُمَّ اجْعَلْ فِي قَلْبِي نُورًا وَفِي لِسَانِي نُورًا وَفِي سَمْعِي نُورًا وَفِي بَصَرِي نُورًا", "source": "صحيح البخاري", "meaning": "دعاء النور الشامل من هدي النبي ﷺ"},
    {"text": "رَبَّنَا اغْفِرْ لَنَا وَلِإِخْوَانِنَا الَّذِينَ سَبَقُونَا بِالْإِيمَانِ", "source": "القرآن الكريم — الحشر 10", "meaning": "دعاء المؤمنين لمن سبقهم بالإيمان"},
    {"text": "اللَّهُمَّ إِنَّكَ عَفُوٌّ تُحِبُّ الْعَفْوَ فَاعْفُ عَنِّي", "source": "سنن الترمذي — صحيح", "meaning": "دعاء ليلة القدر علّمه النبي ﷺ لعائشة"},
    {"text": "رَبِّ أَوْزِعْنِي أَنْ أَشْكُرَ نِعْمَتَكَ الَّتِي أَنْعَمْتَ عَلَيَّ وَعَلَى وَالِدَيَّ وَأَنْ أَعْمَلَ صَالِحًا تَرْضَاهُ", "source": "القرآن الكريم — الأحقاف 15", "meaning": "دعاء المؤمن بالشكر على النعم وصلاح العمل"},
    {"text": "اللَّهُمَّ إِنِّي أَسْأَلُكَ الْجَنَّةَ وَأَعُوذُ بِكَ مِنَ النَّارِ", "source": "سنن أبي داود — صحيح", "meaning": "من أبسط وأعظم الأدعية"},
    {"text": "سُبْحَانَكَ اللَّهُمَّ وَبِحَمْدِكَ أَشْهَدُ أَنْ لَا إِلَهَ إِلَّا أَنتَ أَسْتَغْفِرُكَ وَأَتُوبُ إِلَيْكَ", "source": "سنن الترمذي — صحيح", "meaning": "كفارة المجلس"},
    {"text": "رَبِّ اجْعَلْنِي مُقِيمَ الصَّلَاةِ وَمِن ذُرِّيَّتِي رَبَّنَا وَتَقَبَّلْ دُعَاءِ", "source": "القرآن الكريم — إبراهيم 40", "meaning": "دعاء إبراهيم عليه السلام بإقامة الصلاة"},
    {"text": "اللَّهُمَّ آتِ نَفْسِي تَقْوَاهَا وَزَكِّهَا أَنتَ خَيْرُ مَن زَكَّاهَا أَنتَ وَلِيُّهَا وَمَوْلَاهَا", "source": "صحيح مسلم", "meaning": "دعاء تزكية النفس"},
    {"text": "رَبَّنَا أَفْرِغْ عَلَيْنَا صَبْرًا وَثَبِّتْ أَقْدَامَنَا وَانصُرْنَا عَلَى الْقَوْمِ الْكَافِرِينَ", "source": "القرآن الكريم — البقرة 250", "meaning": "دعاء الثبات والنصر"},
    {"text": "اللَّهُمَّ إِنِّي أَسْأَلُكَ حُبَّكَ وَحُبَّ مَن يُحِبُّكَ وَحُبَّ عَمَلٍ يُقَرِّبُنِي إِلَى حُبِّكَ", "source": "سنن الترمذي — حسن", "meaning": "دعاء طلب محبة الله"},
    {"text": "رَبَّنَا لَا تُؤَاخِذْنَا إِن نَّسِينَا أَوْ أَخْطَأْنَا", "source": "القرآن الكريم — البقرة 286", "meaning": "من آخر البقرة التي أجاب الله كل دعاء فيها بنعم"},
    {"text": "اللَّهُمَّ اهْدِنِي وَسَدِّدْنِي", "source": "صحيح مسلم", "meaning": "دعاء الهداية والسداد علّمه النبي ﷺ لعلي"},
    {"text": "اللَّهُمَّ إِنِّي أَسْأَلُكَ الثَّبَاتَ فِي الْأَمْرِ، وَأَسْأَلُكَ عَزِيمَةَ الرُّشْدِ، وَأَسْأَلُكَ شُكْرَ نِعْمَتِكَ، وَحُسْنَ عِبَادَتِكَ", "source": "سنن النسائي — صحيح", "meaning": "دعاء جامع للثبات والرشد والشكر"},
    {"text": "اللَّهُمَّ إِنِّي أَسْأَلُكَ الْهُدَى وَالتُّقَى وَالْعَفَافَ وَالْغِنَى", "source": "صحيح مسلم", "meaning": "أربع خصال جمع فيها النبي ﷺ خير الدنيا والآخرة"},
    {"text": "اللَّهُمَّ مُصَرِّفَ الْقُلُوبِ صَرِّفْ قُلُوبَنَا عَلَى طَاعَتِكَ", "source": "صحيح مسلم", "meaning": "دعاء تثبيت القلب على الطاعة"},
    {"text": "رَبَّنَا اصْرِفْ عَنَّا عَذَابَ جَهَنَّمَ إِنَّ عَذَابَهَا كَانَ غَرَامًا", "source": "القرآن الكريم — الفرقان 65", "meaning": "دعاء عباد الرحمن للنجاة من عذاب جهنم"},
    {"text": "اللَّهُمَّ أَحْسِنْ عَاقِبَتَنَا فِي الْأُمُورِ كُلِّهَا، وَأَجِرْنَا مِنْ خِزْيِ الدُّنْيَا وَعَذَابِ الْآخِرَةِ", "source": "المعجم الكبير للطبراني — صحيح", "meaning": "دعاء حسن الخاتمة والنجاة"},
    {"text": "يَا مُقَلِّبَ الْقُلُوبِ ثَبِّتْ قَلْبِي عَلَى دِينِكَ", "source": "سنن الترمذي — صحيح", "meaning": "كان النبي ﷺ يكثر من هذا الدعاء"},
    {"text": "اللَّهُمَّ إِنِّي أَعُوذُ بِرِضَاكَ مِنْ سَخَطِكَ، وَبِمُعَافَاتِكَ مِنْ عُقُوبَتِكَ، وَأَعُوذُ بِكَ مِنْكَ", "source": "صحيح مسلم", "meaning": "من دعاء النبي ﷺ في سجوده"},
    {"text": "رَبَّنَا آمَنَّا فَاغْفِرْ لَنَا وَارْحَمْنَا وَأَنتَ خَيْرُ الرَّاحِمِينَ", "source": "القرآن الكريم — المؤمنون 109", "meaning": "دعاء المؤمنين طالبين المغفرة والرحمة"},
    {"text": "اللَّهُمَّ اجْعَلْنِي صَبُورًا وَاجْعَلْنِي شَكُورًا وَاجْعَلْنِي فِي عَيْنِي صَغِيرًا وَفِي أَعْيُنِ النَّاسِ كَبِيرًا", "source": "المستدرك للحاكم — صحيح", "meaning": "دعاء التواضع وحسن السيرة"},
    {"text": "رَبِّ هَبْ لِي حُكْمًا وَأَلْحِقْنِي بِالصَّالِحِينَ", "source": "القرآن الكريم — الشعراء 83", "meaning": "دعاء إبراهيم عليه السلام بالحكمة والصلاح"},
    {"text": "اللَّهُمَّ اجْعَلْ أَوَّلَ هَذَا النَّهَارِ صَلَاحًا وَأَوْسَطَهُ فَلَاحًا وَآخِرَهُ نَجَاحًا", "source": "سنن أبي داود — حسن", "meaning": "دعاء بركة اليوم من أوله لآخره"},
    {"text": "رَبَّنَا اغْفِرْ لِي وَلِوَالِدَيَّ وَلِلْمُؤْمِنِينَ يَوْمَ يَقُومُ الْحِسَابُ", "source": "القرآن الكريم — إبراهيم 41", "meaning": "دعاء إبراهيم عليه السلام للمغفرة يوم القيامة"},
    {"text": "اللَّهُمَّ إِنِّي أَسْأَلُكَ فِعْلَ الْخَيْرَاتِ وَتَرْكَ الْمُنْكَرَاتِ وَحُبَّ الْمَسَاكِينِ", "source": "سنن الترمذي — صحيح", "meaning": "من دعاء الإسراء، طلب فعل الخيرات وحب الفقراء"},
    {"text": "رَبَّنَا لَا تَجْعَلْنَا فِتْنَةً لِّلْقَوْمِ الظَّالِمِينَ وَنَجِّنَا بِرَحْمَتِكَ مِنَ الْقَوْمِ الْكَافِرِينَ", "source": "القرآن الكريم — يونس 85-86", "meaning": "دعاء المؤمنين مع موسى عليه السلام"},
    {"text": "اللَّهُمَّ أَنْتَ رَبِّي لَا إِلَهَ إِلَّا أَنْتَ خَلَقْتَنِي وَأَنَا عَبْدُكَ وَأَنَا عَلَى عَهْدِكَ وَوَعْدِكَ مَا اسْتَطَعْتُ", "source": "صحيح البخاري", "meaning": "سيد الاستغفار — من قاله موقناً فمات دخل الجنة"},
    {"text": "رَبَّنَا آتِنَا مِن لَّدُنكَ رَحْمَةً وَهَيِّئْ لَنَا مِنْ أَمْرِنَا رَشَدًا", "source": "القرآن الكريم — الكهف 10", "meaning": "دعاء أصحاب الكهف بالرحمة والهداية"},
    {"text": "اللَّهُمَّ إِنِّي أَعُوذُ بِكَ مِنَ الْفَقْرِ وَالْقِلَّةِ وَالذِّلَّةِ وَأَعُوذُ بِكَ مِنْ أَنْ أَظْلِمَ أَوْ أُظْلَمَ", "source": "سنن أبي داود — صحيح", "meaning": "الاستعاذة من الفقر والظلم"},
    {"text": "رَبِّ أَعُوذُ بِكَ مِنْ هَمَزَاتِ الشَّيَاطِينِ وَأَعُوذُ بِكَ رَبِّ أَن يَحْضُرُونِ", "source": "القرآن الكريم — المؤمنون 97-98", "meaning": "الاستعاذة من وساوس الشياطين"},
    {"text": "اللَّهُمَّ أَصْلِحْ لِي دِينِي وَوَسِّعْ لِي فِي دَارِي وَبَارِكْ لِي فِيمَا رَزَقْتَنِي", "source": "المستدرك للحاكم — صحيح", "meaning": "دعاء جامع لصلاح الدين والرزق والمسكن"},
    {"text": "رَبَّنَا اكْشِفْ عَنَّا الْعَذَابَ إِنَّا مُؤْمِنُونَ", "source": "القرآن الكريم — الدخان 12", "meaning": "دعاء رفع البلاء والعذاب"},
    {"text": "رَبِّ أَدْخِلْنِي مُدْخَلَ صِدْقٍ وَأَخْرِجْنِي مُخْرَجَ صِدْقٍ وَاجْعَل لِّي مِن لَّدُنكَ سُلْطَانًا نَّصِيرًا", "source": "القرآن الكريم — الإسراء 80", "meaning": "دعاء الصدق في الأمور كلها"},
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
        elif arg.startswith("fc_"):
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
        tour_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔍 جرب بحث الآن", switch_inline_query_current_chat="إنما الأعمال بالنيات")],
            [InlineKeyboardButton("🌅 اشترك بحديث اليوم", callback_data="tour_daily"),
             InlineKeyboardButton("🕌 أذكار الصباح والمساء", callback_data="tour_adhkar")],
            [InlineKeyboardButton("✅ فهمت! ابدأ", callback_data="tour_done")],
        ])
        await update.message.reply_text(
            f"🌙 أهلاً وسهلاً، {user.first_name}!\n\n"
            "أنا *راوِي* 📜\n"
            "بوتك اليومي للأحاديث النبوية والمعرفة الإسلامية\n\n"
            "🔍 تحقق من صحة أي حديث\n"
            "📜 اقترح لي حديثاً من كتب السنة\n"
            "🎯 اختبر معلوماتك يومياً بـ 10 أسئلة\n"
            "🤲 دعاء اليوم من القرآن والسنة\n"
            "✨ اسم الله اليوم مع المعنى والفائدة\n\n"
            "استخدم الأزرار للوصول السريع 👇",
            reply_markup=tour_kb,
            parse_mode="Markdown"
        )
        await update.message.reply_text(
            "القائمة الرئيسية جاهزة 👇",
            reply_markup=main_kb(is_admin, bool(_daily), bool(_adhkar), tier=get_tier(user.id))
        )
    else:
        await update.message.reply_text(
            f"🌙 مرحباً بعودتك، {user.first_name}!\n\n"
            "أنا *راوِي* 📜\n"
            "بوتك اليومي للأحاديث النبوية والمعرفة الإسلامية\n\n"
            "🔍 تحقق من صحة أي حديث\n"
            "📜 اقترح لي حديثاً من كتب السنة\n"
            "🎯 اختبر معلوماتك يومياً بـ 10 أسئلة\n"
            "🤲 دعاء اليوم من القرآن والسنة\n"
            "✨ اسم الله اليوم مع المعنى والفائدة\n\n"
            "استخدم الأزرار للوصول السريع 👇",
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
    """عرض معلومات الإصدار"""
    msg = (
        "╔══════════════════╗\n"
        "   🕌 بوت راوِي\n"
        "   الإصدار  v5.0\n"
        "╚══════════════════╝\n\n"
        "📅 مارس 2026\n\n\n"
        "🆕 ما الجديد؟\n\n"
        "  ⚔️  تحدي الصديق\n"
        "  تحدّ من تشاء في 10 أسئلة\n"
        "  واكتشف من الأذكى منكم!\n\n"
        "  ━━━━━━━\n\n"
        "  🎯  اختبار أقوى من قبل\n"
        "  120 سؤالاً في القرآن والسيرة\n"
        "  والفقه والصحابة الكرام\n\n"
        "  ━━━━━━━\n\n"
        "  🤲  دعاء اليوم\n"
        "  50 دعاءً نبوياً وقرآنياً\n"
        "  يتجدد معك كل يوم\n\n\n"
        "✦ ✦ ✦\n\n"
        "       👨\u200d💻 @ssss_ssss_x\n"
        "  ضمّوني بين دعواتكم 💙"
    )
    await update.message.reply_text(msg)

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
    # نستخدم index الخيار عشان نتجنب مشكلة callback_data الطويل
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(opts[0], callback_data=f"quiz_0"),
         InlineKeyboardButton(opts[1], callback_data=f"quiz_1")],
        [InlineKeyboardButton(opts[2], callback_data=f"quiz_2"),
         InlineKeyboardButton(opts[3], callback_data=f"quiz_3")],
    ])
    await msg.reply_text(
        f"❓ *اختبار اليوم — سؤال {num}/5*\n"
        "━━━━━━━━━━━━━━━\n\n"
        f"📌 {q['q']}\n\n"
        f"1️⃣ {opts[0]}\n"
        f"2️⃣ {opts[1]}\n"
        f"3️⃣ {opts[2]}\n"
        f"4️⃣ {opts[3]}",
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
        [InlineKeyboardButton(opts[0], callback_data="dq_0"),
         InlineKeyboardButton(opts[1], callback_data="dq_1")],
        [InlineKeyboardButton(opts[2], callback_data="dq_2"),
         InlineKeyboardButton(opts[3], callback_data="dq_3")],
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
    await update.message.reply_text("✅ النسخة: v5.0 - 2026-03-12")

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
        two_weeks = (_dt.datetime.now(AMMAN_TZ) - timedelta(days=14)).strftime("%Y-%m-%d %H:%M:%S")
        one_week = (_dt.datetime.now(AMMAN_TZ) - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
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
            # charge_id قد يكون طويل - نخزنه في context
            refund_key = f"refund_{i}"
            if not context.user_data.get("refund_map"):
                context.user_data["refund_map"] = {}
            context.user_data["refund_map"][refund_key] = {"uid": uid, "charge_id": charge_id, "amount": amount}
            buttons.append([InlineKeyboardButton(
                f"↩️ استرداد {amount}⭐ — {name or uid}",
                callback_data=refund_key
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

    if text == "🤲 دعاء اليوم":
        await cmd_duaa(update, context)
        return

    if text == "🎯 اختبر معلوماتك":
        await cmd_quiz_new(update, context)
        return

    if text == "👤 ملفي":
        await cmd_profile(update, context)
        return

    if text == "⚔️ تحدي صديق":
        await cmd_friend_challenge(update, context)
        return

    if text == "📤 مشاركة":
        await cmd_share(update, context)
        return

    if text == "📜 اقترح لي حديثاً":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📗 البخاري", callback_data="suggest_bukhari"),
             InlineKeyboardButton("📘 مسلم", callback_data="suggest_muslim")],
            [InlineKeyboardButton("📙 أبو داود", callback_data="suggest_dawud"),
             InlineKeyboardButton("📕 الترمذي", callback_data="suggest_tirmidhi")],
            [InlineKeyboardButton("📒 ابن ماجه", callback_data="suggest_majah")],
        ])
        await update.message.reply_text(
            "📜 *اقترح لي حديثاً*\n\nاختر الكتاب 👇",
            parse_mode="Markdown",
            reply_markup=kb
        )
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
            f"ℹ️ *{BOT_NAME}* — بوت الأحاديث النبوية\n\n"
            f"📚 يحتوي على {hadiths} حديث من كتب السنة\n"
            "🎯 اختبر معلوماتك يومياً\n"
            "🤲 أدعية يومية من القرآن والسنة\n"
            "✨ أسماء الله الحسنى مع المعنى والفائدة\n"
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
    msg = f"🔍 *نتيجة البحث ({page+1}/{total})*\n"
    msg += "━━━━━━━━━━━━━━━\n\n"
    msg += f"📌 {text}\n\n"
    msg += f"👤 الراوي: {h.get('rawi') or 'غير محدد'}\n"
    if h.get('mohdith'):
        msg += f"🎓 المحدث: {h['mohdith']}\n"
    msg += f"📚 المصدر: *{source}*{sitta_badge}\n"
    msg += f"{grade_icon} الدرجة: {grade}\n"
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
    # زر فلتر الكتب الستة
    sitta_filter = context_filter == "sitta"
    keyboard.append([InlineKeyboardButton(
        "📗 الكتب الستة فقط ✓" if sitta_filter else "📗 الكتب الستة فقط",
        callback_data="filter_sitta"
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
        q_data = questions[idx_q]
        if chosen_idx < 0 or chosen_idx >= len(q_data["options"]):
            await q.answer("خطأ في الإجابة", show_alert=True)
            return
        chosen = q_data["options"][chosen_idx]
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
        total_q = len(questions)
        if next_idx >= total_q:
            # انتهى الاختبار
            context.user_data.pop("in_daily_quiz", None)
            save_quiz_session(user.id, questions, 10, score, date)
            stars = "⭐" * score + "☆" * (total_q - score)
            pct = round(score / total_q * 100)
            if pct == 100: comment = "ممتاز! أنت نجم! 🏆"
            elif pct >= 80: comment = "رائع جداً! 👏"
            elif pct >= 60: comment = "جيد! استمر 👍"
            elif pct >= 40: comment = "تحتاج مراجعة 📚"
            else: comment = "لا تستسلم، استمر في التعلم 💪"
            # ملخص الأسئلة
            summary = ""
            with sqlite3.connect("bot.db") as _conn:
                _answers = _conn.execute(
                    "SELECT question_index, is_correct FROM quiz_answers WHERE user_id=? AND quiz_date=? ORDER BY question_index",
                    (user.id, date) if date else (user.id, _dt.datetime.now(AMMAN_TZ).strftime("%Y-%m-%d"))
                ).fetchall() if False else []  # placeholder
            await q.message.reply_text(
                f"🎯 *انتهى الاختبار!*\n"
                "━━━━━━━━━━━━━━━\n\n"
                f"نتيجتك: *{score}/{total_q}* {stars}\n"
                f"💬 {comment}\n\n"
                "تعال غداً لاختبار جديد 🌙",
                parse_mode="Markdown"
            )
        else:
            # السؤال التالي
            await send_quiz_question(q.message, context, questions[next_idx], next_idx + 1)

    elif q.data.startswith("dq_"):
        await q.answer()
        today = _dt.datetime.now(AMMAN_TZ).strftime("%Y-%m-%d")
        # تحقق إذا أجاب اليوم
        with sqlite3.connect("bot.db") as _conn:
            _row = _conn.execute("SELECT correct FROM daily_question WHERE user_id=? AND date=?", (user.id, today)).fetchone()
        if _row:
            await q.answer("✅ أجبت على هذا السؤال اليوم مسبقاً!", show_alert=True)
            return
        dq = context.user_data.get("daily_q") or get_question_of_day()
        opts = dq["options"]
        answer_idx = int(q.data.split("_")[1])
        chosen = opts[answer_idx]
        correct = dq["answer"]
        is_correct = chosen == correct
        with sqlite3.connect("bot.db") as _conn:
            _conn.execute(
                "INSERT OR REPLACE INTO daily_question (user_id, date, q_index, answered, correct) VALUES (?,?,?,1,?)",
                (user.id, today, 0, 1 if is_correct else 0)
            )
        if is_correct:
            msg = f"✅ إجابة صحيحة! أحسنت 🌟\n\n📖 {dq.get('explain','')}"
        else:
            msg = f"❌ إجابة خاطئة\n\n✅ الإجابة الصحيحة: {correct}\n\n📖 {dq.get('explain','')}"
        await q.edit_message_text(
            f"❓ {dq['q']}\n\n{msg}\n\n🌙 تعال غداً لسؤال جديد!"
        )

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

    elif q.data.startswith("suggest_"):
        await q.answer()
        book_key = q.data.replace("suggest_", "")
        books = {
            "bukhari": "البخاري",
            "muslim": "مسلم",
            "dawud": "أبو داود",
            "tirmidhi": "الترمذي",
            "majah": "ابن ماجه",
        }
        book_name = books.get(book_key, "البخاري")
        hadith = await get_random_hadith(book_name)
        if hadith:
            msg = build_hadith_msg(hadith)
            kb = build_keyboard(hadith)
            await q.message.reply_text(msg, parse_mode="Markdown", reply_markup=kb)
        else:
            await q.message.reply_text(f"⚠️ لم أجد حديثاً من {book_name} الآن، حاول مرة ثانية.")

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
                # الاثنين خلّصوا — أرسل النتيجة لكليهما
                result_msg = build_fc_result(ch)
                await q.message.reply_text(result_msg, parse_mode="Markdown")
                # أرسل للطرف الآخر
                other_id = ch["opponent_id"] if role == "creator" else ch["creator_id"]
                try:
                    await context.bot.send_message(other_id, result_msg, parse_mode="Markdown")
                except Exception:
                    pass
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

    elif q.data.startswith("mood_"):
        await q.answer()
        mood = q.data.split("_")[1]
        mood_hadiths = {
            "happy": ("😊 الشكر لله", "اللَّهُمَّ أَعِنِّي عَلَى ذِكْرِكَ وَشُكْرِكَ وَحُسْنِ عِبَادَتِكَ", "سنن أبي داود — صحيح"),
            "tired": ("😔 الصبر والراحة", "عَجَبًا لِأَمْرِ الْمُؤْمِنِ إِنَّ أَمْرَهُ كُلَّهُ خَيْرٌ، وَلَيْسَ ذَاكَ لِأَحَدٍ إِلَّا لِلْمُؤْمِنِ، إِنْ أَصَابَتْهُ سَرَّاءُ شَكَرَ فَكَانَ خَيْرًا لَهُ، وَإِنْ أَصَابَتْهُ ضَرَّاءُ صَبَرَ فَكَانَ خَيْرًا لَهُ", "صحيح مسلم"),
            "angry": ("😤 كظم الغيظ", "لَيْسَ الشَّدِيدُ بِالصُّرَعَةِ، إِنَّمَا الشَّدِيدُ الَّذِي يَمْلِكُ نَفْسَهُ عِنْدَ الْغَضَبِ", "صحيح البخاري"),
        }
        title, hadith, source = mood_hadiths.get(mood, mood_hadiths["happy"])
        await q.edit_message_text(
            f"📖 *{title}*\n\n{hadith}\n\n📚 {source}",
            parse_mode="Markdown"
        )

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
                # الاثنين خلّصوا — أرسل النتيجة لكليهما
                result_msg = build_fc_result(ch)
                await q.message.reply_text(result_msg, parse_mode="Markdown")
                # أرسل للطرف الآخر
                other_id = ch["opponent_id"] if role == "creator" else ch["creator_id"]
                try:
                    await context.bot.send_message(other_id, result_msg, parse_mode="Markdown")
                except Exception:
                    pass
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

    elif q.data.startswith("mood_"):
        mood = q.data.split("_")[1]
        await q.answer()
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

def watchdog():
    """يراقب البوت ويسجل لو في مشكلة"""
    import time as _time
    import os as _os
    import subprocess as _sub
    _time.sleep(30)
    fails = 0
    while True:
        try:
            import urllib.request as _req
            _req.urlopen("http://localhost:8080", timeout=10)
            fails = 0
        except Exception as e:
            fails += 1
            logger.warning(f"⚠️ Watchdog: البوت لا يستجيب ({fails}/3) - {e}")
            if fails >= 3:
                logger.error("🔴 Watchdog: إعادة تشغيل...")
                _os.execv(__import__('sys').executable, [__import__('sys').executable] + __import__('sys').argv)
        _time.sleep(60)

def self_ping():
    """يقرع البوت نفسه كل دقيقة لمنع النوم"""
    import urllib.request as _req
    import time as _time
    _time.sleep(20)  # انتظر يشتغل البوت أولاً
    while True:
        try:
            _req.urlopen("http://localhost:8080", timeout=5)
        except:
            pass
        _time.sleep(60)  # كل دقيقة

def main():
    logger.info("🚀 بدء تشغيل بوت راوِي...")
    init_db()
    # شغّل web server في thread منفصل عشان Replit ما ينام
    from threading import Thread
    Thread(target=run_web_server, daemon=True).start()
    Thread(target=self_ping, daemon=True).start()
    Thread(target=watchdog, daemon=True).start()
    logger.info("🌐 Web server شغّال على port 8080 + self-ping كل 4 دقائق")
    app = Application.builder().token(BOT_TOKEN).build()

    # إضافة المعالجات - CommandHandlers أولاً دايماً قبل MessageHandler
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("version", version_command))
    app.add_handler(CommandHandler("asma", cmd_asma))
    app.add_handler(CommandHandler("sahaba", cmd_sahaba))
    app.add_handler(CommandHandler("random", random_hadith))
    app.add_handler(CommandHandler("donate", donate_command))
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

async def _send_fc_question(update_or_msg, context: ContextTypes.DEFAULT_TYPE):
    """أرسل سؤال تحدي الصديق"""
    questions = context.user_data.get("fc_questions", [])
    idx = context.user_data.get("fc_index", 0)
    if idx >= len(questions):
        return
    q = questions[idx]
    opts = q["options"]
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(opts[0], callback_data=f"fc_ans_0"),
         InlineKeyboardButton(opts[1], callback_data=f"fc_ans_1")],
        [InlineKeyboardButton(opts[2], callback_data=f"fc_ans_2"),
         InlineKeyboardButton(opts[3], callback_data=f"fc_ans_3")],
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
    share_text = (
        f"⚔️ تحداني {user.full_name} في بوت راوِي الإسلامي!%0A%0A"
        f"هل تقدر تتفوق عليّ؟ 10 أسئلة إسلامية 🎯%0A%0A"
        f"👇 اضغط هنا لقبول التحدي:%0A{link}"
    )
    tg_share_url = f"https://t.me/share/url?url={link}&text={share_text}"
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 شارك التحدي مع صديق", url=tg_share_url)],
        [InlineKeyboardButton("🚀 ابدأ الاختبار الآن", callback_data="fc_start")],
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


async def cmd_duaa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    d = get_duaa_of_day()
    text = (
        "🤲 *دعاء اليوم*\n"
        "━━━━━━━━━━━━━━━\n\n"
        f"*{d['text']}*\n\n"
        f"📚 المصدر: {d['source']}\n"
        f"💡 المعنى: {d['meaning']}"
    )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("📤 مشاركة", switch_inline_query=d['text'])]])
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)


async def cmd_quiz_new(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    today = _dt.datetime.now(AMMAN_TZ).strftime("%Y-%m-%d")
    with sqlite3.connect("bot.db") as _c:
        row = _c.execute("SELECT quiz_score FROM quiz_sessions WHERE user_id=? AND quiz_date=? AND quiz_index=10", (user.id, today)).fetchone()
    if row:
        await update.message.reply_text(f"✅ أكملت اختبار اليوم!\nنتيجتك: {row[0]}/10 ⭐\n\nتعال غداً لاختبار جديد 🌙")
        return
    import random as _rand
    questions = _rand.sample(DAILY_QUESTIONS, min(10, len(DAILY_QUESTIONS)))
    context.user_data["quiz_questions"] = questions
    context.user_data["quiz_index"] = 0
    context.user_data["quiz_score"] = 0
    context.user_data["quiz_date"] = today
    save_quiz_session(user.id, questions, 0, 0, today)
    await update.message.reply_text(
        "🎯 *اختبر معلوماتك*\n━━━━━━━━━━━━━━━\n\n10 أسئلة متنوعة في الفقه والتفسير والسيرة\nستظهر النتيجة الكاملة في النهاية 📊\n\nهيا نبدأ! 💪",
        parse_mode="Markdown"
    )
    await send_quiz_question(update.message, context, questions[0], 1)


async def cmd_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    stats = get_user_stats(user.id)
    streak = get_streak(user.id)
    with sqlite3.connect("bot.db") as _c:
        quiz_rows = _c.execute("SELECT quiz_score FROM quiz_sessions WHERE user_id=? AND quiz_index=10", (user.id,)).fetchall()
    total_quizzes = len(quiz_rows)
    total_score = sum(r[0] for r in quiz_rows) if quiz_rows else 0
    avg_score = round(total_score / total_quizzes, 1) if total_quizzes else 0
    badges = []
    if streak >= 7: badges.append("🔥 متواصل 7 أيام")
    if streak >= 30: badges.append("⭐ متواصل شهر")
    if total_quizzes >= 10: badges.append("🧠 متعلم نشيط")
    if total_score >= 50: badges.append("🏆 متفوق")
    badges_text = " | ".join(badges) if badges else "لا يوجد شارات بعد"
    text = (
        f"👤 *ملف {user.first_name}*\n━━━━━━━━━━━━━━━\n\n"
        f"🔥 أيام متتالية: {streak}\n"
        f"🎯 اختبارات أكملتها: {total_quizzes}\n"
        f"📊 متوسط نتيجتك: {avg_score}/10\n"
        f"🔍 بحوثك: {stats.get('searches', 0)}\n\n"
        f"🏅 شاراتك:\n{badges_text}"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def cmd_share(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("📤 مشاركة البوت", url="https://t.me/share/url?url=https://t.me/G4bGN_bot&text=بوت+راوِي+للأحاديث+النبوية+🌙")]])
    await update.message.reply_text(
        "📤 *شارك راوِي مع أصدقائك*\n\nبوت أحاديث نبوية يومية 🌙\n• اختبر معلوماتك كل يوم\n• أدعية من القرآن والسنة\n• تحقق من صحة الأحاديث",
        parse_mode="Markdown", reply_markup=kb
    )



if __name__ == "__main__":
    main()
