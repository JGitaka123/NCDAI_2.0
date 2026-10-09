"""Export public source metadata only. Does not access patient databases or URLs."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.evidence_manifest import manifest

if __name__ == "__main__":
    print(json.dumps(manifest(), indent=2, ensure_ascii=True))
