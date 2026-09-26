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
   - сделать пакет `ghcr.io/alomaev-hue/gantt-ai-planner` публичным —
     **один раз**, иначе `docker compose pull` на сервере (без залогина в
     GHCR) не сможет скачать образ: GitHub → профиль/организация →
     Packages → `gantt-ai-planner` → Package settings → Change
     visibility → Public;
   - вписать реальный ключ LLM — по умолчанию (`LLM_PROVIDER=openrouter`,
     который bootstrap уже прописал в `/opt/gantt-planner/.env`) это ключ
     OpenRouter (`sk-or-v1-...`) в
     `/opt/gantt-planner/secrets/openrouter_api_key`; если вместо этого
     нужен настоящий ключ Anthropic — `secrets/anthropic_api_key` и
     `LLM_PROVIDER=anthropic` в `.env` (без переноса строки в конце и не
     через аргумент команды — см. «Ключ OpenRouter» / «Ключ Anthropic» и
     «Переключение провайдера LLM» в разделе 3).
     Пока владелец не заполнил нужный файл (bootstrap создаёт оба
     пустыми), приложение работает в демо-режиме без LLM — `make_llm()`
     видит пустой ключ, логирует это (без содержимого ключа) и отдаёт
     `FakeLLM` вместо `AnthropicLLM`, само приложение при этом не падает;
     текущий режим виден в ответе `GET /api/meta` (`llm_mode`) и
     значком в UI;
   - настроить GitHub Environment `production` (Settings → Environments →
     `production`) — **обязательно до первого мёржа в `main`**, это
     внешняя настройка, в репозитории её не видно:
     - **Required reviewers** — владелец репозитория: каждый деплой ждёт
       ручного подтверждения;
     - **Deployment branches and tags** → Selected branches → `main`.
     `deploy.yml` сам проверяет, что запуск пришёл из `push` в `main` этого
     репозитория (а не из PR форка с веткой `main`) или что
     `workflow_dispatch` запущен на `main`; настройки окружения — второй
     рубеж на случай ошибки в этом условии. Секреты `DEPLOY_SSH_KEY` и
     `DEPLOY_KNOWN_HOSTS` хранить только в этом окружении, не в секретах
     репозитория;
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
CI на push в `main` GitHub Actions собирает образ, сканирует его Trivy
(падает на CRITICAL) и только после этого публикует в GHCR под тегами
`sha-<short>` и `latest` (публикуется ровно просканированный образ, без
пересборки), затем по SSH выполняет:

```bash
ssh -i <deploy-key> deploy@<host> sha-<short>
```

Forced command `planner-deploy-wrapper` проверяет, что пришёл ровно один
токен формата `^sha-[0-9a-f]{7,40}$`, и вызывает
`sudo /usr/local/bin/planner-deploy sha-<short>`. Дальше `planner-deploy`:

1. запоминает текущий `IMAGE_TAG` из `.env`;
2. `IMAGE_TAG=<новый> docker compose pull app migrate` — тег передаётся
   только через окружение; если образа нет или сеть упала, скрипт
   выходит с кодом 1, **не трогая** `.env` и работающий стек;
3. только после успешного pull пишет новый тег в `.env` и делает
   `docker compose up -d` (это прогоняет `migrate` — `alembic upgrade
   head` от `planner_owner` — и перезапускает `app` на новом образе);
4. до 60 секунд опрашивает `/healthz` изнутри контейнера `app`
   (`docker compose exec app python -c ...`);
5. если здоров — выходит с кодом 0;
6. при **любой** ошибке после записи `.env` (упал `up -d`, например
   `migrate` вышел с ошибкой; не прошёл healthcheck; скрипт прерван) —
   ловушка `EXIT` возвращает в `.env` предыдущий тег, переподнимает стек
   (`up -d`) и выходит с кодом 1 (CI увидит деплой как упавший). Так
   `.env` никогда не остаётся с тегом, который не задеплоился.
   Поведение покрыто `bash deploy/tests/test_planner_deploy.sh`
   (docker заглушён).

Ограничение: автооткат рассчитан на релизы без новых миграций. Если новая
версия успела применить миграцию, `migrate` старого образа не узнает
новую ревизию и завершится с ошибкой, так что `up -d` при откате тоже
упадёт (скрипт напишет «manual intervention needed»). Тогда — чинить
вперёд новым тегом или `alembic downgrade` новым образом, при
необходимости восстановить из бэкапа (раздел 4).

После успешного деплоя CD дополнительно проверяет
`https://gantt-ai-planner.duckdns.org/healthz` снаружи.

### Ручной деплой конкретного тега (без CI)

Отдельного `scripts/deploy-manual.sh`, который упоминает спецификация
(§14), нет: его роль выполняют команды этого раздела и первого деплоя
(§1, п. 4) — `planner-deploy` уже делает pull, запуск, healthcheck и
откат.

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
# Ключ вводится без эха и не попадает ни в историю shell, ни в аргументы команд.
read -rs -p 'Новый ключ Anthropic: ' key && printf '%s' "$key" > /opt/gantt-planner/secrets/anthropic_api_key; unset key
cd /opt/gantt-planner && docker compose -f compose.prod.yml up -d --force-recreate app
```
Старый ключ отозвать в консоли Anthropic после подтверждения, что новый
работает.

### Ключ OpenRouter

По умолчанию (`LLM_PROVIDER=openrouter`) приложение использует именно этот
секрет. Тот же принцип, что и для Anthropic (ключ не должен попасть ни в
историю shell, ни в аргументы команд, ни на экран) — здесь как
альтернативный вариант через `install` и `/dev/stdin`, без переменной
окружения и без `read`:

```bash
cd /opt/gantt-planner
install -m 0444 -o root -g root /dev/stdin secrets/openrouter_api_key
# Вставить ключ (sk-or-v1-...) одной строкой без завершающего перевода
# строки и нажать Ctrl+D (EOF). Ctrl+C прервёт без изменения файла.
docker compose -f compose.prod.yml up -d --force-recreate app
```
Старый ключ отозвать в личном кабинете OpenRouter после подтверждения, что
новый работает. Тот же приём (`install -m 0444 -o root -g root /dev/stdin
<файл>` + вставка + Ctrl+D) годится и для `secrets/anthropic_api_key`
вместо `read -rs` выше — оба способа не оставляют ключ в истории shell.

### Переключение провайдера LLM

Провайдер и модель заданы в `/opt/gantt-planner/.env` (`LLM_PROVIDER`,
`LLM_MODEL`; читает их `compose.prod.yml` через `${LLM_PROVIDER:-openrouter}`
/ `${LLM_MODEL:-anthropic/claude-sonnet-5}` — bootstrap прописывает эти
значения по умолчанию при первом создании файла и не трогает `.env`, если
он уже существует). Чтобы переключиться:

```bash
cd /opt/gantt-planner
# Anthropic -> OpenRouter (или наоборот) — отредактировать .env,
# например через sed, задав нужные значения:
sed -i \
  -e 's/^LLM_PROVIDER=.*/LLM_PROVIDER=openrouter/' \
  -e 's/^LLM_MODEL=.*/LLM_MODEL=anthropic\/claude-sonnet-5/' \
  .env
docker compose -f compose.prod.yml up -d --force-recreate app
```
Убедиться, что соответствующий секрет (`secrets/openrouter_api_key` или
`secrets/anthropic_api_key`) уже заполнен — иначе приложение молча уйдёт в
демо-режим (см. раздел 1, п. 3). Текущий провайдер и модель видны в
`GET /api/meta` (`llm_mode`, `model`) сразу после переключения.

Отдельно поддержан и автоопределение: если в `secrets/anthropic_api_key`
случайно оказался ключ OpenRouter (начинается с `sk-or-`) при
`LLM_PROVIDER=anthropic`, приложение всё равно пойдёт через OpenRouter и
один раз залогирует предупреждение (без содержимого ключа) — специально
переключать `.env` в этом случае не обязательно, но лучше всё же явно
выставить `LLM_PROVIDER=openrouter`, чтобы не полагаться на автоопределение.

### Пароли БД (`db_app_password`, `db_owner_password`, `pg_superuser_password`)

Файл секрета — это то, что подставляется при следующем старте
контейнера; сам пароль в Postgres нужно поменять отдельно командой
`ALTER ROLE`, иначе роль и файл разойдутся.

Новый пароль нигде не должен оказаться в открытом виде: ни в аргументах
команд (их видно в `ps`), ни в истории shell, ни в логе Postgres. Поэтому
он сразу пишется в файл, а в `psql` попадает только через stdin:

```bash
cd /opt/gantt-planner

# Пример для planner_app; для planner_owner — аналогично, с его ролью/файлом.
( umask 077 && openssl rand -base64 32 | tr -d '\n' > secrets/db_app_password.new )

# printf — встроенная команда bash (не отдельный процесс), так что пароль
# идёт только через pipe; SET выключает запись текста запроса в лог
# сервера, если ALTER вдруг упадёт. В base64 нет кавычек.
{
  echo "SET log_min_error_statement = panic;"
  printf "ALTER ROLE planner_app PASSWORD '%s';\n" "$(cat secrets/db_app_password.new)"
} | docker compose -f compose.prod.yml exec -T db psql -U postgres -v ON_ERROR_STOP=1 -q

mv secrets/db_app_password.new secrets/db_app_password
chmod 0444 secrets/db_app_password

docker compose -f compose.prod.yml up -d --force-recreate app
```

Если ALTER упал, `.new`-файл остаётся, а рабочий пароль не меняется —
разобраться с ошибкой и повторить.

Для `pg_superuser_password` (переменная `POSTGRES_PASSWORD_FILE`) — то же
самое с `ALTER ROLE postgres` и файлом `secrets/pg_superuser_password`,
затем перезапустить `db` (это вызовет короткий даунтайм — сделать вне
пиковых часов).

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

1. **Ключ LLM (Anthropic или OpenRouter, смотря какой активен —
   `GET /api/meta`)**: отключить ключ в консоли соответствующего сервиса
   (лимит расходов на нуле или удаление ключа), сгенерировать новый,
   положить по процедуре из раздела 3.
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
   планов — в куке `__Host-sid` лежит случайный непрозрачный токен
   (256 бит), а в БД хранится только его sha256 (`sessions.token_hash`),
   так что дамп БД сам по себе не даёт войти в чужую сессию.
   Инвалидировать сессии можно, удалив строки из таблицы `sessions`
   через `psql` в контейнере `db` (каскадно удалятся версии планов, чат
   и MCP-токены).
6. Зафиксировать инцидент: что произошло, что отозвано и когда, что
   проверено после — как дополнение к этому разделу или в отдельном
   issue.
7. Только после того, как все новые секреты на месте и стек передеплоен
   — считать инцидент закрытым.
