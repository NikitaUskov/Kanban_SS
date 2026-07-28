# Kanban Board MVP 1.1.0

Многопользовательская канбан-доска для небольшой команды:

- постоянный адрес интерфейса на GitHub Pages;
- FastAPI и SQLite на Windows-компьютере-сервере;
- бесплатный Cloudflare Quick Tunnel;
- автоматическая публикация нового адреса API;
- одинаковый доступ активных пользователей ко всем доскам;
- Argon2id, access token на 12 часов и refresh token на 30 дней;
- WIP-лимиты, оптимистические версии, журнал действий;
- резервное копирование, восстановление и автозапуск;
- адаптивный frontend для компьютеров, планшетов и телефонов.

Версия: `1.1.0`. Базовый API: `/api/v1`.

## Главное изменение 1.1.0

Релиз объединяет исправления, найденные при реальном развёртывании:

- PowerShell-скрипты совместимы с Windows PowerShell 5.1 и сохранены в UTF-8 with BOM;
- запуск сервера умеет временно использовать IPv4 для регистрации Quick Tunnel без
  отключения IPv6;
- исправлены разбор URL туннеля, ожидание DNS, повторный Git push и устаревшие PID-файлы;
- Git remote автоматически переводится на HTTPS;
- исправлены CORS, browser `fetch`, Ruff и Alembic model/migration parity;
- фильтры доски стали сворачиваемой боковой панелью;
- карточки списка досок больше не показывают количество колонок и карточек;
- адаптивная типографика и компоновка улучшены для разных экранов.

## Развёртывание на сервере

Начните с инструкции:

- [Развёртывание на Windows-сервере](docs/server-deployment.md)
- [Инструкция владельца и администратора](docs/admin-guide.md)

Основная команда после клонирования репозитория:

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

Первый запуск выполняется из PowerShell от имени администратора:

```powershell
.\scripts\start-kanban-server.ps1
```

## Основные команды

```powershell
# Состояние
.\scripts\status-kanban.ps1

# Запуск / остановка
.\scripts\start-kanban-server.ps1
.\scripts\stop-kanban.ps1

# Backup / restore
.\scripts\backup-kanban.ps1
.\scripts\restore-kanban.ps1 -BackupPath "D:\Kanban\backups\kanban_....db"

# Обновление сервера из main
.\scripts\update-from-main.ps1 -RunTests -NoBrowser
```

Пользователи:

```powershell
cd .\backend
.\.venv\Scripts\python.exe -m scripts.manage_users list
.\.venv\Scripts\python.exe -m scripts.manage_users create user01 --display-name "Иван Петров"
.\.venv\Scripts\python.exe -m scripts.manage_users disable user01
.\.venv\Scripts\python.exe -m scripts.manage_users enable user01
.\.venv\Scripts\python.exe -m scripts.manage_users reset-password user01
```

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
backend/                     FastAPI, SQLAlchemy, Alembic, CLI и tests
frontend/                    статический адаптивный SPA
scripts/setup-server.ps1     первичная настройка серверного компьютера
scripts/start-kanban-server.ps1 безопасный серверный запуск через IPv4 registration
scripts/start-kanban.ps1     backend, Quick Tunnel, runtime commit и Pages
scripts/status-kanban.ps1    состояние процессов и конфигурации
scripts/update-from-main.ps1 обновление сервера из origin/main
scripts/backup-kanban.ps1    проверенный SQLite backup
scripts/restore-kanban.ps1   восстановление с подтверждением
docs/                        инструкции и архитектура
```

## Ограничения

Quick Tunnel получает случайный URL после каждого запуска и не имеет SLA. Компьютер-сервер,
backend, cloudflared и интернет должны работать. Проект не предназначен для хранения
платёжных данных, паролей сторонних систем и критичных конфиденциальных документов.

SQLite используется с одним Uvicorn worker. Для роста нагрузки критерии перехода на
PostgreSQL описаны в [архитектуре](docs/architecture.md).

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
