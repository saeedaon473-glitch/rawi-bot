import os
import logging
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    logger.error("❌ BOT_TOKEN غير موجود.")
    exit(1)

def start(update: Update, context: CallbackContext):
    update.message.reply_text("مرحباً! البوت يعمل 🚀")

def help_command(update: Update, context: CallbackContext):
    update.message.reply_text("أرسل أي شيء وسأعيده لك.")

def echo(update: Update, context: CallbackContext):
    update.message.reply_text(f"استلمت: {update.message.text}")

def main():
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("help", help_command))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, echo))
    updater.start_polling()
    logger.info("✅ البوت شغال!")
    updater.idle()

if __name__ == "__main__":
    main()
