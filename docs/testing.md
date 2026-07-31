# Тестирование Kanban Board 1.2.0

## Автоматические backend-тесты

```powershell
cd D:\Kanban\repository\backend
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m ruff check app scripts tests
.\.venv\Scripts\python.exe -m ruff format --check app scripts tests
.\.venv\Scripts\python.exe -m alembic check
.\.venv\Scripts\python.exe -m pytest
```

Релиз содержит 23 тест. В том числе проверяются:

- каталог активных пользователей;
- назначение и снятие ответственного;
- завершение и повторная активация карточки;
- создание, редактирование и soft-delete комментариев;
- запрет изменения чужого комментария;
- создание, выполнение, перестановка и удаление пунктов чек-листа;
- счётчики в card detail и board snapshot;
- существующие WIP, ordering, archive, auth и concurrency сценарии.

Тесты используют отдельную базу и не должны обращаться к рабочему
`D:\Kanban\data\kanban.db`.

## Проверка миграций на чистой базе

```powershell
cd D:\Kanban\repository\backend
$env:APP_ENV = "test"
$env:DATABASE_URL = "sqlite:///./migration-check.db"
$env:LOG_DIR = "./migration-check-logs"
$env:JWT_SECRET = "local-test-secret-with-more-than-thirty-two-characters"

.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic check
```

Удалите тестовую базу после проверки.

## Frontend-тесты

Нужен Node.js LTS:

```powershell
cd D:\Kanban\repository
npm --prefix frontend test
Get-ChildItem frontend\assets\js\*.js | ForEach-Object { node --check $_.FullName }
```

Релиз содержит 16 тестов. Они проверяют token flow, runtime config, фильтрацию, overdue,
адаптивную панель карточки, отсутствие счётчиков на карточках списка досок и локальное
сворачивание колонок.

## Проверка API

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health | Format-List
Invoke-RestMethod http://127.0.0.1:8000/api/v1/ready | Format-List
```

В `ready` должны присутствовать:

```text
appVersion      : 1.2.0
alembicRevision : 20260730_0002
```

## Ручной приёмочный сценарий

Используйте две учётные записи и два браузера.

1. Пользователь A создаёт доску и три колонки.
2. Пользователь B видит доску после polling.
3. A создаёт карточку и назначает B ответственным.
4. На карточке доски появляются инициалы B.
5. B открывает карточку в боковой панели и отмечает её завершённой.
6. A видит приглушённую карточку после обновления snapshot.
7. A добавляет три пункта чек-листа; B выполняет один и меняет порядок.
8. На доске отображается прогресс `1/3`.
9. A и B добавляют комментарии.
10. B пытается изменить комментарий A и получает запрет; свой комментарий изменяет успешно.
11. Удалённый комментарий исчезает, а `comment_count` уменьшается.
12. Проверьте фильтры «Только мои», «С комментариями», «С чек-листом» и «Завершённые».
13. Сверните две колонки, обновите страницу и подтвердите сохранение состояния только в этом
    браузере.
14. Откройте доску на телефоне: карточка должна открыться полноэкранно, без горизонтального
    переполнения формы.
15. Одновременно измените одну карточку в двух окнах: устаревшая версия должна получить `409`
    и обновить данные.
16. Проверьте WIP-limit, архив и restore старых функций.
17. Остановите backend: frontend показывает переподключение.
18. Запустите сервер: после публикации нового runtime URL вкладка восстанавливает связь.

## Нагрузочный сценарий

```powershell
cd D:\Kanban\repository\backend
.\.venv\Scripts\python.exe -m scripts.load_test --help
```

Сценарий ориентирован примерно на 30 клиентов и 5 одновременно пишущих пользователей. Не
запускайте его на рабочей доске и через публичный tunnel без согласования с командой.
