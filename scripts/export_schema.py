"""Write schema/spatial-context.v3.json from the pydantic contract (server/app/contracts.py).
Run after changing the contract; tests/test_schema.py fails when the committed file drifts."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
from app.contracts import schema_document  # noqa: E402

target = ROOT / "schema" / "spatial-context.v3.json"
target.parent.mkdir(exist_ok=True)
target.write_text(
    json.dumps(schema_document(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
print(f"wrote {target.relative_to(ROOT)}")
