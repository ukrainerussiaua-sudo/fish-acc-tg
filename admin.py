# ==============================
#  admin.py — админ-панель
# ==============================

import os
import shutil
import logging
import zipfile

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import ADMIN_IDS, ACCOUNTS_DIR, TEMP_DIR, MAX_ZIP_SIZE
from database import (
    get_all_accounts, get_free_accounts, get_given_accounts,
    get_banned_accounts, give_account, ban_account, add_account,
    clear_database, get_all_users, update_account_session,
    update_account_info, get_account_by_id
)
from tg_utils import (
    extract_zip, find_tdata_in_dir, convert_all_accounts,
    check_all_sessions, clear_account_chats, get_account_info,
    convert_tdata_to_session, phone_to_country
)

logger = logging.getLogger(__name__)
router = Router()


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


# ──────────────────────────────────────────────
#  FSM
# ──────────────────────────────────────────────

class AdminStates(StatesGroup):
    give_account_select = State()
    give_account_user = State()
    waiting_zip_upload = State()
    waiting_batch_zip = State()
    reply_to_user = State()
    clear_chats_select = State()


# ──────────────────────────────────────────────
#  Главное меню админа
# ──────────────────────────────────────────────

def admin_main_keyboard():
    kb = InlineKeyboardBuilder()
    kb.button(text="🎁 Выдать аккаунт", callback_data="adm_give")
    kb.button(text="📤 Загрузить аккаунт (ZIP)", callback_data="adm_upload")
    kb.button(text="🔄 Конвертировать аккаунты", callback_data="adm_convert")
    kb.button(text="🧹 Очистить чаты", callback_data="adm_clear_chats")
    kb.button(text="🔍 Проверка аккаунтов (batch)", callback_data="adm_batch_check")
    kb.button(text="🗃 Очистка базы", callback_data="adm_db_clear")
    kb.button(text="📊 Статистика", callback_data="adm_stats")
    kb.adjust(1)
    return kb.as_markup()


@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if not is_admin(message.from_user.id):
        return
    all_accs = get_all_accounts()
    free = len([a for a in all_accs if a["status"] == "free"])
    given = len([a for a in all_accs if a["status"] == "given"])
    banned = len([a for a in all_accs if a["status"] == "banned"])

    await message.answer(
        f"🛠 <b>Админ-панель</b>\n\n"
        f"📦 Всего аккаунтов: <b>{len(all_accs)}</b>\n"
        f"✅ Свободных: <b>{free}</b>\n"
        f"👤 Выданных: <b>{given}</b>\n"
        f"🚫 Забаненных: <b>{banned}</b>",
        reply_markup=admin_main_keyboard(),
        parse_mode="HTML"
    )


# ──────────────────────────────────────────────
#  1. Выдать аккаунт
# ──────────────────────────────────────────────

@router.callback_query(F.data == "adm_give")
async def adm_give(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return

    free_accs = get_free_accounts()
    if not free_accs:
        await call.message.edit_text("😕 Нет свободных аккаунтов.", reply_markup=adm_back())
        return

    kb = InlineKeyboardBuilder()
    for acc in free_accs[:20]:
        label = acc["phone"] or acc["folder_name"]
        spam = acc["spam_status"] or "?"
        kb.button(text=f"📱 {label} | {spam}", callback_data=f"adm_give_select_{acc['id']}")
    kb.button(text="🔙 Назад", callback_data="adm_back")
    kb.adjust(1)

    await call.message.edit_text(
        f"📋 <b>Выберите аккаунт для выдачи ({len(free_accs)} свободных):</b>",
        reply_markup=kb.as_markup(),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("adm_give_select_"))
async def adm_give_select(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    acc_id = int(call.data.split("_")[-1])
    await state.update_data(give_acc_id=acc_id)
    await call.message.edit_text(
        "👤 Введи <b>Telegram ID</b> или <b>@username</b> пользователя:",
        parse_mode="HTML",
        reply_markup=adm_back()
    )
    await state.set_state(AdminStates.give_account_user)


@router.message(AdminStates.give_account_user)
async def adm_give_user(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    from bot import bot

    data = await state.get_data()
    acc_id = data["give_acc_id"]
    text = message.text.strip()

    # Получаем user_id
    try:
        if text.startswith("@"):
            user = await bot.get_chat(text)
            user_id = user.id
        else:
            user_id = int(text)
    except Exception:
        await message.answer("❌ Не нашёл пользователя. Введи корректный ID или @username.")
        return

    if not give_account(acc_id, user_id):
        await message.answer("❌ Аккаунт уже выдан, забанен или не существует.")
        await state.clear()
        return
    acc = get_account_by_id(acc_id)
    if not acc:
        await message.answer("❌ Аккаунт не найден после обновления БД.")
        await state.clear()
        return

    # Уведомляем пользователя
    try:
        await bot.send_message(
            user_id,
            f"🎁 <b>Тебе выдан аккаунт!</b>\n\n"
            f"📞 Номер: <code>{acc['phone'] or '—'}</code>\n"
            f"🌍 Страна: {acc['country'] or '—'}\n"
            f"Зайди в /start → Мои аккаунты.",
            parse_mode="HTML"
        )
    except Exception:
        pass

    await message.answer(
        f"✅ Аккаунт <b>#{acc_id}</b> выдан пользователю <code>{user_id}</code>",
        parse_mode="HTML",
        reply_markup=admin_main_keyboard()
    )
    await state.clear()


# ──────────────────────────────────────────────
#  2. Загрузить аккаунт по ZIP
# ──────────────────────────────────────────────

@router.callback_query(F.data == "adm_upload")
async def adm_upload(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    await call.message.edit_text(
        "📤 <b>Загрузи ZIP-архив</b>\n\n"
        "Внутри ZIP должна быть папка <code>tdata</code>\n"
        "(или папка с tdata внутри)\n\n"
        "Отправь файл сюда:",
        parse_mode="HTML",
        reply_markup=adm_back()
    )
    await state.set_state(AdminStates.waiting_zip_upload)


@router.message(AdminStates.waiting_zip_upload, F.document)
async def adm_receive_zip(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    from bot import bot

    doc = message.document
    if not doc.file_name or not doc.file_name.lower().endswith(".zip"):
        await message.answer("❌ Нужен .zip файл!")
        return
    if doc.file_size and doc.file_size > MAX_ZIP_SIZE:
        await message.answer(f"❌ ZIP слишком большой. Максимум: {MAX_ZIP_SIZE // (1024 * 1024)} МБ.")
        return

    await message.answer("⏳ Обрабатываю...")

    # Скачиваем
    os.makedirs(TEMP_DIR, exist_ok=True)
    zip_path = os.path.join(TEMP_DIR, f"upload_{message.message_id}.zip")
    file = await bot.get_file(doc.file_id)
    await bot.download_file(file.file_path, zip_path)

    # Распаковываем
    extract_dir = os.path.join(TEMP_DIR, f"extract_{message.message_id}")
    tdata_path = extract_zip(zip_path, extract_dir)

    if not tdata_path:
        await message.answer("❌ Папка tdata не найдена в архиве.")
        shutil.rmtree(extract_dir, ignore_errors=True)
        os.remove(zip_path)
        await state.clear()
        return

    # Создаём папку аккаунта
    folder_name = f"acc_{message.message_id}"
    acc_folder = os.path.join(ACCOUNTS_DIR, folder_name)
    os.makedirs(acc_folder, exist_ok=True)
    shutil.copytree(tdata_path, os.path.join(acc_folder, "tdata"))

    # Конвертируем и получаем инфо
    session_path = os.path.join(acc_folder, "session")
    ok = await convert_tdata_to_session(os.path.join(acc_folder, "tdata"), session_path)
    info = await get_account_info(session_path) if ok else {}
    phone = info.get("phone", "")
    country = info.get("country", "")
    flag = info.get("flag", "")
    spam = info.get("spam_status", "unknown")

    # Добавляем в БД
    acc_id = add_account(
        folder_name=folder_name,
        phone=phone,
        country=country,
        spam_status=spam
    )
    if ok:
        from database import update_account_session as uas
        uas(acc_id, True)

    # Чистим временные файлы
    shutil.rmtree(extract_dir, ignore_errors=True)
    os.remove(zip_path)

    await message.answer(
        f"✅ <b>Аккаунт добавлен!</b>\n\n"
        f"🆔 ID в базе: #{acc_id}\n"
        f"📞 Номер: <code>{phone or '—'}</code>\n"
        f"🌍 Страна: {flag} {country or '—'}\n"
        f"🚫 Спам: {spam}\n"
        f"🔐 Сессия: {'✅' if ok else '❌'}",
        parse_mode="HTML",
        reply_markup=admin_main_keyboard()
    )
    await state.clear()


# ──────────────────────────────────────────────
#  3. Конвертировать все аккаунты
# ──────────────────────────────────────────────

@router.callback_query(F.data == "adm_convert")
async def adm_convert(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    await call.message.edit_text("⏳ Конвертирую все аккаунты tdata → session...")
    converted, failed = await convert_all_accounts()
    await call.message.edit_text(
        f"✅ <b>Конвертация завершена</b>\n\n"
        f"✔️ Конвертировано: {converted}\n"
        f"❌ Ошибок: {failed}",
        reply_markup=admin_main_keyboard(),
        parse_mode="HTML"
    )


# ──────────────────────────────────────────────
#  4. Очистить чаты
# ──────────────────────────────────────────────

@router.callback_query(F.data == "adm_clear_chats")
async def adm_clear_chats(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    accs = get_all_accounts()
    kb = InlineKeyboardBuilder()
    for acc in accs:
        if acc["has_session"]:
            label = acc["phone"] or acc["folder_name"]
            kb.button(text=f"🧹 {label}", callback_data=f"adm_clearchat_{acc['id']}")
    kb.button(text="🔙 Назад", callback_data="adm_back")
    kb.adjust(1)

    await call.message.edit_text(
        "🧹 <b>Выберите аккаунт для очистки чатов:</b>",
        reply_markup=kb.as_markup(),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("adm_clearchat_"))
async def adm_clearchat_run(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    acc_id = int(call.data.split("_")[-1])
    acc = get_account_by_id(acc_id)

    await call.message.edit_text("⏳ Выхожу из всех чатов и каналов...")
    session_path = os.path.join(ACCOUNTS_DIR, acc["folder_name"], "session")
    left, errors = await clear_account_chats(session_path)

    await call.message.edit_text(
        f"✅ <b>Очистка завершена</b>\n\n"
        f"📤 Вышел из: {left} чатов/каналов\n"
        f"❌ Ошибок: {errors}",
        reply_markup=admin_main_keyboard(),
        parse_mode="HTML"
    )


# ──────────────────────────────────────────────
#  5. Batch-проверка аккаунтов (несколько ZIP)
# ──────────────────────────────────────────────

@router.callback_query(F.data == "adm_batch_check")
async def adm_batch_check(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    await call.message.edit_text(
        "📦 <b>Batch-загрузка аккаунтов</b>\n\n"
        "Отправь <b>один ZIP-архив</b>, внутри которого лежат папки с tdata.\n\n"
        "Структура:\n"
        "<code>archive.zip/\n"
        "  ├── account1/\n"
        "  │   └── tdata/\n"
        "  ├── account2/\n"
        "  │   └── tdata/\n"
        "  └── ...</code>",
        parse_mode="HTML",
        reply_markup=adm_back()
    )
    await state.set_state(AdminStates.waiting_batch_zip)


@router.message(AdminStates.waiting_batch_zip, F.document)
async def adm_batch_receive(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    from bot import bot

    doc = message.document
    if not doc.file_name or not doc.file_name.lower().endswith(".zip"):
        await message.answer("❌ Нужен .zip файл!")
        return
    if doc.file_size and doc.file_size > MAX_ZIP_SIZE:
        await message.answer(f"❌ ZIP слишком большой. Максимум: {MAX_ZIP_SIZE // (1024 * 1024)} МБ.")
        return

    await message.answer("⏳ Распаковываю и проверяю аккаунты...")

    os.makedirs(TEMP_DIR, exist_ok=True)
    zip_path = os.path.join(TEMP_DIR, f"batch_{message.message_id}.zip")
    file = await bot.get_file(doc.file_id)
    await bot.download_file(file.file_path, zip_path)

    extract_dir = os.path.join(TEMP_DIR, f"batch_extract_{message.message_id}")
    try:
        tdata_root = extract_zip(zip_path, extract_dir)
    except (zipfile.BadZipFile, ValueError, OSError) as e:
        shutil.rmtree(extract_dir, ignore_errors=True)
        if os.path.exists(zip_path):
            os.remove(zip_path)
        await message.answer(f"❌ Не удалось распаковать ZIP: {e}")
        await state.clear()
        return

    tdata_paths = find_tdata_in_dir(extract_dir)
    total = len(tdata_paths)
    ok_count = 0
    spam_count = 0
    dead_count = 0

    results = []
    for i, tdata_path in enumerate(tdata_paths):
        folder_name = f"batch_{message.message_id}_{i}"
        acc_folder = os.path.join(ACCOUNTS_DIR, folder_name)
        os.makedirs(acc_folder, exist_ok=True)
        shutil.copytree(tdata_path, os.path.join(acc_folder, "tdata"))

        session_path = os.path.join(acc_folder, "session")
        ok = await convert_tdata_to_session(os.path.join(acc_folder, "tdata"), session_path)

        if ok:
            info = await get_account_info(session_path)
            phone = info.get("phone", "")
            country = info.get("country", "")
            flag = info.get("flag", "")
            spam = info.get("spam_status", "unknown")

            acc_id = add_account(folder_name, phone, country, spam_status=spam)
            from database import update_account_session as uas
            uas(acc_id, True)

            if "spam" in spam.lower():
                spam_count += 1
            else:
                ok_count += 1

            results.append(f"✅ {flag} {phone or folder_name} | {spam}")
        else:
            dead_count += 1
            results.append(f"❌ (мёртвая) {os.path.basename(os.path.dirname(tdata_path))}")

    shutil.rmtree(extract_dir, ignore_errors=True)
    os.remove(zip_path)

    result_text = "\n".join(results[:30])
    if len(results) > 30:
        result_text += f"\n... и ещё {len(results) - 30} аккаунтов"

    await message.answer(
        f"✅ <b>Batch-загрузка завершена</b>\n\n"
        f"📦 Всего: {total}\n"
        f"✔️ Живых: {ok_count}\n"
        f"🚫 Спам: {spam_count}\n"
        f"💀 Мёртвых: {dead_count}\n\n"
        f"<b>Результаты:</b>\n{result_text}",
        parse_mode="HTML",
        reply_markup=admin_main_keyboard()
    )
    await state.clear()


# ──────────────────────────────────────────────
#  6. Очистка базы
# ──────────────────────────────────────────────

@router.callback_query(F.data == "adm_db_clear")
async def adm_db_clear(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    kb = InlineKeyboardBuilder()
    kb.button(text="🗑 Очистить выданные", callback_data="adm_clear_given")
    kb.button(text="🗑 Очистить забаненные", callback_data="adm_clear_banned")
    kb.button(text="💥 Очистить ВСЮ базу", callback_data="adm_clear_all")
    kb.button(text="🔙 Назад", callback_data="adm_back")
    kb.adjust(1)

    given = len(get_given_accounts())
    banned = len(get_banned_accounts())
    all_count = len(get_all_accounts())

    await call.message.edit_text(
        f"🗃 <b>Очистка базы</b>\n\n"
        f"👤 Выданных: {given}\n"
        f"🚫 Забаненных: {banned}\n"
        f"📦 Всего: {all_count}",
        reply_markup=kb.as_markup(),
        parse_mode="HTML"
    )


@router.callback_query(F.data.in_({"adm_clear_given", "adm_clear_banned", "adm_clear_all"}))
async def adm_clear_confirm(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    mapping = {
        "adm_clear_given": "given",
        "adm_clear_banned": "banned",
        "adm_clear_all": "all"
    }
    target = mapping[call.data]
    clear_database(target)
    await call.message.edit_text(
        f"✅ База очищена ({target})",
        reply_markup=admin_main_keyboard()
    )


# ──────────────────────────────────────────────
#  Статистика
# ──────────────────────────────────────────────

@router.callback_query(F.data == "adm_stats")
async def adm_stats(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    all_accs = get_all_accounts()
    users = get_all_users()
    free = len([a for a in all_accs if a["status"] == "free"])
    given = len([a for a in all_accs if a["status"] == "given"])
    banned = len([a for a in all_accs if a["status"] == "banned"])
    with_session = len([a for a in all_accs if a["has_session"]])

    await call.message.edit_text(
        f"📊 <b>Статистика</b>\n\n"
        f"👥 Пользователей: {len(users)}\n"
        f"📦 Всего аккаунтов: {len(all_accs)}\n"
        f"✅ Свободных: {free}\n"
        f"👤 Выданных: {given}\n"
        f"🚫 Забаненных: {banned}\n"
        f"🔐 С сессией: {with_session}",
        reply_markup=admin_main_keyboard(),
        parse_mode="HTML"
    )


# ──────────────────────────────────────────────
#  Ответ пользователю из поддержки
# ──────────────────────────────────────────────

@router.callback_query(F.data.startswith("reply_user_"))
async def adm_reply_start(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    user_id = int(call.data.split("_")[-1])
    await state.update_data(reply_to=user_id)
    await call.message.answer(
        f"✏️ Напиши ответ пользователю <code>{user_id}</code>:",
        parse_mode="HTML"
    )
    await state.set_state(AdminStates.reply_to_user)


@router.message(AdminStates.reply_to_user)
async def adm_reply_send(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    from bot import bot
    data = await state.get_data()
    user_id = data["reply_to"]

    try:
        await bot.send_message(
            user_id,
            f"📩 <b>Ответ от поддержки:</b>\n\n{message.text}",
            parse_mode="HTML"
        )
        await message.answer("✅ Ответ отправлен!")
    except Exception as e:
        await message.answer(f"❌ Не удалось отправить: {e}")

    await state.clear()


# ──────────────────────────────────────────────
#  Навигация
# ──────────────────────────────────────────────

def adm_back():
    kb = InlineKeyboardBuilder()
    kb.button(text="🔙 Назад", callback_data="adm_back")
    return kb.as_markup()


@router.callback_query(F.data == "adm_back")
async def adm_back_cb(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("🛠 Админ-панель:", reply_markup=admin_main_keyboard())
