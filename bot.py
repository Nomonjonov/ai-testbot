"""
Botni ishga tushirish nuqtasi.

Ishga tushirish:
    python bot.py

Rejim avtomatik tanlanadi:
  - WEBHOOK_URL berilgan bo'lsa  -> webhook rejimi (Render va boshqa hostinglar uchun)
  - aks holda                    -> polling rejimi (lokal kompyuter / VPS uchun qulay)
"""

from __future__ import annotations

import logging

from telegram import BotCommand, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
)

import config
import database as db
import handlers as h

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
# Tashqi kutubxonalarning ortiqcha loglarini kamaytirish
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


async def _post_init(app: Application) -> None:
    """Bot ishga tushgandan keyin: bazani tayyorlash va buyruqlarni o'rnatish."""
    await db.init_db()
    await app.bot.set_my_commands(
        [
            BotCommand("start", "Restart / Asosiy menyu / Главное меню / Main menu"),
        ]
    )
    logger.info(
        "Bot tayyor. Model: %s | Savollar: %d | Vaqt: %ds/savol",
        config.GEMINI_MODEL,
        config.NUM_QUESTIONS,
        config.QUESTION_TIME,
    )


def build_application() -> Application:
    """Application va ConversationHandler'ni yig'ish."""
    app = (
        Application.builder()
        .token(config.BOT_TOKEN)
        .concurrent_updates(True)  # bir nechta foydalanuvchi bir vaqtda ishlay olsin
        .post_init(_post_init)
        .build()
    )

    # Til tanlash har bir holatda ishlashi uchun umumiy handler
    lang_handler = CallbackQueryHandler(h.set_language, pattern="^lang:")

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", h.start)],
        states={
            h.LANGUAGE: [lang_handler],
            h.MAIN_MENU: [
                CallbackQueryHandler(h.main_menu_cb, pattern="^menu:"),
            ],
            h.SUBJECT: [
                CallbackQueryHandler(h.choose_subject, pattern="^subj:"),
            ],
            h.SECTION: [
                CallbackQueryHandler(h.choose_section, pattern="^sect:"),
                CallbackQueryHandler(h.main_menu_cb, pattern="^menu:"),
            ],
            h.DIFFICULTY: [
                CallbackQueryHandler(h.choose_difficulty, pattern="^diff:"),
                CallbackQueryHandler(h.main_menu_cb, pattern="^menu:"),
            ],
            h.TOPIC: [
                CallbackQueryHandler(h.choose_topic, pattern="^topic:"),
                CallbackQueryHandler(h.main_menu_cb, pattern="^menu:"),
            ],
            h.QUESTION: [
                CallbackQueryHandler(h.answer_question, pattern="^ans:"),
            ],
        },
        fallbacks=[
            CommandHandler("start", h.start),
            CallbackQueryHandler(h.to_main_menu, pattern="^nav:menu$"),
            lang_handler,
        ],
        allow_reentry=True,
    )

    app.add_handler(conv)
    app.add_error_handler(h.error_handler)
    return app


def main() -> None:
    config.validate()
    app = build_application()

    if config.WEBHOOK_URL:
        # Webhook rejimi (hosting). Telegram bu URL'ga update yuboradi.
        logger.info("Webhook rejimida ishga tushmoqda: %s", config.WEBHOOK_URL)
        app.run_webhook(
            listen="0.0.0.0",
            port=config.PORT,
            url_path=config.BOT_TOKEN,
            webhook_url=f"{config.WEBHOOK_URL}/{config.BOT_TOKEN}",
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True,
        )
    else:
        # Polling rejimi (lokal / VPS).
        logger.info("Polling rejimida ishga tushmoqda...")
        app.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True,
        )


if __name__ == "__main__":
    main()
