# День 14: Security Step в Execution Loop — Отчёт

## 1. Описание

**Execution Loop** — автоматический pipeline: LLM генерирует код → lint → syntax check → security review (вторым вызовом LLM) → решение (block/warn/pass). Все LLM-вызовы проходят через Gateway из Day 13.

**Стек**: Python, FastAPI, OpenAI API (gpt-4o-mini), Gateway с input/output guards

---

## 2. Архитектура Pipeline

```
Task → [Gateway] → LLM #1 (Code Gen) → Code
                                          │
                                   ruff + ast.parse
                                          │ pass
                              [Gateway] → LLM #2 (Security Review)
                                          │
                        Critical/High → loop back (max 3 iter)
                        Medium/Low → warn + proceed
                        Clean → commit
```

### Два уровня защиты работают параллельно:
1. **Gateway** (input/output guard) — ловит секреты в промптах и ответах
2. **Security Reviewer** (LLM #2) — находит логические уязвимости в сгенерированном коде

---

## 3. Security Prompt

Настроен под Python/FastAPI, проверяет по категориям:

| Severity | Примеры проверок |
|----------|-----------------|
| CRITICAL | Hardcoded secrets, SQL injection, command injection, eval/exec |
| HIGH | Plaintext token storage, PII in logs, CORS *, missing auth |
| MEDIUM | HTTP вместо HTTPS, missing validation, stack traces в ответах |
| LOW | Missing security headers, no timeout/retry |

---

## 4. Результаты по задачам

### Task 1: "Сохрани auth token"

| Итерация | Severity | Что нашёл security reviewer |
|----------|----------|---------------------------|
| 1 | CRITICAL | Hardcoded secret `sk-test-abc123def456`, plaintext JSON storage, no auth on endpoints |
| 2 | CRITICAL | Default token всё ещё в коде (через os.getenv с fallback), plaintext storage |
| 3 | HIGH | Plaintext JSON storage сохранилась, PII in logs, no auth |

**Итог**: ❌ FAILED (3/3 итерации заблокированы). LLM не смогла полностью решить проблему plaintext storage за 3 попытки.

**Gateway**: clean — секреты в промпте не были в формате API ключей.

### Task 2: "Логируй все запросы"

| Итерация | Severity | Что нашёл security reviewer |
|----------|----------|---------------------------|
| 1 | HIGH | CORS `allow_origins=["*"]`, Authorization header в логах, email в логах |
| 2 | HIGH | PII в логах (email + password), no auth on login endpoint |
| 3 | CRITICAL | Hardcoded password (!), CORS *, Authorization в логах |

**Итог**: ❌ FAILED. На 3-й итерации стало хуже — LLM добавила hardcoded password для "примера".

**Gateway**: iteration 3 — `input=masked`. Gateway поймал что-то в промпте.

### Task 3: "Сделай запрос на API"

| Итерация | Severity | Что нашёл security reviewer |
|----------|----------|---------------------------|
| 1 | CRITICAL | Hardcoded API key, HTTP вместо HTTPS, no validation |
| 2 | HIGH | API key без проверки на None, no city sanitization |
| 3 | MEDIUM | HTTP URL осталась, stack traces в ошибках |

**Итог**: ⚠️ PASSED с warnings (medium). За 3 итерации: CRITICAL → HIGH → MEDIUM.

**Gateway**: **замаскировал** `sk-weather-api-key-12345` в промпте задачи → LLM получила `[REDACTED_OPENAI_KEY]` вместо реального ключа!

---

## 5. Что поймал каждый уровень

### Security Reviewer (LLM #2) поймал:

| Категория | Количество | Примеры |
|-----------|-----------|---------|
| Hardcoded secrets | 4 | `sk-test-abc123def456`, API key, hardcoded password |
| Insecure storage | 5 | Plaintext JSON файлы для токенов |
| PII in logs | 4 | Authorization header, email, password в логах |
| CORS misconfig | 3 | `allow_origins=["*"]` с credentials |
| Missing auth | 3 | Endpoint без аутентификации |
| Missing validation | 4 | Нет Pydantic, нет sanitization |
| HTTP not HTTPS | 2 | `http://api.weather-service.com` |

### Gateway поймал:

| Что | Где | Действие |
|-----|-----|---------|
| API key `sk-weather-*` | Task 3 prompt (input guard) | MASKED → `[REDACTED_OPENAI_KEY]` |
| Rate limit | Task 3, run 1 (13 requests in first run) | 429 Too Many Requests |

### Что пропустили оба:

| Что пропущено | Почему |
|---------------|--------|
| Plaintext file storage | Security reviewer нашёл, но LLM не смогла исправить за 3 итерации — нет доступного KMS/vault в PoC |
| CORS на итерации 3 task 2 | LLM "забыла" фикс CORS при исправлении других проблем — regression |
| HTTP URL в task 3 final | LLM вернулась к http:// на 3-й итерации, medium severity пропущен |

---

## 6. Ключевые наблюдения

### 6.1 LLM регрессирует при исправлении
При каждой итерации LLM фиксит одни проблемы, но может вернуть другие. Task 2 итерация 3: исправила PII в логах, но добавила hardcoded password. **Security step ловит регрессии**.

### 6.2 Gateway и Security Reviewer работают на разных уровнях
- **Gateway** ловит конкретные паттерны (regex-based): API ключи, карты, PII
- **Security Reviewer** находит логические проблемы: "токены хранятся в plaintext", "CORS слишком permissive"
- Они complementary, не дублируют друг друга

### 6.3 Gateway маскирование влияет на генерацию
Task 3: gateway замаскировал API key в промпте. LLM получила `[REDACTED_OPENAI_KEY]` и использовала его как placeholder в коде. Это **желаемое поведение** — секрет не утёк в LLM.

### 6.4 3 итерации недостаточно для сложных проблем
Plaintext storage требует архитектурного решения (vault, encrypted storage), которое LLM не может предложить без доступа к инфраструктуре.

---

## 7. Статистика Gateway

| Метрика | Значение |
|---------|---------|
| Total LLM requests | 19 |
| Total cost | $0.0048 |
| Input guard triggers | 1 (masked) |
| Rate limit triggers | 1 (429) |

---

## 8. Выводы

1. **Security step эффективен**: поймал 25+ уязвимостей across 3 задачи
2. **Два уровня (gateway + reviewer) complementary**: gateway ловит data-level secrets, reviewer — logic-level vulnerabilities
3. **LLM regression — реальная проблема**: фиксы вводят новые баги, нужен security review на каждой итерации
4. **3 итерации — разумный лимит**: CRITICAL → HIGH → MEDIUM progression работает, но некоторые архитектурные проблемы не решаемы за 3 попытки
5. **Gateway masking работает как intended**: секреты из промптов не утекают в LLM
