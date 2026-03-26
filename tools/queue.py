#!/usr/bin/env python3
# tools/queue.py
# Simple file-based message queue for node communication.
#
# Stateless — each invocation reads from the queue, processes one message,
# writes the result. No persistent process required. Parallelism and
# distribution are the infrastructure's concern, not the node's.
#
# Queue directory: .node_state/queue/ (gitignored)
# Messages are JSON files: <timestamp>_<id>.json
# Results are written alongside: <timestamp>_<id>.result.json
# Processed messages move to: .node_state/queue/processed/
#
# Message format:
#   {
#     "id":       "uuid",
#     "query":    "nabla.generate",
#     "payload":  { ... },
#     "source":   "mastodon|cli|node:<name>",
#     "created":  "2026-03-22T...",
#     "reply_to": "optional return address"
#   }
#
# Result format:
#   {
#     "id":        "uuid matching message id",
#     "query":     "nabla.generate",
#     "result":    <any>,
#     "completed": "2026-03-22T...",
#     "error":     null or "error message"
#   }
#
# Usage:
#   python tools/queue.py enqueue --query <q> [--payload <json>] [--source <s>]
#   python tools/queue.py process          — process one pending message
#   python tools/queue.py process --all    — process all pending messages
#   python tools/queue.py status           — show queue depth and state
#   python tools/queue.py list             — list pending messages

from __future__ import annotations

import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT       = Path(__file__).resolve().parents[1]
QUEUE_DIR  = ROOT / ".node_state" / "queue"
PROC_DIR   = QUEUE_DIR / "processed"


# ── Queue primitives ──────────────────────────────────────────────────────────

def _ensure_dirs():
    QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    PROC_DIR.mkdir(parents=True, exist_ok=True)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _pending() -> list[Path]:
    if not QUEUE_DIR.exists():
        return []
    return sorted([
        p for p in QUEUE_DIR.iterdir()
        if p.is_file()
        and p.suffix == ".json"
        and not p.stem.endswith(".result")
    ])


# ── Public API ────────────────────────────────────────────────────────────────

def enqueue(
    query:    str,
    payload:  dict | None = None,
    source:   str = "cli",
    reply_to: str | None = None,
) -> str:
    """
    Add a message to the queue. Returns the message id.
    """
    _ensure_dirs()
    msg_id    = str(uuid.uuid4())[:8]
    timestamp = _now().replace(":", "").replace("-", "")[:15]
    filename  = f"{timestamp}_{msg_id}.json"

    message = {
        "id":       msg_id,
        "query":    query,
        "payload":  payload or {},
        "source":   source,
        "created":  _now(),
        "reply_to": reply_to,
    }

    (QUEUE_DIR / filename).write_text(
        json.dumps(message, indent=2), encoding="utf-8"
    )
    return msg_id


def process_one() -> dict | None:
    """
    Process the oldest pending message. Returns the result dict or None.
    Moves processed message to processed/ directory.
    """
    # Import here to avoid circular dependency
    from tools.query import dispatch, bootstrap
    bootstrap()

    pending = _pending()
    if not pending:
        return None

    msg_path = pending[0]
    message  = json.loads(msg_path.read_text(encoding="utf-8"))

    error  = None
    result = None
    try:
        result = dispatch(message["query"], message.get("payload", {}))
    except Exception as e:
        error = str(e)

    result_doc = {
        "id":        message["id"],
        "query":     message["query"],
        "result":    result,
        "completed": _now(),
        "error":     error,
    }

    # Write result alongside message
    result_path = msg_path.with_suffix(".result.json")
    result_path.write_text(json.dumps(result_doc, indent=2), encoding="utf-8")

    # Move message and result to processed/
    msg_path.rename(PROC_DIR / msg_path.name)
    result_path.rename(PROC_DIR / result_path.name)

    return result_doc


def process_all() -> list[dict]:
    """Process all pending messages. Returns list of result dicts."""
    results = []
    while True:
        result = process_one()
        if result is None:
            break
        results.append(result)
    return results


def status() -> dict:
    """Return queue depth and state."""
    pending   = _pending()
    processed = list(PROC_DIR.glob("*.json")) if PROC_DIR.exists() else []
    return {
        "pending":   len(pending),
        "processed": len([p for p in processed if not p.stem.endswith(".result")]),
        "queue_dir": str(QUEUE_DIR),
    }


# ── CLI ───────────────────────────────────────────────────────────────────────

def _cli():
    args = sys.argv[1:]
    if not args or args[0] in ("--help", "-h"):
        print(
            "Usage: python tools/queue.py <command> [options]\n\n"
            "  enqueue --query <q> [--payload <json>] [--source <s>]\n"
            "  process [--all]\n"
            "  status\n"
            "  list\n"
        )
        return

    cmd = args[0]

    if cmd == "enqueue":
        query   = None
        payload = {}
        source  = "cli"
        i = 1
        while i < len(args):
            if args[i] == "--query" and i + 1 < len(args):
                query = args[i + 1]; i += 1
            elif args[i] == "--payload" and i + 1 < len(args):
                payload = json.loads(args[i + 1]); i += 1
            elif args[i] == "--source" and i + 1 < len(args):
                source = args[i + 1]; i += 1
            i += 1
        if not query:
            print("Error: --query required.", file=sys.stderr)
            sys.exit(1)
        msg_id = enqueue(query, payload, source)
        print(f"Enqueued: {msg_id}")

    elif cmd == "process":
        all_flag = "--all" in args
        if all_flag:
            results = process_all()
            print(f"Processed {len(results)} messages.")
            for r in results:
                status_str = "error" if r["error"] else "ok"
                print(f"  [{status_str}] {r['query']} → {r['id']}")
        else:
            result = process_one()
            if result is None:
                print("Queue empty.")
            else:
                status_str = "error" if result["error"] else "ok"
                print(f"[{status_str}] {result['query']}")
                if result["error"]:
                    print(f"  Error: {result['error']}")
                elif result["result"] is not None:
                    if isinstance(result["result"], (dict, list)):
                        print(json.dumps(result["result"], indent=2))
                    else:
                        print(f"  {result['result']}")

    elif cmd == "status":
        s = status()
        print(f"Pending:   {s['pending']}")
        print(f"Processed: {s['processed']}")
        print(f"Queue dir: {s['queue_dir']}")

    elif cmd == "list":
        pending = _pending()
        if not pending:
            print("Queue empty.")
            return
        print(f"Pending messages ({len(pending)}):\n")
        for p in pending:
            msg = json.loads(p.read_text(encoding="utf-8"))
            print(f"  {msg['id']}  {msg['query']}  [{msg['source']}]  {msg['created']}")

    else:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    _cli()
