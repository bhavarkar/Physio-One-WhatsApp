-- ==============================================================================
-- Physio One WhatsApp AI Platform — Host PostgreSQL Verification Probe
-- Verifies pgvector 0.6.0 functionality, HNSW index support, and role safety
-- Usage: sudo -u postgres psql -d physio_db -f verify_host_postgres.sql
-- ==============================================================================

\set ON_ERROR_STOP on

\echo '=== 1. Checking Extension Status ==='
SELECT extname, extversion 
FROM pg_extension 
WHERE extname IN ('vector', 'btree_gist', 'plpgsql');

\echo '=== 2. Checking Role Least-Privilege Invariant ==='
SELECT 
    rolname, 
    rolsuper AS is_superuser, 
    rolcreatedb AS can_create_db, 
    rolcanlogin AS can_login 
FROM pg_roles 
WHERE rolname = 'physio_user';

\echo '=== 3. Checking Database & Schema Ownership ==='
SELECT 
    datname, 
    pg_catalog.pg_get_userbyid(datdba) AS owner 
FROM pg_database 
WHERE datname = 'physio_db';

SELECT 
    schema_name, 
    schema_owner 
FROM information_schema.schemata 
WHERE schema_name = 'public';

\echo '=== 4. Testing 1536-Dimension Vector & HNSW Index Creation ==='
CREATE TEMPORARY TABLE test_vector_probe (
    id serial PRIMARY KEY,
    embedding vector(1536)
);

-- Test HNSW Cosine Index Creation (Matching Alembic 001/004 specification)
CREATE INDEX idx_test_vector_probe_hnsw ON test_vector_probe USING hnsw (embedding vector_cosine_ops);

\echo '>>> PASS: HNSW Cosine Index with 1536 dimensions created successfully on pgvector.'
DROP TABLE test_vector_probe;

\echo '=== 5. Current Table Count in physio_db ==='
SELECT count(*) AS total_public_tables 
FROM information_schema.tables 
WHERE table_schema = 'public';
