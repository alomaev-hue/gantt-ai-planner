#!/bin/sh
# Runs once by the postgres entrypoint on a brand-new (empty) data volume.
# Creates the two application roles and the 'planner' database, and sets
# default privileges so that tables created later by planner_owner (via
# 'alembic upgrade head' in the migrate service) are automatically usable
# by planner_app without further grants.
set -eu

APP_PW_FILE=/run/secrets/db_app_password
OWNER_PW_FILE=/run/secrets/db_owner_password

if [ ! -r "$APP_PW_FILE" ] || [ ! -r "$OWNER_PW_FILE" ]; then
    echo "10-roles.sh: missing db_app_password/db_owner_password secret files, aborting" >&2
    exit 1
fi

APP_PW="$(cat "$APP_PW_FILE")"
OWNER_PW="$(cat "$OWNER_PW_FILE")"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" <<-EOSQL
    CREATE ROLE planner_owner LOGIN PASSWORD '${OWNER_PW}';
    CREATE ROLE planner_app LOGIN PASSWORD '${APP_PW}' CONNECTION LIMIT 15;

    ALTER ROLE planner_app SET statement_timeout = '15s';
    ALTER ROLE planner_app SET idle_in_transaction_session_timeout = '30s';
    ALTER ROLE planner_app SET lock_timeout = '5s';

    CREATE DATABASE planner OWNER planner_owner;
EOSQL

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname planner <<-EOSQL
    REVOKE CREATE ON SCHEMA public FROM PUBLIC;
    GRANT USAGE, CREATE ON SCHEMA public TO planner_owner;

    GRANT CONNECT ON DATABASE planner TO planner_app;
    GRANT USAGE ON SCHEMA public TO planner_app;

    -- planner_app gets DML only, never DDL. These defaults apply to
    -- objects planner_owner creates from now on (e.g. via migrations),
    -- not to anything that already exists at this point (nothing does,
    -- this runs on an empty volume before the first migration).
    ALTER DEFAULT PRIVILEGES FOR ROLE planner_owner IN SCHEMA public
        GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO planner_app;
    ALTER DEFAULT PRIVILEGES FOR ROLE planner_owner IN SCHEMA public
        GRANT USAGE, SELECT ON SEQUENCES TO planner_app;
EOSQL

echo "10-roles.sh: created planner_owner, planner_app and database 'planner'"
