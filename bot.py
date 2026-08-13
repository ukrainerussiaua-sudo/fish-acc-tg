# ==============================
#  bot.py — главный файл запуска
# ==============================

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN
from database import init_db
import user
import admin
import scheduler as sched

# Логирование
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("bot.log", encoding="utf-8"),
    ]
)
logger = logging.getLogger(__name__)

# Создаём бота — экспортируем для использования в других модулях
bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)

dp = Dispatcher(storage=MemoryStorage())

# Регистрируем роутеры
dp.include_router(admin.router)  # сначала admin — фильтры имеют приоритет
dp.include_router(user.router)


async def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN не задан. Установи переменную окружения BOT_TOKEN.")
    # Инициализируем БД
    init_db()
    logger.info("База данных инициализирована.")

    # Запускаем планировщик автопроверок
    scheduler = sched.start_scheduler(bot)
    logger.info("Планировщик запущен.")

    # Удаляем вебхук (на случай если был) и стартуем polling
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Бот запущен, начинаю polling...")

    try:
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown(wait=False)
        await bot.session.close()
        logger.info("Бот остановлен.")


if __name__ == "__main__":
    asyncio.run(main())
