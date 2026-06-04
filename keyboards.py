"""
Inline klaviaturalar (tugmalar). Barcha matnlar foydalanuvchi tiliga moslangan.

Callback data formatlari (qisqa bo'lishi shart - Telegram limiti 64 bayt):
  lang:<uz|ru|en>      -> til tanlash
  menu:test|stats|about|lang  -> asosiy menyu
  subj:<key>           -> fan tanlash
  sect:<key>           -> bo'lim tanlash (ingliz tili)
  diff:<easy|medium|hard>  -> qiyinlik darajasi
  topic:<index>        -> mavzu tanlash (indeks user_data dagi ro'yxatga)
  ans:<A|B|C|D>        -> savol javobi
  nav:menu             -> asosiy menyuga qaytish
"""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import config
from i18n import LANG_NAMES, t


def languages() -> InlineKeyboardMarkup:
    """Til tanlash menyusi."""
    buttons = [
        [InlineKeyboardButton(LANG_NAMES[code], callback_data=f"lang:{code}")]
        for code in config.LANGUAGES
    ]
    return InlineKeyboardMarkup(buttons)


def main_menu(lang: str) -> InlineKeyboardMarkup:
    """Asosiy menyu."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(t("menu_test", lang), callback_data="menu:test")],
            [InlineKeyboardButton(t("menu_stats", lang), callback_data="menu:stats")],
            [InlineKeyboardButton(t("menu_about", lang), callback_data="menu:about")],
            [InlineKeyboardButton(t("menu_language", lang), callback_data="menu:lang")],
        ]
    )


def subjects(lang: str) -> InlineKeyboardMarkup:
    """Fanlar ro'yxati (2 ustun)."""
    buttons: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for key, info in config.SUBJECTS.items():
        label = f"{info['emoji']} {config.subject_name(key, lang)}"
        row.append(InlineKeyboardButton(label, callback_data=f"subj:{key}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(t("btn_back", lang), callback_data="nav:menu")])
    return InlineKeyboardMarkup(buttons)


def sections(subject_key: str, lang: str) -> InlineKeyboardMarkup:
    """Fan ichidagi bo'limlar (masalan: IELTS / Grammar)."""
    info = config.SUBJECTS[subject_key]
    buttons: list[list[InlineKeyboardButton]] = []
    for sec_key, sec_name in info.get("sections", {}).items():
        buttons.append([InlineKeyboardButton(sec_name, callback_data=f"sect:{sec_key}")])
    buttons.append([InlineKeyboardButton(t("btn_back", lang), callback_data="menu:test")])
    return InlineKeyboardMarkup(buttons)


def difficulties(lang: str) -> InlineKeyboardMarkup:
    """Qiyinlik darajasi tanlovi."""
    buttons = [
        [InlineKeyboardButton(config.difficulty_label(key, lang), callback_data=f"diff:{key}")]
        for key in config.DIFFICULTIES
    ]
    buttons.append([InlineKeyboardButton(t("btn_back", lang), callback_data="menu:test")])
    return InlineKeyboardMarkup(buttons)


def topics(topic_list: list[str], lang: str) -> InlineKeyboardMarkup:
    """AI taklif qilgan mavzular (indeks bo'yicha)."""
    buttons = [
        [InlineKeyboardButton(f"{i + 1}. {topic}", callback_data=f"topic:{i}")]
        for i, topic in enumerate(topic_list)
    ]
    buttons.append([InlineKeyboardButton(t("btn_back", lang), callback_data="menu:test")])
    return InlineKeyboardMarkup(buttons)


def answers(lang: str) -> InlineKeyboardMarkup:
    """A, B, C, D variant tugmalari (2x2) + testni to'xtatish."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("A", callback_data="ans:A"),
                InlineKeyboardButton("B", callback_data="ans:B"),
            ],
            [
                InlineKeyboardButton("C", callback_data="ans:C"),
                InlineKeyboardButton("D", callback_data="ans:D"),
            ],
            [InlineKeyboardButton(t("btn_stop_test", lang), callback_data="nav:menu")],
        ]
    )


def back_to_menu(lang: str) -> InlineKeyboardMarkup:
    """Faqat 'Asosiy menyu' tugmasi."""
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(t("btn_home", lang), callback_data="nav:menu")]]
    )
