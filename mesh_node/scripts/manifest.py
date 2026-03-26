# mesh_node/scripts/manifest.py
# What the mesh_node base contributes to the frame bundle.
# Registers default query handlers via tools/query.py.
# Called by tools/build_frame.py and tools/query.py bootstrap().
# NODE_DIR is this file's parent's parent — the node content directory.

from __future__ import annotations
from pathlib import Path
from typing import Any, List
import json

NODE_DIR = Path(__file__).resolve().parents[1]
ROOT     = NODE_DIR.parent


# ── Node.json access ──────────────────────────────────────────────────────────

def _node_json() -> dict:
    path = NODE_DIR / "node.json"
    return json.loads(path.read_text()) if path.exists() else {}


# ── Query registration ────────────────────────────────────────────────────────
# Handlers registered here are the terminal defaults.
# Derived node manifests override by registering the same key.

def _register_defaults():
    try:
        from tools.query import register
    except ImportError:
        return

    nj = _node_json()

    register("model.target",
        lambda _: nj.get("model", {}).get("target"),
        description="Primary model identifier")

    register("model.shorthand",
        lambda _: nj.get("model", {}).get("shorthand"),
        description="Model shorthand alias")

    register("inference.environment",
        lambda _: nj.get("inference", {}).get("environment"),
        description="Inference environment (mlx, ollama, etc)")

    register("venv.python_min",
        lambda _: nj.get("venv", {}).get("python_min", "3.11"),
        description="Minimum Python version")

    register("venv.requirements",
        lambda _: nj.get("venv", {}).get("requirements", []),
        description="Python package requirements")

    register("node.repository",
        lambda _: nj.get("repository"),
        description="Node git repository URL")

    register("node.custodians",
        lambda _: nj.get("custodians", []),
        description="Node custodian GitHub usernames")

    register("node.peers",
        lambda _: nj.get("peers", []),
        description="Registered peer nodes")

    register("node.derived_from",
        lambda _: nj.get("derived_from"),
        description="Parent node name in derivation chain")

    register("derive.instructions",
        lambda _: nj.get("derive", {}).get("instructions"),
        description="Path to derive instructions document for model-assisted scaffolding")


# Register on import — side effect by design
_register_defaults()


# ── Frame bundle ──────────────────────────────────────────────────────────────

def node_name() -> str:
    return "mesh_node"


def repository_url() -> str:
    return _node_json().get("repository", "")


def license_name() -> str:
    return _node_json().get("license", "CC-BY-SA-4.0")


def frame_schema() -> str:
    return "mesh_node/v0.0.0"


def artifact_dir() -> str:
    return "dist"


def artifact_basename(label: str) -> str:
    return f"mesh_node_frame_{label}"


def requirements() -> List[str]:
    """
    Return full requirements list, walking derived_from chain.
    Highest node takes precedence; parents fill in what's missing.
    activate_node.py calls this to build the venv.
    """
    try:
        from tools.query import resolve_all
        return resolve_all("venv.requirements")
    except ImportError:
        return _node_json().get("venv", {}).get("requirements", [])


def python_min() -> str:
    try:
        from tools.query import resolve
        return resolve("venv.python_min") or "3.11"
    except ImportError:
        return _node_json().get("venv", {}).get("python_min", "3.11")


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
    Resolve a frame directory path from mesh_node.json reserved_directories.frame.
    Falls back to default_node mapping, then to the provided default string.
    """
    try:
        meta    = json.loads((ROOT / "mesh_node.json").read_text())
        frame   = meta.get("reserved_directories", {}).get("frame", {})
        mapping = frame.get("mesh_node") or frame.get("default_node", {})
        rel     = mapping.get(key, {}).get("path", default)
        rel     = rel.replace("[node]", "mesh_node")
        return ROOT / rel
    except Exception:
        return ROOT / default


def build_bundle(flags: dict) -> List[Path]:
    """
    Build deduplicated file list for the frame bundle.

    Always included:
      - mesh_node.json
      - README.md
      - mesh_node/node.json
      - mesh_node/epistemic_floor.md
      - tools/*.py / tools/*.sh
      - mesh_node/scripts/*.py

    Included by default (--effluence, default on):
      - mesh_node/library/

    Included by default (--affluence, default on):
      - mesh_node/inbox/
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
        items += _md_files(_resolve_frame_path("effluence", "mesh_node/library/"))

    if flags.get("affluence", True):
        items += _md_files(_resolve_frame_path("affluence", "mesh_node/inbox/"))

    seen: set = set()
    out: List[Path] = []
    for p in items:
        rp = p.resolve()
        if rp not in seen and p.exists():
            seen.add(rp)
            out.append(p)

    return out
