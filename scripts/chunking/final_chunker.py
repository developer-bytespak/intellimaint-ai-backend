#!/usr/bin/env python3
"""
Standalone canonical chunker (finalized)

This file is self-contained and implements the finalized chunking strategy:
- heading-aware splitting
- sentence/section handling with token-window slicing for oversized pieces
- small-section merge heuristics
- token-count caching with FAST_TOKEN_APPROX toggle
- final deterministic enforcement pass that re-slices any chunk exceeding the hard cap

It intentionally does not import other project modules so it can be moved or used independently.
"""
from __future__ import annotations
import os
import re
import json
import argparse
import importlib
import importlib.util
from typing import List, Optional, Tuple, Dict, Any, TYPE_CHECKING

# For static type checkers: expose tiktoken symbol for type hints without requiring runtime import
if TYPE_CHECKING:
    import tiktoken  # type: ignore

# Runtime import of optional tiktoken package (silences Pylance unresolved-import warnings)
_tiktoken_spec = importlib.util.find_spec("tiktoken")
if _tiktoken_spec is not None:
    try:
        tiktoken = importlib.import_module("tiktoken")
        _HAS_TIKTOKEN = True
    except Exception:
        tiktoken = None
        _HAS_TIKTOKEN = False
else:
    tiktoken = None
    _HAS_TIKTOKEN = False

FAST_TOKEN_APPROX = os.getenv("FAST_TOKEN_APPROX", "0") == "1"


class TokenCounter:
    def __init__(self, enc_name: str = "cl100k_base"):
        self._cache: Dict[str, int] = {}
        self.enc_name = enc_name
        if _HAS_TIKTOKEN:
            try:
                self.tokenizer = tiktoken.get_encoding(enc_name)
            except Exception:
                # fallback to a simple tiktoken wrapper if needed
                self.tokenizer = None
        else:
            self.tokenizer = None

    def count(self, text: str) -> int:
        if not text:
            return 0
        if FAST_TOKEN_APPROX:
            return max(0, len(text) // 4)
        # use cache key truncated for long texts
        key = text if len(text) <= 2000 else text[:2000]
        if key in self._cache:
            return self._cache[key]
        if self.tokenizer is not None:
            try:
                v = len(self.tokenizer.encode(text))
            except Exception:
                v = len(text.split())
        else:
            # fallback: approximate by word count
            v = len(text.split())
        self._cache[key] = v
        return v

    # helper to expose encode/decode when tokenizer available
    def encode(self, text: str) -> List[int]:
        if self.tokenizer is None:
            # fallback: approximate by word boundaries into pseudo-ids
            return [len(w) for w in text.split()]
        return self.tokenizer.encode(text)

    def decode(self, tids: List[int]) -> str:
        if self.tokenizer is None:
            # can't reliably decode pseudo-ids — join with spaces
            return " ".join(str(t) for t in tids)
        return self.tokenizer.decode(tids)


class CustomChunking:
    def __init__(self,
                 counter: TokenCounter,
                 chunk_target: int = 300,
                 chunk_size_max: int = 450,
                 chunk_size_min: int = 180,
                 chunk_overlap: int = 50):
        self.counter = counter
        self.tokenizer = counter
        self.chunk_target = chunk_target
        self.chunk_size_max = chunk_size_max
        self.chunk_size_min = chunk_size_min
        self.chunk_overlap = chunk_overlap

    # ------------------ PDF/markdown normalization ------------------
    def normalize_pdf_markdown(self, text: str) -> str:
        # Remove obvious TOC headings and isolated short lines that look like markers
        text = re.sub(r'(?mi)^\s*(table of contents|contents)\s*$', '', text)
        # remove lines that are just bullets or page numbers
        text = re.sub(r'(?m)^[-•*\d\.)\s]{1,20}$', '', text)

        # join wrapped paragraph lines (heuristic): if a line is not a heading
        # and next line is not a heading or blank, merge them with a space
        lines = text.splitlines()
        out_lines: List[str] = []
        for i, ln in enumerate(lines):
            if ln.strip().startswith('#') or ln.strip() == '':
                out_lines.append(ln)
                continue
            if out_lines and out_lines[-1].strip() and not out_lines[-1].strip().startswith('#'):
                out_lines[-1] = out_lines[-1].rstrip() + ' ' + ln.strip()
            else:
                out_lines.append(ln)
        normalized = '\n'.join(out_lines)

        # attach leading image/table markers to following paragraph
        normalized = re.sub(r'(?m)^(!\[.*\]\(.*\))\s*$', lambda m: m.group(1).rstrip() + '\n', normalized)
        return normalized

    # ------------------ Heading splitting ------------------
    def detect_markdown_headings(self, text: str) -> List[Tuple[int, str, int]]:
        headings: List[Tuple[int, str, int]] = []
        lines = text.splitlines()
        for i, line in enumerate(lines):
            m = re.match(r'^(#{1,6})\s+(.*)', line.strip())
            if m:
                level = len(m.group(1))
                headings.append((i, m.group(2).strip(), level))
        return headings

    def split_by_headings(self, text: str) -> List[Tuple[Optional[str], str]]:
        headings = self.detect_markdown_headings(text)
        lines = text.splitlines()
        if not headings:
            return [(None, text)]
        sections: List[Tuple[Optional[str], str]] = []
        # pre-heading text
        if headings[0][0] > 0:
            pre = '\n'.join(lines[:headings[0][0]]).strip()
            if pre:
                sections.append((None, pre))
        for idx, (ln, htxt, lvl) in enumerate(headings):
            start = ln
            end = headings[idx+1][0] if idx+1 < len(headings) else len(lines)
            sec = '\n'.join(lines[start:end]).strip()
            sections.append((htxt, sec))
        return sections

    # ------------------ Large section split by token window ------------------
    def split_large_section(self, content: str, heading: Optional[str]) -> List[Tuple[Optional[str], str]]:
        if self.counter.count(content) <= self.chunk_size_max:
            return [(heading, content)]
        # token-id slicing with overlap
        tids = self.counter.encode(content)
        safety = 8
        window = max(1, self.chunk_size_max - safety)
        step = max(1, window - self.chunk_overlap)
        pieces: List[Tuple[Optional[str], str]] = []
        first = True
        for start in range(0, len(tids), step):
            piece = tids[start:start + window]
            if not piece:
                continue
            try:
                txt = self.counter.decode(piece).strip()
            except Exception:
                # best-effort stringify
                txt = ' '.join(str(x) for x in piece)
            pieces.append((heading if first else None, txt))
            first = False
        return pieces

    # ------------------ Combine small sections ------------------
    def combine_small_sections(self, sections: List[Tuple[Optional[str], str]]) -> List[Tuple[Optional[str], str]]:
        if not sections:
            return []
        merged: List[Tuple[Optional[str], str]] = []
        for heading, content in sections:
            if not merged:
                merged.append((heading, content))
                continue
            prev_h, prev_c = merged[-1]
            prev_tokens = self.counter.count(prev_c)
            cur_tokens = self.counter.count(content)
            # prefer merging into previous if it doesn't exceed max
            if prev_tokens < self.chunk_size_min or (prev_tokens + cur_tokens) <= self.chunk_size_max:
                merged[-1] = (prev_h, prev_c + "\n\n" + content)
            else:
                merged.append((heading, content))
        return merged

    # ------------------ Final enforcement: hard cap ------------------
    def enforce_hard_cap(self, sections: List[Tuple[Optional[str], str]]) -> List[Tuple[Optional[str], str]]:
        enforced: List[Tuple[Optional[str], str]] = []
        safety = 8
        window = max(1, self.chunk_size_max - safety)
        step = max(1, window - self.chunk_overlap)
        for heading, txt in sections:
            tcount = self.counter.count(txt)
            if tcount <= self.chunk_size_max:
                enforced.append((heading, txt))
                continue
            try:
                tids = self.counter.encode(txt)
                first = True
                for start in range(0, len(tids), step):
                    piece = tids[start:start + window]
                    if not piece:
                        continue
                    try:
                        ptxt = self.counter.decode(piece).strip()
                    except Exception:
                        ptxt = ' '.join(str(x) for x in piece)
                    enforced.append((heading if first else None, ptxt))
                    first = False
            except Exception:
                # fallback word-slice
                words = txt.split()
                buf: List[str] = []
                first_piece = True
                for w in words:
                    buf.append(w)
                    if self.counter.count(" ".join(buf)) >= self.chunk_size_max:
                        enforced.append((heading if first_piece else None, " ".join(buf).strip()))
                        buf = []
                        first_piece = False
                if buf:
                    enforced.append((heading if first_piece else None, " ".join(buf).strip()))
        return enforced

    # ------------------ Top-level chunking ------------------
    def chunk_text(self, raw: str) -> List[Dict[str, Any]]:
        txt = self.normalize_pdf_markdown(raw)
        secs = self.split_by_headings(txt)
        processed: List[Tuple[Optional[str], str]] = []
        for h, c in secs:
            if self.counter.count(c) > self.chunk_size_max:
                processed.extend(self.split_large_section(c, h))
            else:
                processed.append((h, c))
        processed = self.combine_small_sections(processed)
        processed = self.enforce_hard_cap(processed)
        out: List[Dict[str, Any]] = []
        for i, (h, c) in enumerate(processed):
            out.append({
                "chunk_index": i,
                "heading": h,
                "content": c,
                "token_count": self.counter.count(c),
                "char_count": len(c),
                "word_count": len(c.split())
            })
        return out


def main():
    ap = argparse.ArgumentParser(prog="final_chunker.py")
    ap.add_argument("--file", "-f", required=True, help="markdown file to chunk")
    ap.add_argument("--out", "-o", help="output json file (optional)")
    args = ap.parse_args()

    with open(args.file, "r", encoding="utf-8") as fh:
        raw = fh.read()
    counter = TokenCounter()
    chunker = CustomChunking(counter)
    chunks = chunker.chunk_text(raw)
    payload = {"file": args.file, "chunks": chunks}
    if args.out:
        with open(args.out, "w", encoding="utf-8") as oh:
            json.dump(payload, oh, indent=2, ensure_ascii=False)
    else:
        print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
