# DOMO Translation Bot 🌐

DOMO uchun Telegram tarjima boti. O'zbek tilida post matnini yuborsangiz, 3 tilga tarjima qiladi va tegishli kanallarga chiqaradi.

## Qanday ishlaydi?

1. ✍️ O'zbek tilida post matnini yuboring
2. 🤖 Bot 3 tilga tarjima qiladi (RU, QQP, EN)
3. 👀 Tarjimalarni ko'rib chiqing va tahrirlang
4. ✅ Tasdiqlang — post kanallarga chiqadi

## O'rnatish

### 1. Telegram Bot yaratish

1. [@BotFather](https://t.me/BotFather) ga `/newbot` yuboring
2. Bot nomini kiriting: `DOMO Translate Bot`
3. Username: `domo_translate_bot` (yoki boshqa)
4. Olingan tokenni saqlang

### 2. Kanallar sozlash

Har bir kanal uchun:
1. Kanalni yarating (agar hali yo'q bo'lsa)
2. Botni kanalga admin qilib qo'shing
3. "Post messages" ruxsatini bering

### 3. Railway.app ga deploy qilish

1. [Railway.app](https://railway.app) ga kiring (GitHub bilan)
2. "New Project" → "Deploy from GitHub repo"
3. Bu reponi ulang
4. Environment variables ni qo'shing:

| O'zgaruvchi | Qiymat |
|---|---|
| `BOT_TOKEN` | BotFather dan olingan token |
| `ANTHROPIC_API_KEY` | Anthropic API kalit |
| `ADMIN_IDS` | Sizning Telegram ID |
| `CHANNEL_RU` | `@domo_ru` |
| `CHANNEL_KAA` | `@domo_kaa` |
| `CHANNEL_EN` | `@domo_en` |
| `TRANSLATION_ENGINE` | `claude` |

5. Deploy bosing — tamom!

### Lokal ishga tushirish (test uchun)

```bash
# Klonlash
git clone https://github.com/your-repo/domo-translate-bot.git
cd domo-translate-bot

# Virtual muhit
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Kutubxonalar
pip install -r requirements.txt

# .env faylini yarating
cp .env.example .env
# .env ichida o'zgaruvchilarni to'ldiring

# Ishga tushirish
python bot.py
```

## Bot buyruqlari

| Buyruq | Tavsif |
|---|---|
| `/start` | Botni boshlash |
| `/help` | Yordam |
| `/channels` | Kanal sozlamalari |
| `/status` | Bot holati |

## Tarjima mexanizmlari

### Claude API (hozirgi)
- ✅ Barcha 3 til uchun yaxshi sifat
- ✅ Kontekstni tushunadi
- ✅ Emoji va formatlashni saqlaydi
- ⚠️ Qoraqalpoq tili uchun o'rtacha sifat

### Tilmoch.ai API (kelajak)
- ✅ Qoraqalpoq tiliga eng yaxshi sifat
- ✅ Turkiy tillarga ixtisoslashgan
- ⏳ API integratsiyasi tayyor bo'lganda qo'shiladi

## Arxitektura

```
Foydalanuvchi (O'zbekcha matn)
        │
        ▼
   Telegram Bot (aiogram)
        │
        ▼
   Tarjima mexanizmi
   (Claude API / Tilmoch.ai)
        │
        ▼
   Preview + Tahrirlash
        │
        ▼
   Tasdiqlash
        │
   ┌────┼────┐
   ▼    ▼    ▼
  RU   QQP   EN
 kanal kanal kanal
```

## Texnik ma'lumotlar

- **Til**: Python 3.12+
- **Framework**: aiogram 3.x
- **Tarjima**: Anthropic Claude API
- **Deploy**: Railway.app / Render.com
- **Litsenziya**: DOMO ichki foydalanish
