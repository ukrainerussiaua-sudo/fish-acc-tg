# Локальная SQLite

База хранится локально в `data/bot.sqlite3`.

`BOT_TOKEN` и `ADMIN_IDS` задаются через переменные окружения.

Запуск:

```bash
python -m pip install -r requirements.txt
export BOT_TOKEN='...'
export ADMIN_IDS='123456789'
python bot.py
```

В исходниках не храните токен Telegram-бота. Если старый токен уже был раскрыт, отзовите его через BotFather и создайте новый.
