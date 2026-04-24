# MCP Quick Reference

Быстрая справка по использованию MCP сервера graphify "для себя".

---

## 🚀 Быстрый старт

### 1. Запустить MCP сервер

```bash
# Windows (двойной клик)
graphify\mcp-personal.bat

# Linux/Mac
python -m graphify.serve graphify-out/graph.json
```

### 2. Сделать запросы

**Интерактивный режим:**
```bash
graphify\mcp-interactive.bat
```

**Программно:**
```python
python graphify/mcp-queries.py
```

**Или через curl:**
```bash
curl -X POST http://localhost:8000/tools/god_nodes -H "Content-Type: application/json" -d '{}'
```

---

## 📋 Команды

### Интерактивный режим

```
query_graph Что связано с CPCRUD?
get_node domain
get_neighbors cacheorchestrationservice
get_community 0
god_nodes
graph_stats
shortest_path cpcrud domain
```

### Через Python API

```python
import requests

# Статистика
requests.post('http://localhost:8000/tools/graph_stats', json={})

# Топ узлы
requests.post('http://localhost:8000/tools/god_nodes', json={})

# Запрос
requests.post('http://localhost:8000/tools/query_graph',
              json={'query': 'Как работает кэширование?'})

# Путь
requests.post('http://localhost:8000/tools/shortest_path',
              json={'source': 'CPCRUD', 'target': 'Domain'})
```

---

## 💡 Типичные сценарии

### "Я хочу изменить X. Что сломается?"

```bash
# 1. Запустить MCP
mcp-personal.bat

# 2. В другом терминале
mcp-interactive.bat

# 3. В интерактивном режиме:
get_neighbors x
shortest_path x critical_component
query_graph "Что зависит от X?"

# 4. Закрыть, сделать выводы
```

### "Я не понимаю как работает Y"

```bash
# 1. Запустить MCP
mcp-personal.bat

# 2. Изучить:
get_node y
get_neighbors y
get_community [найти ID сообщества]

# 3. Понять контекст через связи
```

### "Какие есть главные компоненты?"

```bash
# 1. Запустить MCP
mcp-personal.bat

# 2. Получить хабы:
mcp-interactive.bat
god_nodes

# Или через GRAPH_REPORT.md:
cat graphify-out/GRAPH_REPORT.md | grep -A 20 "God Nodes"
```

---

## 📊 Полезные запросы

### Архитектура проекта
```
query_graph "Как устроен проект FPCR?"
god_nodes
graph_stats
```

### Конкретные модули
```
query_graph "Как работает CPCRUD?"
get_node cpcrud
get_neighbors cpcrud
```

### Зависимости
```
shortest_path CPCRUD Domain
get_neighbors cacheorchestrationservice
```

### Тестирование
```
get_community 41  # Test Suite
query_graph "Что тестируется вместе с X?"
```

---

## 🎯 Рабочий процесс

### Перед изменением
```bash
# 1. Обновить граф
python graphify-relabel.py

# 2. Запустить MCP
mcp-personal.bat

# 3. Исследовать
mcp-interactive.bat
> query_graph "Что сломается если я изменю X?"
> shortest_path X Y

# 4. Закрыть, работать
```

### При застревании
```bash
# 1. Запустить MCP
mcp-personal.bat

# 2. Исследовать проблему
mcp-interactive.bat
> query_graph "Почему компонент X не видит Y?"
> get_neighbors X
> get_neighbors Y

# 3. Понять и исправить
```

### После изменений
```bash
# Обновить граф
python graphify-relabel.py

# Проверить что появилось нового
cat graphify-out/GRAPH_REPORT.md | grep -A 10 "Surprising"
```

---

## 🔧 Устранение проблем

### MCP сервер не запускается

```bash
# Проверить граф
ls graphify-out/graph.json

# Проверить graphify
pip show graphifyy

# Пробный запуск с отладкой
python -m graphify.serve graphify-out/graph.json --debug
```

### Port 8000 уже занят

```bash
# Windows
netstat -ano | findstr :8000

# Linux/Mac
lsof -i :8000

# Убить процесс или использовать другой порт
```

### Нет ответа на запросы

```bash
# Проверить что сервер жив
curl http://localhost:8000/

# Перезапустить сервер
```

---

## 📚 Полная документация

- `docs/MCP_PERSONAL.md` - Полное руководство
- `docs/MCP_CONFIG.md` - Конфигурация MCP
- `docs/GRAPHIFY_INTEGRATION.md` - Интеграция с ассистентами

---

## 🆘 Горячие клавиши

В интерактивном режиме:

| Команда | Для чего |
|---------|----------|
| `q` | Выход |
| `god_nodes` | Топ узлы (хабы) |
| `graph_stats` | Статистика |
| `query_graph <text>` | Естественный язык |
| `shortest_path A B` | Путь между A и B |
| `get_node <id>` | Детали узла |
| `get_neighbors <id>` | Связи узла |
| `get_community <id>` | Всё сообщество |

---

## 💡 Советы

1. **Не держи MCP всегда включенным** - запускай когда нужен
2. **Обновляй граф после изменений** - `python graphify-relabel.py`
3. **Используй graph.html для визуального исследования** - оно быстрее
4. **GRAPH_REPORT.md для обзора** - MCP для уточнений
5. **Интерактивный режим для исследований** - mcp-interactive.bat

---

**Создано для личного использования graphify MCP как инструмента исследования проекта.**
