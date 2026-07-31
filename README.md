# Kanban Board 1.2.0

Многопользовательская канбан-доска для небольшой команды. Интерфейс постоянно размещён на
GitHub Pages, а FastAPI и SQLite работают на Windows-компьютере-сервере через бесплатный
Cloudflare Quick Tunnel.

Версия приложения: `1.2.0`. Базовый путь API: `/api/v1`.

## Возможности

- общие доски и колонки для всех активных пользователей;
- WIP-лимиты, drag-and-drop и оптимистическая блокировка изменений;
- ответственный за карточку и отдельный признак завершения;
- сроки, приоритеты и визуальное выделение просроченных задач;
- комментарии с редактированием и удалением собственных сообщений;
- упорядочиваемые чек-листы с прогрессом;
- боковая панель карточки на компьютере и полноэкранная карточка на телефоне;
- сворачивание колонок с персональным сохранением состояния в браузере;
- компактные карточки с индикаторами срока, комментариев, чек-листа и ответственного;
- опциональные фильтры: поиск, приоритет, колонка, срок, ответственный, выполнение,
  «только мои», комментарии и чек-листы;
- архив досок и карточек, журнал действий, backup, восстановление и автозапуск;
- Argon2id, access token на 12 часов и refresh token на 30 дней.

## Что добавлено в 1.2.0

- публичный каталог активных пользователей для назначения ответственного;
- поля `assignee_user_id` и `completed_at` в карточках;
- комментарии к карточкам;
- чек-листы с изменением порядка и отметкой выполнения;
- новая Alembic-миграция `20260730_0002`;
- адаптивная боковая панель карточки;
- сворачиваемые колонки;
- дополнительные фильтры и компактные индикаторы на доске;
- 23 backend-тест и 16 frontend-тестов.

Подзадачи как отдельные связанные карточки, соисполнители, файлы и уведомления не входят в
этот релиз. Их рационально развивать отдельно, не усложняя миграцию 1.2.0.

## Развёртывание на новом компьютере-сервере

Используйте инструкции:

- [развёртывание на Windows-сервере](docs/server-deployment.md);
- [инструкция владельца и администратора](docs/admin-guide.md).

После клонирования репозитория основная команда выглядит так:

```powershell
Set-ExecutionPolicy -Scope Process Bypass -Force
cd D:\Kanban\repository

.\scripts\setup-server.ps1 `
  -InstallRoot "D:\Kanban" `
  -GitHubOwner "<owner>" `
  -RepositoryName "<repository>" `
  -FirstUsername "admin" `
  -FirstDisplayName "Владелец" `
  -RegisterAutostart
```

Первый и последующие ручные запуски выполняются из PowerShell от имени администратора:

```powershell
.\scripts\start-kanban-server.ps1
```

Скрипт временно направляет только запрос регистрации Quick Tunnel на IPv4, после чего
полностью восстанавливает исходный файл `hosts`. IPv6 сетевого адаптера не отключается.

## Обновление существующей версии 1.1.0

Перед обновлением создайте backup и убедитесь, что Git-дерево чистое. Затем примените пакет
`Kanban_Board_Update_1.2.0.zip` и выполните миграцию:

```powershell
cd D:\Kanban\repository\backend
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic check
.\.venv\Scripts\python.exe -m pytest
```

Данные пользователей, досок, колонок и карточек сохраняются. Новые поля получают значения
`NULL`, а новые таблицы создаются рядом с существующими.

## Основные административные команды

```powershell
cd D:\Kanban\repository

# Состояние
.\scripts\status-kanban.ps1

# Запуск и остановка
.\scripts\start-kanban-server.ps1
.\scripts\stop-kanban.ps1

# Backup и restore
.\scripts\backup-kanban.ps1
.\scripts\restore-kanban.ps1 -BackupPath "D:\Kanban\backups\kanban_....db"

# Получить изменения из origin/main
.\scripts\update-from-main.ps1 -RunTests -NoBrowser
```

Пользователи:

```powershell
cd D:\Kanban\repository\backend
.\.venv\Scripts\python.exe -m scripts.manage_users list
.\.venv\Scripts\python.exe -m scripts.manage_users create user01 --display-name "Иван Петров"
.\.venv\Scripts\python.exe -m scripts.manage_users disable user01
.\.venv\Scripts\python.exe -m scripts.manage_users enable user01
.\.venv\Scripts\python.exe -m scripts.manage_users reset-password user01
```

Отключённый пользователь теряет доступ, но его имя остаётся в истории, комментариях и
карточках. Физическое удаление пользователей намеренно не предусмотрено.

## Проверки перед push

```powershell
cd D:\Kanban\repository\backend
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m ruff check app scripts tests
.\.venv\Scripts\python.exe -m ruff format --check app scripts tests
.\.venv\Scripts\python.exe -m alembic check
.\.venv\Scripts\python.exe -m pytest

cd ..
npm --prefix frontend test
Get-ChildItem frontend\assets\js\*.js | ForEach-Object { node --check $_.FullName }
```

## Структура

```text
backend/                         FastAPI, SQLAlchemy, Alembic, CLI и тесты
backend/alembic/versions/        миграции, включая 20260730_0002
frontend/                        статический адаптивный SPA
frontend/assets/js/card-detail.js панель карточки, комментарии и чек-лист
scripts/setup-server.ps1         первоначальная настройка сервера
scripts/start-kanban-server.ps1  безопасный запуск Quick Tunnel через IPv4 registration
scripts/start-kanban.ps1         backend, tunnel, runtime-config и GitHub Pages
scripts/status-kanban.ps1        состояние процессов и публичной конфигурации
scripts/update-from-main.ps1     backup, pull, migration, tests и restart
scripts/backup-kanban.ps1        согласованный SQLite backup
scripts/restore-kanban.ps1       проверяемое восстановление
docs/                            эксплуатационная и техническая документация
```

## Ограничения

Quick Tunnel получает случайный URL после каждого запуска и не имеет SLA. Компьютер-сервер,
backend, `cloudflared` и интернет должны работать постоянно. Проект не предназначен для
платёжных данных, паролей сторонних сервисов и критичных конфиденциальных документов.

SQLite используется с одним Uvicorn worker. Критерии перехода на PostgreSQL перечислены в
[описании архитектуры](docs/architecture.md).

## Документация

- [Архитектура](docs/architecture.md)
- [API](docs/api.md)
- [Развёртывание](docs/server-deployment.md)
- [Администрирование](docs/admin-guide.md)
- [Quick Tunnel](docs/tunnel-automation.md)
- [Backup и восстановление](docs/backup-and-restore.md)
- [Обновление](docs/update.md)
- [Типовые ошибки](docs/troubleshooting.md)
- [Тестирование](docs/testing.md)

Лицензия: MIT.
