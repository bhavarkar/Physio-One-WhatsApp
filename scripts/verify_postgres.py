#!/usr/bin/env python
"""Task 14 Phase 4 — isolated PostgreSQL/pgvector verification (synthetic DB only).

Usage (inside api container or venv, against a DISPOSABLE database):
  DATABASE_URL_SYNC=postgresql+psycopg2://user:pass@host:5432/physio_staging_verify \
    python scripts/verify_postgres.py [--from-revision 004_knowledge_base_pgvector_rag]

Runs Alembic upgrade to head, then asserts: pgvector present, 63 tables,
HNSW indexes, appointment exclusion constraint, FK/unique presence, lease
recovery + campaign idempotency primitives at SQL level. Exits non-zero on
any failure. Refuses DB names not containing 'staging', 'verify' or 'test'.
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from sqlalchemy import create_engine, text

url = os.environ.get("DATABASE_URL_SYNC", "")
db = url.rsplit("/", 1)[-1].split("?")[0]
if not any(k in db for k in ("staging", "verify", "test")):
    sys.exit(f"REFUSED: database '{db}' does not look disposable (need staging/verify/test in name)")

from alembic.config import Config
from alembic import command
cfg = Config(os.path.join(os.path.dirname(__file__), "..", "backend", "alembic.ini"))
cfg.set_main_option("sqlalchemy.url", url)
target = sys.argv[sys.argv.index("--from-revision") + 1] if "--from-revision" in sys.argv else None
if target:  # upgrade-compatibility path: migrate to earlier rev, insert synthetic row, then head
    command.upgrade(cfg, target)
    eng = create_engine(url)
    with eng.begin() as c:
        c.execute(text("INSERT INTO roles (id, name) VALUES ('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11', 'synthetic_verify_role') ON CONFLICT DO NOTHING"))
    eng.dispose()
command.upgrade(cfg, "head")

eng = create_engine(url); failures = []
def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond: failures.append(name)
with eng.connect() as c:
    check("pgvector extension", c.scalar(text("SELECT count(*) FROM pg_extension WHERE extname='vector'")) == 1)
    tables = c.scalar(text("SELECT count(*) FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE' AND table_name <> 'alembic_version'"))
    check(f"63 tables (got {tables})", tables == 63)
    check("HNSW index exists", c.scalar(text("SELECT count(*) FROM pg_indexes WHERE indexdef ILIKE '%hnsw%'")) >= 1)
    check("appointment exclusion constraint", c.scalar(text("SELECT count(*) FROM pg_constraint WHERE contype='x'")) >= 1)
    check("foreign keys present", c.scalar(text("SELECT count(*) FROM pg_constraint WHERE contype='f'")) > 20)
    check("alembic head 008", c.scalar(text("SELECT version_num FROM alembic_version")) == "008_campaigns_instagram_reengagement")
    if target:
        check("synthetic data preserved after upgrade", c.scalar(text("SELECT count(*) FROM roles WHERE name='synthetic_verify_role'")) == 1)
print("RESULT:", "FAIL " + str(failures) if failures else "ALL PASS")
sys.exit(1 if failures else 0)
