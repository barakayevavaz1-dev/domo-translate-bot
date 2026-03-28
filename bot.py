"""
DOMO Translation Bot
====================
O'zbek tilida matn yuborsangiz, 3 tilga tarjima qiladi:
- Rus tiliga
- Qoraqalpoq tiliga  
- Ingliz tiliga

Tarjimalarni ko'rib chiqib, tahrirlash va tasdiqlash imkoniyati.
Tasdiqlangandan keyin tegishli kanallarga post chiqariladi.

Tarjima mexanizmi: Claude API (Anthropic) — gibrid yondashuv,
Tilmoch.ai API tayyor bo'lganda unga o'tish mumkin.
"""

import os
import logging
import asyncio
import json
from datetime import datetime

from aiogram import Bot, Dispatcher, Router, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    CallbackQuery,
)
from aiogram.enums import ParseMode

import anthropic

# ─── Config ───────────────────────────────────────────────────────────

BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "YOUR_ANTHROPIC_KEY")
ADMIN_IDS = [int(x) for x in os.environ.get("ADMIN_IDS", "").split(",") if x.strip()]

# Kanal IDlari (@ yoki raqamli ID)
CHANNEL_RU = os.environ.get("CHANNEL_RU", "@domo_ru")        # Rus tili kanali
CHANNEL_KAA = os.environ.get("CHANNEL_KAA", "@domo_kaa")     # Qoraqalpoq tili kanali
CHANNEL_EN = os.environ.get("CHANNEL_EN", "@domo_en")        # Ingliz tili kanali

# Tarjima mexanizmi: "claude" yoki "tilmoch" (kelajakda)
TRANSLATION_ENGINE = os.environ.get("TRANSLATION_ENGINE", "claude")

# Tilmoch.ai API (kelajak uchun)
TILMOCH_API_KEY = os.environ.get("TILMOCH_API_KEY", "")
TILMOCH_API_URL = os.environ.get("TILMOCH_API_URL", "https://tilmoch.ai/api/translate")

# ─── Logging ──────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("domo_translate_bot")

# ─── Bot & Dispatcher ────────────────────────────────────────────────

bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()
dp.include_router(router)

claude_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# ─── States ───────────────────────────────────────────────────────────

class TranslationStates(StatesGroup):
    waiting_text = State()           # Matn kutilmoqda
    reviewing = State()              # Ko'rib chiqish
    editing_ru = State()             # Ruscha tahrirlanmoqda
    editing_kaa = State()            # Qoraqalpaqcha tahrirlanmoqda
    editing_en = State()             # Inglizcha tahrirlanmoqda


# ─── In-memory storage for translations ──────────────────────────────

translations_store: dict[int, dict] = {}
# Format: {user_id: {
#     "original": str,
#     "ru": str,
#     "kaa": str,
#     "en": str,
#     "message_id": int,
#     "created_at": str
# }}


# ─── Translation Functions ───────────────────────────────────────────

async def translate_with_claude(text: str) -> dict[str, str]:
    """
    Claude API orqali 3 tilga tarjima qiladi.
    JSON formatida: {"ru": "...", "kaa": "...", "en": "..."}
    """
    system_prompt = """Sen professional tarjimon sifatida ishlaysan. 
Senga o'zbek tilida matn beriladi. Uni quyidagi 3 tilga tarjima qil:

1. **Rus tiliga** (ru) — tabiiy, professional rus tilida
2. **Qoraqalpoq tiliga** (kaa) — qoraqalpoq latin yozuvida, tabiiy qoraqalpoq tilida
3. **Ingliz tiliga** (en) — professional, tabiiy ingliz tilida

MUHIM QOIDALAR:
- Tarjima mazmunini buzma, original ma'noni saqla
- Har bir til uchun tabiiy va silliq tarjima qil
- Qoraqalpoq tilida FAQAT lotin yozuvini ishlat
- Emoji va formatlashni saqlab qol (agar original matnda bo'lsa)
- Telegram post sifatida mos kelishi kerak
- HTML teglarini saqla (agar bor bo'lsa: <b>, <i>, <a> va h.k.)

Javobni FAQAT quyidagi JSON formatida ber, boshqa hech narsa yozma:
{"ru": "tarjima_ruscha", "kaa": "tarjima_qoraqalpaqcha", "en": "tarjima_inglizcha"}"""

    try:
        response = claude_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            system=system_prompt,
            messages=[
                {"role": "user", "content": f"Quyidagi matnni 3 tilga tarjima qil:\n\n{text}"}
            ],
        )
        
        result_text = response.content[0].text.strip()
        
        # JSON ni parse qilish
        # Ba'zan Claude ```json ... ``` ichida qaytaradi
        if result_text.startswith("```"):
            result_text = result_text.split("```")[1]
            if result_text.startswith("json"):
                result_text = result_text[4:]
            result_text = result_text.strip()
        
        translations = json.loads(result_text)
        
        # Validatsiya
        for key in ["ru", "kaa", "en"]:
            if key not in translations:
                translations[key] = f"[Tarjima topilmadi: {key}]"
        
        return translations
    
    except json.JSONDecodeError as e:
        logger.error(f"JSON parse error: {e}, raw: {result_text[:200]}")
        return {
            "ru": "[Tarjima xatosi - qaytadan urinib ko'ring]",
            "kaa": "[Tarjima xatosi - qaytadan urinib ko'ring]",
            "en": "[Translation error - please try again]",
        }
    except Exception as e:
        logger.error(f"Translation error: {e}")
        return {
            "ru": f"[Xato: {str(e)[:100]}]",
            "kaa": f"[Xato: {str(e)[:100]}]",
            "en": f"[Error: {str(e)[:100]}]",
        }


async def translate_with_tilmoch(text: str) -> dict[str, str]:
    """
    Tilmoch.ai API orqali tarjima (kelajak uchun).
    API hujjatlari tayyor bo'lganda implementatsiya qilinadi.
    """
    # TODO: Tilmoch.ai API integratsiyasi
    # Hozircha Claude ga yo'naltiramiz
    logger.warning("Tilmoch API hali tayyor emas, Claude ga o'tyapti")
    return await translate_with_claude(text)


async def translate_text(text: str) -> dict[str, str]:
    """Sozlangan mexanizmga qarab tarjima qiladi."""
    if TRANSLATION_ENGINE == "tilmoch" and TILMOCH_API_KEY:
        return await translate_with_tilmoch(text)
    return await translate_with_claude(text)


# ─── Keyboard Builders ───────────────────────────────────────────────

def build_preview_keyboard() -> InlineKeyboardMarkup:
    """Ko'rib chiqish uchun tugmalar."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✏️ RU tahrirlash", callback_data="edit_ru"),
            InlineKeyboardButton(text="✏️ QQP tahrirlash", callback_data="edit_kaa"),
            InlineKeyboardButton(text="✏️ EN tahrirlash", callback_data="edit_en"),
        ],
        [
            InlineKeyboardButton(text="🔄 Qayta tarjima", callback_data="retranslate"),
        ],
        [
            InlineKeyboardButton(text="✅ Barchasini tasdiqlash", callback_data="approve_all"),
        ],
        [
            InlineKeyboardButton(text="📤 Faqat RU", callback_data="post_ru"),
            InlineKeyboardButton(text="📤 Faqat QQP", callback_data="post_kaa"),
            InlineKeyboardButton(text="📤 Faqat EN", callback_data="post_en"),
        ],
        [
            InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel"),
        ],
    ])


def build_cancel_keyboard() -> InlineKeyboardMarkup:
    """Tahrirlash paytida bekor qilish."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_edit")],
    ])


# ─── Format Helpers ──────────────────────────────────────────────────

def format_preview(original: str, translations: dict) -> str:
    """Preview xabarini formatlaydi."""
    preview = (
        f"📝 <b>Original (O'zbekcha):</b>\n"
        f"{original}\n\n"
        f"{'─' * 30}\n\n"
        f"🇷🇺 <b>Ruscha:</b>\n"
        f"{translations['ru']}\n\n"
        f"{'─' * 30}\n\n"
        f"🏳️ <b>Qoraqalpaqcha:</b>\n"
        f"{translations['kaa']}\n\n"
        f"{'─' * 30}\n\n"
        f"🇬🇧 <b>Inglizcha:</b>\n"
        f"{translations['en']}"
    )
    return preview


# ─── Handlers ─────────────────────────────────────────────────────────

@router.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    """Bot boshlanishi."""
    if ADMIN_IDS and message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ Sizga ruxsat berilmagan. Admin bilan bog'laning.")
        return

    await state.set_state(TranslationStates.waiting_text)
    await message.answer(
        "👋 <b>DOMO Translation Bot</b>\n\n"
        "O'zbek tilida post matnini yuboring.\n"
        "Men uni 3 tilga tarjima qilaman:\n"
        "🇷🇺 Ruscha\n"
        "🏳️ Qoraqalpaqcha\n"
        "🇬🇧 Inglizcha\n\n"
        "Tarjimalarni ko'rib chiqib, tahrirlashingiz va kanallarga "
        "chiqarishingiz mumkin.\n\n"
        "📌 Buyruqlar:\n"
        "/start — Qayta boshlash\n"
        "/help — Yordam\n"
        "/channels — Kanal sozlamalari\n"
        "/status — Bot holati"
    )


@router.message(Command("help"))
async def cmd_help(message: types.Message):
    """Yordam."""
    await message.answer(
        "📖 <b>Qo'llanma</b>\n\n"
        "1️⃣ Post matnini o'zbek tilida yuboring\n"
        "2️⃣ Bot 3 tilga tarjima qiladi\n"
        "3️⃣ Har bir tarjimani tahrirlashingiz mumkin\n"
        "4️⃣ Tayyor bo'lgach, tasdiqlang\n"
        "5️⃣ Post kanallarga chiqariladi\n\n"
        "✏️ Tahrirlash — tegishli til tugmasini bosing\n"
        "🔄 Qayta tarjima — boshqatdan tarjima qiladi\n"
        "📤 Alohida yuborish — faqat bitta tilga\n"
        "✅ Barchasini tasdiqlash — hammasi kanallarga"
    )


@router.message(Command("channels"))
async def cmd_channels(message: types.Message):
    """Kanal sozlamalarini ko'rsatadi."""
    await message.answer(
        "📡 <b>Kanal sozlamalari:</b>\n\n"
        f"🇷🇺 Ruscha: {CHANNEL_RU}\n"
        f"🏳️ Qoraqalpaqcha: {CHANNEL_KAA}\n"
        f"🇬🇧 Inglizcha: {CHANNEL_EN}\n\n"
        f"⚙️ Tarjima mexanizmi: <code>{TRANSLATION_ENGINE}</code>\n\n"
        "Sozlamalarni o'zgartirish uchun environment o'zgaruvchilarini "
        "yangilang va botni qayta ishga tushiring."
    )


@router.message(Command("status"))
async def cmd_status(message: types.Message):
    """Bot holatini ko'rsatadi."""
    engine_status = "✅ Claude API" if TRANSLATION_ENGINE == "claude" else "✅ Tilmoch.ai API"
    channels_ok = all([CHANNEL_RU, CHANNEL_KAA, CHANNEL_EN])
    
    await message.answer(
        "📊 <b>Bot holati:</b>\n\n"
        f"🤖 Tarjima: {engine_status}\n"
        f"📡 Kanallar: {'✅ Sozlangan' if channels_ok else '⚠️ Sozlanmagan'}\n"
        f"👥 Adminlar: {len(ADMIN_IDS)} ta\n"
        f"📝 Aktiv tarjimalar: {len(translations_store)} ta"
    )


# ─── Main text handler (translation trigger) ─────────────────────────

@router.message(
    StateFilter(TranslationStates.waiting_text, None),
    F.text,
    ~F.text.startswith("/"),
)
async def handle_text_for_translation(message: types.Message, state: FSMContext):
    """Matnni qabul qilib tarjima qiladi."""
    if ADMIN_IDS and message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ Sizga ruxsat berilmagan.")
        return

    original_text = message.text
    user_id = message.from_user.id

    # Tarjima jarayoni haqida xabar
    status_msg = await message.answer(
        "⏳ <b>Tarjima qilinyapti...</b>\n\n"
        "🇷🇺 Ruscha... ⏳\n"
        "🏳️ Qoraqalpaqcha... ⏳\n"
        "🇬🇧 Inglizcha... ⏳"
    )

    # Tarjima qilish
    translations = await translate_text(original_text)

    # Saqlash
    translations_store[user_id] = {
        "original": original_text,
        "ru": translations["ru"],
        "kaa": translations["kaa"],
        "en": translations["en"],
        "created_at": datetime.now().isoformat(),
    }

    # Status xabarni o'chirish
    await status_msg.delete()

    # Preview ko'rsatish
    preview_text = format_preview(original_text, translations)
    preview_msg = await message.answer(
        preview_text,
        reply_markup=build_preview_keyboard(),
    )

    translations_store[user_id]["message_id"] = preview_msg.message_id

    await state.set_state(TranslationStates.reviewing)


# ─── Callback handlers ───────────────────────────────────────────────

@router.callback_query(F.data == "edit_ru")
async def cb_edit_ru(callback: CallbackQuery, state: FSMContext):
    """Ruscha tarjimani tahrirlash."""
    user_id = callback.from_user.id
    data = translations_store.get(user_id)
    if not data:
        await callback.answer("⚠️ Tarjima topilmadi. /start bosing.")
        return

    await callback.message.answer(
        f"✏️ <b>Ruscha tarjimani tahrirlang:</b>\n\n"
        f"Hozirgi:\n{data['ru']}\n\n"
        f"Yangi variantni yuboring:",
        reply_markup=build_cancel_keyboard(),
    )
    await state.set_state(TranslationStates.editing_ru)
    await callback.answer()


@router.callback_query(F.data == "edit_kaa")
async def cb_edit_kaa(callback: CallbackQuery, state: FSMContext):
    """Qoraqalpaqcha tarjimani tahrirlash."""
    user_id = callback.from_user.id
    data = translations_store.get(user_id)
    if not data:
        await callback.answer("⚠️ Tarjima topilmadi. /start bosing.")
        return

    await callback.message.answer(
        f"✏️ <b>Qoraqalpaqcha tarjimani tahrirlang:</b>\n\n"
        f"Hozirgi:\n{data['kaa']}\n\n"
        f"Yangi variantni yuboring:",
        reply_markup=build_cancel_keyboard(),
    )
    await state.set_state(TranslationStates.editing_kaa)
    await callback.answer()


@router.callback_query(F.data == "edit_en")
async def cb_edit_en(callback: CallbackQuery, state: FSMContext):
    """Inglizcha tarjimani tahrirlash."""
    user_id = callback.from_user.id
    data = translations_store.get(user_id)
    if not data:
        await callback.answer("⚠️ Tarjima topilmadi. /start bosing.")
        return

    await callback.message.answer(
        f"✏️ <b>Inglizcha tarjimani tahrirlang:</b>\n\n"
        f"Hozirgi:\n{data['en']}\n\n"
        f"Yangi variantni yuboring:",
        reply_markup=build_cancel_keyboard(),
    )
    await state.set_state(TranslationStates.editing_en)
    await callback.answer()


# ─── Edit text handlers ──────────────────────────────────────────────

@router.message(StateFilter(TranslationStates.editing_ru), F.text)
async def handle_edit_ru(message: types.Message, state: FSMContext):
    """Ruscha tarjimani yangilaydi."""
    user_id = message.from_user.id
    if user_id not in translations_store:
        await message.answer("⚠️ Tarjima topilmadi. /start bosing.")
        return

    translations_store[user_id]["ru"] = message.text
    
    preview_text = format_preview(
        translations_store[user_id]["original"],
        translations_store[user_id],
    )
    await message.answer(
        "✅ Ruscha tarjima yangilandi!\n\n" + preview_text,
        reply_markup=build_preview_keyboard(),
    )
    await state.set_state(TranslationStates.reviewing)


@router.message(StateFilter(TranslationStates.editing_kaa), F.text)
async def handle_edit_kaa(message: types.Message, state: FSMContext):
    """Qoraqalpaqcha tarjimani yangilaydi."""
    user_id = message.from_user.id
    if user_id not in translations_store:
        await message.answer("⚠️ Tarjima topilmadi. /start bosing.")
        return

    translations_store[user_id]["kaa"] = message.text
    
    preview_text = format_preview(
        translations_store[user_id]["original"],
        translations_store[user_id],
    )
    await message.answer(
        "✅ Qoraqalpaqcha tarjima yangilandi!\n\n" + preview_text,
        reply_markup=build_preview_keyboard(),
    )
    await state.set_state(TranslationStates.reviewing)


@router.message(StateFilter(TranslationStates.editing_en), F.text)
async def handle_edit_en(message: types.Message, state: FSMContext):
    """Inglizcha tarjimani yangilaydi."""
    user_id = message.from_user.id
    if user_id not in translations_store:
        await message.answer("⚠️ Tarjima topilmadi. /start bosing.")
        return

    translations_store[user_id]["en"] = message.text
    
    preview_text = format_preview(
        translations_store[user_id]["original"],
        translations_store[user_id],
    )
    await message.answer(
        "✅ Inglizcha tarjima yangilandi!\n\n" + preview_text,
        reply_markup=build_preview_keyboard(),
    )
    await state.set_state(TranslationStates.reviewing)


# ─── Retranslate ──────────────────────────────────────────────────────

@router.callback_query(F.data == "retranslate")
async def cb_retranslate(callback: CallbackQuery, state: FSMContext):
    """Qayta tarjima qiladi."""
    user_id = callback.from_user.id
    data = translations_store.get(user_id)
    if not data:
        await callback.answer("⚠️ Tarjima topilmadi.")
        return

    await callback.answer("🔄 Qayta tarjima qilinyapti...")
    
    status_msg = await callback.message.answer("⏳ Qayta tarjima qilinyapti...")

    translations = await translate_text(data["original"])

    translations_store[user_id].update({
        "ru": translations["ru"],
        "kaa": translations["kaa"],
        "en": translations["en"],
    })

    await status_msg.delete()

    preview_text = format_preview(data["original"], translations)
    await callback.message.answer(
        "🔄 Qayta tarjima qilindi!\n\n" + preview_text,
        reply_markup=build_preview_keyboard(),
    )
    await state.set_state(TranslationStates.reviewing)


# ─── Post to channels ────────────────────────────────────────────────

async def post_to_channel(channel_id: str, text: str) -> bool:
    """Kanalga post yuboradi."""
    try:
        await bot.send_message(
            chat_id=channel_id,
            text=text,
            parse_mode=ParseMode.HTML,
        )
        return True
    except Exception as e:
        logger.error(f"Channel post error ({channel_id}): {e}")
        return False


@router.callback_query(F.data == "approve_all")
async def cb_approve_all(callback: CallbackQuery, state: FSMContext):
    """Barcha tarjimalarni tasdiqlaydi va kanallarga yuboradi."""
    user_id = callback.from_user.id
    data = translations_store.get(user_id)
    if not data:
        await callback.answer("⚠️ Tarjima topilmadi.")
        return

    await callback.answer("📤 Kanallarga yuborilmoqda...")

    results = []
    
    # Ruscha
    ok_ru = await post_to_channel(CHANNEL_RU, data["ru"])
    results.append(f"🇷🇺 {CHANNEL_RU}: {'✅' if ok_ru else '❌'}")

    # Qoraqalpaqcha
    ok_kaa = await post_to_channel(CHANNEL_KAA, data["kaa"])
    results.append(f"🏳️ {CHANNEL_KAA}: {'✅' if ok_kaa else '❌'}")

    # Inglizcha
    ok_en = await post_to_channel(CHANNEL_EN, data["en"])
    results.append(f"🇬🇧 {CHANNEL_EN}: {'✅' if ok_en else '❌'}")

    result_text = "\n".join(results)
    
    await callback.message.answer(
        f"📤 <b>Yuborish natijalari:</b>\n\n{result_text}\n\n"
        f"Yangi post uchun matn yuboring."
    )

    # Tozalash
    translations_store.pop(user_id, None)
    await state.set_state(TranslationStates.waiting_text)


@router.callback_query(F.data.startswith("post_"))
async def cb_post_single(callback: CallbackQuery, state: FSMContext):
    """Faqat bitta tilga yuboradi."""
    user_id = callback.from_user.id
    data = translations_store.get(user_id)
    if not data:
        await callback.answer("⚠️ Tarjima topilmadi.")
        return

    lang = callback.data.replace("post_", "")
    channel_map = {"ru": CHANNEL_RU, "kaa": CHANNEL_KAA, "en": CHANNEL_EN}
    flag_map = {"ru": "🇷🇺", "kaa": "🏳️", "en": "🇬🇧"}
    
    channel = channel_map.get(lang)
    if not channel:
        await callback.answer("⚠️ Kanal topilmadi.")
        return

    await callback.answer(f"📤 {flag_map[lang]} kanalga yuborilmoqda...")
    
    ok = await post_to_channel(channel, data[lang])
    
    if ok:
        await callback.message.answer(
            f"✅ {flag_map[lang]} {channel} kanaliga muvaffaqiyatli yuborildi!"
        )
    else:
        await callback.message.answer(
            f"❌ {flag_map[lang]} {channel} kanaliga yuborishda xato. "
            f"Botni kanalga admin qilib qo'shganingizni tekshiring."
        )


@router.callback_query(F.data == "cancel")
async def cb_cancel(callback: CallbackQuery, state: FSMContext):
    """Tarjimani bekor qiladi."""
    user_id = callback.from_user.id
    translations_store.pop(user_id, None)
    
    await callback.message.answer(
        "❌ Bekor qilindi.\n\nYangi post uchun matn yuboring."
    )
    await state.set_state(TranslationStates.waiting_text)
    await callback.answer()


@router.callback_query(F.data == "cancel_edit")
async def cb_cancel_edit(callback: CallbackQuery, state: FSMContext):
    """Tahrirlashni bekor qiladi."""
    user_id = callback.from_user.id
    data = translations_store.get(user_id)
    
    if data:
        preview_text = format_preview(data["original"], data)
        await callback.message.answer(
            preview_text,
            reply_markup=build_preview_keyboard(),
        )

    await state.set_state(TranslationStates.reviewing)
    await callback.answer("Tahrirlash bekor qilindi.")


# ─── Entry point ──────────────────────────────────────────────────────

async def main():
    logger.info("DOMO Translation Bot ishga tushmoqda...")
    logger.info(f"Tarjima mexanizmi: {TRANSLATION_ENGINE}")
    logger.info(f"Kanallar: RU={CHANNEL_RU}, KAA={CHANNEL_KAA}, EN={CHANNEL_EN}")
    logger.info(f"Admin IDlar: {ADMIN_IDS}")
    
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
