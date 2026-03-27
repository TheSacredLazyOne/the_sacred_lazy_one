#!/usr/bin/env python3
# tools/build_frame.py
# Pure driver — parse flags, load manifest, render bundle.
# Manifest owns the logic. Script owns the flags. Neither duplicates the other.
#
# Resolves node name from mesh_node.json, then loads [node]/scripts/manifest.py.
# Falls back to default_node directory mapping if no node-specific override exists.
#
# Usage:
#   python tools/build_frame.py [options]
#
# Flags:
#   --effluence / --no-effluence    include [node]/library/ (default: on)
#   --affluence / --no-affluence    include [node]/inbox/   (default: on)
#   --out <path>                    output path relative to repo root
#                                   (default: dist/<node>_frame_<label>.md)

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from textwrap import dedent
from typing import List

ROOT = Path(__file__).resolve().parents[1]


def _last_committed(src: Path) -> str:
    """Delegate to git_node.last_committed — git interface lives there."""
    import importlib.util as _ilu
    spec = _ilu.spec_from_file_location("git_node", ROOT / "tools" / "git_node.py")
    mod  = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.last_committed(src) or ""



def git_head() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT, stderr=subprocess.DEVNULL
        ).decode().strip()
    except Exception:
        return "unknown"


def load_mesh_node_json() -> dict:
    path = ROOT / "mesh_node.json"
    if not path.exists():
        print("Error: mesh_node.json not found at repo root.", file=sys.stderr)
        sys.exit(1)
    with open(path) as f:
        return json.load(f)


def resolve_node_dir(meta: dict, node_name: str) -> Path:
    """
    Resolve the tools directory for a node using reserved_directories.frame.
    Falls back to default_node mapping if no node-specific override exists.
    """
    frame = meta.get("reserved_directories", {}).get("frame", {})
    mapping = frame.get(node_name) or frame.get("default_node", {})
    scripts_template = mapping.get("scripts", {}).get("path", "[node]/scripts/")
    scripts_rel = scripts_template.replace("[node]", node_name)
    return ROOT / scripts_rel


def load_manifest(meta: dict, node_name: str):
    node_tools = resolve_node_dir(meta, node_name)
    manifest_path = node_tools / "manifest.py"
    if not manifest_path.exists():
        print(f"Error: manifest not found at {manifest_path}", file=sys.stderr)
        sys.exit(1)
    spec = importlib.util.spec_from_file_location("manifest", manifest_path)
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def relpath(p: Path) -> str:
    try:
        return str(p.relative_to(ROOT))
    except ValueError:
        return str(p)


def section_for(rel: str) -> str:
    parts = Path(rel).parts
    return parts[0] if parts else "root"


def dirkey(rel: str) -> str:
    return str(Path(rel).parent)


def render_file(src: Path) -> str:
    suffix = src.suffix.lower()
    rel    = relpath(src)
    try:
        text = src.read_text(encoding="utf-8")
    except Exception as e:
        return f"*[could not read {rel}: {e}]*\n\n"

    LANG = {
        ".json": "json",
        ".py":   "python",
        ".sh":   "bash",
        ".cpp":  "cpp",
        ".c":    "c",
        ".h":    "cpp",
        ".hpp":  "cpp",
        ".lua":  "lua",
    }
    if suffix in LANG:
        return f"```{LANG[suffix]}\n{text}\n```\n\n"
    else:
        # Remap headings so file content sits below bundle structure
        return remap_headings(text) + "\n\n"


def remap_headings(text: str, base_level: int = 4) -> str:
    """
    Remap markdown headings in file content so they sit below the bundle
    structure. Bundle uses #/##/### for section/directory/filename.
    File content headings start at base_level (default: ####).

    A # in the file becomes ####, ## becomes #####, etc.
    Non-heading lines are unchanged.
    """
    lines = []
    for line in text.splitlines():
        if line.startswith("#"):
            # Count leading # characters
            i = 0
            while i < len(line) and line[i] == "#":
                i += 1
            # Only remap if followed by space (actual heading, not just #s)
            if i < len(line) and line[i] == " ":
                new_level = base_level + (i - 1)
                line = "#" * new_level + line[i:]
        lines.append(line)
    return "\n".join(lines)


def bundle_label(flags: dict) -> str:
    parts = []
    if flags.get("affluence", True):
        parts.append("affluence")
    if flags.get("effluence", True):
        parts.append("effluence")
    return "_".join(parts) if parts else "minimal"


def parse_args() -> dict:
    args = sys.argv[1:]
    flags = {"effluence": True, "affluence": True, "out": None}
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--effluence":
            flags["effluence"] = True
        elif a == "--no-effluence":
            flags["effluence"] = False
        elif a == "--affluence":
            flags["affluence"] = True
        elif a == "--no-affluence":
            flags["affluence"] = False
        elif a == "--out" and i + 1 < len(args):
            flags["out"] = args[i + 1]
            i += 1
        elif a in ("--help", "-h"):
            print(dedent("""\
                Usage: python tools/build_frame.py [options]

                  --effluence        include [node]/library/ (default: on)
                  --no-effluence     exclude [node]/library/
                  --affluence        include [node]/inbox/   (default: on)
                  --no-affluence     exclude [node]/inbox/
                  --out <path>       output path (default: dist/<node>_frame_<label>.md)
            """))
            sys.exit(0)
        i += 1
    return flags


def dispatch_render(src: Path, mod) -> str:
    """
    Render a file to markdown. Defers to manifest.render_file(src, text)
    if present — allows nodes to handle file types build_frame does not know about.
    Falls back to build_frame's own render_file for all common types.
    """
    if hasattr(mod, "render_file"):
        try:
            text = src.read_text(encoding="utf-8")
        except Exception as e:
            return f"*[could not read {relpath(src)}: {e}]*\n\n"
        return mod.render_file(src, text)
    return render_file(src)


def main():
    flags = parse_args()
    meta  = load_mesh_node_json()
    # directory is the single entry point — fails loudly if absent
    node = meta.get("directory")
    if not node or not isinstance(node, str):
        print("Error: mesh_node.json missing 'directory' field.", file=sys.stderr)
        sys.exit(1)
    mod   = load_manifest(meta, node)

    out_files: List[Path] = mod.build_bundle(flags)

    label       = bundle_label(flags)
    default_out = f"{mod.artifact_dir()}/{mod.artifact_basename(label)}.md"
    out_rel     = flags["out"] or default_out
    out_path    = ROOT / out_rel
    out_path.parent.mkdir(parents=True, exist_ok=True)

    head = git_head()
    now  = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

    parts: List[str] = []
    parts.append(f"# Node: {mod.node_name()}\n\n")
    parts.append(f"> Repository: {mod.repository_url()}\n")
    parts.append(f"> Source commit: `{head}`\n")
    parts.append(f"> License: {mod.license_name()}\n")
    parts.append(f"> Frame schema: {mod.frame_schema()}\n")
    parts.append(f"> Generated: {now}\n")
    parts.append(f"> Bundle mode: `{label}`\n\n")

    current_section: str | None = None
    current_dir: str | None     = None

    for src in out_files:
        if not src.is_absolute():
            src = (ROOT / src).resolve()

        rel = relpath(src)
        sec = section_for(rel)
        dk  = dirkey(rel)

        # Root-level files (dirkey == ".") need no section or directory
        # header — the filename is sufficient. For all other files, emit
        # section and directory headers only when they change.
        if dk == ".":
            current_section = sec
            current_dir     = dk
        else:
            if sec != current_section:
                current_section = sec
                current_dir     = None
                parts.append(f"\n# {sec}\n\n")

            if dk != current_dir:
                current_dir = dk
                parts.append(f"\n## Directory: `{dk}`\n\n")

        parts.append("---\n\n")
        parts.append(f"### `{rel}`\n\n")
        date = _last_committed(src)
        if date:
            parts.append(f"> Last committed: {date}\n\n")
        parts.append(dispatch_render(src, mod))

    out_path.write_text("".join(parts), encoding="utf-8")
    print(f"Wrote {out_rel}")


if __name__ == "__main__":
    main()
