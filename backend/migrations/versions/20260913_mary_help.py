"""Facility-gated clinical testing, named-account onboarding and durable consult outbox."""
from alembic import op
import sqlalchemy as sa

revision = "20260913_mary_help"
down_revision = "20260912_guards"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('facilities', sa.Column('record_mode', sa.String(30), nullable=False, server_default='synthetic'))
    op.add_column('users', sa.Column('password_change_required', sa.Boolean(), nullable=False, server_default=sa.false()))
    dialect = op.get_bind().dialect.name
    if dialect == 'sqlite':
        op.execute('PRAGMA defer_foreign_keys=ON')
    with op.batch_alter_table('facilities') as batch:
        batch.create_check_constraint('ck_facility_record_mode', "record_mode IN ('synthetic', 'clinical_testing')")
    with op.batch_alter_table('patients') as batch:
        batch.drop_constraint('ck_patient_synthetic_only', type_='check')
    op.create_table('consultation_requests',
        sa.Column('id', sa.String(36), primary_key=True), sa.Column('facility_id', sa.String(36), sa.ForeignKey('facilities.id'), nullable=False),
        sa.Column('encounter_id', sa.String(36), nullable=False), sa.Column('patient_id', sa.String(36), nullable=False),
        sa.Column('requested_by', sa.String(36), sa.ForeignKey('users.id'), nullable=False), sa.Column('idempotency_key', sa.String(36), nullable=False),
        sa.Column('payload_hash', sa.String(64), nullable=False), sa.Column('snapshot', sa.JSON(), nullable=False), sa.Column('snapshot_hash', sa.String(64), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['facility_id','encounter_id','patient_id'], ['encounters.facility_id','encounters.id','encounters.patient_id']),
        sa.UniqueConstraint('requested_by','idempotency_key'),sa.UniqueConstraint('facility_id','id'))
    op.create_index('ix_consultation_requests_facility_id','consultation_requests',['facility_id'])
    op.create_index('ix_consultation_requests_encounter_id','consultation_requests',['encounter_id'])
    op.create_table('consultation_dispositions',
        sa.Column('request_id',sa.String(36),sa.ForeignKey('consultation_requests.id'),primary_key=True),
        sa.Column('facility_id',sa.String(36),sa.ForeignKey('facilities.id'),nullable=False), sa.Column('actor_id',sa.String(36),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('opinion_hash',sa.String(64),nullable=False),sa.Column('opinion_snapshot',sa.JSON(),nullable=False),sa.Column('action',sa.String(20),nullable=False),sa.Column('action_taken',sa.Text(),nullable=False),
        sa.Column('current_encounter_version',sa.Integer(),nullable=False),sa.Column('snapshot_was_stale',sa.Boolean(),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.ForeignKeyConstraint(['facility_id','request_id'],['consultation_requests.facility_id','consultation_requests.id']),
        sa.CheckConstraint("action IN ('accepted', 'modified', 'not_followed')",name='ck_consult_disposition_action'))
    op.create_index('ix_consultation_dispositions_facility_id','consultation_dispositions',['facility_id'])
    if dialect == 'postgresql':
        op.execute("""CREATE FUNCTION ncdai_patient_mode_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF TG_OP = 'UPDATE' AND (NEW.synthetic IS DISTINCT FROM OLD.synthetic OR NEW.facility_id IS DISTINCT FROM OLD.facility_id) THEN
            RAISE EXCEPTION 'Record classification and facility are immutable';
          END IF;
          IF NEW.synthetic = false AND NOT EXISTS (SELECT 1 FROM facilities WHERE id = NEW.facility_id AND record_mode = 'clinical_testing') THEN
            RAISE EXCEPTION 'Real records require an enabled clinical facility';
          END IF;
          RETURN NEW;
        END; $$""")
        op.execute('CREATE TRIGGER patient_mode_guard BEFORE INSERT OR UPDATE ON patients FOR EACH ROW EXECUTE FUNCTION ncdai_patient_mode_guard()')
        for table in ('consultation_requests','consultation_dispositions'):
            op.execute(f'CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION ncdai_audit_immutable()')
    else:
        op.execute("""CREATE TRIGGER patient_mode_insert BEFORE INSERT ON patients WHEN NEW.synthetic = 0 AND NOT EXISTS
          (SELECT 1 FROM facilities WHERE id = NEW.facility_id AND record_mode = 'clinical_testing')
          BEGIN SELECT RAISE(ABORT, 'Real records require an enabled clinical facility'); END""")
        op.execute("""CREATE TRIGGER patient_mode_update BEFORE UPDATE ON patients WHEN NEW.synthetic != OLD.synthetic OR NEW.facility_id != OLD.facility_id
          BEGIN SELECT RAISE(ABORT, 'Record classification and facility are immutable'); END""")
        for table in ('consultation_requests','consultation_dispositions'):
            for action in ('UPDATE','DELETE'):
                op.execute(f"CREATE TRIGGER {table}_no_{action.lower()} BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT, 'Consultation records are immutable'); END")


def downgrade():
    # A real-data release must never downgrade into a synthetic-only schema.
    if op.get_bind().scalar(sa.text('SELECT count(*) FROM patients WHERE synthetic = false')):
        raise RuntimeError('Cannot downgrade a database containing real records')
    if op.get_bind().scalar(sa.text('SELECT count(*) FROM consultation_requests')):
        raise RuntimeError('Cannot discard retained consultation records')
    op.drop_table('consultation_dispositions')
    op.drop_table('consultation_requests')
    if op.get_bind().dialect.name == 'postgresql':
        op.execute('DROP TRIGGER patient_mode_guard ON patients')
        op.execute('DROP FUNCTION ncdai_patient_mode_guard()')
    else:
        op.execute('DROP TRIGGER patient_mode_insert')
        op.execute('DROP TRIGGER patient_mode_update')
        op.execute('PRAGMA defer_foreign_keys=ON')
    with op.batch_alter_table('patients') as batch:
        batch.create_check_constraint('ck_patient_synthetic_only', 'synthetic = true')
    with op.batch_alter_table('facilities') as batch:
        batch.drop_constraint('ck_facility_record_mode',type_='check')
        batch.drop_column('record_mode')
    op.drop_column('users','password_change_required')
