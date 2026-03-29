#!/usr/bin/env python3
# tools/git_node.py
# Git interface and thinking state machine for mesh_node.
#
# Commands:
#   start_thinking    — open a thinking session
#   update_thinking   — stage and commit accumulated changes as thinking: wip
#   end_thinking      — generate delta against session-open HEAD, write delta.txt
#   finalize_thinking — squash thinking: commits, commit with reviewed message
#   change_mind       — open an earlier commit for revision on a rethinking/ branch
#   status            — report current thinking state
#
# Model routing is NOT this script's concern.
# end_thinking writes delta.txt and exits.
# The control script reads delta.txt, calls the model, writes commit_review.md.
# finalize_thinking reads commit_review.md and commits.
#
# State: .node_state/thinking (present = session open)
# .node_state/ is gitignored — ephemeral, never committed.
#
# Usage:
#   python tools/git_node.py <command> [options]

from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from textwrap import dedent

ROOT        = Path(__file__).resolve().parents[1]
STATE_DIR   = ROOT / ".node_state"
THINKING    = STATE_DIR / "thinking"
DELTA_FILE  = STATE_DIR / "delta.txt"
REVIEW_FILE = STATE_DIR / "commit_review.md"


# ── Git primitives ────────────────────────────────────────────────────────────

def git(cmd: list) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git"] + cmd,
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def git_out(cmd: list) -> str:
    return git(cmd).stdout.strip()


def is_git_repo() -> bool:
    return git(["rev-parse", "--git-dir"]).returncode == 0


def has_commits() -> bool:
    return git(["rev-parse", "HEAD"]).returncode == 0


def git_head() -> str:
    return git_out(["rev-parse", "--short", "HEAD"]) or "no-commits"


def git_head_full() -> str:
    return git_out(["rev-parse", "HEAD"]) or ""


def current_branch() -> str:
    return git_out(["rev-parse", "--abbrev-ref", "HEAD"])


def working_tree_dirty() -> bool:
    return bool(git(["status", "--porcelain"]).stdout.strip())


def staged_changes() -> bool:
    return git(["diff", "--cached", "--quiet"]).returncode != 0


def commit_exists(hash_: str) -> bool:
    return git(["cat-file", "-e", f"{hash_}^{{commit}}"]).returncode == 0


def commit_subject(hash_: str) -> str:
    return git_out(["log", "--format=%s", "-1", hash_])


def branch_exists(name: str) -> bool:
    return git(["rev-parse", "--verify", name]).returncode == 0


def last_committed(path) -> str:
    """
    Return the ISO 8601 date of the last commit that touched path.
    Returns empty string if the file has never been committed.

    Callable from build_frame.py, manifest.py, or any tool that needs
    git provenance without owning git logic directly.
    """
    from pathlib import Path as _Path
    p = _Path(path)
    try:
        rel = str(p.relative_to(ROOT)) if p.is_absolute() else str(p)
    except ValueError:
        rel = str(p)
    return git_out(["log", "--format=%ci", "-1", "--", rel])


# ── State ─────────────────────────────────────────────────────────────────────

def thinking_active() -> bool:
    return THINKING.exists()


def read_thinking_meta() -> dict:
    if not THINKING.exists():
        return {}
    try:
        return json.loads(THINKING.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_thinking_meta(meta: dict):
    STATE_DIR.mkdir(exist_ok=True)
    THINKING.write_text(json.dumps(meta, indent=2), encoding="utf-8")



# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_status():
    if not is_git_repo():
        print("Not a git repository.")
        return

    branch = current_branch()
    print(f"Repository: {ROOT}")
    print(f"Branch:     {branch}")
    print(f"HEAD:       {git_head()}")
    print(f"Dirty:      {'yes' if working_tree_dirty() else 'no'}")
    print(f"Staged:     {'yes' if staged_changes() else 'no'}")

    if branch.startswith("rethinking/"):
        print(f"\nMode:       CHANGE MIND in progress ({branch})")

    if thinking_active():
        meta   = read_thinking_meta()
        opened = meta.get("opened_at", "unknown")
        mode   = meta.get("mode", "thinking")
        print(f"\nThinking:   ACTIVE ({mode}, opened {opened})")
        if meta.get("origin_commit"):
            print(f"  Origin:   {meta['origin_commit'][:12]}")
            print(f"  Subject:  {meta.get('origin_subject', '')}")
        if DELTA_FILE.exists():
            lines = len(DELTA_FILE.read_text().splitlines())
            print(f"  Delta:    ready ({lines} lines)")
        if REVIEW_FILE.exists():
            print(f"  Review:   ready for finalize")
    else:
        print("\nThinking:   inactive")

    # Recent thinking: commits on this branch
    if has_commits():
        log = git_out(["log", "--oneline", "-10"])
        thinking_commits = [l for l in log.splitlines() if "thinking:" in l]
        if thinking_commits:
            print(f"\nThinking commits ({len(thinking_commits)}):")
            for line in thinking_commits:
                print(f"  {line}")


def cmd_start_thinking(note: str = ""):
    if not is_git_repo():
        print("Error: not a git repository.", file=sys.stderr)
        sys.exit(1)

    if thinking_active():
        meta = read_thinking_meta()
        print(
            f"Error: thinking session already active "
            f"(opened {meta.get('opened_at', 'unknown')}).",
            file=sys.stderr,
        )
        print(
            "Run 'update_thinking' to accumulate, or 'end_thinking' to close.",
            file=sys.stderr,
        )
        sys.exit(1)

    STATE_DIR.mkdir(exist_ok=True)

    now  = datetime.now(timezone.utc).isoformat(timespec="seconds")
    meta = {
        "mode":         "thinking",
        "opened_at":    now,
        "head_at_open": git_head_full(),
        "branch":       current_branch(),
        "note":         note,
    }
    write_thinking_meta(meta)

    print(f"Thinking session opened.")
    print(f"  Branch:  {meta['branch']}")
    print(f"  HEAD:    {meta['head_at_open'][:12] or 'none'}")
    print(f"  Opened:  {now}")
    if note:
        print(f"  Note:    {note}")
    print(f"\n  Make changes. Run 'update_thinking [note]' to accumulate.")
    print(f"  Run 'end_thinking' when ready to review and commit.")


def cmd_update_thinking(note: str = ""):
    if not is_git_repo():
        print("Error: not a git repository.", file=sys.stderr)
        sys.exit(1)

    if not thinking_active():
        print("No active thinking session — starting one now...")
        cmd_start_thinking(note)
        return

    git(["add", "-A"])

    if not staged_changes():
        print("Nothing staged — no changes to accumulate.")
        return

    now     = datetime.now(timezone.utc).strftime("%H:%M:%S")
    subject = f"thinking: {note}" if note else f"thinking: wip {now}"

    # Amend last thinking: commit to keep session clean,
    # otherwise create a new one.
    last = git_out(["log", "--format=%s", "-1"]) if has_commits() else ""
    if last.startswith("thinking:"):
        r = git(["commit", "--amend", "-m", subject])
    else:
        r = git(["commit", "-m", subject])

    if r.returncode == 0:
        print(f"  Accumulated: {subject}")
        print(f"  HEAD: {git_head()}")
    else:
        print(f"  Error: {r.stderr.strip()}", file=sys.stderr)
        sys.exit(1)


def cmd_end_thinking():
    if not is_git_repo():
        print("Error: not a git repository.", file=sys.stderr)
        sys.exit(1)

    if not thinking_active():
        print("Error: no active thinking session.", file=sys.stderr)
        sys.exit(1)

    # Stage and accumulate remaining changes
    git(["add", "-A"])
    if staged_changes():
        last = git_out(["log", "--format=%s", "-1"]) if has_commits() else ""
        if last.startswith("thinking:"):
            git(["commit", "--amend", "--no-edit"])
        else:
            git(["commit", "-m", "thinking: end accumulation"])

    # Generate delta from session-open HEAD to now
    meta         = read_thinking_meta()
    head_at_open = meta.get("head_at_open", "")

    if head_at_open and has_commits():
        current = git_head_full()
        if head_at_open == current:
            print("No commits since session opened — nothing to record.")
            return
        delta = git_out(["diff", f"{head_at_open}..HEAD"])
        if not delta:
            delta = git_out(["show", "HEAD"])
    elif has_commits():
        delta = git_out(["show", "HEAD"])
    else:
        print("No commits yet — nothing to record.")
        return

    if not delta.strip():
        print("No changes detected. Nothing to record.")
        return

    STATE_DIR.mkdir(exist_ok=True)
    DELTA_FILE.write_text(delta, encoding="utf-8")

    # Write bare review file — control script fills in the commit message
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    review = dedent(f"""\
        # Commit Review

        > Session opened:  {meta.get('opened_at', 'unknown')}
        > End thinking:    {now}
        > HEAD at open:    {head_at_open[:12] if head_at_open else 'none'}
        > HEAD now:        {git_head()}
        > Branch:          {current_branch()}
        > Delta:           {DELTA_FILE.name} ({len(delta.splitlines())} lines)

        ---

        ## Commit Message

        The control script should populate this block from the local model.
        Edit or replace before running `finalize_thinking`.

        ```
        # Replace this placeholder with your commit message.
        # First line: type(scope): summary — max 72 chars
        # Body: what changed and why. The diff is the argument.
        # Nothing here is final.
        ```

        ---

        *Review. Refine. Run `python tools/git_node.py finalize_thinking`.*
        *Nothing here is final.*
    """)
    REVIEW_FILE.write_text(review, encoding="utf-8")

    print(f"  Delta written:  {DELTA_FILE} ({len(delta.splitlines())} lines)")
    print(f"  Review written: {REVIEW_FILE}")
    print(f"\n  Waiting for control script:")
    print(f"    1. Read  {DELTA_FILE.name}")
    print(f"    2. Route to local model")
    print(f"    3. Write candidate message into {REVIEW_FILE.name}")
    print(f"  Then: python tools/git_node.py finalize_thinking")


def cmd_finalize_thinking(message_path: str | None = None):
    if not is_git_repo():
        print("Error: not a git repository.", file=sys.stderr)
        sys.exit(1)

    if not thinking_active():
        print("Error: no active thinking session.", file=sys.stderr)
        sys.exit(1)

    # Resolve commit message
    if message_path:
        p = Path(message_path)
        if not p.exists():
            print(f"Error: message file not found: {message_path}", file=sys.stderr)
            sys.exit(1)
        commit_message = p.read_text(encoding="utf-8").strip()
    elif REVIEW_FILE.exists():
        content = REVIEW_FILE.read_text(encoding="utf-8")
        match   = re.search(r"```\n(.*?)```", content, re.DOTALL)
        if match:
            commit_message = match.group(1).strip()
            if commit_message.startswith("#"):
                print(
                    f"Error: commit message placeholder not replaced.\n"
                    f"  Open {REVIEW_FILE} and write your commit message.",
                    file=sys.stderr,
                )
                sys.exit(1)
        else:
            print(f"Error: could not extract message from {REVIEW_FILE}.", file=sys.stderr)
            sys.exit(1)
    else:
        print(f"Error: no review file at {REVIEW_FILE}.", file=sys.stderr)
        print("Run 'end_thinking' first.", file=sys.stderr)
        sys.exit(1)

    if not commit_message:
        print("Error: commit message is empty.", file=sys.stderr)
        sys.exit(1)

    # Squash all thinking: commits back to session-open HEAD
    meta         = read_thinking_meta()
    head_at_open = meta.get("head_at_open", "")

    if head_at_open and has_commits():
        log = git_out(["log", "--format=%s", f"{head_at_open}..HEAD"])
        thinking_commits = [l for l in log.splitlines() if l.startswith("thinking:")]
    else:
        thinking_commits = []

    msg_tmp = STATE_DIR / "commit_message.txt"
    msg_tmp.write_text(commit_message, encoding="utf-8")

    if len(thinking_commits) > 1:
        print(f"  Squashing {len(thinking_commits)} thinking: commits...")
        r = git(["reset", "--soft", head_at_open])
        if r.returncode != 0:
            print(f"  Error during reset: {r.stderr.strip()}", file=sys.stderr)
            sys.exit(1)
        git(["add", "-A"])
        r = git(["commit", "-F", str(msg_tmp)])
    elif len(thinking_commits) == 1:
        r = git(["commit", "--amend", "-F", str(msg_tmp)])
    else:
        # No thinking: commits — just commit current state
        git(["add", "-A"])
        r = git(["commit", "-F", str(msg_tmp)])

    if r.returncode != 0:
        print(f"  Error: git commit failed: {r.stderr.strip()}", file=sys.stderr)
        sys.exit(1)

    final_head = git_head()
    print(f"  Committed: {final_head}")
    print(f"  Message:   {commit_message.splitlines()[0][:72]}")

    # If change_mind session, print merge instructions
    mode   = meta.get("mode", "thinfking")
    branch = current_branch()
    if mode == "change_mind":
        origin_branch = meta.get("origin_branch", "main")
        print(f"\n  Change of mind committed on: {branch}")
        print(f"  To merge back and surface the strain record:")
        print(f"    git checkout {origin_branch}")
        print(f"    git merge --no-ff {branch} -m 'merge: change of mind — {branch}'")
        print(f"\n  Merge conflicts are the strain record.")
        print(f"  Each conflict is a downstream position that depended on what changed.")
        print(f"  Resolve them. The resolution diff is the evidence the mind moved.")

    # Clean up state
    for f in [THINKING, DELTA_FILE, REVIEW_FILE, msg_tmp]:
        if f.exists():
            f.unlink()
    try:
        STATE_DIR.rmdir()
    except OSError:
        pass

    print(f"\n  Thinking session closed.")
    print(f"  HEAD: {final_head}")
    print(f"  The diff is the argument. The message is the reasoning.")
    print(f"  Nothing here is final.")


def cmd_change_mind(commit_hash: str):
    if not is_git_repo():
        print("Error: not a git repository.", file=sys.stderr)
        sys.exit(1)

    if thinking_active():
        meta = read_thinking_meta()
        print(
            f"Error: thinking session already active "
            f"(opened {meta.get('opened_at', 'unknown')}).",
            file=sys.stderr,
        )
        sys.exit(1)

    if not commit_exists(commit_hash):
        print(f"Error: commit not found: {commit_hash}", file=sys.stderr)
        sys.exit(1)

    if working_tree_dirty():
        print("Error: working tree has uncommitted changes.", file=sys.stderr)
        print("Commit or stash before changing your mind.", file=sys.stderr)
        sys.exit(1)

    subject       = commit_subject(commit_hash)
    origin_branch = current_branch()
    short_hash    = commit_hash[:12]
    branch_name   = f"rethinking/{short_hash}"

    if branch_exists(branch_name):
        print(f"Error: branch '{branch_name}' already exists.", file=sys.stderr)
        print("A change-of-mind session for this commit is already open.", file=sys.stderr)
        sys.exit(1)

    print(f"Opening commit for revision:")
    print(f"  Hash:    {short_hash}")
    print(f"  Subject: {subject}")
    print(f"  Branch:  {branch_name}")
    print()

    r = git(["checkout", "-b", branch_name, commit_hash])
    if r.returncode != 0:
        print(f"  Error: {r.stderr.strip()}", file=sys.stderr)
        sys.exit(1)

    print(f"  Checked out to {branch_name}")

    STATE_DIR.mkdir(exist_ok=True)

    now  = datetime.now(timezone.utc).isoformat(timespec="seconds")
    meta = {
        "mode":           "change_mind",
        "opened_at":      now,
        "head_at_open":   git_head_full(),
        "branch":         branch_name,
        "origin_branch":  origin_branch,
        "origin_commit":  commit_hash,
        "origin_subject": subject,
    }
    write_thinking_meta(meta)

    print(f"\n  Thinking session opened in change-of-mind mode.")
    print(f"  Branch:  {branch_name}")
    print(f"  Revising: {subject}")
    print(f"\n  Edit the files. Run 'update_thinking [note]' to accumulate.")
    print(f"  Run 'end_thinking' when ready. Control script generates message.")
    print(f"  Run 'finalize_thinking' to commit the revision.")
    print(f"\n  Then merge back:")
    print(f"    git checkout {origin_branch}")
    print(f"    git merge --no-ff {branch_name}")
    print(f"\n  Merge conflicts are the strain record.")
    print(f"  The branch is the aside. The merge commit is the conclusion.")
    print(f"  Nothing here is final.")


def cmd_pull_parent(parent_name: str | None):
    """
    Fetch and merge a named parent node into the current branch.

    Reads the derived_from chain from [node]/node.json to find the
    default parent if none is specified. Uses --no-ff to preserve the
    merge commit — the merge event is a record in the corpus.

    Conflicts surface positions that diverged from the parent and need
    explicit resolution. The resolution diff is the evidence of what
    changed and why.

    Usage:
        python tools/git_node.py pull_parent
        python tools/git_node.py pull_parent mesh_node
    """
    if not is_git_repo():
        print("Error: not a git repository.", file=sys.stderr)
        sys.exit(1)

    # Resolve parent name from node.json if not supplied
    if not parent_name:
        import json as _json
        meta   = _load_mesh_node_json()
        node   = meta.get("directory", "")
        npath  = ROOT / node / "node.json"
        if npath.exists():
            parent_name = _json.loads(npath.read_text()).get("derived_from")
        if not parent_name:
            print("Error: no parent name given and derived_from not set in node.json.", file=sys.stderr)
            sys.exit(1)

    # Confirm the remote exists
    remotes = git_out(["remote"]).splitlines()
    if parent_name not in remotes:
        print(f"Error: remote '{parent_name}' not found.", file=sys.stderr)
        print(f"Available remotes: {', '.join(remotes)}", file=sys.stderr)
        print(f"Add it with: git remote add {parent_name} <url>", file=sys.stderr)
        sys.exit(1)

    print(f"Fetching {parent_name}...")
    r = git(["fetch", parent_name])
    if r.returncode != 0:
        print(f"  Error: {r.stderr.strip()}", file=sys.stderr)
        sys.exit(1)
    print(f"  ✓ fetched {parent_name}")

    # Check if already up to date
    _npath = ROOT / _load_mesh_node_json().get("directory", "") / "node.json"
    import json as _json
    _node_data = _json.loads(_npath.read_text()) if _npath.exists() else {}
    sovereign = _node_data.get("sovereign_branch", "master")
    merge_base = git_out(["merge-base", "HEAD", f"{parent_name}/{sovereign}"])
    parent_head = git_out(["rev-parse", f"{parent_name}/{sovereign}"])

    if merge_base == parent_head:
        print(f"  ✓ already up to date with {parent_name}/{sovereign}")
        print(f"\n  The merge commit is the record. Nothing here is final.")
        return
    print(f"  returncode: {r.returncode}\n  stderr: {r.stderr.strip()}") 
    if r.returncode != 0:
        print(f"\n  Merge conflicts detected.")
        print(f"  Resolve them — each conflict is a position that diverged from {parent_name}.")
        print(f"  The resolution diff is the evidence of what changed and why.")
        print(f"\n  When resolved:")
        print(f"    git add -A")
        print(f"    git commit")
    else:
        print(f"  ✓ merged {parent_name}/master")
        print(f"\n  The merge commit is the record. Nothing here is final.")


def _load_mesh_node_json() -> dict:
    path = ROOT / "mesh_node.json"
    return json.loads(path.read_text()) if path.exists() else {}


# ── Entry point ───────────────────────────────────────────────────────────────

def parse_args() -> tuple[str, list, dict]:
    args = sys.argv[1:]
    if not args:
        print(dedent("""\
            Usage: python tools/git_node.py <command> [options]

            Commands:
              start_thinking [note]           open a thinking session
              update_thinking [note]          stage and commit as thinking: wip
              end_thinking                    generate delta, write review file
              finalize_thinking               squash, commit with reviewed message
              change_mind <commit-hash>       open earlier commit for revision
              pull_parent [name]              fetch and merge a parent node
              status                          report current state

            Options:
              finalize_thinking --message <path>   use message from file

            Flow:
              end_thinking writes .node_state/delta.txt and exits.
              Control script reads delta.txt → model → commit_review.md.
              finalize_thinking reads commit_review.md → squash → commit.

            change_mind flow:
              Opens rethinking/<hash> branch at target commit.
              Revise, end_thinking, finalize_thinking.
              Merge back — conflicts are the strain record.
              Branch is the aside. Merge commit is the conclusion.
        """))
        sys.exit(0)

    command    = args[0]
    positional = []
    flags      = {}
    i = 1
    while i < len(args):
        a = args[i]
        if a == "--message" and i + 1 < len(args):
            flags["message"] = args[i + 1]
            i += 1
        else:
            positional.append(a)
        i += 1

    return command, positional, flags


def main():
    command, positional, flags = parse_args()

    if command == "status":
        cmd_status()
    elif command == "start_thinking":
        cmd_start_thinking(positional[0] if positional else "")
    elif command == "update_thinking":
        cmd_update_thinking(positional[0] if positional else "")
    elif command == "end_thinking":
        cmd_end_thinking()
    elif command == "finalize_thinking":
        cmd_finalize_thinking(message_path=flags.get("message"))
    elif command == "change_mind":
        if not positional:
            print("Error: change_mind requires a commit hash.", file=sys.stderr)
            sys.exit(1)
        cmd_change_mind(positional[0])
    elif command == "pull_parent":
        cmd_pull_parent(positional[0] if positional else None)
    else:
        print(f"Error: unknown command '{command}'.", file=sys.stderr)
        print("Run 'python tools/git_node.py' for usage.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
