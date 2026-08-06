# Обновление Kanban Board до 1.3.0

Инструкция предназначена для рабочей установки 1.2.0 в `D:\Kanban\repository`.

## Что сохраняется

Updater не заменяет:

- `backend/.env` и секреты;
- `backend/.venv`;
- `D:\Kanban\data\kanban.db`;
- backup, логи и PID-каталог;
- опубликованный `frontend/runtime-config.json`.

Перед миграцией создаётся проверенный backup базы.

## 1. Подготовка

Остановите изменения в доске и проверьте Git:

```powershell
cd D:\Kanban\repository
git status --short
git push origin main
```

`git status --short` должен быть пустым. Не запускайте updater с несохранёнными изменениями.

## 2. Запуск updater

Распакуйте архив в:

```text
D:\Kanban\Kanban_Board_Update_1.3.0
```

Откройте PowerShell от имени администратора:

```powershell
Get-ChildItem D:\Kanban\Kanban_Board_Update_1.3.0 -Recurse -Filter "*.ps1" | Unblock-File
Set-ExecutionPolicy -Scope Process Bypass -Force

& "D:\Kanban\Kanban_Board_Update_1.3.0\apply-update-1.3.0.ps1" `
  -RepositoryRoot "D:\Kanban\repository"
```

Updater:

1. проверит структуру проекта и чистоту Git;
2. создаст backup базы;
3. безопасно остановит backend и cloudflared, включая обработку устаревших PID-файлов;
4. сохранит заменяемые файлы в `D:\Kanban\update-backups\1.3.0-<date>`;
5. установит код 1.3.0;
6. сохранит `.env`, `.venv`, SQLite и текущий tunnel URL;
7. добавит в `.env` новые параметры, не заменяя SMTP-секреты;
8. применит Alembic revision `20260806_0003`;
9. выполнит readiness и `alembic check`;
10. выполнит Ruff `--fix`, форматирование, pytest и frontend-тесты.

## 3. Коммит обновления

После сообщения об успешном завершении:

```powershell
cd D:\Kanban\repository

git status --short
git diff --check
git diff --stat

git add .gitattributes .gitignore .editorconfig `
  VERSION CHANGELOG.md README.md LICENSE `
  backend frontend scripts docs .github

git diff --cached --check
git commit -m "release: Kanban Board 1.3.0"
git push origin main
```

Дождитесь зелёного GitHub Actions и публикации GitHub Pages.

## 4. Запуск

```powershell
cd D:\Kanban\repository
.\scripts\start-kanban-server.ps1
```

Проверьте:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/ready | Format-List
```

Ожидаются `appVersion: 1.3.0` и `alembicRevision: 20260806_0003`.

## 5. Первый вход после обновления

Старые логины и пароли сохраняются. Самый старый пользователь становится `owner`. Старые пользователи получают доступ к старым доскам, поэтому текущая работа не блокируется.

Владелец открывает раздел «Участники» и может:

- добавить email существующим пользователям;
- изменить системную роль;
- создать приглашение;
- назначить права на отдельные доски;
- сформировать ссылку сброса пароля.

## 6. Email

Без SMTP оставьте:

```env
EMAIL_ENABLED=false
```

При создании приглашения интерфейс покажет ссылку для ручной отправки.

Для SMTP измените `D:\Kanban\repository\backend\.env`:

```env
EMAIL_ENABLED=true
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=kanban@example.com
SMTP_PASSWORD=<secret>
SMTP_USE_TLS=true
EMAIL_FROM_ADDRESS=kanban@example.com
EMAIL_FROM_NAME=Kanban Board
FRONTEND_URL=https://nikitauskov.github.io/Kanban_SS/
```

Перезапустите сервис. `.env` не добавляется в Git.

## Откат кода

Если updater остановился до коммита, код можно вернуть из каталога, напечатанного updater. Базу восстанавливайте только если migration или проверка базы действительно завершилась ошибкой:

```powershell
.\scripts\restore-kanban.ps1 -BackupPath "D:\Kanban\backups\kanban_<date>.db"
```

Перед восстановлением обязательно остановите сервис.
