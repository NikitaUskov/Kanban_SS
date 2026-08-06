# Backup и восстановление Kanban Board 1.3.0

## Создание

```powershell
cd D:\Kanban\repository
.\scripts\backup-kanban.ps1
```

Python backup использует SQLite backup API, затем выполняет integrity check, проверяет Alembic revision и количество строк в ключевых таблицах, включая приглашения, memberships и уведомления.

## Автоматический backup

```powershell
.\scripts\register-autostart.ps1
```

Задача Windows создаёт ежедневные копии в `D:\Kanban\backups`. Retention задаётся скриптом backup.

## Восстановление

1. Остановите backend и tunnel.
2. Сохраните отдельную копию текущей базы.
3. Запустите restore.
4. Примените миграции.
5. Проверьте readiness.

```powershell
.\scripts\stop-kanban.ps1
Copy-Item D:\Kanban\data\kanban.db D:\Kanban\data\kanban-before-restore.db
.\scripts\restore-kanban.ps1 -BackupPath "D:\Kanban\backups\kanban_<date>.db"

cd backend
.\.venv\Scripts\python.exe -m alembic upgrade head
cd ..
.\scripts\start-kanban-server.ps1
```

Нельзя копировать работающий SQLite-файл обычным `Copy-Item` как единственный backup: используйте штатный backup-скрипт.
