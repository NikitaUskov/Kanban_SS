# Резервное копирование и восстановление

## Что сохраняется

Файл SQLite содержит:

- пользователей и хеши паролей;
- refresh-сессии;
- доски, колонки и карточки;
- ответственных, отметки завершения, комментарии и чек-листы;
- архивные объекты;
- журнал действий;
- текущую Alembic revision.

`runtime-config.json`, `.env`, код и логи в backup базы не входят. Для полного аварийного
восстановления отдельно храните:

1. Git-репозиторий с кодом;
2. хотя бы две проверенные копии базы на разных носителях;
3. защищённую копию `backend\.env`.

`.env` содержит JWT secret. Храните его как пароль. Если восстановить базу, но сгенерировать
новый JWT secret, пользователям потребуется войти заново; сами доски не потеряются.

## Создание backup

Backend останавливать не нужно. Используется SQLite Backup API, который создаёт согласованный
снимок работающей WAL-базы.

```powershell
cd D:\Kanban\repository
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\backup-kanban.ps1
```

При успехе будут созданы два файла:

```text
D:\Kanban\backups\kanban_YYYY-MM-DD_HH-mm-ss.db
D:\Kanban\backups\kanban_YYYY-MM-DD_HH-mm-ss.json
```

JSON содержит результат `PRAGMA integrity_check`, Alembic revision, размер и количество
основных записей. Скрипт сообщает об успехе только после проверки:

- `PRAGMA integrity_check = ok`;
- наличия всех обязательных таблиц;
- совпадения Alembic revision с версией приложения.

Показать последние копии:

```powershell
Get-ChildItem D:\Kanban\backups -Filter "kanban_*.db" |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 20 Name,Length,LastWriteTime
```

Прочитать метаданные выбранной копии:

```powershell
Get-Content D:\Kanban\backups\kanban_YYYY-MM-DD_HH-mm-ss.json |
  ConvertFrom-Json |
  Format-List
```

## Политика хранения

Автоматическая очистка затрагивает только копии с корректным соседним `.json`, где
`verified` равно `true`. Хранятся:

- 14 самых новых проверенных копий;
- дополнительно по одной проверенной копии для каждой из 8 последних представленных недель.

Новая копия никогда не удаляется текущим запуском. Файлы, которые скрипт не может подтвердить
по metadata, автоматически не удаляются.

## Ежедневное расписание

После успешной ручной проверки:

```powershell
cd D:\Kanban\repository
.\scripts\register-autostart.ps1
```

Создаётся задача `KanbanBoard-DailyBackup` на 03:00. Проверить последние результаты:

```powershell
Get-ScheduledTaskInfo -TaskName "KanbanBoard-DailyBackup" |
  Select-Object LastRunTime,LastTaskResult,NextRunTime
```

`LastTaskResult = 0` означает успешное завершение. Выполнить задачу вручную:

```powershell
Start-ScheduledTask -TaskName "KanbanBoard-DailyBackup"
Start-Sleep -Seconds 5
Get-ScheduledTaskInfo -TaskName "KanbanBoard-DailyBackup"
```

Затем убедитесь, что появился новый `.db` и соответствующий `.json`.

## Копия на другой носитель

Локальный диск не защищает от поломки компьютера, кражи или шифровальщика. Регулярно
копируйте последние проверенные `.db` и `.json` на другой физический носитель или в
зашифрованное хранилище с историей версий.

Пример копирования выбранной пары на уже подключённый диск `E:`:

```powershell
New-Item E:\KanbanBackups -ItemType Directory -Force
Copy-Item D:\Kanban\backups\kanban_YYYY-MM-DD_HH-mm-ss.db E:\KanbanBackups\
Copy-Item D:\Kanban\backups\kanban_YYYY-MM-DD_HH-mm-ss.json E:\KanbanBackups\
```

Проверьте наличие и размер:

```powershell
Get-Item E:\KanbanBackups\kanban_YYYY-MM-DD_HH-mm-ss.*
```

Backup содержит прикладные данные и должен быть доступен только администратору.

## Восстановление

Восстановление останавливает backend и туннель. Пользователи временно потеряют подключение.
Выберите точный файл `.db`, не metadata `.json`.

```powershell
cd D:\Kanban\repository
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\restore-kanban.ps1 `
  -BackupPath "D:\Kanban\backups\kanban_YYYY-MM-DD_HH-mm-ss.db"
```

Скрипт покажет путь и попросит ввести строго:

```text
ВОССТАНОВИТЬ
```

Затем он:

1. проверит выбранный backup;
2. остановит только процессы Kanban;
3. создаст проверенную аварийную копию текущей рабочей базы в
   `D:\Kanban\backups\emergency`;
4. восстановит выбранную копию сначала во временный файл;
5. ещё раз проверит временную базу;
6. атомарно заменит рабочую базу;
7. запустит сервис, создаст новый tunnel URL и опубликует runtime config;
8. проверит `/api/v1/ready`.

`-Force` убирает текстовое подтверждение и предназначен только для контролируемой
автоматизации. Для ручной операции его не используйте.

Чтобы не открывать браузер после восстановления:

```powershell
.\scripts\restore-kanban.ps1 `
  -BackupPath "D:\Kanban\backups\kanban_YYYY-MM-DD_HH-mm-ss.db" `
  -NoBrowser
```

## Проверка после восстановления

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/ready | Format-List
Get-ChildItem D:\Kanban\backups\emergency |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 5 Name,Length,LastWriteTime
```

В интерфейсе проверьте:

- вход существующим пользователем;
- ожидаемые доски и карточки;
- последние записи журнала;
- создание тестовой карточки;
- отображение изменений во втором браузере.

Удаляйте аварийную копию только после того, как убедились в корректности восстановленной
базы и создали новый обычный backup.

## Восстановление после полной потери компьютера

1. Установите Windows prerequisites по `deployment.md`.
2. Клонируйте нужную версию кода в `D:\Kanban\repository`.
3. Запустите `install-kanban.ps1`: он создаст новую пустую базу и `.env`.
4. Если доступна защищённая копия старого `.env`, остановите сервис и верните её в
   `backend\.env`, проверив пути.
5. Скопируйте проверенный backup в `D:\Kanban\backups`.
6. Выполните `restore-kanban.ps1`.
7. Проверьте ready, вход, данные и Pages runtime config.
8. Если старого `.env` нет, пользователям потребуется новый вход. При необходимости
   выполните `reset-password` для каждой учётной записи.

## Если восстановление завершилось ошибкой

Не копируйте файлы поверх рабочей базы вручную и не удаляйте WAL/SHM во время работающего
backend.

Соберите:

```powershell
Get-Content D:\Kanban\logs\backend-stderr.log -Tail 100
Get-ChildItem D:\Kanban\backups\emergency |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 10 Name,Length,LastWriteTime
Get-ChildItem D:\Kanban\data
```

Если ошибка произошла до атомарной замены, рабочая база остаётся прежней. Если замена прошла,
но повторный старт не удался, сначала диагностируйте старт по `troubleshooting.md`; не
повторяйте восстановление вслепую.
