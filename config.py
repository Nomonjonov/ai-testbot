"""
Bot konfiguratsiyasi.

Barcha maxfiy ma'lumotlar (tokenlar) .env faylidan yoki hosting platformasidagi
Environment Variables (muhit o'zgaruvchilari) orqali olinadi. Kodga hech qachon
tokenni to'g'ridan-to'g'ri yozmang!
"""

import os

from dotenv import load_dotenv

# .env faylini yuklash (lokal ishlatishda). Hostingda muhit o'zgaruvchilari
# avtomatik o'qiladi, .env fayl bo'lmasligi mumkin.
load_dotenv()

# --- Maxfiy kalitlar ---
# @BotFather dan olingan Telegram bot tokeni
BOT_TOKEN: str = os.getenv("BOT_TOKEN", "").strip()
# https://aistudio.google.com/apikey dan olingan Gemini API kaliti
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "").strip()

# --- Gemini sozlamalari ---
# Bepul tarifda ishlaydigan tez model. Boshqa variant: "gemini-flash-latest"
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()

# --- Test sozlamalari ---
NUM_QUESTIONS: int = int(os.getenv("NUM_QUESTIONS", "30"))  # har bir testdagi savollar soni
BATCH_SIZE: int = int(os.getenv("BATCH_SIZE", "15"))        # Gemini'dan bir martada so'raladigan savollar
NUM_TOPICS: int = int(os.getenv("NUM_TOPICS", "8"))         # AI taklif qiladigan mavzular soni
QUESTION_TIME: int = int(os.getenv("QUESTION_TIME", "30"))  # har bir savolga beriladigan vaqt (soniya)

# --- Tillar ---
LANGUAGES: tuple[str, ...] = ("uz", "ru", "en")
DEFAULT_LANGUAGE: str = (os.getenv("DEFAULT_LANGUAGE", "uz").strip() or "uz")

# --- Ma'lumotlar bazasi ---
DB_PATH: str = os.getenv("DB_PATH", "bot.db")

# --- Hosting / ishga tushirish rejimi ---
# Agar WEBHOOK_URL berilsa (masalan Render'da) -> webhook rejimi,
# aks holda -> polling rejimi (lokal yoki VPS uchun qulay).
# Render platformasi xizmat URL'ini RENDER_EXTERNAL_URL orqali avtomatik beradi,
# shuning uchun uni zaxira variant sifatida ishlatamiz.
WEBHOOK_URL: str = (
    os.getenv("WEBHOOK_URL", "").strip()
    or os.getenv("RENDER_EXTERNAL_URL", "").strip()
).rstrip("/")
PORT: int = int(os.getenv("PORT", "8080"))

# --- Fanlar ro'yxati ---
# key -> {emoji, name{uz,ru,en}, (ixtiyoriy) sections}
SUBJECTS: dict[str, dict] = {
    "math": {
        "emoji": "🔢",
        "name": {"uz": "Matematika", "ru": "Математика", "en": "Mathematics"},
    },
    "ona_tili": {
        "emoji": "📖",
        "name": {"uz": "Ona tili", "ru": "Родной язык", "en": "Native language"},
    },
    "tarix": {
        "emoji": "🏛",
        "name": {"uz": "Tarix", "ru": "История", "en": "History"},
    },
    "ingliz": {
        "emoji": "🇬🇧",
        "name": {"uz": "Ingliz tili", "ru": "Английский язык", "en": "English"},
        "sections": {
            "ielts": "IELTS",
            "grammar": "Grammar",
        },
    },
    "fizika": {
        "emoji": "⚛️",
        "name": {"uz": "Fizika", "ru": "Физика", "en": "Physics"},
    },
    "biologiya": {
        "emoji": "🧬",
        "name": {"uz": "Biologiya", "ru": "Биология", "en": "Biology"},
    },
    "kimyo": {
        "emoji": "🧪",
        "name": {"uz": "Kimyo", "ru": "Химия", "en": "Chemistry"},
    },
    "geografiya": {
        "emoji": "🌍",
        "name": {"uz": "Geografiya", "ru": "География", "en": "Geography"},
    },
}

# --- Qiyinlik darajalari ---
DIFFICULTIES: dict[str, dict] = {
    "easy": {
        "emoji": "🟢",
        "name": {"uz": "Oson", "ru": "Лёгкий", "en": "Easy"},
    },
    "medium": {
        "emoji": "🟡",
        "name": {"uz": "O'rta", "ru": "Средний", "en": "Medium"},
    },
    "hard": {
        "emoji": "🔴",
        "name": {"uz": "Qiyin", "ru": "Сложный", "en": "Hard"},
    },
}


def subject_name(key: str, lang: str) -> str:
    """Fan nomini tanlangan tilda qaytarish (topilmasa key)."""
    info = SUBJECTS.get(key)
    if not info:
        return key
    name = info["name"]
    if isinstance(name, dict):
        return name.get(lang) or name.get("uz") or key
    return name


def subject_emoji(key: str) -> str:
    return SUBJECTS.get(key, {}).get("emoji", "")


def difficulty_label(key: str, lang: str) -> str:
    """Qiyinlik darajasini emoji + nom ko'rinishida qaytarish."""
    d = DIFFICULTIES.get(key)
    if not d:
        return key
    name = d["name"].get(lang) or d["name"].get("uz") or key
    return f"{d['emoji']} {name}"


def validate() -> None:
    """Bot ishga tushishidan oldin majburiy sozlamalarni tekshirish."""
    missing = []
    if not BOT_TOKEN:
        missing.append("BOT_TOKEN")
    if not GEMINI_API_KEY:
        missing.append("GEMINI_API_KEY")
    if missing:
        raise RuntimeError(
            "Quyidagi muhit o'zgaruvchilari berilmagan: "
            + ", ".join(missing)
            + ". .env faylini yoki hosting Environment Variables'ni tekshiring."
        )
