# Архитектура Kanban Board 1.2.0

## Компоненты

```text
GitHub Pages SPA
  ├─ runtime config polling
  ├─ access/refresh token client
  ├─ board snapshot/revision polling
  └─ responsive card drawer

Cloudflare Quick Tunnel
  └─ HTTPS → http://127.0.0.1:8000

FastAPI
  ├─ auth
  ├─ boards / columns / cards
  ├─ comments / checklist / user directory
  ├─ activity log
  └─ health / readiness

SQLite WAL
  └─ Alembic revision 20260730_0002
```

Frontend статический и не содержит секретов. Backend слушает только loopback. Публичный адрес
меняется при каждом старте; frontend узнаёт его из `runtime-config.json`.

## Модель доступа

Ролей внутри приложения нет. Каждый активный пользователь:

- видит все доски;
- может менять доски, колонки и карточки;
- может назначать любого активного пользователя ответственным;
- может писать комментарии;
- может редактировать и удалять только собственные комментарии.

Администрирование учётных записей выполняется локальным CLI. Это исключает публичный endpoint
создания пользователей.

## Модель данных

### `users`

Учётные записи, Argon2id hash и признак активности. Пользователь не удаляется физически.

### `boards`

Содержит `revision` для дешёвой проверки изменений и `version` для optimistic locking.

### `columns`

Позиция, WIP-limit, признак done и soft archive.

### `cards`

Основные поля:

```text
id, board_id, column_id
text fields, priority, due_date
assignee_user_id
completed_at
position, version
created_by_user_id, updated_by_user_id
archived_at, timestamps
```

`assignee_user_id` nullable. Завершение не привязано автоматически к done-колонке.

### `card_comments`

```text
id, card_id, author_user_id
body, version
edited_at, deleted_at
timestamps
```

Удаление мягкое, чтобы не разрушать аудит. Полные тексты комментариев не пишутся в технический
лог.

### `card_checklist_items`

```text
id, card_id, text, position
is_completed
completed_by_user_id, completed_at
version, timestamps
```

Позиции плотные, начиная с нуля. Перестановка выполняется под общей write-блокировкой.

### `activity_log`

Append-only предметный журнал. Содержит тип действия, сущность, краткое описание, безопасные
структурированные детали и `client_request_id`.

## Согласованность записи

SQLite работает с одним Uvicorn worker. Все составные мутации проходят через
`WriteCoordinator` и одну транзакцию:

1. проверяется idempotency key;
2. проверяются версия и ограничения;
3. меняются сущность и зависимые позиции;
4. увеличиваются `card.version`, `board.version` и `board.revision`;
5. добавляется activity record;
6. выполняется commit.

Это предотвращает промежуточное состояние, когда комментарий создан, а revision доски не
обновлён.

## Polling

Frontend проверяет revision активной доски. При изменении загружает новый snapshot. Во время
перетаскивания обновление откладывается, чтобы не разрушать drag state.

Детали комментариев и чек-листа загружаются отдельным `GET /cards/{id}` только при открытии
панели. Snapshot хранит агрегаты для компактных индикаторов. Так доска не передаёт весь текст
комментариев на каждом polling.

## Персональное UI-состояние

Свёрнутые колонки хранятся в браузере:

```text
kanban.collapsedColumns.<boardId>
```

Открытость панели фильтров также хранится локально. Эти настройки не влияют на других
пользователей и не создают серверных конфликтов.

## SQLite

Для соединений включены:

```sql
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA busy_timeout = 10000;
```

Schema readiness проверяет revision и таблицы:

```text
users, refresh_tokens, boards, columns, cards,
card_comments, card_checklist_items, activity_log, alembic_version
```

## Безопасность

- Argon2id для паролей;
- JWT access 12 часов;
- ротационный refresh 30 дней, в базе только SHA-256 digest;
- rate limit login по IP + username;
- CORS ограничен origin GitHub Pages и локальной разработкой;
- backend не слушает LAN-интерфейс;
- секреты, пароли, токены и полные описания не логируются.

Quick Tunnel не заменяет инфраструктуру с SLA. Он подходит для внутренней команды при
понимании, что доступ зависит от домашнего/офисного компьютера и бесплатного сервиса.

## Когда переходить на PostgreSQL

Переход нужен при устойчивом проявлении хотя бы одного условия:

- необработанные `database is locked`;
- очередь записи держится более 5 секунд;
- p95 локальной мутации выше 1 секунды;
- заметно больше 30 одновременно активных пользователей;
- необходимы несколько backend workers или несколько серверов;
- появляются тяжёлые вложения, отчёты или сложные зависимости задач.

Публичное API можно сохранить; изменятся SQLAlchemy URL, драйвер, миграция данных и стратегия
блокировок.
