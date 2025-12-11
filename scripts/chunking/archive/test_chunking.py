#!/usr/bin/env python3
"""Test script for chunking iFixit guides - Console output only"""

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


@dataclass
class Chunk:
    """Represents a single chunk"""
    chunk_index: int
    content: str
    heading: Optional[str]
    token_count: int
    char_count: int
    word_count: int


class ChunkingTester:
    """Test chunking logic on iFixit guides"""
    
    def __init__(self):
        self.tokenizer = tiktoken.get_encoding("cl100k_base")  # OpenAI's tokenizer
        self.chunk_size_target = 600  # Target tokens per chunk
        self.chunk_size_min = 200     # Minimum tokens
        self.chunk_size_max = 1000    # Maximum tokens
        self.chunk_overlap = 75       # Overlap tokens
        
    def count_tokens(self, text: str) -> int:
        """Count tokens using tiktoken"""
        return len(self.tokenizer.encode(text))
    
    def detect_markdown_headings(self, text: str) -> List[Tuple[int, str, int]]:
        """
        Detect markdown headings in text.
        Returns: List of (line_number, heading_text, heading_level)
        """
        headings = []
        lines = text.split('\n')
        
        for i, line in enumerate(lines):
            # Match ## Step X. Title or ## Title (H2)
            h2_match = re.match(r'^##\s+(.+)$', line.strip())
            if h2_match:
                headings.append((i, h2_match.group(1), 2))
            # Match # Title (H1)
            else:
                h1_match = re.match(r'^#\s+(.+)$', line.strip())
                if h1_match:
                    headings.append((i, h1_match.group(1), 1))
        
        return headings
    
    def split_by_headings(self, text: str) -> List[Tuple[Optional[str], str]]:
        """
        Split text by markdown headings.
        Returns: List of (heading, content) tuples
        """
        headings = self.detect_markdown_headings(text)
        lines = text.split('\n')
        sections = []
        
        if not headings:
            # No headings found, return entire text as one section
            return [(None, text)]
        
        # Handle content before first heading
        if headings[0][0] > 0:
            pre_content = '\n'.join(lines[:headings[0][0]])
            if pre_content.strip():
                sections.append((None, pre_content))
        
        # Process each section between headings
        for i, (line_num, heading_text, level) in enumerate(headings):
            start_line = line_num
            
            # Find end of this section (start of next heading or end of text)
            if i + 1 < len(headings):
                end_line = headings[i + 1][0]
            else:
                end_line = len(lines)
            
            # Extract section content (include the heading line)
            section_lines = lines[start_line:end_line]
            section_content = '\n'.join(section_lines)
            
            sections.append((heading_text, section_content))
        
        return sections
    
    def split_large_section(self, content: str, heading: Optional[str]) -> List[Tuple[Optional[str], str]]:
        """
        Split a large section into smaller chunks by size.
        Uses overlap to preserve context.
        """
        token_count = self.count_tokens(content)
        
        if token_count <= self.chunk_size_max:
            return [(heading, content)]
        
        # Need to split this section
        chunks = []
        lines = content.split('\n')
        current_chunk_lines = []
        current_tokens = 0
        
        i = 0
        while i < len(lines):
            line = lines[i]
            line_tokens = self.count_tokens(line)
            
            # If adding this line would exceed max, save current chunk
            if current_tokens + line_tokens > self.chunk_size_max and current_chunk_lines:
                chunk_content = '\n'.join(current_chunk_lines)
                chunks.append((heading, chunk_content))
                
                # Start new chunk with overlap (last N lines of previous chunk)
                overlap_lines = []
                overlap_tokens = 0
                # Get last few lines that fit in overlap
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
        
        # Add remaining content
        if current_chunk_lines:
            chunk_content = '\n'.join(current_chunk_lines)
            chunks.append((heading, chunk_content))
        
        return chunks
    
    def combine_small_sections(self, sections: List[Tuple[Optional[str], str]]) -> List[Tuple[Optional[str], str]]:
        """
        Combine small sections together until they reach minimum size.
        Special handling: Always combine title/intro with first step, conclusion with last step.
        """
        if not sections:
            return []
        
        if len(sections) == 1:
            return sections
        
        # Special case: If first section is small (title/intro), combine with next
        first_heading, first_content = sections[0]
        first_tokens = self.count_tokens(first_content)
        
        # If first section is small and we have more sections, combine with next
        if first_tokens < self.chunk_size_min and len(sections) > 1:
            second_heading, second_content = sections[1]
            combined_content = '\n\n'.join([first_content, second_content])
            combined_tokens = self.count_tokens(combined_content)
            
            # Use the more descriptive heading (prefer step heading over title)
            combined_heading = second_heading if second_heading else first_heading
            
            # Start from section 2 (skip first two, already combined)
            remaining_sections = [(combined_heading, combined_content)] + sections[2:]
        else:
            remaining_sections = sections
        
        # Special case: If last section is small (conclusion), combine with previous
        if len(remaining_sections) > 1:
            last_heading, last_content = remaining_sections[-1]
            last_tokens = self.count_tokens(last_content)
            
            if last_tokens < self.chunk_size_min:
                # Combine with previous section
                prev_heading, prev_content = remaining_sections[-2]
                combined_content = '\n\n'.join([prev_content, last_content])
                combined_heading = prev_heading if prev_heading else last_heading
                
                # Replace last two with combined
                remaining_sections = remaining_sections[:-2] + [(combined_heading, combined_content)]
        
        # Now combine any remaining small sections in the middle
        # Improved: Keep combining small sections until we reach minimum size
        combined = []
        current_heading = None
        current_content = []
        current_tokens = 0
        
        for heading, content in remaining_sections:
            content_tokens = self.count_tokens(content)
            
            # Strategy: Keep combining until we reach minimum OR exceed max
            # If current is small (< min), always try to combine with next
            if current_tokens > 0 and current_tokens < self.chunk_size_min:
                # Current is small, combine with this one
                if current_heading is None:
                    current_heading = heading
                current_content.append(content)
                current_tokens += content_tokens
                
                # If we've reached minimum or exceeded max, save this chunk
                if current_tokens >= self.chunk_size_min or current_tokens > self.chunk_size_max:
                    combined.append((current_heading, '\n\n'.join(current_content)))
                    current_heading = None
                    current_content = []
                    current_tokens = 0
            elif current_tokens == 0:
                # Starting fresh
                if content_tokens < self.chunk_size_min:
                    # Small section, start accumulating
                    current_heading = heading
                    current_content = [content]
                    current_tokens = content_tokens
                else:
                    # Large enough, add as-is
                    combined.append((heading, content))
            else:
                # Current is already at minimum, save it and start new
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
        
        # Add remaining
        if current_content:
            combined.append((current_heading, '\n\n'.join(current_content)))
        
        # Final pass: Combine small chunks (< 200 tokens) with adjacent ones
        # This handles edge cases where many small steps couldn't reach minimum
        if len(combined) > 1:
            final_combined = []
            i = 0
            while i < len(combined):
                heading, content = combined[i]
                tokens = self.count_tokens(content)
                
                # If this chunk is below minimum (< 200), try to combine with next
                if tokens < self.chunk_size_min and i + 1 < len(combined):
                    next_heading, next_content = combined[i + 1]
                    next_tokens = self.count_tokens(next_content)
                    
                    # Combine if total is still reasonable (below max)
                    if tokens + next_tokens <= self.chunk_size_max:
                        combined_content = '\n\n'.join([content, next_content])
                        # Prefer step heading over generic heading
                        combined_heading = next_heading if next_heading else heading
                        final_combined.append((combined_heading, combined_content))
                        i += 2  # Skip next one, already combined
                        continue
                
                final_combined.append((heading, content))
                i += 1
            
            return final_combined
        
        return combined
    
    def chunk_text(self, text: str) -> List[Chunk]:
        """
        Main chunking function.
        Strategy:
        1. Split by markdown headings (## Step X)
        2. For large sections, split by size with overlap
        3. Combine small sections together
        """
        # Step 1: Split by headings
        sections = self.split_by_headings(text)
        
        # Step 2: Handle large sections (split them)
        processed_sections = []
        for heading, content in sections:
            token_count = self.count_tokens(content)
            if token_count > self.chunk_size_max:
                # Split large section
                split_sections = self.split_large_section(content, heading)
                processed_sections.extend(split_sections)
            else:
                processed_sections.append((heading, content))
        
        # Step 3: Combine small sections
        final_sections = self.combine_small_sections(processed_sections)
        
        # Step 4: Create Chunk objects
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
    
    def fetch_test_guides(self, limit: int = 6) -> List[Dict[str, Any]]:
        """Fetch iFixit guides from database for testing - mix of small, medium, and large"""
        dsn = os.getenv("DATABASE_URL")
        if not dsn:
            print("\n❌ ERROR: DATABASE_URL not found in environment!")
            print("\nPlease set DATABASE_URL in one of these ways:")
            print("1. Create a .env file in the scripts directory with: DATABASE_URL=your_connection_string")
            print("2. Set it as an environment variable")
            print("3. Export it in your terminal: $env:DATABASE_URL='your_connection_string' (PowerShell)")
            raise ValueError("DATABASE_URL not set in environment")
        
        conn = psycopg2.connect(dsn)
        try:
            cursor = conn.cursor()
            guides = []
            
            # Fetch 2 small guides (< 500 words)
            query_small = """
                SELECT 
                    id,
                    title,
                    raw_content,
                    word_count,
                    metadata
                FROM knowledge_sources
                WHERE source_type = 'ifixit' AND word_count < 500
                ORDER BY word_count
                LIMIT 2
            """
            cursor.execute(query_small)
            for row in cursor.fetchall():
                guides.append({
                    'id': row[0],
                    'title': row[1],
                    'raw_content': row[2],
                    'word_count': row[3],
                    'metadata': row[4]
                })
            
            # Fetch 2 medium guides (500-2000 words)
            query_medium = """
                SELECT 
                    id,
                    title,
                    raw_content,
                    word_count,
                    metadata
                FROM knowledge_sources
                WHERE source_type = 'ifixit' 
                    AND word_count >= 500 
                    AND word_count < 2000
                ORDER BY word_count
                LIMIT 2
            """
            cursor.execute(query_medium)
            for row in cursor.fetchall():
                guides.append({
                    'id': row[0],
                    'title': row[1],
                    'raw_content': row[2],
                    'word_count': row[3],
                    'metadata': row[4]
                })
            
            # Fetch 2 large guides (2000+ words)
            query_large = """
                SELECT 
                    id,
                    title,
                    raw_content,
                    word_count,
                    metadata
                FROM knowledge_sources
                WHERE source_type = 'ifixit' AND word_count >= 2000
                ORDER BY word_count DESC
                LIMIT 2
            """
            cursor.execute(query_large)
            for row in cursor.fetchall():
                guides.append({
                    'id': row[0],
                    'title': row[1],
                    'raw_content': row[2],
                    'word_count': row[3],
                    'metadata': row[4]
                })
            
            return guides
        finally:
            conn.close()
    
    def print_chunk_results(self, guide: Dict[str, Any], chunks: List[Chunk]):
        """Print chunking results to console"""
        print("\n" + "="*80)
        print(f"GUIDE: {guide['title']}")
        print(f"ID: {guide['id']}")
        print(f"Original word count: {guide['word_count']}")
        print(f"Original char count: {len(guide['raw_content'])}")
        print(f"Original token count: {self.count_tokens(guide['raw_content'])}")
        print("="*80)
        
        print(f"\n📦 CHUNKS CREATED: {len(chunks)}\n")
        
        total_tokens = 0
        for chunk in chunks:
            total_tokens += chunk.token_count
            print(f"Chunk {chunk.chunk_index}:")
            print(f"  Heading: {chunk.heading or '(no heading)'}")
            print(f"  Tokens: {chunk.token_count}")
            print(f"  Words: {chunk.word_count}")
            print(f"  Chars: {chunk.char_count}")
            print(f"  Preview: {chunk.content[:150].replace(chr(10), ' ')}...")
            print()
        
        print(f"Total tokens across all chunks: {total_tokens}")
        print(f"Original tokens: {self.count_tokens(guide['raw_content'])}")
        print(f"Token difference: {total_tokens - self.count_tokens(guide['raw_content'])} (overlap adds tokens)")
        print("\n" + "="*80 + "\n")
    
    def run_tests(self, num_guides: int = 6):
        """Run chunking tests on sample guides"""
        print("🔍 Fetching iFixit guides from database (mix of small, medium, and large)...")
        guides = self.fetch_test_guides(num_guides)
        
        if not guides:
            print("❌ No iFixit guides found in database!")
            return
        
        print(f"✅ Found {len(guides)} guides\n")
        
        for guide in guides:
            chunks = self.chunk_text(guide['raw_content'])
            self.print_chunk_results(guide, chunks)


def main():
    """Main entry point"""
    tester = ChunkingTester()
    tester.run_tests(num_guides=6)


if __name__ == "__main__":
    main()

