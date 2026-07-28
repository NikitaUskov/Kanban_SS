# Автоматизация Cloudflare Quick Tunnel

## Назначение

GitHub Pages имеет постоянный URL, а бесплатный Quick Tunnel при каждом новом запуске
получает случайный адрес вида:

```text
https://random-words.trycloudflare.com
```

Frontend не содержит адрес backend в исходном JavaScript. Он при открытии загружает
`runtime-config.json`, проверяет структуру и версию конфигурации, а затем обращается к
`apiBaseUrl`. Благодаря этому для смены туннеля не нужно пересобирать приложение или сообщать
пользователям новый адрес страницы.

## Последовательность запуска

Команда:

```powershell
cd C:\Kanban\repository
.\scripts\start-kanban.ps1
```

выполняет следующие действия:

1. Проверяет наличие `git`, `cloudflared`, `.venv` и `backend\.env`.
2. Проверяет, что основной и, при наличии, отдельный frontend-репозиторий находятся на ветке
   `main`.
3. Отказывается запускаться при посторонних незакоммиченных файлах. Допускается только уже
   изменённый `runtime-config.json`.
4. Проверяет отсутствие `%USERPROFILE%\.cloudflared\config.yaml` и `config.yml`.
5. Останавливает прежние процессы проекта по проверенным PID-файлам.
6. Выполняет `alembic upgrade head`.
7. Запускает:

   ```text
   python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
   ```

8. Ждёт ответа локального `/api/v1/health`.
9. Запускает:

   ```text
   cloudflared tunnel --url http://127.0.0.1:8000 --no-autoupdate --loglevel info
   ```

10. Из stdout/stderr извлекает первый URL `https://*.trycloudflare.com`.
11. Проверяет `/api/v1/health` уже через публичный URL.
12. Создаёт временный runtime-файл, затем атомарно заменяет целевой файл.
13. Увеличивает `configVersion` на единицу.
14. Добавляет в Git index только runtime-файл и проверяет, что других staged-файлов нет.
15. Создаёт commit `chore(runtime): update quick tunnel URL` и выполняет `git push`.
16. Каждые 10 секунд запрашивает опубликованный runtime с cache-busting параметром.
17. Когда `configVersion` совпадёт, открывает GitHub Pages.

## Формат runtime-конфигурации

```json
{
  "apiBaseUrl": "https://example.trycloudflare.com/api/v1",
  "generatedAt": "2026-07-27T12:00:00Z",
  "configVersion": 42,
  "appVersion": "1.0.0",
  "apiVersion": "v1"
}
```

В файле нет секретов. URL туннеля публичный по своей природе, но все прикладные endpoint,
кроме health/ready, требуют авторизации.

## Поведение frontend при смене адреса

- Конфигурация загружается с запретом кэширования.
- При увеличении `configVersion` API-клиент переключается на новый `apiBaseUrl`.
- Access token хранится в `sessionStorage`, refresh token — в `localStorage`. При выходе
  оба удаляются, а refresh token отзывается на backend.
- При временной недоступности показывается состояние переподключения.
- Frontend повторно загружает конфигурацию и health, затем восстанавливает текущий экран.
- Несовпадение `apiVersion` блокирует мутации и показывает сообщение о несовместимости.

## Где находятся процессы и логи

При стандартной установке:

```text
C:\Kanban\run\backend.pid
C:\Kanban\run\cloudflared.pid
C:\Kanban\logs\backend-stdout.log
C:\Kanban\logs\backend-stderr.log
C:\Kanban\logs\cloudflared-stdout.log
C:\Kanban\logs\cloudflared-stderr.log
C:\Kanban\logs\kanban-backend.log
```

Посмотреть последние строки:

```powershell
Get-Content C:\Kanban\logs\backend-stderr.log -Tail 100
Get-Content C:\Kanban\logs\cloudflared-stderr.log -Tail 100
Get-Content C:\Kanban\logs\kanban-backend.log -Tail 100
```

Проверить PID без остановки:

```powershell
$backendPid = [int](Get-Content C:\Kanban\run\backend.pid -Raw)
$tunnelPid = [int](Get-Content C:\Kanban\run\cloudflared.pid -Raw)
Get-CimInstance Win32_Process -Filter "ProcessId = $backendPid" |
  Select-Object ProcessId,CommandLine
Get-CimInstance Win32_Process -Filter "ProcessId = $tunnelPid" |
  Select-Object ProcessId,CommandLine
```

## Что происходит при ошибках

| Этап | Результат ошибки | Действие |
|---|---|---|
| Проверка Git | Ничего не запускается | Сохранить свои изменения отдельным commit |
| Alembic | Backend не запускается | Проверить backup и migration |
| Локальный health | PID сохранён, старт завершается ошибкой | Посмотреть backend stderr, затем `stop-kanban.ps1` |
| Получение Tunnel URL | Backend может работать локально | Посмотреть cloudflared stderr, затем остановить/повторить |
| Публичный health | URL не публикуется | Проверить интернет/Cloudflare |
| Git commit/push | Backend и туннель остаются рабочими; Pages хранит старый URL | Исправить Git-доступ и повторить старт |
| Ожидание Pages | Push уже выполнен | Проверить GitHub Actions; не редактировать runtime вручную |

Скрипт не добавляет в commit другие файлы и не отменяет пользовательские Git-изменения.

## Ручные диагностические проверки

Локальный API:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health
```

Найти выданный адрес:

```powershell
Select-String `
  -Path C:\Kanban\logs\cloudflared-stdout.log,C:\Kanban\logs\cloudflared-stderr.log `
  -Pattern "https://[-a-z0-9]+\.trycloudflare\.com"
```

Проверить публичный API, подставив адрес:

```powershell
Invoke-RestMethod https://<random>.trycloudflare.com/api/v1/health
```

Проверить runtime в рабочем дереве и на Pages:

```powershell
Get-Content C:\Kanban\repository\frontend\runtime-config.json
$url = "https://<owner>.github.io/<repository>/runtime-config.json?ts=$([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds())"
Invoke-RestMethod $url
```

Git-состояние:

```powershell
git -C C:\Kanban\repository status --short
git -C C:\Kanban\repository log -5 --oneline
git -C C:\Kanban\repository diff --cached --name-only
```

## Известные ограничения Quick Tunnel

Cloudflare позиционирует Quick Tunnels для разработки и тестирования, без SLA. У них есть
ограничение на число одновременных запросов, не поддерживается Server-Sent Events и новый URL
выдаётся при каждом старте. Точные текущие ограничения:
[официальная документация Quick Tunnels](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/trycloudflare/).

Для MVP используется polling, поэтому отсутствие SSE не мешает работе. При стабильной
эксплуатации, требованиях SLA или необходимости постоянного API-домена перейдите на named
Cloudflare Tunnel или другой постоянный backend hosting. При таком переходе
`runtime-config.json` можно оставить с постоянным URL, а runtime commit на каждом старте
отключить отдельным изменением скрипта.

## Конфликт с существующей конфигурацией cloudflared

Quick Tunnel может не запускаться, если существует:

```text
%USERPROFILE%\.cloudflared\config.yaml
%USERPROFILE%\.cloudflared\config.yml
```

Скрипт обнаруживает такой файл и останавливается до запуска процессов. Если файл относится к
другому туннелю, не удаляйте его. Вручную временно переименуйте, например:

```powershell
Rename-Item "$env:USERPROFILE\.cloudflared\config.yaml" "config.yaml.disabled"
```

После работы с Quick Tunnel верните имя, если конфигурация нужна другому сервису:

```powershell
Rename-Item "$env:USERPROFILE\.cloudflared\config.yaml.disabled" "config.yaml"
```

Перед переименованием убедитесь, какой сервис использует файл.

## Корректная остановка

```powershell
cd C:\Kanban\repository
.\scripts\stop-kanban.ps1
```

Скрипт читает PID-файл, проверяет command line процесса и только после этого останавливает его.
Если PID уже был переиспользован чужим процессом, остановка не выполняется и показывается
ошибка. Не заменяйте этот механизм массовым завершением всех процессов Python или
cloudflared.
