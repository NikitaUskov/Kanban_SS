# API Kanban Board 1.3.0

Базовый путь: `/api/v1`. Интерактивная документация при запущенном backend: `/docs`.

## Служебные

- `GET /health` — процесс и база;
- `GET /ready` — версия, Alembic revision и обязательные таблицы.

## Авторизация

- `POST /auth/login` — email или username + password;
- `POST /auth/refresh`;
- `POST /auth/logout`;
- `GET /auth/me`;
- `POST /auth/change-password`.

## Публичная регистрация и reset

- `GET /auth/invitations/{token}`;
- `POST /auth/invitations/accept`;
- `POST /auth/password-reset/request`;
- `POST /auth/password-reset/confirm`.

Открытой регистрации без приглашения нет.

## Профиль и участники

- `GET /profile`, `PATCH /profile`;
- `GET /users` — каталог активных пользователей;
- `GET /admin/users`;
- `PATCH /admin/users/{user_id}`;
- `GET /admin/invitations`;
- `POST /admin/invitations`;
- `POST /admin/invitations/{id}/resend`;
- `DELETE /admin/invitations/{id}`;
- `POST /admin/users/{id}/password-reset-link`.

## Доски и доступ

- `GET/POST /boards`;
- `GET/PATCH/DELETE /boards/{id}`;
- `POST /boards/{id}/restore`;
- `GET /boards/{id}/snapshot`;
- `GET /boards/{id}/revision`;
- `GET /boards/{id}/activity`;
- `GET /boards/{id}/members`;
- `PUT /boards/{id}/members/{user_id}`;
- `DELETE /boards/{id}/members/{user_id}`.

## Карточки, подзадачи и совместная работа

- `POST /boards/{board_id}/cards`;
- `GET/PATCH/DELETE /cards/{card_id}`;
- `POST /cards/{card_id}/restore`;
- `POST /cards/{card_id}/move`;
- `POST /cards/{card_id}/comments`;
- `PATCH/DELETE /comments/{comment_id}`;
- `POST /cards/{card_id}/checklist-items`;
- `PATCH/DELETE /checklist-items/{item_id}`;
- `POST /checklist-items/{item_id}/move`.

Подзадача создаётся тем же endpoint карточки с `parent_card_id` в payload.

## Уведомления

- `GET /notifications`;
- `GET /notifications/unread-count`;
- `POST /notifications/{id}/read`;
- `POST /notifications/read-all`.

Ошибки имеют стабильный код и читаемое сообщение; конфликт optimistic lock возвращает `409`.
