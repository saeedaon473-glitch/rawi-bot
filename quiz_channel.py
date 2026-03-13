"""
quiz_channel.py — مسابقة جماعية في القناة/المجموعة
الإصدار: v1.0
المطور: @ssss_ssss_x

كيف تستخدمه:
1. أضف البوت كمشرف في القناة أو المجموعة
2. اكتب /quiz في القناة لبدء مسابقة
3. اضغط "انضمام" لتسجيل المشاركين
4. اضغط "بدء المسابقة" لبدء الأسئلة
5. كل من يجاوب صح يأخذ نقطة
6. في النهاية تظهر لوحة المتصدرين
"""

import os
import asyncio
import logging
import sqlite3
import random
import datetime

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# ─── إعداد ───────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_IDS = list(map(int, os.environ.get("ADMIN_IDS", "0").split(",")))

DB_PATH = "quiz_channel.db"

# ─── قاعدة البيانات ───────────────────────────────────
def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS quiz_sessions (
                session_id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                status TEXT DEFAULT 'waiting',
                current_q INTEGER DEFAULT 0,
                total_q INTEGER DEFAULT 10,
                started_at TEXT,
                created_by INTEGER
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS quiz_participants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER,
                user_id INTEGER,
                username TEXT,
                full_name TEXT,
                score INTEGER DEFAULT 0,
                joined_at TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS quiz_answers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER,
                question_index INTEGER,
                user_id INTEGER,
                answer TEXT,
                is_correct INTEGER DEFAULT 0,
                answered_at TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS quiz_questions_cache (
                session_id INTEGER PRIMARY KEY,
                questions_json TEXT
            )
        """)
        conn.commit()


import json as _json

def save_session_questions(session_id: int, questions: list):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO quiz_questions_cache (session_id, questions_json) VALUES (?,?)",
            (session_id, _json.dumps(questions, ensure_ascii=False))
        )

def load_session_questions(session_id: int) -> list:
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT questions_json FROM quiz_questions_cache WHERE session_id=?",
            (session_id,)
        ).fetchone()
    if row:
        return _json.loads(row[0])
    return []


def get_active_session(chat_id: int) -> dict | None:
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT session_id, status, current_q, total_q, created_by FROM quiz_sessions WHERE chat_id=? AND status != 'finished' ORDER BY session_id DESC LIMIT 1",
            (chat_id,)
        ).fetchone()
    if row:
        return {"session_id": row[0], "status": row[1], "current_q": row[2], "total_q": row[3], "created_by": row[4]}
    return None


def create_session(chat_id: int, user_id: int, total_q: int = 10) -> int:
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute(
            "INSERT INTO quiz_sessions (chat_id, status, current_q, total_q, started_at, created_by) VALUES (?,?,?,?,?,?)",
            (chat_id, "waiting", 0, total_q, datetime.datetime.now().isoformat(), user_id)
        )
        return cur.lastrowid


def join_session(session_id: int, user_id: int, username: str, full_name: str) -> bool:
    with sqlite3.connect(DB_PATH) as conn:
        exists = conn.execute(
            "SELECT id FROM quiz_participants WHERE session_id=? AND user_id=?",
            (session_id, user_id)
        ).fetchone()
        if exists:
            return False
        conn.execute(
            "INSERT INTO quiz_participants (session_id, user_id, username, full_name, score, joined_at) VALUES (?,?,?,?,0,?)",
            (session_id, user_id, username or "", full_name or "مجهول", datetime.datetime.now().isoformat())
        )
        return True


def get_participants(session_id: int) -> list:
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT user_id, full_name, score FROM quiz_participants WHERE session_id=? ORDER BY score DESC",
            (session_id,)
        ).fetchall()
    return [{"user_id": r[0], "full_name": r[1], "score": r[2]} for r in rows]


def has_answered(session_id: int, question_index: int, user_id: int) -> bool:
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT id FROM quiz_answers WHERE session_id=? AND question_index=? AND user_id=?",
            (session_id, question_index, user_id)
        ).fetchone()
    return row is not None


def record_answer(session_id: int, question_index: int, user_id: int, answer: str, is_correct: bool):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO quiz_answers (session_id, question_index, user_id, answer, is_correct, answered_at) VALUES (?,?,?,?,?,?)",
            (session_id, question_index, user_id, answer, 1 if is_correct else 0, datetime.datetime.now().isoformat())
        )
        if is_correct:
            conn.execute(
                "UPDATE quiz_participants SET score = score + 1 WHERE session_id=? AND user_id=?",
                (session_id, user_id)
            )


def update_session_status(session_id: int, status: str, current_q: int = None):
    with sqlite3.connect(DB_PATH) as conn:
        if current_q is not None:
            conn.execute(
                "UPDATE quiz_sessions SET status=?, current_q=? WHERE session_id=?",
                (status, current_q, session_id)
            )
        else:
            conn.execute(
                "UPDATE quiz_sessions SET status=? WHERE session_id=?",
                (status, session_id)
            )


def finish_session(session_id: int):
    update_session_status(session_id, "finished")


# ─── الأسئلة ──────────────────────────────────────────
QUESTIONS = [
    {"q": 'كم عدد أركان الإسلام؟', "options": ['3', '4', '5', '6'], "answer": '5', "explain": 'الشهادتان، الصلاة، الزكاة، الصوم، الحج'},
    {"q": 'ما هي أطول سورة في القرآن؟', "options": ['آل عمران', 'البقرة', 'النساء', 'المائدة'], "answer": 'البقرة', "explain": 'سورة البقرة هي أطول سورة في القرآن الكريم'},
    {"q": 'كم عدد أنبياء الله المذكورين في القرآن؟', "options": ['20', '35', '30', '25'], "answer": '25', "explain": 'ذُكر 25 نبياً بالاسم في القرآن الكريم'},
    {"q": 'ما هو اسم والد النبي إبراهيم عليه السلام؟', "options": ['آزر', 'عمران', 'يشكر', 'تارح'], "answer": 'آزر', "explain": 'ذكر القرآن اسم والد إبراهيم آزر'},
    {"q": 'في أي شهر نزل القرآن الكريم؟', "options": ['رجب', 'شعبان', 'محرم', 'رمضان'], "answer": 'رمضان', "explain": 'قال تعالى: شهر رمضان الذي أنزل فيه القرآن'},
    {"q": 'كم عدد سور القرآن الكريم؟', "options": ['110', '112', '114', '116'], "answer": '114', "explain": 'يتكون القرآن الكريم من 114 سورة'},
    {"q": 'ما هي السورة التي تعدل ثلث القرآن؟', "options": ['الإخلاص', 'الفاتحة', 'الكوثر', 'الفلق'], "answer": 'الإخلاص', "explain": 'قال النبي ﷺ إن سورة الإخلاص تعدل ثلث القرآن'},
    {"q": 'كم عدد أركان الإيمان؟', "options": ['4', '6', '5', '7'], "answer": '6', "explain": 'الإيمان بالله وملائكته وكتبه ورسله واليوم الآخر والقدر'},
    {"q": 'ما هو أول مسجد بُني في الإسلام؟', "options": ['المسجد الحرام', 'مسجد قباء', 'مسجد النبي', 'المسجد الأقصى'], "answer": 'مسجد قباء', "explain": 'مسجد قباء هو أول مسجد بُني في الإسلام عند هجرة النبي ﷺ'},
    {"q": 'كم سنة استغرق نزول القرآن الكريم؟', "options": ['20 سنة', '30 سنة', '25 سنة', '23 سنة'], "answer": '23 سنة', "explain": 'نزل القرآن الكريم على مدى 23 سنة'},
    {"q": 'ما هو اسم جبل النور الذي نزل فيه الوحي؟', "options": ['جبل عرفات', 'جبل ثور', 'جبل حراء', 'جبل أبي قبيس'], "answer": 'جبل حراء', "explain": 'في غار حراء بجبل النور نزل أول وحي على النبي ﷺ'},
    {"q": 'ما هي أول آية نزلت من القرآن؟', "options": ['اقرأ باسم ربك', 'الحمد لله', 'بسم الله', 'يا أيها المدثر'], "answer": 'اقرأ باسم ربك', "explain": 'أول ما نزل: اقرأ باسم ربك الذي خلق'},
    {"q": 'كم سنة بقي أصحاب الكهف في نومهم؟', "options": ['100 سنة', '309 سنوات', '200 سنة', '400 سنة'], "answer": '309 سنوات', "explain": 'قال تعالى: ولبثوا في كهفهم ثلاث مئة سنين وازدادوا تسعاً'},
    {"q": 'ما هي السورة الوحيدة التي ليس فيها بسملة في أولها؟', "options": ['الفيل', 'الإخلاص', 'التوبة', 'المعوذتان'], "answer": 'التوبة', "explain": 'سورة التوبة لم يُكتب في أولها بسملة'},
    {"q": 'ما هي السورة التي تُسمى عروس القرآن؟', "options": ['الرحمن', 'يس', 'الواقعة', 'الكهف'], "answer": 'الرحمن', "explain": 'سورة الرحمن تُسمى عروس القرآن'},
    {"q": 'من هو النبي الذي ابتلعه الحوت؟', "options": ['إلياس', 'إدريس', 'أيوب', 'يونس'], "answer": 'يونس', "explain": 'يونس عليه السلام ذو النون التقمه الحوت'},
    {"q": 'ما هي مدة نوح عليه السلام في قومه؟', "options": ['300 سنة', '950 سنة', '500 سنة', '1000 سنة'], "answer": '950 سنة', "explain": 'قال تعالى: فلبث فيهم ألف سنة إلا خمسين عاماً'},
    {"q": 'ما هي السورة التي تحتوي على آية الكرسي؟', "options": ['آل عمران', 'النساء', 'البقرة', 'المائدة'], "answer": 'البقرة', "explain": 'آية الكرسي هي الآية 255 من سورة البقرة'},
    {"q": 'أي نبي سكن في مصر وأصبح عزيزها؟', "options": ['موسى', 'إسحاق', 'إبراهيم', 'يوسف'], "answer": 'يوسف', "explain": 'يوسف عليه السلام أصبح عزيز مصر'},
    {"q": 'من هو أول من جمع القرآن في مصحف واحد؟', "options": ['أبو بكر الصديق', 'عمر بن الخطاب', 'زيد بن ثابت', 'علي بن أبي طالب'], "answer": 'أبو بكر الصديق', "explain": 'أبو بكر أمر بجمع القرآن في مصحف واحد'},
    {"q": 'كم ركعة تُصلى صلاة العيد؟', "options": ['أربع ركعات', 'ركعتان', 'ثلاث ركعات', 'ست ركعات'], "answer": 'ركعتان', "explain": 'صلاة العيد ركعتان مع تكبيرات زائدة'},
    {"q": 'ما هي الصلاة الوسطى المذكورة في القرآن؟', "options": ['الفجر', 'الظهر', 'المغرب', 'العصر'], "answer": 'العصر', "explain": 'قال تعالى: حافظوا على الصلوات والصلاة الوسطى — وهي العصر'},
    {"q": 'كم حجة حجّها النبي ﷺ؟', "options": ['ثلاث حجج', 'حجتان', 'حجة واحدة', 'لم يحج'], "answer": 'حجة واحدة', "explain": 'حجّ النبي ﷺ حجة واحدة وهي حجة الوداع عام 10هـ'},
    {"q": 'من هو الصحابي الملقب بـ أمين الأمة؟', "options": ['أبو عبيدة', 'عمر', 'أبو بكر', 'علي'], "answer": 'أبو عبيدة', "explain": 'لقّب النبي ﷺ أبا عبيدة بن الجراح بأمين هذه الأمة'},
    {"q": 'ما هو الفرق بين الزكاة والصدقة؟', "options": ['لا فرق', 'الصدقة واجبة والزكاة تطوع', 'الزكاة واجبة والصدقة تطوع', 'الزكاة للفقراء فقط'], "answer": 'الزكاة واجبة والصدقة تطوع', "explain": 'الزكاة ركن من أركان الإسلام واجبة، والصدقة تطوع مستحب'},
    {"q": 'ما هو أول ما خلق الله؟', "options": ['الماء', 'القلم', 'العرش', 'النور'], "answer": 'القلم', "explain": 'قال النبي ﷺ: أول ما خلق الله القلم فقال له اكتب'},
    {"q": 'ما هي آخر آية نزلت من القرآن؟', "options": ['واتقوا يوماً ترجعون', 'اليوم أكملت لكم دينكم', 'إذا جاء نصر الله', 'قل أعوذ برب الناس'], "answer": 'واتقوا يوماً ترجعون', "explain": 'قيل إن آخر آية نزلت: واتقوا يوماً ترجعون فيه إلى الله'},
    {"q": 'ما هي اسم زوجة فرعون المؤمنة؟', "options": ['هاجر', 'بلقيس', 'مريم', 'آسية'], "answer": 'آسية', "explain": 'آسية بنت مزاحم زوجة فرعون آمنت بالله'},
    {"q": 'من هو النبي الذي كان نجاراً؟', "options": ['داود', 'زكريا', 'سليمان', 'يوسف'], "answer": 'زكريا', "explain": 'كان زكريا عليه السلام نجاراً يعمل بيده'},
    {"q": 'ما هي الآية الأطول في القرآن؟', "options": ['آية الكرسي', 'أول البقرة', 'آية النكاح', 'آية الدَّين'], "answer": 'آية الدَّين', "explain": 'آية الدَّين (البقرة 282) هي الأطول في القرآن'},
    {"q": 'في أي عام وُلد النبي محمد ﷺ؟', "options": ['570م', '568م', '572م', '575م'], "answer": '570م', "explain": 'وُلد النبي ﷺ عام الفيل الموافق 570م'},
    {"q": 'كم عمر النبي ﷺ حين تُوفّي؟', "options": ['60 سنة', '61 سنة', '63 سنة', '65 سنة'], "answer": '63 سنة', "explain": 'تُوفّي النبي ﷺ وعمره 63 سنة'},
    {"q": 'ما هو اسم أم النبي ﷺ؟', "options": ['آمنة بنت وهب', 'فاطمة بنت أسد', 'هالة بنت وهب', 'خديجة بنت خويلد'], "answer": 'آمنة بنت وهب', "explain": 'أم النبي ﷺ هي آمنة بنت وهب'},
    {"q": 'من هو أول من أسلم من الرجال؟', "options": ['علي بن أبي طالب', 'عمر بن الخطاب', 'أبو بكر الصديق', 'زيد بن حارثة'], "answer": 'أبو بكر الصديق', "explain": 'أبو بكر أول من أسلم من الرجال الأحرار'},
    {"q": 'في أي سنة كانت الهجرة النبوية؟', "options": ['620م', '622م', '621م', '623م'], "answer": '622م', "explain": 'الهجرة النبوية كانت عام 622م الموافق 1هـ'},
    {"q": 'كم غزوة غزاها النبي ﷺ بنفسه؟', "options": ['20', '23', '30', '27'], "answer": '27', "explain": 'غزا النبي ﷺ 27 غزوة بنفسه'},
    {"q": 'ما هو اسم ناقة النبي ﷺ؟', "options": ['العضباء فقط', 'القصواء فقط', 'كلها أسماء لها', 'الجدعاء فقط'], "answer": 'كلها أسماء لها', "explain": 'القصواء والعضباء والجدعاء كلها أسماء لناقة النبي ﷺ'},
    {"q": 'في أي معركة كُسرت رَباعيّة النبي ﷺ؟', "options": ['بدر', 'الخندق', 'حنين', 'أُحد'], "answer": 'أُحد', "explain": 'في غزوة أُحد شُجّ وجه النبي ﷺ وكُسرت رَباعيّته'},
    {"q": 'من هي أول زوجات النبي ﷺ؟', "options": ['خديجة بنت خويلد', 'حفصة', 'عائشة', 'زينب بنت جحش'], "answer": 'خديجة بنت خويلد', "explain": 'خديجة رضي الله عنها أول زوجات النبي ﷺ'},
    {"q": 'ما اسم جدّ النبي ﷺ الذي رعاه؟', "options": ['عبدالله', 'عبدالمطلب', 'أبو طالب', 'الزبير'], "answer": 'عبدالمطلب', "explain": 'عبدالمطلب رعى النبي ﷺ بعد وفاة أمه'},
    {"q": 'من هو الصحابي الملقب بسيف الله المسلول؟', "options": ['عمرو بن العاص', 'سعد بن أبي وقاص', 'خالد بن الوليد', 'أبو عبيدة'], "answer": 'خالد بن الوليد', "explain": 'لقّبه النبي ﷺ بسيف الله المسلول'},
    {"q": 'من هو أول مؤذن في الإسلام؟', "options": ['عبدالله بن زيد', 'بلال بن رباح', 'أبو محذورة', 'سعد القرظ'], "answer": 'بلال بن رباح', "explain": 'بلال بن رباح رضي الله عنه هو أول مؤذن في الإسلام'},
    {"q": 'من هو الصحابي الملقب بالفاروق؟', "options": ['أبو بكر', 'علي', 'عثمان', 'عمر بن الخطاب'], "answer": 'عمر بن الخطاب', "explain": 'لُقّب عمر بالفاروق لأن الله فرّق به بين الحق والباطل'},
    {"q": 'من هو الصحابي الملقب بذي النورين؟', "options": ['عثمان بن عفان', 'أبو بكر', 'علي بن أبي طالب', 'طلحة'], "answer": 'عثمان بن عفان', "explain": 'لُقّب بذي النورين لأنه تزوج بنتين للنبي ﷺ'},
    {"q": 'من هو الصحابي الذي بكى النبي ﷺ حين سمع قراءته؟', "options": ['أبو موسى الأشعري', 'معاذ بن جبل', 'أبي بن كعب', 'عبدالله بن مسعود'], "answer": 'عبدالله بن مسعود', "explain": 'بكى النبي ﷺ حين سمع قراءة ابن مسعود للقرآن'},
    {"q": 'من هو الصحابي الملقب بحواري رسول الله؟', "options": ['أبو بكر', 'سعد بن أبي وقاص', 'الزبير بن العوام', 'طلحة بن عبيدالله'], "answer": 'الزبير بن العوام', "explain": 'قال النبي ﷺ: إن لكل نبي حوارياً وحواريّ الزبير'},
    {"q": 'أكمل الحديث: إنما الأعمال...', "options": ['بالإخلاص', 'بالنيات', 'بالقلوب', 'بالإيمان'], "answer": 'بالنيات', "explain": 'الحديث: إنما الأعمال بالنيات وإنما لكل امرئ ما نوى'},
    {"q": 'أكمل الحديث: لا يؤمن أحدكم حتى يحب لأخيه...', "options": ['ما يحب لنفسه', 'الخير والهدى', 'ما يحب لربه', 'الجنة والنعيم'], "answer": 'ما يحب لنفسه', "explain": 'رواه البخاري ومسلم — من أصول الإيمان'},
    {"q": 'أكمل الحديث: المسلم من سلم المسلمون من...', "options": ['قلبه ونيته', 'ظلمه وجوره', 'كلامه وفعله', 'لسانه ويده'], "answer": 'لسانه ويده', "explain": 'رواه البخاري — من جوامع كلمه ﷺ'},
    {"q": 'أكمل الحديث: من كان يؤمن بالله واليوم الآخر فليقل...', "options": ['لا إله إلا الله', 'خيراً أو ليصمت', 'الحمد لله', 'سبحان الله'], "answer": 'خيراً أو ليصمت', "explain": 'رواه البخاري ومسلم — حثّ على صون اللسان'},
    {"q": 'أكمل الحديث: بُني الإسلام على خمس شهادة أن لا إله إلا الله...', "options": ['وإقام الصلاة وإيتاء الزكاة وصوم رمضان وحج البيت', 'والجهاد والصبر والتوكل', 'والصلاة والزكاة والصبر والحج', 'والصوم والحج والصدق والأمانة'], "answer": 'وإقام الصلاة وإيتاء الزكاة وصوم رمضان وحج البيت', "explain": 'حديث ابن عمر رضي الله عنهما في الصحيحين'},
    {"q": 'أكمل الآية: إن مع العسر...', "options": ['فرجاً قريباً', 'نصراً مبيناً', 'يُسرا', 'رحمةً واسعة'], "answer": 'يُسرا', "explain": 'سورة الشرح آية 6 — بُشرى بأن مع العسر يُسراً'},
    {"q": 'أكمل الآية: وما توفيقي إلا...', "options": ['بالصبر', 'بالإيمان', 'بالله', 'من عند الله'], "answer": 'بالله', "explain": 'سورة هود آية 88 — قالها شعيب عليه السلام'},
    {"q": 'أكمل الآية: ألا بذكر الله تطمئن...', "options": ['الأرواح', 'النفوس', 'العقول', 'القلوب'], "answer": 'القلوب', "explain": 'سورة الرعد آية 28 — من أعظم آيات القرآن'},
    {"q": 'أكمل الآية: فإذا عزمت فتوكل على...', "options": ['ربك وحده', 'الله', 'نفسك', 'العقل والحكمة'], "answer": 'الله', "explain": 'سورة آل عمران آية 159'},
    {"q": 'ما معنى كلمة الفلاح في القرآن؟', "options": ['النجاح والفوز', 'الرزق الوفير', 'الصبر والتحمل', 'العبادة الدائمة'], "answer": 'النجاح والفوز', "explain": 'الفلاح يعني النجاح والفوز بالجنة والنجاة من النار'},
    {"q": 'ما معنى كلمة القنوت في القرآن؟', "options": ['الطاعة والخشوع', 'الصمت التام', 'الصيام', 'الدعاء فقط'], "answer": 'الطاعة والخشوع', "explain": 'القنوت يعني الطاعة الكاملة والخشوع لله'},
    {"q": 'كم عدد تكبيرات صلاة الجنازة؟', "options": ['3', '4', '5', '6'], "answer": '4', "explain": 'صلاة الجنازة أربع تكبيرات بلا ركوع ولا سجود'},
    {"q": 'ما حكم صيام يوم العيدين؟', "options": ['مستحب', 'مكروه', 'جائز', 'حرام'], "answer": 'حرام', "explain": 'نهى النبي ﷺ عن صيام يوم الفطر ويوم الأضحى'},
    {"q": 'ما نصاب زكاة الذهب بالجرامات تقريباً؟', "options": ['50 جرام', '70 جرام', '85 جرام', '100 جرام'], "answer": '85 جرام', "explain": 'نصاب زكاة الذهب 85 جراماً إذا حال عليها الحول'},
    {"q": 'كم مرة تُطاف الكعبة في الطواف؟', "options": ['5 أشواط', '6 أشواط', '8 أشواط', '7 أشواط'], "answer": '7 أشواط', "explain": 'الطواف حول الكعبة سبعة أشواط'},
    {"q": 'ما الذي ينقض الوضوء باتفاق الفقهاء؟', "options": ['خروج الريح', 'الأكل', 'الضحك', 'النوم جالساً'], "answer": 'خروج الريح', "explain": 'خروج شيء من السبيلين ينقض الوضوء باتفاق'},
    {"q": 'من هو أول خليفة في الإسلام؟', "options": ['عمر بن الخطاب', 'علي بن أبي طالب', 'أبو بكر الصديق', 'عثمان بن عفان'], "answer": 'أبو بكر الصديق', "explain": 'أبو بكر الصديق أول خليفة للمسلمين بعد وفاة النبي ﷺ'},
    {"q": 'من هو الخليفة الذي فتح بيت المقدس؟', "options": ['أبو بكر', 'عمر بن الخطاب', 'علي', 'عثمان'], "answer": 'عمر بن الخطاب', "explain": 'فتح عمر رضي الله عنه بيت المقدس عام 637م'},
    {"q": 'في أي عام فُتحت مكة المكرمة هجرياً؟', "options": ['6هـ', '8هـ', '7هـ', '9هـ'], "answer": '8هـ', "explain": 'فُتحت مكة في رمضان السنة الثامنة للهجرة'},
    {"q": 'من هو أول شهيد في الإسلام؟', "options": ['بلال بن رباح', 'ياسر بن عامر', 'عمار بن ياسر', 'سمية بنت خياط'], "answer": 'سمية بنت خياط', "explain": 'سمية بنت خياط أم عمار — أول شهيدة في الإسلام'},
    {"q": 'من هو باني الكعبة المشرفة؟', "options": ['نوح وإدريس', 'محمد ﷺ وصحابته', 'إبراهيم وإسماعيل', 'آدم وحده'], "answer": 'إبراهيم وإسماعيل', "explain": 'قال تعالى: وإذ يرفع إبراهيم القواعد من البيت وإسماعيل'},
    {"q": 'ما لقب النبي إبراهيم عليه السلام؟', "options": ['خليل الله', 'كليم الله', 'نبي الله', 'روح الله'], "answer": 'خليل الله', "explain": 'قال تعالى: واتخذ الله إبراهيم خليلاً'},
    {"q": 'ما لقب النبي موسى عليه السلام؟', "options": ['خليل الله', 'كليم الله', 'روح الله', 'نجي الله'], "answer": 'كليم الله', "explain": 'كلّم الله موسى تكليماً مباشراً فلُقّب بكليم الله'},
    {"q": 'ما لقب النبي عيسى عليه السلام في القرآن؟', "options": ['خليل الله', 'كليم الله', 'صفي الله', 'روح الله وكلمته'], "answer": 'روح الله وكلمته', "explain": 'قال تعالى: إنما المسيح عيسى ابن مريم رسول الله وكلمته وروح منه'},
    {"q": 'من هو النبي الملقب بأبي البشر؟', "options": ['آدم', 'إبراهيم', 'نوح', 'محمد ﷺ'], "answer": 'آدم', "explain": 'آدم عليه السلام أبو البشرية كلها'},
    {"q": 'كم جزءاً في القرآن الكريم؟', "options": ['25', '28', '30', '32'], "answer": '30', "explain": 'القرآن الكريم مقسّم إلى 30 جزءاً'},
    {"q": 'ما هي أقصر سورة في القرآن؟', "options": ['الفاتحة', 'الناس', 'الفلق', 'الكوثر'], "answer": 'الكوثر', "explain": 'سورة الكوثر أقصر سورة في القرآن بثلاث آيات فقط'},
    {"q": 'كم مرة ذُكر اسم محمد ﷺ في القرآن؟', "options": ['2', '3', '4', '5'], "answer": '4', "explain": 'ذُكر اسم محمد ﷺ أربع مرات في القرآن الكريم'},
    {"q": 'في أي يوم خُلق آدم عليه السلام؟', "options": ['الاثنين', 'الجمعة', 'الأربعاء', 'السبت'], "answer": 'الجمعة', "explain": 'قال النبي ﷺ: خُلق آدم يوم الجمعة'},
    {"q": 'كم باباً للجنة؟', "options": ['8', '7', '6', '9'], "answer": '8', "explain": 'للجنة ثمانية أبواب منها باب الريّان لأهل الصيام'},
    {"q": 'كم باباً للنار؟', "options": ['7', '6', '5', '8'], "answer": '7', "explain": 'قال تعالى: لها سبعة أبواب لكل باب منهم جزء مقسوم'},
    {"q": 'ما هو الذكر الأثقل في الميزان؟', "options": ['لا إله إلا الله', 'سبحان الله وبحمده سبحان الله العظيم', 'الحمد لله رب العالمين', 'الله أكبر كبيراً'], "answer": 'سبحان الله وبحمده سبحان الله العظيم', "explain": 'قال النبي ﷺ: كلمتان خفيفتان على اللسان ثقيلتان في الميزان'},
    {"q": 'من هو الملك الموكّل بالوحي؟', "options": ['ميكائيل', 'إسرافيل', 'جبريل', 'عزرائيل'], "answer": 'جبريل', "explain": 'جبريل عليه السلام هو أمين الوحي'},
    {"q": 'ما هي السورة التي تُقرأ على المحتضر؟', "options": ['الفاتحة', 'البقرة', 'الرحمن', 'يس'], "answer": 'يس', "explain": 'قال النبي ﷺ: اقرأوا على موتاكم يس'},
    {"q": 'في أي سنة وقعت غزوة بدر الكبرى؟', "options": ['2هـ', '1هـ', '3هـ', '4هـ'], "answer": '2هـ', "explain": 'غزوة بدر كانت في 17 رمضان السنة الثانية للهجرة'},
    {"q": 'كم كان عدد المسلمين في غزوة بدر تقريباً؟', "options": ['100', '213', '313', '500'], "answer": '313', "explain": 'كان المسلمون 313 رجلاً في مقابل نحو 1000 من المشركين'},
    {"q": 'من هو الصحابي الذي سمّاه النبي ﷺ حب الله ورسوله؟', "options": ['عمر', 'علي بن أبي طالب', 'أبو بكر', 'أسامة بن زيد'], "answer": 'أسامة بن زيد', "explain": 'قال النبي ﷺ لأسامة: إنك لحبي وابن حبي'},
    {"q": 'ما اسم أول ولد وُلد للمهاجرين في المدينة؟', "options": ['عبدالله بن عمر', 'عبدالله بن الزبير', 'محمد بن علي', 'سالم بن أبي حذيفة'], "answer": 'عبدالله بن الزبير', "explain": 'كان المشركون يقولون لن يولد لهم فجاء عبدالله بن الزبير'},
    {"q": 'كم دامت دعوة النبي ﷺ في مكة قبل الهجرة؟', "options": ['13 سنة', '10 سنوات', '8 سنوات', '15 سنة'], "answer": '13 سنة', "explain": 'مكث النبي ﷺ في مكة يدعو 13 سنة قبل الهجرة'},
    {"q": 'ما هي السورة التي تُسمى قلب القرآن؟', "options": ['الفاتحة', 'البقرة', 'الكهف', 'يس'], "answer": 'يس', "explain": 'قال النبي ﷺ: إن لكل شيء قلباً وقلب القرآن يس'},
    {"q": 'كم آية في سورة الفاتحة؟', "options": ['5', '6', '7', '8'], "answer": '7', "explain": 'سورة الفاتحة سبع آيات وهي السبع المثاني'},
    {"q": 'ما هي السورة التي من قرأها حُفظ من الدجال؟', "options": ['يس', 'الكهف', 'البقرة', 'الإخلاص'], "answer": 'الكهف', "explain": 'قال النبي ﷺ: من قرأ عشر آيات من سورة الكهف عُصم من الدجال'},
    {"q": 'كم حرفاً في البسملة؟', "options": ['17', '19', '18', '20'], "answer": '19', "explain": 'بسم الله الرحمن الرحيم تتكون من 19 حرفاً'},
    {"q": 'ما هو آخر ما نزل من القرآن كاملاً من السور؟', "options": ['المائدة', 'البقرة', 'التوبة', 'النصر'], "answer": 'النصر', "explain": 'سورة النصر آخر ما نزل كاملاً وفيها إشارة لوفاة النبي ﷺ'},
    {"q": 'أكمل الآية: وقل رب زدني...', "options": ['رزقاً', 'صبراً', 'علماً', 'هدىً'], "answer": 'علماً', "explain": 'سورة طه آية 114 — الدعاء بالعلم'},
    {"q": 'أكمل الآية: حسبنا الله ونعم...', "options": ['الوكيل', 'المولى', 'الرحيم', 'الحفيظ'], "answer": 'الوكيل', "explain": 'سورة آل عمران — قالها إبراهيم حين أُلقي في النار وقالها النبي ﷺ'},
    {"q": 'معنى كلمة التوكل في القرآن؟', "options": ['التسليم للقضاء فقط', 'ترك العمل', 'الاعتماد على الله مع الأخذ بالأسباب', 'الصبر على البلاء'], "answer": 'الاعتماد على الله مع الأخذ بالأسباب', "explain": 'التوكل هو صدق الاعتماد على الله مع بذل الأسباب'},
    {"q": 'معنى كلمة الصراط في القرآن؟', "options": ['الجسر', 'الميزان', 'السبيل الضيق', 'الطريق'], "answer": 'الطريق', "explain": 'الصراط يعني الطريق الواضح المستقيم'},
    {"q": 'أكمل الحديث: خير الناس أنفعهم...', "options": ['للناس', 'لأهلهم', 'لدينهم', 'لربهم'], "answer": 'للناس', "explain": 'قال النبي ﷺ: خير الناس أنفعهم للناس — رواه الطبراني'},
    {"q": 'أكمل الحديث: الدنيا سجن المؤمن وجنة...', "options": ['العاصي', 'الكافر', 'المنافق', 'الجاحد'], "answer": 'الكافر', "explain": 'رواه مسلم — يعني المؤمن يصبر في الدنيا وينعم في الآخرة'},
    {"q": 'أكمل الحديث: من صام رمضان إيماناً واحتساباً غُفر له...', "options": ['ذنبه كله', 'ذنوب يوم وليلة', 'ما تقدم من ذنبه', 'كبائر ذنبه'], "answer": 'ما تقدم من ذنبه', "explain": 'متفق عليه — فضل صيام رمضان'},
    {"q": 'أكمل الحديث: تبسّمك في وجه أخيك...', "options": ['صدقة', 'من الإيمان', 'من الإحسان', 'نور'], "answer": 'صدقة', "explain": 'رواه الترمذي — حثّ على إظهار البشاشة'},
    {"q": 'أكمل الحديث: كل ابن آدم خطّاء وخير الخطّائين...', "options": ['من استغفر', 'التوّابون', 'من تاب', 'الصابرون'], "answer": 'التوّابون', "explain": 'رواه الترمذي وابن ماجه — حثّ على التوبة'},
    {"q": 'ما شروط قبول العبادة؟', "options": ['الإخلاص فقط', 'المتابعة فقط', 'النية والخشوع', 'الإخلاص لله والمتابعة للنبي ﷺ'], "answer": 'الإخلاص لله والمتابعة للنبي ﷺ', "explain": 'لا تُقبل العبادة إلا بشرطين: الإخلاص والمتابعة'},
    {"q": 'ما حكم صلاة الجمعة؟', "options": ['سنة مؤكدة', 'فرض عين على الرجال', 'فرض كفاية', 'مستحبة'], "answer": 'فرض عين على الرجال', "explain": 'صلاة الجمعة فرض عين على كل مسلم بالغ حر مقيم'},
    {"q": 'ما هي أركان الصلاة؟', "options": ['النية والتكبير فقط', 'القيام والركوع والسجود فقط', 'خمسة أركان فقط', 'النية والتكبير والقراءة والركوع والسجود والتشهد والتسليم'], "answer": 'النية والتكبير والقراءة والركوع والسجود والتشهد والتسليم', "explain": 'أركان الصلاة سبعة وبدونها لا تصح'},
    {"q": 'ما الفرق بين الركن والواجب في الصلاة؟', "options": ['ترك الركن يُبطل الصلاة وترك الواجب يُوجب سجود السهو', 'لا فرق', 'الواجب أهم من الركن', 'الركن يُقضى والواجب لا'], "answer": 'ترك الركن يُبطل الصلاة وترك الواجب يُوجب سجود السهو', "explain": 'الركن لا تصح الصلاة بدونه والواجب يُجبر بسجود السهو'},
    {"q": 'ما هي النجاسة التي لا تطهر بالغسل؟', "options": ['الدم', 'البول', 'الكلب في الملاقاة', 'المني'], "answer": 'الكلب في الملاقاة', "explain": 'يُغسل الإناء من ولوغ الكلب سبعاً إحداهن بالتراب'},
    {"q": 'من هو المعروف بـ ذي القرنين في التاريخ الإسلامي؟', "options": ['الإسكندر المقدوني', 'كورش الكبير', 'نبي من الأنبياء', 'رجل صالح ذكره القرآن'], "answer": 'رجل صالح ذكره القرآن', "explain": 'ذو القرنين مذكور في سورة الكهف وهو رجل صالح ملّكه الله في الأرض'},
    {"q": 'ما هي أول دولة إسلامية تعترف بالإسلام رسمياً؟', "options": ['فارس', 'الروم', 'الحبشة', 'اليمن'], "answer": 'الحبشة', "explain": 'آوى النجاشي ملك الحبشة المسلمين وعدل بينهم واعترف بالإسلام'},
    {"q": 'من أول من هاجر إلى الحبشة؟', "options": ['جعفر بن أبي طالب', 'عثمان بن عفان', 'الزبير بن العوام', 'عبدالرحمن بن عوف'], "answer": 'عثمان بن عفان', "explain": 'هاجر عثمان وزوجته رقية بنت النبي ﷺ في أول هجرة للحبشة'},
    {"q": 'ما اسم قائد جيش المسلمين في معركة اليرموك؟', "options": ['خالد بن الوليد', 'عمرو بن العاص', 'سعد بن أبي وقاص', 'أبو عبيدة بن الجراح'], "answer": 'خالد بن الوليد', "explain": 'قاد خالد بن الوليد المسلمين في معركة اليرموك الفاصلة'},
    {"q": 'كم سنة كان يوسف عليه السلام في السجن؟', "options": ['3 سنوات', '7 سنوات', '5 سنوات', '10 سنوات'], "answer": '7 سنوات', "explain": 'قيل إن يوسف مكث في السجن سبع سنوات بعد إغواء امرأة العزيز'},
    {"q": 'ما هو المعجزة الكبرى التي أُعطيها موسى عليه السلام؟', "options": ['إحياء الموتى', 'شفاء الأكمه', 'الكلام مع الله مباشرة', 'العصا التي تنقلب حية'], "answer": 'العصا التي تنقلب حية', "explain": 'من أعظم معجزات موسى العصا التي تنقلب ثعباناً وتلقف سحر السحرة'},
    {"q": 'ما هو الجبل الذي كلّم الله عليه موسى؟', "options": ['جبل الطور', 'جبل حراء', 'جبل عرفات', 'جبل أُحد'], "answer": 'جبل الطور', "explain": 'قال تعالى: وناديناه من جانب الطور الأيمن — على جبل الطور'},
    {"q": 'من هو النبي الذي أُوتي الزبور؟', "options": ['إبراهيم', 'موسى', 'داود', 'سليمان'], "answer": 'داود', "explain": 'قال تعالى: وآتينا داود زبوراً'},
    {"q": 'كم نبياً ذُكر في سورة الأنبياء؟', "options": ['10', '14', '18', '16'], "answer": '16', "explain": 'ذُكر في سورة الأنبياء ستة عشر نبياً من الأنبياء الكرام'},
    {"q": 'ما هو الدعاء المستجاب بين الأذان والإقامة؟', "options": ['اللهم رب هذه الدعوة التامة', 'الدعاء في هذا الوقت لا يُرد', 'لا إله إلا الله وحده', 'ربنا لك الحمد'], "answer": 'الدعاء في هذا الوقت لا يُرد', "explain": 'قال النبي ﷺ: الدعاء لا يُرد بين الأذان والإقامة'},
    {"q": 'ما هي ليلة القدر؟', "options": ['إحدى ليالي العشر الأخيرة من رمضان', 'ليلة 27 رمضان فقط', 'أول ليلة رمضان', 'ليلة النصف من شعبان'], "answer": 'إحدى ليالي العشر الأخيرة من رمضان', "explain": 'قال النبي ﷺ: التمسوا ليلة القدر في العشر الأواخر من رمضان'},
    {"q": 'ما هو أفضل الذكر؟', "options": ['الحمد لله', 'سبحان الله', 'لا إله إلا الله', 'الله أكبر'], "answer": 'لا إله إلا الله', "explain": 'قال النبي ﷺ: أفضل الذكر لا إله إلا الله'},
    {"q": 'كم عدد الصلوات المفروضة في اليوم؟', "options": ['5', '4', '3', '6'], "answer": '5', "explain": 'فُرضت خمس صلوات ليلة المعراج وهي الفريضة اليومية'},
    {"q": 'ما هو الوضوء الكامل كم مرة لكل عضو؟', "options": ['مرة واحدة', 'ثلاث مرات', 'مرتان', 'حسب العضو'], "answer": 'ثلاث مرات', "explain": 'السنة غسل كل عضو ثلاث مرات والواجب مرة واحدة'},
    {"q": 'ما هو اسم صلاة الاستسقاء؟', "options": ['صلاة الاستخارة', 'صلاة الحاجة', 'صلاة طلب المطر', 'صلاة التهجد'], "answer": 'صلاة طلب المطر', "explain": 'صلاة الاستسقاء صلاة مشروعة لطلب المطر من الله'},
    {"q": 'ما هو الفرق بين النبي والرسول؟', "options": ['لا فرق بينهما', 'الرسول بشر فقط والنبي قد يكون ملكاً', 'النبي أفضل من الرسول', 'الرسول أُوحي إليه بشريعة جديدة والنبي يتبع شريعة من قبله'], "answer": 'الرسول أُوحي إليه بشريعة جديدة والنبي يتبع شريعة من قبله', "explain": 'الرسول أُرسل بشريعة جديدة وكتاب، والنبي يُبلّغ شريعة من قبله'},
]


# ─── لوحة المتصدرين ───────────────────────────────────
def build_leaderboard(session_id: int) -> str:
    participants = get_participants(session_id)
    if not participants:
        return "لا يوجد مشاركون"
    medals = ["🥇", "🥈", "🥉"]
    text = "🏆 *لوحة المتصدرين*\n━━━━━━━━━━━━━━━\n\n"
    for i, p in enumerate(participants):
        medal = medals[i] if i < 3 else f"{i+1}."
        text += f"{medal} {p['full_name']} — {p['score']} نقطة\n"
    return text


# ─── إرسال سؤال ───────────────────────────────────────
async def send_question(context: ContextTypes.DEFAULT_TYPE, chat_id: int, session_id: int, q_index: int, questions: list):
    if q_index >= len(questions):
        # انتهت الأسئلة
        finish_session(session_id)
        leaderboard = build_leaderboard(session_id)
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"🎉 *انتهت المسابقة!*\n\n{leaderboard}",
            parse_mode="Markdown"
        )
        return

    q = questions[q_index]
    opts = q["options"]
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(opts[0], callback_data=f"cqa_{session_id}_{q_index}_0"),
         InlineKeyboardButton(opts[1], callback_data=f"cqa_{session_id}_{q_index}_1")],
        [InlineKeyboardButton(opts[2], callback_data=f"cqa_{session_id}_{q_index}_2"),
         InlineKeyboardButton(opts[3], callback_data=f"cqa_{session_id}_{q_index}_3")],
    ])
    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            f"❓ *سؤال {q_index + 1}/{len(questions)}*\n"
            "━━━━━━━━━━━━━━━\n\n"
            f"*{q['q']}*\n\n"
            "⏰ لديك 30 ثانية للإجابة"
        ),
        parse_mode="Markdown",
        reply_markup=kb
    )
    update_session_status(session_id, "active", q_index)

    # جدول انتقال السؤال التالي بعد 30 ثانية
    context.job_queue.run_once(
        next_question_job,
        when=30,
        data={"chat_id": chat_id, "session_id": session_id, "q_index": q_index, "questions": questions},
        name=f"quiz_{session_id}_{q_index}"
    )


# ─── أوامر ────────────────────────────────────────────
async def next_question_job(context: ContextTypes.DEFAULT_TYPE):
    """يُشغَّل بعد 30 ثانية للانتقال للسؤال التالي"""
    data = context.job.data
    chat_id = data["chat_id"]
    session_id = data["session_id"]
    q_index = data["q_index"]
    questions = data["questions"]

    # تحقق إذا الجلسة لسا شغّالة
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT status FROM quiz_sessions WHERE session_id=?",
            (session_id,)
        ).fetchone()

    if not row or row[0] == "finished":
        return

    q = questions[q_index]
    # أرسل الإجابة الصحيحة
    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"✅ *الإجابة الصحيحة:* {q['answer']}\n📖 {q.get('explain', '')}",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"خطأ إرسال إجابة: {e}")

    await asyncio.sleep(3)
    await send_question(context, chat_id, session_id, q_index + 1, questions)


async def cmd_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بدء مسابقة جماعية"""
    chat = update.effective_chat
    user = update.effective_user

    if chat.type == "private":
        await update.message.reply_text("⚠️ هذا الأمر للقنوات والمجموعات فقط!")
        return

    # تحقق إذا في جلسة نشطة
    existing = get_active_session(chat.id)
    if existing:
        await update.message.reply_text("⚠️ يوجد مسابقة نشطة الآن! انتظر حتى تنتهي.")
        return

    # أنشئ جلسة جديدة
    session_id = create_session(chat.id, user.id)

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✋ انضمام للمسابقة", callback_data=f"cq_join_{session_id}")],
        [InlineKeyboardButton("🚀 بدء المسابقة", callback_data=f"cq_start_{session_id}")],
        [InlineKeyboardButton("❌ إلغاء", callback_data=f"cq_cancel_{session_id}")],
    ])

    await update.message.reply_text(
        "🏆 *مسابقة إسلامية جماعية*\n"
        "━━━━━━━━━━━━━━━\n\n"
        "📋 10 أسئلة في الفقه والتفسير والسيرة\n"
        "⏰ 30 ثانية لكل سؤال\n"
        "⭐ كل إجابة صحيحة = نقطة\n\n"
        "اضغط **انضمام** للمشاركة\n"
        "ثم اضغط **بدء** لبدء الأسئلة 👇",
        parse_mode="Markdown",
        reply_markup=kb
    )


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    user = q.from_user
    data = q.data

    # ─── انضمام ───
    if data.startswith("cq_join_"):
        session_id = int(data.split("_")[2])
        session = get_active_session(q.message.chat.id)
        if not session or session["status"] != "waiting":
            await q.answer("⚠️ المسابقة بدأت أو انتهت!", show_alert=True)
            return
        joined = join_session(session_id, user.id, user.username, user.full_name)
        if joined:
            await q.answer(f"✅ انضممت للمسابقة!", show_alert=True)
            participants = get_participants(session_id)
            names = "\n".join([f"• {p['full_name']}" for p in participants])
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton(f"✋ انضمام ({len(participants)})", callback_data=f"cq_join_{session_id}")],
                [InlineKeyboardButton("🚀 بدء المسابقة", callback_data=f"cq_start_{session_id}")],
                [InlineKeyboardButton("❌ إلغاء", callback_data=f"cq_cancel_{session_id}")],
            ])
            try:
                await q.edit_message_text(
                    "🏆 *مسابقة إسلامية جماعية*\n"
                    "━━━━━━━━━━━━━━━\n\n"
                    f"👥 *المشاركون ({len(participants)}):*\n{names}\n\n"
                    "اضغط **بدء** للبدء 👇",
                    parse_mode="Markdown",
                    reply_markup=kb
                )
            except Exception:
                pass
        else:
            await q.answer("أنت مسجّل مسبقاً! ✅", show_alert=True)

    # ─── بدء ───
    elif data.startswith("cq_start_"):
        session_id = int(data.split("_")[2])
        session = get_active_session(q.message.chat.id)
        if not session:
            await q.answer("⚠️ الجلسة غير موجودة!", show_alert=True)
            return
        # فقط المشرف أو من أنشأ المسابقة
        if user.id != session["created_by"] and user.id not in ADMIN_IDS:
            await q.answer("⚠️ فقط من أنشأ المسابقة يمكنه البدء!", show_alert=True)
            return
        if session["status"] != "waiting":
            await q.answer("⚠️ المسابقة بدأت مسبقاً!", show_alert=True)
            return
        participants = get_participants(session_id)
        if len(participants) < 1:
            await q.answer("⚠️ لا يوجد مشاركون! اطلب من الأعضاء الانضمام أولاً.", show_alert=True)
            return

        await q.answer("🚀 بدأت المسابقة!")
        try:
            await q.edit_message_text(
                f"🚀 *بدأت المسابقة!*\n\nعدد المشاركين: {len(participants)}\nعدد الأسئلة: 10\n\nاستعدوا! 💪",
                parse_mode="Markdown"
            )
        except Exception:
            pass

        questions = random.sample(QUESTIONS, min(10, len(QUESTIONS)))
        save_session_questions(session_id, questions)
        update_session_status(session_id, "active", 0)
        await send_question(context, q.message.chat.id, session_id, 0, questions)

    # ─── إلغاء ───
    elif data.startswith("cq_cancel_"):
        session_id = int(data.split("_")[2])
        session = get_active_session(q.message.chat.id)
        if not session:
            await q.answer("لا توجد مسابقة نشطة!")
            return
        if user.id != session["created_by"] and user.id not in ADMIN_IDS:
            await q.answer("⚠️ فقط من أنشأ المسابقة يمكنه الإلغاء!", show_alert=True)
            return
        finish_session(session_id)
        await q.answer("تم إلغاء المسابقة")
        try:
            await q.edit_message_text("❌ تم إلغاء المسابقة.")
        except Exception:
            pass

    # ─── إجابة سؤال ───
    elif data.startswith("cqa_"):
        parts = data.split("_")
        session_id = int(parts[1])
        q_index = int(parts[2])
        answer_idx = int(parts[3])

        session = get_active_session(q.message.chat.id)
        if not session or session["status"] == "finished":
            await q.answer("⚠️ المسابقة انتهت!", show_alert=True)
            return

        if session["current_q"] != q_index:
            await q.answer("⚠️ هذا السؤال انتهى!", show_alert=True)
            return

        # تحقق إذا أجاب مسبقاً
        if has_answered(session_id, q_index, user.id):
            await q.answer("أجبت مسبقاً على هذا السؤال!", show_alert=True)
            return

        # تحقق إذا المستخدم مشارك
        participants = get_participants(session_id)
        participant_ids = [p["user_id"] for p in participants]
        if user.id not in participant_ids:
            # أضفه تلقائياً
            join_session(session_id, user.id, user.username, user.full_name)

        questions = load_session_questions(session_id) or QUESTIONS
        if q_index >= len(questions):
            await q.answer("⚠️ خطأ في السؤال!", show_alert=True)
            return

        q_data = questions[q_index]
        chosen = q_data["options"][answer_idx]
        correct = q_data["answer"]
        is_correct = chosen == correct

        record_answer(session_id, q_index, user.id, chosen, is_correct)

        if is_correct:
            await q.answer("✅ إجابة صحيحة! +1 نقطة 🌟", show_alert=True)
        else:
            await q.answer(f"❌ خطأ! الإجابة الصحيحة: {correct}", show_alert=True)


async def cmd_scores(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض النتائج الحالية"""
    chat = update.effective_chat
    session = get_active_session(chat.id)
    if not session:
        await update.message.reply_text("لا توجد مسابقة نشطة الآن.")
        return
    leaderboard = build_leaderboard(session["session_id"])
    await update.message.reply_text(leaderboard, parse_mode="Markdown")


async def cmd_stop_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إيقاف المسابقة"""
    chat = update.effective_chat
    user = update.effective_user
    session = get_active_session(chat.id)
    if not session:
        await update.message.reply_text("لا توجد مسابقة نشطة.")
        return
    if user.id != session["created_by"] and user.id not in ADMIN_IDS:
        await update.message.reply_text("⚠️ فقط من أنشأ المسابقة يمكنه إيقافها!")
        return
    finish_session(session["session_id"])
    leaderboard = build_leaderboard(session["session_id"])
    await update.message.reply_text(
        f"🛑 *تم إيقاف المسابقة*\n\n{leaderboard}",
        parse_mode="Markdown"
    )


# ─── main ─────────────────────────────────────────────
def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN غير موجود!")
        return

    init_db()
    logger.info("🚀 quiz_channel.py يشتغل...")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("quiz", cmd_quiz))
    app.add_handler(CommandHandler("scores", cmd_scores))
    app.add_handler(CommandHandler("stopquiz", cmd_stop_quiz))
    app.add_handler(CallbackQueryHandler(handle_callback))

    logger.info("✅ جاهز — /quiz لبدء مسابقة")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()[
    {"q": 'كم عدد أركان الإسلام؟', "options": ['3', '4', '5', '6'], "answer": '5', "explain": 'الشهادتان، الصلاة، الزكاة، الصوم، الحج'},
    {"q": 'ما هي أطول سورة في القرآن؟', "options": ['آل عمران', 'البقرة', 'النساء', 'المائدة'], "answer": 'البقرة', "explain": 'سورة البقرة هي أطول سورة في القرآن الكريم'},
    {"q": 'كم عدد أنبياء الله المذكورين في القرآن؟', "options": ['20', '35', '30', '25'], "answer": '25', "explain": 'ذُكر 25 نبياً بالاسم في القرآن الكريم'},
    {"q": 'ما هو اسم والد النبي إبراهيم عليه السلام؟', "options": ['آزر', 'عمران', 'يشكر', 'تارح'], "answer": 'آزر', "explain": 'ذكر القرآن اسم والد إبراهيم آزر'},
    {"q": 'في أي شهر نزل القرآن الكريم؟', "options": ['رجب', 'شعبان', 'محرم', 'رمضان'], "answer": 'رمضان', "explain": 'قال تعالى: شهر رمضان الذي أنزل فيه القرآن'},
    {"q": 'كم عدد سور القرآن الكريم؟', "options": ['110', '112', '114', '116'], "answer": '114', "explain": 'يتكون القرآن الكريم من 114 سورة'},
    {"q": 'ما هي السورة التي تعدل ثلث القرآن؟', "options": ['الإخلاص', 'الفاتحة', 'الكوثر', 'الفلق'], "answer": 'الإخلاص', "explain": 'قال النبي ﷺ إن سورة الإخلاص تعدل ثلث القرآن'},
    {"q": 'كم عدد أركان الإيمان؟', "options": ['4', '6', '5', '7'], "answer": '6', "explain": 'الإيمان بالله وملائكته وكتبه ورسله واليوم الآخر والقدر'},
    {"q": 'ما هو أول مسجد بُني في الإسلام؟', "options": ['المسجد الحرام', 'مسجد قباء', 'مسجد النبي', 'المسجد الأقصى'], "answer": 'مسجد قباء', "explain": 'مسجد قباء هو أول مسجد بُني في الإسلام عند هجرة النبي ﷺ'},
    {"q": 'كم سنة استغرق نزول القرآن الكريم؟', "options": ['20 سنة', '30 سنة', '25 سنة', '23 سنة'], "answer": '23 سنة', "explain": 'نزل القرآن الكريم على مدى 23 سنة'},
    {"q": 'ما هو اسم جبل النور الذي نزل فيه الوحي؟', "options": ['جبل عرفات', 'جبل ثور', 'جبل حراء', 'جبل أبي قبيس'], "answer": 'جبل حراء', "explain": 'في غار حراء بجبل النور نزل أول وحي على النبي ﷺ'},
    {"q": 'ما هي أول آية نزلت من القرآن؟', "options": ['اقرأ باسم ربك', 'الحمد لله', 'بسم الله', 'يا أيها المدثر'], "answer": 'اقرأ باسم ربك', "explain": 'أول ما نزل: اقرأ باسم ربك الذي خلق'},
    {"q": 'كم سنة بقي أصحاب الكهف في نومهم؟', "options": ['100 سنة', '309 سنوات', '200 سنة', '400 سنة'], "answer": '309 سنوات', "explain": 'قال تعالى: ولبثوا في كهفهم ثلاث مئة سنين وازدادوا تسعاً'},
    {"q": 'ما هي السورة الوحيدة التي ليس فيها بسملة في أولها؟', "options": ['الفيل', 'الإخلاص', 'التوبة', 'المعوذتان'], "answer": 'التوبة', "explain": 'سورة التوبة لم يُكتب في أولها بسملة'},
    {"q": 'ما هي السورة التي تُسمى عروس القرآن؟', "options": ['الرحمن', 'يس', 'الواقعة', 'الكهف'], "answer": 'الرحمن', "explain": 'سورة الرحمن تُسمى عروس القرآن'},
    {"q": 'من هو النبي الذي ابتلعه الحوت؟', "options": ['إلياس', 'إدريس', 'أيوب', 'يونس'], "answer": 'يونس', "explain": 'يونس عليه السلام ذو النون التقمه الحوت'},
    {"q": 'ما هي مدة نوح عليه السلام في قومه؟', "options": ['300 سنة', '950 سنة', '500 سنة', '1000 سنة'], "answer": '950 سنة', "explain": 'قال تعالى: فلبث فيهم ألف سنة إلا خمسين عاماً'},
    {"q": 'ما هي السورة التي تحتوي على آية الكرسي؟', "options": ['آل عمران', 'النساء', 'البقرة', 'المائدة'], "answer": 'البقرة', "explain": 'آية الكرسي هي الآية 255 من سورة البقرة'},
    {"q": 'أي نبي سكن في مصر وأصبح عزيزها؟', "options": ['موسى', 'إسحاق', 'إبراهيم', 'يوسف'], "answer": 'يوسف', "explain": 'يوسف عليه السلام أصبح عزيز مصر'},
    {"q": 'من هو أول من جمع القرآن في مصحف واحد؟', "options": ['أبو بكر الصديق', 'عمر بن الخطاب', 'زيد بن ثابت', 'علي بن أبي طالب'], "answer": 'أبو بكر الصديق', "explain": 'أبو بكر أمر بجمع القرآن في مصحف واحد'},
    {"q": 'كم ركعة تُصلى صلاة العيد؟', "options": ['أربع ركعات', 'ركعتان', 'ثلاث ركعات', 'ست ركعات'], "answer": 'ركعتان', "explain": 'صلاة العيد ركعتان مع تكبيرات زائدة'},
    {"q": 'ما هي الصلاة الوسطى المذكورة في القرآن؟', "options": ['الفجر', 'الظهر', 'المغرب', 'العصر'], "answer": 'العصر', "explain": 'قال تعالى: حافظوا على الصلوات والصلاة الوسطى — وهي العصر'},
    {"q": 'كم حجة حجّها النبي ﷺ؟', "options": ['ثلاث حجج', 'حجتان', 'حجة واحدة', 'لم يحج'], "answer": 'حجة واحدة', "explain": 'حجّ النبي ﷺ حجة واحدة وهي حجة الوداع عام 10هـ'},
    {"q": 'من هو الصحابي الملقب بـ أمين الأمة؟', "options": ['أبو عبيدة', 'عمر', 'أبو بكر', 'علي'], "answer": 'أبو عبيدة', "explain": 'لقّب النبي ﷺ أبا عبيدة بن الجراح بأمين هذه الأمة'},
    {"q": 'ما هو الفرق بين الزكاة والصدقة؟', "options": ['لا فرق', 'الصدقة واجبة والزكاة تطوع', 'الزكاة واجبة والصدقة تطوع', 'الزكاة للفقراء فقط'], "answer": 'الزكاة واجبة والصدقة تطوع', "explain": 'الزكاة ركن من أركان الإسلام واجبة، والصدقة تطوع مستحب'},
    {"q": 'ما هو أول ما خلق الله؟', "options": ['الماء', 'القلم', 'العرش', 'النور'], "answer": 'القلم', "explain": 'قال النبي ﷺ: أول ما خلق الله القلم فقال له اكتب'},
    {"q": 'ما هي آخر آية نزلت من القرآن؟', "options": ['واتقوا يوماً ترجعون', 'اليوم أكملت لكم دينكم', 'إذا جاء نصر الله', 'قل أعوذ برب الناس'], "answer": 'واتقوا يوماً ترجعون', "explain": 'قيل إن آخر آية نزلت: واتقوا يوماً ترجعون فيه إلى الله'},
    {"q": 'ما هي اسم زوجة فرعون المؤمنة؟', "options": ['هاجر', 'بلقيس', 'مريم', 'آسية'], "answer": 'آسية', "explain": 'آسية بنت مزاحم زوجة فرعون آمنت بالله'},
    {"q": 'من هو النبي الذي كان نجاراً؟', "options": ['داود', 'زكريا', 'سليمان', 'يوسف'], "answer": 'زكريا', "explain": 'كان زكريا عليه السلام نجاراً يعمل بيده'},
    {"q": 'ما هي الآية الأطول في القرآن؟', "options": ['آية الكرسي', 'أول البقرة', 'آية النكاح', 'آية الدَّين'], "answer": 'آية الدَّين', "explain": 'آية الدَّين (البقرة 282) هي الأطول في القرآن'},
    {"q": 'في أي عام وُلد النبي محمد ﷺ؟', "options": ['570م', '568م', '572م', '575م'], "answer": '570م', "explain": 'وُلد النبي ﷺ عام الفيل الموافق 570م'},
    {"q": 'كم عمر النبي ﷺ حين تُوفّي؟', "options": ['60 سنة', '61 سنة', '63 سنة', '65 سنة'], "answer": '63 سنة', "explain": 'تُوفّي النبي ﷺ وعمره 63 سنة'},
    {"q": 'ما هو اسم أم النبي ﷺ؟', "options": ['آمنة بنت وهب', 'فاطمة بنت أسد', 'هالة بنت وهب', 'خديجة بنت خويلد'], "answer": 'آمنة بنت وهب', "explain": 'أم النبي ﷺ هي آمنة بنت وهب'},
    {"q": 'من هو أول من أسلم من الرجال؟', "options": ['علي بن أبي طالب', 'عمر بن الخطاب', 'أبو بكر الصديق', 'زيد بن حارثة'], "answer": 'أبو بكر الصديق', "explain": 'أبو بكر أول من أسلم من الرجال الأحرار'},
    {"q": 'في أي سنة كانت الهجرة النبوية؟', "options": ['620م', '622م', '621م', '623م'], "answer": '622م', "explain": 'الهجرة النبوية كانت عام 622م الموافق 1هـ'},
    {"q": 'كم غزوة غزاها النبي ﷺ بنفسه؟', "options": ['20', '23', '30', '27'], "answer": '27', "explain": 'غزا النبي ﷺ 27 غزوة بنفسه'},
    {"q": 'ما هو اسم ناقة النبي ﷺ؟', "options": ['العضباء فقط', 'القصواء فقط', 'كلها أسماء لها', 'الجدعاء فقط'], "answer": 'كلها أسماء لها', "explain": 'القصواء والعضباء والجدعاء كلها أسماء لناقة النبي ﷺ'},
    {"q": 'في أي معركة كُسرت رَباعيّة النبي ﷺ؟', "options": ['بدر', 'الخندق', 'حنين', 'أُحد'], "answer": 'أُحد', "explain": 'في غزوة أُحد شُجّ وجه النبي ﷺ وكُسرت رَباعيّته'},
    {"q": 'من هي أول زوجات النبي ﷺ؟', "options": ['خديجة بنت خويلد', 'حفصة', 'عائشة', 'زينب بنت جحش'], "answer": 'خديجة بنت خويلد', "explain": 'خديجة رضي الله عنها أول زوجات النبي ﷺ'},
    {"q": 'ما اسم جدّ النبي ﷺ الذي رعاه؟', "options": ['عبدالله', 'عبدالمطلب', 'أبو طالب', 'الزبير'], "answer": 'عبدالمطلب', "explain": 'عبدالمطلب رعى النبي ﷺ بعد وفاة أمه'},
    {"q": 'من هو الصحابي الملقب بسيف الله المسلول؟', "options": ['عمرو بن العاص', 'سعد بن أبي وقاص', 'خالد بن الوليد', 'أبو عبيدة'], "answer": 'خالد بن الوليد', "explain": 'لقّبه النبي ﷺ بسيف الله المسلول'},
    {"q": 'من هو أول مؤذن في الإسلام؟', "options": ['عبدالله بن زيد', 'بلال بن رباح', 'أبو محذورة', 'سعد القرظ'], "answer": 'بلال بن رباح', "explain": 'بلال بن رباح رضي الله عنه هو أول مؤذن في الإسلام'},
    {"q": 'من هو الصحابي الملقب بالفاروق؟', "options": ['أبو بكر', 'علي', 'عثمان', 'عمر بن الخطاب'], "answer": 'عمر بن الخطاب', "explain": 'لُقّب عمر بالفاروق لأن الله فرّق به بين الحق والباطل'},
    {"q": 'من هو الصحابي الملقب بذي النورين؟', "options": ['عثمان بن عفان', 'أبو بكر', 'علي بن أبي طالب', 'طلحة'], "answer": 'عثمان بن عفان', "explain": 'لُقّب بذي النورين لأنه تزوج بنتين للنبي ﷺ'},
    {"q": 'من هو الصحابي الذي بكى النبي ﷺ حين سمع قراءته؟', "options": ['أبو موسى الأشعري', 'معاذ بن جبل', 'أبي بن كعب', 'عبدالله بن مسعود'], "answer": 'عبدالله بن مسعود', "explain": 'بكى النبي ﷺ حين سمع قراءة ابن مسعود للقرآن'},
    {"q": 'من هو الصحابي الملقب بحواري رسول الله؟', "options": ['أبو بكر', 'سعد بن أبي وقاص', 'الزبير بن العوام', 'طلحة بن عبيدالله'], "answer": 'الزبير بن العوام', "explain": 'قال النبي ﷺ: إن لكل نبي حوارياً وحواريّ الزبير'},
    {"q": 'أكمل الحديث: إنما الأعمال...', "options": ['بالإخلاص', 'بالنيات', 'بالقلوب', 'بالإيمان'], "answer": 'بالنيات', "explain": 'الحديث: إنما الأعمال بالنيات وإنما لكل امرئ ما نوى'},
    {"q": 'أكمل الحديث: لا يؤمن أحدكم حتى يحب لأخيه...', "options": ['ما يحب لنفسه', 'الخير والهدى', 'ما يحب لربه', 'الجنة والنعيم'], "answer": 'ما يحب لنفسه', "explain": 'رواه البخاري ومسلم — من أصول الإيمان'},
    {"q": 'أكمل الحديث: المسلم من سلم المسلمون من...', "options": ['قلبه ونيته', 'ظلمه وجوره', 'كلامه وفعله', 'لسانه ويده'], "answer": 'لسانه ويده', "explain": 'رواه البخاري — من جوامع كلمه ﷺ'},
    {"q": 'أكمل الحديث: من كان يؤمن بالله واليوم الآخر فليقل...', "options": ['لا إله إلا الله', 'خيراً أو ليصمت', 'الحمد لله', 'سبحان الله'], "answer": 'خيراً أو ليصمت', "explain": 'رواه البخاري ومسلم — حثّ على صون اللسان'},
    {"q": 'أكمل الحديث: بُني الإسلام على خمس شهادة أن لا إله إلا الله...', "options": ['وإقام الصلاة وإيتاء الزكاة وصوم رمضان وحج البيت', 'والجهاد والصبر والتوكل', 'والصلاة والزكاة والصبر والحج', 'والصوم والحج والصدق والأمانة'], "answer": 'وإقام الصلاة وإيتاء الزكاة وصوم رمضان وحج البيت', "explain": 'حديث ابن عمر رضي الله عنهما في الصحيحين'},
    {"q": 'أكمل الآية: إن مع العسر...', "options": ['فرجاً قريباً', 'نصراً مبيناً', 'يُسرا', 'رحمةً واسعة'], "answer": 'يُسرا', "explain": 'سورة الشرح آية 6 — بُشرى بأن مع العسر يُسراً'},
    {"q": 'أكمل الآية: وما توفيقي إلا...', "options": ['بالصبر', 'بالإيمان', 'بالله', 'من عند الله'], "answer": 'بالله', "explain": 'سورة هود آية 88 — قالها شعيب عليه السلام'},
    {"q": 'أكمل الآية: ألا بذكر الله تطمئن...', "options": ['الأرواح', 'النفوس', 'العقول', 'القلوب'], "answer": 'القلوب', "explain": 'سورة الرعد آية 28 — من أعظم آيات القرآن'},
    {"q": 'أكمل الآية: فإذا عزمت فتوكل على...', "options": ['ربك وحده', 'الله', 'نفسك', 'العقل والحكمة'], "answer": 'الله', "explain": 'سورة آل عمران آية 159'},
    {"q": 'ما معنى كلمة الفلاح في القرآن؟', "options": ['النجاح والفوز', 'الرزق الوفير', 'الصبر والتحمل', 'العبادة الدائمة'], "answer": 'النجاح والفوز', "explain": 'الفلاح يعني النجاح والفوز بالجنة والنجاة من النار'},
    {"q": 'ما معنى كلمة القنوت في القرآن؟', "options": ['الطاعة والخشوع', 'الصمت التام', 'الصيام', 'الدعاء فقط'], "answer": 'الطاعة والخشوع', "explain": 'القنوت يعني الطاعة الكاملة والخشوع لله'},
    {"q": 'كم عدد تكبيرات صلاة الجنازة؟', "options": ['3', '4', '5', '6'], "answer": '4', "explain": 'صلاة الجنازة أربع تكبيرات بلا ركوع ولا سجود'},
    {"q": 'ما حكم صيام يوم العيدين؟', "options": ['مستحب', 'مكروه', 'جائز', 'حرام'], "answer": 'حرام', "explain": 'نهى النبي ﷺ عن صيام يوم الفطر ويوم الأضحى'},
    {"q": 'ما نصاب زكاة الذهب بالجرامات تقريباً؟', "options": ['50 جرام', '70 جرام', '85 جرام', '100 جرام'], "answer": '85 جرام', "explain": 'نصاب زكاة الذهب 85 جراماً إذا حال عليها الحول'},
    {"q": 'كم مرة تُطاف الكعبة في الطواف؟', "options": ['5 أشواط', '6 أشواط', '8 أشواط', '7 أشواط'], "answer": '7 أشواط', "explain": 'الطواف حول الكعبة سبعة أشواط'},
    {"q": 'ما الذي ينقض الوضوء باتفاق الفقهاء؟', "options": ['خروج الريح', 'الأكل', 'الضحك', 'النوم جالساً'], "answer": 'خروج الريح', "explain": 'خروج شيء من السبيلين ينقض الوضوء باتفاق'},
    {"q": 'من هو أول خليفة في الإسلام؟', "options": ['عمر بن الخطاب', 'علي بن أبي طالب', 'أبو بكر الصديق', 'عثمان بن عفان'], "answer": 'أبو بكر الصديق', "explain": 'أبو بكر الصديق أول خليفة للمسلمين بعد وفاة النبي ﷺ'},
    {"q": 'من هو الخليفة الذي فتح بيت المقدس؟', "options": ['أبو بكر', 'عمر بن الخطاب', 'علي', 'عثمان'], "answer": 'عمر بن الخطاب', "explain": 'فتح عمر رضي الله عنه بيت المقدس عام 637م'},
    {"q": 'في أي عام فُتحت مكة المكرمة هجرياً؟', "options": ['6هـ', '8هـ', '7هـ', '9هـ'], "answer": '8هـ', "explain": 'فُتحت مكة في رمضان السنة الثامنة للهجرة'},
    {"q": 'من هو أول شهيد في الإسلام؟', "options": ['بلال بن رباح', 'ياسر بن عامر', 'عمار بن ياسر', 'سمية بنت خياط'], "answer": 'سمية بنت خياط', "explain": 'سمية بنت خياط أم عمار — أول شهيدة في الإسلام'},
    {"q": 'من هو باني الكعبة المشرفة؟', "options": ['نوح وإدريس', 'محمد ﷺ وصحابته', 'إبراهيم وإسماعيل', 'آدم وحده'], "answer": 'إبراهيم وإسماعيل', "explain": 'قال تعالى: وإذ يرفع إبراهيم القواعد من البيت وإسماعيل'},
    {"q": 'ما لقب النبي إبراهيم عليه السلام؟', "options": ['خليل الله', 'كليم الله', 'نبي الله', 'روح الله'], "answer": 'خليل الله', "explain": 'قال تعالى: واتخذ الله إبراهيم خليلاً'},
    {"q": 'ما لقب النبي موسى عليه السلام؟', "options": ['خليل الله', 'كليم الله', 'روح الله', 'نجي الله'], "answer": 'كليم الله', "explain": 'كلّم الله موسى تكليماً مباشراً فلُقّب بكليم الله'},
    {"q": 'ما لقب النبي عيسى عليه السلام في القرآن؟', "options": ['خليل الله', 'كليم الله', 'صفي الله', 'روح الله وكلمته'], "answer": 'روح الله وكلمته', "explain": 'قال تعالى: إنما المسيح عيسى ابن مريم رسول الله وكلمته وروح منه'},
    {"q": 'من هو النبي الملقب بأبي البشر؟', "options": ['آدم', 'إبراهيم', 'نوح', 'محمد ﷺ'], "answer": 'آدم', "explain": 'آدم عليه السلام أبو البشرية كلها'},
    {"q": 'كم جزءاً في القرآن الكريم؟', "options": ['25', '28', '30', '32'], "answer": '30', "explain": 'القرآن الكريم مقسّم إلى 30 جزءاً'},
    {"q": 'ما هي أقصر سورة في القرآن؟', "options": ['الفاتحة', 'الناس', 'الفلق', 'الكوثر'], "answer": 'الكوثر', "explain": 'سورة الكوثر أقصر سورة في القرآن بثلاث آيات فقط'},
    {"q": 'كم مرة ذُكر اسم محمد ﷺ في القرآن؟', "options": ['2', '3', '4', '5'], "answer": '4', "explain": 'ذُكر اسم محمد ﷺ أربع مرات في القرآن الكريم'},
    {"q": 'في أي يوم خُلق آدم عليه السلام؟', "options": ['الاثنين', 'الجمعة', 'الأربعاء', 'السبت'], "answer": 'الجمعة', "explain": 'قال النبي ﷺ: خُلق آدم يوم الجمعة'},
    {"q": 'كم باباً للجنة؟', "options": ['8', '7', '6', '9'], "answer": '8', "explain": 'للجنة ثمانية أبواب منها باب الريّان لأهل الصيام'},
    {"q": 'كم باباً للنار؟', "options": ['7', '6', '5', '8'], "answer": '7', "explain": 'قال تعالى: لها سبعة أبواب لكل باب منهم جزء مقسوم'},
    {"q": 'ما هو الذكر الأثقل في الميزان؟', "options": ['لا إله إلا الله', 'سبحان الله وبحمده سبحان الله العظيم', 'الحمد لله رب العالمين', 'الله أكبر كبيراً'], "answer": 'سبحان الله وبحمده سبحان الله العظيم', "explain": 'قال النبي ﷺ: كلمتان خفيفتان على اللسان ثقيلتان في الميزان'},
    {"q": 'من هو الملك الموكّل بالوحي؟', "options": ['ميكائيل', 'إسرافيل', 'جبريل', 'عزرائيل'], "answer": 'جبريل', "explain": 'جبريل عليه السلام هو أمين الوحي'},
    {"q": 'ما هي السورة التي تُقرأ على المحتضر؟', "options": ['الفاتحة', 'البقرة', 'الرحمن', 'يس'], "answer": 'يس', "explain": 'قال النبي ﷺ: اقرأوا على موتاكم يس'},
    {"q": 'في أي سنة وقعت غزوة بدر الكبرى؟', "options": ['2هـ', '1هـ', '3هـ', '4هـ'], "answer": '2هـ', "explain": 'غزوة بدر كانت في 17 رمضان السنة الثانية للهجرة'},
    {"q": 'كم كان عدد المسلمين في غزوة بدر تقريباً؟', "options": ['100', '213', '313', '500'], "answer": '313', "explain": 'كان المسلمون 313 رجلاً في مقابل نحو 1000 من المشركين'},
    {"q": 'من هو الصحابي الذي سمّاه النبي ﷺ حب الله ورسوله؟', "options": ['عمر', 'علي بن أبي طالب', 'أبو بكر', 'أسامة بن زيد'], "answer": 'أسامة بن زيد', "explain": 'قال النبي ﷺ لأسامة: إنك لحبي وابن حبي'},
    {"q": 'ما اسم أول ولد وُلد للمهاجرين في المدينة؟', "options": ['عبدالله بن عمر', 'عبدالله بن الزبير', 'محمد بن علي', 'سالم بن أبي حذيفة'], "answer": 'عبدالله بن الزبير', "explain": 'كان المشركون يقولون لن يولد لهم فجاء عبدالله بن الزبير'},
    {"q": 'كم دامت دعوة النبي ﷺ في مكة قبل الهجرة؟', "options": ['13 سنة', '10 سنوات', '8 سنوات', '15 سنة'], "answer": '13 سنة', "explain": 'مكث النبي ﷺ في مكة يدعو 13 سنة قبل الهجرة'},
    {"q": 'ما هي السورة التي تُسمى قلب القرآن؟', "options": ['الفاتحة', 'البقرة', 'الكهف', 'يس'], "answer": 'يس', "explain": 'قال النبي ﷺ: إن لكل شيء قلباً وقلب القرآن يس'},
    {"q": 'كم آية في سورة الفاتحة؟', "options": ['5', '6', '7', '8'], "answer": '7', "explain": 'سورة الفاتحة سبع آيات وهي السبع المثاني'},
    {"q": 'ما هي السورة التي من قرأها حُفظ من الدجال؟', "options": ['يس', 'الكهف', 'البقرة', 'الإخلاص'], "answer": 'الكهف', "explain": 'قال النبي ﷺ: من قرأ عشر آيات من سورة الكهف عُصم من الدجال'},
    {"q": 'كم حرفاً في البسملة؟', "options": ['17', '19', '18', '20'], "answer": '19', "explain": 'بسم الله الرحمن الرحيم تتكون من 19 حرفاً'},
    {"q": 'ما هو آخر ما نزل من القرآن كاملاً من السور؟', "options": ['المائدة', 'البقرة', 'التوبة', 'النصر'], "answer": 'النصر', "explain": 'سورة النصر آخر ما نزل كاملاً وفيها إشارة لوفاة النبي ﷺ'},
    {"q": 'أكمل الآية: وقل رب زدني...', "options": ['رزقاً', 'صبراً', 'علماً', 'هدىً'], "answer": 'علماً', "explain": 'سورة طه آية 114 — الدعاء بالعلم'},
    {"q": 'أكمل الآية: حسبنا الله ونعم...', "options": ['الوكيل', 'المولى', 'الرحيم', 'الحفيظ'], "answer": 'الوكيل', "explain": 'سورة آل عمران — قالها إبراهيم حين أُلقي في النار وقالها النبي ﷺ'},
    {"q": 'معنى كلمة التوكل في القرآن؟', "options": ['التسليم للقضاء فقط', 'ترك العمل', 'الاعتماد على الله مع الأخذ بالأسباب', 'الصبر على البلاء'], "answer": 'الاعتماد على الله مع الأخذ بالأسباب', "explain": 'التوكل هو صدق الاعتماد على الله مع بذل الأسباب'},
    {"q": 'معنى كلمة الصراط في القرآن؟', "options": ['الجسر', 'الميزان', 'السبيل الضيق', 'الطريق'], "answer": 'الطريق', "explain": 'الصراط يعني الطريق الواضح المستقيم'},
    {"q": 'أكمل الحديث: خير الناس أنفعهم...', "options": ['للناس', 'لأهلهم', 'لدينهم', 'لربهم'], "answer": 'للناس', "explain": 'قال النبي ﷺ: خير الناس أنفعهم للناس — رواه الطبراني'},
    {"q": 'أكمل الحديث: الدنيا سجن المؤمن وجنة...', "options": ['العاصي', 'الكافر', 'المنافق', 'الجاحد'], "answer": 'الكافر', "explain": 'رواه مسلم — يعني المؤمن يصبر في الدنيا وينعم في الآخرة'},
    {"q": 'أكمل الحديث: من صام رمضان إيماناً واحتساباً غُفر له...', "options": ['ذنبه كله', 'ذنوب يوم وليلة', 'ما تقدم من ذنبه', 'كبائر ذنبه'], "answer": 'ما تقدم من ذنبه', "explain": 'متفق عليه — فضل صيام رمضان'},
    {"q": 'أكمل الحديث: تبسّمك في وجه أخيك...', "options": ['صدقة', 'من الإيمان', 'من الإحسان', 'نور'], "answer": 'صدقة', "explain": 'رواه الترمذي — حثّ على إظهار البشاشة'},
    {"q": 'أكمل الحديث: كل ابن آدم خطّاء وخير الخطّائين...', "options": ['من استغفر', 'التوّابون', 'من تاب', 'الصابرون'], "answer": 'التوّابون', "explain": 'رواه الترمذي وابن ماجه — حثّ على التوبة'},
    {"q": 'ما شروط قبول العبادة؟', "options": ['الإخلاص فقط', 'المتابعة فقط', 'النية والخشوع', 'الإخلاص لله والمتابعة للنبي ﷺ'], "answer": 'الإخلاص لله والمتابعة للنبي ﷺ', "explain": 'لا تُقبل العبادة إلا بشرطين: الإخلاص والمتابعة'},
    {"q": 'ما حكم صلاة الجمعة؟', "options": ['سنة مؤكدة', 'فرض عين على الرجال', 'فرض كفاية', 'مستحبة'], "answer": 'فرض عين على الرجال', "explain": 'صلاة الجمعة فرض عين على كل مسلم بالغ حر مقيم'},
    {"q": 'ما هي أركان الصلاة؟', "options": ['النية والتكبير فقط', 'القيام والركوع والسجود فقط', 'خمسة أركان فقط', 'النية والتكبير والقراءة والركوع والسجود والتشهد والتسليم'], "answer": 'النية والتكبير والقراءة والركوع والسجود والتشهد والتسليم', "explain": 'أركان الصلاة سبعة وبدونها لا تصح'},
    {"q": 'ما الفرق بين الركن والواجب في الصلاة؟', "options": ['ترك الركن يُبطل الصلاة وترك الواجب يُوجب سجود السهو', 'لا فرق', 'الواجب أهم من الركن', 'الركن يُقضى والواجب لا'], "answer": 'ترك الركن يُبطل الصلاة وترك الواجب يُوجب سجود السهو', "explain": 'الركن لا تصح الصلاة بدونه والواجب يُجبر بسجود السهو'},
    {"q": 'ما هي النجاسة التي لا تطهر بالغسل؟', "options": ['الدم', 'البول', 'الكلب في الملاقاة', 'المني'], "answer": 'الكلب في الملاقاة', "explain": 'يُغسل الإناء من ولوغ الكلب سبعاً إحداهن بالتراب'},
    {"q": 'من هو المعروف بـ ذي القرنين في التاريخ الإسلامي؟', "options": ['الإسكندر المقدوني', 'كورش الكبير', 'نبي من الأنبياء', 'رجل صالح ذكره القرآن'], "answer": 'رجل صالح ذكره القرآن', "explain": 'ذو القرنين مذكور في سورة الكهف وهو رجل صالح ملّكه الله في الأرض'},
    {"q": 'ما هي أول دولة إسلامية تعترف بالإسلام رسمياً؟', "options": ['فارس', 'الروم', 'الحبشة', 'اليمن'], "answer": 'الحبشة', "explain": 'آوى النجاشي ملك الحبشة المسلمين وعدل بينهم واعترف بالإسلام'},
    {"q": 'من أول من هاجر إلى الحبشة؟', "options": ['جعفر بن أبي طالب', 'عثمان بن عفان', 'الزبير بن العوام', 'عبدالرحمن بن عوف'], "answer": 'عثمان بن عفان', "explain": 'هاجر عثمان وزوجته رقية بنت النبي ﷺ في أول هجرة للحبشة'},
    {"q": 'ما اسم قائد جيش المسلمين في معركة اليرموك؟', "options": ['خالد بن الوليد', 'عمرو بن العاص', 'سعد بن أبي وقاص', 'أبو عبيدة بن الجراح'], "answer": 'خالد بن الوليد', "explain": 'قاد خالد بن الوليد المسلمين في معركة اليرموك الفاصلة'},
    {"q": 'كم سنة كان يوسف عليه السلام في السجن؟', "options": ['3 سنوات', '7 سنوات', '5 سنوات', '10 سنوات'], "answer": '7 سنوات', "explain": 'قيل إن يوسف مكث في السجن سبع سنوات بعد إغواء امرأة العزيز'},
    {"q": 'ما هو المعجزة الكبرى التي أُعطيها موسى عليه السلام؟', "options": ['إحياء الموتى', 'شفاء الأكمه', 'الكلام مع الله مباشرة', 'العصا التي تنقلب حية'], "answer": 'العصا التي تنقلب حية', "explain": 'من أعظم معجزات موسى العصا التي تنقلب ثعباناً وتلقف سحر السحرة'},
    {"q": 'ما هو الجبل الذي كلّم الله عليه موسى؟', "options": ['جبل الطور', 'جبل حراء', 'جبل عرفات', 'جبل أُحد'], "answer": 'جبل الطور', "explain": 'قال تعالى: وناديناه من جانب الطور الأيمن — على جبل الطور'},
    {"q": 'من هو النبي الذي أُوتي الزبور؟', "options": ['إبراهيم', 'موسى', 'داود', 'سليمان'], "answer": 'داود', "explain": 'قال تعالى: وآتينا داود زبوراً'},
    {"q": 'كم نبياً ذُكر في سورة الأنبياء؟', "options": ['10', '14', '18', '16'], "answer": '16', "explain": 'ذُكر في سورة الأنبياء ستة عشر نبياً من الأنبياء الكرام'},
    {"q": 'ما هو الدعاء المستجاب بين الأذان والإقامة؟', "options": ['اللهم رب هذه الدعوة التامة', 'الدعاء في هذا الوقت لا يُرد', 'لا إله إلا الله وحده', 'ربنا لك الحمد'], "answer": 'الدعاء في هذا الوقت لا يُرد', "explain": 'قال النبي ﷺ: الدعاء لا يُرد بين الأذان والإقامة'},
    {"q": 'ما هي ليلة القدر؟', "options": ['إحدى ليالي العشر الأخيرة من رمضان', 'ليلة 27 رمضان فقط', 'أول ليلة رمضان', 'ليلة النصف من شعبان'], "answer": 'إحدى ليالي العشر الأخيرة من رمضان', "explain": 'قال النبي ﷺ: التمسوا ليلة القدر في العشر الأواخر من رمضان'},
    {"q": 'ما هو أفضل الذكر؟', "options": ['الحمد لله', 'سبحان الله', 'لا إله إلا الله', 'الله أكبر'], "answer": 'لا إله إلا الله', "explain": 'قال النبي ﷺ: أفضل الذكر لا إله إلا الله'},
    {"q": 'كم عدد الصلوات المفروضة في اليوم؟', "options": ['5', '4', '3', '6'], "answer": '5', "explain": 'فُرضت خمس صلوات ليلة المعراج وهي الفريضة اليومية'},
    {"q": 'ما هو الوضوء الكامل كم مرة لكل عضو؟', "options": ['مرة واحدة', 'ثلاث مرات', 'مرتان', 'حسب العضو'], "answer": 'ثلاث مرات', "explain": 'السنة غسل كل عضو ثلاث مرات والواجب مرة واحدة'},
    {"q": 'ما هو اسم صلاة الاستسقاء؟', "options": ['صلاة الاستخارة', 'صلاة الحاجة', 'صلاة طلب المطر', 'صلاة التهجد'], "answer": 'صلاة طلب المطر', "explain": 'صلاة الاستسقاء صلاة مشروعة لطلب المطر من الله'},
    {"q": 'ما هو الفرق بين النبي والرسول؟', "options": ['لا فرق بينهما', 'الرسول بشر فقط والنبي قد يكون ملكاً', 'النبي أفضل من الرسول', 'الرسول أُوحي إليه بشريعة جديدة والنبي يتبع شريعة من قبله'], "answer": 'الرسول أُوحي إليه بشريعة جديدة والنبي يتبع شريعة من قبله', "explain": 'الرسول أُرسل بشريعة جديدة وكتاب، والنبي يُبلّغ شريعة من قبله'},
]
    return []


def get_active_session(chat_id: int) -> dict | None:
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT session_id, status, current_q, total_q, created_by FROM quiz_sessions WHERE chat_id=? AND status != 'finished' ORDER BY session_id DESC LIMIT 1",
            (chat_id,)
        ).fetchone()
    if row:
        return {"session_id": row[0], "status": row[1], "current_q": row[2], "total_q": row[3], "created_by": row[4]}
    return None


def create_session(chat_id: int, user_id: int, total_q: int = 10) -> int:
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute(
            "INSERT INTO quiz_sessions (chat_id, status, current_q, total_q, started_at, created_by) VALUES (?,?,?,?,?,?)",
            (chat_id, "waiting", 0, total_q, datetime.datetime.now().isoformat(), user_id)
        )
        return cur.lastrowid


def join_session(session_id: int, user_id: int, username: str, full_name: str) -> bool:
    with sqlite3.connect(DB_PATH) as conn:
        exists = conn.execute(
            "SELECT id FROM quiz_participants WHERE session_id=? AND user_id=?",
            (session_id, user_id)
        ).fetchone()
        if exists:
            return False
        conn.execute(
            "INSERT INTO quiz_participants (session_id, user_id, username, full_name, score, joined_at) VALUES (?,?,?,?,0,?)",
            (session_id, user_id, username or "", full_name or "مجهول", datetime.datetime.now().isoformat())
        )
        return True


def get_participants(session_id: int) -> list:
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT user_id, full_name, score FROM quiz_participants WHERE session_id=? ORDER BY score DESC",
            (session_id,)
        ).fetchall()
    return [{"user_id": r[0], "full_name": r[1], "score": r[2]} for r in rows]


def has_answered(session_id: int, question_index: int, user_id: int) -> bool:
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT id FROM quiz_answers WHERE session_id=? AND question_index=? AND user_id=?",
            (session_id, question_index, user_id)
        ).fetchone()
    return row is not None


def record_answer(session_id: int, question_index: int, user_id: int, answer: str, is_correct: bool):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO quiz_answers (session_id, question_index, user_id, answer, is_correct, answered_at) VALUES (?,?,?,?,?,?)",
            (session_id, question_index, user_id, answer, 1 if is_correct else 0, datetime.datetime.now().isoformat())
        )
        if is_correct:
            conn.execute(
                "UPDATE quiz_participants SET score = score + 1 WHERE session_id=? AND user_id=?",
                (session_id, user_id)
            )


def update_session_status(session_id: int, status: str, current_q: int = None):
    with sqlite3.connect(DB_PATH) as conn:
        if current_q is not None:
            conn.execute(
                "UPDATE quiz_sessions SET status=?, current_q=? WHERE session_id=?",
                (status, current_q, session_id)
            )
        else:
            conn.execute(
                "UPDATE quiz_sessions SET status=? WHERE session_id=?",
                (status, session_id)
            )


def finish_session(session_id: int):
    update_session_status(session_id, "finished")


# ─── الأسئلة ──────────────────────────────────────────
# ─── لوحة المتصدرين ───────────────────────────────────
def build_leaderboard(session_id: int) -> str:
    participants = get_participants(session_id)
    if not participants:
        return "لا يوجد مشاركون"
    medals = ["🥇", "🥈", "🥉"]
    text = "🏆 *لوحة المتصدرين*\n━━━━━━━━━━━━━━━\n\n"
    for i, p in enumerate(participants):
        medal = medals[i] if i < 3 else f"{i+1}."
        text += f"{medal} {p['full_name']} — {p['score']} نقطة\n"
    return text


# ─── إرسال سؤال ───────────────────────────────────────
async def send_question(context: ContextTypes.DEFAULT_TYPE, chat_id: int, session_id: int, q_index: int, questions: list):
    if q_index >= len(questions):
        # انتهت الأسئلة
        finish_session(session_id)
        leaderboard = build_leaderboard(session_id)
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"🎉 *انتهت المسابقة!*\n\n{leaderboard}",
            parse_mode="Markdown"
        )
        return

    q = questions[q_index]
    opts = q["options"]
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(opts[0], callback_data=f"cqa_{session_id}_{q_index}_0"),
         InlineKeyboardButton(opts[1], callback_data=f"cqa_{session_id}_{q_index}_1")],
        [InlineKeyboardButton(opts[2], callback_data=f"cqa_{session_id}_{q_index}_2"),
         InlineKeyboardButton(opts[3], callback_data=f"cqa_{session_id}_{q_index}_3")],
    ])
    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            f"❓ *سؤال {q_index + 1}/{len(questions)}*\n"
            "━━━━━━━━━━━━━━━\n\n"
            f"*{q['q']}*\n\n"
            "⏰ لديك 30 ثانية للإجابة"
        ),
        parse_mode="Markdown",
        reply_markup=kb
    )
    update_session_status(session_id, "active", q_index)

    # جدول انتقال السؤال التالي بعد 30 ثانية
    context.job_queue.run_once(
        next_question_job,
        when=30,
        data={"chat_id": chat_id, "session_id": session_id, "q_index": q_index, "questions": questions},
        name=f"quiz_{session_id}_{q_index}"
    )


# ─── أوامر ────────────────────────────────────────────
async def next_question_job(context: ContextTypes.DEFAULT_TYPE):
    """يُشغَّل بعد 30 ثانية للانتقال للسؤال التالي"""
    data = context.job.data
    chat_id = data["chat_id"]
    session_id = data["session_id"]
    q_index = data["q_index"]
    questions = data["questions"]

    # تحقق إذا الجلسة لسا شغّالة
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT status FROM quiz_sessions WHERE session_id=?",
            (session_id,)
        ).fetchone()

    if not row or row[0] == "finished":
        return

    q = questions[q_index]
    # أرسل الإجابة الصحيحة
    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"✅ *الإجابة الصحيحة:* {q['answer']}\n📖 {q.get('explain', '')}",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"خطأ إرسال إجابة: {e}")

    await asyncio.sleep(3)
    await send_question(context, chat_id, session_id, q_index + 1, questions)


async def cmd_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بدء مسابقة جماعية"""
    chat = update.effective_chat
    user = update.effective_user

    if chat.type == "private":
        await update.message.reply_text("⚠️ هذا الأمر للقنوات والمجموعات فقط!")
        return

    # تحقق إذا في جلسة نشطة
    existing = get_active_session(chat.id)
    if existing:
        await update.message.reply_text("⚠️ يوجد مسابقة نشطة الآن! انتظر حتى تنتهي.")
        return

    # أنشئ جلسة جديدة
    session_id = create_session(chat.id, user.id)

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✋ انضمام للمسابقة", callback_data=f"cq_join_{session_id}")],
        [InlineKeyboardButton("🚀 بدء المسابقة", callback_data=f"cq_start_{session_id}")],
        [InlineKeyboardButton("❌ إلغاء", callback_data=f"cq_cancel_{session_id}")],
    ])

    await update.message.reply_text(
        "🏆 *مسابقة إسلامية جماعية*\n"
        "━━━━━━━━━━━━━━━\n\n"
        "📋 10 أسئلة في الفقه والتفسير والسيرة\n"
        "⏰ 30 ثانية لكل سؤال\n"
        "⭐ كل إجابة صحيحة = نقطة\n\n"
        "اضغط **انضمام** للمشاركة\n"
        "ثم اضغط **بدء** لبدء الأسئلة 👇",
        parse_mode="Markdown",
        reply_markup=kb
    )


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    user = q.from_user
    data = q.data

    # ─── انضمام ───
    if data.startswith("cq_join_"):
        session_id = int(data.split("_")[2])
        session = get_active_session(q.message.chat.id)
        if not session or session["status"] != "waiting":
            await q.answer("⚠️ المسابقة بدأت أو انتهت!", show_alert=True)
            return
        joined = join_session(session_id, user.id, user.username, user.full_name)
        if joined:
            await q.answer(f"✅ انضممت للمسابقة!", show_alert=True)
            participants = get_participants(session_id)
            names = "\n".join([f"• {p['full_name']}" for p in participants])
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton(f"✋ انضمام ({len(participants)})", callback_data=f"cq_join_{session_id}")],
                [InlineKeyboardButton("🚀 بدء المسابقة", callback_data=f"cq_start_{session_id}")],
                [InlineKeyboardButton("❌ إلغاء", callback_data=f"cq_cancel_{session_id}")],
            ])
            try:
                await q.edit_message_text(
                    "🏆 *مسابقة إسلامية جماعية*\n"
                    "━━━━━━━━━━━━━━━\n\n"
                    f"👥 *المشاركون ({len(participants)}):*\n{names}\n\n"
                    "اضغط **بدء** للبدء 👇",
                    parse_mode="Markdown",
                    reply_markup=kb
                )
            except Exception:
                pass
        else:
            await q.answer("أنت مسجّل مسبقاً! ✅", show_alert=True)

    # ─── بدء ───
    elif data.startswith("cq_start_"):
        session_id = int(data.split("_")[2])
        session = get_active_session(q.message.chat.id)
        if not session:
            await q.answer("⚠️ الجلسة غير موجودة!", show_alert=True)
            return
        # فقط المشرف أو من أنشأ المسابقة
        if user.id != session["created_by"] and user.id not in ADMIN_IDS:
            await q.answer("⚠️ فقط من أنشأ المسابقة يمكنه البدء!", show_alert=True)
            return
        if session["status"] != "waiting":
            await q.answer("⚠️ المسابقة بدأت مسبقاً!", show_alert=True)
            return
        participants = get_participants(session_id)
        if len(participants) < 1:
            await q.answer("⚠️ لا يوجد مشاركون! اطلب من الأعضاء الانضمام أولاً.", show_alert=True)
            return

        await q.answer("🚀 بدأت المسابقة!")
        try:
            await q.edit_message_text(
                f"🚀 *بدأت المسابقة!*\n\nعدد المشاركين: {len(participants)}\nعدد الأسئلة: 10\n\nاستعدوا! 💪",
                parse_mode="Markdown"
            )
        except Exception:
            pass

        questions = random.sample(QUESTIONS, min(10, len(QUESTIONS)))
        save_session_questions(session_id, questions)
        update_session_status(session_id, "active", 0)
        await send_question(context, q.message.chat.id, session_id, 0, questions)

    # ─── إلغاء ───
    elif data.startswith("cq_cancel_"):
        session_id = int(data.split("_")[2])
        session = get_active_session(q.message.chat.id)
        if not session:
            await q.answer("لا توجد مسابقة نشطة!")
            return
        if user.id != session["created_by"] and user.id not in ADMIN_IDS:
            await q.answer("⚠️ فقط من أنشأ المسابقة يمكنه الإلغاء!", show_alert=True)
            return
        finish_session(session_id)
        await q.answer("تم إلغاء المسابقة")
        try:
            await q.edit_message_text("❌ تم إلغاء المسابقة.")
        except Exception:
            pass

    # ─── إجابة سؤال ───
    elif data.startswith("cqa_"):
        parts = data.split("_")
        session_id = int(parts[1])
        q_index = int(parts[2])
        answer_idx = int(parts[3])

        session = get_active_session(q.message.chat.id)
        if not session or session["status"] == "finished":
            await q.answer("⚠️ المسابقة انتهت!", show_alert=True)
            return

        if session["current_q"] != q_index:
            await q.answer("⚠️ هذا السؤال انتهى!", show_alert=True)
            return

        # تحقق إذا أجاب مسبقاً
        if has_answered(session_id, q_index, user.id):
            await q.answer("أجبت مسبقاً على هذا السؤال!", show_alert=True)
            return

        # تحقق إذا المستخدم مشارك
        participants = get_participants(session_id)
        participant_ids = [p["user_id"] for p in participants]
        if user.id not in participant_ids:
            # أضفه تلقائياً
            join_session(session_id, user.id, user.username, user.full_name)

        questions = load_session_questions(session_id) or QUESTIONS
        if q_index >= len(questions):
            await q.answer("⚠️ خطأ في السؤال!", show_alert=True)
            return

        q_data = questions[q_index]
        chosen = q_data["options"][answer_idx]
        correct = q_data["answer"]
        is_correct = chosen == correct

        record_answer(session_id, q_index, user.id, chosen, is_correct)

        if is_correct:
            await q.answer("✅ إجابة صحيحة! +1 نقطة 🌟", show_alert=True)
        else:
            await q.answer(f"❌ خطأ! الإجابة الصحيحة: {correct}", show_alert=True)


async def cmd_scores(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض النتائج الحالية"""
    chat = update.effective_chat
    session = get_active_session(chat.id)
    if not session:
        await update.message.reply_text("لا توجد مسابقة نشطة الآن.")
        return
    leaderboard = build_leaderboard(session["session_id"])
    await update.message.reply_text(leaderboard, parse_mode="Markdown")


async def cmd_stop_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إيقاف المسابقة"""
    chat = update.effective_chat
    user = update.effective_user
    session = get_active_session(chat.id)
    if not session:
        await update.message.reply_text("لا توجد مسابقة نشطة.")
        return
    if user.id != session["created_by"] and user.id not in ADMIN_IDS:
        await update.message.reply_text("⚠️ فقط من أنشأ المسابقة يمكنه إيقافها!")
        return
    finish_session(session["session_id"])
    leaderboard = build_leaderboard(session["session_id"])
    await update.message.reply_text(
        f"🛑 *تم إيقاف المسابقة*\n\n{leaderboard}",
        parse_mode="Markdown"
    )


# ─── main ─────────────────────────────────────────────
def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN غير موجود!")
        return

    init_db()
    logger.info("🚀 quiz_channel.py يشتغل...")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("quiz", cmd_quiz))
    app.add_handler(CommandHandler("scores", cmd_scores))
    app.add_handler(CommandHandler("stopquiz", cmd_stop_quiz))
    app.add_handler(CallbackQueryHandler(handle_callback))

    logger.info("✅ جاهز — /quiz لبدء مسابقة")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()