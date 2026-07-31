# Типовые ошибки Kanban Board 1.2.0

## PowerShell показывает `РќРµ...` и ParserError

Windows PowerShell 5.1 неверно читает UTF-8 без BOM. Все `.ps1` релиза сохранены в UTF-8 BOM и
CRLF. Не пересохраняйте их в ANSI или UTF-8 without BOM.

Если файл пришёл из ZIP:

```powershell
Get-ChildItem D:\Kanban\repository\scripts -Recurse -Filter "*.ps1" | Unblock-File
Set-ExecutionPolicy -Scope Process Bypass -Force
```

## Скрипт требует цифровую подпись

Снимите Internet Zone marker командой `Unblock-File` выше. Затем проверьте:

```powershell
Get-ExecutionPolicy -List
```

Если `MachinePolicy` или `UserPolicy` равна `AllSigned`, это политика организации; локальный
`Bypass` может её не переопределить.

## Запуск запрещён из-за незакоммиченных файлов

```powershell
git status --short
```

`.env`, `.venv`, `__pycache__`, `test-logs`, `.idea`, логи и базы должны игнорироваться. Код и
документацию сохраните отдельным commit. Не используйте `git add .` без просмотра списка.

## PID принадлежит другому процессу

Скрипты 1.2 удаляют устаревший PID-файл и не останавливают чужой процесс. Затем выполняется
поиск только по точной командной строке этого backend/tunnel:

```powershell
.\scripts\stop-kanban.ps1
```

Если обновляется очень старая версия, используйте updater 1.2.0: он содержит собственную
безопасную fallback-остановку до копирования новых скриптов.

## `failed to request quick Tunnel` и IPv6 reset

Запускайте:

```powershell
.\scripts\start-kanban-server.ps1
```

Он временно направляет `api.trycloudflare.com` на IPv4 через `hosts`, а затем восстанавливает
исходный файл. IPv6 адаптера не отключается.

Проверка:

```powershell
curl.exe -4 -v -X POST https://api.trycloudflare.com/tunnel -o NUL
curl.exe -6 -v -X POST https://api.trycloudflare.com/tunnel -o NUL
```

## URL выдан, но hostname ещё не разрешается

Скрипт ждёт DNS и очищает отрицательный DNS cache. Посмотрите:

```powershell
Get-Content D:\Kanban\logs\cloudflared-stderr.log -Tail 100
```

Не копируйте URL в runtime-config вручную.

## Git push падает на порту 22

```powershell
git remote -v
git remote set-url origin https://github.com/<owner>/<repository>.git
git push --dry-run origin main
```

Для HTTPS обычно откроется Git Credential Manager.

## Сайт пишет «Сервер недоступен», но public health работает

```powershell
$url = "https://<owner>.github.io/<repository>/runtime-config.json?ts=$([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds())"
$config = Invoke-RestMethod $url
$config | Format-List
Invoke-RestMethod "$($config.apiBaseUrl)/health" | Format-List
```

Проверьте CORS. Origin не включает `/repository` и должен быть в нижнем регистре:

```text
https://<owner-lowercase>.github.io
```

После изменения `.env` обязательно перезапустите backend.

## `Disallowed CORS origin`

```powershell
Select-String D:\Kanban\repository\backend\.env -Pattern "^ALLOWED_ORIGINS="
```

Повторный installer сохраняет secret и базу, но нормализует URL:

```powershell
.\scripts\install-kanban.ps1 `
  -InstallRoot "D:\Kanban" `
  -GitHubOwner "<owner>" `
  -RepositoryName "<repository>"
```

## `/ready` сообщает старую revision

```powershell
cd D:\Kanban\repository\backend
.\.venv\Scripts\python.exe -m alembic current
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic check
```

Для 1.2.0 ожидается `20260730_0002`. Не запускайте backend 1.2 до успешного upgrade.

## После обновления нет ответственных, комментариев или чек-листа

Проверьте revision и наличие таблиц:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/ready | Format-List
```

Очистите cache frontend через `Ctrl+F5`. Проверьте, что GitHub Pages опубликовал новую версию
`frontend/assets/js/card-detail.js`.

## Ответственный не появляется в списке

Список содержит только активных пользователей. Проверьте:

```powershell
cd D:\Kanban\repository\backend
.\.venv\Scripts\python.exe -m scripts.manage_users list
.\.venv\Scripts\python.exe -m scripts.manage_users enable <username>
```

## Нельзя изменить чужой комментарий

Это ожидаемое правило 1.2. Любой пользователь видит комментарий, но изменить или удалить его
может только автор. Администратор может отключить автора, но не редактирует сообщение через UI.

## Browser: `Failed to execute fetch ... Illegal invocation`

Native fetch вызывается через безопасную обёртку. После обновления дождитесь Pages и нажмите
`Ctrl+F5`. Если ошибка сохраняется, проверьте, что опубликован актуальный `config.js`.

## Где смотреть логи

```powershell
Get-Content D:\Kanban\logs\backend-stderr.log -Tail 100
Get-Content D:\Kanban\logs\cloudflared-stderr.log -Tail 100
Get-Content D:\Kanban\logs\kanban-backend.log -Tail 100
.\scripts\status-kanban.ps1
```
