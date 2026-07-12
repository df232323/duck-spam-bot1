FROM python:3.10-slim

WORKDIR /app

# Копируем файл со списком библиотек
COPY requirements.txt .

# СНАЧАЛА обновляем сам установщик pip, а потом устанавливаем библиотеки
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь остальной код
COPY . .

# Запускаем бота
CMD ["python", "app.py"]
