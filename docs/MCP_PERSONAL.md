# MCP для личного использования

Это руководство по использованию MCP сервера graphify как **личного инструмента** для исследования проекта — без постоянной интеграции с Claude Desktop.

---

## 🎯 Зачем MCP "для себя"?

MCP сервер позволяет:
- **Интерактивно исследовать** граф в реальном времени
- **Делать сложные запросы** на естественном языке
- **Находить неочевидные связи** между компонентами
- **Понимать влияние изменений** перед их внедрением

**Когда это полезно:**
- Перед началом работы над новой функцией
- При отладке сложных проблем
- При исследовании чужого кода
- При необходимости понять "как это связано с тем"

---

## 🚀 Быстрый старт

### Вариант 1: Запуск по запросу (рекомендуется)

MCP сервер запускается только когда нужен — не работает постоянно.

```bash
# Windows (двойной клик)
graphify\mcp-personal.bat

# Linux/Mac
python -m graphify.serve graphify-out/graph.json

# Сервер работает на порту 8000
# Можно делать запросы через curl или другой инструмент
```

**Плюсы:**
- ✅ Не потребляет ресурсы когда не нужен
- ✅ Можно запускать из любой директории
- ✅ Нет настройки в Claude Desktop

**Минусы:**
- ❌ Нужно помнить команду запуска
- ❌ Нет интеграции с Claude

---

### Вариант 2: Временная интеграция с Claude Desktop

Включить MCP только на время работы над проектом.

```bash
# 1. Запустить настройку
cd graphify
python setup-mcp.py

# 2. Перезапустить Claude Desktop

# 3. Работать с графом через Claude

# 4. После работы - удалить из конфига
```

**Плюсы:**
- ✅ Удобно - работает в Claude
- ✅ Можно включить/выключить

**Минусы:**
- ❌ Нужно перезапускать Claude

---

### Вариант 3: Фоновый режим (для долгосрочных проектов)

MCP сервер работает постоянно, обновляется при изменениях.

```bash
# Запустить в фоновом режиме
Start-Process python -ArgumentList "-m","graphify.serve","graphify-out/graph.json"
```

**Плюсы:**
- ✅ Всегда доступен
- ✅ Можно обновлять при изменениях

**Минусы:**
- ❌ Постоянно потребляет ресурсы
- ❌ Нужно следить за процессом

---

## 🔍 Примеры использования MCP

### Пример 1: Перед началом работы над функцией

```
Задача: Добавить новую обработку в CPCRUD

Шаг 1: Запустить MCP
> graphify\mcp-personal.bat  (Windows)
> python -m graphify.serve graphify-out/graph.json  (Linux/Mac)

Шаг 2: Сделать запросы
> query_graph "Что зависит от CPCRUD и что будет сломано если я изменю метод X?"

Шаг 3: Получить ответ
> Связи:
>   - PositionHelper зависит от CPCRUD
>   - RuleManager использует PositionHelper
>   - 3 теста используют эти модули
>   
>   Рекомендация: Изменения сломают 3 теста

Шаг 4: Закрыть MCP
> Ctrl+C
```

---

### Пример 2: Отладка непонятной проблемы

```
Проблема: Cache refresh не работает после изменений

Шаг 1: Запустить MCP
> graphify\mcp-personal.bat  (Windows)
> python -m graphify.serve graphify-out/graph.json  (Linux/Mac)

Шаг 2: Найти связи
> shortest_path "CacheService" "DatabaseManager"
> Путь: CacheService → CachedDomain → DatabaseManager

Шаг 3: Проверить confidence
> get_node node_id="cache_service_database"
> Рекомендации: 3 INFERRED связи с низким confidence → проверить вручную

Шаг 4: Понять проблему
> query_graph "Почему cache refresh unstable?"
> Анализирует связи и выдаёт рекомендации
```

---

### Пример 3: Понять чужой код

```
Задача: Нужно разобраться в RITM модуле

Шаг 1: Запустить MCP
> graphify\mcp-personal.bat  (Windows)
> python -m graphify.serve graphify-out/graph.json  (Linux/Mac)

Шаг 2: Изучить сообщество
> get_community community_id=13
> Возвращает все ноды в RITM Implementation:
>   - ritm_table, policy_table, approval_locking
>   - Связи с Domain, CacheService, Authentication

Шаг 3: Найти ключевые узлы
> god_nodes
> Показывает: Domain, CacheOrchestrationService, CPAIOPSClient

Шаг 4: Понять потоки
> query_graph "Как работает RITM approval workflow?"
> Описывает весь процесс через связи в графе
```

---

## 🛠️ Практические сценарии

### Сценарий 1: Планирование изменений

```
1. Открыть терминал
2. graphify\mcp-personal.bat  (Windows)
   или python -m graphify.serve graphify-out/graph.json  (Linux/Mac)
3. В другом терминале - делать запросы
4. Когда понял - закрыть (Ctrl+C)
```

### Сценарий 2: Исследование перед code review

```
1. Запустить MCP (graphify\mcp-personal.bat)
2. shortest_path "МойНовыйКод" "СуществующиеКомпоненты"
3. query_graph "Что сломается если я изменю X?"
4. Закрыть MCP, сделать выводы
```

### Сценарий 3: Понять архитектуру

```
1. Запустить MCP (graphify\mcp-personal.bat)
2. god_nodes - увидеть хабы
3. get_community для каждого хаба
4. Построить ментальную карту
5. Закрыть MCP
```

---

## 📋 Доступные MCP инструменты

| Инструмент | Описание | Пример использования |
|------------|-----------|---------------------|
| `query_graph` | Запрос на естественном языке | "Как работает кэширование?" |
| `get_node` | Детали о конкретном узле | Узнать о Domain |
| `get_neighbors` | Все связи узла | Кто использует CPCRUD? |
| `get_community` | Все узлы сообщества | Что в RITM модуле? |
| `god_nodes` | Самые связанные узлы | Главные компоненты |
| `graph_stats` | Статистика графа | Сколько узлов/рёбер? |
| `shortest_path` | Кратчайший путь | Как связаны A и B? |

---

## 💡 Как интегрировать в рабочий процесс

### Перед началом работы над задачей

```bash
# 1. Построить/обновить граф
python graphify-relabel.py

# 2. Открыть GRAPH_REPORT.md - получить обзор
cat graphify-out/GRAPH_REPORT.md | head -50

# 3. Если нужны уточнения - запустить MCP
python -m graphify.serve graphify-out/graph.json

# 4. Сделать запросы (примеры ниже)

# 5. Закрыть MCP и работать
```

### Во время работы

```bash
# Если возник вопрос - быстро запустить MCP
graphify\mcp-personal.bat  # Windows
# или
python -m graphify.serve graphify-out/graph.json  # Linux/Mac

# Сделать один запрос

# Закрыть и продолжить
```

### После завершения работы

```bash
# Обновить граф если были изменения
python graphify-relabel.py

# Посмотреть что изменилось в GRAPH_REPORT.md
```

---

## 🔧 Как делать запросы к MCP

### Через curl (если не интегрирован с Claude)

```bash
# 1. Запустить MCP сервер
graphify\mcp-personal.bat  # Windows
# или
python -m graphify.serve graphify-out/graph.json  # Linux/Mac

# 2. В другом терминале - запросы
curl -X POST http://localhost:8000/tools/query_graph \
  -H "Content-Type: application/json" \
  -d '{"query": "Что связано с CPCRUD?"}'

# 3. Получить JSON с результатом
```

### Через Python скрипт

```python
import requests
import json

# Запрос к MCP серверу
response = requests.post('http://localhost:8000/tools/query_graph',
    json={"query": "Что связано с CPCRUD?"}
result = response.json()

# Обработать результат
print(result['content'])
```

### Через Claude Desktop (если настроен)

Просто спрашивай в чате:
```
/spin Используй graphify MCP чтобы узнать что связано с CPCRUD
```

---

## 📊 Примеры запросов для разных ситуаций

### Перед изменением в коде

```
query_graph: "Что зависит от модуля, который я хочу изменить?"
get_neighbors: node_id="мойдуль"
shortest_path: "мойдуль" "другой_модуль"
```

### При отладке

```
query_graph: "Почему компонент X не видит компонент Y?"
get_node: node_id="компонент_X"
get_neighbors: node_id="компонент_Y"
```

### При изучении архитектуры

```
god_nodes: ""
get_community: community_id=0  # Самое большое сообщество
query_graph: "Как работает [фича]?"
```

### При code review

```
query_graph: "Что затронет это изменение?"
shortest_path: "изменённый_код" "критические_компоненты"
graph_stats: ""
```

---

## 🎯 Рекомендации

### Для твоего случая (FPCR проект)

**Рабочая стратегия:**

1. **Обычный режим** - не использовать MCP
   - Читать `GRAPH_REPORT.md`
   - Открывать `graph.html` визуально
   - Обновлять: `graphify\graphify-relabel.bat` (двойной клик)

2. **Исследовательский режим** - запускать MCP когда нужно
   - Перед сложными изменениями
   - При изучении новых областей
   - Для ответа на вопросы "а что если..."

3. **Запуск MCP по требованию:**
   ```bash
   # Запуск (Windows)
   graphify\mcp-personal.bat

   # Запуск (Linux/Mac)
   python -m graphify.serve graphify-out/graph.json
   
   # Работа (делай запросы)
   
   # Завершение
   Ctrl+C
   ```

---

## 📝 Практический чек-лист

### Когда запускать MCP?

- [ ] Перед сложным рефакторингом
- [ ] При изучении неизвестного модуля
- [ ] Для поиска зависимостей
- [ ] При архитектурных решениях
- [ ] Для понимения влияния изменений

### Когда НЕ запускать?

- [ ] Для рутинных задач (достаточно GRAPH_REPORT.md)
- [ ] Для простых изменений (очевидно что затронуто)
- [ ] Когда граф устарел (сначала `python graphify-relabel.py`)

---

## 🔗 Связанные файлы

- `graphify-out/graph.json` - Граф (обязательно существует)
- `graphify-out/GRAPH_REPORT.md` - Статический отчёт
- `graphify-out/wiki/` - Документация по сообществам
- `graphify-out/community_labels.json` - Лейблы сообществ

---

## 🆘 Нужна помощь?

Если MCP не запускается:
```bash
# Проверить что граф существует
ls graphify-out/graph.json  # Linux/Mac
dir graphify-out\graph.json  # Windows

# Проверить что graphify установлен
pip show graphifyy

# Запустить с отладкой
python -m graphify.serve graphify-out/graph.json --debug
```
