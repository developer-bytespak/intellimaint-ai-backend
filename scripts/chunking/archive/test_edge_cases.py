#!/usr/bin/env python3
"""Test chunking on edge cases to find issues"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import psycopg2
import tiktoken
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Chunk:
    chunk_index: int
    content: str
    heading: Optional[str]
    token_count: int
    char_count: int
    word_count: int


class ChunkingTester:
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
                word_count=len(content.split())
            ))
        
        return chunks
    
    def fetch_edge_case_guides(self) -> List[Dict[str, Any]]:
        """Fetch guides that might have edge cases"""
        dsn = os.getenv("DATABASE_URL")
        if not dsn:
            raise ValueError("DATABASE_URL not set")
        
        conn = psycopg2.connect(dsn)
        try:
            cursor = conn.cursor()
            guides = []
            
            # Test cases:
            # 1. Very short guide (< 100 words)
            # 2. Guide with no steps (just title/intro)
            # 3. Guide with very long single step
            # 4. Guide with many small steps
            # 5. Guide with unusual formatting
            
            queries = [
                ("Very Short", "WHERE source_type = 'ifixit' AND word_count < 100 ORDER BY word_count LIMIT 1"),
                ("Single Step", """
                    WHERE source_type = 'ifixit' 
                    AND raw_content NOT LIKE '%## 2.%'
                    AND raw_content LIKE '%## 1.%'
                    AND raw_content NOT LIKE '%## 3.%'
                    LIMIT 1
                """),
                ("Many Small Steps", """
                    WHERE source_type = 'ifixit' 
                    AND word_count BETWEEN 500 AND 1500
                    AND (LENGTH(raw_content) - LENGTH(REPLACE(raw_content, '##', ''))) / 2 > 10
                    ORDER BY (LENGTH(raw_content) - LENGTH(REPLACE(raw_content, '##', ''))) / 2 DESC
                    LIMIT 1
                """),
                ("Long Step", """
                    WHERE source_type = 'ifixit'
                    AND word_count > 2000
                    LIMIT 1
                """),
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
                        'test_case': label
                    })
            
            return guides
        finally:
            conn.close()
    
    def analyze_chunks(self, guide: Dict[str, Any], chunks: List[Chunk]):
        """Analyze chunks for potential issues"""
        issues = []
        
        # Check for very small chunks
        small_chunks = [c for c in chunks if c.token_count < self.chunk_size_min]
        if small_chunks:
            issues.append(f"⚠️  {len(small_chunks)} chunks below minimum ({self.chunk_size_min} tokens): {[c.token_count for c in small_chunks[:5]]}")
        
        # Check for very large chunks
        large_chunks = [c for c in chunks if c.token_count > self.chunk_size_max]
        if large_chunks:
            issues.append(f"⚠️  {len(large_chunks)} chunks above maximum ({self.chunk_size_max} tokens): {[c.token_count for c in large_chunks[:5]]}")
        
        # Check for chunks without headings
        no_heading = [c for c in chunks if not c.heading]
        if no_heading:
            issues.append(f"⚠️  {len(no_heading)} chunks without headings")
        
        # Check token distribution
        if chunks:
            avg_tokens = sum(c.token_count for c in chunks) / len(chunks)
            if avg_tokens < 300 or avg_tokens > 700:
                issues.append(f"⚠️  Average chunk size ({avg_tokens:.0f} tokens) outside ideal range (300-700)")
        
        return issues
    
    def print_results(self, guide: Dict[str, Any], chunks: List[Chunk]):
        """Print test results"""
        print("\n" + "="*80)
        print(f"TEST CASE: {guide['test_case']}")
        print(f"GUIDE: {guide['title']}")
        print(f"Original: {guide['word_count']} words, {self.count_tokens(guide['raw_content'])} tokens")
        print("="*80)
        
        print(f"\n📦 CHUNKS: {len(chunks)}")
        
        if chunks:
            tokens = [c.token_count for c in chunks]
            print(f"Token stats: min={min(tokens)}, max={max(tokens)}, avg={sum(tokens)/len(tokens):.0f}")
            print(f"Chunks with headings: {sum(1 for c in chunks if c.heading)}/{len(chunks)}")
        
        # Analyze for issues
        issues = self.analyze_chunks(guide, chunks)
        if issues:
            print("\n🔍 ISSUES FOUND:")
            for issue in issues:
                print(f"  {issue}")
        else:
            print("\n✅ No issues detected")
        
        # Show chunk details
        print(f"\nChunk Details:")
        for chunk in chunks[:5]:  # Show first 5
            print(f"  Chunk {chunk.chunk_index}: {chunk.token_count}t, heading: {chunk.heading or 'None'}")
            print(f"    Preview: {chunk.content[:100].replace(chr(10), ' ')}...")
        
        if len(chunks) > 5:
            print(f"  ... and {len(chunks) - 5} more chunks")
        
        print("="*80 + "\n")
    
    def run_edge_case_tests(self):
        """Run tests on edge cases"""
        print("🔍 Testing Edge Cases...\n")
        guides = self.fetch_edge_case_guides()
        
        if not guides:
            print("❌ No edge case guides found!")
            return
        
        print(f"✅ Found {len(guides)} test cases\n")
        
        for guide in guides:
            chunks = self.chunk_text(guide['raw_content'])
            self.print_results(guide, chunks)


def main():
    tester = ChunkingTester()
    tester.run_edge_case_tests()


if __name__ == "__main__":
    main()

