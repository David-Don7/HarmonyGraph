"""Record the complete runtime dependency closure, excluding unrelated host packages."""

from importlib.metadata import distribution
import tomllib
from pathlib import Path
from packaging.requirements import Requirement

seen = {}


def visit(name, extra=""):
    dist = distribution(name)
    canonical = dist.metadata["Name"]
    if canonical.lower() in seen:
        return
    seen[canonical.lower()] = f"{canonical}=={dist.version}"
    for spec in dist.requires or []:
        requirement = Requirement(spec)
        if requirement.marker is None or requirement.marker.evaluate({"extra": extra}):
            visit(requirement.name)


root = Path(__file__).resolve().parents[1]
project = tomllib.loads((root / "pyproject.toml").read_text())["project"]
for spec in project["dependencies"]:
    req = Requirement(spec)
    visit(req.name, next(iter(req.extras), ""))
# Binary driver is a cross-platform declared optional extra of psycopg.
visit("psycopg-binary")
# setuptools is needed for the editable/build backend, pinned alongside runtime dependencies.
visit("setuptools")
lock = "# Runtime dependency closure. Python 3.12. Regenerate with scripts/lock_dependencies.py.\n"
lock += "\n".join(value for key, value in sorted(seen.items()) if key not in {"colorama", "tzdata"})
lock += '\ncolorama==0.4.6; sys_platform == "win32"\ntzdata==2024.1; sys_platform == "win32"\n'
(root / "requirements.lock").write_text(lock, encoding="utf-8")

for spec in project.get("optional-dependencies", {}).get("dev", []):
    visit(Requirement(spec).name)
dev_lock = "# Complete development dependency closure. Python 3.12.\n"
dev_lock += "\n".join(value for key, value in sorted(seen.items()) if key not in {"colorama", "tzdata"})
dev_lock += '\ncolorama==0.4.6; sys_platform == "win32"\ntzdata==2024.1; sys_platform == "win32"\n'
(root / "requirements-dev.lock").write_text(dev_lock, encoding="utf-8")
