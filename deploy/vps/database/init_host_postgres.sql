-- ==============================================================================
-- Physio One WhatsApp AI Platform — Host PostgreSQL 16 Provisioning Script
-- Target: Hostinger Ubuntu 24.04 LTS (Host PostgreSQL 16 + pgvector 0.6.0)
-- Usage: sudo -u postgres psql -v physio_password="<STRONG_PASSWORD_32_CHARS>" -f init_host_postgres.sql
-- ==============================================================================

\set ON_ERROR_STOP on

-- 1. Ensure password parameter was provided to avoid hardcoded credentials
\if :{?physio_password}
   \echo '>>> Provisioning database with operator-supplied password...'
\else
   \echo '=================================================================='
   \echo ' ERROR: Password variable physio_password is required!'
   \echo ' Usage:'
   \echo '   sudo -u postgres psql -v physio_password="YOUR_PASSWORD" -f init_host_postgres.sql'
   \echo '=================================================================='
   \q
\endif

-- 2. Create or Update Application Role with Least Privilege (NOSUPERUSER)
DO
$do$
BEGIN
   IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'physio_user') THEN
      EXECUTE format(
         'CREATE ROLE physio_user WITH LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION', 
         :'physio_password'
      );
      RAISE NOTICE 'Role physio_user created with NOSUPERUSER privileges.';
   ELSE
      EXECUTE format(
         'ALTER ROLE physio_user WITH LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION', 
         :'physio_password'
      );
      RAISE NOTICE 'Role physio_user password and attributes updated idempotently.';
   END IF;
END
$do$;

-- 3. Create Dedicated Database owned by physio_user
SELECT 'CREATE DATABASE physio_db OWNER physio_user'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'physio_db')\gexec

ALTER DATABASE physio_db OWNER TO physio_user;

-- 4. Connect to physio_db to install superuser extensions and grant schema access
\connect physio_db

-- Extensions MUST be created by superuser (postgres).
-- Once installed, unprivileged physio_user can use vector types and HNSW indexes.
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS btree_gist;

-- Ensure schema public is owned by physio_user for Alembic migrations
GRANT ALL ON SCHEMA public TO physio_user;
ALTER SCHEMA public OWNER TO physio_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO physio_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO physio_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON FUNCTIONS TO physio_user;

-- 5. Verification Output
\echo '=================================================================='
\echo ' PROVISIONING COMPLETE — VERIFYING EXTENSIONS & OWNERSHIP'
\echo '=================================================================='
SELECT 
    extname AS extension_name, 
    extversion AS installed_version 
FROM pg_extension 
WHERE extname IN ('vector', 'btree_gist', 'plpgsql');

SELECT 
    datname AS database_name, 
    pg_catalog.pg_get_userbyid(datdba) AS database_owner 
FROM pg_database 
WHERE datname = 'physio_db';

SELECT 
    rolname AS role_name, 
    rolsuper AS is_superuser, 
    rolcanlogin AS can_login 
FROM pg_roles 
WHERE rolname = 'physio_user';
