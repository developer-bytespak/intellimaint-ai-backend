#!/usr/bin/env python3
# Quick single-file runner: uses CustomChunking only (no LangChain)
from pathlib import Path
import json
import os
import tiktoken
from compare_chunking_approaches import CustomChunking

# cached token helper (a simplified copy of the experiment script)
FAST_TOKEN_APPROX = os.getenv("FAST_TOKEN_APPROX", "0") == "1"
_TOKEN_CACHE = {}
def count_tokens_cached(tokenizer, text: str):
    if not text:
        return 0
    if FAST_TOKEN_APPROX:
        return max(1, len(text) // 4)
    key = text if len(text) <= 2000 else text[:2000] + f"...len{len(text)}"
    v = _TOKEN_CACHE.get(key)
    if v is not None:
        return v
    v = len(tokenizer.encode(text))
    _TOKEN_CACHE[key] = v
    return v

def bind_cached_counter(chunker, tokenizer):
    import types
    chunker.count_tokens = types.MethodType(lambda self, text, tok=tokenizer: count_tokens_cached(tok, text), chunker)

def run_one(md_path: str):
    tokenizer = tiktoken.get_encoding("cl100k_base")
    chunker = CustomChunking()
    bind_cached_counter(chunker, tokenizer)

    text = Path(md_path).read_text(encoding="utf-8")
    chunks = chunker.chunk_text(text)
    out = {
        "file": md_path,
        "num_chunks": len(chunks),
        "token_stats": {
            "min": min((c.token_count for c in chunks), default=0),
            "max": max((c.token_count for c in chunks), default=0),
            "avg": (sum(c.token_count for c in chunks) / len(chunks)) if chunks else 0
        },
        "chunks_with_headings": sum(1 for c in chunks if getattr(c, "heading", None)),
        "sample_previews": [
            {"index": c.chunk_index, "tokens": c.token_count, "heading": c.heading, "preview": c.content[:300].replace("\n"," ")}
            for c in chunks[:6]
        ]
    }
    print(json.dumps(out, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python run_one_file_chunking.py path/to/sample.md")
        sys.exit(1)
    run_one(sys.argv[1])