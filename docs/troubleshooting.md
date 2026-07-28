# Диагностика типовых ошибок

Начинайте с точного текста ошибки. Не удаляйте базу, `.env`, `.git` или backup и не
завершайте все процессы Python на компьютере.

## Быстрый снимок состояния

Выполните:

```powershell
cd C:\Kanban\repository

py -3.11 --version
git --version
cloudflared --version

git status --short
git branch --show-current
git remote -v

Test-Path .\backend\.env
Test-Path .\backend\.venv\Scripts\python.exe
Test-Path C:\Kanban\data\kanban.db

Get-Content C:\Kanban\logs\backend-stderr.log -Tail 100
Get-Content C:\Kanban\logs\cloudflared-stderr.log -Tail 100
```

При обращении за помощью сохраните вывод, но удалите из него секреты. Не показывайте
содержимое `JWT_SECRET`, пароли или файлы backup.

## PowerShell запрещает выполнение скрипта

Сообщение содержит `running scripts is disabled`.

Разрешите только в текущем окне:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
```

Затем повторите команду в том же PowerShell. Изменять системную политику навсегда не
требуется.

## `py`, `git` или `cloudflared` не найдены

Закройте PowerShell после установки и откройте новый. Проверьте:

```powershell
Get-Command py,git,cloudflared
```

Если команда всё ещё отсутствует, повторите установку из `deployment.md`. Для cloudflared,
установленного вручную, убедитесь, что каталог с `cloudflared.exe` добавлен в `Path`.

## Installer не находит Python 3.11

```powershell
py --list
py -3.11 --version
```

Если 3.11 отсутствует:

```powershell
winget install --exact --id Python.Python.3.11 --accept-package-agreements --accept-source-agreements
```

Откройте новый PowerShell и повторите installer.

## Ошибка установки Python-зависимостей

Проверьте интернет и запустите:

```powershell
cd C:\Kanban\repository
.\backend\.venv\Scripts\python.exe -m pip --version
.\backend\.venv\Scripts\python.exe -m pip install -r .\backend\requirements.txt
```

Сохраните полный вывод. Не заменяйте версии пакетов случайными более новыми версиями до
выяснения причины.

## `backend\.env` уже существует

Installer специально не перезаписывает секреты. Если это корректная прежняя установка,
оставьте файл. Проверьте пути:

```powershell
Select-String -Path C:\Kanban\repository\backend\.env `
  -Pattern "DATABASE_URL|LOG_DIR|RUN_DIR|BACKUP_DIR|GITHUB_PAGES_URL|REPOSITORY_PATH|FRONTEND_REPOSITORY_PATH|RUNTIME_CONFIG_PATH"
```

Не публикуйте строку `JWT_SECRET`.

Если `.env` создан ошибочно до первого использования и в базе нет данных, сначала сохраните
его копию вручную, затем решите, нужно ли создавать конфигурацию заново. Installer не делает
этот выбор автоматически.

## Старт сообщает о незакоммиченных изменениях

```powershell
git -C C:\Kanban\repository status --short
git -C C:\Kanban\repository diff
git -C C:\Kanban\repository diff --cached
```

Проверьте каждый файл. Если это ваша работа, создайте осмысленный commit:

```powershell
git add <точный-путь-к-файлу>
git commit -m "описание изменения"
git push
```

Не используйте команды массового сброса. Старт разрешает автоматически менять только
настроенный runtime-файл.

Для отдельного frontend проверьте оба дерева:

```powershell
git -C C:\Kanban\repository status --short
git -C C:\Kanban\frontend-pages status --short
```

## Старт требует ветку `main`

```powershell
git status --short
git branch --show-current
```

Сначала сохраните изменения. Затем переключитесь на существующую `main`:

```powershell
git switch main
```

Если ветки `main` нет, выясните имя default branch в GitHub и приведите репозиторий к
описанной в инструкции структуре. Не переименовывайте ветку во время работающего сервиса.

## Backend не отвечает локально

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health
Get-Content C:\Kanban\logs\backend-stderr.log -Tail 200
Get-Content C:\Kanban\logs\kanban-backend.log -Tail 200
```

Проверьте PID:

```powershell
$pidValue = [int](Get-Content C:\Kanban\run\backend.pid -Raw)
Get-CimInstance Win32_Process -Filter "ProcessId = $pidValue" |
  Select-Object ProcessId,CommandLine
```

Если порт занят другим приложением:

```powershell
Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue |
  Select-Object LocalAddress,LocalPort,State,OwningProcess
```

Не завершайте найденный чужой процесс, пока не установите, что это такое. MVP ожидает
свободный локальный порт 8000.

## `database is locked`

Проверьте, не запущен ли второй Uvicorn или ручная копия backend:

```powershell
Get-CimInstance Win32_Process |
  Where-Object { $_.CommandLine -like "*uvicorn*app.main:app*" } |
  Select-Object ProcessId,CommandLine
```

Должен быть один процесс с `--workers 1`. Остановите сервис комплектным скриптом и запустите
снова:

```powershell
.\scripts\stop-kanban.ps1
.\scripts\start-kanban.ps1
```

Не запускайте `uvicorn --workers 2` и не открывайте рабочую базу утилитой, которая удерживает
write transaction.

## Миграция или `/ready` завершается ошибкой

Сначала создайте/найдите последний проверенный backup и сохраните логи. Посмотреть revision:

```powershell
cd C:\Kanban\repository\backend
.\.venv\Scripts\python.exe -m alembic current
.\.venv\Scripts\python.exe -m alembic heads
```

Не редактируйте таблицу `alembic_version` вручную. Если код и база разных релизов, верните
согласованную версию кода или выполните документированное обновление.

## cloudflared не выдаёт URL

```powershell
Get-Content C:\Kanban\logs\cloudflared-stdout.log -Tail 200
Get-Content C:\Kanban\logs\cloudflared-stderr.log -Tail 200
Test-NetConnection region1.v2.argotunnel.com -Port 7844
```

Проверьте наличие конфликтующей конфигурации:

```powershell
Test-Path "$env:USERPROFILE\.cloudflared\config.yaml"
Test-Path "$env:USERPROFILE\.cloudflared\config.yml"
```

Если файл существует и принадлежит другому сервису, временно переименуйте его согласно
`tunnel-automation.md`. Также проверьте корпоративный firewall, VPN, антивирус и доступ в
интернет.

## Публичный tunnel URL есть, но health не отвечает

Возьмите точный URL из лога:

```powershell
Select-String `
  -Path C:\Kanban\logs\cloudflared-stdout.log,C:\Kanban\logs\cloudflared-stderr.log `
  -Pattern "https://[-a-z0-9]+\.trycloudflare\.com"
```

Проверьте:

```powershell
Invoke-RestMethod https://<точный-url>.trycloudflare.com/api/v1/health
```

Если локальный health работает, а публичный — нет, проблема находится между cloudflared и
Cloudflare: смотрите stderr, сеть, VPN и firewall.

## `git push` требует пароль или завершается 403

Проверьте remote:

```powershell
git remote -v
git config --show-origin --get-all credential.helper
```

Ожидается HTTPS URL нужного репозитория и Git Credential Manager. Выполните:

```powershell
git push --dry-run
```

Если открылся браузер, войдите в правильную учётную запись GitHub. У этой учётной записи
должно быть право записи в репозиторий. Пароль аккаунта GitHub не заменяет browser/OAuth
авторизацию.

## GitHub Pages не публикует новую конфигурацию

1. Откройте вкладку **Actions**.
2. Откройте последний workflow **Deploy GitHub Pages**.
3. Проверьте, что **Settings → Pages → Source** установлено в **GitHub Actions**.
4. Проверьте текущие tariff/visibility ограничения Pages.
5. Проверьте runtime commit:

```powershell
git log -5 --oneline
git show --stat --oneline HEAD
```

Опубликованную конфигурацию запросите без кэша:

```powershell
$url = "https://<owner>.github.io/<repository>/runtime-config.json?ts=$([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds())"
Invoke-RestMethod $url | Format-List
```

Если push успешен, не создавайте вручную несколько runtime commits подряд: дождитесь
завершения или прочитайте точную ошибку workflow.

## Страница открывается, но браузер сообщает CORS

Проверьте точный origin страницы в адресной строке и `ALLOWED_ORIGINS`:

```powershell
Select-String C:\Kanban\repository\backend\.env -Pattern "^ALLOWED_ORIGINS="
```

Для project Pages origin — только:

```text
https://<owner>.github.io
```

Путь `/<repository>/` в CORS origin не входит. После изменения `.env` перезапустите сервис:

```powershell
.\scripts\stop-kanban.ps1
.\scripts\start-kanban.ps1
```

Не используйте `*` для CORS с авторизованными запросами.

## Frontend показывает старый tunnel URL

Сравните локальную и удалённую конфигурации:

```powershell
Get-Content C:\Kanban\repository\frontend\runtime-config.json
$url = "https://<owner>.github.io/<repository>/runtime-config.json?ts=$([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds())"
Invoke-RestMethod $url | ConvertTo-Json
```

Если `configVersion` на Pages меньше, ждите GitHub Actions или диагностируйте workflow. Если
он равен, обновите вкладку `Ctrl+F5`. Service Worker в проекте не используется.

## Ошибки входа: 401, 403, 429

- `401` — неверный login/password, завершившаяся сессия или старый JWT после смены secret.
- `403` — учётная запись отключена или действие запрещено состоянием объекта.
- `429` — превышен лимит неудачных входов для пары IP/username; дождитесь указанного
  `Retry-After`.

Проверьте учётные записи локально:

```powershell
cd C:\Kanban\repository\backend
.\.venv\Scripts\python.exe -m scripts.manage_users list
```

При необходимости:

```powershell
.\.venv\Scripts\python.exe -m scripts.manage_users enable user01
.\.venv\Scripts\python.exe -m scripts.manage_users reset-password user01
```

Не пытайтесь извлекать пароль из базы: там хранится Argon2id hash.

## Ошибка версии или конфликт изменения

`*_VERSION_CONFLICT` означает, что другой пользователь изменил объект после загрузки вашей
формы. Frontend получает актуальное состояние. Повторите действие после проверки данных.

`WIP_LIMIT_EXCEEDED` означает, что целевая колонка достигла лимита. Увеличьте WIP-limit,
переместите другую карточку или выберите другую колонку.

## Автозапуск не сработал

```powershell
Get-ScheduledTask -TaskName "KanbanBoard-Autostart" | Format-List
Get-ScheduledTaskInfo -TaskName "KanbanBoard-Autostart" |
  Select-Object LastRunTime,LastTaskResult,NextRunTime
```

Запустите вручную:

```powershell
Start-ScheduledTask -TaskName "KanbanBoard-Autostart"
Start-Sleep -Seconds 10
Get-Content C:\Kanban\logs\backend-stderr.log -Tail 100
Get-Content C:\Kanban\logs\cloudflared-stderr.log -Tail 100
```

Задача запускается при интерактивном входе того Windows-пользователя, который её
зарегистрировал. У этого пользователя должен работать Git Credential Manager.

## Backup не создаётся

```powershell
Test-Path C:\Kanban\data\kanban.db
Test-Path C:\Kanban\repository\backend\.venv\Scripts\python.exe
Get-ChildItem C:\Kanban\backups
```

Запустите вручную и сохраните полный вывод:

```powershell
cd C:\Kanban\repository
.\scripts\backup-kanban.ps1
```

Ошибка integrity, отсутствующая таблица или несовпадающая Alembic revision означает, что
копия не считается проверенной. Не игнорируйте это сообщение.

## Безопасная повторная попытка запуска

После исправления причины:

```powershell
cd C:\Kanban\repository
.\scripts\stop-kanban.ps1
git status --short
.\scripts\start-kanban.ps1
```

Если `git status --short` показывает ваши изменения, сначала разберите и сохраните их. Не
автоматизируйте сброс рабочего дерева.
