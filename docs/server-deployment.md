# Развёртывание Kanban Board 1.1.0 на Windows-компьютере-сервере

Инструкция рассчитана на Windows 10/11 и Windows PowerShell 5.1. В примерах проект расположен
в `D:\Kanban\repository`, а данные — в `D:\Kanban\data`. Другой диск допустим: везде замените
`D:\Kanban` на свой путь.

## 1. Что будет работать на сервере

- GitHub Pages хранит HTML, CSS, JavaScript и `runtime-config.json`.
- FastAPI и SQLite работают только на серверном компьютере.
- Cloudflare Quick Tunnel выдаёт временный HTTPS-адрес API.
- При каждом запуске скрипт публикует новый адрес в `runtime-config.json` и отправляет его в
  GitHub через HTTPS.
- Пользователи всегда открывают один адрес GitHub Pages.

Quick Tunnel бесплатен, но Cloudflare предназначает его для тестирования и разработки, не
гарантирует uptime и ограничивает число одновременно обрабатываемых запросов. Официальная
документация: <https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/trycloudflare/>.

## 2. Подготовьте GitHub

1. В репозитории откройте `Settings -> Pages`.
2. В `Build and deployment` выберите `Source: GitHub Actions`.
3. Убедитесь, что workflow `Deploy GitHub Pages` завершился успешно.
4. Запишите постоянный адрес вида:

   ```text
   https://<owner>.github.io/<repository>/
   ```

GitHub описывает публикацию Pages через Actions здесь:
<https://docs.github.com/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site>.

## 3. Установите программы на сервер

Откройте PowerShell от имени администратора:

```powershell
winget install --exact --id Python.Python.3.11 --accept-package-agreements --accept-source-agreements
winget install --exact --id Git.Git --accept-package-agreements --accept-source-agreements
winget install --exact --id Cloudflare.cloudflared --accept-package-agreements --accept-source-agreements
```

Закройте PowerShell, откройте заново и проверьте:

```powershell
py -3.11 --version
git --version
cloudflared --version
```

## 4. Клонируйте репозиторий через HTTPS

```powershell
New-Item -ItemType Directory -Path D:\Kanban -Force | Out-Null
cd D:\Kanban
git clone https://github.com/<owner>/<repository>.git repository
cd D:\Kanban\repository
git remote -v
```

`origin` должен начинаться с `https://github.com/`, а не с `git@github.com:`. HTTPS работает
через порт 443 и обычно устойчивее в сетях, где SSH-порт 22 ограничен. Официальная команда
смены remote: <https://docs.github.com/get-started/git-basics/managing-remote-repositories>.

При необходимости:

```powershell
git remote set-url origin https://github.com/<owner>/<repository>.git
```

## 5. Запустите автоматическую настройку

PowerShell должен быть открыт от имени администратора:

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

Во время создания первого пользователя пароль вводится два раза и не отображается. Скрипт:

1. создаёт `.venv` и устанавливает зависимости;
2. создаёт или безопасно обновляет `backend\.env`;
3. генерирует `JWT_SECRET`, если `.env` создаётся впервые;
4. добавляет корректный CORS-origin в нижнем регистре;
5. создаёт каталоги данных, логов, backup и PID;
6. применяет Alembic-миграции;
7. переводит Git remote на HTTPS;
8. при указанном флаге регистрирует автозапуск и ежедневный backup.

## 6. Завершите GitHub-аутентификацию

До первого автоматического запуска выполните вручную:

```powershell
cd D:\Kanban\repository
git push --dry-run origin main
```

Git Credential Manager может открыть браузер. Авторизуйтесь под владельцем репозитория.
Команда `--dry-run` не отправляет изменения, но проверяет право на push.

## 7. Первый запуск

Используйте именно серверный скрипт:

```powershell
cd D:\Kanban\repository
.\scripts\start-kanban-server.ps1
```

Он временно закрепляет `api.trycloudflare.com` за IPv4 только на время регистрации Quick
Tunnel, затем удаляет запись. IPv6 в Windows не отключается и системные сетевые приоритеты не
изменяются.

Нормальный вывод содержит:

```text
Backend запущен...
Ожидание публикации DNS Quick Tunnel...
Quick Tunnel отвечает: https://....trycloudflare.com
runtime-config.json обновлён...
GitHub Pages получил configVersion=...
```

## 8. Проверка

```powershell
.\scripts\status-kanban.ps1
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health | Format-List
Invoke-RestMethod http://127.0.0.1:8000/api/v1/ready | Format-List
```

Затем откройте Pages URL, нажмите `Ctrl+F5`, войдите и создайте тестовую доску.

Проверка CORS:

```powershell
$pagesConfig = "https://<owner>.github.io/<repository>/runtime-config.json?ts=$([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds())"
$config = Invoke-RestMethod $pagesConfig
curl.exe -i -X OPTIONS "$($config.apiBaseUrl)/health" `
  -H "Origin: https://<owner>.github.io" `
  -H "Access-Control-Request-Method: GET" `
  -H "Access-Control-Request-Headers: x-request-id"
```

Ответ должен содержать `HTTP/1.1 200` и `access-control-allow-origin`.

## 9. Автозапуск

Если `-RegisterAutostart` не использовался:

```powershell
cd D:\Kanban\repository
.\scripts\register-autostart.ps1 -StartNow
```

Задача запускается при входе владельца сервера с повышенными правами. Это нужно для временной
записи в `hosts`. Вторая задача ежедневно создаёт проверенную копию базы в 03:00.

Проверка:

```powershell
Get-ScheduledTaskInfo -TaskName "KanbanBoard-Autostart" |
  Select-Object LastRunTime,LastTaskResult
Get-ScheduledTaskInfo -TaskName "KanbanBoard-DailyBackup" |
  Select-Object LastRunTime,LastTaskResult
```

`LastTaskResult = 0` означает успешный запуск.

## 10. Перенос существующих данных на новый сервер

На старом компьютере:

```powershell
cd D:\Kanban\repository
.\scripts\backup-kanban.ps1
.\scripts\stop-kanban.ps1
Get-ChildItem D:\Kanban\backups -Filter "kanban_*.db" |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 1 FullName,Length,LastWriteTime
```

Скопируйте выбранный `.db` и соседний `.json` на новый сервер, например в
`D:\Kanban\incoming-backup`. После установки нового сервера:

```powershell
cd D:\Kanban\repository
.\scripts\stop-kanban.ps1
.\scripts\restore-kanban.ps1 `
  -BackupPath "D:\Kanban\incoming-backup\kanban_YYYY-MM-DD_HH-mm-ss.db"
```

Одновременно держать старый и новый сервер запущенными нельзя: оба будут публиковать разные
Quick Tunnel URL в один `runtime-config.json`.

Копировать старый `.env` необязательно. Новый `JWT_SECRET` завершит старые браузерные сессии,
но пользователи и пароли сохранятся в базе. Старый `.env` можно переносить только через
защищённый канал и никогда не добавлять в Git.
