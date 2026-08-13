# ==============================
#  user.py — обработчики пользовательских команд
# ==============================

import os
import logging
from html import escape
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import ADMIN_IDS, RULES_TEXT
from database import register_user, get_user_accounts, get_account_by_id
from tg_utils import find_account_by_phone, get_tdata_zip_path, get_account_info, convert_tdata_to_session

logger = logging.getLogger(__name__)
router = Router()

ACCOUNTS_DIR = "accounts"


# ──────────────────────────────────────────────
#  FSM состояния
# ──────────────────────────────────────────────

class UserStates(StatesGroup):
    waiting_phone = State()
    support_chat = State()


# ──────────────────────────────────────────────
#  Главное меню пользователя
# ──────────────────────────────────────────────

def user_main_keyboard():
    kb = InlineKeyboardBuilder()
    kb.button(text="📁 Мои аккаунты", callback_data="my_accounts")
    kb.button(text="📋 Правила", callback_data="rules")
    kb.button(text="💬 Поддержка", callback_data="support")
    kb.adjust(1)
    return kb.as_markup()


@router.message(Command("start"))
async def cmd_start(message: Message):
    user = message.from_user
    register_user(user.id, user.username, user.full_name)
    await message.answer(
        f"👋 Привет, <b>{user.full_name}</b>!\n\n"
        "Выбери действие:",
        reply_markup=user_main_keyboard(),
        parse_mode="HTML"
    )


# ──────────────────────────────────────────────
#  Мои аккаунты
# ──────────────────────────────────────────────

@router.callback_query(F.data == "my_accounts")
async def cb_my_accounts(call: CallbackQuery):
    accs = get_user_accounts(call.from_user.id)
    if not accs:
        await call.message.edit_text(
            "😕 У тебя пока нет выданных аккаунтов.\n\n"
            "Обратись в поддержку для получения.",
            reply_markup=back_keyboard()
        )
        return

    kb = InlineKeyboardBuilder()
    for acc in accs:
        label = acc["phone"] or acc["folder_name"]
        spam = acc["spam_status"] or "?"
        kb.button(
            text=f"📱 {label} | {spam}",
            callback_data=f"acc_detail_{acc['id']}"
        )
    kb.button(text="🔙 Назад", callback_data="back_main")
    kb.adjust(1)

    await call.message.edit_text(
        f"📁 <b>Твои аккаунты ({len(accs)}):</b>",
        reply_markup=kb.as_markup(),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("acc_detail_"))
async def cb_acc_detail(call: CallbackQuery):
    acc_id = int(call.data.split("_")[-1])
    acc = get_account_by_id(acc_id)

    if not acc or acc["given_to"] != call.from_user.id:
        await call.answer("❌ Аккаунт не найден.", show_alert=True)
        return

    phone = acc["phone"] or "Неизвестен"
    country = acc["country"] or "—"
    spam = acc["spam_status"] or "—"
    has_tdata = "✅" if acc["has_tdata"] else "❌"
    has_session = "✅" if acc["has_session"] else "❌"

    text = (
        f"📱 <b>Аккаунт #{acc['id']}</b>\n\n"
        f"📞 Номер: <code>{phone}</code>\n"
        f"🌍 Страна: {country}\n"
        f"🚫 Спам: {spam}\n"
        f"📂 tdata: {has_tdata}\n"
        f"🔐 Session: {has_session}\n"
    )

    kb = InlineKeyboardBuilder()
    if acc["has_tdata"]:
        kb.button(text="📥 Скачать tdata", callback_data=f"download_tdata_{acc_id}")
    kb.button(text="🔙 К списку", callback_data="my_accounts")
    kb.adjust(1)

    await call.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")


@router.callback_query(F.data.startswith("download_tdata_"))
async def cb_download_tdata(call: CallbackQuery):
    acc_id = int(call.data.split("_")[-1])
    acc = get_account_by_id(acc_id)

    if not acc or acc["given_to"] != call.from_user.id:
        await call.answer("❌ Нет доступа.", show_alert=True)
        return

    await call.answer("⏳ Упаковываю tdata...")
    await call.message.answer("⏳ Подготавливаю файл, подожди...")

    zip_path = get_tdata_zip_path(acc)
    if not zip_path:
        await call.message.answer("❌ tdata не найдена для этого аккаунта.")
        return

    from aiogram.types import FSInputFile
    try:
        file = FSInputFile(zip_path, filename=f"tdata_{acc['phone'] or acc['folder_name']}.zip")
        await call.message.answer_document(file, caption="📂 Твоя tdata")
    finally:
        try:
            os.remove(zip_path)
        except OSError:
            pass


# ──────────────────────────────────────────────
#  Получить последний код из Telegram (777000)
# ──────────────────────────────────────────────

@router.callback_query(F.data.startswith("get_code_"))
async def cb_get_code(call: CallbackQuery):
    await call.answer("Эта функция отключена.", show_alert=True)


# ──────────────────────────────────────────────
#  Получить tdata из номера телефона
# ──────────────────────────────────────────────

@router.callback_query(F.data == "get_tdata_by_phone")
async def cb_get_tdata_by_phone(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text(
        "ℹ️ Получение tdata по номеру отключено.\n\n"
        "Используй раздел «Мои аккаунты» — доступные тебе файлы можно скачать только там.",
        reply_markup=back_keyboard(),
    )


# ──────────────────────────────────────────────
#  Правила
# ──────────────────────────────────────────────

@router.callback_query(F.data == "rules")
async def cb_rules(call: CallbackQuery):
    await call.message.edit_text(
        RULES_TEXT,
        reply_markup=back_keyboard(),
        parse_mode="HTML"
    )


# ──────────────────────────────────────────────
#  Поддержка
# ──────────────────────────────────────────────

@router.callback_query(F.data == "support")
async def cb_support(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text(
        "💬 <b>Поддержка</b>\n\n"
        "Напиши своё сообщение, и администратор ответит тебе:\n\n"
        "<i>Или нажми Назад для отмены.</i>",
        reply_markup=back_keyboard(),
        parse_mode="HTML"
    )
    await state.set_state(UserStates.support_chat)


@router.message(UserStates.support_chat)
async def process_support_message(message: Message, state: FSMContext):
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    from bot import bot

    user = message.from_user
    text = (
        f"📩 <b>Сообщение в поддержку</b>\n\n"
        f"👤 <a href='tg://user?id={user.id}'>{escape(user.full_name or '')}</a> (@{escape(user.username or '—')})\n"
        f"🆔 ID: <code>{user.id}</code>\n\n"
        f"💬 {escape(message.text or '')}"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="↩️ Ответить", callback_data=f"reply_user_{user.id}")]
    ])

    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, text, parse_mode="HTML", reply_markup=kb)
        except Exception:
            pass

    await message.answer("✅ Сообщение отправлено! Ожидай ответа.")
    await state.clear()


# ──────────────────────────────────────────────
#  Утилиты навигации
# ──────────────────────────────────────────────

def back_keyboard():
    kb = InlineKeyboardBuilder()
    kb.button(text="🔙 Назад", callback_data="back_main")
    return kb.as_markup()


@router.callback_query(F.data == "back_main")
async def cb_back_main(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text(
        "Выбери действие:",
        reply_markup=user_main_keyboard()
    )
