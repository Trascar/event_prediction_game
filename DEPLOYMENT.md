# Деплой прототипа

## Вариант 1: Render.com (бесплатно, быстро)

1. Создайте аккаунт на render.com
2. Создайте новый Web Service
3. Подключите GitHub репозиторий
4. Настройки:
   - **Runtime**: Python 3.11
   - **Build Command**: `pip install --upgrade pip && pip install -r requirements.txt`
   - **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
5. Добавьте Environment Variable: `GEMINI_API_KEY` или `GROQ_API_KEY`
6. Deploy!

**Важно**: Если возникает ошибка с Rust/maturin, используйте файл `render.yaml` (уже включен в проект) или убедитесь, что используете Python 3.11.

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


## Устранение проблем

### Ошибка "maturin failed" или "Rust toolchain" на Render

Эта ошибка возникает когда pip пытается скомпилировать пакеты из исходников вместо использования готовых бинарников.

**Решение 1**: Используйте `render.yaml` (уже включен в проект)
- Render автоматически обнаружит файл и применит настройки
- Убедитесь что Python версия 3.11

**Решение 2**: Обновите Build Command в настройках Render:
```bash
pip install --upgrade pip && pip install -r requirements.txt
```

**Решение 3**: Если проблема сохраняется, используйте Docker деплой:
- В Render выберите "Docker" вместо "Python"
- Render автоматически использует Dockerfile из репозитория

### Проверка работоспособности

После деплоя откройте:
- `https://your-app.onrender.com/` - главная страница игры
- `https://your-app.onrender.com/api/leaderboard` - API таблицы лидеров

### Логи и отладка

На Render:
1. Перейдите в Dashboard → Ваш сервис
2. Откройте вкладку "Logs"
3. Проверьте сообщения о запуске AI провайдеров:
   - `✓ Gemini API configured` - Gemini работает
   - `✓ Groq API configured` - Groq работает
   - `⚠ No AI providers configured` - используется fallback режим
