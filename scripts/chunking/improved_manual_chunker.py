#!/usr/bin/env python3
"""
Improved Universal Chunker for Technical Manuals
================================================

This chunker is optimized for:
- Camera manuals
- Equipment manuals  
- User guides
- Technical documentation

Key improvements over the original:
1. Lighter preprocessing - preserves more content
2. Better heading detection - catches more heading formats
3. Sentence-aware splitting - doesn't break mid-sentence
4. Improved overlap - cleaner context preservation
5. Preserves important metadata (names, model numbers, specs)
"""

import re
import json
import logging
from dataclasses import dataclass, field
from typing import Optional, List, Tuple, Dict, Any
from pathlib import Path

logger = logging.getLogger(__name__)

# Try to import tiktoken for accurate token counting
try:
    import tiktoken
    _enc = tiktoken.get_encoding("cl100k_base")
    HAS_TIKTOKEN = True
except ImportError:
    _enc = None
    HAS_TIKTOKEN = False


def count_tokens(text: str) -> int:
    """Count tokens using tiktoken or fallback to word-based estimate."""
    if not text:
        return 0
    if HAS_TIKTOKEN and _enc:
        try:
            return len(_enc.encode(text))
        except:
            pass
    # Fallback: ~1.3 tokens per word average
    return int(len(text.split()) * 1.3)


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class ChunkCandidate:
    """Raw chunk before final processing"""
    heading: Optional[str]
    content: str
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    image_urls: List[str] = field(default_factory=list)


@dataclass  
class Chunk:
    """Final chunk matching KnowledgeChunk Prisma schema"""
    chunk_index: int
    content: str
    heading: Optional[str]
    token_count: int
    metadata: dict
    
    def to_dict(self, source_id: str = None) -> dict:
        """Convert to dictionary for JSON/DB insertion"""
        result = {
            "chunk_index": self.chunk_index,
            "content": self.content,
            "heading": self.heading,
            "token_count": self.token_count,
            "metadata": self.metadata,
            "embedding": None,
        }
        if source_id:
            result["source_id"] = source_id
        return result


# =============================================================================
# IMPROVED PREPROCESSOR - Less Aggressive
# =============================================================================

class ImprovedPreprocessor:
    """
    Light preprocessing that preserves document structure.
    Only removes obvious noise, keeps everything else.
    """
    
    # Only remove truly useless patterns
    NOISE_PATTERNS = [
        r"^Page\s+\d+\s*of\s+\d+\s*$",           # "Page 5 of 10"
        r"^-\s*\d+\s*-$",                         # "- 5 -"
        r"^\d+\s*$",                              # Standalone page numbers
        r"^©\s*\d{4}.*All Rights Reserved.*$",   # Full copyright lines
        r"(?i)^this page (is )?intentionally (left )?blank\s*$",
    ]
    
    def __init__(self):
        self.noise_regex = [re.compile(p, re.MULTILINE | re.IGNORECASE) for p in self.NOISE_PATTERNS]
    
    def preprocess(self, text: str) -> str:
        """
        Light preprocessing:
        1. Normalize line endings and whitespace
        2. Remove only obvious noise (page numbers, blank page notices)
        3. Merge wrapped lines
        4. Keep everything else intact
        """
        # Normalize line endings
        text = re.sub(r'\r\n', '\n', text)
        text = re.sub(r'\r', '\n', text)
        
        # Remove truly noisy lines
        lines = text.split("\n")
        cleaned_lines = []
        
        for line in lines:
            stripped = line.strip()
            
            # Keep empty lines for structure
            if not stripped:
                cleaned_lines.append("")
                continue
            
            # Check if it's noise
            is_noise = False
            for pattern in self.noise_regex:
                if pattern.match(stripped):
                    is_noise = True
                    break
            
            if not is_noise:
                cleaned_lines.append(line)
        
        text = "\n".join(cleaned_lines)
        
        # Normalize excessive whitespace
        text = re.sub(r'[ \t]+', ' ', text)  # Multiple spaces/tabs -> single space
        text = re.sub(r'\n{4,}', '\n\n\n', text)  # Max 3 newlines
        
        # Merge wrapped lines (line doesn't end with punctuation and next starts lowercase)
        text = self._merge_wrapped_lines(text)
        
        return text.strip()
    
    def _merge_wrapped_lines(self, text: str) -> str:
        """Merge lines that were wrapped in the PDF."""
        lines = text.split("\n")
        merged = []
        
        for i, line in enumerate(lines):
            stripped = line.strip()
            
            if not stripped:
                merged.append(line)
                continue
            
            # Check if should merge with previous
            if merged and merged[-1].strip():
                prev = merged[-1].strip()
                
                # Merge if:
                # - Previous doesn't end with sentence-ender
                # - Current starts with lowercase
                # - Current is not a heading/bullet
                if (prev and 
                    prev[-1] not in ".!?:;)" and 
                    stripped and 
                    stripped[0].islower() and
                    not stripped.startswith(('•', '-', '*', '■', '●', '►'))):
                    merged[-1] = merged[-1].rstrip() + " " + stripped
                    continue
            
            merged.append(line)
        
        return "\n".join(merged)


# =============================================================================
# IMPROVED HEADING DETECTION
# =============================================================================

class ImprovedHeadingDetector:
    """
    Better heading detection that catches more formats.
    """
    
    # Comprehensive heading patterns
    HEADING_PATTERNS = [
        r'^#{1,6}\s+.+',                              # Markdown: # Heading
        r'^[A-Z][A-Z\s\-\d]{2,60}$',                  # ALL CAPS (allow numbers)
        r'^\d+\.[\d.]*\s+[A-Z].{0,80}$',              # Numbered: 1.2 Safety
        r'^(?:Chapter|Section|Part|Step)\s+\d+',      # Chapter/Section markers
        r'^[■●▶►→•]\s*.{3,60}$',                      # Bullet headings
        r'^(?:WARNING|CAUTION|NOTE|IMPORTANT|TIP)\s*[:\-]?', # Safety headings
        r'^\[.{2,40}\]$',                             # Bracketed: [MAINTENANCE]
        r'^.{3,50}:\s*$',                             # Ends with colon alone
        r'^(?:EXPERIENCE|EDUCATION|SKILLS|PROJECTS|TECHNICAL SKILLS)\s*$',  # Resume sections
        r'^[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,5}\s*$',   # Title Case (2-6 words)
    ]
    
    def __init__(self):
        self._patterns = [re.compile(p, re.MULTILINE) for p in self.HEADING_PATTERNS]
    
    def is_heading(self, line: str, context_lines: List[str] = None) -> bool:
        """Check if a line is a heading."""
        line = line.strip()
        
        if not line or len(line) > 100:
            return False
        
        # Skip lines that look like content (have periods in middle, long sentences)
        if '. ' in line and len(line) > 50:
            return False
        
        # Check against patterns
        for pattern in self._patterns:
            if pattern.match(line):
                return True
        
        # Additional heuristic: Short ALL CAPS words (2+)
        if line.isupper() and len(line) >= 3 and len(line) <= 60:
            return True
        
        # Short line followed by longer content (contextual check)
        if context_lines and len(line) < 40 and line[0].isupper():
            # If it doesn't end with punctuation and next line is content
            if line[-1] not in '.!?,;:' and len(context_lines) > 0:
                next_line = context_lines[0].strip() if context_lines else ""
                if next_line and len(next_line) > len(line):
                    return True
        
        return False


# =============================================================================
# IMPROVED CHUNK CREATOR
# =============================================================================

class ImprovedChunkCreator:
    """
    Creates chunks with better structure preservation.
    """
    
    def __init__(self):
        self.heading_detector = ImprovedHeadingDetector()
    
    def create_candidates(self, text: str) -> List[ChunkCandidate]:
        """
        Create chunk candidates by:
        1. Splitting on headings
        2. Preserving bullet lists and numbered steps together
        3. Extracting images to metadata
        """
        # Extract images first
        text, image_urls = self._extract_images(text)
        
        # Split by headings
        sections = self._split_by_headings(text)
        
        # Convert to ChunkCandidates
        candidates = []
        for heading, content in sections:
            content = content.strip()
            
            # Skip empty sections
            if not content or len(content) < 5:
                continue
            
            # Include heading in content if exists
            if heading:
                full_content = f"{heading}\n\n{content}"
            else:
                full_content = content
            
            candidates.append(ChunkCandidate(
                heading=heading,
                content=full_content,
                image_urls=image_urls if not candidates else []  # Images go to first chunk
            ))
        
        return candidates
    
    def _extract_images(self, text: str) -> Tuple[str, List[str]]:
        """Extract image URLs to metadata, remove from text."""
        image_urls = []
        
        # Markdown images: ![alt](url)
        md_pattern = r"!\[[^\]]*\]\(([^)]+)\)"
        for match in re.finditer(md_pattern, text):
            url = match.group(1)
            if url.startswith("http"):
                image_urls.append(url)
        
        # Remove markdown images from text
        text = re.sub(md_pattern, "", text)
        
        # Remove broken image placeholders
        text = re.sub(r"\[UPLOAD_FAILED[^\]]*\]", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\[TABLE_PLACEHOLDER\]", "", text, flags=re.IGNORECASE)
        
        return text.strip(), list(set(image_urls))
    
    def _split_by_headings(self, text: str) -> List[Tuple[Optional[str], str]]:
        """Split text by detected headings."""
        lines = text.split("\n")
        sections = []
        current_heading = None
        current_content = []
        
        for i, line in enumerate(lines):
            stripped = line.strip()
            
            # Get context for heading detection
            remaining_lines = lines[i+1:i+3] if i+1 < len(lines) else []
            
            if stripped and self.heading_detector.is_heading(stripped, remaining_lines):
                # Save previous section
                if current_content or current_heading:
                    content = "\n".join(current_content).strip()
                    if content:
                        sections.append((current_heading, content))
                
                current_heading = stripped
                current_content = []
            else:
                current_content.append(line)
        
        # Don't forget the last section
        if current_content:
            content = "\n".join(current_content).strip()
            if content:
                sections.append((current_heading, content))
        
        # If no sections found, treat entire text as one section
        if not sections:
            sections = [(None, text)]
        
        return sections


# =============================================================================
# IMPROVED SIZE CONTROLLER
# =============================================================================

class ImprovedSizeController:
    """
    Controls chunk sizes with sentence-aware splitting.
    """
    
    def __init__(
        self, 
        min_tokens: int = 80, 
        max_tokens: int = 600, 
        target_tokens: int = 350,
        overlap_tokens: int = 40
    ):
        self.min_tokens = min_tokens
        self.max_tokens = max_tokens
        self.target_tokens = target_tokens
        self.overlap_tokens = overlap_tokens
    
    def control_size(self, candidates: List[ChunkCandidate]) -> List[ChunkCandidate]:
        """Apply size control with sentence-aware splitting."""
        # First pass: split oversized
        sized = []
        for candidate in candidates:
            tokens = count_tokens(candidate.content)
            
            if tokens > self.max_tokens:
                sub_chunks = self._split_chunk_by_sentences(candidate)
                sized.extend(sub_chunks)
            else:
                sized.append(candidate)
        
        # Second pass: merge undersized
        merged = self._merge_small_chunks(sized)
        
        return merged
    
    def _split_chunk_by_sentences(self, candidate: ChunkCandidate) -> List[ChunkCandidate]:
        """Split chunk by sentences, not arbitrary token boundaries."""
        content = candidate.content
        heading = candidate.heading
        
        # Split into sentences (preserve bullet points)
        sentences = self._split_into_sentences(content)
        
        chunks = []
        current_content = []
        current_tokens = 0
        
        for sentence in sentences:
            sentence_tokens = count_tokens(sentence)
            
            # If adding this sentence exceeds max, save current and start new
            if current_tokens + sentence_tokens > self.target_tokens and current_content:
                chunk_text = "\n".join(current_content)
                chunks.append(ChunkCandidate(
                    heading=heading if not chunks else f"{heading} (continued)" if heading else None,
                    content=chunk_text,
                    image_urls=candidate.image_urls if not chunks else []
                ))
                
                # Start new chunk with overlap from previous
                overlap = current_content[-2:] if len(current_content) >= 2 else current_content[-1:]
                current_content = overlap + [sentence]
                current_tokens = sum(count_tokens(s) for s in current_content)
            else:
                current_content.append(sentence)
                current_tokens += sentence_tokens
        
        # Save last chunk
        if current_content:
            chunk_text = "\n".join(current_content)
            chunks.append(ChunkCandidate(
                heading=heading if not chunks else f"{heading} (continued)" if heading else None,
                content=chunk_text,
                image_urls=candidate.image_urls if not chunks else []
            ))
        
        return chunks if chunks else [candidate]
    
    def _split_into_sentences(self, text: str) -> List[str]:
        """Split text into sentences, preserving bullet points and lists."""
        # First, split by double newlines (paragraphs)
        paragraphs = text.split("\n\n")
        
        sentences = []
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            
            # Check if it's a list (bullets or numbers)
            lines = para.split("\n")
            if any(line.strip().startswith(('•', '-', '*', '■', '●', '►', '1.', '2.', '3.')) for line in lines):
                # Keep list items together but separate
                for line in lines:
                    if line.strip():
                        sentences.append(line.strip())
            else:
                # Split by sentence boundaries
                para_sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])', para)
                sentences.extend([s.strip() for s in para_sentences if s.strip()])
        
        return sentences
    
    def _merge_small_chunks(self, candidates: List[ChunkCandidate]) -> List[ChunkCandidate]:
        """Merge chunks that are too small."""
        if not candidates:
            return candidates
        
        merged = []
        for candidate in candidates:
            tokens = count_tokens(candidate.content)
            
            if tokens < self.min_tokens and merged:
                # Try to merge with previous chunk
                prev = merged[-1]
                combined_tokens = count_tokens(prev.content) + tokens
                
                if combined_tokens <= self.max_tokens:
                    # Merge with previous
                    merged_content = prev.content + "\n\n" + candidate.content
                    merged[-1] = ChunkCandidate(
                        heading=prev.heading,
                        content=merged_content,
                        image_urls=list(set(prev.image_urls + candidate.image_urls))
                    )
                    continue
            
            merged.append(candidate)
        
        return merged


# =============================================================================
# IMPROVED CHUNK BUILDER
# =============================================================================

class ImprovedChunkBuilder:
    """Builds final Chunk objects with proper metadata."""
    
    def build_chunks(self, candidates: List[ChunkCandidate]) -> List[Chunk]:
        """Convert candidates to final Chunk objects."""
        chunks = []
        
        for i, candidate in enumerate(candidates):
            token_count = count_tokens(candidate.content)
            
            # Determine content type
            content_type = self._classify_content(candidate.content)
            
            metadata = {
                "image_urls": candidate.image_urls,
                "content_type": content_type,
                "word_count": len(candidate.content.split()),
                "char_count": len(candidate.content),
                "chunker_version": "v2_improved",
            }
            
            chunk = Chunk(
                chunk_index=i,
                content=candidate.content,
                heading=candidate.heading,
                token_count=token_count,
                metadata=metadata
            )
            chunks.append(chunk)
        
        return chunks
    
    def _classify_content(self, content: str) -> str:
        """Simple content type classification."""
        content_lower = content.lower()
        
        # Check for table-like structure
        if content.count('|') > 5 or content.count('\t') > 5:
            return "table"
        
        # Check for list/reference
        lines = content.split('\n')
        bullet_lines = sum(1 for l in lines if l.strip().startswith(('•', '-', '*', '■', '●')))
        if bullet_lines > len(lines) * 0.5:
            return "list"
        
        # Check for specs/reference (lots of numbers)
        digit_ratio = sum(1 for c in content if c.isdigit()) / max(len(content), 1)
        if digit_ratio > 0.3:
            return "reference"
        
        # Default to narrative
        return "narrative"


# =============================================================================
# MAIN PIPELINE
# =============================================================================

class ImprovedChunkingPipeline:
    """
    Improved chunking pipeline for technical manuals.
    
    Key improvements:
    1. Less aggressive preprocessing
    2. Better heading detection
    3. Sentence-aware splitting
    4. Preserves document structure
    """
    
    def __init__(
        self,
        min_tokens: int = 80,
        max_tokens: int = 600,
        target_tokens: int = 350,
        overlap_tokens: int = 40
    ):
        self.preprocessor = ImprovedPreprocessor()
        self.chunk_creator = ImprovedChunkCreator()
        self.size_controller = ImprovedSizeController(
            min_tokens=min_tokens,
            max_tokens=max_tokens,
            target_tokens=target_tokens,
            overlap_tokens=overlap_tokens
        )
        self.chunk_builder = ImprovedChunkBuilder()
    
    def process(self, text: str, source_id: str = None) -> List[Chunk]:
        """
        Process text through the improved pipeline.
        
        Args:
            text: Raw text from PDF extraction
            source_id: UUID of knowledge source (optional)
            
        Returns:
            List of Chunk objects ready for storage
        """
        logger.info(f"Starting improved chunking pipeline, input length: {len(text)}")
        
        # Phase 1: Light preprocessing
        cleaned = self.preprocessor.preprocess(text)
        logger.debug(f"After preprocessing: {len(cleaned)} chars")
        
        # Phase 2: Create chunk candidates
        candidates = self.chunk_creator.create_candidates(cleaned)
        logger.debug(f"Created {len(candidates)} initial candidates")
        
        # Phase 3: Size control
        sized_candidates = self.size_controller.control_size(candidates)
        logger.debug(f"After size control: {len(sized_candidates)} candidates")
        
        # Phase 4: Build final chunks
        chunks = self.chunk_builder.build_chunks(sized_candidates)
        logger.info(f"Created {len(chunks)} final chunks")
        
        return chunks
    
    def process_file(self, input_path: str, output_path: str, source_id: str = None) -> dict:
        """Process a file and save results."""
        with open(input_path, "r", encoding="utf-8") as f:
            text = f.read()
        
        chunks = self.process(text, source_id)
        
        # Calculate stats
        total_chars = sum(len(c.content) for c in chunks)
        total_words = sum(c.metadata.get("word_count", 0) for c in chunks)
        total_tokens = sum(c.token_count for c in chunks)
        
        output = {
            "metadata": {
                "total_chunks": len(chunks),
                "total_characters": total_chars,
                "total_words": total_words,
                "total_tokens": total_tokens,
                "source_id": source_id,
                "chunker_version": "v2_improved",
            },
            "chunks": [c.to_dict(source_id) for c in chunks]
        }
        
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        
        return output["metadata"]


# Convenience function for backward compatibility
def chunk_manual(text: str, **kwargs) -> List[Dict[str, Any]]:
    """Chunk a technical manual document."""
    pipeline = ImprovedChunkingPipeline(**kwargs)
    chunks = pipeline.process(text)
    return [c.to_dict() for c in chunks]


# =============================================================================
# CLI
# =============================================================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Improved PDF/Manual Chunking Pipeline"
    )
    parser.add_argument("--input", "-i", required=True, help="Input markdown file path")
    parser.add_argument("--output", "-o", required=True, help="Output JSON file path")
    parser.add_argument("--source-id", help="UUID of knowledge source")
    parser.add_argument("--min-tokens", type=int, default=80, help="Minimum tokens per chunk")
    parser.add_argument("--max-tokens", type=int, default=600, help="Maximum tokens per chunk")
    parser.add_argument("--target-tokens", type=int, default=350, help="Target tokens per chunk")
    
    args = parser.parse_args()
    
    pipeline = ImprovedChunkingPipeline(
        min_tokens=args.min_tokens,
        max_tokens=args.max_tokens,
        target_tokens=args.target_tokens
    )
    
    stats = pipeline.process_file(args.input, args.output, args.source_id)
    
    print(f"✓ Saved {stats['total_chunks']} chunks to {args.output}")
    print(f"\n📊 Chunking Summary:")
    print(f"  Total chunks: {stats['total_chunks']}")
    print(f"  Total tokens: {stats['total_tokens']}")
    print(f"  Total words: {stats['total_words']}")
