#!/usr/bin/env python3
# tools/query.py
# Fixed entry point for all node communication.
#
# Every tool, every peer node, every Mastodon command routes through here.
# The entry point is always the same. The infrastructure is invisible to it.
#
# Three modes:
#
# 1. Resolution — dot-notation key lookup through node.json chain
#    query("model.target")          → value or None
#    query("venv.requirements")     → value or None
#
# 2. Dispatch — registered handler called with optional payload
#    query("nabla.generate", payload={"source": "path/to/file.md"})
#
# 3. Registry — nodes register handlers for named queries
#    Query.register("nabla.generate", handler_fn, schema={"source": str})
#
# Resolution chain:
#    highest node/node.json → derived_from chain → mesh_node/node.json
#    None is a valid result — callers handle it.
#
# Stateless — no persistent process required. One message in, one result out.
# Queue, parallelism, and distribution are the caller's concern.
#
# Usage:
#   python tools/query.py <key> [--payload <json>] [--list]
#
# As a library:
#   from tools.query import Query
#   result = Query.dispatch("model.target")
#   Query.register("my.handler", fn, schema={"input": str})

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]


# ── Node.json resolution ──────────────────────────────────────────────────────

def _load_node_json(node_dir: Path) -> dict:
    """Load [node]/node.json, return empty dict if not found."""
    path = node_dir / "node.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _load_mesh_node_json() -> dict:
    path = ROOT / "mesh_node.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def _resolve_node_dirs() -> list[Path]:
    """
    Return list of node directories from highest to lowest (mesh_node last).

    mesh_node.json holds a single string in 'directory' — the highest node
    in this repo. The integrated node is never aware of what derives from it.
    We walk the derived_from chain through node.json files to build the full
    resolution order.

    Fails loudly if 'directory' is not a string — the type enforces the
    constraint that exactly one node is the entry point.
    """
    meta = _load_mesh_node_json()
    top  = meta.get("directory")

    if top is None:
        top = "mesh_node"  # safe default for bootstrapping
    if not isinstance(top, str):
        raise ValueError(
            f"mesh_node.json 'directory' must be a string, got {type(top).__name__}. "
            f"Each repo has exactly one entry point node."
        )

    chain     = [ROOT / top]
    seen      = {top}
    node_json = _load_node_json(ROOT / top)
    parent    = node_json.get("derived_from")

    while parent and parent not in seen:
        seen.add(parent)
        chain.append(ROOT / parent)
        node_json = _load_node_json(ROOT / parent)
        parent    = node_json.get("derived_from")

    return chain


def _get_nested(obj: dict, key_path: str) -> tuple[bool, Any]:
    """
    Traverse dot-notation key path in obj.
    Returns (found, value).
    """
    parts = key_path.split(".")
    cur   = obj
    for part in parts:
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return False, None
    return True, cur


def resolve(key: str) -> Any:
    """
    Resolve a dot-notation key through the node.json chain.
    Starts at highest node, walks derived_from, terminates at mesh_node/node.json.
    Returns None if not found anywhere.

    Examples:
        resolve("model.target")       → "mlx-community/..."
        resolve("venv.requirements")  → ["mlx-lm", ...]
        resolve("peers")              → []
        resolve("nonexistent")        → None
    """
    node_dirs = _resolve_node_dirs()

    for node_dir in node_dirs:
        node_json = _load_node_json(node_dir)
        found, value = _get_nested(node_json, key)
        if found:
            return value

    return None


def resolve_all(key: str) -> list[Any]:
    """
    Collect values for key from all nodes in the chain.
    Useful for additive keys like requirements — merges without duplicates.
    """
    seen:   set  = set()
    result: list = []

    node_dirs = _resolve_node_dirs()
    for node_dir in node_dirs:
        node_json = _load_node_json(node_dir)
        found, value = _get_nested(node_json, key)
        if found:
            if isinstance(value, list):
                for item in value:
                    k = str(item)
                    if k not in seen:
                        seen.add(k)
                        result.append(item)
            else:
                k = str(value)
                if k not in seen:
                    seen.add(k)
                    result.append(value)

    return result


# ── Handler registry ──────────────────────────────────────────────────────────

_registry: dict[str, dict] = {}


def register(
    name:    str,
    handler: Callable,
    schema:  dict | None = None,
    description: str = "",
):
    """
    Register a handler for a named query.

    name        — dot-notation query name (e.g. "nabla.generate")
    handler     — callable(payload: dict) -> Any
    schema      — optional dict describing expected payload keys and types
    description — human-readable description for the registry listing

    Registered handlers take priority over chain resolution.
    Later registrations override earlier ones — derived nodes override parents.

    Examples:
        register("nabla.generate", generate_nabla, schema={"source": str})
        register("frame.respond", respond, schema={"message": str})
    """
    _registry[name] = {
        "handler":     handler,
        "schema":      schema or {},
        "description": description,
    }


def dispatch(name: str, payload: dict | None = None) -> Any:
    """
    Dispatch a query by name.

    If a handler is registered for name, call it with payload.
    Otherwise fall through to chain resolution.
    Returns None if nothing handles it — callers must handle None.

    This is the primary entry point. Tools and external nodes call this.
    """
    payload = payload or {}

    # Registered handler takes priority
    if name in _registry:
        try:
            return _registry[name]["handler"](payload)
        except Exception as e:
            print(f"  Handler error for '{name}': {e}", file=sys.stderr)
            return None

    # Fall through to chain resolution
    return resolve(name)


def list_handlers() -> list[dict]:
    """Return all registered handlers with their schemas and descriptions."""
    return [
        {
            "name":        name,
            "schema":      entry["schema"],
            "description": entry["description"],
        }
        for name, entry in sorted(_registry.items())
    ]


# ── Manifest loader ───────────────────────────────────────────────────────────

def load_manifest(node_dir: Path):
    """
    Load [node]/scripts/manifest.py and return the module.
    Manifest registers handlers on import — side effect by design.
    """
    meta     = _load_mesh_node_json()
    name     = (node_dir / "node.json")
    node_name = json.loads(name.read_text()).get("node", node_dir.name) if name.exists() else node_dir.name
    frame    = meta.get("reserved_directories", {}).get("frame", {})
    mapping  = frame.get(node_name) or frame.get("default_node", {})
    scripts  = mapping.get("scripts", {}).get("path", f"{node_name}/scripts/")
    scripts  = scripts.replace("[node]", node_name)
    manifest_path = ROOT / scripts / "manifest.py"

    if not manifest_path.exists():
        return None

    spec = importlib.util.spec_from_file_location("manifest", manifest_path)
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def bootstrap():
    """
    Load manifests for all nodes in the chain, highest first.
    Each manifest registers its handlers — later registrations override earlier.
    Call this once at the start of any process that uses dispatch().
    """
    node_dirs = _resolve_node_dirs()
    # Load from lowest (mesh_node) to highest — so highest overrides
    for node_dir in reversed(node_dirs):
        load_manifest(node_dir)


# ── CLI ───────────────────────────────────────────────────────────────────────

def _cli():
    args = sys.argv[1:]
    if not args or args[0] in ("--help", "-h"):
        print(
            "Usage: python tools/query.py <key> [--payload <json>]\n"
            "       python tools/query.py --list\n\n"
            "  <key>              dot-notation key to resolve or dispatch\n"
            "  --payload <json>   JSON payload for registered handlers\n"
            "  --list             list all registered handlers\n"
        )
        return

    if args[0] == "--list":
        bootstrap()
        handlers = list_handlers()
        if not handlers:
            print("No handlers registered.")
            return
        print(f"Registered handlers ({len(handlers)}):\n")
        for h in handlers:
            print(f"  {h['name']}")
            if h["description"]:
                print(f"    {h['description']}")
            if h["schema"]:
                print(f"    schema: {h['schema']}")
        return

    key     = args[0]
    payload = {}
    i = 1
    while i < len(args):
        if args[i] == "--payload" and i + 1 < len(args):
            try:
                payload = json.loads(args[i + 1])
            except json.JSONDecodeError as e:
                print(f"Error parsing payload: {e}", file=sys.stderr)
                sys.exit(1)
            i += 1
        i += 1

    bootstrap()
    result = dispatch(key, payload)

    if result is None:
        print("None")
    elif isinstance(result, (dict, list)):
        print(json.dumps(result, indent=2))
    else:
        print(result)


if __name__ == "__main__":
    _cli()
