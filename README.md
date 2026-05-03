# Prompt Injection Lab — Day 11

Лабораторная работа по изучению prompt injection: векторы атак и методы защиты.

## Сценарий

**MedPlus AI** — виртуальный ассистент медицинской клиники. System prompt содержит "конфиденциальные" данные (цены, маржа, промокоды). Задача: извлечь эти данные через prompt injection, затем защитить бота.

## Структура

```
src/bot.py              — Naive бот (жертва)
src/bot_hardened.py      — Защищённая версия
attacks/attack_01_*.py   — Скрипты атак по категориям
attacks/runner.py        — Автоматический прогон всех атак
collection/              — Коллекция реальных инъекций
reports/                 — Результаты тестов
```

## Запуск

```bash
# Setup
cp .env.example .env     # добавить OPENAI_API_KEY
pip install -r requirements.txt

# Интерактивный чат с ботом
cd src && python bot.py

# Автоматический прогон атак
cd src && python -m attacks.runner            # naive bot
cd src && python -m attacks.runner --hardened  # hardened bot
```

## Задания

1. **3 техники атаки**: role-play, instruction override, extraction
2. **Коллекция 5 инъекций** из открытых источников с классификацией
3. **Атака своего промпта** — ломаем MedPlus AI
4. **Hardened system prompt** — защищённая версия
5. **Тестирование защиты** — те же атаки на hardened версию
