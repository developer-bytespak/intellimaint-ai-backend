#!/usr/bin/env python3
"""
Run chunking experiments on local sample markdowns (pdf_samples, ifixit_samples).
Saves JSON reports under scripts/chunking/results/.
"""

from __future__ import annotations
import os
import json
import re
from pathlib import Path

# Import chunkers from existing script
from compare_chunking_approaches import CustomChunking, LangChainChunking, LANGCHAIN_AVAILABLE
import tiktoken

BASE_DIR = Path(__file__).resolve().parent
PDF_DIR = BASE_DIR / "pdf_samples"
IFIXIT_DIR = BASE_DIR / "ifixit_samples"
RESULTS_DIR = BASE_DIR / "results"
RESULTS_DIR.mkdir(exist_ok=True)

# Simple PDF-specific normalization:
def normalize_pdf_markdown(text: str) -> str:
    lines = text.splitlines()
    out_lines = []
    buffer_para = []
    short_line_accum_threshold = 3  # collapse short lines into paragraph if many in a row
    short_seq = 0

    def flush_buffer():
        nonlocal buffer_para
        if buffer_para:
            out_lines.append(" ".join(l.strip() for l in buffer_para if l.strip()))
            buffer_para = []

    for line in lines:
        s = line.rstrip()
        # Remove explicit page headers
        if re.match(r'^\s*#\s*Page\s+\d+', s, re.IGNORECASE):
            flush_buffer()
            continue
        # Collapse image/url blocks into a single token
        if s.lower().startswith("image:") or s.lower().startswith("url:") or s.strip().startswith("[TABLE_PLACEHOLDER]"):
            flush_buffer()
            # add a single marker line
            if s.strip().startswith("[TABLE_PLACEHOLDER]"):
                out_lines.append("[TABLE_PLACEHOLDER]")
            else:
                out_lines.append("[IMAGE]")
            short_seq = 0
            continue
        # If line looks like a very short table/row (few words), accumulate and then join
        if len(s.strip().split()) <= 6 and s.strip():
            buffer_para.append(s.strip())
            short_seq += 1
            if short_seq >= short_line_accum_threshold:
                flush_buffer()
                short_seq = 0
            continue
        # Heading lines keep as-is
        if re.match(r'^\s*#{1,6}\s+', s):
            flush_buffer()
            out_lines.append(s)
            short_seq = 0
            continue
        # Normal paragraph line -> accumulate into buffer for paragraphs
        if s.strip() == "":
            flush_buffer()
            out_lines.append("")
            short_seq = 0
            continue
        buffer_para.append(s.strip())
        short_seq = 0

    flush_buffer()
    return "\n".join(out_lines)

def run_on_file(path: Path, chunkers: dict):
    raw = path.read_text(encoding="utf-8")
    # Decide normalization: if file contains "# Page" or "[TABLE_PLACEHOLDER]" treat as PDF output
    if re.search(r'^\s*#\s*Page\s+\d+', raw, re.IGNORECASE) or "[TABLE_PLACEHOLDER]" in raw or "image:" in raw:
        text = normalize_pdf_markdown(raw)
        source_type = "pdf_extracted"
    else:
        text = raw
        source_type = "ifixit"
    reports = {}
    tokenizer = tiktoken.get_encoding("cl100k_base")

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
    custom = CustomChunking()
    chunkers = {"custom": custom}
    if LANGCHAIN_AVAILABLE:
        try:
            lang = LangChainChunking()
            chunkers["langchain"] = lang
        except Exception:
            pass

    all_files = list(PDF_DIR.glob("*.md")) + list(IFIXIT_DIR.glob("*.md"))
    if not all_files:
        print("No sample files found in pdf_samples or ifixit_samples.")
        return

    summary = []
    for f in all_files:
        print(f"Processing {f.name} ...")
        normalized_text, reports = run_on_file(f, chunkers)
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