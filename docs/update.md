# Обновление Kanban Board

## Обновление с 1.1.0 до 1.2.0 пакетом

Перед началом:

```powershell
cd D:\Kanban\repository
git status --short
.\scripts\backup-kanban.ps1
```

Git-дерево должно быть чистым. Распакуйте `Kanban_Board_Update_1.2.0.zip`, разблокируйте
PowerShell-файл и запустите от имени администратора:

```powershell
Get-ChildItem D:\Kanban\Kanban_Board_Update_1.2.0 -Recurse -Filter "*.ps1" | Unblock-File
Set-ExecutionPolicy -Scope Process Bypass -Force

& "D:\Kanban\Kanban_Board_Update_1.2.0\apply-update-1.2.0.ps1" `
  -RepositoryRoot "D:\Kanban\repository"
```

Updater безопасно останавливает процессы, копирует код, сохраняет заменяемые файлы в
`D:\Kanban\update-backups`, не трогает `.env`, `.venv`, базу и текущий
`frontend/runtime-config.json`.

После копирования:

```powershell
cd D:\Kanban\repository\backend
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m ruff check app scripts tests
.\.venv\Scripts\python.exe -m ruff format --check app scripts tests
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic check
.\.venv\Scripts\python.exe -m pytest

cd ..
npm --prefix frontend test
Get-ChildItem frontend\assets\js\*.js | ForEach-Object { node --check $_.FullName }
```

Проверьте изменения и отправьте в GitHub:

```powershell
git status --short
git diff --check
git diff --stat

git add .gitattributes .gitignore .editorconfig VERSION CHANGELOG.md README.md LICENSE `
  backend frontend scripts docs

git commit -m "release: Kanban Board 1.2.0"
git push origin main
```

После зелёных GitHub Actions:

```powershell
.\scripts\start-kanban-server.ps1
```

## Что делает миграция 1.2.0

`20260730_0002`:

- добавляет nullable `cards.assignee_user_id`;
- добавляет nullable `cards.completed_at`;
- создаёт `card_comments`;
- создаёт `card_checklist_items`;
- добавляет индексы и внешние ключи.

Существующие пользователи, доски, колонки и карточки не переписываются. Старые карточки после
upgrade остаются без ответственного, незавершёнными, без комментариев и чек-листа.

## Рекомендуемый способ после 1.2.0: origin/main

После успешных GitHub Actions откройте PowerShell на сервере от имени администратора:

```powershell
cd D:\Kanban\repository
.\scripts\update-from-main.ps1 -RunTests -NoBrowser
```

Скрипт создаёт backup, останавливает сервис, выполняет fast-forward pull, устанавливает
зависимости, применяет миграции, запускает тесты и стартует новый tunnel.

Быстрый вариант после зелёного workflow:

```powershell
.\scripts\update-from-main.ps1 -NoBrowser
```

## Обновление по release tag

```powershell
.\scripts\update-kanban.ps1 -VersionTag "v1.2.0" -NoBrowser
```

Tag должен быть fast-forward продолжением текущего commit.

## Откат к backup кода

Updater выводит каталог вида:

```text
D:\Kanban\update-backups\1.2.0-20260730-180000
```

До миграции можно вернуть файлы из этого каталога. После применения миграции безопаснее
оставить новую схему: приложение 1.1 не знает новых таблиц, но наличие дополнительных таблиц и
nullable-колонок обычно не мешает. Полный downgrade делайте только вместе с проверенным backup
базы и командой:

```powershell
cd D:\Kanban\repository\backend
.\.venv\Scripts\python.exe -m alembic downgrade 20260727_0001
```

Downgrade удалит комментарии, чек-листы, ответственных и отметки завершения. Поэтому перед ним
обязателен backup.

## Проверка после обновления

```powershell
Get-Content D:\Kanban\repository\VERSION
.\scripts\status-kanban.ps1
Invoke-RestMethod http://127.0.0.1:8000/api/v1/ready | Format-List
```

Ожидаются версия `1.2.0` и revision `20260730_0002`.
