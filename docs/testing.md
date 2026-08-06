# Тестирование Kanban Board 1.3.0

## Backend

```powershell
cd D:\Kanban\repository\backend
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m ruff check app scripts tests
.\.venv\Scripts\python.exe -m ruff format --check app scripts tests
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic check
.\.venv\Scripts\python.exe -m pytest
```

## Frontend

```powershell
cd D:\Kanban\repository
npm --prefix frontend test
npm --prefix frontend run check
```

## Readiness

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/ready | Format-List
```

Ожидается `appVersion=1.3.0`, `alembicRevision=20260806_0003` и наличие новых таблиц.

## Ручной smoke test

1. Войти старым логином.
2. Создать приглашение без SMTP и скопировать ссылку.
3. Открыть ссылку в приватном окне и зарегистрироваться.
4. Назначить новому пользователю viewer, убедиться, что редактирование скрыто/запрещено.
5. Повысить до editor, создать карточку и подзадачу.
6. Упомянуть пользователя через `@username`.
7. Проверить уведомление и переход к карточке.
8. Создать ручную ссылку сброса пароля и сменить пароль.
9. Выполнить backup и readiness.
