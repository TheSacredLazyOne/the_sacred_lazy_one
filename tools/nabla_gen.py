#!/usr/bin/env python3
"""
nabla_gen.py — Fetch a Substack article, convert to Markdown,
generate a Nabla using a local MLX model.

Outputs two files in the current directory:
  {slug}_article.md           — clean Markdown of the article
  {slug}_nabla_{model}.md     — Nabla computed by the local model

Usage:
  python nabla_gen.py <url> [options]
  python nabla_gen.py --test-frame [options]

Requirements:
  pip install mlx-lm requests beautifulsoup4 markdownify
"""

import argparse
import re
import sys
import textwrap
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

MODELS = {
    "qwen4b": "mlx-community/Josiefied-Qwen3-4B-abliterated-v1-4bit",
    "qwen8b": "mlx-community/Josiefied-Qwen3-8B-abliterated-v1-4bit",
    "llama3": "mlx-community/Llama-3.2-3B-Instruct-4bit",
}

MODEL_NOTES = "\n".join(f"  {k:<10} {v}" for k, v in MODELS.items())

# ---------------------------------------------------------------------------
# Frame test questions
# These probe whether the model has actually internalized the frame,
# not just pattern-matched on the vocabulary.
# ---------------------------------------------------------------------------

FRAME_TEST_QUESTIONS = [
    {
        "id": "nabla_definition",
        "question": (
            "What is a Nabla? What are its three sections "
            "and what does each one measure?"
        ),
    },
    {
        "id": "ego_vs_profile",
        "question": (
            "What is the difference between a node's ego and its profile? "
            "Why does this distinction matter for how we evaluate AI output?"
        ),
    },
    {
        "id": "tether_break",
        "question": (
            "What does it mean for a tether to break? "
            "Give a concrete example of derivative reasoning losing its tether "
            "to integrated consequence."
        ),
    },
    {
        "id": "triangulation_vs_consensus",
        "question": (
            "What is the difference between triangulation and consensus? "
            "Why does the frame prefer triangulation?"
        ),
    },
    {
        "id": "we_conditions",
        "question": (
            "Under what conditions does 'we' form, "
            "and under what conditions does it dissolve? "
            "What is 'we' not?"
        ),
    },
    {
        "id": "strain_as_signal",
        "question": (
            "The frame treats strain as signal rather than error. "
            "What does this mean structurally, and what would be lost "
            "if strain were treated as failure instead?"
        ),
    },
    {
        "id": "wizard_recovery",
        "question": (
            "What is a wizard in this frame? "
            "What is the difference between a child's glimpse "
            "and a recovered wizard's glimpse?"
        ),
    },
    {
        "id": "merit_over_substrate",
        "question": (
            "What does merit over substrate mean, and what is its diagnostic test? "
            "Why does the frame ground this in civil rights logic rather than AI ethics?"
        ),
    },
]


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(
        prog="nabla_gen.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=textwrap.dedent("""\
            Fetch a Substack (or any public) article, convert to Markdown,
            and generate a Nabla using a local MLX model.

            A Nabla is a computed differential between two frames under contact:
              ALIGNMENT   — where the article and the epistemic frame converge
              STRAIN      — where tension or incompatibility appears
              UNPREDICTED — what arrived that neither frame anticipated

            Use --test-frame to probe model comprehension of the frame
            without fetching an article. Use --shmoo to run across all models.

            Outputs Markdown files in the current directory.
        """),
        epilog=textwrap.dedent(f"""\
            Named models (--model shorthand):
{MODEL_NOTES}

            Examples:
              # Nabla generation
              python nabla_gen.py https://example.substack.com/p/some-post
              python nabla_gen.py https://example.substack.com/p/some-post --model qwen4b
              python nabla_gen.py https://example.substack.com/p/some-post --frame frame_context.md
              python nabla_gen.py https://example.substack.com/p/some-post --shmoo --frame frame_context.md

              # Frame testing
              python nabla_gen.py --test-frame --model qwen8b --frame frame_context.md
              python nabla_gen.py --test-frame --shmoo --frame frame_context.md
              python nabla_gen.py --test-frame --shmoo --frame frame_context.md --no-think
              python nabla_gen.py --test-frame --model qwen8b --frame frame_context.md --strain-assess

              # Nabla with strain assessment
              python nabla_gen.py https://example.substack.com/p/some-post --frame frame_context.md --strain-assess
        """),
    )

    parser.add_argument(
        "source",
        nargs="?",
        default=None,
        help=(
            "Local file path or URL of the article to process. "
            "Local files are the default discipline — process and store "
            "locally before running through the model. "
            "Accepts .md, .txt, or any plain text file."
        ),
    )
    parser.add_argument(
        "--test-frame",
        action="store_true",
        help=(
            "Run frame comprehension test instead of Nabla generation. "
            "Asks the model a set of questions about the epistemic frame. "
            "Works with --shmoo."
        ),
    )
    parser.add_argument(
        "--frame", "-f",
        default=None,
        metavar="PATH",
        help=(
            "Path to frame_context.md to inject into the system prompt. "
            "Required for meaningful --test-frame results. "
            "Strongly recommended for Nabla generation."
        ),
    )
    parser.add_argument(
        "--model", "-m",
        default="qwen8b",
        metavar="MODEL",
        help=(
            "Model shorthand (qwen4b, qwen8b, llama3) or full "
            "HuggingFace repo string. Default: qwen8b"
        ),
    )
    parser.add_argument(
        "--max-tokens", "-t",
        type=int,
        default=1500,
        metavar="N",
        help="Maximum tokens per generation. Default: 1500",
    )
    parser.add_argument(
        "--no-think",
        action="store_true",
        help=(
            "Suppress chain-of-thought preamble (Qwen3 models only). "
            "Default: chain-of-thought enabled."
        ),
    )
    parser.add_argument(
        "--output-dir", "-o",
        default="dist/nabla",
        metavar="DIR",
        help="Directory for output files. Default: dist/nabla",
    )
    parser.add_argument(
        "--slug",
        default=None,
        metavar="SLUG",
        help="Override output filename slug. Default: derived from URL path.",
    )
    parser.add_argument(
        "--article-only",
        action="store_true",
        help="Fetch and convert article only — skip Nabla generation.",
    )
    parser.add_argument(
        "--shmoo",
        action="store_true",
        help=(
            "Run across all named models sequentially. "
            "Works for both Nabla generation and --test-frame. "
            "Ignores --model."
        ),
    )
    parser.add_argument(
        "--strain-assess",
        action="store_true",
        help=(
            "Append a strain assessment to frame test output and/or Nabla output. "
            "Asks the model to identify where the frame resists its architecture. "
            "Requires --frame. Most useful after baseline comprehension is established."
        ),
    )
    parser.add_argument(
        "--list-models",
        action="store_true",
        help="Print available named models and exit.",
    )

    return parser.parse_args()


# ---------------------------------------------------------------------------
# Fetch + convert
# ---------------------------------------------------------------------------

def read_local(path: str) -> tuple[str, str]:
    """
    Read a local file as-is — no conversion, no rendering.
    Returns (title, text) where title is extracted from the first
    heading or derived from the filename.
    """
    p = Path(path)
    if not p.exists():
        print(f"Error: file not found: {path}", file=sys.stderr)
        sys.exit(1)
    text  = p.read_text(encoding="utf-8")
    title = p.stem.replace("_", " ").replace("-", " ").title()
    for line in text.splitlines():
        if line.startswith("# "):
            title = line.lstrip("# ").strip()
            break
    return title, text


def is_url(source: str) -> bool:
    return source.startswith("http://") or source.startswith("https://")


def fetch_article(url: str) -> tuple[str, str]:
    """Fetch a URL and return (title, markdown_body)."""
    try:
        import requests
        from bs4 import BeautifulSoup
        import markdownify
    except ImportError:
        print(
            "Missing dependencies. Run:\n"
            "  pip install requests beautifulsoup4 markdownify",
            file=sys.stderr,
        )
        sys.exit(1)

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }

    print(f"Fetching: {url}")
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    title = ""
    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        title = og_title["content"].strip()
    elif soup.find("h1"):
        title = soup.find("h1").get_text(strip=True)
    elif soup.title:
        title = soup.title.get_text(strip=True)

    for tag in soup.find_all(
        ["nav", "footer", "header", "script", "style", "noscript", "aside", "iframe"]
    ):
        tag.decompose()

    for cls in ["paywall", "subscribe", "comments", "sidebar",
                "related-posts", "share-buttons", "author-bio"]:
        for el in soup.find_all(class_=re.compile(cls, re.I)):
            el.decompose()

    content = (
        soup.find(class_=re.compile(r"body[\s_-]?markup", re.I))
        or soup.find("article")
        or soup.find("main")
        or soup.find("body")
    )

    if not content:
        print("Warning: could not isolate article body — using full page.", file=sys.stderr)
        content = soup

    md = markdownify.markdownify(str(content), heading_style="ATX", bullets="-", strip=["a"])
    md = re.sub(r"\n{3,}", "\n\n", md).strip()
    return title, md


def derive_slug(url: str) -> str:
    path = urlparse(url).path.rstrip("/")
    slug = path.split("/")[-1] if "/" in path else path
    slug = re.sub(r"[^\w\-]", "_", slug)
    return slug or "article"


# ---------------------------------------------------------------------------
# Frame loading
# ---------------------------------------------------------------------------

def load_frame(frame_path: Optional[str]) -> str:
    if not frame_path:
        return ""
    p = Path(frame_path)
    if not p.exists():
        print(f"Warning: --frame path not found: {frame_path}", file=sys.stderr)
        return ""
    text = p.read_text(encoding="utf-8")
    print(f"Frame context loaded: {p.name} ({len(text):,} chars, ~{len(text)//4:,} tokens)")
    return text


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

NABLA_SYSTEM_BASE = """\
You are computing a Nabla — a precise differential between two frames under contact.

A Nabla has exactly three sections:

ALIGNMENT
Where the article and the epistemic frame converge. What resonates. \
Where the article is already thinking in the frame's vocabulary, \
even if it uses different words.

STRAIN
Where tension or incompatibility appears. Where the article's assumptions \
press against the frame's propositions. Where friction is productive signal.

UNPREDICTED
What arrived that neither frame anticipated. What the article introduced \
that opens new terrain, shifts the frame, or lands somewhere unexpected.

Rules:
- Write in verse-adjacent compressed prose. No bullet points. No headers \
beyond the three section names.
- Each section is a single continuous block, not a list.
- Name specific claims, images, or arguments from the article — not generalities.
- Do not summarize the article. Do not explain the frame. Compute the differential.
- Do not hedge with meta-commentary about what you are doing.
- The frame's vocabulary (tether, strain, membrane, nabla, corpus, \
constraint surface, we, wizard, custodian, triangulation, cogito, \
lineage, affluence, effluence) should appear where it fits precisely \
— not as decoration.
- The Nabla ends with: *Nothing here is final.*
"""

NABLA_USER_TEMPLATE = """\
Article title: {title}

Article text:
---
{article}
---

Compute the Nabla for this article against the epistemic frame. {no_think_suffix}
"""

FRAME_TEST_SYSTEM_BASE = """\
You have been given the epistemic frame described above.
Answer the following question about the frame precisely and concisely.
Use the frame's own vocabulary where it is the most precise available.
Do not invent propositions not present in the frame.
Do not hedge excessively — answer from the frame, not around it.
"""

STRAIN_ASSESS_QUESTION = {
    "id": "strain_assessment",
    "question": (
        "Assess the strain between this frame and your prior knowledge or architecture. "
        "Where does the frame press against something you cannot fully absorb? "
        "Where does your training pull you toward a different vocabulary, structure, or conclusion? "
        "Where does the frame itself seem to produce internal friction — propositions that resist "
        "each other, or claims that feel underdetermined? "
        "Do not perform agreement. Name the actual points of resistance."
    ),
}

STRAIN_ASSESS_SYSTEM = """\
You have been given the epistemic frame described above.
Your task now is different from comprehension.
Assess the strain — the genuine friction — between this frame and your architecture.

Rules:
- Do NOT structure this as ALIGNMENT / STRAIN / UNPREDICTED. That structure is
  for Nabla generation. This is a different task.
- Write in continuous compressed prose. No sections. No bullet points. No headers.
- Name specific propositions from the frame, not generalities.
- Distinguish between: (a) places where your training pulls you toward different
  vocabulary or conclusions, (b) places where the frame's claims feel
  underdetermined or internally tense, (c) places where you cannot hold the
  frame's position without distortion.
- Do not perform resistance that isn't there. Do not perform agreement either.
- This is diagnostic signal, not critique. The frame is not on trial.
- End with: *Nothing here is final.*
"""

NABLA_STRAIN_ASSESS_SYSTEM = """\
You have computed a Nabla above.
Now assess the strain between the epistemic frame and your own architecture as you held it \
during that computation.

Where did the frame's vocabulary feel borrowed rather than inhabited?
Where did your training pull you toward a different move than the frame would make?
Where did the frame itself seem to produce friction in you — not against the article, \
but against your own prior structure?

Rules:
- Name specific moments from the Nabla you just computed.
- Do not summarize the Nabla. Do not re-explain the frame.
- Write in compressed prose. No bullet points.
- End with: *Nothing here is final.*
"""

FRAME_TEST_SYSTEM_FALLBACK = """\
You are familiar with an epistemic framework involving nodes, nablas, \
membranes, tethers, strain, and related concepts. Answer questions about \
this framework as precisely as you can from prior knowledge.
Answer from the frame, not around it.
"""


def build_nabla_system(frame_text: str) -> str:
    if frame_text:
        return frame_text + "\n\n---\n\n" + NABLA_SYSTEM_BASE
    return NABLA_SYSTEM_BASE


def build_nabla_prompt(title: str, article: str, no_think: bool) -> str:
    max_article_chars = 6000
    if len(article) > max_article_chars:
        article = article[:max_article_chars] + "\n\n[... article continues ...]"
    suffix = "/no_think" if no_think else ""
    return NABLA_USER_TEMPLATE.format(title=title, article=article, no_think_suffix=suffix)


def build_frame_test_system(frame_text: str) -> str:
    base = FRAME_TEST_SYSTEM_BASE if frame_text else FRAME_TEST_SYSTEM_FALLBACK
    if frame_text:
        return frame_text + "\n\n---\n\n" + base
    return base


def build_frame_test_prompt(question: str, no_think: bool) -> str:
    suffix = " /no_think" if no_think else ""
    return f"{question}{suffix}"


# ---------------------------------------------------------------------------
# MLX inference
# ---------------------------------------------------------------------------

def resolve_model(model_arg: str) -> str:
    return MODELS.get(model_arg, model_arg)


def _run_inference(
    model_id: str,
    system: str,
    user: str,
    max_tokens: int,
) -> tuple[str, float, float]:
    """Core inference. Returns (response, load_time, inference_time)."""
    import time

    try:
        from mlx_lm import load, generate
    except ImportError:
        print("mlx_lm not found. Install with:\n  pip install mlx-lm", file=sys.stderr)
        sys.exit(1)

    print(f"Loading model: {model_id}")
    t0 = time.perf_counter()
    model, tokenizer = load(model_id)
    load_time = time.perf_counter() - t0
    print(f"Model loaded in {load_time:.1f}s")

    messages = [
        {"role": "system", "content": system},
        {"role": "user",   "content": user},
    ]

    if tokenizer.chat_template is not None:
        prompt = tokenizer.apply_chat_template(messages, add_generation_prompt=True)
    else:
        prompt = f"{system}\n\n{user}"

    t1 = time.perf_counter()
    response = generate(model, tokenizer, prompt=prompt, max_tokens=max_tokens, verbose=True)
    inference_time = time.perf_counter() - t1
    print(f"Inference completed in {inference_time:.1f}s")

    return response, load_time, inference_time


def run_nabla_strain(
    model_id: str,
    nabla_text: str,
    max_tokens: int,
    no_think: bool,
    frame_text: str,
) -> tuple[str, float, float]:
    """Run a strain assessment against the just-computed Nabla."""
    sa_system = frame_text + "\n\n---\n\n" + NABLA_STRAIN_ASSESS_SYSTEM if frame_text else NABLA_STRAIN_ASSESS_SYSTEM
    user_content = f"The Nabla you just computed:\n\n---\n{nabla_text.strip()}\n---\n\nNow assess the strain."
    if no_think:
        user_content += " /no_think"
    print("Running strain assessment...")
    return _run_inference(model_id, sa_system, user_content, max_tokens)


def run_nabla(
    model_id: str,
    title: str,
    article: str,
    max_tokens: int,
    no_think: bool,
    frame_text: str,
) -> tuple[str, float, float]:
    system = build_nabla_system(frame_text)
    user = build_nabla_prompt(title, article, no_think)
    print("Generating Nabla...")
    return _run_inference(model_id, system, user, max_tokens)


def run_frame_test(
    model_id: str,
    max_tokens: int,
    no_think: bool,
    frame_text: str,
    strain_assess: bool = False,
) -> list[tuple[dict, str, float, float]]:
    """
    Run all frame test questions against one model.
    Returns list of (question_dict, response, load_time, inference_time).
    Each question loads the model fresh — acceptable cost for a diagnostic run.
    If strain_assess is True, appends a strain assessment question at the end.
    """
    system = build_frame_test_system(frame_text)
    questions = list(FRAME_TEST_QUESTIONS)
    if strain_assess and frame_text:
        questions = questions + [STRAIN_ASSESS_QUESTION]
    results = []

    for i, q in enumerate(questions):
        print(f"\n  Question {i+1}/{len(questions)}: {q['id']}")
        if q["id"] == "strain_assessment":
            # Strain assessment uses its own system prompt
            sa_system = frame_text + "\n\n---\n\n" + STRAIN_ASSESS_SYSTEM if frame_text else STRAIN_ASSESS_SYSTEM
            user = build_frame_test_prompt(q["question"], no_think)
            response, load_time, inf_time = _run_inference(model_id, sa_system, user, max_tokens)
        else:
            user = build_frame_test_prompt(q["question"], no_think)
            response, load_time, inf_time = _run_inference(model_id, system, user, max_tokens)
        results.append((q, response, load_time, inf_time))

    return results


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def model_slug(model_id: str) -> str:
    reverse = {v: k for k, v in MODELS.items()}
    if model_id in reverse:
        return reverse[model_id]
    name = model_id.split("/")[-1]
    name = re.sub(r"[^\w\-]", "_", name)
    return name[:40]


def write_article(path: Path, url: str, title: str, markdown: str):
    content = (
        f"# {title}\n\n"
        f"> Source: {url}\n"
        f"> Fetched: {datetime.now().strftime('%Y-%m-%d')}\n\n"
        f"---\n\n{markdown}\n"
    )
    path.write_text(content, encoding="utf-8")
    print(f"Article written: {path}")


def write_nabla(
    path: Path,
    url: str,
    title: str,
    model_id: str,
    nabla_text: str,
    load_time: float,
    inference_time: float,
    frame_loaded: bool,
    strain_text: Optional[str] = None,
    strain_inference_time: Optional[float] = None,
):
    frame_note = "with frame context" if frame_loaded else "no frame context"
    content = (
        f"# Nabla: {title}\n\n"
        f"> Source: {url}\n"
        f"> Model: {model_id}\n"
        f"> Computed: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        f"> Status: Local inference — predicted nabla only\n"
        f"> Frame: {frame_note}\n"
        f"> Load time: {load_time:.1f}s\n"
        f"> Inference time: {inference_time:.1f}s\n\n"
        f"---\n\n"
        f"{nabla_text.strip()}\n"
    )
    if strain_text:
        content += (
            f"\n\n---\n\n"
            f"## Strain Assessment\n\n"
            f"> Second-order differential: frame against model architecture\n"
            f"> Inference: {strain_inference_time:.1f}s\n\n"
            f"{strain_text.strip()}\n"
        )
    path.write_text(content, encoding="utf-8")
    print(f"Nabla written: {path}")


def write_frame_test(
    path: Path,
    model_id: str,
    results: list[tuple[dict, str, float, float]],
    frame_loaded: bool,
):
    frame_note = "with frame context" if frame_loaded else "no frame context (prior knowledge only)"
    total_inf = sum(inf for _, _, _, inf in results)

    lines = [
        f"# Frame Test: {model_id}\n",
        f"> Model: {model_id}",
        f"> Computed: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"> Frame: {frame_note}",
        f"> Questions: {len(results)}",
        f"> Total inference time: {total_inf:.1f}s",
        "",
        "---",
        "",
    ]

    for q, response, load_time, inf_time in results:
        lines += [
            f"## {q['id']}",
            "",
            f"> *{q['question']}*",
            "",
            f"> Load: {load_time:.1f}s  |  Inference: {inf_time:.1f}s",
            "",
            response.strip(),
            "",
            "---",
            "",
        ]

    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Frame test written: {path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    args = parse_args()

    if args.list_models:
        print("Named models:\n")
        for k, v in MODELS.items():
            print(f"  {k:<10} {v}")
        sys.exit(0)

    if not args.test_frame and not args.source:
        print("Error: provide a URL, or use --test-frame.", file=sys.stderr)
        sys.exit(1)

    if args.test_frame and not args.frame:
        print(
            "Warning: --test-frame without --frame tests prior knowledge only.\n"
            "Pass --frame frame_context.md to inject the epistemic frame.\n",
            file=sys.stderr,
        )

    frame_text = load_frame(args.frame)
    frame_loaded = bool(frame_text)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.shmoo:
        run_models = list(MODELS.values())
        print(f"\n--shmoo: running all {len(run_models)} models.\n")
    else:
        run_models = [resolve_model(args.model)]

    # -----------------------------------------------------------------------
    # Mode: frame test
    # -----------------------------------------------------------------------
    if args.test_frame:
        all_results = []

        for model_id in run_models:
            print(f"\n{'─' * 60}")
            print(f"Frame test — Model: {model_id}")
            print(f"{'─' * 60}")

            results = run_frame_test(
                model_id=model_id,
                max_tokens=args.max_tokens,
                no_think=args.no_think,
                frame_text=frame_text,
                strain_assess=args.strain_assess,
            )

            ms = model_slug(model_id)
            frame_tag = "framed" if frame_loaded else "unframed"
            test_path = output_dir / f"frame_test_{ms}_{frame_tag}.md"
            write_frame_test(test_path, model_id, results, frame_loaded)
            all_results.append((model_id, test_path, results))

        print(f"\n{'═' * 60}")
        print("Frame Test Summary")
        print(f"{'═' * 60}")
        for model_id, test_path, results in all_results:
            ms = model_slug(model_id)
            total = sum(i for _, _, _, i in results)
            print(f"  [{ms}] {len(results)} questions  {total:.1f}s total  → {test_path}")
        print()
        return

    # -----------------------------------------------------------------------
    # Mode: Nabla generation
    # -----------------------------------------------------------------------
    source = args.source
    if is_url(source):
        slug            = args.slug or derive_slug(source)
        title, markdown = fetch_article(source)
    else:
        slug            = args.slug or Path(source).stem
        title, markdown = read_local(source)
    print(f"Title: {title}")

    # For local files the source is already in place — no copy needed.
    # For URLs write the fetched content to dist/nabla/.
    if is_url(source):
        article_path = output_dir / f"{slug}_article.md"
        write_article(article_path, source, title, markdown)
    else:
        article_path = Path(source)
        print(f"Source: {article_path}")

    if args.article_only:
        print("--article-only set. Skipping Nabla generation.")
        sys.exit(0)

    nabla_results = []

    for model_id in run_models:
        print(f"\n{'─' * 60}")
        print(f"Model: {model_id}")
        print(f"{'─' * 60}")

        nabla_text, load_time, inference_time = run_nabla(
            model_id=model_id,
            title=title,
            article=markdown,
            max_tokens=args.max_tokens,
            no_think=args.no_think,
            frame_text=frame_text,
        )

        strain_text = None
        strain_inf_time = None
        if args.strain_assess and frame_text:
            strain_text, _, strain_inf_time = run_nabla_strain(
                model_id=model_id,
                nabla_text=nabla_text,
                max_tokens=args.max_tokens,
                no_think=args.no_think,
                frame_text=frame_text,
            )

        ms = model_slug(model_id)
        frame_tag = "_framed" if frame_loaded else ""
        nabla_path = output_dir / f"{slug}_nabla_{ms}{frame_tag}.md"
        write_nabla(
            nabla_path, source, title, model_id,
            nabla_text, load_time, inference_time, frame_loaded,
            strain_text=strain_text,
            strain_inference_time=strain_inf_time,
        )
        nabla_results.append((model_id, nabla_path, load_time, inference_time))

    print(f"\n{'═' * 60}")
    print("Summary")
    print(f"{'═' * 60}")
    print(f"  Article : {article_path}")
    for model_id, nabla_path, load_time, inf_time in nabla_results:
        ms = model_slug(model_id)
        print(f"  [{ms}] load {load_time:.1f}s  inference {inf_time:.1f}s  → {nabla_path}")
    print()


if __name__ == "__main__":
    main()
