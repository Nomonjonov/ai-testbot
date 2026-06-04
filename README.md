# 🤖 AI Test Bot

Gemini AI'ga ulangan Telegram test boti. Foydalanuvchi til → fan → mavzu →
qiyinlik tanlaydi, AI 30 ta A/B/C/D test savolini generatsiya qiladi, har bir
savolga vaqt cheklovi bo'ladi, test yakunida natija, foiz va xatolar tahlilini
ko'rsatadi. Natijalar saqlanadi ("Mening natijalarim").

## ✨ Imkoniyatlar

- 📚 8 ta fan: Matematika, Ona tili, Tarix, Ingliz tili (IELTS & Grammar), Fizika, Biologiya, Kimyo, Geografiya
- 🌐 **3 til:** O'zbekcha 🇺🇿 / Русский 🇷🇺 / English 🇬🇧 (interfeys va savollar tanlangan tilda)
- 🎯 **3 qiyinlik darajasi:** 🟢 Oson / 🟡 O'rta / 🔴 Qiyin
- ⏱ **Vaqt cheklovi:** har bir savolga belgilangan vaqt (default 30s), tugasa avtomatik keyingisiga o'tadi
- 🧠 AI (Gemini): mavzular taklif qiladi, savol tuzadi, xatolarni tushuntiradi
- 📊 Statistika: umumiy, fanlar bo'yicha, so'nggi testlar
- ⚙️ Polling va Webhook rejimlari (lokal yoki hosting)

## 🗂 Fayllar

| Fayl | Vazifasi |
|------|----------|
| `bot.py` | Ishga tushirish nuqtasi (polling/webhook) |
| `config.py` | Sozlamalar, fanlar, qiyinlik darajalari |
| `i18n.py` | Ko'p tillilik (uz/ru/en tarjimalar) |
| `database.py` | SQLite (foydalanuvchilar + til, natijalar) |
| `gemini_client.py` | Gemini AI (til + qiyinlikni hisobga oladi) |
| `handlers.py` | Suhbat oqimi (menyu → test → natija + timer) |
| `keyboards.py` | Inline tugmalar |

## 🔄 Foydalanuvchi oqimi

```
/start
 ├── (birinchi marta) 🌐 Til tanlash (uz/ru/en)
 └── Asosiy menyu
      ├── 📚 Test boshlash → Fan → (Ingliz: IELTS/Grammar) → 🎯 Qiyinlik → AI mavzu → 30 savol
      │      └── Har bir savolda ⏱ vaqt; tugasa avtomatik keyingisiga o'tadi
      │      └── Yakunda: ✅to'g'ri/❌xato/📊foiz + 🧠AI tavsiyasi + 📝xatolar tahlili
      ├── 📊 Mening natijalarim → umumiy + fanlar bo'yicha + so'nggi testlar
      ├── ℹ️ Bot haqida
      └── 🌐 Til / Language → tilni o'zgartirish
```

## 🔑 1. Kalitlarni olish

1. **Bot tokeni** — Telegramda [@BotFather](https://t.me/BotFather) ga `/newbot` yozing.
2. **Gemini API kaliti** — [Google AI Studio](https://aistudio.google.com/apikey) → *Create API key* (bepul).

## 💻 2. Lokal ishga tushirish

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env             # .env ichiga BOT_TOKEN va GEMINI_API_KEY yozing
python bot.py
```

`.env` da `WEBHOOK_URL` bo'sh bo'lsa, bot **polling** rejimida ishlaydi — lokal sinov uchun ideal.

## ☁️ 3. Bepul 24/7 hosting

### Variant A — Render.com (tavsiya, eng oson, kredit karta shart emas)

1. Kodni GitHub repozitoriyasiga joylang (`.env` ni emas — u `.gitignore` da).
2. [render.com](https://render.com) → **New → Web Service** → repozitoriyani ulang.
3. **Build:** `pip install -r requirements.txt` · **Start:** `python bot.py` · **Plan:** Free
4. **Environment** bo'limida qo'shing: `BOT_TOKEN`, `GEMINI_API_KEY`.
   `WEBHOOK_URL` ni kiritish **shart emas** — bot Render bergan `RENDER_EXTERNAL_URL` ni avtomatik oladi.
5. Deploy. (Repoda `render.yaml` bo'lsa, Render sozlamalarni avtomatik o'qiydi.)

> ⚠️ **Uxlab qolish:** Render bepul xizmati 15 daq harakatsizlikdan keyin "uxlaydi".
> [cron-job.org](https://cron-job.org) yoki [UptimeRobot](https://uptimerobot.com) da har 10 daq
> xizmat URL'ingizga (`https://<app>.onrender.com`) ping yuboring.

> ⚠️ **Ma'lumotlar bazasi:** Render bepul diski qayta deploy'da tozalanadi (SQLite yo'qoladi).
> Doimiy saqlash kerak bo'lsa — Persistent Disk / tashqi Postgres yoki Variant B'ni tanlang.

### Variant B — Oracle Cloud "Always Free" VM (eng ishonchli, ma'lumot yo'qolmaydi)

`systemd` xizmati sifatida polling rejimida ishlatiladi (batafsil `systemd` namunasi quyida).

```ini
# /etc/systemd/system/testbot.service
[Unit]
Description=AI Test Bot
After=network.target

[Service]
WorkingDirectory=/home/ubuntu/test-bot
ExecStart=/home/ubuntu/test-bot/.venv/bin/python bot.py
Restart=always
EnvironmentFile=/home/ubuntu/test-bot/.env

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now testbot
sudo journalctl -u testbot -f
```

## ⚙️ Sozlamalar (env)

| O'zgaruvchi | Default | Izoh |
|-------------|---------|------|
| `BOT_TOKEN` | — | **Majburiy** |
| `GEMINI_API_KEY` | — | **Majburiy** |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Gemini modeli |
| `NUM_QUESTIONS` | `30` | Testdagi savollar soni |
| `BATCH_SIZE` | `15` | AI'dan bir martada so'raladigan savollar |
| `NUM_TOPICS` | `8` | Taklif qilinadigan mavzular soni |
| `QUESTION_TIME` | `30` | Har bir savolga vaqt (soniya) |
| `DEFAULT_LANGUAGE` | `uz` | Standart til (uz/ru/en) |
| `WEBHOOK_URL` | — | Berilsa webhook, aks holda polling |
| `PORT` | `8080` | Webhook porti |

## 📌 Eslatma

- Vaqt cheklovi `python-telegram-bot[job-queue]` (JobQueue) orqali ishlaydi — `requirements.txt` da yoqilgan.
- Gemini bepul tarifida so'rovlar soniga limit bor (RPM/RPD). Ko'p foydalanuvchi bo'lsa, limitga yetishi mumkin.
- Savollar AI tomonidan generatsiya qilinadi — kamdan-kam hollarda noaniqlik bo'lishi mumkin.
