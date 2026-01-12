import os
import re
import uuid
import json
import sys
import logging
from typing import List, Optional, Tuple, Dict, Any

import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
from pathlib import Path

logger = logging.getLogger(__name__)

# Add the chunking scripts to path for importing the universal chunker
# Path: /app/app/services/chunker.py -> /app/scripts/chunking (3 parents up)
SCRIPTS_CHUNKING_PATH = Path(__file__).parent.parent.parent / "scripts" / "chunking"
if str(SCRIPTS_CHUNKING_PATH) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_CHUNKING_PATH))

try:
    from pdf_universal_chunker import UniversalChunkingPipeline
    HAS_UNIVERSAL_CHUNKER = True
except ImportError as e:
    logger.warning(f"Could not import UniversalChunkingPipeline: {e}")
    HAS_UNIVERSAL_CHUNKER = False

try:
    import importlib.util
    _tikt_spec = importlib.util.find_spec("tiktoken")
    if _tikt_spec is not None:
        import tiktoken  # type: ignore
        _HAS_TIKTOKEN = True
    else:
        tiktoken = None  # type: ignore
        _HAS_TIKTOKEN = False
except Exception:
    tiktoken = None  # type: ignore
    _HAS_TIKTOKEN = False

FAST_TOKEN_APPROX = False


class TokenCounter:
    def __init__(self, enc_name: str = "cl100k_base"):
        self._cache: Dict[str, int] = {}
        self.enc_name = enc_name
        if _HAS_TIKTOKEN:
            try:
                self.tokenizer = tiktoken.get_encoding(enc_name)
            except Exception:
                self.tokenizer = None
        else:
            self.tokenizer = None

    def count(self, text: str) -> int:
        if not text:
            return 0
        if FAST_TOKEN_APPROX:
            return max(0, len(text) // 4)
        key = text if len(text) <= 2000 else text[:2000]
        if key in self._cache:
            return self._cache[key]
        if self.tokenizer is not None:
            try:
                v = len(self.tokenizer.encode(text))
            except Exception:
                v = len(text.split())
        else:
            v = len(text.split())
        self._cache[key] = v
        return v

    def encode(self, text: str) -> List[int]:
        if self.tokenizer is None:
            return [len(w) for w in text.split()]
        return self.tokenizer.encode(text)

    def decode(self, tids: List[int]) -> str:
        if self.tokenizer is None:
            return " ".join(str(t) for t in tids)
        return self.tokenizer.decode(tids)



# --- Inline iFixit-style chunking functions (from scripts/chunking/test_script.py)


def is_noise_line(line: str) -> bool:
    s = line.strip()
    if not s:
        return False
    if s.startswith("![") and "](" in s:
        return True
    if s.startswith("<!--") and s.endswith("-->"):
        return True
    return False


def normalize_section_body(lines: List[str]) -> str:
    out: List[str] = []
    for line in lines:
        if is_noise_line(line):
            continue
        out.append(line.rstrip())

    text = "\n".join(out)
    text = re.sub(r"\[[^|\]]+\|[^|\]]*\|([^|\]]+)\]", r"\1", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def parse_guide_sections(md_text: str) -> Tuple[str, str, List[Dict[str, Any]]]:
    lines = md_text.splitlines()

    title: str | None = None
    intro_lines: List[str] = []
    sections: List[Dict[str, Any]] = []
    current_section: Dict[str, Any] | None = None
    step_counter = 0

    for line in lines:
        if line.startswith("# "):
            if title is None:
                title = line[2:].strip()
            else:
                if current_section is None:
                    intro_lines.append(line)
                else:
                    current_section["lines"].append(line)

        elif line.startswith("## "):
            if current_section is not None:
                sections.append(current_section)

            heading_text = line[3:].strip()
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
            if title is None:
                intro_lines.append(line)
            elif current_section is None:
                intro_lines.append(line)
            else:
                current_section["lines"].append(line)

    if current_section is not None:
        sections.append(current_section)

    if title is None:
        title = "Untitled Guide"

    intro_text = "\n".join(intro_lines).strip()
    return title, intro_text, sections


def derive_heading_from_body(body: str) -> str | None:
    if not body:
        return None
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(">"):
            continue
        stripped = re.sub(r"^[-*•]\s*", "", stripped)
        if stripped:
            return stripped[:80]
    return None


def chunk_sections(
    title: str,
    intro_text: str,
    sections: List[Dict[str, Any]],
    max_chars: int = 1200,
    max_steps: int = 5,
    step_overlap: int = 1,
) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
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

    for sec in sections:
        body = normalize_section_body(sec["lines"])
        if not body:
            continue
        heading = sec["heading"]
        heading_display = heading
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

    segments: List[List[Dict[str, Any]]] = []
    current_segment: List[Dict[str, Any]] = []
    current_char = 0
    current_steps = 0

    for item in items:
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

    chunks: List[Dict[str, Any]] = []
    chunk_index = 0

    for idx, seg in enumerate(segments):
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
            lines.append("")

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


def extract_images_by_step(md_text: str) -> Dict[int, List[Dict[str, Any]]]:
    images_by_step: Dict[int, List[Dict[str, Any]]] = {}
    current_step_index = 0

    lines = md_text.splitlines()

    for line in lines:
        stripped = line.strip()

        if stripped.startswith("## "):
            heading_text = stripped[3:].strip()
            m = re.match(r"(\d+)\.\s*(.*)", heading_text)
            if m:
                current_step_index = int(m.group(1))
            else:
                current_step_index += 1

        for m in re.finditer(r'!\[(.*?)\]\((.*?)\)', stripped):
            alt = m.group(1).strip()
            url = m.group(2).strip()
            if not url:
                continue
            if current_step_index <= 0:
                step_idx = 0
            else:
                step_idx = current_step_index

            lst = images_by_step.setdefault(step_idx, [])
            lst.append(
                {
                    "step_index": step_idx,
                    "url": url,
                    "alt": alt,
                    "order": len(lst),
                }
            )

        if stripped.startswith("<!--") and "http" in stripped:
            url_match = re.search(r"https?://[^\s>]+", stripped)
            if url_match:
                url = url_match.group(0)
                url = url.rstrip(".,]")
                if current_step_index <= 0:
                    step_idx = 0
                else:
                    step_idx = current_step_index
                lst = images_by_step.setdefault(step_idx, [])
                lst.append(
                    {
                        "step_index": step_idx,
                        "url": url,
                        "alt": "",
                        "order": len(lst),
                    }
                )

    return images_by_step


def process_source(source_id: str, dry_run: bool = False, overwrite: bool = False, max_retries: int = 1) -> Dict[str, Any]:
    """
    Process a knowledge source and create chunks with 15% overlap.
    
    Uses the universal PDF chunker with English-only filtering and overlap logic.
    
    Args:
        source_id: UUID of the knowledge source
        dry_run: If True, returns chunks without inserting to DB
        overwrite: If True, deletes existing chunks before inserting
        max_retries: Number of retries on failure (default 1)
    
    Returns:
        Dict with source_id and num_chunks (or full chunks if dry_run)
    """
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        raise ValueError("DATABASE_URL not set in environment")

    retry_count = 0
    last_error = None
    
    while retry_count <= max_retries:
        try:
            return _process_source_internal(source_id, dry_run, overwrite, dsn)
        except Exception as e:
            last_error = e
            retry_count += 1
            if retry_count <= max_retries:
                logger.warning(f"Chunking failed for {source_id}, retrying ({retry_count}/{max_retries}): {e}")
            else:
                logger.error(f"Chunking failed for {source_id} after {max_retries} retries: {e}")
    
    raise last_error


def _process_source_internal(source_id: str, dry_run: bool, overwrite: bool, dsn: str) -> Dict[str, Any]:
    """Internal processing function (called by process_source with retry logic)."""
    
    # Connect to Neon/Postgres
    conn = psycopg2.connect(dsn, sslmode="require")
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT title, raw_content FROM knowledge_sources WHERE id = %s", (source_id,))
            row = cur.fetchone()
            if not row:
                raise ValueError(f"knowledge_source not found: {source_id}")
            raw = row.get("raw_content")
            title = row.get("title", "Untitled")
            if raw is None:
                raise ValueError("raw_content is empty")

        # Use the universal chunker with overlap (preferred) or fall back to iFixit-style
        if HAS_UNIVERSAL_CHUNKER:
            chunks = _process_with_universal_chunker(raw, source_id)
        else:
            logger.warning("Universal chunker not available, falling back to iFixit-style chunking")
            chunks = _process_with_ifixit_chunker(raw, source_id)

        if dry_run:
            return {"source_id": source_id, "num_chunks": len(chunks), "chunks": chunks}

        with conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT id FROM knowledge_chunks WHERE source_id = %s LIMIT 1", (source_id,))
                existing = cur.fetchone()
                if existing and not overwrite:
                    raise ValueError("chunks already exist for this source_id; set overwrite=true to replace")

                if overwrite:
                    cur.execute("DELETE FROM knowledge_chunks WHERE source_id = %s", (source_id,))

                values = []
                for c in chunks:
                    values.append((
                        str(uuid.uuid4()),
                        source_id,
                        c["chunk_index"],
                        c["content"],
                        c.get("heading"),
                        None,  # embedding
                        c.get("token_count"),
                        json.dumps(c.get("metadata", {"chunker_version": "v2"}))
                    ))

                insert_sql = (
                    "INSERT INTO knowledge_chunks"
                    " (id, source_id, chunk_index, content, heading, embedding, token_count, metadata)"
                    " VALUES %s"
                )
                if values:
                    execute_values(cur, insert_sql, values, template=None, page_size=100)

        logger.info(f"Successfully created {len(chunks)} chunks for source {source_id}")
        return {"source_id": source_id, "num_chunks": len(chunks)}

    finally:
        conn.close()


def _process_with_universal_chunker(raw_content: str, source_id: str) -> List[Dict[str, Any]]:
    """
    Process raw content using the universal PDF chunker.
    Includes English-only filtering and 15% overlap.
    """
    pipeline = UniversalChunkingPipeline()
    chunk_objects = pipeline.process(raw_content, source_id=source_id)
    
    chunks = []
    for chunk in chunk_objects:
        chunk_data = {
            "chunk_index": chunk.chunk_index,
            "heading": chunk.heading,
            "content": chunk.content,
            "token_count": chunk.token_count,
            "metadata": chunk.metadata,
        }
        chunks.append(chunk_data)
    
    return chunks


def _process_with_ifixit_chunker(raw_content: str, source_id: str) -> List[Dict[str, Any]]:
    """
    Fallback: Process using the iFixit-style chunker (legacy).
    """
    counter = TokenCounter()
    
    try:
        title, intro_text, sections = parse_guide_sections(raw_content)
        raw_chunks = chunk_sections(title, intro_text, sections)
    except Exception as e:
        raise ValueError(f"error while running chunker: {e}")

    # Map raw_chunks to expected schema
    images_by_step = extract_images_by_step(raw_content)

    chunks: List[Dict[str, Any]] = []
    for c in raw_chunks:
        content = c.get("content", "")
        step_indices = c.get("step_indices", [])
        headings = c.get("headings", [])
        heading = headings[0] if headings else None
        token_count = counter.count(content)

        # collect images belonging to this chunk's steps
        chunk_images: List[Dict[str, Any]] = []
        seen_keys = set()
        for step_idx in step_indices:
            for img in images_by_step.get(step_idx, []):
                key = (img.get("url"), img.get("step_index"), img.get("order"))
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                chunk_images.append(img)

        metadata = {
            "step_indices": step_indices,
            "images": chunk_images,
            "char_count": len(content),
            "word_count": len(content.split()),
            "chunker_version": "v1_ifixit",
        }

        chunks.append({
            "chunk_index": c.get("chunk_index", 0),
            "heading": heading,
            "content": content,
            "token_count": token_count,
            "metadata": metadata,
        })

    return chunks
