# the_sacred_lazy_one/scripts/manifest.py
# What this node contributes to the frame bundle.
# Called by tools/build_frame.py via load_manifest().
# Extend build_bundle() to include directories this node contributes.

from __future__ import annotations
from pathlib import Path
from typing import Any, List
import json

NODE_DIR = Path(__file__).resolve().parents[1]
ROOT     = NODE_DIR.parent


def node_name() -> str:
    return "the_sacred_lazy_one"


def repository_url() -> str:
    import json as _json
    nj = _json.loads((NODE_DIR / "node.json").read_text())
    return nj.get("repository", "")


def license_name() -> str:
    return "CC-BY-SA-4.0"


def frame_schema() -> str:
    return "mesh_node/v0.0.0"


def artifact_dir() -> str:
    return "dist"


def artifact_basename(label: str) -> str:
    return f"the_sacred_lazy_one_frame_{label}"


def requirements() -> List[str]:
    """
    Return full requirements list, walking derived_from chain.
    Delegates to tools/query.py resolve_all for chain walking.
    Add node-specific packages to node.json venv.requirements.
    """
    try:
        from tools.query import resolve_all
        return resolve_all("venv.requirements")
    except ImportError:
        import json as _json
        meta = _json.loads((ROOT / "mesh_node.json").read_text())
        return (meta.get("reserved_directories", {})
                    .get("root", {})
                    .get("venv", {})
                    .get("requirements", []))


def python_min() -> str:
    try:
        from tools.query import resolve
        return resolve("venv.python_min") or "3.11"
    except ImportError:
        import json as _json
        meta = _json.loads((ROOT / "mesh_node.json").read_text())
        return (meta.get("reserved_directories", {})
                    .get("root", {})
                    .get("venv", {})
                    .get("python_min", "3.11"))


def _md_files(path: Path) -> List[Path]:
    if not path.exists():
        return []
    return sorted([p for p in path.rglob("*.md") if p.is_file()])


def _script_files(path: Path) -> List[Path]:
    if not path.exists():
        return []
    return sorted([
        p for p in path.iterdir()
        if p.is_file() and p.suffix in (".py", ".sh")
    ])


def _resolve_frame_path(key: str, default: str) -> Path:
    """
    Resolve a frame directory path from mesh_node.json
    reserved_directories.frame. Falls back to default_node
    mapping, then to the provided default string.
    """
    try:
        meta    = json.loads((ROOT / "mesh_node.json").read_text())
        frame   = meta.get("reserved_directories", {}).get("frame", {})
        mapping = frame.get("the_sacred_lazy_one") or frame.get("default_node", {})
        rel     = mapping.get(key, {}).get("path", default)
        rel     = rel.replace("[node]", "the_sacred_lazy_one")
        return ROOT / rel
    except Exception:
        return ROOT / default


def build_bundle(flags: dict) -> List[Path]:
    """
    Build deduplicated file list for the frame bundle.

    Always included:
      - mesh_node.json
      - README.md
      - the_sacred_lazy_one/node.json
      - the_sacred_lazy_one/epistemic_floor.md (if present)
      - tools/*.py / tools/*.sh
      - the_sacred_lazy_one/scripts/*.py

    Included by default (--effluence, default on):
      - the_sacred_lazy_one/library/

    Included by default (--affluence, default on):
      - the_sacred_lazy_one/inbox/
    """
    items: List[Path] = [
        ROOT / "mesh_node.json",
        ROOT / "README.md",
        NODE_DIR / "node.json",
    ]

    floor = NODE_DIR / "epistemic_floor.md"
    if floor.exists():
        items.append(floor)

    items += _script_files(ROOT / "tools")
    items += _script_files(NODE_DIR / "scripts")

    if flags.get("effluence", True):
        items += _md_files(
            _resolve_frame_path("effluence", "the_sacred_lazy_one/library/")
        )

    if flags.get("affluence", True):
        items += _md_files(
            _resolve_frame_path("affluence", "the_sacred_lazy_one/inbox/")
        )

    seen: set = set()
    out: List[Path] = []
    for p in items:
        rp = p.resolve()
        if rp not in seen and p.exists():
            seen.add(rp)
            out.append(p)

    return out
