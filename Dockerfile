FROM python:3.11-slim

WORKDIR /app

# Минимальные системные либы для PyQt5 (bundled Qt иногда нужен glib)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libdbus-1-3 \
    && rm -rf /var/lib/apt/lists/*

# Сначала ставим зависимости (кеш Docker)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код
COPY . .

# Создаём нужные директории
RUN mkdir -p accounts temp

CMD ["python", "bot.py"]
