# Полное развёртывание Kanban Board MVP

Инструкция рассчитана на Windows 10/11 и первый запуск человеком, который раньше не
разворачивал веб-сервисы. Команды выполняйте в **Windows PowerShell 5.1** от обычного
пользователя. Права администратора нужны только тогда, когда Windows сама запросит их при
установке программ или регистрации задачи.

В примерах:

- `<owner>` — ваш GitHub username, например `ivan-petrov`;
- `<repository>` — имя репозитория, например `kanban-board`;
- постоянный адрес интерфейса — `https://<owner>.github.io/<repository>/`;
- исходный код находится в `C:\Kanban\repository`;
- рабочие данные находятся в `C:\Kanban\data`.

Не вводите угловые скобки буквально: заменяйте весь фрагмент вместе со скобками.

## 1. Как будет работать сервис

На GitHub Pages размещается только статический интерфейс. База, пароли, карточки и backend
остаются на вашем Windows-компьютере. При каждом запуске `cloudflared` выдаёт новый случайный
HTTPS-адрес. Скрипт запуска:

1. применяет миграции SQLite;
2. запускает один процесс Uvicorn на `127.0.0.1:8000`;
3. запускает Cloudflare Quick Tunnel;
4. проверяет API через публичный адрес;
5. атомарно обновляет `runtime-config.json`;
6. делает отдельный Git commit только этого файла и выполняет `git push`;
7. ждёт, пока GitHub Pages опубликует новую конфигурацию;
8. открывает постоянный URL интерфейса.

Если компьютер выключен, backend или туннель остановлены либо нет интернета, страница
GitHub Pages откроется, но работать с досками не сможет.

## 2. Выберите вариант GitHub Pages

### Вариант A — один публичный репозиторий

Это самый короткий путь. Подходит для GitHub Free. Исходный код будет виден всем, но база,
пароли, `.env`, логи и резервные копии в Git не попадают.

### Вариант B — приватный основной репозиторий

GitHub Pages для приватного репозитория доступен не на всех тарифах. Если ваш тариф
поддерживает Pages из приватного репозитория, дальнейшие шаги такие же, как для варианта A.
Сама опубликованная Pages-страница всё равно должна считаться публичной.

### Вариант C — приватный код и отдельный публичный frontend

На GitHub Free создайте приватный основной репозиторий и второй публичный репозиторий только
для содержимого `frontend/`. Сначала выполните обычную установку, затем настройте отдельный
frontend по разделу 13.

Актуальные ограничения тарифов проверяйте в официальной
[документации GitHub Pages](https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages).

## 3. Установите необходимые программы

Откройте PowerShell и проверьте наличие `winget`:

```powershell
winget --version
```

Если команда не найдена, обновите или установите **App Installer** из Microsoft Store. Затем
установите Python 3.11, Git и cloudflared:

```powershell
winget install --exact --id Python.Python.3.11 --accept-package-agreements --accept-source-agreements
winget install --exact --id Git.Git --accept-package-agreements --accept-source-agreements
winget install --exact --id Cloudflare.cloudflared --accept-package-agreements --accept-source-agreements
```

Закройте все окна PowerShell, откройте новое и проверьте:

```powershell
py -3.11 --version
git --version
cloudflared --version
```

Ожидается Python `3.11.x` или новее и номера версий Git/cloudflared. Если пакет cloudflared
не находится через WinGet, скачайте 64-bit Windows executable из официального раздела
[Cloudflare Downloads](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/downloads/),
переименуйте его в `cloudflared.exe`, положите, например, в
`C:\Program Files\cloudflared\` и добавьте этот каталог в системную переменную `Path`.

Можно попросить комплектный скрипт установить отсутствующие программы:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
cd C:\Kanban\repository
.\scripts\install-kanban.ps1 -InstallPrerequisites
```

После этого всё равно закройте PowerShell, откройте заново и проверьте три команды версий.

## 4. Подготовьте каталог проекта

Создайте каталоги:

```powershell
New-Item -ItemType Directory -Path C:\Kanban -Force
New-Item -ItemType Directory -Path C:\Kanban\repository -Force
```

Распакуйте предоставленный архив. В `C:\Kanban\repository` должны находиться непосредственно
`README.md`, папки `backend`, `frontend`, `scripts`, `docs` и `.github`, а не ещё одна
вложенная папка `kanban-board`.

Проверка:

```powershell
Get-ChildItem C:\Kanban\repository
Test-Path C:\Kanban\repository\backend\requirements.txt
Test-Path C:\Kanban\repository\scripts\start-kanban.ps1
```

Последние две команды должны вывести `True`.

## 5. Создайте GitHub-репозиторий и отправьте код

1. Войдите на `https://github.com/`.
2. Нажмите **New repository**.
3. В поле **Repository name** введите `<repository>`.
4. Выберите `Public` для варианта A или `Private` для вариантов B/C.
5. Не добавляйте README, `.gitignore` и лицензию: они уже есть.
6. Нажмите **Create repository**.

Настройте Git и выполните первый push:

```powershell
cd C:\Kanban\repository
git config --global user.name "Ваше имя"
git config --global user.email "ваш-email@example.com"
git init -b main
git add .
git commit -m "feat: initial Kanban Board"
git remote add origin https://github.com/<owner>/<repository>.git
git push -u origin main
```

Git Credential Manager откроет браузер. Войдите в нужную учётную запись GitHub и подтвердите
доступ. Пароль GitHub в PowerShell вводить не нужно. Если `origin` уже существует, не
добавляйте его повторно; проверьте адрес:

```powershell
git remote -v
```

Для исправления неверного адреса:

```powershell
git remote set-url origin https://github.com/<owner>/<repository>.git
```

Проверка сохранённого механизма учётных данных:

```powershell
git config --show-origin --get-all credential.helper
git push --dry-run
```

`git push --dry-run` не должен запрашивать пароль и не должен менять репозиторий.

## 6. Включите GitHub Pages

1. Откройте репозиторий на GitHub.
2. Перейдите **Settings → Pages**.
3. В разделе **Build and deployment** выберите **Source: GitHub Actions**.
4. Откройте вкладку **Actions** репозитория.
5. Найдите workflow **Deploy GitHub Pages** и дождитесь зелёного результата. Если он ещё не
   запускался, нажмите **Run workflow → Run workflow**.
6. Снова откройте **Settings → Pages**. GitHub покажет адрес
   `https://<owner>.github.io/<repository>/`.

Workflow использует официальный механизм GitHub Actions. Справочник:
[публикация Pages через custom workflow](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages).

До первого запуска backend страница может показать, что сервер недоступен: в исходном
`runtime-config.json` ещё нет рабочего Quick Tunnel URL. Это нормально.

## 7. Установите backend

Разрешите запуск локальных скриптов только в текущем окне PowerShell:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
cd C:\Kanban\repository
.\scripts\install-kanban.ps1 `
  -InstallRoot "C:\Kanban" `
  -GitHubOwner "<owner>" `
  -RepositoryName "<repository>"
```

Скрипт:

- создаст `C:\Kanban\data`, `logs`, `backups`, `run`;
- создаст `backend\.venv`;
- установит зафиксированные Python-зависимости;
- сгенерирует случайный `JWT_SECRET`, не показывая его;
- создаст `backend\.env`;
- создаст SQLite-базу и применит Alembic migration.

Ожидаемое завершение: `Установка завершена.` Безопасные проверки:

```powershell
Test-Path C:\Kanban\repository\backend\.venv\Scripts\python.exe
Test-Path C:\Kanban\repository\backend\.env
Test-Path C:\Kanban\data\kanban.db
```

Все команды должны вывести `True`. Не публикуйте `backend\.env` и не отправляйте его другим
людям: там находится ключ подписи сессий.

Если `.env` уже существовал, installer намеренно его не переписывает. Чтобы изменить owner,
имя репозитория или пути после установки, отредактируйте именно
`C:\Kanban\repository\backend\.env`.

## 8. Создайте пользователей

Публичной регистрации нет. Учётные записи создаются только локальной CLI-командой.

```powershell
cd C:\Kanban\repository\backend
.\.venv\Scripts\python.exe -m scripts.manage_users create user01 --display-name "Иван Петров"
```

Введите пароль дважды. Минимальная длина — 8 символов. Username: от 3 до 80 символов,
только латинские `a-z`, цифры, точка, дефис и подчёркивание. Регистр username не учитывается.

Для пакетного создания скопируйте шаблон **за пределы Git-репозитория**:

```powershell
Copy-Item .\scripts\users.example.csv C:\Kanban\users.csv
notepad C:\Kanban\users.csv
```

Формат:

```csv
username,display_name,password
user01,Иван Петров,длинный-уникальный-пароль
user02,Мария Иванова,другой-длинный-пароль
```

Импорт выполняется одной транзакцией: если хотя бы одна строка неверна, никто из файла не
будет создан.

```powershell
.\.venv\Scripts\python.exe -m scripts.manage_users import-csv C:\Kanban\users.csv
.\.venv\Scripts\python.exe -m scripts.manage_users list
```

Чтобы подготовить ровно 30 аккаунтов `user01`–`user30` со случайными индивидуальными
паролями, можно сгенерировать CSV локально:

```powershell
$kanbanPasswordRng = New-Object Security.Cryptography.RNGCryptoServiceProvider
$kanbanUserRows = 1..30 | ForEach-Object {
  $kanbanPasswordBytes = New-Object byte[] 18
  $kanbanPasswordRng.GetBytes($kanbanPasswordBytes)
  [PSCustomObject]@{
    username = "user{0:d2}" -f $_
    display_name = "Пользователь {0:d2}" -f $_
    password = [Convert]::ToBase64String($kanbanPasswordBytes)
  }
}
$kanbanPasswordRng.Dispose()
$kanbanUserRows | Export-Csv C:\Kanban\users.csv -NoTypeInformation -Encoding UTF8
```

Импортируйте этот файл предыдущей командой. Передайте каждому человеку только его пароль по
подходящему защищённому каналу и потребуйте сменить пароль в интерфейсе после первого входа.
Пока пароли нужны для раздачи, храните CSV с ограниченным доступом. После успешного импорта и
раздачи удалите точный файл, потому что в нём открытые пароли:

```powershell
Remove-Item -LiteralPath C:\Kanban\users.csv
```

Другие команды:

```powershell
.\.venv\Scripts\python.exe -m scripts.manage_users disable user01
.\.venv\Scripts\python.exe -m scripts.manage_users enable user01
.\.venv\Scripts\python.exe -m scripts.manage_users reset-password user01
```

Отключение пользователя и сброс пароля отзывают его refresh-сессии.

## 9. Выполните первый запуск

Перед запуском убедитесь, что Git-дерево чистое:

```powershell
cd C:\Kanban\repository
git status --short
```

Команда не должна ничего вывести. Затем:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\start-kanban.ps1
```

Нормальная последовательность сообщений:

```text
Backend запущен: PID ..., версия 1.0.0.
Quick Tunnel отвечает: https://....trycloudflare.com, API v1.
runtime-config.json обновлён: configVersion=...
[main ...] chore(runtime): update quick tunnel URL
GitHub Pages получил configVersion=...: https://<owner>.github.io/<repository>/
Система продолжает работать в фоне.
```

Скрипт может ждать GitHub Pages до пяти минут. Не закрывайте окно до итогового сообщения.
После завершения backend и cloudflared работают скрыто в фоне; PowerShell можно закрыть.

Если Git push не удался, backend и туннель продолжают работать, но постоянная страница не
узнает новый адрес. Исправьте Git-доступ и повторите `start-kanban.ps1`.

## 10. Проверьте первый запуск

Локальный health:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health | Format-List
Invoke-RestMethod http://127.0.0.1:8000/api/v1/ready | Format-List
```

Ожидается `status: ok` для health и `ready: True` для ready. Проверьте опубликованную
конфигурацию:

```powershell
$pagesConfig = "https://<owner>.github.io/<repository>/runtime-config.json?ts=$([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds())"
Invoke-RestMethod $pagesConfig | Format-List
```

`apiBaseUrl` должен начинаться с `https://` и заканчиваться `/api/v1`,
`configVersion` должен быть не меньше `1`.

Теперь откройте:

```text
https://<owner>.github.io/<repository>/
```

Войдите созданным пользователем и вручную проверьте:

1. создание доски;
2. добавление колонок;
3. создание и перенос карточки;
4. WIP-лимит;
5. поиск и фильтры;
6. архивирование и восстановление карточки/доски;
7. журнал действий;
8. вход вторым пользователем в другом браузере и обновление состояния без перезагрузки.

Эти проверки не являются частью установки; выполните их после вашего первого запуска.

## 11. Остановка и повторный запуск

Остановить только процессы этого проекта:

```powershell
cd C:\Kanban\repository
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\stop-kanban.ps1
```

После перезагрузки компьютера:

```powershell
cd C:\Kanban\repository
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\start-kanban.ps1
```

Каждый старт получает новый `trycloudflare.com` URL и публикует новый runtime commit. Это
ожидаемое поведение Quick Tunnel.

## 12. Включите автозапуск и ежедневный backup

Сначала убедитесь, что ручные установка, запуск и backup работают. Затем:

```powershell
cd C:\Kanban\repository
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\register-autostart.ps1
```

Будут созданы две задачи:

- `KanbanBoard-Autostart` — при входе текущего Windows-пользователя;
- `KanbanBoard-DailyBackup` — ежедневно в 03:00.

Проверка:

```powershell
Get-ScheduledTask -TaskName "KanbanBoard-Autostart","KanbanBoard-DailyBackup" |
  Select-Object TaskName,State
```

Задача запуска привязана к интерактивному входу пользователя, чтобы Git Credential Manager
мог использовать сохранённую авторизацию. После перезагрузки войдите в Windows и подождите
до пяти минут публикации Pages.

## 13. Отдельный публичный frontend-репозиторий

Этот раздел нужен только для варианта C.

### 13.1. Создайте и клонируйте frontend-репозиторий

На GitHub создайте публичный пустой репозиторий, например `<repository>-pages`. Затем:

```powershell
cd C:\Kanban
git clone https://github.com/<owner>/<repository>-pages.git frontend-pages
```

Скопируйте статический frontend в корень нового репозитория:

```powershell
Copy-Item C:\Kanban\repository\frontend\index.html C:\Kanban\frontend-pages\
Copy-Item C:\Kanban\repository\frontend\404.html C:\Kanban\frontend-pages\
Copy-Item C:\Kanban\repository\frontend\.nojekyll C:\Kanban\frontend-pages\
Copy-Item C:\Kanban\repository\frontend\runtime-config.json C:\Kanban\frontend-pages\
Copy-Item C:\Kanban\repository\frontend\runtime-config.example.json C:\Kanban\frontend-pages\
Copy-Item C:\Kanban\repository\frontend\package.json C:\Kanban\frontend-pages\
Copy-Item C:\Kanban\repository\frontend\assets C:\Kanban\frontend-pages\assets -Recurse
Copy-Item C:\Kanban\repository\frontend\tests C:\Kanban\frontend-pages\tests -Recurse
New-Item C:\Kanban\frontend-pages\.github\workflows -ItemType Directory -Force
Copy-Item C:\Kanban\repository\docs\templates\deploy-pages-standalone.yml `
  C:\Kanban\frontend-pages\.github\workflows\deploy-pages.yml
```

Отправьте frontend:

```powershell
cd C:\Kanban\frontend-pages
git add .
git commit -m "feat: publish Kanban frontend"
git push -u origin main
```

В этом репозитории выберите **Settings → Pages → Source: GitHub Actions**, дождитесь зелёного
workflow и проверьте URL:

```text
https://<owner>.github.io/<repository>-pages/
```

### 13.2. Переключите runtime-публикацию

Откройте:

```powershell
notepad C:\Kanban\repository\backend\.env
```

Замените ровно три значения:

```dotenv
GITHUB_PAGES_URL=https://<owner>.github.io/<repository>-pages/
FRONTEND_REPOSITORY_PATH=C:/Kanban/frontend-pages
RUNTIME_CONFIG_PATH=runtime-config.json
```

`ALLOWED_ORIGINS` оставьте в виде `https://<owner>.github.io,...`: CORS origin не содержит
путь репозитория.

Оба Git-репозитория должны быть на ветке `main` и без посторонних изменений:

```powershell
git -C C:\Kanban\repository status --short
git -C C:\Kanban\frontend-pages status --short
```

Обе команды должны ничего не вывести. Запустите:

```powershell
cd C:\Kanban\repository
.\scripts\start-kanban.ps1
```

Backend останется в приватном основном репозитории, а runtime commit будет создаваться только
в публичном frontend-репозитории.

## 14. Что хранить и чего не делать

Храните резервные копии `C:\Kanban\backups` ещё на одном физическом носителе или в
защищённом хранилище. Папка с backup содержит все данные досок и хеши паролей.

Не делайте следующее:

- не запускайте Uvicorn с несколькими workers при SQLite;
- не коммитьте `backend\.env`, базу, логи и backup;
- не публикуйте CSV с открытыми паролями;
- не запускайте второй экземпляр `start-kanban.ps1` параллельно;
- не редактируйте `runtime-config.json` вручную во время работающего старта;
- не используйте Quick Tunnel как инфраструктуру с гарантированным SLA;
- не храните в MVP платёжные данные, пароли сторонних систем или критичные документы.

## 15. Контрольный список готовности

- [ ] Python, Git и cloudflared доступны из нового PowerShell.
- [ ] Код отправлен в ветку `main`.
- [ ] Git Credential Manager позволяет выполнить `git push --dry-run`.
- [ ] GitHub Pages использует Source: GitHub Actions.
- [ ] `install-kanban.ps1` завершился без ошибки.
- [ ] Создан хотя бы один локальный пользователь.
- [ ] `start-kanban.ps1` получил Quick Tunnel URL и сделал runtime push.
- [ ] `/health` и `/ready` отвечают.
- [ ] Опубликованный `runtime-config.json` содержит текущий URL.
- [ ] Вход и базовые операции проверены вручную.
- [ ] Создан и проверен первый backup.
- [ ] Только после ручной проверки зарегистрирован автозапуск.

При любой ошибке сначала откройте [troubleshooting.md](troubleshooting.md), а для понимания
публикации адреса — [tunnel-automation.md](tunnel-automation.md).
