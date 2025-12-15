#!/usr/bin/env python3
"""
Run chunking experiments on local sample markdowns (pdf_samples, ifixit_samples).
Saves JSON reports under scripts/chunking/results/.

Optimizations added:
- In-memory token-count cache to avoid repeated tiktoken.encode() calls.
- FAST_TOKEN_APPROX env var: when set to "1" uses a cheap char-count approximation (len//4).
- Bind cached counter into chunker instances at runtime so chunker.count_tokens uses the cache.
"""
from __future__ import annotations
import os
import json
import re
import types
from pathlib import Path

# Import chunkers from existing script
from compare_chunking_approaches import CustomChunking
import tiktoken

BASE_DIR = Path(__file__).resolve().parent
PDF_DIR = BASE_DIR / "pdf_samples"
IFIXIT_DIR = BASE_DIR / "ifixit_samples"
RESULTS_DIR = BASE_DIR / "results"
RESULTS_DIR.mkdir(exist_ok=True)

# ---- Token counting helpers (cache + fast approx) ----
FAST_TOKEN_APPROX = os.getenv("FAST_TOKEN_APPROX", "0") == "1"
_TOKEN_COUNT_CACHE: dict = {}

def count_tokens_cached(tokenizer, text: str) -> int:
    """
    Cached token counter.
    If FAST_TOKEN_APPROX is enabled, uses character-based approximation (fast).
    Otherwise uses tokenizer.encode and caches results keyed by text (truncated for long text).
    """
    if not text:
        return 0
    if FAST_TOKEN_APPROX:
        # Cheap approximation (roughly 4 chars per token)
        return max(1, len(text) // 4)
    # Use truncated key for memory safety on very long texts
    if len(text) <= 2000:
        key = text
    else:
        key = text[:2000] + f"...len{len(text)}"
    v = _TOKEN_COUNT_CACHE.get(key)
    if v is not None:
        return v
    # expensive call only when not cached
    v = len(tokenizer.encode(text))
    _TOKEN_COUNT_CACHE[key] = v
    return v

# Simple PDF-specific normalization (kept same as before, minor performance-minded code)
def normalize_pdf_markdown(text: str) -> str:
    """
    Normalize PDF-extracted markdown for chunking.
    - Merge short broken lines into paragraphs.
    - Remove repeated headers/footers heuristically.
    - Detect and remove Table of Contents blocks (DO NOT parse or store TOC).
    - Normalize image/table markers: append inline marker to previous paragraph when possible.
    Returns normalized_text (TOC is intentionally discarded).
    """
    lines = text.splitlines()
    out_lines: List[str] = []
    buffer_para: List[str] = []
    # We intentionally do not collect or return TOC entries; TOC lines are skipped.
    short_line_counts = {}
    for l in lines:
        s = l.strip()
        if len(s) <= 60:
            short_line_counts[s] = short_line_counts.get(s, 0) + 1

    def flush_buffer():
        nonlocal buffer_para
        if buffer_para:
            combined = " ".join(p.strip() for p in buffer_para if p.strip())
            out_lines.append(combined)
            buffer_para = []

    toc_line_re = re.compile(r'^\s*[\w\W]{1,200}\.\.{2,}\s*\d+\s*$')
    page_number_re = re.compile(r'^\s*page\s+\d+\s*$', re.IGNORECASE)

    i = 0
    while i < len(lines):
        raw = lines[i]
        s = raw.rstrip()
        if re.search(r'\btable of contents\b', s, flags=re.IGNORECASE):
            flush_buffer()
            i += 1
            while i < len(lines):
                candidate = lines[i].strip()
                if not candidate:
                    i += 1
                    continue
                # Skip TOC-style lines (do not parse or store them)
                if toc_line_re.match(candidate) or re.search(r'\d+\s*$', candidate):
                    i += 1
                    continue
                break
            continue

        if page_number_re.match(s) or (len(s) < 40 and short_line_counts.get(s, 0) > 3):
            flush_buffer()
            i += 1
            continue

        if s.lower().startswith("image:") or s.lower().startswith("url:") or s.strip().startswith("[TABLE_PLACEHOLDER]") or s.strip().startswith("[IMAGE:"):
            marker = "[IMAGE]"
            if s.strip().startswith("[TABLE_PLACEHOLDER]"):
                marker = "[TABLE_PLACEHOLDER]"
            else:
                m = re.match(r'^\[?IMAGE:?\s*([0-9]+)\]?$', s.strip(), re.IGNORECASE)
                if m:
                    marker = f"[IMAGE:{int(m.group(1))}]"
            if out_lines:
                out_lines[-1] = out_lines[-1].rstrip() + " " + marker
            else:
                out_lines.append(marker)
            i += 1
            continue

        if re.match(r'^\s*#{1,6}\s+', s):
            flush_buffer()
            out_lines.append(s.strip())
            i += 1
            continue

        if s.strip() == "":
            flush_buffer()
            i += 1
            continue

        buffer_para.append(s.strip())
        i += 1

    flush_buffer()
    normalized = "\n".join(out_lines)
    return normalized


def bind_cached_counter_to_chunker(chunker, tokenizer):
    """
    Bind the count_tokens method on chunker to use cached/tokenizer-based counter.
    Uses types.MethodType to bind a function as a method to the instance.
    """
    try:
        # create a bound method: lambda self, text: count_tokens_cached(tokenizer, text)
        bound = types.MethodType(lambda self, text, tok=tokenizer: count_tokens_cached(tok, text), chunker)
        chunker.count_tokens = bound
    except Exception:
        # If binding fails, ignore (chunker will use its original method)
        pass


def run_on_file(path: Path, chunkers: dict, tokenizer):
    raw = path.read_text(encoding="utf-8")
    # Decide normalization: if file contains "# Page" or "[TABLE_PLACEHOLDER]" treat as PDF output
    if re.search(r'^\s*#\s*Page\s+\d+', raw, re.IGNORECASE) or "[TABLE_PLACEHOLDER]" in raw or "image:" in raw or "[IMAGE:" in raw:
        # PDF-extracted content: normalize and discard any TOC-like regions
        text = normalize_pdf_markdown(raw)
        source_type = "pdf_extracted"
    else:
        text = raw
        source_type = "ifixit"
    reports = {}

    for name, chunker in chunkers.items():
        try:
            chunks = chunker.chunk_text(text)
        except Exception as e:
            reports[name] = {"error": str(e)}
            continue

        tokens = [c.token_count for c in chunks] if chunks else []
        reports[name] = {
            "source": source_type,
            "file": str(path.name),
            "num_chunks": len(chunks),
            "token_stats": {
                "min": min(tokens) if tokens else 0,
                "max": max(tokens) if tokens else 0,
                "avg": (sum(tokens) / len(tokens)) if tokens else 0
            },
            "chunks_with_headings": sum(1 for c in chunks if getattr(c, "heading", None)),
            "first_chunks_preview": [
                {
                    "index": c.chunk_index,
                    "tokens": c.token_count,
                    "heading": getattr(c, "heading", None),
                    "preview": c.content[:400].replace("\n", " ")
                }
                for c in chunks[:5]
            ]
        }
    return text, reports


def main():
    print("Running chunking experiments...")
    tokenizer = tiktoken.get_encoding("cl100k_base")

    custom = CustomChunking()
    chunkers = {"custom": custom}
    # LangChain removed from default experiment pipeline.

    # Bind cached counter into chunkers (so chunkers use cached token counting)
    for c in chunkers.values():
        bind_cached_counter_to_chunker(c, tokenizer)

    all_files = list(PDF_DIR.glob("*.md")) + list(IFIXIT_DIR.glob("*.md"))
    if not all_files:
        print("No sample files found in pdf_samples or ifixit_samples.")
        return

    summary = []
    for f in all_files:
        print(f"Processing {f.name} ...")
        normalized_text, reports = run_on_file(f, chunkers, tokenizer)
        out_file = RESULTS_DIR / f"{f.stem}_report.json"
        out_data = {
            "file": str(f),
            "reports": reports
        }
        out_file.write_text(json.dumps(out_data, indent=2, ensure_ascii=False), encoding="utf-8")
        summary.append({"file": f.name, "reports": {k: v["num_chunks"] if "num_chunks" in v else None for k, v in reports.items()}})
        print(f"  Saved {out_file}")

    print("\nSummary:")
    for s in summary:
        print(s)

if __name__ == "__main__":
    main()