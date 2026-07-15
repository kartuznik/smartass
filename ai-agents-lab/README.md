# AI Agents Lab

Учебный мини-проект для освоения LangGraph и построения простого агента с маршрутизацией.

## Неделя 1: Simple Agent

### Архитектура графа

```text
START
  |
  v
[classify_node] --(math)--> [math_node] ----\
          |                                  |
          +--(code)--> [code_node] ---------> END
          |                                  |
          +-(general)-> [general_node] -----/
```

- `classify_node` определяет тип запроса: `math`, `code`, `general`.
- Далее conditional edges направляют выполнение в профильный узел.
- Каждый узел обновляет общее состояние `AgentState`.

### Установка и запуск

1. Создай и активируй виртуальное окружение:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```
2. Установи зависимости:
   ```bash
   pip install -r requirements.txt
   ```
3. Подготовь переменные окружения:
   ```bash
   cp .env.example .env
   ```
   Впиши в `.env` значение `OPENAI_API_KEY`.

### Быстрый запуск агента

```bash
python -c "from agents.simple_agent import run_simple_agent; print(run_simple_agent('2+2=?'))"
```

### Тестирование

```bash
pytest tests/ -v
```

### Примеры запросов и ожидаемых ответов

- Запрос: `2+2=?`
  - Классификация: `math`
  - Ответ: `Math result: 4`
- Запрос: `напиши функцию hello world на python`
  - Классификация: `code`
  - Ответ: Python-сниппет с `def hello_world()`
- Запрос: `привет, как дела?`
  - Классификация: `general`
  - Ответ: дружелюбный общий ответ

## Неделя 2: Multi-Agent Loop

### Концепция

На этой неделе строим multi-agent систему с тремя ролями:
- `Researcher` собирает факты по теме.
- `Writer` готовит черновик.
- `Reviewer` проверяет качество и может вернуть задачу на доработку.

### Архитектура цикла

```text
START -> [research_node] -> [writer_node] -> [reviewer_node]
                                          ^         |
                                          |         |
                                          +----(feedback & revision_count < 2)

[reviewer_node] --(no feedback OR revision_count >= 2)--> END
```

### Как избегаем бесконечных циклов

- `Reviewer` повышает `revision_count`, когда находит проблему в черновике.
- Маршрутизация после ревью:
  - если есть `feedback` и `revision_count < 2` -> вернуться в `writer_node`;
  - иначе -> завершить граф (`END`).
- Это гарантирует, что цикл ограничен максимум двумя возвратами.

### Запуск теста недели 2

```bash
pytest tests/test_multi_agent.py -v
```
