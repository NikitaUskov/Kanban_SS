# Типовые ошибки Kanban Board 1.3.0

## `Disallowed CORS origin`

Проверьте в `backend/.env`:

```env
ALLOWED_ORIGINS=https://<owner-lowercase>.github.io,http://127.0.0.1:5500,http://localhost:5500
```

Origin не содержит путь репозитория и hostname должен быть в нижнем регистре. Перезапустите backend.

## Устаревший PID

Запустите новые `stop-kanban.ps1`/`start-kanban-server.ps1`. Они проверяют, принадлежит ли PID Kanban, и не завершают чужой процесс. При необходимости удалите только `D:\Kanban\run\*.pid` после проверки реальных процессов.

## Письмо не отправилось

Приглашение всё равно создано. Скопируйте ссылку вручную. Проверьте:

- `EMAIL_ENABLED=true`;
- host/port;
- логин/пароль приложения;
- TLS;
- `EMAIL_FROM_ADDRESS`;
- `FRONTEND_URL`;
- `backend-stderr.log` и `kanban-backend.log`.

После исправления используйте «Отправить повторно» — будет создан новый токен/ссылка.

## Ссылка приглашения истекла

Администратор повторно отправляет приглашение. Старый токен не восстанавливается.

## Пользователь не видит доску

Проверьте раздел участников доски. Системная роль `member` сама по себе не предоставляет доступ. Добавьте membership с ролью viewer/editor/admin.

## Viewer видит кнопки после смены роли

Обновите страницу `Ctrl+F5`. Backend всё равно проверяет права и не разрешит операцию.

## `alembic check` предлагает операции

Не запускайте backend до выяснения. Выполните updater 1.3.0 повторно только при чистом Git или сравните `backend/app/models.py` и migration. Ожидаемая revision — `20260806_0003`.

## PowerShell требует подпись

```powershell
Get-ChildItem D:\Kanban\repository\scripts -Recurse -Filter "*.ps1" | Unblock-File
Set-ExecutionPolicy -Scope Process Bypass -Force
```

## Git не позволяет запуск из-за грязного дерева

Сначала изучите:

```powershell
git status --short
git diff
git diff --cached
```

Сохраните нужные изменения коммитом либо восстановите осознанно. Не удаляйте `.env` и рабочую базу.
