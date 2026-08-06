# Инструкция владельца и администратора Kanban Board 1.3.0

## Роли

### Системные роли

- `owner` — полный доступ; назначение владельцев; защита последнего владельца;
- `admin` — управление участниками, приглашениями и досками, кроме защищённых действий владельца;
- `member` — доступ только к назначенным доскам.

### Роли на доске

- `admin` — настройки доски, колонки, участники, архив;
- `editor` — карточки, подзадачи, ответственные, комментарии и чек-листы;
- `viewer` — только просмотр.

## Приглашение участника

1. Войдите владельцем или администратором.
2. Откройте «Участники».
3. Нажмите «Пригласить».
4. Укажите email, имя, системную роль и доступ к доскам.
5. Создайте приглашение.

Если SMTP включён, письмо отправляется автоматически. Если выключен, скопируйте ссылку. Ссылка имеет вид:

```text
https://<owner>.github.io/<repository>/?invite=<token>
```

Токен показывается только в созданной/повторно созданной ссылке; в базе хранится его хеш.

## Управление приглашениями

В разделе «Участники» доступны:

- повторная отправка;
- копирование новой ссылки;
- отзыв приглашения;
- статусы `created`, `sent`, `failed`, `disabled`;
- информация о сроке, принятии и ошибке SMTP.

По умолчанию приглашение действует 72 часа.

## Существующие пользователи

После обновления старые аккаунты сохраняются. Им можно добавить email в карточке пользователя. Вход поддерживает и email, и прежний username.

## Управление пользователем

Администратор может:

- изменить отображаемое имя;
- назначить или очистить email;
- изменить роль;
- включить/отключить аккаунт;
- создать ссылку восстановления пароля;
- отозвать сессии через смену/сброс пароля;
- изменить доступы к доскам.

Нельзя отключить или понизить последнего активного владельца.

## Восстановление пароля

Пользователь нажимает «Забыли пароль?» и вводит email. Ответ системы всегда одинаковый, чтобы не раскрывать наличие аккаунта.

Администратор может создать ручную ссылку в разделе участников. По умолчанию ссылка действует 30 минут. После смены пароля refresh-сессии пользователя отзываются.

## Доступ к доске

Откройте доску → настройки доступа. Добавьте активного пользователя и выберите `admin`, `editor` или `viewer`. Удаление членства сразу убирает доску из списка пользователя.

Создатель новой доски автоматически получает роль администратора доски.

## Подзадачи

Откройте карточку и раздел «Подзадачи». Подзадача является полноценной карточкой, но глубина ограничена одним уровнем. У неё могут быть:

- ответственный;
- срок;
- приоритет;
- комментарии;
- чек-лист;
- завершение.

Подзадача не может содержать собственные подзадачи. Родитель показывает прогресс выполненных подзадач.

## Упоминания и уведомления

В комментарии используйте `@username`. Упомянутый участник доски получает уведомление. Уведомление также создаётся при назначении ответственным.

В профиле пользователь может отключить отдельные категории уведомлений. Центр уведомлений позволяет отметить одно или все сообщения прочитанными.

## CLI — аварийное управление

```powershell
cd D:\Kanban\repository\backend
```

Создать пользователя:

```powershell
.\.venv\Scripts\python.exe -m scripts.manage_users create user01 `
  --display-name "Иван Иванов" `
  --email "user01@example.com" `
  --role member
```

Первый пользователь пустой базы автоматически станет `owner`.

Список:

```powershell
.\.venv\Scripts\python.exe -m scripts.manage_users list
```

Отключение/включение:

```powershell
.\.venv\Scripts\python.exe -m scripts.manage_users disable user01
.\.venv\Scripts\python.exe -m scripts.manage_users enable user01
```

Сброс пароля:

```powershell
.\.venv\Scripts\python.exe -m scripts.manage_users reset-password user01
```

Импорт CSV:

```powershell
.\.venv\Scripts\python.exe -m scripts.manage_users import-csv scripts\users.example.csv
```

CSV: `username,display_name,password,email,role`.

## Обновление кода владельцем

Перед push:

```powershell
cd D:\Kanban\repository\backend
.\.venv\Scripts\python.exe -m ruff check app scripts tests
.\.venv\Scripts\python.exe -m ruff format --check app scripts tests
.\.venv\Scripts\python.exe -m alembic check
.\.venv\Scripts\python.exe -m pytest

cd ..
npm --prefix frontend test
npm --prefix frontend run check
git diff --check
```

Публикация:

```powershell
git add .
git commit -m "feat: describe change"
git push origin main
```

Не используйте `git add .`, если в `git status` появились неизвестные секреты или базы. `.env`, `.db`, `.venv`, backup и logs должны оставаться неотслеживаемыми.

## Backup

Создать:

```powershell
.\scripts\backup-kanban.ps1
```

Остановить и восстановить:

```powershell
.\scripts\stop-kanban.ps1
.\scripts\restore-kanban.ps1 -BackupPath "D:\Kanban\backups\kanban_<date>.db"
.\scripts\start-kanban-server.ps1
```

После восстановления проверьте `/api/v1/ready`.

## Логи

```text
D:\Kanban\logs\backend-stdout.log
D:\Kanban\logs\backend-stderr.log
D:\Kanban\logs\cloudflared-stdout.log
D:\Kanban\logs\cloudflared-stderr.log
D:\Kanban\logs\kanban-backend.log
```

```powershell
Get-Content D:\Kanban\logs\backend-stderr.log -Tail 100 -Wait
```
