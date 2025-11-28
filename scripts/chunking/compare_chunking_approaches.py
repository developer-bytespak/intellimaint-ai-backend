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

try:
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    LANGCHAIN_AVAILABLE = True
except ImportError:
    try:
        from langchain.text_splitter import RecursiveCharacterTextSplitter
        LANGCHAIN_AVAILABLE = True
    except ImportError:
        LANGCHAIN_AVAILABLE = False
        print("⚠️  LangChain not installed. Install with: pip install langchain langchain-text-splitters")
        print("   Will only test custom approach.\n")


@dataclass
class Chunk:
    """Represents a single chunk"""
    chunk_index: int
    content: str
    heading: Optional[str]
    token_count: int
    char_count: int
    word_count: int
    approach: str  # "custom" or "langchain"


class CustomChunking:
    """Our custom chunking approach - heading-aware"""
    
    def __init__(self):
        self.tokenizer = tiktoken.get_encoding("cl100k_base")
        self.chunk_size_target = 600
        self.chunk_size_min = 200
        self.chunk_size_max = 1000
        self.chunk_overlap = 75
        
    def count_tokens(self, text: str) -> int:
        return len(self.tokenizer.encode(text))
    
    def detect_markdown_headings(self, text: str) -> List[Tuple[int, str, int]]:
        headings = []
        lines = text.split('\n')
        
        for i, line in enumerate(lines):
            h2_match = re.match(r'^##\s+(.+)$', line.strip())
            if h2_match:
                headings.append((i, h2_match.group(1), 2))
            else:
                h1_match = re.match(r'^#\s+(.+)$', line.strip())
                if h1_match:
                    headings.append((i, h1_match.group(1), 1))
        
        return headings
    
    def split_by_headings(self, text: str) -> List[Tuple[Optional[str], str]]:
        headings = self.detect_markdown_headings(text)
        lines = text.split('\n')
        sections = []
        
        if not headings:
            return [(None, text)]
        
        # Handle content before first heading
        if headings[0][0] > 0:
            pre_content = '\n'.join(lines[:headings[0][0]])
            if pre_content.strip():
                sections.append((None, pre_content))
        
        for i, (line_num, heading_text, level) in enumerate(headings):
            start_line = line_num
            if i + 1 < len(headings):
                end_line = headings[i + 1][0]
            else:
                end_line = len(lines)
            
            section_lines = lines[start_line:end_line]
            section_content = '\n'.join(section_lines)
            sections.append((heading_text, section_content))
        
        return sections
    
    def split_large_section(self, content: str, heading: Optional[str]) -> List[Tuple[Optional[str], str]]:
        token_count = self.count_tokens(content)
        
        if token_count <= self.chunk_size_max:
            return [(heading, content)]
        
        chunks = []
        lines = content.split('\n')
        current_chunk_lines = []
        current_tokens = 0
        
        i = 0
        while i < len(lines):
            line = lines[i]
            line_tokens = self.count_tokens(line)
            
            if current_tokens + line_tokens > self.chunk_size_max and current_chunk_lines:
                chunk_content = '\n'.join(current_chunk_lines)
                chunks.append((heading, chunk_content))
                
                overlap_lines = []
                overlap_tokens = 0
                for j in range(len(current_chunk_lines) - 1, -1, -1):
                    line_tok = self.count_tokens(current_chunk_lines[j])
                    if overlap_tokens + line_tok <= self.chunk_overlap:
                        overlap_lines.insert(0, current_chunk_lines[j])
                        overlap_tokens += line_tok
                    else:
                        break
                
                current_chunk_lines = overlap_lines
                current_tokens = overlap_tokens
            else:
                current_chunk_lines.append(line)
                current_tokens += line_tokens
                i += 1
        
        if current_chunk_lines:
            chunk_content = '\n'.join(current_chunk_lines)
            chunks.append((heading, chunk_content))
        
        return chunks
    
    def combine_small_sections(self, sections: List[Tuple[Optional[str], str]]) -> List[Tuple[Optional[str], str]]:
        if not sections:
            return []
        
        if len(sections) == 1:
            return sections
        
        first_heading, first_content = sections[0]
        first_tokens = self.count_tokens(first_content)
        
        if first_tokens < self.chunk_size_min and len(sections) > 1:
            second_heading, second_content = sections[1]
            combined_content = '\n\n'.join([first_content, second_content])
            combined_heading = second_heading if second_heading else first_heading
            remaining_sections = [(combined_heading, combined_content)] + sections[2:]
        else:
            remaining_sections = sections
        
        if len(remaining_sections) > 1:
            last_heading, last_content = remaining_sections[-1]
            last_tokens = self.count_tokens(last_content)
            
            if last_tokens < self.chunk_size_min:
                prev_heading, prev_content = remaining_sections[-2]
                combined_content = '\n\n'.join([prev_content, last_content])
                combined_heading = prev_heading if prev_heading else last_heading
                remaining_sections = remaining_sections[:-2] + [(combined_heading, combined_content)]
        
        combined = []
        current_heading = None
        current_content = []
        current_tokens = 0
        
        for heading, content in remaining_sections:
            content_tokens = self.count_tokens(content)
            
            if current_tokens + content_tokens < self.chunk_size_min:
                if current_heading is None:
                    current_heading = heading
                current_content.append(content)
                current_tokens += content_tokens
            else:
                if current_content:
                    combined.append((current_heading, '\n\n'.join(current_content)))
                
                if content_tokens < self.chunk_size_min:
                    current_heading = heading
                    current_content = [content]
                    current_tokens = content_tokens
                else:
                    combined.append((heading, content))
                    current_heading = None
                    current_content = []
                    current_tokens = 0
        
        if current_content:
            combined.append((current_heading, '\n\n'.join(current_content)))
        
        return combined
    
    def chunk_text(self, text: str) -> List[Chunk]:
        sections = self.split_by_headings(text)
        
        processed_sections = []
        for heading, content in sections:
            token_count = self.count_tokens(content)
            if token_count > self.chunk_size_max:
                split_sections = self.split_large_section(content, heading)
                processed_sections.extend(split_sections)
            else:
                processed_sections.append((heading, content))
        
        final_sections = self.combine_small_sections(processed_sections)
        
        chunks = []
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


class LangChainChunking:
    """LangChain's RecursiveCharacterTextSplitter approach"""
    
    def __init__(self):
        if not LANGCHAIN_AVAILABLE:
            raise ImportError("LangChain not installed")
        
        self.tokenizer = tiktoken.get_encoding("cl100k_base")
        # LangChain uses character count, but we'll configure it to approximate tokens
        # ~4 characters per token on average
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=2400,  # ~600 tokens * 4 chars
            chunk_overlap=300,  # ~75 tokens * 4 chars
            separators=["\n\n", "\n", ". ", " ", ""],
            length_function=len,
        )
        
    def count_tokens(self, text: str) -> int:
        return len(self.tokenizer.encode(text))
    
    def chunk_text(self, text: str) -> List[Chunk]:
        # LangChain doesn't preserve headings, so we'll try to detect them after
        text_chunks = self.splitter.split_text(text)
        
        chunks = []
        for idx, chunk_text in enumerate(text_chunks):
            # Try to extract heading from chunk (first ## or # line)
            heading = None
            lines = chunk_text.split('\n')
            for line in lines[:5]:  # Check first 5 lines
                h2_match = re.match(r'^##\s+(.+)$', line.strip())
                if h2_match:
                    heading = h2_match.group(1)
                    break
                h1_match = re.match(r'^#\s+(.+)$', line.strip())
                if h1_match:
                    heading = h1_match.group(1)
                    break
            
            token_count = self.count_tokens(chunk_text)
            chunks.append(Chunk(
                chunk_index=idx,
                content=chunk_text,
                heading=heading,
                token_count=token_count,
                char_count=len(chunk_text),
                word_count=len(chunk_text.split()),
                approach="langchain"
            ))
        
        return chunks


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


def print_comparison(guide: Dict[str, Any], custom_chunks: List[Chunk], langchain_chunks: List[Chunk]):
    """Print side-by-side comparison"""
    tokenizer = tiktoken.get_encoding("cl100k_base")
    original_tokens = len(tokenizer.encode(guide['raw_content']))
    
    print("\n" + "="*100)
    print(f"GUIDE: {guide['title']} ({guide['size_label']})")
    print(f"Original: {guide['word_count']} words, {original_tokens} tokens")
    print("="*100)
    
    tokenizer = tiktoken.get_encoding("cl100k_base")
    original_tokens = len(tokenizer.encode(guide['raw_content']))
    
    print(f"\n{'CUSTOM APPROACH':<50} | {'LANGCHAIN APPROACH':<50}")
    print("-" * 100)
    print(f"Chunks: {len(custom_chunks):<49} | Chunks: {len(langchain_chunks)}")
    
    # Token statistics
    custom_tokens = [c.token_count for c in custom_chunks]
    langchain_tokens = [c.token_count for c in langchain_chunks]
    
    print(f"Avg tokens: {sum(custom_tokens)/len(custom_tokens):.0f}{'':<42} | Avg tokens: {sum(langchain_tokens)/len(langchain_tokens):.0f}")
    print(f"Min tokens: {min(custom_tokens):<49} | Min tokens: {min(langchain_tokens)}")
    print(f"Max tokens: {max(custom_tokens):<49} | Max tokens: {max(langchain_tokens)}")
    
    # Chunks with headings
    custom_with_headings = sum(1 for c in custom_chunks if c.heading)
    langchain_with_headings = sum(1 for c in langchain_chunks if c.heading)
    
    print(f"Chunks with headings: {custom_with_headings}/{len(custom_chunks)}{'':<35} | Chunks with headings: {langchain_with_headings}/{len(langchain_chunks)}")
    
    # Show first 3 chunks from each
    print(f"\n{'FIRST 3 CHUNKS - CUSTOM':<50} | {'FIRST 3 CHUNKS - LANGCHAIN':<50}")
    print("-" * 100)
    
    max_show = min(3, len(custom_chunks), len(langchain_chunks))
    for i in range(max_show):
        custom = custom_chunks[i]
        langchain = langchain_chunks[i] if i < len(langchain_chunks) else None
        
        custom_preview = f"#{i+1} [{custom.token_count}t] {custom.heading or 'No heading'}"
        if langchain:
            langchain_preview = f"#{i+1} [{langchain.token_count}t] {langchain.heading or 'No heading'}"
        else:
            langchain_preview = "N/A"
        
        print(f"{custom_preview:<50} | {langchain_preview:<50}")
        print(f"  {custom.content[:80].replace(chr(10), ' ')}...")
        if langchain:
            print(f"  {langchain.content[:80].replace(chr(10), ' ')}...")
        print()
    
    print("="*100 + "\n")


def main():
    """Compare approaches"""
    print("🔍 Comparing Chunking Approaches\n")
    
    if not LANGCHAIN_AVAILABLE:
        print("⚠️  LangChain not available. Install with: pip install langchain")
        print("   Will only show custom approach results.\n")
    
    guides = fetch_test_guides()
    custom_chunker = CustomChunking()
    
    if LANGCHAIN_AVAILABLE:
        langchain_chunker = LangChainChunking()
    else:
        langchain_chunker = None
    
    for guide in guides:
        custom_chunks = custom_chunker.chunk_text(guide['raw_content'])
        
        if langchain_chunker:
            langchain_chunks = langchain_chunker.chunk_text(guide['raw_content'])
            print_comparison(guide, custom_chunks, langchain_chunks)
        else:
            tokenizer = tiktoken.get_encoding("cl100k_base")
            original_tokens = len(tokenizer.encode(guide['raw_content']))
            
            print(f"\n{'='*100}")
            print(f"GUIDE: {guide['title']} ({guide['size_label']}) - CUSTOM APPROACH ONLY")
            print(f"Original: {guide['word_count']} words, {original_tokens} tokens")
            print(f"Chunks: {len(custom_chunks)}")
            print(f"Avg tokens: {sum(c.token_count for c in custom_chunks)/len(custom_chunks):.0f}")
            print(f"Chunks with headings: {sum(1 for c in custom_chunks if c.heading)}/{len(custom_chunks)}")
            print("="*100 + "\n")


if __name__ == "__main__":
    main()

