import os
import re
import uuid
import json
from typing import List, Optional, Tuple, Dict, Any

import psycopg2
from psycopg2.extras import RealDictCursor, execute_values

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

    def normalize_pdf_markdown(self, text: str) -> str:
        text = re.sub(r'(?mi)^\s*(table of contents|contents)\s*$', '', text)
        text = re.sub(r'(?m)^[-•*\d\.)\s]{1,20}$', '', text)
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
        normalized = re.sub(r'(?m)^(!\[.*\]\(.*\))\s*$', lambda m: m.group(1).rstrip() + '\n', normalized)
        return normalized

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

    def split_large_section(self, content: str, heading: Optional[str]) -> List[Tuple[Optional[str], str]]:
        if self.counter.count(content) <= self.chunk_size_max:
            return [(heading, content)]
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
                txt = ' '.join(str(x) for x in piece)
            pieces.append((heading if first else None, txt))
            first = False
        return pieces

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
            if prev_tokens < self.chunk_size_min or (prev_tokens + cur_tokens) <= self.chunk_size_max:
                merged[-1] = (prev_h, prev_c + "\n\n" + content)
            else:
                merged.append((heading, content))
        return merged

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


def process_source(source_id: str, dry_run: bool = False, overwrite: bool = False) -> Dict[str, Any]:
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        raise ValueError("DATABASE_URL not set in environment")

    # Connect to Neon/Postgres
    conn = psycopg2.connect(dsn, sslmode="require")
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT raw_content FROM knowledge_sources WHERE id = %s", (source_id,))
            row = cur.fetchone()
            if not row:
                raise ValueError(f"knowledge_source not found: {source_id}")
            raw = row.get("raw_content")
            if raw is None:
                raise ValueError("raw_content is empty")

        counter = TokenCounter()
        chunker = CustomChunking(counter)
        chunks = chunker.chunk_text(raw)

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
                        None,
                        c.get("token_count"),
                        json.dumps({"char_count": c.get("char_count"), "word_count": c.get("word_count"), "chunker_version": "v1"})
                    ))

                insert_sql = (
                    "INSERT INTO knowledge_chunks"
                    " (id, source_id, chunk_index, content, heading, embedding, token_count, metadata)"
                    " VALUES %s"
                )
                if values:
                    execute_values(cur, insert_sql, values, template=None, page_size=100)

        return {"source_id": source_id, "num_chunks": len(chunks)}

    finally:
        conn.close()
