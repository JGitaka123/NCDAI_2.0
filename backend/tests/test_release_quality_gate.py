import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "scripts" / "check_release_quality.py"
spec = importlib.util.spec_from_file_location("release_quality", SOURCE)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)
SHA = "a" * 40


def run(rid=1, **changes):
    return {"id": rid, "workflow_id": gate.QUALITY_WORKFLOW_ID, "head_sha": SHA,
            "status": "completed", "conclusion": "success", **changes}


def test_latest_run_must_pass_not_an_older_green_result():
    with pytest.raises(ValueError):
        gate.latest_quality_run({"workflow_runs": [run(), run(2, conclusion="failure")]}, SHA)


@pytest.mark.parametrize("payload", [
    {"workflow_runs": []}, {"workflow_runs": [run(head_sha="b" * 40)]},
    {"workflow_runs": [run(workflow_id=1)]}, {"workflow_runs": [run(status="in_progress")]},
])
def test_missing_wrong_or_incomplete_run_blocks(payload):
    with pytest.raises(ValueError):
        gate.latest_quality_run(payload, SHA)


def test_exact_commit_and_all_three_jobs_required():
    assert gate.latest_quality_run({"workflow_runs": [run()]}, SHA)["id"] == 1
    jobs = [{"name": name, "status": "completed", "conclusion": "success"} for name in gate.REQUIRED_JOBS]
    gate.verify_jobs({"jobs": jobs})
    with pytest.raises(ValueError):
        gate.verify_jobs({"jobs": jobs[:-1]})
    jobs[0]["conclusion"] = "skipped"
    with pytest.raises(ValueError):
        gate.verify_jobs({"jobs": jobs})


def test_workflow_gate_is_trusted_inline_code_before_credentials():
    workflow = (ROOT / ".github" / "workflows" / "deploy-production.yml").read_text(encoding="utf-8")
    # Inline code cannot be substituted by the arbitrary ref checked out for deployment.
    block = workflow.split("          python3 - <<'QUALITY_GATE'\n", 1)[1].split("          QUALITY_GATE", 1)[0]
    assert "\n".join(line[10:] for line in block.splitlines()) == SOURCE.read_text(encoding="utf-8").rstrip()
    assert workflow.index("Require exact-commit quality") < workflow.index("Check the deployment credential")
    assert "vercel@59.14.0" in workflow
