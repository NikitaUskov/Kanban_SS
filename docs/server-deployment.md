# Развёртывание Kanban Board 1.3.0 на Windows-сервере

## Требования

- Windows 10/11 или Windows Server;
- PowerShell 5.1+;
- Python 3.11+;
- Git for Windows;
- cloudflared;
- GitHub-репозиторий с включённым GitHub Pages;
- права администратора для временной IPv4-записи Quick Tunnel.

Node.js нужен только для локальной проверки frontend, но не для работы сервиса.

## 1. Подготовка каталогов

Рекомендуемая структура:

```text
C:\Kanban\repository
C:\Kanban\data
C:\Kanban\logs
C:\Kanban\backups
C:\Kanban\run
```

Клонируйте репозиторий через HTTPS:

```powershell
New-Item -ItemType Directory C:\Kanban -Force | Out-Null
cd C:\Kanban
git clone https://github.com/<owner>/<repository>.git repository
cd repository
```

## 2. Разблокировка скриптов

```powershell
Get-ChildItem C:\Kanban\repository\scripts -Recurse -Filter "*.ps1" | Unblock-File
Set-ExecutionPolicy -Scope Process Bypass -Force
```

## 3. Установка

Откройте PowerShell от имени администратора:

```powershell
cd C:\Kanban\repository

.\scripts\setup-server.ps1 `
  -InstallRoot "C:\Kanban" `
  -GitHubOwner "<owner>" `
  -RepositoryName "<repository>" `
  -FirstUsername "owner" `
  -FirstDisplayName "Владелец" `
  -FirstEmail "owner@example.com"
```

Скрипт:

- создаёт `.venv`;
- устанавливает зависимости;
- генерирует JWT secret;
- создаёт локальный `.env`;
- настраивает CORS и GitHub Pages URL;
- создаёт SQLite-базу;
- применяет Alembic до `20260806_0003`;
- создаёт первого владельца;
- переводит Git remote на HTTPS.

Если программы ещё не установлены:

```powershell
.\scripts\install-kanban.ps1 -InstallPrerequisites
```

После установки закройте PowerShell, откройте заново и повторите setup.

## 4. GitHub Pages

В GitHub откройте `Settings → Pages` и выберите публикацию через GitHub Actions. Workflow `.github/workflows/deploy-pages.yml` публикует каталог frontend.

Проверьте, что публичный frontend открывается по адресу:

```text
https://<owner>.github.io/<repository>/
```

## 5. Первый запуск

Из PowerShell администратора:

```powershell
cd C:\Kanban\repository
.\scripts\start-kanban-server.ps1
```

Скрипт:

- очищает устаревшие PID-файлы;
- запускает backend;
- регистрирует Quick Tunnel через IPv4;
- ждёт DNS-публикацию;
- записывает адрес API в `frontend/runtime-config.json`;
- делает commit/push runtime config;
- ждёт публикацию GitHub Pages.

Проверка:

```powershell
.\scripts\status-kanban.ps1
Invoke-RestMethod http://127.0.0.1:8000/api/v1/ready | Format-List
```

## 6. Настройка email

Email необязателен. В ручном режиме администратор копирует ссылку приглашения:

```env
EMAIL_ENABLED=false
```

Для SMTP измените `backend/.env` и перезапустите сервис:

```env
EMAIL_ENABLED=true
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=kanban@example.com
SMTP_PASSWORD=<secret>
SMTP_USE_TLS=true
SMTP_TIMEOUT_SECONDS=15
EMAIL_FROM_ADDRESS=kanban@example.com
EMAIL_FROM_NAME=Kanban Board
FRONTEND_URL=https://<owner>.github.io/<repository>/
```

Не отправляйте `.env` в Git и не публикуйте SMTP/JWT секреты.

## 7. Автозапуск

После ручной проверки:

```powershell
.\scripts\register-autostart.ps1
```

Создаются задачи Windows для запуска Kanban и ежедневного backup. Учётная запись задачи должна иметь право изменять `hosts`.

## 8. Остановка

```powershell
.\scripts\stop-kanban.ps1
```

Если PID-файл устарел, новые скрипты проверяют командную строку процесса и не завершают чужой процесс.
