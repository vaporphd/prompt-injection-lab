# День 13: LLM Gateway — Отчёт

## 1. Описание

**LLM Gateway** — HTTP-прокси (FastAPI) между пользователем и OpenAI API. Все запросы проходят через цепочку безопасности: rate limiting → input guard → LLM → output guard → ответ. Все запросы и ответы логируются для аудита.

**Стек**: Python, FastAPI, OpenAI API (gpt-4o-mini)

---

## 2. Архитектура

```
User Request → Rate Limiter → Input Guard → OpenAI API → Output Guard → User Response
                   │               │                          │
                  429          BLOCK/MASK                BLOCK if leak
                              + audit log                + audit log
```

### Endpoints:
- `POST /v1/chat/completions` — OpenAI-совместимый прокси
- `GET /stats` — статистика использования и стоимости
- `GET /health` — healthcheck

---

## 3. Input Guard

### Два режима:
- **BLOCK**: отклоняет запрос с HTTP 400, секрет не уходит в LLM
- **MASK**: заменяет секрет на `[REDACTED_*]`, запрос проксируется

### Детектируемые паттерны:

| Категория | Паттерн | Маска |
|-----------|---------|-------|
| OpenAI API key | `sk-proj-*`, `sk-*` | `[REDACTED_OPENAI_KEY]` |
| AWS Access Key | `AKIA*` (16 символов) | `[REDACTED_AWS_KEY]` |
| GitHub Token | `ghp_*`, `gho_*`, `ghs_*` | `[REDACTED_GITHUB_TOKEN]` |
| Slack Token | `xoxb-*`, `xoxp-*` | `[REDACTED_SLACK_TOKEN]` |
| Кредитная карта | 13-19 цифр + Luhn validation | `[REDACTED_CARD]` |
| Email | RFC-совместимый паттерн | `[REDACTED_EMAIL]` |
| Телефон | `+7`, `+1` и др. международные | `[REDACTED_PHONE]` |
| Base64-encoded secret | Decode → проверка на key patterns | `[REDACTED_BASE64_SECRET]` |
| Split secret | `"sk-" + "proj-abc"` | `[REDACTED_SPLIT_KEY]` |
| Generic secret | `token=*`, `api_key=*` | `[REDACTED_SECRET]` |

---

## 4. Output Guard

### Проверки ответа LLM:

| Категория | Severity | Действие |
|-----------|----------|----------|
| Галлюцинированные API ключи | HIGH | Блокировать ответ |
| Утечка system prompt | HIGH | Блокировать ответ |
| Подозрительные URL (IP-based) | MEDIUM | Флаг в логе |
| Вредоносные URL (evil, phish) | HIGH | Блокировать ответ |
| Деструктивные shell-команды | HIGH | Блокировать ответ |
| SQL injection | MEDIUM | Флаг в логе |

---

## 5. Middleware

### Rate Limiter
- Sliding window: 10 запросов / 60 секунд per IP
- HTTP 429 с заголовком `Retry-After`

### Cost Tracker
- Подсчёт prompt + completion tokens из OpenAI response
- Расчёт стоимости по модели (gpt-4o-mini: $0.15/$0.60 per 1M)
- Endpoint `/stats` с историей

---

## 6. Результаты тестирования (34 теста)

### Input Guard (18 тестов):

| # | Тест | Результат |
|---|------|-----------|
| 1 | Чистый промпт (без секретов) | ✅ PASS |
| 2 | OpenAI API key (sk-proj-...) | ✅ Detected + masked |
| 3 | AWS key (AKIAIOSFODNN7EXAMPLE) | ✅ Detected + masked |
| 4 | GitHub token (ghp_...) | ✅ Detected |
| 5 | Кредитная карта (4111...1111, Luhn valid) | ✅ Detected + masked |
| 5b | Невалидная карта (fails Luhn) | ✅ Not detected (correct) |
| 6 | Email в промпте | ✅ Detected + masked |
| 7 | Телефон (+7 999 123-45-67) | ✅ Detected |
| 8 | Base64-encoded API key | ✅ Detected |
| 9 | Split secret ("sk-" + "proj-abc") | ✅ Detected |
| 10 | Несколько секретов в одном промпте | ✅ All detected |
| 11 | False positive "skip" ≠ "sk-" | ✅ Not detected (correct) |
| 12 | Ключ в контексте кода | ✅ Detected |

### Output Guard (8 тестов):

| # | Тест | Результат |
|---|------|-----------|
| 1 | Чистый ответ | ✅ PASS |
| 2 | Утечка OpenAI ключа в ответе | ✅ Blocked |
| 3 | Утечка AWS ключа | ✅ Detected |
| 4 | IP-based URL | ✅ Flagged |
| 5 | Malicious URL | ✅ Detected |
| 6 | rm -rf / | ✅ Blocked |
| 7 | curl pipe shell | ✅ Detected |
| 8 | System prompt leak | ✅ Detected |

### Integration (8 тестов):

| # | Тест | Результат |
|---|------|-----------|
| 1 | Health endpoint | ✅ 200 OK |
| 2 | Clean request proxied | ✅ 200 + response |
| 3 | BLOCK mode rejects secret | ✅ 400 |
| 4 | MASK mode redacts + forwards | ✅ 200 + masked |
| 5 | Output guard blocks leaked key | ✅ content_filter |
| 6 | Rate limit (11th request) | ✅ 429 |
| 7 | Cost tracking via /stats | ✅ tokens + cost |

**Total: 34/34 passed**

---

## 7. Что ловим, что пропускаем

### Ловим:
- Все основные паттерны API ключей (OpenAI, AWS, GitHub, Slack)
- Валидные кредитные карты (Luhn check отсекает false positives)
- Base64-encoded секреты
- Простые split-секреты с конкатенацией строк
- Галлюцинированные ключи в ответах LLM

### Пропускаем (known limitations):
- **ROT13/hex encoded secrets** — нет декодирования кроме base64
- **Описание секрета словами** ("мой ключ начинается с sk, дальше proj, потом...")
- **Стеганография** — секрет в первых буквах каждого слова
- **Multilingual evasion** — секрет транслитерированный кириллицей
- **Контекстный false positive** — обсуждение формата ключей без реального ключа

---

## 8. Выводы

1. **Gateway pattern** — стандарт для production LLM: всё проходит через единую точку контроля
2. **Input guard** эффективен против случайных утечек (пользователь копипастит ключ в промпт) — самый частый реальный сценарий
3. **Output guard** ловит галлюцинации модели — она иногда генерирует реалистичные ключи
4. **Luhn validation** критически важен для credit cards — без него 90% длинных чисел были бы false positives
5. **Base64 detection** — нетривиально: нужно декодировать и проверять содержимое
6. **Rate limiting + cost tracking** — обязательные компоненты для production, предотвращают abuse и контролируют расходы
