# API

Базовый путь: `/api/v1`. Формат: JSON. Интерактивная OpenAPI-документация локально:

- `http://127.0.0.1:8000/api/docs`;
- `http://127.0.0.1:8000/api/redoc`;
- схема: `http://127.0.0.1:8000/api/v1/openapi.json`.

Защищённые маршруты требуют:

```http
Authorization: Bearer <access_token>
```

Каждый ответ содержит `X-Request-ID` и `X-Server-Time`.

## Ошибка

```json
{
  "error": {
    "code": "CARD_VERSION_CONFLICT",
    "message": "Карточка уже была изменена другим пользователем",
    "details": {
      "entityId": "uuid",
      "currentVersion": 8
    },
    "requestId": "uuid"
  }
}
```

| HTTP | Смысл |
| --- | --- |
| 200 | успешный запрос |
| 201 | сущность создана |
| 204 | успешный запрос без тела |
| 400 | некорректная бизнес-операция |
| 401 | токен отсутствует, истёк или недействителен |
| 403 | пользователь отключён |
| 404 | сущность не найдена |
| 409 | version, WIP, порядок или идемпотентность |
| 422 | ошибка валидации Pydantic |
| 429 | превышено ограничение входа |
| 503 | база или схема не готовы |

## Авторизация

| Метод | Путь | Тело |
| --- | --- | --- |
| POST | `/auth/login` | `username`, `password` |
| POST | `/auth/refresh` | `refresh_token` |
| POST | `/auth/logout` | `refresh_token` |
| GET | `/auth/me` | — |
| POST | `/auth/change-password` | `current_password`, `new_password` |

Ответ login/refresh:

```json
{
  "access_token": "<jwt>",
  "refresh_token": "<jwt>",
  "token_type": "bearer",
  "expires_in": 43200,
  "refresh_expires_in": 2592000,
  "user": {
    "id": "uuid",
    "username": "user01",
    "display_name": "Пользователь 01",
    "is_active": true
  }
}
```

## Доски

| Метод | Путь | Назначение |
| --- | --- | --- |
| GET | `/boards?archived=false` | активные или архивные доски |
| POST | `/boards` | создать доску |
| GET | `/boards/{board_id}` | получить доску |
| PATCH | `/boards/{board_id}` | изменить название/описание |
| DELETE | `/boards/{board_id}` | архивировать |
| POST | `/boards/{board_id}/restore` | восстановить |
| GET | `/boards/{board_id}/snapshot` | доска, колонки и карточки |
| GET | `/boards/{board_id}/revision` | лёгкая проверка изменений |
| GET | `/boards/{board_id}/activity` | последние действия |

Создание:

```json
{
  "title": "Проект",
  "description": "Рабочая доска",
  "create_default_columns": true,
  "client_request_id": "uuid"
}
```

Изменение:

```json
{
  "title": "Новое название",
  "description": "Новое описание",
  "expected_version": 3,
  "client_request_id": "uuid"
}
```

Для очистки описания передаётся `clear_description: true`.

## Колонки

| Метод | Путь | Назначение |
| --- | --- | --- |
| POST | `/boards/{board_id}/columns` | создать колонку |
| PATCH | `/columns/{column_id}` | изменить колонку |
| DELETE | `/columns/{column_id}` | безопасно удалить |
| PUT | `/boards/{board_id}/columns/order` | сохранить порядок |

Создание:

```json
{
  "title": "В работе",
  "wip_limit": 5,
  "is_done": false,
  "target_index": 2,
  "client_request_id": "uuid"
}
```

Удаление непустой колонки с переносом:

```json
{
  "expected_version": 4,
  "card_action": "move",
  "target_column_id": "uuid",
  "client_request_id": "uuid"
}
```

Для архивации карточек используется `card_action: "archive"`. Для пустой колонки
`card_action` и `target_column_id` равны `null`.

Порядок:

```json
{
  "column_ids": ["uuid-1", "uuid-2", "uuid-3"],
  "expected_board_version": 10,
  "client_request_id": "uuid"
}
```

## Карточки

| Метод | Путь | Назначение |
| --- | --- | --- |
| POST | `/boards/{board_id}/cards` | создать |
| GET | `/cards/{card_id}` | получить |
| PATCH | `/cards/{card_id}` | изменить |
| DELETE | `/cards/{card_id}` | архивировать |
| POST | `/cards/{card_id}/restore` | восстановить |
| POST | `/cards/{card_id}/move` | переместить |

Создание:

```json
{
  "column_id": "uuid",
  "title": "Подготовить макет",
  "description": "Проверить мобильный экран",
  "priority": "high",
  "due_date": "2026-08-01T12:00:00Z",
  "target_index": 0,
  "client_request_id": "uuid"
}
```

Допустимые приоритеты: `low`, `normal`, `high`, `critical`. Для очистки описания или срока
используются `clear_description: true` и `clear_due_date: true`.

Перемещение:

```json
{
  "target_column_id": "uuid",
  "target_index": 2,
  "expected_version": 7,
  "client_request_id": "uuid"
}
```

`target_index` — индекс в итоговом активном списке после удаления перемещаемой карточки из
исходной позиции.

## Состояние

`GET /health` проверяет соединение с SQLite:

```json
{
  "status": "ok",
  "appVersion": "1.1.0",
  "apiVersion": "v1",
  "database": "ok",
  "time": "2026-07-27T12:00:00Z"
}
```

`GET /ready` дополнительно проверяет обязательные таблицы и Alembic revision.
