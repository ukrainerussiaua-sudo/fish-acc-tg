# ==============================
#  scheduler.py — автопроверки
# ==============================

import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from config import ADMIN_IDS, SESSION_CHECK_INTERVAL
from tg_utils import check_all_sessions

logger = logging.getLogger(__name__)


async def job_check_sessions(bot):
    """
    Проверяет все активные сессии.
    При обнаружении слетевших — уведомляет всех админов.
    """
    logger.info("Автопроверка сессий запущена...")
    try:
        dead_list = await check_all_sessions()
    except Exception as e:
        logger.error(f"Ошибка при автопроверке сессий: {e}")
        return

    if not dead_list:
        logger.info("Все сессии живы.")
        return

    # Формируем сообщение для админов
    lines = []
    for item in dead_list:
        status_emoji = "💀" if item["status"] == "dead" else "🚫"
        lines.append(
            f"{status_emoji} Акк <b>#{item['id']}</b> | "
            f"<code>{item['phone']}</code> | "
            f"Статус: <b>{item['status']}</b> | "
            f"Был выдан: <code>{item['given_to']}</code>"
        )

    text = (
        f"⚠️ <b>Автопроверка сессий</b>\n\n"
        f"Обнаружено слетевших аккаунтов: <b>{len(dead_list)}</b>\n\n"
        + "\n".join(lines)
    )

    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, text, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Не удалось отправить уведомление админу {admin_id}: {e}")

    logger.info(f"Автопроверка завершена. Слетело: {len(dead_list)} аккаунтов.")


def start_scheduler(bot) -> AsyncIOScheduler:
    """
    Запускает APScheduler с задачами автопроверки.
    Возвращает объект scheduler для корректного завершения.
    """
    scheduler = AsyncIOScheduler()

    scheduler.add_job(
        job_check_sessions,
        trigger=IntervalTrigger(seconds=SESSION_CHECK_INTERVAL),
        args=[bot],
        id="check_sessions",
        name="Автопроверка сессий",
        replace_existing=True,
        # Первый запуск — через 60 секунд после старта бота
        misfire_grace_time=60,
    )

    scheduler.start()
    logger.info(
        f"Планировщик запущен. Проверка сессий каждые "
        f"{SESSION_CHECK_INTERVAL // 60} мин."
    )
    return scheduler
