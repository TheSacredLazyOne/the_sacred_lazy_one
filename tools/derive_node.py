#!/usr/bin/env python3
# tools/derive_node.py
# Derive a new node from this one.
#
# Creates a sibling repository (same parent directory as this repo),
# clones the source repo from the URL in mesh_node.json, then sets up
# the derived node structure on top of that foundation.
#
# Branch convention: master — not main.
# Master carries its lineage from the music industry: the master tape
# is the definitive reference recording, the copy everything downstream
# is pressed from. That meaning is load-bearing here. The master branch
# is the integrated position. Rethinking branches diverge from it and
# return to it. Derived nodes pull upstream changes from the mesh_node
# remote into their own master.
#
# Usage:
#   python tools/derive_node.py --name <node_name> [--remote <url>]
#
# What it does:
#   1. Reads mesh_node.json for source repository URL and conventions
#   2. Creates ../<node_name>/ (sibling to this repo)
#   3. git clone <source_url> into that directory
#   4. Renames origin remote to mesh_node (for pulling parent updates)
#   5. Adds ancestor remotes from derived_from chain
#   6. Adds new node's own remote as origin if provided
#   7. Sets up <node_name>/ subdirectory with manifest stub
#   8. Creates inbox/ and library/ directories
#   9. Writes derived mesh_node.json with full derived_from chain
#  10. Creates <node_name>/README.md stub
#  11. Adds Inheritance section to root README.md
#  12. Stages all changes
#  13. Generates delta to .node_state/derive_delta.txt
#  14. Prompts custodian for first commit and push
#
# What it does NOT do:
#   - Does not commit on your behalf
#   - Does not store credentials
#   - Does not run ingestion or training

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from textwrap import dedent

ROOT = Path(__file__).resolve().parents[1]


def load_mesh_node_json() -> dict:
    path = ROOT / "mesh_node.json"
    with open(path) as f:
        return json.load(f)


def git(cmd: list, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git"] + cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def git_out(cmd: list, cwd: Path) -> str:
    return git(cmd, cwd).stdout.strip()


def resolve_frame_dirs(meta: dict, node_name: str) -> dict:
    frame   = meta.get("reserved_directories", {}).get("frame", {})
    mapping = frame.get(node_name) or frame.get("default_node", {})
    return {
        key: val.get("path", f"[node]/{key}/").replace("[node]", node_name)
        for key, val in mapping.items()
        if isinstance(val, dict) and "path" in val
    }


def collect_ancestors(meta: dict) -> list[dict]:
    chain = []
    node  = meta
    while node:
        chain.append({
            "name":       node.get("name", ""),
            "repository": node.get("repository", ""),
        })
        node = node.get("derived_from")
    chain.reverse()
    return chain


def stub_manifest(node_name: str, parent_meta: dict) -> str:
    license_val = parent_meta.get("license", "CC-BY-SA-4.0")
    return dedent(f'''\
        # {node_name}/scripts/manifest.py
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
            return "{node_name}"


        def repository_url() -> str:
            import json as _json
            nj = _json.loads((NODE_DIR / "node.json").read_text())
            return nj.get("repository", "")


        def license_name() -> str:
            return "{license_val}"


        def frame_schema() -> str:
            return "mesh_node/v0.0.0"


        def artifact_dir() -> str:
            return "dist"


        def artifact_basename(label: str) -> str:
            return f"{node_name}_frame_{{label}}"


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
                return (meta.get("reserved_directories", {{}})
                            .get("root", {{}})
                            .get("venv", {{}})
                            .get("requirements", []))


        def python_min() -> str:
            try:
                from tools.query import resolve
                return resolve("venv.python_min") or "3.11"
            except ImportError:
                import json as _json
                meta = _json.loads((ROOT / "mesh_node.json").read_text())
                return (meta.get("reserved_directories", {{}})
                            .get("root", {{}})
                            .get("venv", {{}})
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
                frame   = meta.get("reserved_directories", {{}}).get("frame", {{}})
                mapping = frame.get("{node_name}") or frame.get("default_node", {{}})
                rel     = mapping.get(key, {{}}).get("path", default)
                rel     = rel.replace("[node]", "{node_name}")
                return ROOT / rel
            except Exception:
                return ROOT / default


        def build_bundle(flags: dict) -> List[Path]:
            """
            Build deduplicated file list for the frame bundle.

            Always included:
              - mesh_node.json
              - README.md
              - {node_name}/node.json
              - {node_name}/epistemic_floor.md (if present)
              - tools/*.py / tools/*.sh
              - {node_name}/scripts/*.py

            Included by default (--effluence, default on):
              - {node_name}/library/

            Included by default (--affluence, default on):
              - {node_name}/inbox/
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
                    _resolve_frame_path("effluence", "{node_name}/library/")
                )

            if flags.get("affluence", True):
                items += _md_files(
                    _resolve_frame_path("affluence", "{node_name}/inbox/")
                )

            seen: set = set()
            out: List[Path] = []
            for p in items:
                rp = p.resolve()
                if rp not in seen and p.exists():
                    seen.add(rp)
                    out.append(p)

            return out
    ''')


def stub_readme(node_name: str, parent_name: str, parent_repo: str) -> str:
    return dedent(f"""\
        # {node_name}

        Derived from [{parent_name}]({parent_repo}).

        *Nothing here is final.*
    """)


def parse_args() -> dict:
    args  = sys.argv[1:]
    flags = {"name": None, "remote": None}
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--name" and i + 1 < len(args):
            flags["name"] = args[i + 1]; i += 1
        elif a == "--remote" and i + 1 < len(args):
            flags["remote"] = args[i + 1]; i += 1
        elif a in ("--help", "-h"):
            print(dedent("""\
                Usage: python tools/derive_node.py --name <n> [--remote <url>]

                  --name <n>       name for the new node
                  --remote <url>   git remote URL for the new node (optional)
            """))
            sys.exit(0)
        i += 1

    if not flags["name"]:
        print("Error: --name is required.", file=sys.stderr)
        sys.exit(1)

    return flags


def main():
    flags      = parse_args()
    node_name  = flags["name"]
    remote     = flags["remote"]
    parent     = load_mesh_node_json()
    import sys as _sys
    if str(ROOT) not in _sys.path:
        _sys.path.insert(0, str(ROOT))
    from tools.query import dispatch, bootstrap
    bootstrap()
    source_url = dispatch("node.repository") or ""
    out_path   = ROOT.parent / node_name

    print(f"\nDeriving node: {node_name}")
    print(f"Source:        {source_url}")
    print(f"Output:        {out_path}")
    if remote:
        print(f"Remote:        {remote}")
    print()

    if not source_url:
        print("Error: mesh_node.json has no repository URL.", file=sys.stderr)
        sys.exit(1)

    if out_path.exists():
        print(f"Error: {out_path} already exists.", file=sys.stderr)
        sys.exit(1)

    # ── 1. Clone source repo ──────────────────────────────────────────────────

    print("  Cloning source repository...")
    r = subprocess.run(
        ["git", "clone", source_url, str(out_path)],
        capture_output=True, text=True, check=False,
    )
    if r.returncode != 0:
        print(f"  Error: git clone failed: {r.stderr.strip()}", file=sys.stderr)
        sys.exit(1)
    print(f"  ✓ cloned to {out_path}")

    # Ensure we are on master
    current = git_out(["rev-parse", "--abbrev-ref", "HEAD"], out_path)
    if current == "main":
        git(["branch", "-m", "main", "master"], out_path)
        print("  ✓ renamed branch: main → master")
    elif current != "master":
        git(["checkout", "-b", "master"], out_path)
        print("  ✓ created branch: master")

    # ── 2. Rename origin → mesh_node, add remotes ─────────────────────────────

    git(["remote", "rename", "origin", parent["name"]], out_path)
    print(f"  ✓ remote: origin → {parent['name']}")

    ancestors = collect_ancestors(parent)
    added     = {parent["name"]}
    for anc in ancestors:
        if anc["name"] not in added and anc["repository"]:
            git(["remote", "add", anc["name"], anc["repository"]], out_path)
            print(f"  ✓ remote: {anc['name']} → {anc['repository']}")
            added.add(anc["name"])

    if remote:
        git(["remote", "add", "origin", remote], out_path)
        print(f"  ✓ remote: origin → {remote}")

    # ── 3. Create node directory structure ────────────────────────────────────

    dirs = resolve_frame_dirs(parent, node_name)
    for rel_path in dirs.values():
        (out_path / rel_path).mkdir(parents=True, exist_ok=True)
        print(f"  ✓ {rel_path}")

    # ── 4. Write derived mesh_node.json and [node]/node.json ─────────────────

    # mesh_node.json — structural bootstrap only.
    # directory is a single string: the highest node in this repo.
    # The integrated node (mesh_node) is never aware of what derives from it.
    # Type is enforced as string — no lists, no creep.
    new_mesh_meta = dict(parent)
    new_mesh_meta.pop("directories", None)  # remove if inherited as list
    new_mesh_meta["directory"] = node_name

    (out_path / "mesh_node.json").write_text(
        json.dumps(new_mesh_meta, indent=2), encoding="utf-8"
    )
    print("  ✓ mesh_node.json")

    # [node]/node.json — node-specific identity, resolved via query chain
    node_dir = out_path / node_name
    node_dir.mkdir(parents=True, exist_ok=True)

    # Load parent node.json for defaults
    parent_node_json_path = out_path / parent.get("name", "mesh_node") / "node.json"
    parent_node_data = json.loads(parent_node_json_path.read_text()) if parent_node_json_path.exists() else {}

    new_node_json = {
        "node":         node_name,
        "repository":   remote or "",
        "license":      parent_node_data.get("license", "CC-BY-SA-4.0"),
        "custodians":   [],
        "description":  f"Derived from {parent.get('name', 'mesh_node')}. Override this field.",
        "derived_from": parent.get("name", "mesh_node"),
        "peers":        [],
    }

    (node_dir / "node.json").write_text(
        json.dumps(new_node_json, indent=2), encoding="utf-8"
    )
    print(f"  ✓ {node_name}/node.json")

    # ── 5. Stub manifest ──────────────────────────────────────────────────────

    scripts_path = out_path / dirs.get("scripts", f"{node_name}/scripts/")
    scripts_path.mkdir(parents=True, exist_ok=True)
    (scripts_path / "manifest.py").write_text(
        stub_manifest(node_name, parent), encoding="utf-8"
    )
    print(f"  ✓ {node_name}/scripts/manifest.py")

    # ── 6. Node README stub ───────────────────────────────────────────────────

    node_readme = out_path / node_name / "README.md"
    node_readme.write_text(
        stub_readme(node_name, parent["name"], source_url),
        encoding="utf-8",
    )
    print(f"  ✓ {node_name}/README.md")

    # ── 7. Update root README.md — append self-link to Inheritance section ──────

    root_readme = out_path / "README.md"
    if root_readme.exists():
        rc        = root_readme.read_text(encoding="utf-8")
        self_link = f"- [{node_name}]({node_name}/README.md)"
        if self_link not in rc:
            if "## Inheritance" in rc:
                lines     = rc.splitlines()
                insert_at = None
                in_section = False
                for i, line in enumerate(lines):
                    if line.strip() == "## Inheritance":
                        in_section = True
                        continue
                    if in_section and (line.startswith("## ") or line.startswith("---")):
                        insert_at = i
                        break
                if insert_at is not None:
                    lines.insert(insert_at, "")
                    lines.insert(insert_at, self_link)
                else:
                    lines.append("")
                    lines.append(self_link)
                rc = "\n".join(lines) + "\n"
            else:
                rc += f"\n---\n\n## Inheritance\n\n{self_link}\n"
            root_readme.write_text(rc, encoding="utf-8")
            print(f"  ✓ README.md — {node_name} added to Inheritance")

    # ── 8. Stage all changes ──────────────────────────────────────────────────

    git(["add", "-A"], out_path)
    print("  ✓ staged")

    # ── 9. Generate derive delta ──────────────────────────────────────────────

    state_dir  = out_path / ".node_state"
    state_dir.mkdir(exist_ok=True)
    delta      = git_out(["diff", "--cached"], out_path)
    if not delta:
        delta  = git_out(["status", "--short"], out_path)
    delta_path = state_dir / "derive_delta.txt"
    delta_path.write_text(delta, encoding="utf-8")
    print(f"  ✓ derive delta → {delta_path}")

    # ── 10. Prompt custodian ──────────────────────────────────────────────────

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    print(dedent(f"""
  Derivation complete: {node_name}
  Derived from:        {parent['name']}
  Time:                {now}

  Review the derive delta:
    cat {delta_path}

  Then commit and push:
    cd {out_path}
    git commit -m "init — {node_name} derived from {parent['name']}"
    git push -u origin master

  master — not main. The master branch is the definitive reference
  state everything downstream is pressed from. Pull parent updates via:
    git pull {parent['name']} master

  The diff is the argument. The message is the reasoning.
  Nothing here is final.
    """))


if __name__ == "__main__":
    main()
