#!/usr/bin/env python3
"""
Chunk iFixit-style markdown guides into RAG-friendly chunks.

Usage (from 'chunking' folder):

    python test_script.py \
        --input-dir ./ifixit_sample \
        --output ./ifixit_chunks.json
"""

import argparse
import json
import re
from pathlib import Path
from typing import List, Dict, Any, Tuple

# --- Chunking config ---------------------------------------------------------

# Roughly ~300 tokens-ish target
MAX_CHARS_PER_CHUNK = 1200

# Hard cap on how many *steps* we want per chunk
MAX_STEPS_PER_CHUNK = 5

# How many of the previous chunk's steps to overlap into the next one
STEP_OVERLAP = 1


# --- Markdown parsing helpers ------------------------------------------------

def is_noise_line(line: str) -> bool:
    """
    Returns True for lines we want to drop (images, image URL comments, etc.).
    """
    s = line.strip()
    if not s:
        return False  # keep blank lines for spacing
    if s.startswith("![") and "](" in s:
        return True
    if s.startswith("<!--") and s.endswith("-->"):
        return True
    return False


def normalize_section_body(lines: List[str]) -> str:
    """
    Remove noise lines, normalize some iFixit-specific link syntax,
    and collapse excess blank lines inside a section.
    """
    out: List[str] = []
    for line in lines:
        if is_noise_line(line):
            continue
        out.append(line.rstrip())

    text = "\n".join(out)

    # Convert iFixit triple-pipe link syntax to plain text:
    # [product|IF145-020|tweezers] -> tweezers
    # [link|https://...|this calibration guide] -> this calibration guide
    text = re.sub(r"\[[^|\]]+\|[^|\]]*\|([^|\]]+)\]", r"\1", text)

    # Collapse 3+ newlines into 2
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def parse_guide_sections(md_text: str) -> Tuple[str, str, List[Dict[str, Any]]]:
    """
    Parse a single iFixit-style markdown file into:
      - title (H1)
      - intro_text (text before first H2)
      - sections: list of { heading_raw, heading, step_index, lines }
    """
    lines = md_text.splitlines()

    title: str | None = None
    intro_lines: List[str] = []
    sections: List[Dict[str, Any]] = []
    current_section: Dict[str, Any] | None = None
    step_counter = 0

    for line in lines:
        if line.startswith("# "):
            # First H1 is the guide title
            if title is None:
                title = line[2:].strip()
            else:
                # Any additional H1s just treated as normal text
                if current_section is None:
                    intro_lines.append(line)
                else:
                    current_section["lines"].append(line)

        elif line.startswith("## "):
            # New top-level section / step
            if current_section is not None:
                sections.append(current_section)

            heading_text = line[3:].strip()

            # Try to parse "N. Something something"
            m = re.match(r"(\d+)\.\s*(.*)", heading_text)
            if m:
                step_counter = int(m.group(1))
                heading_clean = m.group(2).strip() or heading_text
            else:
                step_counter += 1
                heading_clean = heading_text

            current_section = {
                "heading_raw": heading_text,
                "heading": heading_clean,
                "step_index": step_counter,
                "lines": [],
            }

        else:
            # Normal content line
            if title is None:
                # We haven't seen a title yet
                intro_lines.append(line)
            elif current_section is None:
                # After title, before first step
                intro_lines.append(line)
            else:
                current_section["lines"].append(line)

    # Add last section if present
    if current_section is not None:
        sections.append(current_section)

    if title is None:
        title = "Untitled Guide"

    intro_text = "\n".join(intro_lines).strip()

    return title, intro_text, sections


def derive_heading_from_body(body: str) -> str | None:
    """
    When a heading is just 'Step 3' etc., try to derive a more descriptive
    heading from the first meaningful body line.
    """
    if not body:
        return None

    for line in body.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(">"):
            continue  # skip quote/notes lines

        # Remove bullet markers like '- ', '* ', '• '
        stripped = re.sub(r"^[-*•]\s*", "", stripped)
        if stripped:
            # Truncate to a reasonable length
            return stripped[:80]

    return None


def chunk_sections(
    title: str,
    intro_text: str,
    sections: List[Dict[str, Any]],
    max_chars: int = MAX_CHARS_PER_CHUNK,
    max_steps: int = MAX_STEPS_PER_CHUNK,
    step_overlap: int = STEP_OVERLAP,
) -> List[Dict[str, Any]]:
    """
    Turn intro + step sections into a list of chunk dicts with:
      {
        "chunk_index": int,
        "step_indices": [int, ...],
        "headings": [str, ...],
        "content": str,
      }

    Enhancements:
      - Every chunk starts with "Guide: <title>".
      - Hard cap on steps per chunk.
      - Last `step_overlap` steps of previous chunk are repeated in next chunk.
      - Headings like "Step 3" are upgraded using the first meaningful body line.
    """
    items: List[Dict[str, Any]] = []

    # Intro as a pseudo-item
    if intro_text:
        items.append(
            {
                "kind": "intro",
                "step_index": 0,
                "heading": "Introduction",
                "heading_display": "Introduction",
                "body": intro_text,
            }
        )

    # Steps as items
    for sec in sections:
        body = normalize_section_body(sec["lines"])
        if not body:
            continue

        heading = sec["heading"]
        heading_display = heading

        # Improve headings that are just "Step 3", "Step 4", etc.
        if re.match(r"(?i)^step\s*\d+$", heading):
            derived = derive_heading_from_body(body)
            if derived:
                heading_display = derived

        items.append(
            {
                "kind": "step",
                "step_index": sec["step_index"],
                "heading": heading,
                "heading_display": heading_display,
                "body": body,
            }
        )

    if not items:
        return []

    # --- Segment items into chunks based on char + step limits (no overlap yet) ---

    segments: List[List[Dict[str, Any]]] = []
    current_segment: List[Dict[str, Any]] = []
    current_char = 0
    current_steps = 0

    for item in items:
        # Rough length estimate for segmentation
        approx_len = len(item["body"]) + len(item["heading_display"]) + 10
        additional_steps = 1 if item["kind"] == "step" else 0

        if current_segment and (
            current_char + approx_len > max_chars
            or current_steps + additional_steps > max_steps
        ):
            segments.append(current_segment)
            current_segment = []
            current_char = 0
            current_steps = 0

        current_segment.append(item)
        current_char += approx_len
        current_steps += additional_steps

    if current_segment:
        segments.append(current_segment)

    # --- Build final chunks with overlap + guide header in each chunk ------------

    chunks: List[Dict[str, Any]] = []
    chunk_index = 0

    for idx, seg in enumerate(segments):
        # Determine which step items to overlap from the previous segment
        overlap_items: List[Dict[str, Any]] = []
        if idx > 0 and step_overlap > 0:
            prev_seg = segments[idx - 1]
            prev_step_items = [it for it in prev_seg if it["kind"] == "step"]
            if prev_step_items:
                overlap_items = prev_step_items[-step_overlap:]

        ordered_items = overlap_items + seg

        lines: List[str] = []
        step_indices: List[int] = []
        headings: List[str] = []
        heading_seen = set()

        # Add guide context at top of every chunk
        lines.append(f"Guide: {title}")
        lines.append("")

        for item in ordered_items:
            if item["kind"] == "intro":
                heading_line = item["heading_display"]
            else:
                heading_line = f"Step {item['step_index']}: {item['heading_display']}"

            lines.append(heading_line)
            if item["body"]:
                lines.append(item["body"])
            lines.append("")  # blank line between items

            if item["kind"] == "step":
                if item["step_index"] not in step_indices:
                    step_indices.append(item["step_index"])

            if item["heading_display"] not in heading_seen:
                headings.append(item["heading_display"])
                heading_seen.add(item["heading_display"])

        content = "\n".join(lines).strip()

        chunks.append(
            {
                "chunk_index": chunk_index,
                "step_indices": step_indices,
                "headings": headings,
                "content": content,
            }
        )
        chunk_index += 1

    return chunks


# --- Main entrypoint ---------------------------------------------------------

def chunk_markdown_file(path: Path) -> List[Dict[str, Any]]:
    """
    Parse and chunk a single markdown file, returning a list of chunk dicts with metadata.
    """
    text = path.read_text(encoding="utf-8")
    title, intro_text, sections = parse_guide_sections(text)
    raw_chunks = chunk_sections(title, intro_text, sections)

    # Attach per-chunk metadata (source path, title, etc.)
    enriched: List[Dict[str, Any]] = []
    for c in raw_chunks:
        enriched.append(
            {
                "id": f"{path.stem}-{c['chunk_index']}",
                "source_path": str(path.as_posix()),
                "guide_title": title,
                "chunk_index": c["chunk_index"],
                "step_indices": c["step_indices"],
                "headings": c["headings"],
                "content": c["content"],
            }
        )
    return enriched


def main() -> None:
    parser = argparse.ArgumentParser(description="Chunk iFixit markdown guides.")
    parser.add_argument(
        "--input-dir",
        type=str,
        default="./ifixit_sample",
        help="Directory containing .md iFixit guides",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="./ifixit_chunks.json",
        help="Path to output JSON file",
    )

    args = parser.parse_args()
    input_dir = Path(args.input_dir)
    output_path = Path(args.output)

    if not input_dir.is_dir():
        raise SystemExit(f"Input directory not found: {input_dir}")

    all_chunks: List[Dict[str, Any]] = []

    for path in sorted(input_dir.glob("*.md")):
        print(f"Processing {path} ...")
        file_chunks = chunk_markdown_file(path)
        all_chunks.extend(file_chunks)

    print(f"Total chunks: {len(all_chunks)}")

    # Write as a flat list of chunk objects
    output_path.write_text(
        json.dumps(all_chunks, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Wrote chunks to: {output_path}")


if __name__ == "__main__":
    main()
