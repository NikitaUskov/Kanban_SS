# Автоматизация Quick Tunnel

## Основной запуск

На сервере используется:

```powershell
.\scripts\start-kanban-server.ps1
```

Скрипт-обёртка временно добавляет IPv4-запись для `api.trycloudflare.com`, вызывает основной
`start-kanban.ps1` и обязательно удаляет запись в `finally`. IPv6 не отключается.

Основной скрипт:

1. проверяет Git, `.env`, `.venv` и cloudflared;
2. очищает устаревшие PID-файлы без остановки чужих процессов;
3. запускает Alembic и один Uvicorn worker;
4. запускает cloudflared с IPv4 edge и HTTP/2;
5. игнорирует служебный URL `api.trycloudflare.com` при разборе вывода;
6. ждёт публикации DNS нового случайного hostname;
7. проверяет публичный health;
8. обновляет `runtime-config.json`;
9. создаёт commit только этого файла;
10. повторяет `git push` до трёх раз;
11. ждёт появления новой `configVersion` на GitHub Pages.

## Почему адрес меняется

Quick Tunnel анонимный и временный. Адрес `*.trycloudflare.com` существует только пока работает
процесс cloudflared. Поэтому GitHub Pages хранит не адрес в JavaScript, а отдельно загружаемый
`runtime-config.json`.

## Если push не удался

Backend и туннель остаются запущенными. Выполните:

```powershell
cd D:\Kanban\repository
git push origin main
```

После успешного push дождитесь `Deploy GitHub Pages`. Перезапускать backend только ради push
не нужно.

## Ограничения

Cloudflare не гарантирует SLA Quick Tunnel и позиционирует его для разработки и тестирования.
Текущие ограничения публикуются здесь:
<https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/trycloudflare/>.
