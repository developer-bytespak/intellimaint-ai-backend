**Finalized Chunking Strategy**

This document captures the finalized canonical chunking strategy used by the project and the standalone implementation in `final_chunker.py`.

**Purpose**:
- Produce embedding-ready chunks for both iFixit guide markdown and PDF-extracted markdown.
- Keep chunk sizes deterministic, heading-aware, and robust to noisy PDF extraction artifacts (TOCs, image/table markers, broken lines).

**High-level approach**
- Normalize PDF/markdown input to remove obvious TOC noise, join wrapped lines into paragraphs, and attach leading image/table markers to the next paragraph.
- Split content by Markdown headings (heading-aware). Pre-heading text becomes its own section (heading=None).
- Within each section, perform sentence/section-level logic:
  - If a section is small (<= `chunk_size_max`): keep as-is.
  - If oversized: slice deterministically by token windows using the tokenizer (token-id slicing) with a controlled overlap.
- Merge very small sections into neighbors using heuristics that prefer merging into the previous section when the combined token count does not exceed `chunk_size_max`.
- Final enforcement pass: after merges, re-slice any chunk that still exceeds `chunk_size_max` using token-id windows (guarantees hard cap). If tokenizer not available or encoding fails, fall back to word-based slicing.

**Key behavioral guarantees**
- No final chunk will exceed `chunk_size_max` after the final enforcement pass (token-based slicing is used where possible).
- Small/marker-only fragments are attached to neighbors when safe to avoid tiny standalone chunks.
- Headings are preserved on the first chunk they belong to; subsequent pieces created by slicing set `heading=None` (so heading alignment is preserved without duplication).

**Tuned defaults**
- `chunk_target`: 300 tokens (preferred/target chunk size)
- `chunk_size_max`: 450 tokens (hard cap)
- `chunk_size_min`: 180 tokens (preferred minimum before merging)
- `chunk_overlap`: 50 tokens (overlap between adjacent slices)

These defaults are configurable when constructing the chunker.

**Token counting modes**
- Exact mode (default): uses `tiktoken`'s `cl100k_base` encoding to count tokens (authoritative; set `FAST_TOKEN_APPROX=0`).
- Fast iteration mode: set environment `FAST_TOKEN_APPROX=1` to use a cheap `len(text)//4` approximation for token counts. This is helpful for fast iteration but boundaries will differ from exact mode — always validate final outputs using exact mode.

**Implementation files**
- `final_chunker.py` — standalone canonical chunker implementing the approach above (CLI included). Keep this as canonical.
- `run_one_file_chunking.py` — single-file harness useful for quick local checks (optional; may be adapted to call `final_chunker.py`).
- `run_chunking_experiments.py` — batch runner used for experiment reporting; optional to keep for audit/history.
- `compare_chunking_approaches.py` — historical development file (archive if you finalize). It can be left in VCS history.

**CLI usage**
From `scripts/chunking`:
```
$env:FAST_TOKEN_APPROX = "0"
python final_chunker.py --file ./pdf_samples/sample2.md --out ./results-final-pdf/sample2_final.json
```

**Outputs**
- The CLI writes a JSON with top-level `file` and `chunks` array. Each chunk contains:
  - `chunk_index` (int)
  - `heading` (string|null)
  - `content` (string)
  - `token_count`, `char_count`, `word_count`

**Troubleshooting & tweaks**
- If you observe `token_stats.max > chunk_size_max` after an exact run:
  - Ensure exact mode (`FAST_TOKEN_APPROX=0`) was used.
  - Confirm `tiktoken` is installed and available.
  - The final-enforcement pass is intended to prevent this. If it doesn't, share the failing JSON and the script can be adjusted to increase the safety margin (reduce `window` by a few tokens) or alter merge heuristics.
- If you see many very small chunks (`min < ~40`):
  - Check PDF normalization: TOC or marker fragments may remain; tune `normalize_pdf_markdown` to remove or attach them.
  - You can lower `chunk_size_min` or change merge logic to be more aggressive.

**Recommended safety workflow before deleting old files**
1. Create a branch (example: `finalize-chunker`).
2. Run the full exact batch using `final_chunker.py` and compare outputs with prior experiment results.
3. If outputs are satisfactory, move historical/experimental scripts into an `archive/` folder rather than permanently deleting them immediately.
4. Commit the branch, test downstream embedding/ingestion pipelines on a subset of the chunks, then merge.

**Notes**
- The standalone `final_chunker.py` intentionally contains minimal external dependencies. It uses `tiktoken` when available but falls back to word-based heuristics if not. For best accuracy and final validation, install `tiktoken`.
- The approach focuses on deterministic, reproducible slicing and conservative merging to produce reliable embedding inputs.

If you want, I can create a small shim to keep old import points working (a thin `compare_chunking_approaches.py` that delegates to `final_chunker.CustomChunking`) so other scripts won't break when you remove the previous implementation.
