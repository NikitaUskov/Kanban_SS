# Развёртывание Kanban Board 1.2.0 на Windows-компьютере-сервере

Инструкция рассчитана на Windows 10/11, PowerShell 5.1 или PowerShell 7 и постоянный путь
`D:\Kanban`. Другой диск допустим: замените путь во всех командах и передайте его в
`-InstallRoot`.

## 1. Как устроено размещение

```text
GitHub Pages
  https://<owner>.github.io/<repository>/
             │
             │ runtime-config.json
             ▼
Cloudflare Quick Tunnel — случайный URL после каждого запуска
             │
             ▼
FastAPI http://127.0.0.1:8000
             │
             ▼
SQLite D:\Kanban\data\kanban.db
```

Frontend всегда открывается по одному адресу GitHub Pages. После запуска сервер получает новый
Quick Tunnel URL, записывает его в `frontend/runtime-config.json`, создаёт runtime commit и
отправляет его в GitHub через HTTPS.

## 2. Требования

- компьютер должен быть включён, когда команда работает с доской;
- Windows-пользователь сервера должен иметь права администратора для временной записи в
  `hosts` во время регистрации Quick Tunnel;
- GitHub-репозиторий должен существовать и содержать проект;
- GitHub Pages должен публиковать каталог `frontend` через workflow;
- исходящие HTTPS-соединения к GitHub и Cloudflare должны быть разрешены.

Минимальные программы:

```powershell
winget install --exact --id Python.Python.3.11 --accept-package-agreements --accept-source-agreements
winget install --exact --id Git.Git --accept-package-agreements --accept-source-agreements
winget install --exact --id Cloudflare.cloudflared --accept-package-agreements --accept-source-agreements
```

Для локальных frontend-тестов дополнительно нужен Node.js LTS:

```powershell
winget install --exact --id OpenJS.NodeJS.LTS --accept-package-agreements --accept-source-agreements
```

После установки закройте PowerShell и откройте заново.

## 3. Подготовка каталога и клонирование

```powershell
New-Item D:\Kanban -ItemType Directory -Force | Out-Null
cd D:\Kanban

git clone https://github.com/<owner>/<repository>.git repository
cd .\repository
```

Проверьте:

```powershell
git remote -v
git branch --show-current
git status --short
```

Ожидаются HTTPS remote, ветка `main` и пустой вывод `git status --short`.

## 4. Разблокировка PowerShell-файлов

ZIP и файлы, скачанные из браузера, могут иметь метку Internet Zone. Снимите её:

```powershell
Get-ChildItem D:\Kanban\repository\scripts -Recurse -Filter "*.ps1" | Unblock-File
Set-ExecutionPolicy -Scope Process Bypass -Force
```

Скрипты проекта сохранены в UTF-8 with BOM и CRLF для Windows PowerShell 5.1.

## 5. Первичная настройка

Откройте PowerShell **от имени администратора**:

```powershell
Set-ExecutionPolicy -Scope Process Bypass -Force
cd D:\Kanban\repository

.\scripts\setup-server.ps1 `
  -InstallRoot "D:\Kanban" `
  -GitHubOwner "<owner>" `
  -RepositoryName "<repository>" `
  -FirstUsername "admin" `
  -FirstDisplayName "Владелец доски" `
  -RegisterAutostart
```

Скрипт:

1. создаёт `data`, `logs`, `backups` и `run`;
2. создаёт `backend\.venv`;
3. устанавливает зависимости;
4. создаёт или аккуратно обновляет `backend\.env`;
5. генерирует локальный `JWT_SECRET`, не выводя его в консоль;
6. добавляет CORS origin GitHub Pages в нижнем регистре;
7. переводит Git remote на HTTPS;
8. применяет Alembic-миграции до `20260730_0002`;
9. создаёт первого пользователя;
10. при `-RegisterAutostart` создаёт задачи запуска и backup.

Пароль первого пользователя вводится скрыто в консоли.

## 6. Ручная проверка установки

```powershell
Test-Path D:\Kanban\repository\backend\.venv\Scripts\python.exe
Test-Path D:\Kanban\repository\backend\.env
Test-Path D:\Kanban\data\kanban.db
```

Все команды должны вернуть `True`.

Проверьте схему:

```powershell
cd D:\Kanban\repository\backend
.\.venv\Scripts\python.exe -m alembic current
.\.venv\Scripts\python.exe -m alembic check
.\.venv\Scripts\python.exe -c "from app.health.service import ready; print(ready().model_dump_json())"
```

Ожидаемая revision: `20260730_0002`.

## 7. Первый запуск

Вернитесь в корень и убедитесь, что Git-дерево чистое:

```powershell
cd D:\Kanban\repository
git status --short
```

Откройте PowerShell от имени администратора:

```powershell
.\scripts\start-kanban-server.ps1
```

Не запускайте `start-kanban.ps1` напрямую на сети, где регистрация Cloudflare по IPv6
сбрасывается. `start-kanban-server.ps1`:

- получает A-запись `api.trycloudflare.com`;
- временно добавляет её в `hosts`;
- регистрирует Quick Tunnel по IPv4;
- запускает соединение tunnel edge по IPv4/HTTP2;
- восстанавливает исходный `hosts` побайтово;
- не отключает IPv6 сетевого адаптера.

Успешный вывод содержит:

```text
Backend запущен: PID ..., версия 1.2.0.
Quick Tunnel отвечает: https://....trycloudflare.com, API v1.
runtime-config.json обновлён: configVersion=...
GitHub Pages получил configVersion=...
```

## 8. Проверка API и CORS

Локально:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health | Format-List
Invoke-RestMethod http://127.0.0.1:8000/api/v1/ready | Format-List
```

Опубликованная конфигурация:

```powershell
$pagesConfig = "https://<owner>.github.io/<repository>/runtime-config.json?ts=$([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds())"
$config = Invoke-RestMethod $pagesConfig
$config | Format-List
Invoke-RestMethod "$($config.apiBaseUrl)/health" | Format-List
```

CORS preflight:

```powershell
curl.exe -i -X OPTIONS "$($config.apiBaseUrl)/health" `
  -H "Origin: https://<owner-lowercase>.github.io" `
  -H "Access-Control-Request-Method: GET" `
  -H "Access-Control-Request-Headers: x-request-id"
```

Ответ должен содержать `access-control-allow-origin` с origin GitHub Pages.

## 9. GitHub Pages

Workflow `.github/workflows/deploy-pages.yml` публикует `frontend`. В настройках репозитория:

1. откройте `Settings → Pages`;
2. в `Build and deployment` выберите `GitHub Actions`;
3. дождитесь зелёного workflow `Deploy GitHub Pages`.

Frontend не содержит секретов. `runtime-config.json` содержит только публичный адрес API и
версии.

## 10. Автозапуск

Если параметр `-RegisterAutostart` не использовался:

```powershell
cd D:\Kanban\repository
.\scripts\register-autostart.ps1
```

Создаются две задачи Task Scheduler:

- запуск Kanban при входе владельца;
- ежедневный backup.

Проверьте после перезагрузки:

```powershell
.\scripts\status-kanban.ps1
```

## 11. Перенос существующей базы на новый сервер

На старом сервере:

```powershell
.\scripts\backup-kanban.ps1
.\scripts\stop-kanban.ps1
```

На новом сервере сначала выполните чистую установку, затем остановите сервис и восстановите
backup:

```powershell
.\scripts\restore-kanban.ps1 -BackupPath "D:\путь\к\backup.db"
```

После восстановления примените миграции текущего релиза:

```powershell
cd .\backend
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic check
```

## 12. Что нельзя переносить в Git

Никогда не добавляйте:

- `backend/.env`;
- `backend/.venv`;
- `*.db`, `*.db-wal`, `*.db-shm`;
- `logs`, `backups`, `run`;
- CSV с открытыми паролями;
- содержимое `JWT_SECRET` и токены.
