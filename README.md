# Kanban Board 1.3.0

Внутренняя Kanban-доска для небольшой команды. Frontend публикуется через GitHub Pages, backend работает на Windows-компьютере с SQLite и открывается через Cloudflare Quick Tunnel.

Версия приложения: `1.3.0`. Версия API: `v1`. Ожидаемая Alembic revision: `20260806_0003`.

## Возможности

- доски, колонки и карточки с drag-and-drop;
- ответственные, сроки, приоритеты, комментарии и чек-листы;
- сворачивание колонок и адаптивный интерфейс;
- одноуровневые подзадачи с собственным ответственным, сроком и обсуждением;
- закрытая регистрация по приглашению на email;
- ручная ссылка приглашения, когда SMTP отключён;
- восстановление пароля по email или через ссылку администратора;
- системные роли `owner`, `admin`, `member`;
- роли на доске `admin`, `editor`, `viewer`;
- управление участниками и доступами из интерфейса;
- упоминания `@username` и внутренние уведомления;
- профиль пользователя и настройки уведомлений;
- журнал действий, резервное копирование и миграции Alembic.

## Архитектура

```text
GitHub Pages frontend
        ↓ runtime-config.json
Cloudflare Quick Tunnel
        ↓
FastAPI backend на Windows
        ↓
SQLite C:\Kanban\data\kanban.db
```

Ссылка приглашения ведёт на постоянный GitHub Pages URL. Frontend при открытии считывает текущий адрес туннеля из `runtime-config.json`, поэтому ранее отправленная ссылка не ломается после перезапуска туннеля.

## Быстрое обновление 1.2.0 → 1.3.0

1. Скачайте и распакуйте `Kanban_Board_Update_1.3.0.zip`.
2. Убедитесь, что `git status --short` ничего не выводит.
3. Откройте PowerShell от имени администратора.
4. Запустите:

```powershell
Get-ChildItem D:\Kanban\Kanban_Board_Update_1.3.0 -Recurse -Filter "*.ps1" | Unblock-File
Set-ExecutionPolicy -Scope Process Bypass -Force

& "D:\Kanban\Kanban_Board_Update_1.3.0\apply-update-1.3.0.ps1" `
  -RepositoryRoot "D:\Kanban\repository"
```

Updater создаёт backup, сохраняет `.env`, `.venv`, базу и текущий `runtime-config.json`, применяет migration `20260806_0003`, запускает Ruff, Alembic, pytest и frontend-тесты.

Подробности: `docs/update.md`.

## Новая установка

Рекомендуемый путь репозитория:

```text
C:\Kanban\repository
```

Из PowerShell администратора:

```powershell
Set-ExecutionPolicy -Scope Process Bypass -Force

.\scripts\setup-server.ps1 `
  -InstallRoot "C:\Kanban" `
  -GitHubOwner "YOUR_GITHUB_OWNER" `
  -RepositoryName "YOUR_REPOSITORY" `
  -FirstUsername "owner" `
  -FirstDisplayName "Владелец" `
  -FirstEmail "owner@example.com"
```

Первый созданный пользователь автоматически становится владельцем. После установки:

```powershell
.\scripts\start-kanban-server.ps1
```

Подробности: `docs/server-deployment.md`.

## Email и приглашения

По умолчанию email выключен:

```env
EMAIL_ENABLED=false
```

Администратор всё равно может создать приглашение и скопировать готовую ссылку из интерфейса. Для SMTP заполните параметры в `backend/.env` и перезапустите backend:

```env
EMAIL_ENABLED=true
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=kanban@example.com
SMTP_PASSWORD=<secret>
SMTP_USE_TLS=true
EMAIL_FROM_ADDRESS=kanban@example.com
EMAIL_FROM_NAME=Kanban Board
FRONTEND_URL=https://<owner>.github.io/<repository>/
```

SMTP-пароль и JWT secret нельзя добавлять в Git.

## Проверка версии

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/ready | Format-List
```

Ожидается:

```text
status          : ok
appVersion      : 1.3.0
alembicRevision : 20260806_0003
```

## Основная документация

- `docs/server-deployment.md` — установка на Windows-сервере;
- `docs/update.md` — обновление и откат;
- `docs/admin-guide.md` — пользователи, приглашения, роли, Git и backup;
- `docs/architecture.md` — архитектура и модель доступа;
- `docs/api.md` — API;
- `docs/testing.md` — проверки;
- `docs/troubleshooting.md` — типовые ошибки;
- `docs/backup-and-restore.md` — backup и восстановление.
