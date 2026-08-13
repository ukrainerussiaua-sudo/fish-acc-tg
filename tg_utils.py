# ==============================
#  tg_utils.py — работа с tdata и сессиями через opentele + telethon
# ==============================

import os
import shutil
import asyncio
import zipfile
import logging
from pathlib import Path

try:
    from opentele.td import TDesktop
    from opentele.api import UseCurrentSession
    OPENTELE_AVAILABLE = True
except ImportError as _ote_err:
    OPENTELE_AVAILABLE = False
    TDesktop = None
    UseCurrentSession = None
    import logging as _log
    _log.getLogger(__name__).critical(
        f"opentele не загружен: {_ote_err}\n"
        "Конвертация tdata->session недоступна.\n"
        "Решение: pip install PyQt5==5.15.11 PyQt5-Qt5==5.15.19 PyQt5-sip==12.19.0\n"
        "Или запускай через Docker (Dockerfile прилагается)."
    )

from telethon import TelegramClient
from telethon.errors import (
    AuthKeyUnregisteredError, SessionRevokedError,
    UserDeactivatedBanError, PhoneNumberBannedError
)
from telethon.tl.functions.account import GetAuthorizationsRequest

import pycountry

logger = logging.getLogger(__name__)

ACCOUNTS_DIR = "accounts"
TEMP_DIR = "temp"


# ──────────────────────────────────────────────
#  Распаковка ZIP и поиск папки tdata
# ──────────────────────────────────────────────

def extract_zip(zip_path: str, dest_folder: str) -> str | None:
    """
    Распаковывает ZIP, ищет папку tdata внутри.
    Возвращает путь к найденной tdata-папке или None.
    """
    os.makedirs(dest_folder, exist_ok=True)
    dest_root = Path(dest_folder).resolve()
    with zipfile.ZipFile(zip_path, "r") as z:
        for member in z.infolist():
            target = (dest_root / member.filename).resolve()
            if target != dest_root and dest_root not in target.parents:
                raise ValueError(f"Опасный путь в ZIP: {member.filename}")
        z.extractall(dest_root)

    # Ищем папку tdata рекурсивно
    for root, dirs, files in os.walk(dest_folder):
        for d in dirs:
            if d.lower() == "tdata":
                return os.path.join(root, d)
    return None


def find_tdata_in_dir(base_dir: str) -> list[str]:
    """Ищет все папки tdata внутри директории (для batch-загрузки)."""
    results = []
    for root, dirs, files in os.walk(base_dir):
        for d in dirs:
            if d.lower() == "tdata":
                results.append(os.path.join(root, d))
    return results


# ──────────────────────────────────────────────
#  Конвертация tdata → .session (telethon)
# ──────────────────────────────────────────────

async def convert_tdata_to_session(tdata_path: str, session_output_path: str) -> bool:
    """
    Конвертирует папку tdata в .session файл через opentele.
    Возвращает True при успехе.
    """
    if not OPENTELE_AVAILABLE:
        logger.error("opentele не установлен — конвертация tdata невозможна.")
        return False
    try:
        tdesk = TDesktop(tdata_path)
        if not tdesk.isLoaded():
            logger.error(f"TDesktop не смог загрузить tdata: {tdata_path}")
            return False

        client = await tdesk.ToTelethon(
            session=session_output_path,
            flag=UseCurrentSession
        )
        await client.connect()
        is_auth = await client.is_user_authorized()
        await client.disconnect()
        return is_auth
    except Exception as e:
        logger.error(f"Ошибка конвертации tdata {tdata_path}: {e}")
        return False


async def convert_all_accounts():
    """Конвертирует все аккаунты с tdata но без session."""
    from database import get_all_accounts, update_account_session

    accounts = get_all_accounts()
    converted = 0
    failed = 0

    for acc in accounts:
        tdata_path = os.path.join(ACCOUNTS_DIR, acc["folder_name"], "tdata")
        session_path = os.path.join(ACCOUNTS_DIR, acc["folder_name"], "session")

        if not os.path.exists(tdata_path):
            continue
        if os.path.exists(session_path + ".session"):
            update_account_session(acc["id"], True)
            continue

        success = await convert_tdata_to_session(tdata_path, session_path)
        if success:
            update_account_session(acc["id"], True)
            converted += 1
        else:
            failed += 1

    return converted, failed


# ──────────────────────────────────────────────
#  Получить tdata по номеру телефона
# ──────────────────────────────────────────────

def find_account_by_phone(phone: str):
    """Ищет аккаунт в БД по номеру телефона."""
    from database import get_all_accounts
    phone_clean = phone.replace("+", "").replace(" ", "").strip()

    for acc in get_all_accounts():
        acc_phone = (acc["phone"] or "").replace("+", "").replace(" ", "").strip()
        if acc_phone == phone_clean:
            return acc
    return None


def get_tdata_zip_path(acc) -> str | None:
    """
    Пакует папку tdata аккаунта в ZIP и возвращает путь к нему.
    """
    tdata_path = os.path.join(ACCOUNTS_DIR, acc["folder_name"], "tdata")
    if not os.path.exists(tdata_path):
        return None

    zip_out = os.path.join(TEMP_DIR, f"{acc['folder_name']}_tdata.zip")
    os.makedirs(TEMP_DIR, exist_ok=True)

    with zipfile.ZipFile(zip_out, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(tdata_path):
            for file in files:
                filepath = os.path.join(root, file)
                arcname = os.path.relpath(filepath, os.path.dirname(tdata_path))
                zf.write(filepath, arcname)

    return zip_out


# ──────────────────────────────────────────────
#  Проверка сессии на валидность
# ──────────────────────────────────────────────

async def check_session_valid(session_path: str) -> str:
    """
    Проверяет сессию. Возвращает: 'ok', 'dead', 'banned', 'error'
    """
    try:
        client = TelegramClient(session_path, api_id=2040, api_hash="b18441a1ff607e10a989891a5462e627")
        await client.connect()
        if not await client.is_user_authorized():
            await client.disconnect()
            return "dead"
        # Проверка авторизаций (если сессия слетела)
        await client(GetAuthorizationsRequest())
        await client.disconnect()
        return "ok"
    except (AuthKeyUnregisteredError, SessionRevokedError):
        return "dead"
    except (UserDeactivatedBanError, PhoneNumberBannedError):
        return "banned"
    except Exception as e:
        logger.error(f"Ошибка проверки сессии {session_path}: {e}")
        return "error"


async def check_all_sessions() -> list[dict]:
    """
    Проверяет все активные сессии. Возвращает список слетевших.
    """
    from database import get_given_accounts, ban_account

    results = []
    accounts = get_given_accounts()

    for acc in accounts:
        session_path = os.path.join(ACCOUNTS_DIR, acc["folder_name"], "session")
        if not os.path.exists(session_path + ".session"):
            continue

        status = await check_session_valid(session_path)
        if status in ("dead", "banned"):
            results.append({
                "id": acc["id"],
                "phone": acc["phone"] or acc["folder_name"],
                "status": status,
                "given_to": acc["given_to"]
            })
            if status == "banned":
                ban_account(acc["id"])

    return results


# ──────────────────────────────────────────────
#  Очистка чатов аккаунта
# ──────────────────────────────────────────────

async def clear_account_chats(session_path: str) -> tuple[int, int]:
    """
    Выходит из всех чатов и каналов аккаунта.
    Возвращает (вышел_из_чатов, ошибки).
    """
    from telethon.tl.functions.channels import LeaveChannelRequest
    from telethon.tl.functions.messages import DeleteHistoryRequest
    from telethon import functions

    client = TelegramClient(session_path, api_id=2040, api_hash="b18441a1ff607e10a989891a5462e627")
    await client.connect()

    if not await client.is_user_authorized():
        await client.disconnect()
        return 0, 0

    left = 0
    errors = 0

    try:
        dialogs = await client.get_dialogs()
        for dialog in dialogs:
            try:
                entity = dialog.entity
                if hasattr(entity, "megagroup") or hasattr(entity, "broadcast"):
                    await client(LeaveChannelRequest(entity))
                else:
                    await client(DeleteHistoryRequest(peer=entity, max_id=0, just_clear=False))
                left += 1
                await asyncio.sleep(0.5)  # антифлуд
            except Exception:
                errors += 1
    finally:
        await client.disconnect()

    return left, errors


# ──────────────────────────────────────────────
#  Получение инфо об аккаунте (страна, спам, дата рег)
# ──────────────────────────────────────────────

COUNTRY_FLAGS = {
    "RU": "🇷🇺", "UA": "🇺🇦", "KZ": "🇰🇿", "BY": "🇧🇾", "US": "🇺🇸",
    "DE": "🇩🇪", "FR": "🇫🇷", "GB": "🇬🇧", "TR": "🇹🇷", "UZ": "🇺🇿",
    "AM": "🇦🇲", "GE": "🇬🇪", "AZ": "🇦🇿", "MD": "🇲🇩", "KG": "🇰🇬",
}


def phone_to_country(phone: str) -> tuple[str, str]:
    """Определяет страну и флаг по номеру телефона."""
    try:
        import phonenumbers
        parsed = phonenumbers.parse(phone if phone.startswith("+") else "+" + phone)
        region = phonenumbers.region_code_for_number(parsed)
        flag = COUNTRY_FLAGS.get(region, "🏳️")
        country_obj = pycountry.countries.get(alpha_2=region)
        country_name = country_obj.name if country_obj else region
        return country_name, flag
    except Exception:
        return "Unknown", "🏳️"


async def get_account_info(session_path: str) -> dict:
    """
    Получает информацию об аккаунте: телефон, спам-статус.
    """
    try:
        client = TelegramClient(session_path, api_id=2040, api_hash="b18441a1ff607e10a989891a5462e627")
        await client.connect()

        if not await client.is_user_authorized():
            await client.disconnect()
            return {"valid": False}

        me = await client.get_me()
        phone = me.phone or ""

        # Проверка спам-статуса через SpamBot
        spam_status = "unknown"
        try:
            async with client.conversation("@SpamBot") as conv:
                await conv.send_message("/start")
                resp = await conv.get_response(timeout=10)
                text = resp.text.lower()
                if "no limits" in text or "нет ограничений" in text:
                    spam_status = "clean ✅"
                elif "spam" in text or "ограничен" in text or "limited" in text:
                    spam_status = "spam ⛔"
                else:
                    spam_status = "unknown ❓"
        except Exception:
            spam_status = "unknown ❓"

        await client.disconnect()

        country, flag = phone_to_country(phone)
        return {
            "valid": True,
            "phone": phone,
            "country": country,
            "flag": flag,
            "spam_status": spam_status,
            "first_name": me.first_name or "",
        }
    except Exception as e:
        logger.error(f"Ошибка получения инфо: {e}")
        return {"valid": False}
