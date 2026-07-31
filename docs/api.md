# API Kanban Board 1.2.0

Базовый путь: `/api/v1`. Все защищённые запросы используют:

```http
Authorization: Bearer <access-token>
Content-Type: application/json
X-Request-ID: <uuid-или-произвольный-id>
```

Мутации дополнительно принимают `client_request_id`. Для изменения существующей сущности
требуется `expected_version`.

## Системные endpoints

```text
GET /health
GET /ready
```

`/ready` проверяет SQLite, обязательные таблицы и Alembic revision `20260730_0002`.

Пример:

```json
{
  "status": "ok",
  "appVersion": "1.2.0",
  "apiVersion": "v1",
  "database": "ok",
  "alembicRevision": "20260730_0002"
}
```

## Авторизация

```text
POST /auth/login
POST /auth/refresh
POST /auth/logout
GET  /auth/me
POST /auth/change-password
```

Login:

```json
{
  "username": "user01",
  "password": "..."
}
```

Access token живёт 12 часов. Refresh token живёт 30 дней и ротируется при использовании.

## Каталог пользователей

```text
GET /users?active_only=true
```

Доступен только авторизованным пользователям. Возвращает данные, достаточные для назначения
ответственного:

```json
{
  "items": [
    {
      "id": "uuid",
      "username": "user01",
      "display_name": "Иван Петров",
      "is_active": true
    }
  ]
}
```

Управление пользователями через публичный API намеренно отсутствует; владелец использует CLI
`scripts.manage_users` на сервере.

## Доски

```text
GET    /boards?archived=false
POST   /boards
GET    /boards/{board_id}
PATCH  /boards/{board_id}
DELETE /boards/{board_id}
POST   /boards/{board_id}/restore
GET    /boards/{board_id}/snapshot
GET    /boards/{board_id}/revision
GET    /boards/{board_id}/activity?limit=50&before_id=<id>
```

Snapshot содержит доску, активные колонки и карточки. В 1.2 карточка snapshot дополнительно
содержит:

```json
{
  "assignee_user_id": "uuid-or-null",
  "assignee": {
    "id": "uuid",
    "username": "user01",
    "display_name": "Иван Петров"
  },
  "completed_at": null,
  "comment_count": 2,
  "checklist_total": 4,
  "checklist_completed": 1
}
```

Тексты комментариев и пункты чек-листа в snapshot не включаются; они загружаются при открытии
карточки.

## Колонки

```text
POST   /boards/{board_id}/columns
PATCH  /columns/{column_id}
DELETE /columns/{column_id}
PUT    /boards/{board_id}/columns/order
```

Удаление непустой колонки требует `card_action=move` с `target_column_id` либо
`card_action=archive`.

Сворачивание колонок не является общей серверной операцией. Это персональное состояние
браузера в `localStorage`.

## Карточки

```text
POST   /boards/{board_id}/cards
GET    /cards/{card_id}
PATCH  /cards/{card_id}
DELETE /cards/{card_id}
POST   /cards/{card_id}/restore
POST   /cards/{card_id}/move
```

### Создание карточки

```json
{
  "column_id": "uuid",
  "title": "Подготовить концепцию",
  "description": "Согласовать структуру с командой",
  "priority": "high",
  "due_date": "2026-08-03T15:00:00Z",
  "assignee_user_id": "uuid",
  "target_index": 0,
  "client_request_id": "uuid"
}
```

`assignee_user_id` должен принадлежать активному пользователю.

### Детальная карточка

`GET /cards/{card_id}` возвращает summary-поля, активные комментарии и весь чек-лист:

```json
{
  "id": "uuid",
  "title": "Подготовить концепцию",
  "assignee_user_id": "uuid",
  "completed_at": null,
  "comment_count": 1,
  "checklist_total": 2,
  "checklist_completed": 1,
  "comments": [],
  "checklist_items": []
}
```

### Изменение карточки

```json
{
  "title": "Новое название",
  "assignee_user_id": "uuid",
  "completed": true,
  "expected_version": 4,
  "client_request_id": "uuid"
}
```

Для очистки используются отдельные флаги:

```json
{
  "clear_description": true,
  "clear_due_date": true,
  "clear_assignee": true,
  "expected_version": 4,
  "client_request_id": "uuid"
}
```

`completed=true` устанавливает `completed_at` по серверному UTC-времени. `completed=false`
очищает его. Завершение независимо от колонки.

## Комментарии

```text
POST   /cards/{card_id}/comments
PATCH  /comments/{comment_id}
DELETE /comments/{comment_id}
```

Создание:

```json
{
  "body": "Согласовал с Антоном, встречу можно ставить после пятницы.",
  "client_request_id": "uuid"
}
```

Изменение:

```json
{
  "body": "Уточнённый текст",
  "expected_version": 1,
  "client_request_id": "uuid"
}
```

Редактировать и удалять можно только собственный комментарий. Удаление мягкое: строка остаётся
в базе и журнале, но не возвращается в детальной карточке и не входит в `comment_count`.

## Чек-лист

```text
POST   /cards/{card_id}/checklist-items
PATCH  /checklist-items/{item_id}
POST   /checklist-items/{item_id}/move
DELETE /checklist-items/{item_id}
```

Создать пункт:

```json
{
  "text": "Получить согласование",
  "target_index": 0,
  "client_request_id": "uuid"
}
```

Изменить текст или выполнение:

```json
{
  "text": "Получить письменное согласование",
  "is_completed": true,
  "expected_version": 2,
  "client_request_id": "uuid"
}
```

Переместить:

```json
{
  "target_index": 1,
  "expected_version": 3,
  "client_request_id": "uuid"
}
```

При выполнении сервер заполняет `completed_at` и `completed_by_user_id`. При снятии отметки
оба поля очищаются.

## Ошибки

Единый формат:

```json
{
  "error": {
    "code": "CARD_VERSION_CONFLICT",
    "message": "Карточка уже была изменена другим пользователем",
    "details": {
      "entityId": "uuid",
      "currentVersion": 5
    }
  },
  "requestId": "..."
}
```

Основные коды совместной работы:

```text
USER_NOT_FOUND / USER_DISABLED
CARD_VERSION_CONFLICT
COMMENT_NOT_FOUND / COMMENT_FORBIDDEN / COMMENT_VERSION_CONFLICT
CHECKLIST_ITEM_NOT_FOUND / CHECKLIST_ITEM_VERSION_CONFLICT
NO_CHANGES
CLIENT_REQUEST_ID_REUSED
```

## Идемпотентность и конкуренция

Создание и мутации принимают UUID `client_request_id`. Он сохраняется вместе с
`activity_log`. Повтор того же запроса не должен создавать вторую сущность. UUID нельзя
повторно использовать для другого действия.

Карточки, комментарии и пункты чек-листа имеют `version`. При несовпадении
`expected_version` сервер возвращает `409`, а frontend загружает актуальное состояние.
