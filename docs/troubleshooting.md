# Типовые ошибки

## PowerShell показывает `РќРµ...` и ParserError

Это кодировка UTF-8 без BOM в Windows PowerShell 5.1. В релизе 1.1.0 все `.ps1` сохранены как
UTF-8 with BOM. Не пересохраняйте их старым редактором в ANSI или UTF-8 without BOM.

## Запуск запрещён из-за незакоммиченных файлов

```powershell
git status --short
```

Сохраните код отдельным commit. Локальные `.env`, `.venv`, `__pycache__`, `test-logs`, `.idea`,
логи и базы должны скрываться `.gitignore`. Не используйте `git add .`, пока не проверили
список.

## PID принадлежит другому процессу

Версия 1.1.0 удаляет устаревший PID-файл и не останавливает чужой процесс. Затем выполняется
поиск только процессов с точной командной строкой Kanban.

```powershell
.\scripts\stop-kanban.ps1
```

## `failed to request quick Tunnel` и IPv6 reset

Запускайте не `start-kanban.ps1`, а:

```powershell
.\scripts\start-kanban-server.ps1
```

Он временно использует IPv4 только для запроса регистрации. IPv6 адаптера и реестр Windows не
изменяются.

Проверка сети:

```powershell
curl.exe -4 -v -X POST https://api.trycloudflare.com/tunnel -o NUL
curl.exe -6 -v -X POST https://api.trycloudflare.com/tunnel -o NUL
```

## Выдан URL, но hostname ещё не разрешается

Скрипт ждёт DNS и периодически очищает локальный DNS-кэш. Не копируйте URL вручную. Посмотрите:

```powershell
Get-Content D:\Kanban\logs\cloudflared-stderr.log -Tail 100
```

## Git push падает на порту 22

Проверьте remote:

```powershell
git remote -v
```

Исправьте на HTTPS:

```powershell
git remote set-url origin https://github.com/<owner>/<repository>.git
git push --dry-run origin main
```

## Сайт пишет «Сервер недоступен», но public health работает

Проверьте удалённый runtime:

```powershell
$url = "https://<owner>.github.io/<repository>/runtime-config.json?ts=$([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds())"
$config = Invoke-RestMethod $url
$config | Format-List
Invoke-RestMethod "$($config.apiBaseUrl)/health" | Format-List
```

Затем проверьте CORS. Origin не включает путь репозитория и должен быть в нижнем регистре:

```text
https://<owner>.github.io
```

После изменения `.env` перезапустите backend.

## `Disallowed CORS origin`

```powershell
Select-String D:\Kanban\repository\backend\.env -Pattern "^ALLOWED_ORIGINS="
```

Повторно запустите installer: он сохранит secret и данные, но исправит публичные URL:

```powershell
.\scripts\install-kanban.ps1 `
  -InstallRoot "D:\Kanban" `
  -GitHubOwner "<owner>" `
  -RepositoryName "<repository>"
```

## GitHub Actions: `alembic check` сообщает changed index

Модель и миграция расходятся. Не генерируйте случайную миграцию поверх рабочей базы. В версии
1.1.0 модель `users.username` соответствует initial migration: UNIQUE constraint и отдельный
неуникальный индекс.

Локальная проверка:

```powershell
cd backend
.\.venv\Scripts\python.exe -m alembic check
```

## Browser: `Failed to execute fetch ... Illegal invocation`

В версии 1.1.0 native fetch вызывается через обёртку, сохраняющую правильный контекст. После
обновления frontend дождитесь Pages и нажмите `Ctrl+F5`.

## Где смотреть логи

```powershell
Get-Content D:\Kanban\logs\backend-stderr.log -Tail 100
Get-Content D:\Kanban\logs\cloudflared-stderr.log -Tail 100
Get-Content D:\Kanban\logs\kanban-backend.log -Tail 100
.\scripts\status-kanban.ps1
```
