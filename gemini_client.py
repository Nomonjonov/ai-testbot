"""
Gemini AI bilan ishlash.

Yangi rasmiy SDK ishlatiladi: `google-genai` (from google import genai).
Strukturali (JSON) javob olish uchun response_schema bilan so'rov yuboriladi,
shunda javobni ishonchli tarzda parslash mumkin.

Funksiyalar (barchasi til `lang` va qiyinlik `difficulty` ni hisobga oladi):
  - generate_topics(...)    -> mavzular ro'yxati (list[str])
  - generate_questions(...) -> savollar ro'yxati (list[dict])
  - generate_feedback(...)  -> test bo'yicha qisqa AI tavsiya (str)
"""

from __future__ import annotations

import json
import logging

from google import genai
from google.genai import types
from pydantic import BaseModel

import config
from i18n import LANG_PROMPT

logger = logging.getLogger(__name__)

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    """Gemini klientini bir marta yaratib, qayta ishlatish."""
    global _client
    if _client is None:
        _client = genai.Client(api_key=config.GEMINI_API_KEY)
    return _client


# --- Savol uchun JSON sxema (Pydantic modeli) ---
class _Question(BaseModel):
    question: str
    A: str
    B: str
    C: str
    D: str
    correct: str  # "A", "B", "C" yoki "D"
    explanation: str


def _is_english(subject_key: str) -> bool:
    return subject_key == "ingliz"


def _difficulty_prompt(difficulty: str, lang: str) -> str:
    """Qiyinlik darajasi bo'yicha AI ko'rsatmasi."""
    mapping = {
        "easy": {
            "uz": "Savollar OSON darajada bo'lsin (boshlang'ich, asosiy tushunchalar).",
            "ru": "Вопросы должны быть ЛЁГКОГО уровня (базовые понятия).",
            "en": "Questions should be EASY level (basic concepts).",
        },
        "medium": {
            "uz": "Savollar O'RTA darajada bo'lsin (standart, amaliy).",
            "ru": "Вопросы должны быть СРЕДНЕГО уровня (стандартные, практические).",
            "en": "Questions should be MEDIUM level (standard, applied).",
        },
        "hard": {
            "uz": "Savollar QIYIN darajada bo'lsin (chuqur, tahliliy, murakkab).",
            "ru": "Вопросы должны быть СЛОЖНОГО уровня (глубокие, аналитические).",
            "en": "Questions should be HARD level (deep, analytical, complex).",
        },
    }
    block = mapping.get(difficulty, mapping["medium"])
    return block.get(lang) or block.get("uz")


async def generate_topics(
    subject_key: str,
    section_name: str | None = None,
    lang: str = "uz",
) -> list[str]:
    """Fan (va bo'lim) bo'yicha test mavzularini taklif qilish."""
    subject_name = config.subject_name(subject_key, lang)
    target = subject_name + (f" - {section_name}" if section_name else "")

    if _is_english(subject_key):
        lang_note = "Topic names must be in English."
    else:
        lang_note = f"Topic names must be {LANG_PROMPT.get(lang, LANG_PROMPT['uz'])}."

    prompt = (
        f"Suggest {config.NUM_TOPICS} test topics suitable for students "
        f"for the subject \"{target}\". {lang_note} "
        f"Each topic should be short (2-5 words) and specific. "
        f"Topics must differ from each other and cover the main areas. "
        f"Return as a JSON array of strings."
    )

    cfg = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=list[str],
        temperature=1.0,
    )

    client = _get_client()
    resp = await client.aio.models.generate_content(
        model=config.GEMINI_MODEL,
        contents=prompt,
        config=cfg,
    )
    topics = _safe_json(resp.text)
    if not isinstance(topics, list):
        raise ValueError("Gemini mavzularni noto'g'ri formatda qaytardi.")
    # Tozalash: bo'sh va takror mavzularni olib tashlash
    seen: set[str] = set()
    clean: list[str] = []
    for item in topics:
        item = str(item).strip()
        if item and item.lower() not in seen:
            seen.add(item.lower())
            clean.append(item)
    return clean[: config.NUM_TOPICS]


async def generate_questions(
    subject_key: str,
    section_name: str | None,
    topic: str,
    difficulty: str = "medium",
    lang: str = "uz",
    count: int | None = None,
) -> list[dict]:
    """
    Berilgan mavzu bo'yicha A/B/C/D variantli savollar generatsiya qilish.

    Ishonchlilik uchun savollar BATCH_SIZE bo'laklarda so'raladi
    (bir martada 30 ta so'rasak, javob uzilib qolishi mumkin).
    """
    count = count or config.NUM_QUESTIONS
    questions: list[dict] = []
    attempts = 0
    max_attempts = (count // config.BATCH_SIZE) + 4

    while len(questions) < count and attempts < max_attempts:
        attempts += 1
        need = min(config.BATCH_SIZE, count - len(questions))
        try:
            batch = await _generate_batch(
                subject_key, section_name, topic, difficulty, lang, need, len(questions)
            )
        except Exception:  # noqa: BLE001
            logger.exception("Savollar bo'lagini generatsiya qilishda xatolik")
            batch = []
        questions.extend(batch)
        if not batch and attempts >= 3 and not questions:
            break

    return questions[:count]


async def _generate_batch(
    subject_key: str,
    section_name: str | None,
    topic: str,
    difficulty: str,
    lang: str,
    count: int,
    already: int,
) -> list[dict]:
    """Bitta bo'lak savollarni generatsiya qilish."""
    subject_name = config.subject_name(subject_key, lang)
    target = subject_name + (f" ({section_name})" if section_name else "")
    diff_note = _difficulty_prompt(difficulty, lang)

    if _is_english(subject_key):
        lang_note = (
            "The question text and options must be in ENGLISH. "
            f"The 'explanation' field must be {LANG_PROMPT.get(lang, LANG_PROMPT['uz'])}."
        )
    else:
        target_lang = LANG_PROMPT.get(lang, LANG_PROMPT["uz"])
        lang_note = f"The question, options and explanation must all be {target_lang}."

    prompt = (
        f"Create {count} multiple-choice test questions for the subject "
        f"\"{target}\", topic \"{topic}\".\n"
        f"Requirements:\n"
        f"- Each question has exactly 4 options: A, B, C, D.\n"
        f"- Only one correct answer (put the letter A/B/C/D in the 'correct' field).\n"
        f"- In the 'explanation' field, explain in 1-2 sentences why the answer is correct.\n"
        f"- Questions must not repeat each other.\n"
        f"- {diff_note}\n"
        f"- {lang_note}\n"
        f"- This is a set starting from question {already + 1}, make them different "
        f"from previous ones."
    )

    cfg = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=list[_Question],
        temperature=1.0,
    )

    client = _get_client()
    resp = await client.aio.models.generate_content(
        model=config.GEMINI_MODEL,
        contents=prompt,
        config=cfg,
    )
    data = _safe_json(resp.text)
    if not isinstance(data, list):
        return []

    result: list[dict] = []
    for item in data:
        q = _normalize_question(item)
        if q:
            result.append(q)
    return result


async def generate_feedback(
    subject_key: str,
    topic: str,
    correct: int,
    total: int,
    wrong_topics: list[str],
    lang: str = "uz",
) -> str:
    """Test yakunida qisqa, rag'batlantiruvchi AI tavsiya."""
    subject_name = config.subject_name(subject_key, lang)
    if wrong_topics:
        wrong_note = "The user made mistakes in these questions: " + "; ".join(wrong_topics[:8])
    else:
        wrong_note = "The user answered almost everything correctly."

    target_lang = LANG_PROMPT.get(lang, LANG_PROMPT["uz"])
    prompt = (
        f"A student took a test on the subject {subject_name}, topic \"{topic}\". "
        f"Result: {correct} correct out of {total}. {wrong_note}. "
        f"Write a short, warm and useful piece of advice in 2-3 sentences, "
        f"{target_lang}: tell them what to focus on. You may use emojis."
    )
    try:
        client = _get_client()
        resp = await client.aio.models.generate_content(
            model=config.GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.8),
        )
        return (resp.text or "").strip()
    except Exception:  # noqa: BLE001
        logger.exception("AI tavsiyasini olishda xatolik")
        return ""


# --- Yordamchi funksiyalar ---

def _safe_json(text: str | None):
    """Gemini javobini xavfsiz parslash."""
    if not text:
        return None
    text = text.strip()
    # Ba'zan model ```json ... ``` ichida qaytaradi — tozalaymiz
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        logger.warning("JSON parslab bo'lmadi: %s", text[:200])
        return None


def _normalize_question(item: dict) -> dict | None:
    """Bitta savolni tekshirish va standart ko'rinishga keltirish."""
    if not isinstance(item, dict):
        return None
    try:
        question = str(item["question"]).strip()
        options = {
            "A": str(item["A"]).strip(),
            "B": str(item["B"]).strip(),
            "C": str(item["C"]).strip(),
            "D": str(item["D"]).strip(),
        }
        correct = str(item["correct"]).strip().upper()[:1]
        explanation = str(item.get("explanation", "")).strip()
    except (KeyError, TypeError):
        return None

    if not question or correct not in ("A", "B", "C", "D"):
        return None
    if not all(options.values()):
        return None

    return {
        "question": question,
        "options": options,
        "correct": correct,
        "explanation": explanation,
    }
