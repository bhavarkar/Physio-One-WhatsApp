-- ==============================================================================
-- Physio One WhatsApp AI Platform — Host PostgreSQL Verification Probe
-- Verifies pgvector 0.6.0 functionality and HNSW index support
-- Usage: sudo -u postgres psql -d physio_db -f verify_host_postgres.sql
-- ==============================================================================

\set ON_ERROR_STOP on

\echo '=== 1. Checking Extension Status ==='
SELECT extname, extversion 
FROM pg_extension 
WHERE extname IN ('vector', 'btree_gist');

\echo '=== 2. Testing 1536-Dimension Vector Operations ==='
CREATE TEMPORARY TABLE test_vector_probe (
    id serial PRIMARY KEY,
    embedding vector(1536)
);

-- Test HNSW Cosine Index Creation (Matching Alembic 001/004 specification)
CREATE INDEX idx_test_vector_probe_hnsw ON test_vector_probe USING hnsw (embedding vector_cosine_ops);

\echo '=== 3. HNSW Index Created Successfully on Host pgvector 0.6.0 ==='
DROP TABLE test_vector_probe;

\echo '=== 4. Checking Table Count in physio_db ==='
SELECT count(*) AS total_public_tables 
FROM information_schema.tables 
WHERE table_schema = 'public';
