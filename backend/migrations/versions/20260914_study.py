"""Prospective study observations and transactional activity evidence."""
from alembic import op
import sqlalchemy as sa

revision = '20260914_study'
down_revision = '20260913_mary_help'
branch_labels = depends_on = None


def upgrade():
    op.create_table('study_records',
        sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('facility_id',sa.String(36),sa.ForeignKey('facilities.id'),nullable=False),
        sa.Column('patient_id',sa.String(36)),sa.Column('encounter_id',sa.String(36)),
        sa.Column('actor_id',sa.String(36),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('kind',sa.String(30),nullable=False),sa.Column('record_key',sa.String(120),nullable=False),
        sa.Column('revision',sa.Integer(),nullable=False),
        sa.Column('previous_id',sa.String(36),sa.ForeignKey('study_records.id')),
        sa.Column('idempotency_key',sa.String(36),nullable=False),
        sa.Column('payload_hash',sa.String(64),nullable=False),sa.Column('synthetic',sa.Boolean(),nullable=False),
        sa.Column('payload',sa.JSON(),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.UniqueConstraint('facility_id','record_key','revision'),sa.UniqueConstraint('actor_id','idempotency_key'),
        sa.CheckConstraint('revision >= 1',name='ck_study_revision'),
        sa.CheckConstraint("kind IN ('enrolment','visit','followup','safety','daily_tally')",name='ck_study_kind'),
        sa.ForeignKeyConstraint(['facility_id','patient_id'],['patients.facility_id','patients.id']),
        sa.ForeignKeyConstraint(['facility_id','encounter_id','patient_id'],['encounters.facility_id','encounters.id','encounters.patient_id']))
    op.create_index('ix_study_records_facility_id','study_records',['facility_id'])
    op.create_table('study_events',
        sa.Column('id',sa.String(36),sa.ForeignKey('audit_events.id'),primary_key=True),
        sa.Column('facility_id',sa.String(36),sa.ForeignKey('facilities.id'),nullable=False),
        sa.Column('patient_id',sa.String(36),nullable=False),sa.Column('encounter_id',sa.String(36),nullable=False),
        sa.Column('actor_id',sa.String(36),nullable=False),
        sa.Column('action',sa.String(60),nullable=False),sa.Column('synthetic',sa.Boolean(),nullable=False),
        sa.Column('payload',sa.JSON(),nullable=False),sa.Column('payload_hash',sa.String(64),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.ForeignKeyConstraint(['facility_id','encounter_id','patient_id'],['encounters.facility_id','encounters.id','encounters.patient_id']))
    for col in ('facility_id','encounter_id','created_at'):
        op.create_index('ix_study_events_'+col,'study_events',[col])
    for table in ('study_records','study_events'):
        if op.get_bind().dialect.name == 'postgresql':
            op.execute(f'CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION ncdai_audit_immutable()')
        else:
            for action in ('UPDATE','DELETE'):
                op.execute(f"CREATE TRIGGER {table}_no_{action.lower()} BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT, 'Study records are immutable'); END")


def downgrade():
    for table in ('study_events','study_records'):
        if op.get_bind().scalar(sa.text(f'SELECT count(*) FROM {table}')):
            raise RuntimeError('Cannot discard retained study evidence')
    op.drop_table('study_events')
    op.drop_table('study_records')
