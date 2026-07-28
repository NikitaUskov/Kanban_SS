# Проверка после первого запуска

Этот файл — чек-лист для этапа после фактического развёртывания. Комплект не предполагает,
что тесты уже выполнялись на вашем компьютере.

## Автоматические backend-тесты

```powershell
cd C:\Kanban\repository\backend
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check app scripts tests
```

Тесты используют временную базу и не должны обращаться к `C:\Kanban\data\kanban.db`.

## Frontend-тесты

Нужен Node.js 24:

```powershell
winget install --exact --id OpenJS.NodeJS.LTS --accept-package-agreements --accept-source-agreements
```

После открытия нового PowerShell:

```powershell
node --version
cd C:\Kanban\repository\frontend
npm test
Get-ChildItem .\assets\js\*.js | ForEach-Object { node --check $_.FullName }
```

## Проверка API

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health | Format-List
Invoke-RestMethod http://127.0.0.1:8000/api/v1/ready | Format-List
```

Проверьте также публичный health через точный текущий `trycloudflare.com` URL.

## Ручной приёмочный сценарий

Используйте две разные учётные записи и два браузера.

1. Пользователь A создаёт доску и три колонки.
2. Пользователь B видит доску без ручной перезагрузки.
3. A создаёт карточку со сроком, приоритетом и описанием.
4. B редактирует карточку; A получает обновление через polling.
5. Одновременно откройте редактирование одной карточки в двух окнах и подтвердите, что
   устаревшая запись получает conflict, а интерфейс загружает актуальные данные.
6. Задайте WIP-limit и подтвердите, что лишняя карточка не переносится.
7. Перетащите карточки внутри колонки и между колонками.
8. Проверьте поиск, priority, overdue и due-date фильтры.
9. Архивируйте и восстановите карточку.
10. Убедитесь, что непустую колонку нельзя удалить без обработки карточек.
11. Архивируйте и восстановите доску.
12. Проверьте журнал действий с именами обоих пользователей.
13. Остановите backend: frontend должен показать переподключение, а не потерять интерфейс.
14. Запустите снова: после публикации нового runtime URL вкладка должна восстановить связь.

## Нагрузочный сценарий

Запускайте только на тестовых данных и после ознакомления с параметрами:

```powershell
cd C:\Kanban\repository\backend
.\.venv\Scripts\python.exe -m scripts.load_test --help
```

Он предназначен для проверки поведения MVP примерно при 30 клиентах, а не для генерации
боевой нагрузки через публичный Quick Tunnel.

Подготовьте тестовую доску минимум с двумя колонками без WIP-лимита и 30 тестовых
пользователей `user01`–`user30` с одинаковым временным паролем. Затем выполните локально:

```powershell
.\.venv\Scripts\python.exe -m scripts.load_test `
  --base-url "http://127.0.0.1:8000" `
  --board-id "<uuid-тестовой-доски>" `
  --username-prefix "user" `
  --users 30 `
  --writers 5 `
  --iterations 20
```

Пароль будет запрошен скрытым prompt. Сценарий выполняет revision polling всеми клиентами,
периодические snapshot, а пять клиентов одновременно создают, редактируют и перемещают
карточки. В конце проверяются наличие созданных карточек и плотность позиций. Любой HTTP 500,
включая необработанный `database is locked`, завершает сценарий ошибкой.
