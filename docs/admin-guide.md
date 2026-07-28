# Инструкция владельца и администратора Kanban Board 1.1.0

Все команды ниже выполняются на сервере из `D:\Kanban\repository`, если не указано иное.

## Ежедневное управление

```powershell
# Состояние процессов, локального API и опубликованной конфигурации
.\scripts\status-kanban.ps1

# Запуск — PowerShell от имени администратора
.\scripts\start-kanban-server.ps1

# Остановка
.\scripts\stop-kanban.ps1

# Резервная копия
.\scripts\backup-kanban.ps1
```

## Пользователи

Перейдите в backend:

```powershell
cd D:\Kanban\repository\backend
```

Список:

```powershell
.\.venv\Scripts\python.exe -m scripts.manage_users list
```

Создание:

```powershell
.\.venv\Scripts\python.exe -m scripts.manage_users create user01 `
  --display-name "Иван Петров"
```

Отключение пользователя:

```powershell
.\.venv\Scripts\python.exe -m scripts.manage_users disable user01
```

Включение:

```powershell
.\.venv\Scripts\python.exe -m scripts.manage_users enable user01
```

Сброс пароля:

```powershell
.\.venv\Scripts\python.exe -m scripts.manage_users reset-password user01
```

Физического удаления пользователя нет намеренно: журнал действий и ссылки на автора должны
оставаться целостными. «Убрать пользователя» означает `disable`; он сразу теряет доступ.

Пакетный импорт:

```powershell
.\.venv\Scripts\python.exe -m scripts.manage_users import-csv D:\Kanban\users.csv
```

CSV содержит `username,display_name,password`. Не храните файл с открытыми паролями в
репозитории; удалите его после импорта и безопасной передачи паролей.

## Как заливать изменения в GitHub

Работать с кодом удобнее на основном компьютере разработчика, а не прямо на сервере.

### 1. Перед началом работы

```powershell
cd D:\Kanban\repository
git switch main
git pull --ff-only origin main
git status --short
```

`git status --short` не должен ничего вывести. Runtime-коммиты создаются сервером, поэтому
`git pull` перед каждой новой правкой обязателен.

### 2. Проверка backend

```powershell
cd D:\Kanban\repository\backend
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m ruff check app scripts tests
.\.venv\Scripts\python.exe -m ruff format --check app scripts tests
.\.venv\Scripts\python.exe -m alembic check
.\.venv\Scripts\python.exe -m pytest
```

### 3. Проверка frontend

```powershell
cd D:\Kanban\repository
npm --prefix frontend test
Get-ChildItem frontend\assets\js\*.js | ForEach-Object {
  node --check $_.FullName
}
```

### 4. Просмотр и commit

```powershell
git status --short
git diff --check
git diff --stat
git diff
```

Добавляйте конкретные файлы, а не всё подряд:

```powershell
git add frontend\assets\css\styles.css frontend\assets\js\app.js
git commit -m "feat: improve responsive board layout"
git push origin main
```

Не добавляйте `.env`, `.venv`, базы, логи, backup, `.idea` и CSV с паролями.

### 5. GitHub Actions

После push дождитесь зелёных workflow:

- `Tests`;
- `Deploy GitHub Pages`, если менялся `frontend/**`.

Если `Tests` красный, сервер не обновляйте. Откройте упавший шаг и исправьте первую реальную
ошибку, а не последующие сообщения.

## Как обновить сервер после push

Откройте PowerShell от имени администратора:

```powershell
cd D:\Kanban\repository
.\scripts\update-from-main.ps1 -RunTests -NoBrowser
```

Скрипт:

1. проверяет чистое Git-дерево;
2. создаёт backup;
3. останавливает сервис;
4. выполняет `git pull --ff-only origin main`;
5. обновляет зависимости и миграции;
6. при `-RunTests` запускает Ruff и pytest;
7. запускает новый Quick Tunnel и публикует runtime-config.

Для изменения только frontend перезапуск backend не обязателен: достаточно успешного push и
workflow Pages. Но сервер всё равно должен позже получить изменения через `git pull`, чтобы
его рабочая копия не отставала.

## Резервные копии и восстановление

Создать backup:

```powershell
.\scripts\backup-kanban.ps1
```

Посмотреть последние копии:

```powershell
Get-ChildItem D:\Kanban\backups -Filter "kanban_*.db" |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 10 Name,Length,LastWriteTime
```

Восстановить:

```powershell
.\scripts\stop-kanban.ps1
.\scripts\restore-kanban.ps1 `
  -BackupPath "D:\Kanban\backups\kanban_YYYY-MM-DD_HH-mm-ss.db"
```

Restore требует подтверждения и перед заменой создаёт аварийную копию текущей базы.

## Логи

```powershell
Get-Content D:\Kanban\logs\backend-stderr.log -Tail 100
Get-Content D:\Kanban\logs\cloudflared-stderr.log -Tail 100
Get-Content D:\Kanban\logs\kanban-backend.log -Tail 100
```

Локальная готовность:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/ready | Format-List
```

## После перезагрузки Windows

1. Войдите под владельцем сервера.
2. Подождите 2–5 минут.
3. Выполните `.\scripts\status-kanban.ps1`.
4. Если автозапуск не сработал, проверьте Task Scheduler и запустите вручную:

```powershell
Start-ScheduledTask -TaskName "KanbanBoard-Autostart"
```

## Аварийный порядок действий

1. Не удаляйте базу и `.env`.
2. Сохраните вывод ошибки и последние 100 строк логов.
3. Выполните `git status --short`.
4. Проверьте локальный `/health`.
5. Если локальный API работает, но сайт нет — проверяйте runtime-config, GitHub Pages и CORS.
6. Если backend не запускается после обновления — остановите процессы и восстановите последний
   проверенный backup.
