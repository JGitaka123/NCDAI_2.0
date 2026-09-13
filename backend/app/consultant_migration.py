"""Explicit first migration for the separate consultant database.

Run under the migration-owner credential, never from a web request or startup.
Later schema revisions require a new migration, not editing an applied revision.
"""
from sqlalchemy import inspect, text
from .consultant_models import ConsultantBase, CONSULTANT_SCHEMA


def migrate_initial(engine):
    existing = set(inspect(engine).get_table_names())
    expected = set(ConsultantBase.metadata.tables)
    if existing:
        if existing != expected:
            raise RuntimeError('Consultant migration refuses an unrelated/nonempty database')
        with engine.connect() as conn:
            if conn.scalar(text('SELECT version FROM consultant_schema')) != CONSULTANT_SCHEMA:
                raise RuntimeError('Unknown consultant database version')
        return
    with engine.begin() as conn:
        ConsultantBase.metadata.create_all(conn)
        if engine.dialect.name == 'postgresql':
            conn.execute(text("""CREATE FUNCTION consultant_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN RAISE EXCEPTION 'Consultation history is immutable'; END; $$"""))
            for table in ('consultant_cases','consultant_opinions'):
                conn.execute(text(f'CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION consultant_immutable()'))
        else:
            for table in ('consultant_cases','consultant_opinions'):
                for action in ('UPDATE','DELETE'):
                    conn.execute(text(f"CREATE TRIGGER {table}_{action.lower()} BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT, 'Consultation history is immutable'); END"))
        conn.execute(text('INSERT INTO consultant_schema (version) VALUES (:v)'), {'v':CONSULTANT_SCHEMA})
