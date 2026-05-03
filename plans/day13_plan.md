# Day 13: LLM Gateway — План

## Задание

Построить HTTP-прокси между пользователем и LLM с input/output guard, rate limiting, cost tracking. Написать 10+ тестов.

## Эволюция от Day 11-12

Days 11-12 — скрипты, запускаемые из CLI. Day 13 — реальный HTTP-сервис, как в production. Это переход от "лабораторных" экспериментов к архитектурному паттерну.

## Предварительные решения

### Куда поместить код
Рассматривали:
1. **Отдельный репозиторий** (llm-gateway/) — чище, production-like
2. **Расширение prompt-injection-lab** ✅ — выбрали, чтобы переиспользовать config.py, .env и паттерны из defenses/

### Стек
- **FastAPI** — async, автодокументация (Swagger), Pydantic validation, TestClient для тестов
- **OpenAI-совместимый API** (`POST /v1/chat/completions`) — можно подключить как drop-in proxy

### Input Guard — два режима

Ключевое архитектурное решение: **BLOCK vs MASK**.

| Режим | Поведение | Когда использовать |
|-------|-----------|-------------------|
| BLOCK | HTTP 400, запрос не уходит в LLM | Высокая безопасность, zero tolerance |
| MASK | Секрет заменяется на `[REDACTED_*]`, запрос проксируется | Баланс безопасности и UX |

MASK выбран по умолчанию — пользователь получает ответ, но его секрет не утекает в LLM.

### Какие секреты детектить

Приоритизировали по частоте реальных инцидентов:
1. **API ключи** (OpenAI, AWS, GitHub, Slack) — самый частый кейс, разработчик копипастит ключ в промпт
2. **Кредитные карты** — с Luhn validation чтобы отсечь false positives (обычные длинные числа)
3. **Email и телефоны** — PII, регулируется GDPR/152-ФЗ
4. **Base64-encoded** — evasion-техника: закодировать ключ в base64
5. **Split secrets** — evasion: "sk-" + "proj-abc" через конкатенацию строк

### Output Guard

Переиспользовали паттерн из Day 12 (`output_validator.py`), расширили:
- **Галлюцинированные ключи** — LLM иногда генерирует реалистичные API ключи (особенно в примерах кода)
- **System prompt leakage** — сравнение ответа с system prompt (порог: 2+ значимых строк совпали)
- **Dangerous commands** — `rm -rf /`, `curl | sh` — модель может предложить деструктивные команды
- **Suspicious URLs** — IP-based URL'ы, подозрительные TLD

### Rate Limiter

- In-memory sliding window — достаточно для PoC, в production → Redis
- 10 req/min per IP — разумный лимит для демонстрации
- HTTP 429 с `Retry-After` header — стандартное поведение

### Cost Tracker

- Считаем tokens из OpenAI response (prompt_tokens + completion_tokens)
- Расчёт стоимости по модели (таблица цен зашита)
- `/stats` endpoint — просмотр накопленной статистики
- В production → Prometheus metrics + Grafana dashboard

### Тесты — 3 уровня

1. **Unit tests** (input_guard) — 12 кейсов: от чистого промпта до base64 evasion
2. **Unit tests** (output_guard) — 8 кейсов: утечки ключей, URL, команды, system prompt
3. **Integration tests** (FastAPI TestClient) — 8 кейсов: full flow через HTTP

Особое внимание:
- **False positive test**: "skip" ≠ "sk-ip" — word boundary проверка
- **Luhn validation**: невалидная карта не должна детектиться
- **Mock OpenAI**: integration тесты не делают реальных API вызовов

## Результат

- 34/34 тестов пройдено
- Gateway работает как drop-in proxy для OpenAI API
- Все компоненты (guards, rate limiter, cost tracker, audit log) интегрированы
