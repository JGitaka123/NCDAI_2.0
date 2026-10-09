"""Read-only public CI gate. No token, deployment, or patient data access."""
import json
import os
import re
import sys
from urllib.request import Request, urlopen

REPOSITORY = "JGitaka123/NCDAI_2.0"
QUALITY_WORKFLOW_ID = 356656520
REQUIRED_JOBS = {"backend", "frontend", "postgres"}


def latest_quality_run(payload, sha):
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("A resolved 40-character commit SHA is required")
    runs = payload.get("workflow_runs", [])
    matches = [run for run in runs if run.get("head_sha") == sha and run.get("workflow_id") == QUALITY_WORKFLOW_ID]
    if not matches:
        raise ValueError("No quality run exists for the selected commit")
    latest = max(matches, key=lambda run: int(run["id"]))
    if latest.get("status") != "completed" or latest.get("conclusion") != "success":
        raise ValueError("The latest quality run for the selected commit has not passed")
    return latest


def verify_jobs(payload):
    jobs = payload.get("jobs", [])
    if payload.get("total_count", len(jobs)) > len(jobs):
        raise ValueError("Quality-job response is incomplete")
    for name in REQUIRED_JOBS:
        matching = [job for job in jobs if job.get("name") == name]
        if len(matching) != 1 or matching[0].get("status") != "completed" or matching[0].get("conclusion") != "success":
            raise ValueError(f"Required quality job has not passed: {name}")


def fetch_json(path):
    request = Request("https://api.github.com/repos/" + REPOSITORY + path,
                      headers={"Accept": "application/vnd.github+json", "User-Agent": "NCDAI-read-only-release-gate"})
    with urlopen(request, timeout=20) as response:
        content = response.read(2_000_001)
        if len(content) > 2_000_000:
            raise ValueError("Quality response exceeds the supported limit")
        return json.loads(content)


def main():
    sha = os.environ.get("NCDAI_RELEASE_SHA", "")
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("A resolved 40-character commit SHA is required")
    run = latest_quality_run(fetch_json(f"/actions/workflows/{QUALITY_WORKFLOW_ID}/runs?head_sha={sha}&per_page=100"), sha)
    verify_jobs(fetch_json(f"/actions/runs/{int(run['id'])}/jobs?filter=latest&per_page=100"))
    print(f"Quality passed for {sha}: https://github.com/{REPOSITORY}/actions/runs/{int(run['id'])}")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # No deployment credential is available here. A network/API/parse error
        # still blocks release rather than falling back to an older green run.
        print("::error::Release blocked: exact-commit quality verification failed. Check the latest quality run and retry only after all required jobs pass.", file=sys.stderr)
        sys.exit(1)
