import json
from pathlib import Path
from harmonygraph.api import app

root = Path(__file__).resolve().parents[1]
(root / "docs" / "openapi.json").write_text(json.dumps(app.openapi(), indent=2), encoding="utf-8")
