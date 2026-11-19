-- ==============================================================================
-- Physio One WhatsApp AI Platform — Host PostgreSQL 16 Provisioning Script
-- Target: Hostinger Ubuntu 24.04 LTS (Host PostgreSQL 16 + pgvector 0.6.0)
-- Usage: sudo -u postgres psql -f init_host_postgres.sql
-- ==============================================================================

\set ON_ERROR_STOP on

-- 1. Create Dedicated Application User with Least Privilege
DO
$do$
BEGIN
   IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'physio_user') THEN
      CREATE ROLE physio_user WITH LOGIN PASSWORD 'GENERATE_STRONG_PASSWORD_32_CHARS';
      RAISE NOTICE 'Role physio_user created.';
   ELSE
      RAISE NOTICE 'Role physio_user already exists.';
   END IF;
END
$do$;

-- 2. Create Dedicated Database
SELECT 'CREATE DATABASE physio_db OWNER physio_user'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'physio_db')\gexec

-- 3. Connect to the new database and configure extensions
\connect physio_db

-- Enable pgvector (v0.6.0 on host)
CREATE EXTENSION IF NOT EXISTS vector;

-- Enable btree_gist (required for exclusion constraints / temporal ranges)
CREATE EXTENSION IF NOT EXISTS btree_gist;

-- 4. Schema Permissions & Ownership
GRANT ALL ON SCHEMA public TO physio_user;
ALTER SCHEMA public OWNER TO physio_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO physio_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO physio_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON FUNCTIONS TO physio_user;

-- 5. Output Verification
SELECT 
    extname AS extension_name, 
    extversion AS installed_version 
FROM pg_extension 
WHERE extname IN ('vector', 'btree_gist', 'plpgsql');
