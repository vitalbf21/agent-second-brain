# Todoist Integration

## Task Links Format

ВАЖНО: Todoist изменил формат ссылок. Используй НОВЫЙ формат:

✅ Правильно: `https://app.todoist.com/app/task/{task_id}`
❌ Устарело: `https://todoist.com/showTask?id={task_id}`
❌ Устарело: `https://todoist.com/app/task/{task_id}`

Если MCP tool вернул task с `url` полем — используй его напрямую.
Если нужно построить ссылку из task_id — используй формат выше.

---

## Todoist через mcp-cli

**ВСЕГДА используй mcp-cli. НЕ используй MCP tools напрямую.**

### Reading Tasks

```bash
# Обзор всех проектов
mcp-cli call todoist get-overview '{}'

# Поиск по тексту, проекту, секции
mcp-cli call todoist find-tasks '{"searchText": "keyword"}'

# Задачи по дате
mcp-cli call todoist find-tasks-by-date '{"startDate": "today", "daysCount": 7}'
```

### Writing Tasks

```bash
# Создать задачу
mcp-cli call todoist add-tasks '{"tasks": [{"content": "Task", "dueString": "tomorrow", "priority": 2}]}'

# Завершить задачу
mcp-cli call todoist complete-tasks '{"ids": ["task_id"]}'

# Обновить задачу
mcp-cli call todoist update-tasks '{"tasks": [{"id": "task_id", "content": "New title"}]}'
```

---

## Pre-Creation Checklist

### 1. Check Workload (REQUIRED)

```bash
mcp-cli call todoist find-tasks-by-date '{"startDate": "today", "daysCount": 7, "limit": 50}'
```

Build workload map:
```
Mon: 2 tasks
Tue: 4 tasks  ← overloaded
Wed: 1 task
Thu: 3 tasks  ← at limit
Fri: 2 tasks
Sat: 0 tasks
Sun: 0 tasks
```

### 2. Check Duplicates (REQUIRED)

```bash
mcp-cli call todoist find-tasks '{"searchText": "key words from new task"}'
```

If similar exists → mark as duplicate, don't create.

---

## Priority by Domain

Based on user's work context (see [ABOUT.md](ABOUT.md)):

| Domain | Default Priority | Override |
|--------|-----------------|----------|
| Client Work | p1-p2 | — |
| Agency Ops (urgent) | p2 | — |
| Agency Ops (regular) | p3 | — |
| Content (with deadline) | p2-p3 | — |
| Product/R&D | p4 | масштабируемость → p3 |
| AI & Tech | p4 | автоматизация → p3 |

### Priority Keywords

| Keywords in text | Priority |
|-----------------|----------|
| срочно, критично, дедлайн клиента | p1 |
| важно, приоритет, до конца недели | p2 |
| нужно, надо, не забыть | p3 |
| (strategic, R&D, long-term) | p4 |

### Apply Decision Filters for Priority Boost

If entry matches 2+ filters → boost priority by 1 level:
- Это масштабируется?
- Это можно автоматизировать?
- Это усиливает экспертизу [Your Business]?
- Это приближает к продукту/SaaS?

---

## Date Mapping

| Context | dueString |
|---------|-----------|
| **Client deadline** | exact date |
| **Urgent ops** | today / tomorrow |
| **This week** | friday |
| **Next week** | next monday |
| **Strategic/R&D** | in 7 days |
| **Not specified** | in 3 days |

### Russian → dueString

| Russian | dueString |
|---------|-----------|
| сегодня | today |
| завтра | tomorrow |
| послезавтра | in 2 days |
| в понедельник | monday |
| в пятницу | friday |
| на этой неделе | friday |
| на следующей неделе | next monday |
| через неделю | in 7 days |
| 15 января | January 15 |

---

## Task Creation

```bash
mcp-cli call todoist add-tasks '{"tasks": [{"content": "Task title", "dueString": "friday", "priority": 4}]}'
```

С projectId:
```bash
mcp-cli call todoist add-tasks '{"tasks": [{"content": "Task title", "dueString": "friday", "priority": 4, "projectId": "..."}]}'
```

### Task Title Style

User prefers: прямота, ясность, конкретика

✅ Good:
- "Отправить презентацию [Client A]"
- "Созвон с командой по AI-агентам"
- "Написать пост про Claude MCP"

❌ Bad:
- "Подумать о презентации"
- "Что-то с клиентом"
- "Разобраться с AI"

### Workload Balancing

If target day has 3+ tasks:
1. Find next day with < 3 tasks
2. Use that day instead
3. Mention in report: "сдвинуто на {day} (перегрузка)"

---

## Project Detection

Based on work domains:

| Keywords | Project |
|----------|---------|
| [Client A], [Client B], клиент, бренд | Client Work |
| [Your Business], агентство, команда, найм | Agency Ops |
| продукт, SaaS, MVP | Product |
| пост, @yourbrand, контент | Content |

If unclear → use Inbox (no projectId).

---

## Client Labels

При создании задач связанных с клиентом, добавляй label.

### Format
`client:{kebab-case-name}`

### Примеры
- client:acme-corp
- client:techco
- client:phonebrand

### Использование
```bash
mcp-cli call todoist add-tasks '{"tasks": [{"content": "Follow-up [Client A] по проекту", "labels": ["client:acme-corp", "deadline"]}]}'
```

### Фильтр в Todoist
`@client:acme-corp` — все задачи по [Client A]

---

## Anti-Patterns (НЕ СОЗДАВАТЬ)

Based on user preferences:

- ❌ "Подумать о..." → конкретизируй действие
- ❌ "Разобраться с..." → что именно сделать?
- ❌ Абстрактные задачи без Next Action
- ❌ Дубликаты существующих задач
- ❌ Задачи без дат

---

## Error Handling

CRITICAL: Никогда не предлагай "добавить вручную".

If `add-tasks` fails:
1. Include EXACT error message in report
2. Continue with next entry
3. Don't mark as processed
4. User will see error and can debug

WRONG output:
  "Не удалось добавить (MCP недоступен). Добавь вручную: Task title"

CORRECT output:
  "Ошибка создания задачи: [exact error from MCP tool]"

---

## Recurring Tasks for Process Goals

When creating process commitments → use dueString with recurring pattern.

### Recurring Patterns

| Process Description | dueString |
|---------------------|-----------|
| каждое утро в 6 | every day at 6am |
| каждый день | every day |
| каждый рабочий день | every weekday |
| 3 раза в неделю | every monday, wednesday, friday |
| раз в неделю | every week |
| каждый понедельник | every monday |
| каждую пятницу | every friday |

### Example: Creating Process Goal Tasks

```bash
mcp-cli call todoist add-tasks '{"tasks": [
  {"content": "2h deep work: программа [Client B]", "dueString": "every day at 6am", "priority": 2, "labels": ["process-goal"]},
  {"content": "1 outreach для поиска 2го спикера", "dueString": "every weekday", "priority": 3, "labels": ["process-goal"]}
]}'
```

### Label for Process Goals

Use label `process-goal` for recurring tasks created from Process Commitments.
This allows easy filtering and cleanup.

### When to Create Recurring

Create recurring tasks when:
- Generating weekly digest (new week planning)
- User explicitly asks for process goal setup
- Transforming outcome goal to process (if user confirms)

### Cleanup Stale Recurring

In weekly digest, check:
```bash
mcp-cli call todoist find-tasks '{"labels": ["process-goal"]}'
```
If task from previous week → warn user to complete or delete
