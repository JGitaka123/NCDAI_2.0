"""Immutable clinical records and append-only audit at database boundary.

Revision ID: 20260912_guards
Revises: c396c15b3b53
"""
from alembic import op

revision = "20260912_guards"
down_revision = "c396c15b3b53"
branch_labels = None
depends_on = None


def upgrade():
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        for action in ("UPDATE", "DELETE"):
            op.execute(f"CREATE TRIGGER audit_no_{action.lower()} BEFORE {action} ON audit_events BEGIN SELECT RAISE(ABORT, 'Audit events are append-only'); END")
            op.execute(f"CREATE TRIGGER reviewed_no_{action.lower()} BEFORE {action} ON encounters WHEN OLD.status = 'reviewed' BEGIN SELECT RAISE(ABORT, 'Reviewed encounters are immutable'); END")
        op.execute("""CREATE TRIGGER referral_transition BEFORE UPDATE OF status ON referrals
            WHEN NOT ((OLD.status = 'requested' AND NEW.status IN ('accepted', 'cancelled'))
                   OR (OLD.status = 'accepted' AND NEW.status IN ('completed', 'cancelled')))
            BEGIN SELECT RAISE(ABORT, 'Invalid referral transition'); END""")
    elif dialect == "postgresql":
        op.execute("""CREATE FUNCTION ncdai_audit_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'Audit events are append-only'; END; $$""")
        op.execute("CREATE TRIGGER audit_immutable BEFORE UPDATE OR DELETE ON audit_events FOR EACH ROW EXECUTE FUNCTION ncdai_audit_immutable()")
        op.execute("""CREATE FUNCTION ncdai_reviewed_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
              IF OLD.status = 'reviewed' THEN RAISE EXCEPTION 'Reviewed encounters are immutable'; END IF;
              IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
              RETURN NEW;
            END; $$""")
        op.execute("CREATE TRIGGER reviewed_immutable BEFORE UPDATE OR DELETE ON encounters FOR EACH ROW EXECUTE FUNCTION ncdai_reviewed_immutable()")
        op.execute("""CREATE FUNCTION ncdai_referral_transition() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
              IF NOT ((OLD.status = 'requested' AND NEW.status IN ('accepted', 'cancelled'))
                OR (OLD.status = 'accepted' AND NEW.status IN ('completed', 'cancelled')))
              THEN RAISE EXCEPTION 'Invalid referral transition'; END IF;
              RETURN NEW;
            END; $$""")
        op.execute("CREATE TRIGGER referral_transition BEFORE UPDATE OF status ON referrals FOR EACH ROW EXECUTE FUNCTION ncdai_referral_transition()")


def downgrade():
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        for name in ("audit_no_update", "audit_no_delete", "reviewed_no_update", "reviewed_no_delete", "referral_transition"):
            op.execute(f"DROP TRIGGER {name}")
    elif dialect == "postgresql":
        for trigger, table, function in [("audit_immutable", "audit_events", "ncdai_audit_immutable"), ("reviewed_immutable", "encounters", "ncdai_reviewed_immutable"), ("referral_transition", "referrals", "ncdai_referral_transition")]:
            op.execute(f"DROP TRIGGER {trigger} ON {table}")
            op.execute(f"DROP FUNCTION {function}()")
