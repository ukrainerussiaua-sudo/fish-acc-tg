# ==============================
# config.py — настройки бота
# ==============================
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
ACCOUNTS_DIR = BASE_DIR / "accounts"
TEMP_DIR = BASE_DIR / "temp"
DB_PATH = str(DATA_DIR / "bot.sqlite3")

BOT_TOKEN = "8332587828:AAHD-ZtJGUUOOVS5-ci2PPdZZlK3VlPy3LM".strip()
ADMIN_IDS = [int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()]
SESSION_CHECK_INTERVAL = int(os.getenv("SESSION_CHECK_INTERVAL", "1800"))
MAX_ZIP_SIZE = int(os.getenv("MAX_ZIP_SIZE", str(100 * 1024 * 1024)))

RULES_TEXT = """
📋 <b>Правила использования сервиса:</b>

1. Аккаунты выдаются только зарегистрированным пользователям.
2. Запрещено передавать аккаунты третьим лицам.
3. При обнаружении проблем — сразу сообщайте в поддержку.
4. Администрация не несёт ответственности за блокировки по вине пользователя.

По всем вопросам обращайтесь в поддержку.
"""
