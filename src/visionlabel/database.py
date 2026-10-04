"""SQLAlchemy owns connections; explicit SQL keeps CAS transactions reviewable."""

from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event

from .storage import local_directory

SCHEMA_REVISION = "0003"

SCHEMA = [
    "CREATE TABLE users (id TEXT PRIMARY KEY, username TEXT NOT NULL UNIQUE, display_name TEXT NOT NULL, password_hash TEXT NOT NULL, is_admin INTEGER NOT NULL CHECK(is_admin IN (0,1)), disabled INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL)",
    "CREATE TABLE auth_tokens (id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), token_hash TEXT NOT NULL UNIQUE, expires_at TEXT NOT NULL, revoked_at TEXT, created_at TEXT NOT NULL)",
    "CREATE TABLE projects (id TEXT PRIMARY KEY, slug TEXT NOT NULL UNIQUE, name TEXT NOT NULL, task_type TEXT NOT NULL CHECK(task_type IN ('detection','classification')), active_schema_id TEXT REFERENCES class_schemas(id), project_revision INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, created_by TEXT NOT NULL REFERENCES users(id))",
    "CREATE TABLE project_members (project_id TEXT NOT NULL REFERENCES projects(id), user_id TEXT NOT NULL REFERENCES users(id), role TEXT NOT NULL CHECK(role IN ('viewer','annotator','reviewer','maintainer')), PRIMARY KEY(project_id,user_id))",
    "CREATE TABLE classes (id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id), stable_key TEXT NOT NULL, UNIQUE(project_id,stable_key))",
    "CREATE TABLE class_schemas (id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id), number INTEGER NOT NULL, blob_path TEXT NOT NULL UNIQUE, sha256 TEXT NOT NULL, created_at TEXT NOT NULL, created_by TEXT NOT NULL REFERENCES users(id), UNIQUE(project_id,number))",
    "CREATE TABLE class_schema_entries (schema_id TEXT NOT NULL REFERENCES class_schemas(id), class_id TEXT NOT NULL REFERENCES classes(id), display_name TEXT NOT NULL, export_index INTEGER NOT NULL CHECK(export_index>=0), color_hex TEXT NOT NULL, active INTEGER NOT NULL, PRIMARY KEY(schema_id,class_id), UNIQUE(schema_id,export_index))",
    "CREATE TABLE assets (sha256 TEXT PRIMARY KEY, byte_size INTEGER NOT NULL CHECK(byte_size>0), media_type TEXT NOT NULL, extension TEXT NOT NULL, width INTEGER NOT NULL CHECK(width>0), height INTEGER NOT NULL CHECK(height>0), blob_path TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL, created_by TEXT NOT NULL REFERENCES users(id))",
    "CREATE TABLE images (id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id), asset_sha256 TEXT NOT NULL REFERENCES assets(sha256), display_filename TEXT NOT NULL, group_key TEXT, archived INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, created_by TEXT NOT NULL REFERENCES users(id), UNIQUE(project_id,asset_sha256))",
    "CREATE TABLE annotation_heads (image_id TEXT PRIMARY KEY REFERENCES images(id), current_revision INTEGER NOT NULL DEFAULT 0 CHECK(current_revision>=0), state_revision INTEGER NOT NULL DEFAULT 0 CHECK(state_revision>=0), status TEXT NOT NULL DEFAULT 'UNLABELED', updated_at TEXT NOT NULL)",
    "CREATE TABLE annotation_revisions (image_id TEXT NOT NULL REFERENCES images(id), revision INTEGER NOT NULL CHECK(revision>0), schema_id TEXT NOT NULL REFERENCES class_schemas(id), blob_path TEXT NOT NULL UNIQUE, sha256 TEXT NOT NULL, verified_empty INTEGER NOT NULL, object_count INTEGER NOT NULL, created_at TEXT NOT NULL, created_by TEXT NOT NULL REFERENCES users(id), PRIMARY KEY(image_id,revision))",
    "CREATE TABLE task_claims (image_id TEXT PRIMARY KEY REFERENCES images(id), claim_id TEXT NOT NULL UNIQUE, owner_id TEXT NOT NULL REFERENCES users(id), client_instance_id TEXT NOT NULL, generation INTEGER NOT NULL, token_hash TEXT NOT NULL, expires_at TEXT NOT NULL, last_heartbeat_at TEXT NOT NULL)",
    "CREATE TABLE audit_events (id TEXT PRIMARY KEY, project_id TEXT REFERENCES projects(id), actor_id TEXT REFERENCES users(id), action TEXT NOT NULL, entity_id TEXT NOT NULL, request_id TEXT NOT NULL, detail_json TEXT NOT NULL, created_at TEXT NOT NULL)",
    "CREATE TABLE idempotency_records (user_id TEXT NOT NULL REFERENCES users(id), route_scope TEXT NOT NULL, key TEXT NOT NULL, request_sha256 TEXT NOT NULL, response_json TEXT NOT NULL, response_status INTEGER NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY(user_id,route_scope,key))",
    "CREATE TABLE jobs (id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id), created_by TEXT NOT NULL REFERENCES users(id), type TEXT NOT NULL, state TEXT NOT NULL, payload_json TEXT NOT NULL, progress_done INTEGER NOT NULL DEFAULT 0, progress_total INTEGER NOT NULL, result_json TEXT, error_json TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)",
    "CREATE TABLE image_sources (id TEXT PRIMARY KEY, image_id TEXT NOT NULL REFERENCES images(id), import_job_id TEXT NOT NULL REFERENCES jobs(id), source_alias TEXT NOT NULL, source_relpath TEXT NOT NULL, source_sha256 TEXT NOT NULL, created_at TEXT NOT NULL)",
    "CREATE INDEX images_project ON images(project_id,archived,created_at,id)",
    "CREATE INDEX revisions_schema ON annotation_revisions(schema_id)",
]

for table in (
    "annotation_revisions",
    "assets",
    "class_schemas",
    "classes",
    "class_schema_entries",
    "audit_events",
):
    for operation in ("UPDATE", "DELETE"):
        SCHEMA.append(
            f"CREATE TRIGGER immutable_{table}_{operation.lower()} BEFORE {operation} ON {table} BEGIN SELECT RAISE(ABORT,'immutable record'); END"
        )


def row(conn, sql, parameters=()):
    result = conn.exec_driver_sql(sql, parameters).mappings().first()
    return dict(result) if result else None


def rows(conn, sql, parameters=()):
    return [dict(item) for item in conn.exec_driver_sql(sql, parameters).mappings()]


class Database:
    def __init__(self, path: Path):
        local_directory(path.parent).mkdir(parents=True, exist_ok=True)
        self.path = path
        self.engine = create_engine("sqlite:///" + path.as_posix(), connect_args={"check_same_thread": False})

        @event.listens_for(self.engine, "connect")
        def configure(dbapi, record):
            for pragma in ("foreign_keys=ON", "journal_mode=WAL", "synchronous=FULL", "busy_timeout=5000"):
                dbapi.execute("PRAGMA " + pragma)

    def migrate(self):
        from alembic import command
        from alembic.config import Config

        config = Config()
        config.set_main_option("script_location", str(Path(__file__).parent / "migrations"))
        with self.engine.connect() as connection:
            # Rebuilding a SQLite CHECK constraint requires FK enforcement off.
            # This startup-only connection is protected by the service directory lock.
            connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
            connection.commit()
            try:
                connection.exec_driver_sql("BEGIN IMMEDIATE")
                config.attributes["connection"] = connection
                command.upgrade(config, "head")
                if connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall():
                    raise RuntimeError("Migration failed foreign-key validation.")
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
            finally:
                connection.exec_driver_sql("PRAGMA foreign_keys=ON")
                connection.commit()

    @contextmanager
    def transaction(self):
        with self.engine.connect() as conn:
            conn.exec_driver_sql("BEGIN IMMEDIATE")
            try:
                yield conn
                conn.commit()
            except BaseException:
                conn.rollback()
                raise
