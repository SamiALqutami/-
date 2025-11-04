import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

# 1. 🔑 المعلومات الأساسية للتنفيذ (التوكن والآي دي والقنوات)
TOKEN = "8575873020:AAHNyHAMf_Mls62kprIP7EMC_SqqruhD4s4"
OWNER_ID = 7834574830
# اسم مستخدم القناة بدون @، أو ID القناة السالب
FORCE_SUBSCRIBE_CHANNEL_USERNAME = "NN26S" 
OPTIONAL_CHANNEL_LINK = "https://t.me/SSAA100"

# تهيئة التسجيل (Logging)
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- حالة المستخدمين وقاعدة البيانات (للتوضيح فقط) ---
# تخزين مؤقت لبيانات المستخدمين وحالاتهم.
# يُفضل استبدال هذا بقاعدة بيانات فعلية (مثل SQLite) في بيئة الإنتاج.
user_data = {}  # {user_id: {'status': 'idle', 'partner_id': None, 'settings': {...}}}
waiting_queue = [] # قائمة بـ IDs المستخدمين المنتظرين للربط
current_chats = {} # {user1_id: user2_id, user2_id: user1_id}

# --- 2. 📝 تصميم الأزرار ولوحات المفاتيح ---

# لوحة المفاتيح الرئيسية (Reply Keyboard)
MAIN_KEYBOARD = [
    ["🚀 البحث عن شريك عشوائي", "🫆 القائمة"],
    ["🔋 الاعدادات", "🔗 Share account link"]
]
main_markup = ReplyKeyboardMarkup(MAIN_KEYBOARD, resize_keyboard=True)

# لوحة مفاتيح الإعدادات (Reply Keyboard)
SETTINGS_KEYBOARD = [
    ["1 👦 الجنس", "2 🌍 اللغة"],
    ["3 👶 العمر", "4 🚩 الموقع الجغرافي"],
    ["🫆 القائمة"]
]
settings_markup = ReplyKeyboardMarkup(SETTINGS_KEYBOARD, resize_keyboard=True)

# لوحة مفاتيح الدردشة (Reply Keyboard - عند العثور على شريك)
CHAT_KEYBOARD = [
    ["/next", "/stop"]
]
chat_markup = ReplyKeyboardMarkup(CHAT_KEYBOARD, resize_keyboard=True)

# --- 3. 🌐 وظائف مساعدة (التحقق من الاشتراك) ---

async def is_subscribed(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    """يتحقق مما إذا كان المستخدم مشتركاً في القناة الإجبارية."""
    try:
        # Get member returns the member object if subscribed, raises an error or returns specific status otherwise
        member = await context.bot.get_chat_member(f"@{FORCE_SUBSCRIBE_CHANNEL_USERNAME}", user_id)
        # States like 'member', 'administrator', 'creator' mean they are subscribed/part of the channel
        if member.status in ['member', 'administrator', 'creator']:
            return True
        else:
            return False
    except Exception as e:
        logger.error(f"Error checking subscription for {user_id}: {e}")
        # In case of error (e.g., bot not admin in channel, or channel is private and ID is used), assume not subscribed or handle
        return False

async def enforce_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """ينفذ التحقق من الاشتراك ويرسل رسالة التنبيه إذا لزم الأمر."""
    if update.effective_user:
        user_id = update.effective_user.id
        if not await is_subscribed(context, user_id):
            text = (
                f"🚫 **يجب عليك الاشتراك في القناة التالية لاستخدام البوت:**\n\n"
                f"🔗 @{FORCE_SUBSCRIBE_CHANNEL_USERNAME}\n\n"
                f"بعد الاشتراك، اضغط على /start أو **🫆 القائمة** للمتابعة."
            )
            # زر Inline للربط المباشر بالقناة
            keyboard = [[InlineKeyboardButton("اشترك في القناة 🚀", url=f"https://t.me/{FORCE_SUBSCRIBE_CHANNEL_USERNAME}")]]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.effective_message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
            return True # تم فرض الاشتراك
    return False # لم يتم فرض الاشتراك، يمكن المتابعة

# --- 4. 🚀 وظائف إدارة الدردشة (Matching Logic) ---

async def find_partner(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """منطق البحث عن شريك عشوائي."""
    user_id = update.effective_user.id
    
    if user_id in waiting_queue:
        await update.effective_message.reply_text("أنت بالفعل في طابور البحث. يرجى الانتظار...", reply_markup=main_markup)
        return

    # 1. إزالة المستخدم من أي دردشة سابقة أو انتظار
    if user_id in current_chats:
        await stop_chat_internal(context, user_id)
    if user_id in waiting_queue:
        waiting_queue.remove(user_id)

    # 2. التحقق من وجود شريك متاح
    if waiting_queue:
        partner_id = waiting_queue.pop(0) # استخراج أول شخص ينتظر
        
        # ربط الشريكين
        current_chats[user_id] = partner_id
        current_chats[partner_id] = user_id
        
        # تحديث حالة المستخدمين
        user_data.setdefault(user_id, {})['status'] = 'chatting'
        user_data.setdefault(partner_id, {})['status'] = 'chatting'

        success_message = "🐸 **تم العثور على شريك!**\n\n/next — الدردشة التالية.\n/stop — إيقاف الدردشة."
        
        # إرسال رسالة النجاح للشريكين وتغيير لوحة المفاتيح
        await context.bot.send_message(user_id, success_message, reply_markup=chat_markup, parse_mode='Markdown')
        await context.bot.send_message(partner_id, success_message, reply_markup=chat_markup, parse_mode='Markdown')
        logger.info(f"Chat started between {user_id} and {partner_id}")

    # 3. عدم وجود شريك متاح - الدخول إلى طابور الانتظار
    else:
        waiting_queue.append(user_id)
        user_data.setdefault(user_id, {})['status'] = 'waiting'
        await update.effective_message.reply_text("🔎 **جارٍ البحث عن شريك...** يرجى الانتظار.\n\nاضغط **🫆 القائمة** لإلغاء البحث.", reply_markup=main_markup, parse_mode='Markdown')
        logger.info(f"User {user_id} added to waiting queue.")

async def next_chat_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """إنهاء الدردشة الحالية والبدء في البحث عن شريك جديد (/next)."""
    user_id = update.effective_user.id

    if await enforce_subscription(update, context):
        return
        
    if user_id in current_chats:
        # إيقاف الدردشة الحالية
        await stop_chat_internal(context, user_id)
        # البدء في بحث جديد
        await find_partner(update, context)
    else:
        await update.effective_message.reply_text("أنت لست في دردشة حالية. اضغط على **🚀 البحث عن شريك عشوائي** للبدء.", reply_markup=main_markup)

async def stop_chat_internal(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> None:
    """دالة مساعدة لإيقاف الدردشة داخلياً."""
    partner_id = current_chats.pop(user_id, None)

    if partner_id:
        # إنهاء الدردشة من الجانب الآخر
        current_chats.pop(partner_id, None)
        user_data.setdefault(user_id, {})['status'] = 'idle'
        user_data.setdefault(partner_id, {})['status'] = 'idle'

        # إرسال رسائل الإيقاف
        stop_message = "🚫 **تم إيقاف الدردشة.**"
        await context.bot.send_message(user_id, stop_message, reply_markup=main_markup, parse_mode='Markdown')
        await context.bot.send_message(partner_id, stop_message, reply_markup=main_markup, parse_mode='Markdown')
        logger.info(f"Chat stopped between {user_id} and {partner_id}")
    elif user_id in waiting_queue:
        # إذا كان في وضع الانتظار فقط
        waiting_queue.remove(user_id)
        user_data.setdefault(user_id, {})['status'] = 'idle'
        await context.bot.send_message(user_id, "❌ **تم إلغاء البحث.**", reply_markup=main_markup, parse_mode='Markdown')
        logger.info(f"User {user_id} cancelled search.")

async def stop_chat_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """إيقاف الدردشة الحالية (/stop)."""
    user_id = update.effective_user.id
    if await enforce_subscription(update, context):
        return
    await stop_chat_internal(context, user_id)

# --- 5. 🫆 وظائف معالجة الأوامر والأزرار الرئيسية ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """يعالج أمر /start ويعرض القائمة الرئيسية."""
    if await enforce_subscription(update, context):
        return

    text = "👋 **أهلاً بك في بوت الدردشة العشوائية!**\nاختر من القائمة أدناه للبدء."
    await update.message.reply_text(text, reply_markup=main_markup, parse_mode='Markdown')

async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """يعالج زر القائمة 🫆 (للرجوع للقائمة الأصلية)."""
    if await enforce_subscription(update, context):
        return
        
    user_id = update.effective_user.id
    
    # إذا كان المستخدم في وضع الانتظار، يلغي البحث
    if user_id in waiting_queue:
        await stop_chat_internal(context, user_id)

    text = "رجوع إلى **القائمة الرئيسية**."
    await update.effective_message.reply_text(text, reply_markup=main_markup, parse_mode='Markdown')

async def settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """يعرض قائمة الإعدادات الفرعية."""
    if await enforce_subscription(update, context):
        return
        
    text = "⚙️ **الإعدادات:**\nيرجى تحديد معلوماتك لتضييق نطاق البحث."
    await update.effective_message.reply_text(text, reply_markup=settings_markup, parse_mode='Markdown')

async def share_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """يرسل رابط مشاركة البوت."""
    if await enforce_subscription(update, context):
        return
        
    bot_username = (await context.bot.get_me()).username
    share_text = (
        f"🔗 **شارك رابط البوت:**\n\n"
        f"قم بدعوة أصدقائك للدردشة العشوائية!\n"
        f"https://t.me/{bot_username}"
    )
    await update.effective_message.reply_text(share_text, reply_markup=main_markup, parse_mode='Markdown')

# --- 6. ⚙️ وظائف معالجة الإعدادات ---

async def handle_settings_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """يعالج الأزرار الفرعية للإعدادات (الجنس، اللغة، العمر، الموقع)."""
    text = update.effective_message.text
    user_id = update.effective_user.id

    if await enforce_subscription(update, context):
        return

    # إعدادات بسيطة: يحتاج إلى منطق جمع مدخلات المستخدم (ConversationHandler)
    # لكن لتبسيط الهيكل، سنعرض رسالة طلب إدخال
    user_data.setdefault(user_id, {})
    
    if "👦 الجنس" in text:
        user_data[user_id]['awaiting_input'] = 'gender'
        await update.effective_message.reply_text("يرجى إرسال جنسك (ذكر/أنثى):", reply_markup=settings_markup)
    elif "🌍 اللغة" in text:
        user_data[user_id]['awaiting_input'] = 'language'
        await update.effective_message.reply_text("يرجى إرسال لغتك المفضلة (مثل العربية، الإنجليزية):", reply_markup=settings_markup)
    elif "👶 العمر" in text:
        user_data[user_id]['awaiting_input'] = 'age'
        await update.effective_message.reply_text("يرجى إرسال عمرك (كرقم):", reply_markup=settings_markup)
    elif "🚩 الموقع الجغرافي" in text:
        user_data[user_id]['awaiting_input'] = 'location'
        await update.effective_message.reply_text("يرجى إرسال موقعك الجغرافي (مثل اسم المدينة/البلد):", reply_markup=settings_markup)
    else:
        # رسالة غير متوقعة
        await update.effective_message.reply_text("لم يتم التعرف على الأمر. اختر من القائمة أو اضغط على 🫆 القائمة.", reply_markup=main_markup)


async def handle_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """يعالج الرسائل النصية من المستخدمين (سواء في الدردشة أو إدخال الإعدادات)."""
    user_id = update.effective_user.id
    message_text = update.effective_message.text

    if await enforce_subscription(update, context):
        return

    # حالة: إدخال بيانات الإعدادات
    if user_data.get(user_id, {}).get('awaiting_input'):
        setting_key = user_data[user_id].pop('awaiting_input')
        
        # حفظ القيمة
        user_data[user_id].setdefault('settings', {})[setting_key] = message_text
        
        await update.effective_message.reply_text(f"✅ تم حفظ **{setting_key}** بنجاح: **{message_text}**", parse_mode='Markdown', reply_markup=settings_markup)
        logger.info(f"User {user_id} set {setting_key} to {message_text}")
        return

    # حالة: إرسال رسالة في دردشة عشوائية
    elif user_id in current_chats:
        partner_id = current_chats.get(user_id)
        if partner_id:
            try:
                # إعادة توجيه الرسالة
                await context.bot.copy_message(
                    chat_id=partner_id,
                    from_chat_id=user_id,
                    message_id=update.effective_message.message_id
                )
            except Exception as e:
                logger.error(f"Failed to forward message from {user_id} to {partner_id}: {e}")
                await stop_chat_internal(context, user_id)
                await update.effective_message.reply_text("🚫 حدث خطأ في إرسال الرسالة، تم إنهاء الدردشة.", reply_markup=main_markup)
        return
        
    # حالة: رسالة عادية لا تنتمي لدردشة أو إعدادات
    else:
        await update.effective_message.reply_text("الرجاء اختيار أمر من القائمة الرئيسية أدناه.", reply_markup=main_markup)


# --- 7. تشغيل البوت ---

def main() -> None:
    """الدالة الرئيسية لتشغيل البوت."""
    # إنشاء التطبيق
    application = Application.builder().token(TOKEN).build()

    # الأوامر الرئيسية
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("next", next_chat_command))
    application.add_handler(CommandHandler("stop", stop_chat_command))

    # معالجة أزرار القائمة الرئيسية (التي هي نصوص في لوحة المفاتيح)
    application.add_handler(MessageHandler(filters.Regex("^🚀 البحث عن شريك عشوائي$"), find_partner))
    application.add_handler(MessageHandler(filters.Regex("^🫆 القائمة$"), main_menu))
    application.add_handler(MessageHandler(filters.Regex("^🔋 الاعدادات$"), settings_menu))
    application.add_handler(MessageHandler(filters.Regex("^🔗 Share account link$"), share_link))

    # معالجة أزرار الإعدادات الفرعية
    application.add_handler(MessageHandler(filters.Regex("^(1 👦 الجنس|2 🌍 اللغة|3 👶 العمر|4 🚩 الموقع الجغرافي)$"), handle_settings_selection))

    # معالجة جميع النصوص الأخرى (رسائل الدردشة، وإدخالات الإعدادات)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_input))

    # ابدأ تشغيل البوت
    logger.info("Bot started and polling...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
