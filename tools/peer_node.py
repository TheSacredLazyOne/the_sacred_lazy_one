#!/usr/bin/env python3
# tools/peer_node.py
# Link an existing node or spawn a new one as a peer.
#
# Peers are horizontal — sovereign frames, no inheritance expected.
# Derivation is vertical — lineage, inheritance, merges back.
#
# Two modes:
#
#   --link   Register an existing node as a peer. Clones its repo into
#            peers/<name>/. Registers in [node]/node.json. No derivation.
#
#   --spawn  Create a new node derived from a fixed point in the mesh.
#            Defaults to mesh_node. Use --from <node> to specify a different
#            derivation point. The spawned node carries that lineage but is
#            not a child of this node — it is a lateral peer derived from
#            a shared ancestor. This is the collaboration mechanism:
#            two custodians derive from the same fixed point independently,
#            and the mesh can detect where their frames converged or diverged.
#
# Usage:
#   python tools/peer_node.py --link --name <n> --repository <url>
#   python tools/peer_node.py --spawn --name <n> [--from <node>] [--remote <url>]
#   python tools/peer_node.py --list
#   python tools/peer_node.py --update --name <n>
#   python tools/peer_node.py --update --all

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT      = Path(__file__).resolve().parents[1]
PEERS_DIR = ROOT / "peers"


# ── Git ───────────────────────────────────────────────────────────────────────

def git(cmd: list, cwd: Path = ROOT) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git"] + cmd, cwd=cwd,
        capture_output=True, text=True, check=False,
    )


def git_out(cmd: list, cwd: Path = ROOT) -> str:
    return git(cmd, cwd).stdout.strip()


# ── Node json helpers ─────────────────────────────────────────────────────────

def _load_mesh_node_json() -> dict:
    path = ROOT / "mesh_node.json"
    return json.loads(path.read_text()) if path.exists() else {}


def _highest_node_dir() -> Path:
    meta = _load_mesh_node_json()
    top  = meta.get("directory")
    if not isinstance(top, str):
        raise ValueError(
            f"mesh_node.json 'directory' must be a string, got {type(top).__name__}."
        )
    return ROOT / top


def _load_node_json() -> dict:
    path = _highest_node_dir() / "node.json"
    return json.loads(path.read_text()) if path.exists() else {}


def _save_node_json(data: dict):
    path = _highest_node_dir() / "node.json"
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


# ── Peer registration ─────────────────────────────────────────────────────────

def _register_peer(name: str, repository: str, spawned: bool, derived_from: str | None):
    node_json = _load_node_json()
    peers     = node_json.get("peers", [])

    # Check if already registered
    for p in peers:
        if p["name"] == name:
            print(f"  Peer '{name}' already registered.")
            return

    peers.append({
        "name":         name,
        "repository":   repository,
        "path":         f"peers/{name}/",
        "registered":   _now()[:10],
        "spawned":      spawned,
        "derived_from": derived_from,
    })
    node_json["peers"] = peers
    _save_node_json(node_json)
    print(f"  ✓ Registered peer: {name}")


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_link(name: str, repository: str):
    """Link an existing node as a peer."""
    peer_path = PEERS_DIR / name

    if peer_path.exists():
        print(f"  peers/{name}/ already exists — updating registration.")
    else:
        PEERS_DIR.mkdir(exist_ok=True)
        print(f"  Cloning {repository}...")
        r = subprocess.run(
            ["git", "clone", repository, str(peer_path)],
            capture_output=True, text=True, check=False,
        )
        if r.returncode != 0:
            print(f"  Error: {r.stderr.strip()}", file=sys.stderr)
            sys.exit(1)
        print(f"  ✓ Cloned to peers/{name}/")

    _register_peer(name, repository, spawned=False, derived_from=None)

    print(f"\n  Peer linked: {name}")
    print(f"  Pull updates with: python tools/peer_node.py --update --name {name}")


def cmd_spawn(name: str, derive_from: str, remote: str | None):
    """
    Spawn a new peer node derived from a fixed point in the mesh.
    derive_from is a node name — defaults to mesh_node.
    The new node is a lateral peer, not a child of this node.
    Two custodians deriving from the same fixed point can compare
    frames to detect convergence or divergence.
    """
    # Find the source repository for derive_from node
    from tools.query import resolve
    source_url = resolve("repository") if derive_from == "mesh_node" else None

    # Try to find the repository from the named node's node.json in peers/
    if not source_url:
        peer_node_json = PEERS_DIR / derive_from / "node.json"
        if peer_node_json.exists():
            source_url = json.loads(peer_node_json.read_text()).get("repository", "")

    if not source_url:
        # Fall back to mesh_node repository
        source_url = resolve("repository") or ""

    if not source_url:
        print(f"  Error: could not find repository for '{derive_from}'.", file=sys.stderr)
        sys.exit(1)

    peer_path = PEERS_DIR / name
    PEERS_DIR.mkdir(exist_ok=True)

    if peer_path.exists():
        print(f"  Error: peers/{name}/ already exists.", file=sys.stderr)
        sys.exit(1)

    print(f"  Spawning peer: {name}")
    print(f"  Deriving from: {derive_from} ({source_url})")
    if remote:
        print(f"  Remote:        {remote}")
    print()

    # Clone the source node
    r = subprocess.run(
        ["git", "clone", source_url, str(peer_path)],
        capture_output=True, text=True, check=False,
    )
    if r.returncode != 0:
        print(f"  Error: git clone failed: {r.stderr.strip()}", file=sys.stderr)
        sys.exit(1)
    print(f"  ✓ Cloned {derive_from} to peers/{name}/")

    # Ensure master branch
    current = git_out(["rev-parse", "--abbrev-ref", "HEAD"], peer_path)
    if current == "main":
        git(["branch", "-m", "main", "master"], peer_path)
        print("  ✓ Renamed branch: main → master")

    # Rename origin → source node name
    git(["remote", "rename", "origin", derive_from], peer_path)
    print(f"  ✓ Remote: origin → {derive_from}")

    # Add own remote if provided
    if remote:
        git(["remote", "add", "origin", remote], peer_path)
        print(f"  ✓ Remote: origin → {remote}")

    # Write node.json for the spawned peer
    parent_node_json_path = ROOT / derive_from / "node.json"
    parent_data = json.loads(parent_node_json_path.read_text()) if parent_node_json_path.exists() else {}

    spawned_node_json = {
        "node":         name,
        "repository":   remote or "",
        "license":      parent_data.get("license", "CC-BY-SA-4.0"),
        "custodians":   [],
        "description":  f"Peer node spawned from {derive_from}. Override this field.",
        "derived_from": derive_from,
        "peers":        [],
    }

    # Find the node directory (first directory in mesh_node.json of the peer)
    peer_mesh_json_path = peer_path / "mesh_node.json"
    if peer_mesh_json_path.exists():
        peer_meta = json.loads(peer_mesh_json_path.read_text())
        peer_dir = peer_meta.get("directory", derive_from)
        if not isinstance(peer_dir, str):
            peer_dir = derive_from
        node_dir  = peer_path / peer_dir
        node_dir.mkdir(exist_ok=True)
        (node_dir / "node.json").write_text(
            json.dumps(spawned_node_json, indent=2), encoding="utf-8"
        )
        print(f"  ✓ {peer_dirs[-1]}/node.json")

    # Stage
    git(["add", "-A"], peer_path)
    print("  ✓ Staged")

    # Register as peer of this node
    _register_peer(name, remote or source_url, spawned=True, derived_from=derive_from)

    print(f"\n  Peer spawned: {name}")
    print(f"  Fixed point:  {derive_from}")
    print(f"\n  cd {peer_path}")
    print(f"  git commit -m \"init — {name} spawned from {derive_from}\"")
    print(f"  git push -u origin master")
    print(f"\n  This node and {name} share the {derive_from} fixed point.")
    print(f"  Frames that diverge from here are measurable.")
    print(f"  Nothing here is final.")


def cmd_update(name: str | None, all_peers: bool):
    """Pull latest from one or all registered peers."""
    node_json = _load_node_json()
    peers     = node_json.get("peers", [])

    if not peers:
        print("No peers registered.")
        return

    targets = peers if all_peers else [p for p in peers if p["name"] == name]
    if not targets:
        print(f"Peer '{name}' not found.", file=sys.stderr)
        sys.exit(1)

    for peer in targets:
        peer_path = ROOT / peer["path"]
        if not peer_path.exists():
            print(f"  {peer['name']}: not cloned — run --link first")
            continue
        r = git(["pull"], peer_path)
        if r.returncode == 0:
            print(f"  ✓ {peer['name']}: updated")
        else:
            print(f"  ✗ {peer['name']}: {r.stderr.strip()}")


def cmd_list():
    """List registered peers."""
    node_json = _load_node_json()
    peers     = node_json.get("peers", [])
    if not peers:
        print("No peers registered.")
        return
    print(f"Peers ({len(peers)}):\n")
    for p in peers:
        spawned = "spawned" if p.get("spawned") else "linked"
        cloned  = "✓" if (ROOT / p["path"]).exists() else "✗"
        parent  = f" ← {p['derived_from']}" if p.get("derived_from") else ""
        print(f"  [{cloned}] {p['name']}  ({spawned}{parent})  {p.get('registered', '')}")
        print(f"       {p['repository']}")


# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args() -> dict:
    args  = sys.argv[1:]
    flags = {
        "cmd":     None,
        "name":    None,
        "repo":    None,
        "from":    "mesh_node",
        "remote":  None,
        "all":     False,
    }
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--link":
            flags["cmd"] = "link"
        elif a == "--spawn":
            flags["cmd"] = "spawn"
        elif a == "--update":
            flags["cmd"] = "update"
        elif a == "--list":
            flags["cmd"] = "list"
        elif a == "--name" and i + 1 < len(args):
            flags["name"] = args[i + 1]; i += 1
        elif a == "--repository" and i + 1 < len(args):
            flags["repo"] = args[i + 1]; i += 1
        elif a == "--from" and i + 1 < len(args):
            flags["from"] = args[i + 1]; i += 1
        elif a == "--remote" and i + 1 < len(args):
            flags["remote"] = args[i + 1]; i += 1
        elif a == "--all":
            flags["all"] = True
        elif a in ("--help", "-h"):
            print(
                "Usage: python tools/peer_node.py <command> [options]\n\n"
                "  --link --name <n> --repository <url>\n"
                "      Link an existing node as a peer\n\n"
                "  --spawn --name <n> [--from <node>] [--remote <url>]\n"
                "      Spawn a new node from a fixed point (default: mesh_node)\n\n"
                "  --update --name <n> | --all\n"
                "      Pull latest from peer(s)\n\n"
                "  --list\n"
                "      List registered peers\n"
            )
            sys.exit(0)
        i += 1
    return flags


def main():
    flags = parse_args()
    cmd   = flags["cmd"]

    if cmd == "link":
        if not flags["name"] or not flags["repo"]:
            print("Error: --link requires --name and --repository.", file=sys.stderr)
            sys.exit(1)
        cmd_link(flags["name"], flags["repo"])

    elif cmd == "spawn":
        if not flags["name"]:
            print("Error: --spawn requires --name.", file=sys.stderr)
            sys.exit(1)
        cmd_spawn(flags["name"], flags["from"], flags["remote"])

    elif cmd == "update":
        if not flags["all"] and not flags["name"]:
            print("Error: --update requires --name or --all.", file=sys.stderr)
            sys.exit(1)
        cmd_update(flags["name"], flags["all"])

    elif cmd == "list":
        cmd_list()

    else:
        print("Run 'python tools/peer_node.py --help' for usage.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
