import os
import logging
import sqlite3
import re
import random
import urllib.parse
from datetime import datetime, date, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

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

# ==================== قاعدة البيانات ====================
def init_db():
    conn = sqlite3.connect("bot.db")
    conn.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        full_name TEXT,
        searches INTEGER DEFAULT 0,
        saved INTEGER DEFAULT 0,
        points INTEGER DEFAULT 0,
        banned INTEGER DEFAULT 0,
        joined_at TEXT DEFAULT (datetime('now'))
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS searches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        query TEXT,
        date TEXT DEFAULT (datetime('now'))
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS favourites (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        hadith_id INTEGER,
        hadith_text TEXT,
        source TEXT,
        grade TEXT,
        saved_at TEXT DEFAULT (datetime('now'))
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS ahadith (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        text TEXT UNIQUE,
        rawi TEXT,
        source TEXT,
        grade TEXT,
        topic TEXT,
        explanation TEXT
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )""")
    conn.commit()
    conn.close()
    logger.info("✅ تم إنشاء قاعدة البيانات.")

def populate_ahadith():
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM ahadith")
    if cur.fetchone()[0] > 0:
        conn.close()
        return

    ahadith_list = [
        ("إنما الأعمال بالنيات، وإنما لكل امرئ ما نوى", "عمر بن الخطاب", "صحيح البخاري (1)", "صحيح", "أحكام", "النية أساس قبول الأعمال."),
        ("بني الإسلام على خمس: شهادة أن لا إله إلا الله وأن محمداً رسول الله، وإقام الصلاة، وإيتاء الزكاة، وحج البيت، وصوم رمضان", "عبد الله بن عمر", "صحيح البخاري (8)", "صحيح", "أحكام", "أركان الإسلام الخمسة."),
        ("لا يؤمن أحدكم حتى أكون أحب إليه من ولده ووالده والناس أجمعين", "أنس بن مالك", "صحيح البخاري (15)", "صحيح", "عقيدة", "محبة النبي ﷺ من الإيمان."),
        ("المسلم من سلم المسلمون من لسانه ويده، والمهاجر من هجر ما نهى الله عنه", "عبد الله بن عمرو", "صحيح البخاري (10)", "صحيح", "أخلاق", "المسلم الحقيقي من لا يؤذي غيره."),
        ("لا يزني الزاني حين يزني وهو مؤمن، ولا يشرب الخمر حين يشرب وهو مؤمن، ولا يسرق حين يسرق وهو مؤمن", "أبو هريرة", "صحيح البخاري (2475)", "صحيح", "أحكام", "الإيمان يضعف عند المعصية."),
        ("ليس الشديد بالصرعة، إنما الشديد الذي يملك نفسه عند الغضب", "أبو هريرة", "صحيح البخاري (6114)", "صحيح", "أخلاق", "القوة في ضبط النفس."),
        ("من سلك طريقاً يلتمس فيه علماً سهل الله له به طريقاً إلى الجنة", "أبو الدرداء", "صحيح البخاري", "صحيح", "فضل العلم", "فضل طلب العلم."),
        ("أحب الأعمال إلى الله أدومها وإن قل", "عائشة", "صحيح البخاري (6465)", "صحيح", "أحكام", "الاستمرارية في العمل."),
        ("المؤمن للمؤمن كالبنيان يشد بعضه بعضا", "أبو موسى الأشعري", "صحيح البخاري (6026)", "صحيح", "أخلاق", "التكاتف بين المؤمنين."),
        ("مثل المؤمنين في توادهم وتراحمهم وتعاطفهم كمثل الجسد الواحد، إذا اشتكى منه عضو تداعى له سائر الجسد بالسهر والحمى", "النعمان بن بشير", "صحيح البخاري (6011)", "صحيح", "أخلاق", "وحدة الأمة."),
        ("من قام رمضان إيماناً واحتساباً غفر له ما تقدم من ذنبه", "أبو هريرة", "صحيح البخاري (37)", "صحيح", "أحكام", "فضل قيام رمضان."),
        ("من صام رمضان إيماناً واحتساباً غفر له ما تقدم من ذنبه", "أبو هريرة", "صحيح البخاري (38)", "صحيح", "أحكام", "فضل صيام رمضان."),
        ("ليلة القدر خير من ألف شهر", "أنس بن مالك", "صحيح البخاري (1917)", "صحيح", "فضائل", "فضل ليلة القدر."),
        ("المرء مع من أحب", "أنس بن مالك", "صحيح البخاري (6168)", "صحيح", "أخلاق", "المرء يحشر مع من أحب."),
        ("المسلم أخو المسلم لا يظلمه ولا يسلمه، ومن كان في حاجة أخيه كان الله في حاجته، ومن فرج عن مسلم كربة فرج الله عنه بها كربة من كرب يوم القيامة، ومن ستر مسلماً ستره الله يوم القيامة", "عبد الله بن عمر", "صحيح البخاري (2442)", "صحيح", "أخلاق", "حقوق المسلم."),
        ("اتقوا الظلم، فإن الظلم ظلمات يوم القيامة", "جابر بن عبد الله", "صحيح البخاري", "صحيح", "أحكام", "تحريم الظلم."),
        ("إياكم والظن، فإن الظن أكذب الحديث، ولا تحسسوا، ولا تجسسوا، ولا تنافسوا، ولا تحاسدوا، ولا تباغضوا، ولا تدابروا، وكونوا عباد الله إخواناً", "أبو هريرة", "صحيح البخاري (6064)", "صحيح", "أخلاق", "النهي عن سوء الظن."),
        ("لا تحاسدوا، ولا تناجشوا، ولا تباغضوا، ولا تدابروا، ولا يبع بعضكم على بيع بعض، وكونوا عباد الله إخواناً", "أبو هريرة", "صحيح البخاري", "صحيح", "أخلاق", "تحريم الحسد والكراهية."),
        ("الأنصار لا يحبهم إلا مؤمن، ولا يبغضهم إلا منافق، فمن أحبهم أحبه الله، ومن أبغضهم أبغضه الله", "البراء بن عازب", "صحيح البخاري (3783)", "صحيح", "فضائل", "فضل الأنصار."),
        ("من كان يؤمن بالله واليوم الآخر فليقل خيراً أو ليصمت، ومن كان يؤمن بالله واليوم الآخر فليكرم جاره، ومن كان يؤمن بالله واليوم الآخر فليكرم ضيفه", "أبو هريرة", "صحيح البخاري (6018)", "صحيح", "أخلاق", "آداب الكلام وإكرام الجار."),
        ("الدين النصيحة، قلنا: لمن؟ قال: لله، ولكتابه، ولرسوله، ولأئمة المسلمين وعامتهم", "تميم الداري", "صحيح مسلم (55)", "صحيح", "عقيدة", "النصيحة أساس الدين."),
        ("لا يؤمن أحدكم حتى يحب لأخيه ما يحب لنفسه", "أنس بن مالك", "صحيح مسلم (45)", "صحيح", "أخلاق", "الإيثار."),
        ("إن الله لا ينظر إلى صوركم وأموالكم، ولكن ينظر إلى قلوبكم وأعمالكم", "أبو هريرة", "صحيح مسلم (2564)", "صحيح", "أخلاق", "الاعتبار بالقلوب والأعمال."),
        ("إن الله كتب الإحسان على كل شيء، فإذا قتلتم فأحسنوا القتلة، وإذا ذبحتم فأحسنوا الذبحة", "شداد بن أوس", "صحيح مسلم (1955)", "صحيح", "أحكام", "الإحسان في كل شيء."),
        ("الطهور شطر الإيمان، والحمد لله تملأ الميزان، وسبحان الله والحمد لله تملآن ما بين السماوات والأرض", "أبو مالك الأشعري", "صحيح مسلم (223)", "صحيح", "أحكام", "فضل الطهارة."),
        ("الصلوات الخمس، والجمعة إلى الجمعة، ورمضان إلى رمضان، مكفرات لما بينهن إذا اجتنبت الكبائر", "أبو هريرة", "صحيح مسلم (233)", "صحيح", "أحكام", "تكفير الصلوات."),
        ("ما نقصت صدقة من مال، وما زاد الله عبداً بعفو إلا عزا، وما تواضع أحد لله إلا رفعه الله", "أبو هريرة", "صحيح مسلم (2588)", "صحيح", "أحكام", "فضل الصدقة."),
        ("المؤمن القوي خير وأحب إلى الله من المؤمن الضعيف، وفي كل خير، احرص على ما ينفعك، واستعن بالله ولا تعجز", "أبو هريرة", "صحيح مسلم (2664)", "صحيح", "عقيدة", "القوة في الإيمان."),
        ("عجباً لأمر المؤمن، إن أمره كله خير، وليس ذلك لأحد إلا للمؤمن: إن أصابته سراء شكر فكان خيراً له، وإن أصابته ضراء صبر فكان خيراً له", "صهيب بن سنان", "صحيح مسلم (2999)", "صحيح", "أخلاق", "المؤمن في كل حال خير."),
        ("ما يصيب المؤمن من وصب ولا نصب ولا سقم ولا حزن حتى الهم يهمه، إلا كفر به من خطاياه", "أبو هريرة", "صحيح مسلم (2573)", "صحيح", "أخلاق", "الابتلاء يكفر الذنوب."),
        ("الدنيا سجن المؤمن وجنة الكافر", "أبو هريرة", "صحيح مسلم (2956)", "صحيح", "أخلاق", "حقيقة الدنيا."),
        ("اللهم إني أسألك الهدى والتقى والعفاف والغنى", "عبد الله بن مسعود", "صحيح مسلم (2721)", "صحيح", "دعاء", "دعاء شامل."),
        ("اللهم إني أعوذ بك من علم لا ينفع، ومن قلب لا يخشع، ومن نفس لا تشبع، ومن دعوة لا يستجاب لها", "أنس بن مالك", "صحيح مسلم (2722)", "صحيح", "دعاء", "الاستعاذة من شرور النفس."),
        ("من سره أن يبسط له في رزقه، وينسأ له في أثره، فليصل رحمه", "أنس بن مالك", "صحيح مسلم (2557)", "صحيح", "أحكام", "فضل صلة الرحم."),
        ("ما من عبد يصلي علي صلاة إلا صلى الله عليه بها عشراً", "أبو هريرة", "صحيح مسلم (408)", "صحيح", "دعاء", "فضل الصلاة على النبي."),
        ("طعام الواحد يكفي الاثنين، وطعام الاثنين يكفي الأربعة", "أبو هريرة", "صحيح مسلم (2058)", "صحيح", "آداب", "البركة في الطعام."),
        ("المسلم يأكل في معي واحد، والكافر يأكل في سبعة أمعاء", "أبو هريرة", "صحيح مسلم (2060)", "صحيح", "آداب", "الفرق في الأكل."),
        ("من صام رمضان ثم أتبعه ستاً من شوال كان كصيام الدهر", "أبو أيوب الأنصاري", "صحيح مسلم (1164)", "صحيح", "أحكام", "صيام الست من شوال."),
        ("صوم يوم عرفة يكفر سنتين: ماضية ومستقبلة", "أبو قتادة", "صحيح مسلم (1162)", "صحيح", "أحكام", "فضل صوم عرفة."),
        ("صوم يوم عاشوراء يكفر سنة ماضية", "أبو قتادة", "صحيح مسلم (1162)", "صحيح", "أحكام", "فضل صوم عاشوراء."),
        ("ركعتا الفجر خير من الدنيا وما فيها", "عائشة", "صحيح مسلم (725)", "صحيح", "أحكام", "فضل سنة الفجر."),
        ("أفضل الصلاة بعد المكتوبة صلاة الليل", "أبو هريرة", "صحيح مسلم (1163)", "صحيح", "أحكام", "فضل قيام الليل."),
        ("صلاة الليل مثنى مثنى، فإذا خشي أحدكم الصبح صلى ركعة واحدة توتر له ما قد صلى", "ابن عمر", "صحيح مسلم (749)", "صحيح", "أحكام", "كيفية صلاة الليل."),
        ("لا يدخل الجنة من كان في قلبه مثقال ذرة من كبر", "عبد الله بن مسعود", "صحيح مسلم (91)", "صحيح", "أخلاق", "تحريم الكبر."),
        ("اللهم إني أعوذ بك من عذاب القبر، ومن عذاب النار، ومن فتنة المحيا والممات، ومن فتنة المسيح الدجال", "أبو هريرة", "صحيح مسلم (588)", "صحيح", "دعاء", "الاستعاذة من الفتن."),
        ("اللهم إني أعوذ بك من الكسل والهرم والمأثم والمغرم", "أنس بن مالك", "صحيح مسلم (2706)", "صحيح", "دعاء", "الاستعاذة من الكسل."),
        ("اللهم إني أعوذ بك من جهد البلاء، ودرك الشقاء، وسوء القضاء، وشماتة الأعداء", "أبو هريرة", "صحيح مسلم (2707)", "صحيح", "دعاء", "الاستعاذة من البلاء."),
        ("اللهم إني أعوذ بك من زوال نعمتك، وتحول عافيتك، وفجاءة نقمتك، وجميع سخطك", "عبد الله بن عمر", "صحيح مسلم (2739)", "صحيح", "دعاء", "الاستعاذة من زوال النعم."),
        ("اللهم إني أعوذ بك من العجز والكسل والجبن والبخل والهرم وعذاب القبر", "أنس بن مالك", "صحيح مسلم (2706)", "صحيح", "دعاء", "الاستعاذة من الصفات السيئة."),
        ("اللهم إني أعوذ بك من شر ما عملت، ومن شر ما لم أعمل", "أبو هريرة", "صحيح مسلم (2716)", "صحيح", "دعاء", "الاستعاذة من شر الأعمال."),
        ("الدعاء هو العبادة", "النعمان بن بشير", "سنن أبي داود (1479)", "صحيح", "عقيدة", "فضل الدعاء."),
        ("النساء شقائق الرجال", "عائشة", "سنن أبي داود (236)", "صحيح", "أحكام", "المساواة في التكاليف."),
        ("اتق الله حيثما كنت، وأتبع السيئة الحسنة تمحها، وخالق الناس بخلق حسن", "أبو ذر الغفاري", "سنن الترمذي (1987)", "حسن", "أخلاق", "التقوى ومحاسبة النفس."),
        ("الراحمون يرحمهم الرحمن، ارحموا من في الأرض يرحمكم من في السماء", "عبد الله بن عمرو", "سنن الترمذي (1924)", "صحيح", "أخلاق", "الرحمة بالخلق."),
        ("من حسن إسلام المرء تركه ما لا يعنيه", "أبو هريرة", "سنن الترمذي (2318)", "حسن", "أخلاق", "الاشتغال بما ينفع."),
        ("أكمل المؤمنين إيماناً أحسنهم خلقاً، وخياركم خياركم لنسائهم", "أبو هريرة", "سنن الترمذي (1162)", "صحيح", "أخلاق", "حسن الخلق."),
        ("إذا سألت فاسأل الله، وإذا استعنت فاستعن بالله، واعلم أن الأمة لو اجتمعت على أن ينفعوك بشيء لم ينفعوك إلا بشيء قد كتبه الله لك", "ابن عباس", "سنن الترمذي (2516)", "حسن صحيح", "عقيدة", "التوكل على الله."),
        ("طلب العلم فريضة على كل مسلم", "أنس بن مالك", "سنن النسائي", "ضعيف", "فضل العلم", "حديث ضعيف لكن مشهور."),
        ("الجنة تحت أقدام الأمهات", "أنس بن مالك", "سنن النسائي (3104)", "صحيح لغيره", "أخلاق", "بر الوالدين."),
        ("لا ضرر ولا ضرار", "أبو سعيد الخدري", "سنن ابن ماجه (2340)", "صحيح", "أحكام", "قاعدة فقهية مهمة."),
        ("إنما بعثت لأتمم صالح الأخلاق", "أبو هريرة", "مسند أحمد (8939)", "صحيح", "أخلاق", "غاية البعثة."),
        ("اتقوا النار ولو بشق تمرة، فمن لم يجد فبكلمة طيبة", "عدي بن حاتم", "صحيح البخاري ومسلم", "صحيح", "أخلاق", "الصدقة ولو قليلة."),
        ("أفضل الناس أنفعهم للناس", "جابر بن عبد الله", "الجامع الصغير", "حسن", "أخلاق", "أفضلية نفع الناس."),
    ]

    for item in ahadith_list:
        try:
            cur.execute("INSERT OR IGNORE INTO ahadith (text, rawi, source, grade, topic, explanation) VALUES (?,?,?,?,?,?)", item)
        except Exception as e:
            logger.warning(f"خطأ في إدراج حديث: {e}")
    conn.commit()
    count = cur.execute("SELECT COUNT(*) FROM ahadith").fetchone()[0]
    conn.close()
    logger.info(f"✅ تم إضافة {count} حديث إلى قاعدة البيانات.")

# ==================== دوال المساعدة ====================
def register_user(user_id, username, full_name):
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM users WHERE user_id=?", (user_id,))
    if not cur.fetchone():
        cur.execute("INSERT INTO users (user_id, username, full_name, points) VALUES (?,?,?,?)",
                    (user_id, username, full_name, 0))
        conn.commit()
        conn.close()
        return True
    else:
        cur.execute("UPDATE users SET username=? WHERE user_id=?", (username, user_id))
        conn.commit()
        conn.close()
        return False

def get_setting(key, default=None):
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute("SELECT value FROM settings WHERE key=?", (key,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else default

def set_setting(key, value):
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute("REPLACE INTO settings (key, value) VALUES (?,?)", (key, value))
    conn.commit()
    conn.close()

def is_banned(user_id):
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute("SELECT banned FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return row and row[0] == 1

def ban_user(user_id):
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute("UPDATE users SET banned=1 WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()

def unban_user(user_id):
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute("UPDATE users SET banned=0 WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()

def add_points(user_id, points):
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute("UPDATE users SET points = points + ? WHERE user_id=?", (points, user_id))
    conn.commit()
    conn.close()

def log_search(user_id, query):
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute("UPDATE users SET searches = searches + 1, points = points + 1 WHERE user_id = ?", (user_id,))
    cur.execute("INSERT INTO searches (user_id, query) VALUES (?,?)", (user_id, query[:200]))
    conn.commit()
    conn.close()

def log_save(user_id):
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute("UPDATE users SET saved = saved + 1, points = points + 2 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def get_user_stats(user_id):
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute("SELECT searches, saved, points, joined_at, username FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return row if row else (0, 0, 0, "غير معروف", "")

def get_global_stats():
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    users = cur.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    searches = cur.execute("SELECT COUNT(*) FROM searches").fetchone()[0]
    hadiths = cur.execute("SELECT COUNT(*) FROM ahadith").fetchone()[0]
    conn.close()
    return users, searches, hadiths

def get_most_searched(limit=5):
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute("SELECT query FROM searches ORDER BY date DESC LIMIT 500")
    queries = cur.fetchall()
    conn.close()
    words = {}
    for (q,) in queries:
        for w in q.split():
            w = w.strip()
            if len(w) > 2:
                words[w] = words.get(w, 0) + 1
    top = sorted(words.items(), key=lambda x: x[1], reverse=True)[:limit]
    return top

def get_most_active_users(limit=5):
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute("SELECT full_name, username, searches FROM users ORDER BY searches DESC LIMIT ?", (limit,))
    rows = cur.fetchall()
    conn.close()
    return rows

def get_monthly_users():
    month_ago = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users WHERE joined_at >= ?", (month_ago,))
    count = cur.fetchone()[0]
    conn.close()
    return count

def get_top_points(limit=5):
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute("SELECT full_name, points FROM users ORDER BY points DESC LIMIT ?", (limit,))
    rows = cur.fetchall()
    conn.close()
    return rows

def add_favourite(user_id, hadith_id, hadith_text, source, grade):
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute("INSERT INTO favourites (user_id, hadith_id, hadith_text, source, grade) VALUES (?,?,?,?,?)",
                (user_id, hadith_id, hadith_text[:500], source, grade))
    log_save(user_id)
    conn.commit()
    conn.close()

def get_favourites(user_id):
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute("SELECT id, hadith_text, source, grade, saved_at FROM favourites WHERE user_id=? ORDER BY saved_at DESC", (user_id,))
    rows = cur.fetchall()
    conn.close()
    return rows

def delete_favourite(fav_id):
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute("DELETE FROM favourites WHERE id=?", (fav_id,))
    conn.commit()
    conn.close()

def search_ahadith(query):
    words = query.split()
    if not words:
        return []
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    conditions = []
    params = []
    for w in words[:5]:
        conditions.append("text LIKE ?")
        params.append(f"%{w}%")
    sql = "SELECT id, text, rawi, source, grade, topic, explanation FROM ahadith WHERE " + " AND ".join(conditions) + " LIMIT 10"
    cur.execute(sql, params)
    results = cur.fetchall()
    conn.close()
    return results

def search_by_rawi(rawi_name):
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute("SELECT id, text, source, grade FROM ahadith WHERE rawi LIKE ? LIMIT 5", (f"%{rawi_name}%",))
    rows = cur.fetchall()
    conn.close()
    return rows

def get_hadiths_by_topic(topic, limit=5):
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute("SELECT id, text, source, grade FROM ahadith WHERE topic LIKE ? ORDER BY RANDOM() LIMIT ?", (f"%{topic}%", limit))
    rows = cur.fetchall()
    conn.close()
    return rows

def get_random_hadith():
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute("SELECT text, source, grade FROM ahadith ORDER BY RANDOM() LIMIT 1")
    row = cur.fetchone()
    conn.close()
    if row:
        return row
    return ("إنما الأعمال بالنيات", "صحيح البخاري (1)", "صحيح")

def get_daily_hadith():
    today = date.today().toordinal()
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    count = cur.execute("SELECT COUNT(*) FROM ahadith").fetchone()[0]
    if count == 0:
        conn.close()
        return get_random_hadith()
    offset = today % count
    cur.execute("SELECT text, source, grade, rawi, explanation FROM ahadith ORDER BY id LIMIT 1 OFFSET ?", (offset,))
    row = cur.fetchone()
    conn.close()
    if row:
        return row
    return get_random_hadith()

def get_recent_users(limit=10):
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute("SELECT user_id, full_name, username, joined_at FROM users ORDER BY joined_at DESC LIMIT ?", (limit,))
    rows = cur.fetchall()
    conn.close()
    return rows

# ==================== لوحة المفاتيح ====================
def main_kb(is_admin=False):
    keys = [
        [KeyboardButton("🔍 تحقق من حديث"), KeyboardButton("📚 كتب الحديث")],
        [KeyboardButton("📊 إحصائياتي"), KeyboardButton("⭐ المفضلة")],
        [KeyboardButton("📅 حديث اليوم"), KeyboardButton("📂 تصنيفات")],
        [KeyboardButton("🏆 لوحة الشرف"), KeyboardButton("ℹ️ عن البوت")],
    ]
    if is_admin:
        keys.append([KeyboardButton("⚙️ لوحة التحكم")])
    return ReplyKeyboardMarkup(keys, resize_keyboard=True)

def topics_keyboard():
    topics = [
        ["🕌 عقيدة", "⚖️ أحكام"],
        ["💞 أخلاق", "📖 فضائل"],
        ["🤲 أدعية", "📚 فضل العلم"],
        ["🍽️ آداب", "🔙 رجوع"],
    ]
    return ReplyKeyboardMarkup(topics, resize_keyboard=True)

def admin_main_keyboard():
    keys = [
        [KeyboardButton("📊 إحصائيات متقدمة"), KeyboardButton("📢 إشعار للجميع")],
        [KeyboardButton("📈 عدد المستخدمين"), KeyboardButton("📊 المستخدمين الشهري")],
        [KeyboardButton("🚫 حظر/إلغاء حظر"), KeyboardButton("🛠 وضع الصيانة")],
        [KeyboardButton("👥 آخر المستخدمين"), KeyboardButton("🔙 رجوع")],
    ]
    return ReplyKeyboardMarkup(keys, resize_keyboard=True)

# ==================== المعالجات ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if get_setting("maintenance", "off") == "on" and update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("⚠️ البوت تحت الصيانة حالياً.")
        return

    user = update.effective_user
    is_new = register_user(user.id, user.username or "", user.full_name)
    is_admin = user.id in ADMIN_IDS
    total_users, _, total_hadiths = get_global_stats()
    await update.message.reply_text(
        f"🕌 {'اهلاً وسهلاً' if is_new else 'مرحباً بعودتك'}، {user.first_name}!\n\n"
        f"أنا **{BOT_NAME}**، بوت التحقق من الأحاديث النبوية.\n\n"
        "✅ أرسل لي أي حديث وسأبحث عنه.\n"
        f"📚 قاعدة البيانات تحتوي على {total_hadiths} حديث.\n"
        "استخدم الأزرار للوصول السريع.",
        reply_markup=main_kb(is_admin)
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"🆘 مساعدة بوت {BOT_NAME}:\n\n"
        "• أرسل أي حديث وسأبحث عنه.\n"
        "• يمكنك البحث باسم الراوي (مثلاً: أبو هريرة).\n"
        "• الأوامر:\n"
        "/random - حديث عشوائي\n"
        "/save - حفظ الحديث المعروض\n"
        "/fav - عرض المفضلة\n"
        "/stats - إحصائياتك\n"
        "/daily - حديث اليوم\n"
        "/leaderboard - لوحة الشرف"
    )

async def random_hadith(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_banned(update.effective_user.id) and update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("🚫 أنت محظور.")
        return
    text, src, grade = get_random_hadith()
    await update.message.reply_text(f"🎲 **حديث عشوائي:**\n\n{text}\n\n📚 {src}\n⚖️ {grade}")

async def daily_hadith(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_banned(update.effective_user.id) and update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("🚫 أنت محظور.")
        return
    result = get_daily_hadith()
    if len(result) == 5:
        text, src, grade, rawi, exp = result
        msg = f"📅 **حديث اليوم:**\n\n{text}\n\n👤 **الراوي:** {rawi}\n📚 {src}\n⚖️ {grade}"
        if exp:
            msg += f"\n📝 {exp}"
    else:
        text, src, grade = result
        msg = f"📅 **حديث اليوم:**\n\n{text}\n\n📚 {src}\n⚖️ {grade}"
    await update.message.reply_text(msg)

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_banned(update.effective_user.id) and update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("🚫 أنت محظور.")
        return
    user = update.effective_user
    s, sv, pts, j, uname = get_user_stats(user.id)
    total_users, total_searches, _ = get_global_stats()
    await update.message.reply_text(
        f"📊 إحصائياتك:\n"
        f"👤 {user.full_name}\n"
        f"🆔 @{uname if uname else 'لا يوجد'}\n"
        f"🔍 بحث: {s}\n"
        f"⭐ مفضلة: {sv}\n"
        f"🏅 نقاط: {pts}\n"
        f"📅 من: {j}\n\n"
        f"🌍 عام:\n"
        f"👥 المستخدمون: {total_users}\n"
        f"🔎 البحوث: {total_searches}"
    )

async def leaderboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    top_points = get_top_points()
    msg = "🏆 **لوحة الشرف (النقاط):**\n\n"
    for i, (name, pts) in enumerate(top_points, 1):
        msg += f"{i}. {name} – {pts} نقطة\n"
    await update.message.reply_text(msg)

async def fav_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_banned(update.effective_user.id) and update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("🚫 أنت محظور.")
        return
    favs = get_favourites(update.effective_user.id)
    if not favs:
        await update.message.reply_text("📭 لا توجد أحاديث في المفضلة.")
        return
    msg = "⭐ **مفضلتك:**\n\n"
    keyboard = []
    for i, (fid, text, src, grade, _) in enumerate(favs[:5], 1):
        short = text[:50] + "..."
        msg += f"{i}. {short}\n   📚 {src} | {grade}\n➖➖➖\n"
        keyboard.append([InlineKeyboardButton(f"❌ حذف {i}", callback_data=f"del_{fid}")])
    keyboard.append([InlineKeyboardButton("🔁 تحديث", callback_data="refresh_fav")])
    await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(keyboard))

async def save_hadith(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_banned(update.effective_user.id) and update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("🚫 أنت محظور.")
        return
    last = context.user_data.get("last_hadith")
    if not last:
        await update.message.reply_text("⚠️ لا يوجد حديث لحفظه.")
        return
    hid, text, src, grade = last
    add_favourite(update.effective_user.id, hid, text, src, grade)
    await update.message.reply_text("✅ تم حفظ الحديث (+2 نقطة).")

async def topics_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_banned(update.effective_user.id) and update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("🚫 أنت محظور.")
        return
    await update.message.reply_text("📂 اختر التصنيف:", reply_markup=topics_keyboard())

async def handle_topics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    topic_map = {
        "🕌 عقيدة": "عقيدة",
        "⚖️ أحكام": "أحكام",
        "💞 أخلاق": "أخلاق",
        "📖 فضائل": "فضائل",
        "🤲 أدعية": "دعاء",
        "📚 فضل العلم": "فضل العلم",
        "🍽️ آداب": "آداب",
    }
    if text in topic_map:
        topic = topic_map[text]
        results = get_hadiths_by_topic(topic)
        if results:
            msg = f"📂 **أحاديث في {text}:**\n\n"
            for i, (hid, htext, src, grade) in enumerate(results, 1):
                msg += f"🔹 **الحديث {i}**\n{htext[:100]}...\n📚 {src}\n⚖️ {grade}\n➖➖➖\n"
            await update.message.reply_text(msg)
        else:
            await update.message.reply_text("⚠️ لا توجد أحاديث في هذا التصنيف حالياً.")
    elif text == "🔙 رجوع":
        is_admin = update.effective_user.id in ADMIN_IDS
        await update.message.reply_text("تم العودة", reply_markup=main_kb(is_admin))

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    await update.message.reply_text("⚙️ لوحة تحكم المشرف", reply_markup=admin_main_keyboard())

async def handle_admin_actions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id not in ADMIN_IDS:
        return
    text = update.message.text

    if text == "📊 إحصائيات متقدمة":
        total_users, total_searches, total_hadiths = get_global_stats()
        most_searched = get_most_searched()
        most_active = get_most_active_users()
        msg = "📊 **إحصائيات متقدمة**\n\n"
        msg += f"👥 إجمالي المستخدمين: {total_users}\n"
        msg += f"🔎 إجمالي البحوث: {total_searches}\n"
        msg += f"📚 عدد الأحاديث: {total_hadiths}\n\n"
        msg += "🔥 **أكثر الكلمات بحثاً:**\n"
        for word, count in most_searched:
            msg += f"• {word}: {count} مرة\n"
        msg += "\n🏆 **أكثر المستخدمين نشاطاً:**\n"
        for name, uname, s in most_active:
            msg += f"• {name} (@{uname}): {s} بحث\n" if uname else f"• {name}: {s} بحث\n"
        await update.message.reply_text(msg)

    elif text == "📢 إشعار للجميع":
        context.user_data["broadcast"] = True
        await update.message.reply_text("أرسل الرسالة:")

    elif text == "📈 عدد المستخدمين":
        total, _, _ = get_global_stats()
        await update.message.reply_text(f"👥 إجمالي المستخدمين: {total}")

    elif text == "📊 المستخدمين الشهري":
        monthly = get_monthly_users()
        total, _, _ = get_global_stats()
        await update.message.reply_text(f"📊 شهرياً: {monthly}\n👥 الإجمالي: {total}")

    elif text == "🚫 حظر/إلغاء حظر":
        context.user_data["ban_action"] = True
        await update.message.reply_text("أرسل ID المستخدم ثم كلمة 'حظر' أو 'الغاء حظر' في سطر جديد:\nمثال:\n123456789\nحظر")

    elif text == "🛠 وضع الصيانة":
        current = get_setting("maintenance", "off")
        new = "on" if current == "off" else "off"
        set_setting("maintenance", new)
        status = "مفعل" if new == "on" else "معطل"
        await update.message.reply_text(f"🛠 وضع الصيانة: {status}")

    elif text == "👥 آخر المستخدمين":
        recent = get_recent_users(10)
        msg = "👥 **آخر 10 مستخدمين:**\n\n"
        for uid, name, uname, joined in recent:
            msg += f"• {name} (@{uname}) - {joined}\n" if uname else f"• {name} - {joined}\n"
        await update.message.reply_text(msg)

    elif text == "🔙 رجوع":
        is_admin = user.id in ADMIN_IDS
        await update.message.reply_text("تم العودة", reply_markup=main_kb(is_admin))

async def handle_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("broadcast"):
        text = update.message.text
        conn = sqlite3.connect("bot.db")
        users = conn.execute("SELECT user_id FROM users").fetchall()
        conn.close()
        success = fail = 0
        for (uid,) in users:
            try:
                await context.bot.send_message(uid, f"📢 إشعار من الإدارة:\n{text}")
                success += 1
                await asyncio.sleep(0.05)
            except:
                fail += 1
        await update.message.reply_text(f"✅ تم: {success} نجح، {fail} فشل")
        context.user_data["broadcast"] = False
        return True
    return False

async def handle_ban_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("ban_action"):
        lines = update.message.text.strip().split('\n', 1)
        if len(lines) == 2:
            try:
                uid = int(lines[0].strip())
                action = lines[1].strip()
                if action == "حظر":
                    ban_user(uid)
                    await update.message.reply_text(f"🚫 تم حظر {uid}.")
                elif action == "الغاء حظر":
                    unban_user(uid)
                    await update.message.reply_text(f"✅ تم إلغاء حظر {uid}.")
                else:
                    await update.message.reply_text("⚠️ إجراء غير معروف.")
            except:
                await update.message.reply_text("❌ خطأ في الإدخال.")
        else:
            await update.message.reply_text("⚠️ صيغة غير صحيحة.")
        context.user_data["ban_action"] = False
        return True
    return False

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text.strip()

    # تحقق من الحظر والصيانة
    if is_banned(user.id) and user.id not in ADMIN_IDS:
        await update.message.reply_text("🚫 أنت محظور.")
        return
    if get_setting("maintenance", "off") == "on" and user.id not in ADMIN_IDS:
        await update.message.reply_text("⚠️ تحت الصيانة.")
        return

    # تسجيل المستخدم
    register_user(user.id, user.username or "", user.full_name)

    # معالجة إجراءات الأدمن أولاً
    if user.id in ADMIN_IDS:
        if await handle_broadcast(update, context):
            return
        if await handle_ban_action(update, context):
            return

    # الأزرار الرئيسية
    if text == "📚 كتب الحديث":
        await update.message.reply_text("📚 الكتب الستة: البخاري، مسلم، أبو داود، الترمذي، النسائي، ابن ماجه")
        return
    if text == "📊 إحصائياتي":
        await stats_command(update, context)
        return
    if text == "⭐ المفضلة":
        await fav_command(update, context)
        return
    if text == "📅 حديث اليوم":
        await daily_hadith(update, context)
        return
    if text == "📂 تصنيفات":
        await topics_menu(update, context)
        return
    if text == "🏆 لوحة الشرف":
        await leaderboard_command(update, context)
        return
    if text == "ℹ️ عن البوت":
        total_users, _, total_hadiths = get_global_stats()
        await update.message.reply_text(
            f"ℹ️ **{BOT_NAME}** - بوت أحاديث.\n📚 يحتوي على {total_hadiths} حديث.\n/help للمساعدة."
        )
        return
    if text == "🔍 تحقق من حديث":
        await update.message.reply_text("✍️ أرسل نص الحديث أو اسم الراوي:")
        return
    if text == "⚙️ لوحة التحكم" and user.id in ADMIN_IDS:
        await admin_panel(update, context)
        return

    # أوامر الأدمن
    if user.id in ADMIN_IDS and text in ["📊 إحصائيات متقدمة", "📢 إشعار للجميع", "📈 عدد المستخدمين", "📊 المستخدمين الشهري", "🚫 حظر/إلغاء حظر", "🛠 وضع الصيانة", "👥 آخر المستخدمين", "🔙 رجوع"]:
        await handle_admin_actions(update, context)
        return

    # معالجة التصنيفات
    if text in ["🕌 عقيدة", "⚖️ أحكام", "💞 أخلاق", "📖 فضائل", "🤲 أدعية", "📚 فضل العلم", "🍽️ آداب", "🔙 رجوع"]:
        await handle_topics(update, context)
        return

    # البحث عن حديث
    if len(text) < 10:
        await update.message.reply_text("⚠️ أرسل نصاً أطول (10 أحرف على الأقل).")
        return

    wait = await update.message.reply_text("⏳ جاري البحث...")
    try:
        results = search_ahadith(text)
        if not results:
            results = search_by_rawi(text)
        if results:
            log_search(user.id, text)
            context.user_data["search_results"] = results
            context.user_data["search_page"] = 0
            await show_search_page(update, context, wait)
        else:
            url = f"https://dorar.net/hadith/search?q={urllib.parse.quote(text)}"
            kb = [[InlineKeyboardButton("🔍 ابحث في الدرر السنية", url=url)]]
            await wait.edit_text("⚠️ لم أجد الحديث.", reply_markup=InlineKeyboardMarkup(kb))
    except Exception as e:
        logger.error(e)
        await wait.edit_text("⚠️ حدث خطأ.")

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

    row = results[page]
    if len(row) == 7:
        hid, htext, rawi, src, grade, topic, exp = row
        msg = f"🔍 **نتيجة البحث ({page+1}/{total_pages}):**\n\n"
        msg += f"📌 {htext}\n\n"
        msg += f"👤 **الراوي:** {rawi}\n"
        msg += f"📚 {src}\n"
        msg += f"⚖️ **الدرجة:** {grade}"
        if exp:
            msg += f"\n📝 {exp}"
    else:
        hid, htext, src, grade = row
        msg = f"🔍 **نتيجة البحث ({page+1}/{total_pages}):**\n\n"
        msg += f"📌 {htext}\n\n"
        msg += f"📚 {src}\n"
        msg += f"⚖️ **الدرجة:** {grade}"

    context.user_data["last_hadith"] = (hid, htext, src, grade)

    keyboard = []
    if total_pages > 1:
        nav_row = []
        if page > 0:
            nav_row.append(InlineKeyboardButton("⬅️ السابق", callback_data="nav_prev"))
        nav_row.append(InlineKeyboardButton(f"{page+1}/{total_pages}", callback_data="noop"))
        if page < total_pages - 1:
            nav_row.append(InlineKeyboardButton("التالي ➡️", callback_data="nav_next"))
        keyboard.append(nav_row)

    action_row = [
        InlineKeyboardButton("⭐ حفظ", callback_data="save"),
        InlineKeyboardButton("🔄 جديد", callback_data="new")
    ]
    keyboard.append(action_row)

    await wait_message.delete()
    await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if q.data == "new":
        await q.message.reply_text("✍️ أرسل الحديث الجديد!")
        await q.message.delete()
    elif q.data == "save":
        last = context.user_data.get("last_hadith")
        if last:
            hid, text, src, grade = last
            add_favourite(q.from_user.id, hid, text, src, grade)
            await q.edit_message_text("✅ تم الحفظ (+2 نقطة).")
        else:
            await q.edit_message_text("⚠️ لا يوجد حديث.")
    elif q.data == "nav_prev":
        page = context.user_data.get("search_page", 0)
        if page > 0:
            context.user_data["search_page"] = page - 1
            await q.message.delete()
            await show_search_page_from_callback(update, context)
        else:
            await q.answer("أنت في الصفحة الأولى", show_alert=True)
    elif q.data == "nav_next":
        results = context.user_data.get("search_results", [])
        page = context.user_data.get("search_page", 0)
        if page < len(results) - 1:
            context.user_data["search_page"] = page + 1
            await q.message.delete()
            await show_search_page_from_callback(update, context)
        else:
            await q.answer("أنت في الصفحة الأخيرة", show_alert=True)
    elif q.data.startswith("del_"):
        fav_id = int(q.data.split("_")[1])
        delete_favourite(fav_id)
        await q.edit_message_text("✅ تم الحذف.")
    elif q.data == "refresh_fav":
        await fav_command(update, context)
    elif q.data == "noop":
        pass

async def show_search_page_from_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    results = context.user_data.get("search_results", [])
    page = context.user_data.get("search_page", 0)
    if not results:
        await update.callback_query.message.reply_text("⚠️ لا توجد نتائج.")
        return

    total_pages = len(results)
    if page >= total_pages:
        page = total_pages - 1
        context.user_data["search_page"] = page

    row = results[page]
    if len(row) == 7:
        hid, htext, rawi, src, grade, topic, exp = row
        msg = f"🔍 **نتيجة البحث ({page+1}/{total_pages}):**\n\n"
        msg += f"📌 {htext}\n\n"
        msg += f"👤 **الراوي:** {rawi}\n"
        msg += f"📚 {src}\n"
        msg += f"⚖️ **الدرجة:** {grade}"
        if exp:
            msg += f"\n📝 {exp}"
    else:
        hid, htext, src, grade = row
        msg = f"🔍 **نتيجة البحث ({page+1}/{total_pages}):**\n\n"
        msg += f"📌 {htext}\n\n"
        msg += f"📚 {src}\n"
        msg += f"⚖️ **الدرجة:** {grade}"

    context.user_data["last_hadith"] = (hid, htext, src, grade)

    keyboard = []
    if total_pages > 1:
        nav_row = []
        if page > 0:
            nav_row.append(InlineKeyboardButton("⬅️ السابق", callback_data="nav_prev"))
        nav_row.append(InlineKeyboardButton(f"{page+1}/{total_pages}", callback_data="noop"))
        if page < total_pages - 1:
            nav_row.append(InlineKeyboardButton("التالي ➡️", callback_data="nav_next"))
        keyboard.append(nav_row)

    action_row = [
        InlineKeyboardButton("⭐ حفظ", callback_data="save"),
        InlineKeyboardButton("🔄 جديد", callback_data="new")
    ]
    keyboard.append(action_row)

    await update.callback_query.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(keyboard))

# ==================== التشغيل ====================
def main():
    logger.info("🚀 بدء تشغيل بوت راوِي...")
    init_db()
    populate_ahadith()
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("random", random_hadith))
    app.add_handler(CommandHandler("daily", daily_hadith))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("leaderboard", leaderboard_command))
    app.add_handler(CommandHandler("fav", fav_command))
    app.add_handler(CommandHandler("save", save_hadith))
    app.add_handler(CommandHandler("topics", topics_menu))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(handle_callback))

    logger.info("✅ البوت جاهز بجميع الميزات!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()