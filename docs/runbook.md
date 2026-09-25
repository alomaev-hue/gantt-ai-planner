# Runbook: эксплуатация Gantt AI Planner в продакшене

Этот документ описывает операции с продакшен-стендом на VPS: первичную
настройку сервера, регулярный деплой и откат, ротацию секретов, проверку
восстановления из бэкапа и чек-лист на случай инцидента.

Сервер общий с другими сервисами — ничего из описанного здесь не должно
затрагивать их порты, сети или конфигурацию. Скрипты в `deploy/` тоже
этого не делают: `deploy/bootstrap.sh` работает только с пользователем
`deploy`, каталогами `/opt/gantt-planner`, `/opt/caddy`, сетью Docker
`edge` и cron-задачей бэкапа.

## Обзор стенда

- `/opt/gantt-planner` — стек приложения (compose-проект `gantt-planner`):
  `compose.prod.yml`, `.env` (только `IMAGE_TAG`), `secrets/` (0700,
  файлы 0444), `initdb/10-roles.sh`.
- `/var/lib/gantt-planner/pg` — данные Postgres (bind-mount).
- `/var/backups/gantt-planner` — дампы `pg_dump`, хранятся 7 дней.
- `/opt/caddy` — общий reverse proxy (Caddy 2) в сети `edge`, обслуживает
  `gantt-ai-planner.duckdns.org` вместе с другими сайтами на этом хосте.
- Образ приложения: `ghcr.io/alomaev-hue/gantt-ai-planner`, теги
  `sha-<короткий-sha>` и `latest`.

## 1. Первичная настройка сервера

Выполняется один раз, вручную, от root.

1. Скопировать репозиторий (или только каталог `deploy/`) на сервер.
2. Запустить `sudo bash deploy/bootstrap.sh`. Скрипт идемпотентен, каждый
   шаг печатает, что делает:
   - создаёт системного пользователя `deploy` (без группы `docker`);
   - устанавливает `/usr/local/bin/planner-deploy`,
     `/usr/local/bin/planner-deploy-wrapper`,
     `/usr/local/bin/gantt-planner-backup.sh`;
   - устанавливает правило sudoers `/etc/sudoers.d/gantt-planner-deploy`
     (провалидировано `visudo -cf` перед установкой);
   - создаёт каталоги `/opt/gantt-planner`, `/opt/gantt-planner/secrets`
     (0700, root), `/var/lib/gantt-planner/pg` (владелец uid:gid 70:70,
     как у postgres в образе `postgres:17-alpine`), `/var/backups/gantt-planner`,
     `/opt/caddy`;
   - копирует `compose.prod.yml`, `initdb/10-roles.sh`, конфиг Caddy;
   - генерирует `db_app_password`, `db_owner_password`,
     `pg_superuser_password` через `openssl rand -base64 32` — **только
     если файлов ещё нет**, существующие пароли не трогает;
   - создаёт пустой файл-заглушку `secrets/anthropic_api_key`, если его
     нет;
   - создаёт сеть Docker `edge`, если её нет;
   - поднимает стек Caddy (`docker compose up -d` в `/opt/caddy`);
   - устанавливает cron `/etc/cron.d/gantt-planner-backup` (03:15 каждый
     день).
3. После bootstrap вручную:
   - вписать реальный ключ Anthropic в
     `/opt/gantt-planner/secrets/anthropic_api_key` (без переноса строки
     в конце — как отдаёт провайдер, `printf '%s' '<key>' > .../anthropic_api_key`);
   - добавить публичный deploy-ключ CI в
     `/home/deploy/.ssh/authorized_keys` строкой вида:
     ```
     restrict,command="/usr/local/bin/planner-deploy-wrapper" ssh-ed25519 AAAA... gha-gantt-planner
     ```
   - попросить владельца VPS создать A-запись DuckDNS
     `gantt-ai-planner.duckdns.org` → IP сервера (токен DuckDNS на
     сервере не нужен, поддомен создаёт владелец);
   - убедиться, что порты 80/443 доступны из интернета (это единственная
     проверка сетевого доступа, которая нужна при первом деплое).
4. Первый деплой — вручную, без CD:
   ```bash
   cd /opt/gantt-planner
   echo "IMAGE_TAG=sha-<commit>" > .env   # публичный тег из ghcr.io
   docker compose -f compose.prod.yml pull
   docker compose -f compose.prod.yml up -d
   docker compose -f compose.prod.yml logs -f migrate app
   ```
   Проверить `https://gantt-ai-planner.duckdns.org/healthz` — должен
   отвечать `200`.

## 2. Регулярный деплой

Обычный путь — через CD (`.github/workflows/deploy.yml`): после зелёного
CI на `main` GitHub Actions собирает образ, публикует его в GHCR под
тегами `sha-<short>` и `latest`, прогоняет Trivy (падает на CRITICAL) и
по SSH выполняет:

```bash
ssh -i <deploy-key> deploy@<host> sha-<short>
```

Forced command `planner-deploy-wrapper` проверяет, что пришёл ровно один
токен формата `^sha-[0-9a-f]{7,40}$`, и вызывает
`sudo /usr/local/bin/planner-deploy sha-<short>`. Дальше `planner-deploy`:

1. запоминает текущий `IMAGE_TAG` из `.env`;
2. пишет новый тег в `.env`;
3. `docker compose pull app migrate && docker compose up -d`
   (это прогоняет `migrate` — `alembic upgrade head` от `planner_owner`
   — и перезапускает `app` на новом образе);
4. до 60 секунд опрашивает `/healthz` изнутри контейнера `app`
   (`docker compose exec app python -c ...`);
5. если здоров — выходит с кодом 0;
6. если не здоров — возвращает `IMAGE_TAG` на предыдущее значение,
   переподнимает стек (`up -d`) и выходит с кодом 1 (CI увидит деплой как
   упавший).

После успешного деплоя CD дополнительно проверяет
`https://gantt-ai-planner.duckdns.org/healthz` снаружи.

### Ручной деплой конкретного тега (без CI)

```bash
ssh -i <deploy-key> deploy@<host> sha-<short>
```

Или прямо на сервере от root (в обход wrapper'а, например для
диагностики):

```bash
sudo /usr/local/bin/planner-deploy sha-<short>
```

### Откат

Откат — это обычный деплой предыдущего тега:

```bash
ssh -i <deploy-key> deploy@<host> sha-<предыдущий-short>
```

Короткий тег предыдущего успешного деплоя можно взять:
- из истории запусков workflow `Deploy` в GitHub Actions;
- из `/opt/gantt-planner/.env` — `planner-deploy` перед каждым деплоем
  печатает в лог `previous: '<tag>'`, это видно в journalctl/логах sshd
  или можно посмотреть теги образов в GHCR по времени публикации.

`planner-deploy` откатывается автоматически при неуспешном healthcheck,
описанный выше ручной откат нужен, если проблема обнаружилась позже
(например, в логах или у пользователей), а не сразу при деплое.

## 3. Ротация секретов

При любой ротации: сначала положить новое значение, затем перезапустить
только те контейнеры, которым оно нужно (secrets в Compose читаются при
старте контейнера, hot reload не поддерживается).

### Ключ Anthropic

```bash
printf '%s' '<новый-ключ>' > /opt/gantt-planner/secrets/anthropic_api_key
cd /opt/gantt-planner && docker compose -f compose.prod.yml up -d --force-recreate app
```
Старый ключ отозвать в консоли Anthropic после подтверждения, что новый
работает.

### Пароли БД (`db_app_password`, `db_owner_password`, `pg_superuser_password`)

Файл секрета — это то, что подставляется при следующем старте
контейнера; сам пароль в Postgres нужно поменять отдельно командой
`ALTER ROLE`, иначе роль и файл разойдутся.

```bash
cd /opt/gantt-planner
new_pw="$(openssl rand -base64 32)"

# Пример для planner_app; для planner_owner и суперпользователя —
# аналогично, с соответствующей ролью/файлом.
docker compose -f compose.prod.yml exec -T db psql -U postgres -c \
  "ALTER ROLE planner_app PASSWORD '${new_pw}';"

printf '%s' "$new_pw" > secrets/db_app_password
chmod 0444 secrets/db_app_password

docker compose -f compose.prod.yml up -d --force-recreate app
```

Для `pg_superuser_password` (переменная `POSTGRES_PASSWORD_FILE`) вместо
`ALTER ROLE` от `postgres` нужно выполнить `ALTER ROLE postgres
PASSWORD ...` тем же способом, затем пересоздать секрет-файл и
перезапустить `db` (это вызовет короткий даунтайм — сделать вне пиковых
часов).

Ключевой момент: **никогда не менять только файл секрета** — контейнер
Postgres создаёт роли один раз, при первом старте на пустом томе;
изменение файла без `ALTER ROLE` в уже существующей базе ничего не даст.

### Deploy-ключ (SSH)

1. Сгенерировать новую пару ключей (`ssh-keygen -t ed25519 -C
   gha-gantt-planner`).
2. Добавить новую публичную часть в
   `/home/deploy/.ssh/authorized_keys` (со `restrict,command="..."`),
   старую строку не удалять пока не убедились, что новая работает.
3. Обновить секрет `DEPLOY_SSH_KEY` (приватный ключ) в GitHub Environment
   `production`.
4. Прогнать `Deploy` через `workflow_dispatch`, убедиться, что деплой
   прошёл.
5. Удалить старую строку из `authorized_keys`.

## 4. Проверка восстановления из бэкапа

Бэкап делает `deploy/backup.sh` каждую ночь в 03:15
(`/etc/cron.d/gantt-planner-backup`): `pg_dump -Fc` от `planner_owner` в
`/var/backups/gantt-planner/<дата>.dump`, дампы старше 7 дней удаляются.

Восстановление проверяется руками, в отдельную (scratch) базу, **не** в
`planner` — чтобы не задеть продакшен-данные:

```bash
cd /opt/gantt-planner

# 1. создать временную базу и роль-владельца в том же контейнере db
docker compose -f compose.prod.yml exec -T db psql -U postgres -c \
  "CREATE DATABASE planner_restore_test OWNER planner_owner;"

# 2. восстановить последний дамп в неё
latest_dump="$(ls -1t /var/backups/gantt-planner/*.dump | head -n1)"
docker compose -f compose.prod.yml exec -T db pg_restore \
  -U planner_owner -d planner_restore_test --no-owner < "$latest_dump"

# 3. проверить, что данные на месте (пример)
docker compose -f compose.prod.yml exec -T db psql -U planner_owner \
  -d planner_restore_test -c "SELECT count(*) FROM plan_versions;"

# 4. убрать за собой
docker compose -f compose.prod.yml exec -T db psql -U postgres -c \
  "DROP DATABASE planner_restore_test;"
```

Дата и результат последней проверки восстановления фиксируются здесь:

| Дата | Кто проверял | Результат |
|---|---|---|
| _(заполнить после первой проверки)_ | | |

## 5. Чек-лист при инциденте (компрометация секрета/сервера)

Если есть подозрение, что скомпрометирован ключ Anthropic, пароль БД,
deploy-ключ или сам сервер — отзываем всё сразу, не по одному:

1. **Anthropic**: отключить ключ в консоли Anthropic (лимит расходов на
   нуле или удаление ключа), сгенерировать новый, положить по процедуре
   из раздела 3.
2. **Пароли БД**: сменить все три (`planner_app`, `planner_owner`,
   суперпользователь) по процедуре из раздела 3, даже если под
   подозрением только один.
3. **Deploy-ключ**: удалить скомпрометированную строку из
   `/home/deploy/.ssh/authorized_keys` немедленно (это отключает CD),
   затем выпустить новый ключ по процедуре из раздела 3.
4. **GitHub**: проверить `DEPLOY_SSH_KEY`/`DEPLOY_KNOWN_HOSTS` в
   Environment `production`, при необходимости отозвать и пересоздать
   `GITHUB_TOKEN`-зависимые интеграции (пакет в GHCR публичный, но права
   на публикацию идут через сам workflow).
5. **Сессии пользователей**: если есть подозрение на утечку данных
   планов — сессии хранятся в БД (`session_id` в куке — это просто
   ссылка на строку), инвалидировать их можно, удалив соответствующие
   строки из таблицы сессий напрямую через `psql` в контейнере `db`.
6. Зафиксировать инцидент: что произошло, что отозвано и когда, что
   проверено после — как дополнение к этому разделу или в отдельном
   issue.
7. Только после того, как все новые секреты на месте и стек передеплоен
   — считать инцидент закрытым.
