"""
Bot handlerlari — to'liq suhbat oqimi (3 til, qiyinlik darajasi, vaqt cheklovi).

Oqim:
  /start
    └─ (yangi foydalanuvchi) 🌐 Til tanlash
    └─ Asosiy menyu
         ├─ 📚 Test boshlash -> Fan -> (Bo'lim) -> Qiyinlik -> Mavzu(AI) -> savollar
         │     └─ Har bir savolga vaqt cheklovi (JobQueue timer)
         │     └─ Yakunda: natija + AI tahlil + xatolar tahlili
         ├─ 📊 Mening natijalarim
         ├─ ℹ️ Bot haqida
         └─ 🌐 Til / Language
"""

from __future__ import annotations

import html
import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import ContextTypes

import config
import database as db
import gemini_client as ai
import keyboards as kb
from i18n import t

logger = logging.getLogger(__name__)

# --- Suhbat holatlari ---
MAIN_MENU, LANGUAGE, SUBJECT, SECTION, DIFFICULTY, TOPIC, QUESTION = range(7)


# ======================================================================
#  Yordamchi funksiyalar
# ======================================================================

async def _get_lang(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> str:
    """Foydalanuvchi tilini olish (user_data keshidan yoki bazadan)."""
    lang = context.user_data.get("lang")
    if lang in config.LANGUAGES:
        return lang
    lang = await db.get_language(user_id) or config.DEFAULT_LANGUAGE
    context.user_data["lang"] = lang
    return lang


def _grade(pct: float, lang: str) -> str:
    if pct >= 90:
        return t("grade_excellent", lang)
    if pct >= 70:
        return t("grade_good", lang)
    if pct >= 50:
        return t("grade_ok", lang)
    return t("grade_bad", lang)


def _timer_name(user_id: int) -> str:
    return f"qtimer:{user_id}"


def _cancel_timer(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> None:
    """Joriy savol uchun ishlab turgan timerni bekor qilish."""
    if not context.job_queue:
        return
    for job in context.job_queue.get_jobs_by_name(_timer_name(user_id)):
        job.schedule_removal()


def _schedule_timer(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    user_id: int,
    index: int,
) -> None:
    """Joriy savol uchun vaqt cheklovini o'rnatish."""
    if not context.job_queue:
        return
    _cancel_timer(context, user_id)
    context.job_queue.run_once(
        _on_timeout,
        when=config.QUESTION_TIME,
        chat_id=chat_id,
        user_id=user_id,
        data={"index": index},
        name=_timer_name(user_id),
    )


# ======================================================================
#  /start, til tanlash va asosiy menyu
# ======================================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """/start — foydalanuvchini ro'yxatga oladi. Yangi bo'lsa til so'raydi."""
    user = update.effective_user
    await db.add_user(user.id, user.username, user.first_name)
    _cancel_timer(context, user.id)
    context.user_data.pop("test", None)

    saved_lang = await db.get_language(user.id)
    if saved_lang is None:
        # Yangi foydalanuvchi -> til tanlash
        await _send_or_edit(update, t("choose_language", config.DEFAULT_LANGUAGE), kb.languages())
        return LANGUAGE

    context.user_data["lang"] = saved_lang
    await _show_main_menu(update, saved_lang, user.first_name)
    return MAIN_MENU


async def set_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Til tanlandi (lang:<code>)."""
    query = update.callback_query
    await query.answer()
    code = query.data.split(":", 1)[1]
    if code not in config.LANGUAGES:
        code = config.DEFAULT_LANGUAGE

    await db.set_language(update.effective_user.id, code)
    context.user_data["lang"] = code

    await query.edit_message_text(t("language_set", code))
    await _show_main_menu(update, code, update.effective_user.first_name, new_message=True)
    return MAIN_MENU


async def main_menu_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Asosiy menyu tugmalari (menu:...)."""
    query = update.callback_query
    await query.answer()
    lang = await _get_lang(context, update.effective_user.id)
    action = query.data.split(":", 1)[1]

    if action == "test":
        await query.edit_message_text(
            t("choose_subject", lang),
            parse_mode=ParseMode.HTML,
            reply_markup=kb.subjects(lang),
        )
        return SUBJECT

    if action == "stats":
        await _show_stats(update, lang)
        return MAIN_MENU

    if action == "about":
        await query.edit_message_text(
            t("about", lang, num=config.NUM_QUESTIONS, time=config.QUESTION_TIME),
            parse_mode=ParseMode.HTML,
            reply_markup=kb.back_to_menu(lang),
        )
        return MAIN_MENU

    if action == "lang":
        await query.edit_message_text(
            t("choose_language", lang), reply_markup=kb.languages()
        )
        return LANGUAGE

    return MAIN_MENU


async def to_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Istalgan joydan asosiy menyuga qaytish (nav:menu)."""
    query = update.callback_query
    await query.answer()
    _cancel_timer(context, update.effective_user.id)
    context.user_data.pop("test", None)
    lang = await _get_lang(context, update.effective_user.id)
    text = t("welcome", lang, name=html.escape(update.effective_user.first_name or "👤"))
    await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb.main_menu(lang))
    return MAIN_MENU


# ======================================================================
#  Fan / bo'lim / qiyinlik tanlash
# ======================================================================

async def choose_subject(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Fan tanlandi."""
    query = update.callback_query
    await query.answer()
    lang = await _get_lang(context, update.effective_user.id)
    subject_key = query.data.split(":", 1)[1]

    if subject_key not in config.SUBJECTS:
        return SUBJECT

    context.user_data["subject_key"] = subject_key
    context.user_data["section_key"] = None
    context.user_data["section_name"] = None

    info = config.SUBJECTS[subject_key]

    if "sections" in info:
        await query.edit_message_text(
            t("choose_section", lang, emoji=info["emoji"],
              subject=html.escape(config.subject_name(subject_key, lang))),
            parse_mode=ParseMode.HTML,
            reply_markup=kb.sections(subject_key, lang),
        )
        return SECTION

    await _ask_difficulty(update, lang)
    return DIFFICULTY


async def choose_section(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Bo'lim tanlandi (IELTS / Grammar)."""
    query = update.callback_query
    await query.answer()
    lang = await _get_lang(context, update.effective_user.id)
    section_key = query.data.split(":", 1)[1]

    subject_key = context.user_data.get("subject_key")
    info = config.SUBJECTS.get(subject_key, {})
    sections = info.get("sections", {})
    if section_key not in sections:
        return SECTION

    context.user_data["section_key"] = section_key
    context.user_data["section_name"] = sections[section_key]

    await _ask_difficulty(update, lang)
    return DIFFICULTY


async def _ask_difficulty(update: Update, lang: str) -> None:
    """Qiyinlik darajasini so'rash."""
    await update.callback_query.edit_message_text(
        t("choose_difficulty", lang),
        parse_mode=ParseMode.HTML,
        reply_markup=kb.difficulties(lang),
    )


async def choose_difficulty(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Qiyinlik tanlandi -> mavzularni yuklash."""
    query = update.callback_query
    await query.answer()
    difficulty = query.data.split(":", 1)[1]
    if difficulty not in config.DIFFICULTIES:
        difficulty = "medium"
    context.user_data["difficulty"] = difficulty

    await _load_topics(update, context)
    return TOPIC


async def _load_topics(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """AI dan mavzularni olib ko'rsatish."""
    query = update.callback_query
    lang = await _get_lang(context, update.effective_user.id)
    subject_key = context.user_data["subject_key"]
    section_name = context.user_data.get("section_name")
    info = config.SUBJECTS[subject_key]

    await query.edit_message_text(t("loading_topics", lang))

    try:
        topics = await ai.generate_topics(subject_key, section_name, lang)
    except Exception:  # noqa: BLE001
        logger.exception("Mavzularni olishda xatolik")
        topics = []

    if not topics:
        await query.edit_message_text(
            t("topics_error", lang), reply_markup=kb.back_to_menu(lang)
        )
        return

    context.user_data["topics"] = topics
    title = config.subject_name(subject_key, lang) + (f" — {section_name}" if section_name else "")
    await query.edit_message_text(
        t("choose_topic", lang, emoji=info["emoji"], title=html.escape(title)),
        parse_mode=ParseMode.HTML,
        reply_markup=kb.topics(topics, lang),
    )


# ======================================================================
#  Mavzu tanlash va testni boshlash
# ======================================================================

async def choose_topic(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Mavzu tanlandi -> savollarni generatsiya qilib testni boshlaymiz."""
    query = update.callback_query
    await query.answer()
    lang = await _get_lang(context, update.effective_user.id)

    try:
        index = int(query.data.split(":", 1)[1])
    except (ValueError, IndexError):
        return TOPIC

    topics = context.user_data.get("topics", [])
    if index < 0 or index >= len(topics):
        return TOPIC

    topic = topics[index]
    subject_key = context.user_data["subject_key"]
    section_name = context.user_data.get("section_name")
    difficulty = context.user_data.get("difficulty", "medium")

    await query.edit_message_text(
        t("loading_questions", lang, topic=html.escape(topic), num=config.NUM_QUESTIONS),
        parse_mode=ParseMode.HTML,
    )

    try:
        questions = await ai.generate_questions(
            subject_key, section_name, topic, difficulty, lang
        )
    except Exception:  # noqa: BLE001
        logger.exception("Savollarni generatsiya qilishda xatolik")
        questions = []

    if len(questions) < 1:
        await query.edit_message_text(
            t("questions_error", lang), reply_markup=kb.back_to_menu(lang)
        )
        return MAIN_MENU

    # Test holatini saqlash
    context.user_data["test"] = {
        "subject_key": subject_key,
        "section_name": section_name,
        "difficulty": difficulty,
        "topic": topic,
        "questions": questions,
        "index": 0,
        "correct": 0,
        "wrong_details": [],
        "lang": lang,
        "chat_id": query.message.chat_id,
        "message_id": query.message.message_id,
    }

    await _render_question(context, context.user_data["test"], update.effective_user.id)
    return QUESTION


async def _render_question(
    context: ContextTypes.DEFAULT_TYPE, test: dict, user_id: int, send_new: bool = False
) -> None:
    """
    Joriy savolni ko'rsatish va timerni o'rnatish.

    send_new=False -> mavjud xabarni tahrirlash (foydalanuvchi tugma bosgach).
    send_new=True  -> yangi xabar yuborish (vaqt tugaganda — xabar pastda ko'rinadi).
    """
    i = test["index"]
    q = test["questions"][i]
    total = len(test["questions"])
    lang = test["lang"]

    text = (
        t("question", lang, n=i + 1, total=total, time=config.QUESTION_TIME)
        + "\n\n"
        + f"{html.escape(q['question'])}\n\n"
        + f"<b>A)</b> {html.escape(q['options']['A'])}\n"
        + f"<b>B)</b> {html.escape(q['options']['B'])}\n"
        + f"<b>C)</b> {html.escape(q['options']['C'])}\n"
        + f"<b>D)</b> {html.escape(q['options']['D'])}"
    )

    if not send_new:
        try:
            await context.bot.edit_message_text(
                text,
                chat_id=test["chat_id"],
                message_id=test["message_id"],
                parse_mode=ParseMode.HTML,
                reply_markup=kb.answers(lang),
            )
        except BadRequest:
            logger.warning("Savolni tahrirlab bo'lmadi, yangi xabar yuboriladi.")
            send_new = True

    if send_new:
        msg = await context.bot.send_message(
            chat_id=test["chat_id"],
            text=text,
            parse_mode=ParseMode.HTML,
            reply_markup=kb.answers(lang),
        )
        test["message_id"] = msg.message_id

    _schedule_timer(context, test["chat_id"], user_id, i)


async def answer_question(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Foydalanuvchi javobini qabul qilish."""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    _cancel_timer(context, user_id)

    test = context.user_data.get("test")
    if not test:
        return await to_main_menu(update, context)

    selected = query.data.split(":", 1)[1]
    _record_answer(test, selected)
    test["index"] += 1

    if test["index"] < len(test["questions"]):
        await _render_question(context, test, user_id)
        return QUESTION

    await _finish_test(context, test, user_id)
    return MAIN_MENU


async def _on_timeout(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Vaqt tugaganda avtomatik keyingi savolga o'tish (JobQueue callback)."""
    test = context.user_data.get("test")
    if not test:
        return
    job_index = context.job.data.get("index")
    # Eskirgan timer (foydalanuvchi allaqachon javob bergan) — e'tiborsiz qoldiramiz
    if job_index != test["index"]:
        return

    user_id = context.job.user_id
    _record_answer(test, None)  # javob berilmadi
    test["index"] += 1

    # "Vaqt tugadi" xabari
    try:
        await context.bot.send_message(chat_id=test["chat_id"], text=t("time_up", test["lang"]))
    except BadRequest:
        pass

    if test["index"] < len(test["questions"]):
        await _render_question(context, test, user_id, send_new=True)
    else:
        await _finish_test(context, test, user_id)


def _record_answer(test: dict, selected: str | None) -> None:
    """Javobni hisobga olish (None bo'lsa = vaqt tugagan / javob yo'q)."""
    i = test["index"]
    q = test["questions"][i]
    if selected is not None and selected == q["correct"]:
        test["correct"] += 1
    else:
        test["wrong_details"].append(
            {
                "n": i + 1,
                "question": q["question"],
                "selected": selected,
                "selected_text": q["options"].get(selected) if selected else None,
                "correct": q["correct"],
                "correct_text": q["options"][q["correct"]],
                "explanation": q["explanation"],
            }
        )


# ======================================================================
#  Test yakuni va natija tahlili
# ======================================================================

async def _finish_test(
    context: ContextTypes.DEFAULT_TYPE, test: dict, user_id: int
) -> None:
    """Natijani hisoblash, saqlash va tahlilni ko'rsatish."""
    _cancel_timer(context, user_id)
    lang = test["lang"]
    chat_id = test["chat_id"]
    total = len(test["questions"])
    correct = test["correct"]
    wrong = total - correct
    pct = round((correct / total) * 100, 1) if total else 0.0

    subject_key = test["subject_key"]
    section_name = test.get("section_name")
    difficulty = test.get("difficulty", "medium")
    topic = test["topic"]
    subject_name = config.subject_name(subject_key, lang)

    # Bazaga saqlash
    await db.save_result(
        user_id=user_id,
        subject=subject_name,
        section=section_name,
        topic=topic,
        difficulty=difficulty,
        total=total,
        correct=correct,
    )

    # Natija sarlavhasi
    header = (
        f"{t('test_finished', lang)}\n\n"
        f"{t('result_subject', lang)}: <b>{html.escape(subject_name)}</b>"
        + (f" — {html.escape(section_name)}" if section_name else "")
        + f"\n{t('result_topic', lang)}: <b>{html.escape(topic)}</b>"
        + f"\n{t('result_difficulty', lang)}: <b>{config.difficulty_label(difficulty, lang)}</b>\n\n"
        + f"{t('result_correct', lang)}: <b>{correct}</b>\n"
        + f"{t('result_wrong', lang)}: <b>{wrong}</b>\n"
        + f"{t('result_score', lang)}: <b>{pct}%</b>  {_grade(pct, lang)}"
    )
    try:
        await context.bot.edit_message_text(
            header, chat_id=chat_id, message_id=test["message_id"], parse_mode=ParseMode.HTML
        )
    except BadRequest:
        await context.bot.send_message(chat_id=chat_id, text=header, parse_mode=ParseMode.HTML)

    # AI tavsiyasi
    wrong_topics = [w["question"] for w in test["wrong_details"]]
    feedback = await ai.generate_feedback(subject_key, topic, correct, total, wrong_topics, lang)
    if feedback:
        await context.bot.send_message(
            chat_id=chat_id,
            text=t("ai_feedback", lang) + html.escape(feedback),
            parse_mode=ParseMode.HTML,
        )

    # Xatolar tahlili
    if test["wrong_details"]:
        await _send_wrong_analysis(context, chat_id, lang, test["wrong_details"])
    else:
        await context.bot.send_message(chat_id=chat_id, text=t("all_correct", lang))

    await context.bot.send_message(
        chat_id=chat_id,
        text=t("continue_below", lang),
        reply_markup=kb.main_menu(lang),
    )
    context.user_data.pop("test", None)


async def _send_wrong_analysis(
    context: ContextTypes.DEFAULT_TYPE, chat_id: int, lang: str, wrong: list[dict]
) -> None:
    """Xatolar tahlilini Telegram limitiga moslab bo'laklab yuborish."""
    blocks = [t("wrong_analysis_title", lang)]
    for w in wrong:
        if w["selected"]:
            your = f"<b>{w['selected']}</b>) {html.escape(w['selected_text'])}"
        else:
            your = t("no_answer", lang)
        block = (
            f"\n<b>{t('wrong_q', lang)} {w['n']}.</b> {html.escape(w['question'])}\n"
            f"{t('your_answer', lang)}: {your}\n"
            f"{t('correct_answer', lang)}: <b>{w['correct']}</b>) "
            f"{html.escape(w['correct_text'])}\n"
        )
        if w["explanation"]:
            block += f"💡 {html.escape(w['explanation'])}\n"
        blocks.append(block)

    chunk = ""
    for block in blocks:
        if len(chunk) + len(block) > 3800:
            await context.bot.send_message(chat_id=chat_id, text=chunk, parse_mode=ParseMode.HTML)
            chunk = ""
        chunk += block
    if chunk:
        await context.bot.send_message(chat_id=chat_id, text=chunk, parse_mode=ParseMode.HTML)


# ======================================================================
#  Statistika — "Mening natijalarim"
# ======================================================================

async def _show_stats(update: Update, lang: str) -> None:
    """Foydalanuvchi statistikasini ko'rsatish."""
    query = update.callback_query
    user_id = update.effective_user.id

    overall = await db.get_overall_stats(user_id)
    if overall["tests"] == 0:
        await query.edit_message_text(
            t("stats_empty", lang),
            parse_mode=ParseMode.HTML,
            reply_markup=kb.back_to_menu(lang),
        )
        return

    subjects = await db.get_subject_stats(user_id)
    recent = await db.get_recent_results(user_id, limit=5)

    text = (
        f"{t('stats_title', lang)}\n\n"
        f"{t('stats_overall', lang)}\n"
        f"• {t('stats_tests', lang)}: <b>{overall['tests']}</b>\n"
        f"• {t('stats_questions', lang)}: <b>{overall['questions']}</b>\n"
        f"• {t('stats_correct', lang)}: <b>{overall['correct']}</b>\n"
        f"• {t('stats_avg', lang)}: <b>{overall['avg_pct']}%</b>\n"
        f"• {t('stats_best', lang)}: <b>{overall['best_pct']}%</b>\n"
    )

    if subjects:
        text += f"\n{t('stats_by_subject', lang)}\n"
        for s in subjects:
            text += (
                f"• {html.escape(s['subject'])}: <b>{s['avg_pct']}%</b> "
                f"({s['tests']} {t('stats_tests_count', lang)})\n"
            )

    if recent:
        text += f"\n{t('stats_recent', lang)}\n"
        for r in recent:
            line = f"• {html.escape(r['subject'])}"
            if r["topic"]:
                line += f" ({html.escape(r['topic'])})"
            line += f" — <b>{r['percentage']}%</b>\n"
            text += line

    await query.edit_message_text(
        text, parse_mode=ParseMode.HTML, reply_markup=kb.back_to_menu(lang)
    )


# ======================================================================
#  Umumiy yordamchilar
# ======================================================================

async def _show_main_menu(
    update: Update, lang: str, first_name: str | None, new_message: bool = False
) -> None:
    """Asosiy menyuni ko'rsatish."""
    text = t("welcome", lang, name=html.escape(first_name or "👤"))
    if new_message or not update.callback_query:
        await update.effective_chat.send_message(
            text, parse_mode=ParseMode.HTML, reply_markup=kb.main_menu(lang)
        )
    else:
        await update.callback_query.edit_message_text(
            text, parse_mode=ParseMode.HTML, reply_markup=kb.main_menu(lang)
        )


async def _send_or_edit(update: Update, text: str, reply_markup) -> None:
    """callback bo'lsa tahrirlash, aks holda yangi xabar."""
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            text, parse_mode=ParseMode.HTML, reply_markup=reply_markup
        )
    else:
        await update.effective_message.reply_text(
            text, parse_mode=ParseMode.HTML, reply_markup=reply_markup
        )


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Kutilmagan xatoliklarni loglash."""
    logger.error("Xatolik yuz berdi:", exc_info=context.error)
