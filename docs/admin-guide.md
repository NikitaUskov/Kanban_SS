# Инструкция владельца и администратора Kanban Board 1.2.0

Команды ниже рассчитаны на серверную установку в `D:\Kanban\repository`.

## Ежедневные команды

```powershell
cd D:\Kanban\repository

# Проверить backend, tunnel, public config и Git
.\scripts\status-kanban.ps1

# Запустить — PowerShell от имени администратора
.\scripts\start-kanban-server.ps1

# Остановить
.\scripts\stop-kanban.ps1

# Создать согласованный SQLite backup
.\scripts\backup-kanban.ps1
```

## Пользователи

```powershell
cd D:\Kanban\repository\backend
```

Список:

```powershell
.\.venv\Scripts\python.exe -m scripts.manage_users list
```

Создать:

```powershell
.\.venv\Scripts\python.exe -m scripts.manage_users create user01 `
  --display-name "Иван Петров"
```

Отключить:

```powershell
.\.venv\Scripts\python.exe -m scripts.manage_users disable user01
```

Включить:

```powershell
.\.venv\Scripts\python.exe -m scripts.manage_users enable user01
```

Сбросить пароль:

```powershell
.\.venv\Scripts\python.exe -m scripts.manage_users reset-password user01
```

Пакетный импорт:

```powershell
.\.venv\Scripts\python.exe -m scripts.manage_users import-csv D:\Kanban\users.csv
```

CSV: `username,display_name,password`. Удалите файл после импорта. Не помещайте его в Git.

Физического удаления пользователя нет. Команда `disable` блокирует вход и refresh, но
сохраняет автора комментариев, историю и ссылки на ответственного. В карточке ранее назначенный
отключённый пользователь остаётся видимым до смены ответственного.

## Управление новой карточкой 1.2

Любой активный пользователь может:

- назначить активного пользователя ответственным;
- снять ответственного;
- завершить или вернуть задачу в активное состояние;
- добавить пункт чек-листа, изменить порядок и отметить выполнение;
- добавить комментарий;
- редактировать и удалять только собственный комментарий.

Отключённые пользователи не появляются в списке новых назначений. Все изменения фиксируются в
`activity_log` и увеличивают revision доски.

## Как заливать изменения в GitHub

### 1. Перед началом

```powershell
cd D:\Kanban\repository
git switch main
git pull --ff-only origin main
git status --short
```

Вывод `git status --short` должен быть пустым. Сервер создаёт runtime-коммиты при смене Quick
Tunnel URL, поэтому `git pull` перед разработкой обязателен.

### 2. Создайте ветку для крупной функции

```powershell
git switch -c feature/<короткое-название>
```

Небольшое исправление допустимо делать в `main`, но ветка безопаснее для изменений модели и
миграций.

### 3. Backend-проверки

```powershell
cd D:\Kanban\repository\backend
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m ruff check app scripts tests
.\.venv\Scripts\python.exe -m ruff format --check app scripts tests
.\.venv\Scripts\python.exe -m alembic check
.\.venv\Scripts\python.exe -m pytest
```

После изменения моделей всегда должна существовать миграция. Не исправляйте красный
`alembic check` случайным изменением уже применённой миграции.

### 4. Frontend-проверки

```powershell
cd D:\Kanban\repository
npm --prefix frontend test
Get-ChildItem frontend\assets\js\*.js | ForEach-Object {
  node --check $_.FullName
}
```

### 5. Просмотр изменений

```powershell
git status --short
git diff --check
git diff --stat
git diff
```

Добавляйте осознанные пути:

```powershell
git add backend\app backend\alembic\versions backend\tests `
  frontend\assets frontend\index.html frontend\tests `
  VERSION CHANGELOG.md README.md docs

git commit -m "feat: add card collaboration"
git push -u origin HEAD
```

Не используйте `git add .`, пока не просмотрен `git status`.

### 6. GitHub Actions

Перед обновлением сервера должны быть зелёными:

- `Tests`;
- `Deploy GitHub Pages`, если менялся `frontend/**`.

При падении workflow исправляйте первую реальную ошибку. Последующие шаги часто падают только
потому, что предыдущий не прошёл.

## Обновление сервера после push в main

Откройте PowerShell от имени администратора:

```powershell
cd D:\Kanban\repository
.\scripts\update-from-main.ps1 -RunTests -NoBrowser
```

Скрипт:

1. требует чистое Git-дерево и ветку `main`;
2. создаёт backup;
3. останавливает только процессы этого Kanban;
4. выполняет `git pull --ff-only`;
5. обновляет Python-зависимости;
6. выполняет `alembic upgrade head`;
7. при `-RunTests` запускает Ruff и pytest;
8. создаёт новый Quick Tunnel и публикует runtime-config.

Если изменился только frontend, GitHub Pages обновится после push. Но серверную рабочую копию
всё равно нужно позже синхронизировать, иначе следующий runtime commit может конфликтовать.

## Выпуск новой версии

1. Измените `VERSION`, `backend/app/__init__.py`, `backend/pyproject.toml`, frontend version и
   `.env.example`.
2. Создайте Alembic-миграцию, если меняется схема.
3. Обновите `CHANGELOG.md` и документацию.
4. Выполните все проверки.
5. Создайте release commit и tag:

```powershell
git switch main
git pull --ff-only origin main
git merge --ff-only feature/<ветка>
git commit -m "release: Kanban Board 1.2.0"   # если release-commit ещё не создан
git tag -a v1.2.0 -m "Kanban Board 1.2.0"
git push origin main --tags
```

## Backup и восстановление

Создать backup:

```powershell
cd D:\Kanban\repository
.\scripts\backup-kanban.ps1
```

Проверить список:

```powershell
Get-ChildItem D:\Kanban\backups | Sort-Object LastWriteTime -Descending
```

Восстановить:

```powershell
.\scripts\restore-kanban.ps1 `
  -BackupPath "D:\Kanban\backups\kanban_20260730_120000.db"
```

После restore:

```powershell
cd .\backend
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic check
```

## Логи и диагностика

```powershell
cd D:\Kanban\repository
.\scripts\status-kanban.ps1

Get-Content D:\Kanban\logs\backend-stderr.log -Tail 100
Get-Content D:\Kanban\logs\cloudflared-stderr.log -Tail 100
Get-Content D:\Kanban\logs\kanban-backend.log -Tail 100
```

Локальные проверки:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health | Format-List
Invoke-RestMethod http://127.0.0.1:8000/api/v1/ready | Format-List
```

## Аварийная остановка

Сначала используйте штатный скрипт:

```powershell
.\scripts\stop-kanban.ps1
```

Он проверяет не только PID, но и имя/командную строку процесса. Устаревший PID-файл удаляется,
а чужой процесс не останавливается.

Не завершайте все процессы `python.exe` или `cloudflared.exe` на компьютере без проверки: они
могут принадлежать другим приложениям.
