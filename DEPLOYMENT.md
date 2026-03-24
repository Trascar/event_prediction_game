# Деплой прототипа

## Вариант 1: Render.com (бесплатно, быстро)

1. Создайте аккаунт на render.com
2. Создайте новый Web Service
3. Подключите GitHub репозиторий
4. Настройки:
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
5. Добавьте Environment Variable: `GEMINI_API_KEY` или `GROQ_API_KEY`
6. Deploy!

## Вариант 2: Railway.app (еще проще)

1. Установите Railway CLI или используйте веб-интерфейс
2. `railway login`
3. `railway init`
4. `railway add` - добавьте переменную GEMINI_API_KEY или GROQ_API_KEY
5. `railway up`

## Вариант 3: Локальный запуск с ngrok

1. Запустите сервер локально:
```bash
uvicorn main:app --reload
```

2. В другом терминале:
```bash
ngrok http 8000
```

3. Получите публичный URL и отправьте его

## Вариант 4: Docker (универсальный)

Создайте `Dockerfile`:
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Запуск:
```bash
docker build -t event-game .
docker run -p 8000:8000 -e GEMINI_API_KEY=your_key event-game
```
