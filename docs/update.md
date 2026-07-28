# Обновление приложения

## Рекомендуемый способ: origin/main

После успешных GitHub Actions откройте PowerShell на сервере от имени администратора:

```powershell
cd D:\Kanban\repository
.\scripts\update-from-main.ps1 -RunTests -NoBrowser
```

До запуска рабочее дерево должно быть чистым. Скрипт создаёт backup, останавливает сервис,
выполняет fast-forward pull, обновляет зависимости и миграции, запускает тесты и стартует
сервис заново.

## Быстрое обновление без локальных тестов

```powershell
.\scripts\update-from-main.ps1 -NoBrowser
```

Используйте только после зелёного workflow `Tests`.

## Обновление по release tag

Для зафиксированных релизов остаётся скрипт:

```powershell
.\scripts\update-kanban.ps1 -VersionTag "v1.1.0" -NoBrowser
```

Tag должен быть fast-forward продолжением текущего commit.

## Проверка

```powershell
Get-Content .\VERSION
.\scripts\status-kanban.ps1
Invoke-RestMethod http://127.0.0.1:8000/api/v1/ready | Format-List
```
