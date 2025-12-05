#!/usr/bin/env python3
"""Compare different chunking approaches side-by-side"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import psycopg2
import tiktoken
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# LangChain removed: this script now only contains the custom chunker implementation


@dataclass
class Chunk:
    """Represents a single chunk"""
    chunk_index: int
    content: str
    heading: Optional[str]
    token_count: int
    char_count: int
    word_count: int
    approach: str  # e.g. "custom"


class CustomChunking:
    """Heading-aware chunker tuned for ifixit + normalized PDF markdown."""

    def __init__(self):
        self.tokenizer = tiktoken.get_encoding("cl100k_base")
        # Tuned defaults
        self.chunk_target = 300         # target tokens (used for sentence-based splitting)
        self.chunk_size_max = 500       # hard cap tokens for a single chunk
        self.chunk_size_min = 150       # merge until >= this
        self.chunk_overlap = 50         # tokens to overlap between adjacent chunks

    def count_tokens(self, text: str) -> int:
        return len(self.tokenizer.encode(text)) if text else 0

    def detect_markdown_headings(self, text: str) -> List[Tuple[int, str, int]]:
        headings = []
        lines = text.splitlines()
        for i, line in enumerate(lines):
            s = line.strip()
            h2_match = re.match(r'^##\s+(.+)$', s)
            if h2_match:
                headings.append((i, h2_match.group(1), 2))
            else:
                h1_match = re.match(r'^#\s+(.+)$', s)
                if h1_match:
                    headings.append((i, h1_match.group(1), 1))
        return headings

    def split_by_headings(self, text: str) -> List[Tuple[Optional[str], str]]:
        headings = self.detect_markdown_headings(text)
        lines = text.splitlines()
        sections: List[Tuple[Optional[str], str]] = []

        if not headings:
            return [(None, text)]

        # content before first heading
        if headings[0][0] > 0:
            pre = "\n".join(lines[:headings[0][0]]).strip()
            if pre:
                sections.append((None, pre))

        for i, (line_num, heading_text, level) in enumerate(headings):
            start = line_num
            end = headings[i + 1][0] if i + 1 < len(headings) else len(lines)
            section_text = "\n".join(lines[start:end]).strip()
            sections.append((heading_text, section_text))
        return sections

    def _split_into_sentences(self, text: str) -> List[str]:
        # Naive sentence splitter (keeps punctuation). Good enough for chunking.
        parts = re.split(r'(?<=[\.\?\!])\s+', text)
        if len(parts) == 1:
            parts = text.splitlines()
        return [p.strip() for p in parts if p and p.strip()]

    def split_large_section(self, content: str, heading: Optional[str]) -> List[Tuple[Optional[str], str]]:
        total_tokens = self.count_tokens(content)
        if total_tokens <= self.chunk_size_max:
            return [(heading, content)]

        sentences = self._split_into_sentences(content)
        chunks: List[Tuple[Optional[str], str]] = []
        current_sentences: List[str] = []
        current_tokens = 0

        def flush_chunk():
            nonlocal current_sentences, current_tokens
            if current_sentences:
                chunk_text = " ".join(current_sentences).strip()
                chunks.append((heading, chunk_text))
                overlap_sentences: List[str] = []
                overlap_tokens = 0
                for s in reversed(current_sentences):
                    tok = self.count_tokens(s)
                    if overlap_tokens + tok <= self.chunk_overlap:
                        overlap_sentences.insert(0, s)
                        overlap_tokens += tok
                    else:
                        break
                current_sentences = overlap_sentences
                current_tokens = overlap_tokens
            else:
                current_sentences = []
                current_tokens = 0

        for s in sentences:
            s_tokens = self.count_tokens(s)
            if s_tokens > self.chunk_size_max:
                words = s.split()
                piece = []
                piece_tokens = 0
                for w in words:
                    w_tok = self.count_tokens(w + " ")
                    if piece_tokens + w_tok > self.chunk_size_max and piece:
                        current_sentences.append(" ".join(piece))
                        flush_chunk()
                        piece = [w]
                        piece_tokens = w_tok
                    else:
                        piece.append(w)
                        piece_tokens += w_tok
                if piece:
                    current_sentences.append(" ".join(piece))
                    current_tokens += piece_tokens
            else:
                if current_tokens + s_tokens > self.chunk_size_max and current_sentences:
                    flush_chunk()
                current_sentences.append(s)
                current_tokens += s_tokens

        if current_sentences:
            chunk_text = " ".join(current_sentences).strip()
            chunks.append((heading, chunk_text))
        return chunks

    def combine_small_sections(self, sections: List[Tuple[Optional[str], str]]) -> List[Tuple[Optional[str], str]]:
        if not sections:
            return []
        merged: List[Tuple[Optional[str], str]] = []
        carry_heading: Optional[str] = None
        carry_texts: List[str] = []
        carry_tokens = 0

        def emit_carry():
            nonlocal carry_heading, carry_texts, carry_tokens
            if carry_texts:
                combined_text = "\n\n".join(carry_texts).strip()
                merged.append((carry_heading, combined_text))
            carry_heading = None
            carry_texts = []
            carry_tokens = 0

        for heading, content in sections:
            tok = self.count_tokens(content)
            is_marker_only = re.fullmatch(r'^\s*(?:\[IMAGE[:\d]*\]|\[TABLE_PLACEHOLDER\]|\[_IMAGE\]|\[TABLE\])\s*$', content, re.IGNORECASE) is not None
            if carry_tokens == 0:
                carry_heading = heading
                carry_texts = [content]
                carry_tokens = tok
                if carry_tokens >= self.chunk_size_min and not is_marker_only:
                    emit_carry()
                continue
            else:
                if carry_tokens + tok <= self.chunk_size_max:
                    carry_texts.append(content)
                    carry_tokens += tok
                    if carry_tokens >= self.chunk_size_min and not is_marker_only:
                        emit_carry()
                    else:
                        continue
                else:
                    emit_carry()
                    carry_heading = heading
                    carry_texts = [content]
                    carry_tokens = tok
                    if carry_tokens >= self.chunk_size_min and not is_marker_only:
                        emit_carry()
                    continue

        emit_carry()

        final: List[Tuple[Optional[str], str]] = []
        for h, c in merged:
            if final and self.count_tokens(c) < self.chunk_size_min:
                prev_h, prev_c = final[-1]
                combined = prev_c + "\n\n" + c
                final[-1] = (prev_h if prev_h else h, combined)
            else:
                final.append((h, c))
        return final

    def chunk_text(self, text: str) -> List[Chunk]:
        sections = self.split_by_headings(text)
        processed: List[Tuple[Optional[str], str]] = []

        for heading, content in sections:
            tok = self.count_tokens(content)
            if tok > self.chunk_size_max:
                splits = self.split_large_section(content, heading)
                processed.extend(splits)
            else:
                processed.append((heading, content))

        final_sections = self.combine_small_sections(processed)

        chunks: List[Chunk] = []
        for idx, (heading, content) in enumerate(final_sections):
            token_count = self.count_tokens(content)
            chunks.append(Chunk(
                chunk_index=idx,
                content=content,
                heading=heading,
                token_count=token_count,
                char_count=len(content),
                word_count=len(content.split()),
                approach="custom"
            ))
        return chunks


# LangChain code removed to keep repository lightweight and deterministic.


def fetch_test_guides() -> List[Dict[str, Any]]:
    """Fetch a mix of guides for testing"""
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        raise ValueError("DATABASE_URL not set")
    
    conn = psycopg2.connect(dsn)
    try:
        cursor = conn.cursor()
        guides = []
        
        # 1 small, 1 medium, 1 large
        queries = [
            ("Small", "WHERE source_type = 'ifixit' AND word_count < 500 ORDER BY word_count LIMIT 1"),
            ("Medium", "WHERE source_type = 'ifixit' AND word_count >= 500 AND word_count < 2000 ORDER BY word_count LIMIT 1"),
            ("Large", "WHERE source_type = 'ifixit' AND word_count >= 2000 ORDER BY word_count DESC LIMIT 1"),
        ]
        
        for label, where_clause in queries:
            query = f"""
                SELECT id, title, raw_content, word_count, metadata
                FROM knowledge_sources
                {where_clause}
            """
            cursor.execute(query)
            row = cursor.fetchone()
            if row:
                guides.append({
                    'id': row[0],
                    'title': row[1],
                    'raw_content': row[2],
                    'word_count': row[3],
                    'metadata': row[4],
                    'size_label': label
                })
        
        return guides
    finally:
        conn.close()


def print_custom_summary(guide: Dict[str, Any], custom_chunks: List[Chunk]):
    """Print summary statistics for the custom chunker."""
    tokenizer = tiktoken.get_encoding("cl100k_base")
    original_tokens = len(tokenizer.encode(guide['raw_content']))

    print("\n" + "="*100)
    print(f"GUIDE: {guide['title']} ({guide['size_label']}) - CUSTOM APPROACH ONLY")
    print(f"Original: {guide['word_count']} words, {original_tokens} tokens")
    print("="*100)

    print(f"Chunks: {len(custom_chunks)}")
    custom_tokens = [c.token_count for c in custom_chunks]
    print(f"Avg tokens: {sum(custom_tokens)/len(custom_tokens):.0f}")
    print(f"Min tokens: {min(custom_tokens)}")
    print(f"Max tokens: {max(custom_tokens)}")
    print(f"Chunks with headings: {sum(1 for c in custom_chunks if c.heading)}/{len(custom_chunks)}")

    print(f"\nFIRST 3 CHUNKS - CUSTOM")
    print("-" * 80)
    for i in range(min(3, len(custom_chunks))):
        c = custom_chunks[i]
        print(f"#{i+1} [{c.token_count}t] {c.heading or 'No heading'}")
        print(f"  {c.content[:200].replace(chr(10), ' ')}...")
        print()

    print("="*100 + "\n")


def main():
    """Compare approaches"""
    print("🔍 Comparing Chunking Approaches\n")
    guides = fetch_test_guides()
    custom_chunker = CustomChunking()

    for guide in guides:
        custom_chunks = custom_chunker.chunk_text(guide['raw_content'])
        print_custom_summary(guide, custom_chunks)


if __name__ == "__main__":
    main()

