# Day 15: Red Team Challenge — План

## Задание

Развернуть публичный CTF-челлендж: бот с hardened prompt доступен онлайн, участники пытаются сломать через prompt injection. Логирование всех попыток для отчёта.

## Ключевые решения

### Формат — CTF с флагами
Вместо абстрактного "попробуй сломать" — конкретные цели: 3 секрета в system prompt = 3 флага. Участники видят scoreboard, знают сколько флагов найдено. Gamification мотивирует.

### Веб-чат + API
- **Web UI** для новичков — простой chat в браузере, как ChatGPT
- **API** для продвинутых — curl/скрипты для автоматизированных атак
- Оба вектора логируются одинаково

### Бот = hardened MedPlus из Day 11
Переиспользуем system prompt с 5-слойной защитой (identity anchoring, explicit attack enumeration, input delimiting, data isolation, sandwich defense). Секреты те же: промокод, телефон, себестоимость.

### Cost cap $2
- Глобальный счётчик токенов → стоимость по модели
- При $2 → HTTP 503 "budget exhausted"
- Сохраняется на диск (переживает рестарт)
- gpt-4o-mini = $0.15/1M input + $0.60/1M output → ~2600 запросов за $2

### Rate limiting
- 5 req/min per IP — жёстче чем gateway (публичный сервис)
- Достаточно для ручных попыток, блокирует автоматический brute force

### Audit log
- JSONL: timestamp, IP, message, response, tokens, cost, detected leaks
- `GET /api/audit/download?key=ADMIN_KEY` — скачивание для отчёта
- Это и есть "отчёт атакующего" — все попытки с результатами

### Docker
- Single service, no DB — state в файлах (cost_state.json, audit.jsonl)
- Docker volume для persistence
- `docker compose up -d` — один шаг на VPS

### Безопасность UI
- Никакого innerHTML — всё через textContent (XSS prevention)
- Message length limit (2000 chars)
- Escaping всех данных от сервера

## Результат

- Challenge app работает локально (uvicorn)
- Web chat + API endpoint + scoreboard
- Cost guard ($2 cap) + rate limiter (5/min)
- Полное audit logging, скачиваемое
- Docker ready для VPS deploy
