# Обновление приложения

Обновляйте только на конкретный проверенный Git tag, например `v1.1.0`. Не запускайте
обновление по названию ветки и не подменяйте tag вручную.

## Предварительные условия

- tag находится в том же `origin`, который показывает `git remote -v`;
- целевой tag является прямым fast-forward продолжением текущего commit;
- оба runtime-процесса могут быть кратковременно остановлены;
- `C:\Kanban\backups` доступен для записи;
- рабочее Git-дерево чистое;
- для новой версии прочитаны release notes и инструкция миграции.

Проверка:

```powershell
cd C:\Kanban\repository
git status --short
git branch --show-current
git remote -v
git fetch origin --tags --prune
git tag --list "v*"
```

`git status --short` не должен ничего вывести, ветка должна быть `main`.

## Запуск обновления

```powershell
cd C:\Kanban\repository
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\update-kanban.ps1 -VersionTag "v1.1.0"
```

Скрипт:

1. проверяет чистоту Git и ветку `main`;
2. получает tags и проверяет существование выбранного;
3. убеждается, что обновление fast-forward;
4. создаёт проверенный backup;
5. останавливает backend и cloudflared;
6. выполняет `git merge --ff-only <tag>`;
7. обновляет Python-зависимости;
8. применяет Alembic migrations;
9. запускает backend и новый Quick Tunnel;
10. публикует runtime config;
11. проверяет `/api/v1/ready`.

Для запуска без открытия браузера:

```powershell
.\scripts\update-kanban.ps1 -VersionTag "v1.1.0" -NoBrowser
```

## Проверка после обновления

```powershell
Get-Content C:\Kanban\repository\VERSION
git -C C:\Kanban\repository log -5 --oneline
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health | Format-List
Invoke-RestMethod http://127.0.0.1:8000/api/v1/ready | Format-List
```

Затем откройте постоянный Pages URL, проверьте версии в разделе «О системе», вход, одну доску,
создание/перемещение тестовой карточки и журнал действий.

## Если обновление прервано

Скрипт выводит:

- предыдущий Git commit;
- целевой commit;
- путь к backup;
- команды ручного восстановления.

Не повторяйте обновление до выяснения этапа ошибки. Сохраните вывод и проверьте:

```powershell
git status --short
git log -5 --oneline
Get-ChildItem C:\Kanban\backups -Filter "kanban_*.db" |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 5 Name,Length,LastWriteTime
Get-Content C:\Kanban\logs\backend-stderr.log -Tail 200
```

Если код уже обновлён, но backend не стартует, сначала проверьте зависимости и Alembic
revision. Если migration изменила базу и release notes требуют возврат данных, восстановите
точно выбранную предобновленческую копию через `restore-kanban.ps1`.

Автоматический откат кода не выполняется: это защищает локальные runtime commits и
пользовательские изменения от перезаписи.
