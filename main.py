import sqlite3
import time
import random
from datetime import datetime
import telebot
from telebot import types
from PIL import Image, ImageDraw, ImageFont
import arabic_reshaper
from bidi.algorithm import get_display
import os

# ---------------------------------------------------------
# 1. إعدادات البوت والبيانات الأساسية
# ---------------------------------------------------------
TOKEN = "8846764355:AAHf3xSNjLwv0v3Hmey53OQWd0BhJbnolTM"
ADMIN_ID = 1426318708  # معرف المشرف الخاص بك

bot = telebot.TeleBot(TOKEN)
IS_MAINTENANCE = False
user_states = {}

# قائمة المواد المطلوبة بالكامل (تمت إضافة التربية الإسلامية)
SUBJECTS = [
    "التربية الإسلامية",
    "اللغة العربية",
    "الانكليزي - كتاب الطالب",
    "الانكليزي - كتاب النشاط",
    "الرياضيات",
    "الفيزياء",
    "الكيمياء",
    "الأحياء",
    "الحاسوب",
    "جرائم حزب البعث"
]

# ---------------------------------------------------------
# 2. إعداد قاعدة البيانات (SQLite)
# ---------------------------------------------------------
def init_db():
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            full_name TEXT,
            student_code INTEGER,
            language TEXT DEFAULT 'ar',
            is_registered INTEGER DEFAULT 0,
            joined_at TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS books (
            subject_name TEXT PRIMARY KEY,
            file_id TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS content (
            key TEXT PRIMARY KEY,
            value TEXT,
            content_type TEXT DEFAULT 'text'
        )
    ''')
    # جدول الحظر
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS banned_users (
            user_id INTEGER PRIMARY KEY
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# --- وظائف قاعدة البيانات للحظر ---
def ban_user(user_id):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO banned_users (user_id) VALUES (?)", (user_id,))
    conn.commit()
    conn.close()

def unban_user(user_id):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM banned_users WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def is_banned(user_id):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM banned_users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row is not None

# --- باقي وظائف قاعدة البيانات ---
def get_user(user_id):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT full_name, language, is_registered, student_code FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row

def register_user(user_id, full_name):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    joined_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    student_code = random.randint(1000, 9999)
    cursor.execute('''
        INSERT OR REPLACE INTO users (user_id, full_name, student_code, language, is_registered, joined_at)
        VALUES (?, ?, ?, 'ar', 1, ?)
    ''', (user_id, full_name, student_code, joined_at))
    conn.commit()
    conn.close()
    return student_code

def set_user_lang(user_id, lang):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET language = ? WHERE user_id = ?", (lang, user_id))
    conn.commit()
    conn.close()

def set_content(key, value, c_type='text'):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO content (key, value, content_type) VALUES (?, ?, ?)", (key, value, c_type))
    conn.commit()
    conn.close()

def get_content(key):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT value, content_type FROM content WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    return row if row else (None, None)

def set_book(subject_name, file_id):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO books (subject_name, file_id) VALUES (?, ?)", (subject_name, file_id))
    conn.commit()
    conn.close()

def get_book(subject_name):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT file_id FROM books WHERE subject_name = ?", (subject_name,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None

def get_all_users():
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()
    conn.close()
    return [u[0] for u in users]

# ---------------------------------------------------------
# 3. تصميم وإنشاء باج الطالب
# ---------------------------------------------------------
def generate_student_badge(user_id, full_name, student_code):
    bg_path = "badge_bg.png"
    output_path = f"badge_{user_id}.png"
    
    if os.path.exists(bg_path):
        img = Image.open(bg_path)
    else:
        img = Image.new("RGB", (800, 450), color=(255, 255, 255))
        
    draw = ImageDraw.Draw(img)
    img_width, _ = img.size
    
    font_path = "arial.ttf" if os.path.exists("arial.ttf") else "Arial.ttf"
    if os.path.exists(font_path):
        font_name = ImageFont.truetype(font_path, 34)
        font_info = ImageFont.truetype(font_path, 30)
    else:
        font_name = ImageFont.load_default()
        font_info = ImageFont.load_default()

    issue_date = datetime.now().strftime("%Y/%m/%d")

    lines = [
        (f"اسم الطالب: {full_name}", font_name),
        (f"رقم الهوية: {student_code}", font_info),
        (f"تاريخ إصدار الهوية: {issue_date}", font_info)
    ]
    
    start_y = 280
    line_spacing = 50
    
    for idx, (text, font) in enumerate(lines):
        reshaped = arabic_reshaper.reshape(text)
        bidi_text = get_display(reshaped)
        
        bbox = draw.textbbox((0, 0), bidi_text, font=font)
        text_width = bbox[2] - bbox[0]
        x_position = (img_width - text_width) / 2
        y_position = start_y + (idx * line_spacing)
        
        draw.text((x_position, y_position), bidi_text, fill=(0, 0, 0), font=font)

    img.save(output_path)
    return output_path

# ---------------------------------------------------------
# 4. لوحات الأزرار
# ---------------------------------------------------------
def main_menu_keyboard(lang='ar', is_admin=False):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    if lang == 'ar':
        btn_schedule = types.KeyboardButton("🗓️ الجدول الأسبوعي")
        btn_books = types.KeyboardButton("📚 المناهج الدراسية")
        btn_homework = types.KeyboardButton("📝 التحاضير اليومية")
        btn_badge = types.KeyboardButton("🪪 باج الطالب (هويتي)")
        btn_lang = types.KeyboardButton("⚙️ تغيير اللغة")
        markup.add(btn_schedule, btn_books)
        markup.add(btn_homework, btn_badge)
        markup.add(btn_lang)
        if is_admin:
            markup.add(types.KeyboardButton("👑 لوحة المشرف"))
    else:
        btn_schedule = types.KeyboardButton("🗓️ Schedule")
        btn_books = types.KeyboardButton("📚 School Books")
        btn_homework = types.KeyboardButton("📝 Daily Homework")
        btn_badge = types.KeyboardButton("🪪 My Student ID")
        btn_lang = types.KeyboardButton("⚙️ Change Language")
        markup.add(btn_schedule, btn_books)
        markup.add(btn_homework, btn_badge)
        markup.add(btn_lang)
        if is_admin:
            markup.add(types.KeyboardButton("👑 Admin Panel"))
    return markup

def subjects_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    for sub in SUBJECTS:
        markup.add(types.KeyboardButton(f"📖 {sub}"))
    markup.add(types.KeyboardButton("🔙 العودة للقائمة الرئيسية"))
    return markup

def admin_menu_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(types.KeyboardButton("📤 رفع/تعديل كتاب"), types.KeyboardButton("📅 تعديل الجدول"))
    markup.add(types.KeyboardButton("📝 تعديل التحاضير"), types.KeyboardButton("📢 إذاعة للجميع"))
    markup.add(types.KeyboardButton("⛔ حظر طالب"), types.KeyboardButton("🟢 رفع حظر"))
    markup.add(types.KeyboardButton("🛠️ مفتاح الصيانة"), types.KeyboardButton("🔙 العودة للقائمة الرئيسية"))
    return markup

# ---------------------------------------------------------
# 5. معالجة الأوامر والرسائل
# ---------------------------------------------------------

@bot.message_handler(commands=['start'])
def start_cmd(message):
    user_id = message.from_user.id
    if is_banned(user_id):
        bot.send_message(user_id, "⛔ أنت محظور من استخدام هذا البوت.")
        return

    user_data = get_user(user_id)
    if not user_data or user_data[2] == 0:
        user_states[user_id] = 'waiting_full_name'
        bot.send_message(
            user_id,
            "أهلاً بك في البوت التعليمي! 🎓\n\nيرجى إرسال **اسمك الثلاثي الكامل** للتسجيل وإصدار هويتك الطلابية:"
        )
    else:
        lang = user_data[1]
        is_admin = (user_id == ADMIN_ID)
        bot.send_message(
            user_id,
            f"أهلاً بك مجدداً يا {user_data[0]}! 👋\nاختر من القائمة أدناه:",
            reply_markup=main_menu_keyboard(lang, is_admin)
        )

@bot.message_handler(func=lambda m: True, content_types=['text', 'document', 'photo', 'sticker', 'video', 'voice'])
def handle_all_messages(message):
    global IS_MAINTENANCE
    user_id = message.from_user.id

    # 1. فحص الحظر
    if is_banned(user_id):
        bot.send_message(user_id, "⛔ تم حظرك من استخدام البوت.")
        return

    user_data = get_user(user_id)
    text = message.text if message.text else ""
    
    # 2. إدخال الاسم
    if user_states.get(user_id) == 'waiting_full_name':
        full_name = text.strip()
        if len(full_name.split()) < 2:
            bot.send_message(user_id, "⚠️ يرجى كتابة الاسم الثنائي أو الثلاثي على الأقل:")
            return
            
        code = register_user(user_id, full_name)
        user_states[user_id] = None
        bot.send_message(user_id, "✅ تم تسجيل معلوماتك بنجاح! جاري إصدار هويتك...")
        
        badge_path = generate_student_badge(user_id, full_name, code)
        with open(badge_path, 'rb') as photo:
            bot.send_photo(user_id, photo, caption=f"🪪 بطاقة الطالب الخاصة بك:\n**{full_name}**\n**رقم الهوية:** `{code}`", parse_mode="Markdown")
        if os.path.exists(badge_path):
            os.remove(badge_path)
            
        bot.send_message(user_id, "مرحباً بك! اختر من القائمة أدناه:", reply_markup=main_menu_keyboard('ar', user_id == ADMIN_ID))
        return

    # فحص الصيانة
    if IS_MAINTENANCE and user_id != ADMIN_ID:
        bot.send_message(user_id, "⚠️ البوت قيد الصيانة حالياً، يرجى المحاولة لاحقاً.")
        return

    lang = user_data[1] if user_data else 'ar'
    is_admin = (user_id == ADMIN_ID)

    # 3. معالجة خيارات المشرف
    if is_admin:
        state = user_states.get(user_id)

        if text == "⛔ حظر طالب":
            user_states[user_id] = 'adm_wait_ban'
            bot.send_message(user_id, "أرسل الـ User ID الخاص بالطالب المراد حظره:")
            return

        elif state == 'adm_wait_ban':
            try:
                target_id = int(text.strip())
                ban_user(target_id)
                user_states[user_id] = None
                bot.send_message(user_id, f"✅ تم حظر الطالب صاحب المعرف `{target_id}` بنجاح!", reply_markup=admin_menu_keyboard())
            except ValueError:
                bot.send_message(user_id, "⚠️ يرجى إرسال رقم ID صحيح (أرقام فقط).")
            return

        elif text == "🟢 رفع حظر":
            user_states[user_id] = 'adm_wait_unban'
            bot.send_message(user_id, "أرسل الـ User ID الخاص بالطالب لإلغاء حظره:")
            return

        elif state == 'adm_wait_unban':
            try:
                target_id = int(text.strip())
                unban_user(target_id)
                user_states[user_id] = None
                bot.send_message(user_id, f"✅ تم رفع الحظر عن الطالب `{target_id}` بنجاح!", reply_markup=admin_menu_keyboard())
            except ValueError:
                bot.send_message(user_id, "⚠️ يرجى إرسال رقم ID صحيح (أرقام فقط).")
            return

        elif text == "📅 تعديل الجدول":
            user_states[user_id] = 'adm_wait_sch'
            bot.send_message(user_id, "أرسل الآن نص الجدول أو صورة الجدول الجديد:")
            return

        elif state == 'adm_wait_sch':
            if message.photo:
                set_content("schedule", message.photo[-1].file_id, "photo")
            else:
                set_content("schedule", text, "text")
            user_states[user_id] = None
            bot.send_message(user_id, "✅ تم تحديث الجدول الأسبوعي بنجاح!", reply_markup=admin_menu_keyboard())
            return

        elif text == "📝 تعديل التحاضير":
            user_states[user_id] = 'adm_wait_hw'
            bot.send_message(user_id, "أرسل نص أو صورة التحاضير والواجبات الجديدة:")
            return

        elif state == 'adm_wait_hw':
            if message.photo:
                set_content("homework", message.photo[-1].file_id, "photo")
            else:
                set_content("homework", text, "text")
            user_states[user_id] = None
            bot.send_message(user_id, "✅ تم تحديث التحاضير اليومية بنجاح!", reply_markup=admin_menu_keyboard())
            return

        elif text == "📢 إذاعة للجميع":
            user_states[user_id] = 'adm_wait_broadcast'
            bot.send_message(user_id, "📢 أرسل الرسالة الآن (نص، صورة، ملصق، أو ملف) لإذاعتها لجميع الطلاب:")
            return

        elif state == 'adm_wait_broadcast':
            user_states[user_id] = None
            users = get_all_users()
            success_count = 0
            bot.send_message(user_id, "⏳ جاري الإذاعة...")
            for u_id in users:
                try:
                    bot.copy_message(chat_id=u_id, from_chat_id=user_id, message_id=message.message_id)
                    success_count += 1
                    time.sleep(0.04)
                except Exception:
                    pass
            bot.send_message(user_id, f"✅ تمت الإذاعة بنجاح واستلمها {success_count} طالب.", reply_markup=admin_menu_keyboard())
            return

        elif text == "📤 رفع/تعديل كتاب":
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
            for sub in SUBJECTS:
                markup.add(types.KeyboardButton(f"رفع {sub}"))
            markup.add(types.KeyboardButton("🔙 العودة للقائمة الرئيسية"))
            bot.send_message(user_id, "اختر المادة التي تريد رفع/تحديث كتابها:", reply_markup=markup)
            return

        elif text.startswith("رفع "):
            subject_to_upload = text.replace("رفع ", "").strip()
            user_states[user_id] = f'adm_upload_{subject_to_upload}'
            bot.send_message(user_id, f"أرسل الآن ملف الـ PDF الخاص بـ ({subject_to_upload}):")
            return

        elif state and state.startswith('adm_upload_'):
            if message.document:
                sub_name = state.replace('adm_upload_', '')
                set_book(sub_name, message.document.file_id)
                user_states[user_id] = None
                bot.send_message(user_id, f"✅ تم حفظ وتحديث كتاب ({sub_name}) بنجاح!", reply_markup=admin_menu_keyboard())
            else:
                bot.send_message(user_id, "⚠️ يرجى إرسال ملف (Document/PDF).")
            return

        elif text == "🛠️ مفتاح الصيانة":
            IS_MAINTENANCE = not IS_MAINTENANCE
            status = "🔴 مفعلة" if IS_MAINTENANCE else "🟢 معطلة"
            bot.send_message(user_id, f"🛠️ حالة الصيانة الآن: {status}")
            return

    # 4. التنقل والقوائم العامة للطلاب
    if text in ["🔙 العودة للقائمة الرئيسية", "🔙 Back"]:
        user_states[user_id] = None
        bot.send_message(user_id, "القائمة الرئيسية 🏠", reply_markup=main_menu_keyboard(lang, is_admin))

    elif text in ["🗓️ الجدول الأسبوعي", "🗓️ Schedule"]:
        val, c_type = get_content("schedule")
        if not val:
            bot.send_message(user_id, "لم يتم إضافة الجدول الأسبوعي بعد.")
        elif c_type == 'photo':
            bot.send_photo(user_id, val, caption="🗓️ **الجدول الأسبوعي**", parse_mode="Markdown")
        else:
            bot.send_message(user_id, f"🗓️ **الجدول الأسبوعي:**\n\n{val}", parse_mode="Markdown")

    elif text in ["📝 التحاضير اليومية", "📝 Daily Homework"]:
        val, c_type = get_content("homework")
        if not val:
            bot.send_message(user_id, "لا توجد تحاضير يومية مضافة حالياً.")
        elif c_type == 'photo':
            bot.send_photo(user_id, val, caption="📝 **التحاضير اليومية**", parse_mode="Markdown")
        else:
            bot.send_message(user_id, f"📝 **التحاضير اليومية:**\n\n{val}", parse_mode="Markdown")

    elif text in ["📚 المناهج الدراسية", "📚 School Books"]:
        bot.send_message(user_id, "📚 اختر المادة التي تريد تحميل كتابها:", reply_markup=subjects_keyboard())

    elif text in ["🪪 باج الطالب (هويتي)", "🪪 My Student ID"]:
        if user_data:
            student_code = user_data[3] if user_data[3] else random.randint(1000, 9999)
            badge_path = generate_student_badge(user_id, user_data[0], student_code)
            with open(badge_path, 'rb') as photo:
                bot.send_photo(user_id, photo, caption=f"🪪 هوية الطالب: **{user_data[0]}**\n**رقم الهوية:** `{student_code}`", parse_mode="Markdown")
            if os.path.exists(badge_path):
                os.remove(badge_path)

    elif text in ["⚙️ تغيير اللغة", "⚙️ Change Language"]:
        new_lang = 'en' if lang == 'ar' else 'ar'
        set_user_lang(user_id, new_lang)
        msg = "Language changed to English! 🇬🇧" if new_lang == 'en' else "تم تغيير اللغة إلى العربية! 🇸🇦"
        bot.send_message(user_id, msg, reply_markup=main_menu_keyboard(new_lang, is_admin))

    elif text.startswith("📖 "):
        subject_name = text.replace("📖 ", "").strip()
        file_id = get_book(subject_name)
        if file_id:
            bot.send_document(user_id, file_id, caption=f"📖 كتاب: **{subject_name}**", parse_mode="Markdown")
        else:
            bot.send_message(user_id, f"⚠️ لم يتم رفع كتاب ({subject_name}) بعد من قبل الإدارة.")

    elif text in ["👑 لوحة المشرف", "👑 Admin Panel"] and is_admin:
        bot.send_message(user_id, "👑 أهلاً بك في لوحة تحكم المشرف:", reply_markup=admin_menu_keyboard())

# ---------------------------------------------------------
# 6. تشغيل البوت
# ---------------------------------------------------------
print("🤖 البوت التعليمي المطور يعمل الآن بالكامل وبدون مشاكل...")
bot.infinity_polling()
