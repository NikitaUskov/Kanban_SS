# Kanban Board MVP

Полный исходный код многопользовательской канбан-доски по ТЗ версии 2.0:

- постоянный адрес интерфейса на GitHub Pages;
- FastAPI на постоянно работающем компьютере Windows;
- SQLite в режиме WAL и один Uvicorn worker;
- бесплатный Cloudflare Quick Tunnel;
- автоматическая публикация нового адреса API без ручного копирования;
- одинаковый доступ всех активных пользователей ко всем доскам;
- JWT access token на 12 часов и refresh token на 30 дней;
- Argon2id для паролей;
- polling revision каждые 5/20 секунд;
- оптимистические версии, WIP-лимиты и идемпотентные мутации;
- журнал действий, backup/restore и автозапуск.

Версия приложения: `1.0.0`. Базовый API: `/api/v1`.

## С чего начать

Полная инструкция для пользователя без опыта развёртывания находится в
[docs/deployment.md](docs/deployment.md). Не пропускайте настройку GitHub Pages и Git
Credential Manager: без них автоматическое обновление Quick Tunnel URL не сможет попасть на
постоянную страницу.

После подготовки репозитория основной путь установки выглядит так:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
cd C:\Kanban\repository
.\scripts\install-kanban.ps1 `
  -InstallRoot "C:\Kanban" `
  -GitHubOwner "<owner>" `
  -RepositoryName "<repository>"
```

Затем создайте хотя бы одного пользователя:

```powershell
cd C:\Kanban\repository\backend
.\.venv\Scripts\python.exe -m scripts.manage_users create user01 --display-name "Пользователь 01"
```

И выполните первый запуск:

```powershell
cd C:\Kanban\repository
.\scripts\start-kanban.ps1
```

Скрипт сам применит миграции, запустит backend и `cloudflared`, получит случайный
`trycloudflare.com` URL, проверит его, обновит `runtime-config.json`, создаст runtime commit,
выполнит `git push` и дождётся GitHub Pages.

## Структура

```text
backend/
  app/                    FastAPI, доменные сервисы, ORM и авторизация
  alembic/                миграции
  scripts/                CLI пользователей, backup/restore, нагрузочный сценарий
  tests/                  модульные и интеграционные тесты
frontend/
  index.html              статическое SPA
  assets/                 CSS и JavaScript ES modules
  runtime-config.json     текущий публичный URL API
scripts/
  install-kanban.ps1      установка
  start-kanban.ps1        единый запуск и публикация нового tunnel URL
  stop-kanban.ps1         остановка только процессов проекта
  backup-kanban.ps1       согласованный SQLite backup
  restore-kanban.ps1      проверяемое восстановление
  register-autostart.ps1  Task Scheduler: запуск и ежедневный backup
  update-kanban.ps1       обновление по release tag
.github/workflows/
  tests.yml               backend/frontend проверки
  deploy-pages.yml        публикация GitHub Pages
docs/                     архитектура и эксплуатационная документация
```

## Основные команды

Все команды выполняются в PowerShell от обычного пользователя, если в инструкции не указано
обратное.

```powershell
# Запуск
.\scripts\start-kanban.ps1

# Остановка
.\scripts\stop-kanban.ps1

# Backup
.\scripts\backup-kanban.ps1

# Restore с обязательным подтверждением
.\scripts\restore-kanban.ps1 -BackupPath "C:\Kanban\backups\kanban_YYYY-MM-DD_HH-mm-ss.db"

# Автозапуск и ежедневный backup
.\scripts\register-autostart.ps1

# Пользователи
cd .\backend
.\.venv\Scripts\python.exe -m scripts.manage_users list
.\.venv\Scripts\python.exe -m scripts.manage_users disable user01
.\.venv\Scripts\python.exe -m scripts.manage_users enable user01
.\.venv\Scripts\python.exe -m scripts.manage_users reset-password user01
```

## Документация

- [Архитектура](docs/architecture.md)
- [API](docs/api.md)
- [Полное развёртывание](docs/deployment.md)
- [Автоматизация Quick Tunnel](docs/tunnel-automation.md)
- [Backup и восстановление](docs/backup-and-restore.md)
- [Обновление](docs/update.md)
- [Типовые ошибки](docs/troubleshooting.md)
- [Проверка после первого запуска](docs/testing.md)

## Ограничения

- Quick Tunnel предназначен для MVP, разработки и пилотов, не имеет SLA и при новом запуске
  получает новый случайный адрес.
- Работа с данными возможна только при включённом компьютере владельца, работающем backend,
  `cloudflared` и доступном интернете.
- Frontend остаётся доступным независимо от backend, но покажет состояние переподключения.
- Сервис не предназначен для паролей сторонних систем, платёжных данных, конфиденциальных
  документов и других критичных сведений.
- С SQLite разрешён только один Uvicorn worker. Для роста нагрузки критерии перехода на
  PostgreSQL приведены в архитектурной документации.

## Секреты и данные

Файлы `backend/.env`, `*.db`, `*.db-wal`, `*.db-shm`, `logs/`, `backups/` и `run/` исключены из
Git. В `runtime-config.json` находятся только публичный HTTPS URL API и номера версий. Данные
досок не включаются в статический frontend.

Лицензия: MIT, см. [LICENSE](LICENSE).
