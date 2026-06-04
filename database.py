"""
SQLite ma'lumotlar bazasi (aiosqlite orqali asinxron).

Ikkita jadval:
  - users   : foydalanuvchilar (til sozlamasi bilan)
  - results : har bir tugatilgan test natijasi (statistika uchun)
"""

from __future__ import annotations

from datetime import datetime, timezone

import aiosqlite

import config


async def init_db() -> None:
    """Jadvallarni yaratish (agar mavjud bo'lmasa) va migratsiya."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id    INTEGER PRIMARY KEY,
                username   TEXT,
                first_name TEXT,
                language   TEXT DEFAULT 'uz',
                created_at TEXT
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS results (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                subject     TEXT NOT NULL,
                section     TEXT,
                topic       TEXT,
                difficulty  TEXT,
                total       INTEGER NOT NULL,
                correct     INTEGER NOT NULL,
                wrong       INTEGER NOT NULL,
                percentage  REAL NOT NULL,
                created_at  TEXT NOT NULL
            )
            """
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_results_user ON results(user_id)"
        )
        # --- Eski bazalar uchun migratsiya (ustun yo'q bo'lsa qo'shamiz) ---
        await _ensure_column(db, "users", "language", "TEXT DEFAULT 'uz'")
        await _ensure_column(db, "results", "difficulty", "TEXT")
        await db.commit()


async def _ensure_column(db, table: str, column: str, definition: str) -> None:
    """Jadvalda ustun bo'lmasa, ALTER TABLE bilan qo'shish."""
    async with db.execute(f"PRAGMA table_info({table})") as cur:
        cols = [row[1] for row in await cur.fetchall()]
    if column not in cols:
        await db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


async def add_user(user_id: int, username: str | None, first_name: str | None) -> None:
    """
    Foydalanuvchini qo'shish/yangilash. Yangi foydalanuvchining tili NULL
    qoldiriladi — shunda /start da til tanlash menyusi ko'rsatiladi.
    Mavjud foydalanuvchining tili o'zgartirilmaydi.
    """
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO users (user_id, username, first_name, language, created_at)
            VALUES (?, ?, ?, NULL, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name
            """,
            (user_id, username, first_name, _now()),
        )
        await db.commit()


async def get_language(user_id: int) -> str | None:
    """Foydalanuvchining tilini olish (yo'q bo'lsa None)."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        async with db.execute(
            "SELECT language FROM users WHERE user_id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
    if row and row[0] in config.LANGUAGES:
        return row[0]
    return None


async def set_language(user_id: int, language: str) -> None:
    """Foydalanuvchining tilini saqlash."""
    if language not in config.LANGUAGES:
        language = config.DEFAULT_LANGUAGE
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "UPDATE users SET language = ? WHERE user_id = ?", (language, user_id)
        )
        await db.commit()


async def save_result(
    user_id: int,
    subject: str,
    section: str | None,
    topic: str | None,
    difficulty: str | None,
    total: int,
    correct: int,
) -> None:
    """Test natijasini saqlash."""
    wrong = total - correct
    percentage = round((correct / total) * 100, 1) if total else 0.0
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO results
                (user_id, subject, section, topic, difficulty,
                 total, correct, wrong, percentage, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id, subject, section, topic, difficulty,
                total, correct, wrong, percentage, _now(),
            ),
        )
        await db.commit()


async def get_overall_stats(user_id: int) -> dict:
    """Umumiy statistika: testlar soni, savollar, o'rtacha foiz, eng yaxshi natija."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT
                COUNT(*)            AS tests,
                COALESCE(SUM(total), 0)   AS questions,
                COALESCE(SUM(correct), 0) AS correct,
                COALESCE(AVG(percentage), 0) AS avg_pct,
                COALESCE(MAX(percentage), 0) AS best_pct
            FROM results
            WHERE user_id = ?
            """,
            (user_id,),
        ) as cur:
            row = await cur.fetchone()
    return {
        "tests": row["tests"],
        "questions": row["questions"],
        "correct": row["correct"],
        "avg_pct": round(row["avg_pct"], 1),
        "best_pct": round(row["best_pct"], 1),
    }


async def get_subject_stats(user_id: int) -> list[dict]:
    """Fanlar bo'yicha o'rtacha natija."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT subject,
                   COUNT(*)              AS tests,
                   ROUND(AVG(percentage), 1) AS avg_pct
            FROM results
            WHERE user_id = ?
            GROUP BY subject
            ORDER BY avg_pct DESC
            """,
            (user_id,),
        ) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def get_recent_results(user_id: int, limit: int = 5) -> list[dict]:
    """So'nggi testlar ro'yxati."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT subject, section, topic, difficulty, total, correct, percentage, created_at
            FROM results
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (user_id, limit),
        ) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]


def _now() -> str:
    """Hozirgi vaqt (ISO formatda, UTC)."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
