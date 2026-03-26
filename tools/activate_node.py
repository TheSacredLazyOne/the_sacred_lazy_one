#!/usr/bin/env python3
# tools/activate_node.py
# Set up and activate the Python virtual environment for this node.
#
# Run this any time you want to engage the node. It detects whether
# the environment needs to be created or updated, and handles both.
# If the environment is already current, it reports ready status.
#
# Requirements are declared in mesh_node.json and provided by
# manifest.requirements() — derived nodes inject their own requirements
# automatically by extending the parent chain.
#
# Model cache is reported, not downloaded automatically. The custodian
# decides where models live:
#   --global   use HuggingFace cache (default, good before training)
#   --local    download to model/ directory (for training runs)
#
# Usage:
#   python tools/activate_node.py [--local | --global]
#
# Since a child process cannot activate a shell, this script prints
# the source command. Wrap it for convenience:
#   source <(python tools/activate_node.py --print-activate)

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# ROOT must be on sys.path before any tools.* imports.
# The .pth file handles this once the venv exists — this covers
# the bootstrap case where the venv doesn't exist yet.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ── Bootstrap — re-exec with correct Python if needed ────────────────────────
# Runs before anything else. If the current interpreter is too old,
# finds a suitable Python and replaces this process with it via os.execv.
# The script restarts transparently with the correct interpreter.

def _bootstrap_python(min_version: str = "3.11"):
    required = tuple(int(x) for x in min_version.split(".")[:2])
    if sys.version_info[:2] >= required:
        return  # already correct, continue

    import shutil

    def _check(python: str) -> bool:
        try:
            r = subprocess.run(
                [python, "-c",
                 "import sys; v=sys.version_info; print(f'{v.major}.{v.minor}')"],
                capture_output=True, text=True, timeout=5, check=False,
            )
            if r.returncode == 0:
                v = tuple(int(x) for x in r.stdout.strip().split(".")[:2])
                return v >= required
        except Exception:
            pass
        return False

    candidates = []

    # PATH candidates
    major, minor = required
    for m in range(minor, minor + 5):
        for name in [f"python3.{m}", f"python{major}.{m}"]:
            found = shutil.which(name)
            if found:
                candidates.append(found)

    # pyenv versions
    pyenv_root = Path.home() / ".pyenv" / "versions"
    if pyenv_root.exists():
        for entry in sorted(pyenv_root.iterdir(), reverse=True):
            for py_name in ["python3", "python"]:
                py = entry / "bin" / py_name
                if py.exists():
                    candidates.append(str(py))

    for candidate in candidates:
        if _check(candidate):
            print(f"  Re-launching with {candidate}...")
            os.execv(candidate, [candidate] + sys.argv)

    # Nothing found
    print(
        f"\nError: Python {min_version}+ required, "
        f"current is {sys.version.split()[0]}\n"
        f"\nTo install:\n"
        f"  pyenv install {min_version}\n"
        f"  pyenv local {min_version}\n",
        file=sys.stderr,
    )
    sys.exit(1)


_bootstrap_python("3.11")

# ─────────────────────────────────────────────────────────────────────────────


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_manifest():
    spec = importlib.util.spec_from_file_location(
        "manifest", ROOT / "mesh_node.json"
    )
    # Load the node's manifest.py via mesh_node.json name resolution
    meta      = json.loads((ROOT / "mesh_node.json").read_text())
    # directory is the single entry point — fails loudly if absent
    node_name = meta.get("directory")
    if not node_name or not isinstance(node_name, str):
        print("Error: mesh_node.json missing 'directory' field.", file=sys.stderr)
        sys.exit(1)
    frame       = meta.get("reserved_directories", {}).get("frame", {})
    mapping     = frame.get(node_name) or frame.get("default_node", {})
    scripts_rel = mapping.get("scripts", {}).get("path", f"{node_name}/scripts/")
    scripts_rel = scripts_rel.replace("[node]", node_name)
    manifest_path = ROOT / scripts_rel / "manifest.py"

    spec = importlib.util.spec_from_file_location("manifest", manifest_path)
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def version_tuple(version_str: str) -> tuple:
    return tuple(int(x) for x in version_str.split(".")[:2])


def find_python(min_version: str) -> Path:
    """
    Find a suitable Python interpreter meeting min_version.
    Searches in order:
      1. sys.executable (current interpreter)
      2. python3.X candidates on PATH and common locations
      3. pyenv versions directory
    Returns the path to a suitable interpreter, or exits with a clear message.
    """
    import shutil
    required = version_tuple(min_version)

    def check_interpreter(python_path: str) -> tuple[bool, tuple]:
        try:
            result = subprocess.run(
                [python_path, "-c",
                 "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"],
                capture_output=True, text=True, check=False, timeout=5,
            )
            if result.returncode == 0:
                v = version_tuple(result.stdout.strip())
                return v >= required, v
        except Exception:
            pass
        return False, (0, 0)

    # 1. Check current interpreter first
    ok, v = check_interpreter(sys.executable)
    if ok:
        return Path(sys.executable)

    # 2. Search PATH for python3.X candidates
    major, minor = required
    candidates = []
    for m in range(minor, minor + 5):  # try minor version and a few above
        for name in [f"python3.{m}", f"python{major}.{m}"]:
            found = shutil.which(name)
            if found:
                candidates.append(found)

    # 3. Check pyenv versions
    pyenv_root = Path.home() / ".pyenv" / "versions"
    if pyenv_root.exists():
        for entry in sorted(pyenv_root.iterdir()):
            py = entry / "bin" / "python3"
            if py.exists():
                candidates.append(str(py))
            py2 = entry / "bin" / "python"
            if py2.exists():
                candidates.append(str(py2))

    for candidate in candidates:
        ok, v = check_interpreter(candidate)
        if ok:
            return Path(candidate)

    # Nothing found — give a clear message
    current_v = f"{sys.version_info.major}.{sys.version_info.minor}"
    print(
        f"\n  Error: Python {min_version}+ required, found {current_v}.\n"
        f"\n  Searched: PATH, pyenv versions"
        f"\n  To install Python {min_version}:\n"
        f"    pyenv install {min_version}\n"
        f"    pyenv local {min_version}   # run from repo root\n"
        f"\n  Or run this script directly with the right interpreter:\n"
        f"    python3.11 tools/activate_node.py\n",
        file=sys.stderr,
    )
    sys.exit(1)


def check_python(min_version: str) -> Path:
    """Find and report a suitable Python interpreter."""
    python_path = find_python(min_version)
    result = subprocess.run(
        [str(python_path), "--version"],
        capture_output=True, text=True, check=False,
    )
    version_str = result.stdout.strip() or result.stderr.strip()
    print(f"  ✓ {version_str} ({python_path})")
    return python_path


def venv_python() -> Path:
    return ROOT / ".venv" / "bin" / "python"


def venv_pip() -> Path:
    return ROOT / ".venv" / "bin" / "pip"


def venv_exists() -> bool:
    return venv_python().exists()


def installed_packages() -> set:
    """Return set of installed package names (lowercased) in the venv."""
    if not venv_exists():
        return set()
    result = subprocess.run(
        [str(venv_python()), "-m", "pip", "freeze", "--quiet"],
        capture_output=True, text=True, check=False,
    )
    packages = set()
    for line in result.stdout.splitlines():
        if "==" in line:
            packages.add(line.split("==")[0].lower().replace("-", "_"))
        elif line.startswith("-e") or "@" in line:
            pass
    return packages


def normalize(pkg: str) -> str:
    return pkg.lower().split("[")[0].replace("-", "_")


def needs_update(requirements: list) -> tuple[bool, list]:
    """Returns (needs_update, missing_packages)."""
    installed = installed_packages()
    missing   = [r for r in requirements if normalize(r) not in installed]
    return bool(missing), missing


def create_venv(python_path: Path):
    print("  Creating virtual environment...")
    r = subprocess.run(
        [str(python_path), "-m", "venv", str(ROOT / ".venv")],
        check=False, capture_output=True, text=True,
    )
    if r.returncode != 0:
        print(f"  Error creating venv: {r.stderr.strip()}", file=sys.stderr)
        sys.exit(1)
    # Upgrade pip quietly
    subprocess.run(
        [str(venv_python()), "-m", "pip", "install", "--upgrade", "pip", "--quiet"],
        check=False,
    )
    print("  ✓ Virtual environment created")


def write_pth_file():
    """
    Write a .pth file into the venv site-packages so ROOT is always
    on sys.path when the venv is active. This is the foundational fix —
    all tools and manifests resolve imports relative to ROOT without
    any manual sys.path manipulation.
    """
    import glob
    venv_lib = ROOT / ".venv" / "lib"
    # Find site-packages across python versions
    site_packages = sorted(venv_lib.glob("python*/site-packages"))
    if not site_packages:
        print("  Warning: could not find site-packages in venv.", file=sys.stderr)
        return
    pth_path = site_packages[-1] / "mesh_node.pth"
    pth_path.write_text(str(ROOT) + "\n", encoding="utf-8")
    print(f"  ✓ sys.path root: {pth_path.name} → {ROOT}")


def install_requirements(requirements: list, missing: list):
    print(f"  Installing {len(missing)} package(s): {', '.join(missing)}")
    r = subprocess.run(
        [str(venv_pip()), "install"] + requirements + ["--quiet"],
        check=False, capture_output=True, text=True,
    )
    if r.returncode != 0:
        print(f"  Error installing packages:\n{r.stderr.strip()}", file=sys.stderr)
        sys.exit(1)
    print(f"  ✓ Packages installed")


def check_model_cache(model_id: str, use_local: bool):
    """Report model cache status. Never download silently."""
    if use_local:
        model_dir = ROOT / "model"
        model_dir.mkdir(exist_ok=True)
        # Check for any model files in model/
        model_files = list(model_dir.glob("*.safetensors")) + \
                      list(model_dir.glob("*.gguf")) + \
                      list(model_dir.glob("config.json"))
        if model_files:
            print(f"  ✓ Model: local ({model_dir})")
        else:
            print(f"\n  Model not found in {model_dir}")
            print(f"  To download to local model/ directory:")
            print(f"    source .venv/bin/activate")
            print(f"    python -c \"from mlx_lm import load; load('{model_id}')\"")
            print(f"    # Then move from HuggingFace cache to model/")
    else:
        # Check HuggingFace cache
        cache_base = Path.home() / ".cache" / "huggingface" / "hub"
        model_slug = "models--" + model_id.replace("/", "--")
        cached     = (cache_base / model_slug).exists()
        if cached:
            print(f"  ✓ Model: cached ({cache_base / model_slug})")
        else:
            print(f"\n  Model not in HuggingFace cache: {model_id}")
            print(f"  To download (will be cached globally):")
            print(f"    source .venv/bin/activate")
            print(f"    python -c \"from mlx_lm import load; load('{model_id}')\"")


# ── Main ──────────────────────────────────────────────────────────────────────

def parse_args() -> dict:
    args  = sys.argv[1:]
    flags = {"local": False, "print_activate": False}
    for a in args:
        if a == "--local":
            flags["local"] = True
        elif a == "--global":
            flags["local"] = False
        elif a == "--print-activate":
            flags["print_activate"] = True
        elif a in ("--help", "-h"):
            print(
                "Usage: python tools/activate_node.py [--local | --global]\n\n"
                "  --global          use HuggingFace model cache (default)\n"
                "  --local           use model/ directory\n"
                "  --print-activate  print activation command only (for shell sourcing)\n"
            )
            sys.exit(0)
    return flags


def main():
    flags = parse_args()

    # If called with --print-activate, just print the source command
    if flags["print_activate"]:
        print(f"source {ROOT / '.venv' / 'bin' / 'activate'}")
        return

    print(f"\nActivating node: {ROOT.name}")

    # Load requirements and python_min via query chain
    try:
        from tools.query import resolve, resolve_all, bootstrap
        bootstrap()
        reqs   = resolve_all("venv.requirements")
        py_min = resolve("venv.python_min") or "3.11"
    except Exception as e:
        print(f"  Error loading node config: {e}", file=sys.stderr)
        sys.exit(1)

    # Check Python version
    python_path = check_python(py_min)

    # Create or update venv
    if not venv_exists():
        create_venv(python_path)
        install_requirements(reqs, reqs)
        write_pth_file()
    else:
        update_needed, missing = needs_update(reqs)
        if update_needed:
            print(f"  Environment needs update...")
            install_requirements(reqs, missing)
        else:
            print(f"  ✓ Environment current ({len(reqs)} packages)")
        write_pth_file()

    # Check model cache
    from tools.query import resolve
    model_id = resolve("model.target") or ""
    if model_id:
        check_model_cache(model_id, flags["local"])

    # Print activation instructions
    activate_path = ROOT / ".venv" / "bin" / "activate"
    print(f"\n  Node ready.")
    print(f"\n  Activate with:")
    print(f"    source {activate_path}")
    print(f"\n  Or source directly:")
    print(f"    source <(python tools/activate_node.py --print-activate)")
    print(f"\n  Test with:")
    print(f"    python tools/nabla_gen.py mesh_node/README.md \\")
    print(f"      --frame mesh_node/epistemic_floor.md \\")
    print(f"      --model qwen8b")


if __name__ == "__main__":
    main()
