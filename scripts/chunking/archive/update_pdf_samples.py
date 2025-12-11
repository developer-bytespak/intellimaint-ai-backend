#!/usr/bin/env python3
"""
Update PDF sample markdowns by extracting PDFs using the existing DocumentService.

Usage (PowerShell):
    python .\scripts\chunking\update_pdf_samples.py
    python .\scripts\chunking\update_pdf_samples.py --pdf-dir .\scripts\chunking\pdf_samples\docs --out-dir .\scripts\chunking\pdf_samples\samples --upload

Notes:
- This script imports DocumentService from the repo. It sets sys.path so you can run it from the repo root or the scripts folder.
- If --upload is passed, the script will call DocumentService.upload_images_to_supabase (requires your DB/env).
"""
from __future__ import annotations
import argparse
import os
import shutil
import uuid
from pathlib import Path
import sys

# Ensure repo root is on sys.path so we can import services.* modules
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

# Import DocumentService from existing code
try:
    from services.app.services.doc_extract_service import DocumentService
except Exception as e:
    print("ERROR: Could not import DocumentService. Make sure you run this from the repo, and dependencies are installed.")
    raise

def extract_one(pdf_path: Path, out_dir: Path, upload: bool):
    out_dir.mkdir(parents=True, exist_ok=True)

    images_dir = out_dir / f"images_{pdf_path.stem}_{uuid.uuid4().hex[:8]}"
    images_dir.mkdir(parents=True, exist_ok=True)

    print(f"Extracting: {pdf_path.name} -> md: {out_dir}/{pdf_path.stem}.md, images: {images_dir.name}")

    full_text, image_files = DocumentService.extract_text_with_image_markers(str(pdf_path), str(images_dir))

    # Optionally upload images and replace markers with URLs
    image_infos = []
    if upload and image_files:
        try:
            image_infos = DocumentService.upload_images_to_supabase(image_files)
            # replace placeholders with urls in the text for convenience
            full_text = DocumentService.replace_placeholders_with_urls(full_text, image_infos)
        except Exception as e:
            print(f"Warning: image upload failed for {pdf_path.name}: {e}")
            # proceed with local image files

    # Save markdown
    md_path = out_dir / f"{pdf_path.stem}.md"
    header = "# Extracted PDF Content\n\n"
    md_path.write_text(header + full_text, encoding="utf-8")

    # Save an assets JSON (local image paths and uploaded URLs if any)
    assets = []
    for idx, p in enumerate(image_files, start=1):
        info = {"image_number": idx, "local_path": str(p)}
        # if upload produced info for this image number, attach url/filename
        matching = next((x for x in image_infos if int(x.get("image_number", 0)) == idx), None)
        if matching:
            info.update({"url": matching.get("url"), "filename": matching.get("filename")})
        assets.append(info)

    assets_path = out_dir / f"{pdf_path.stem}_assets.json"
    try:
        import json
        assets_path.write_text(json.dumps(assets, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass

    print(f"Saved: {md_path}  (images: {len(image_files)})")
    return md_path, images_dir, assets_path

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf-dir", type=str, default=str(Path(__file__).resolve().parent / "pdf_samples" / "docs"),
                        help="Directory containing source PDFs")
    parser.add_argument("--out-dir", type=str, default=str(Path(__file__).resolve().parent / "pdf_samples" / "samples"),
                        help="Directory where extracted md and images will be stored")
    parser.add_argument("--upload", action="store_true", help="Upload extracted images to Supabase (requires DB env)")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing md files")
    args = parser.parse_args()

    pdf_dir = Path(args.pdf_dir)
    out_root = Path(args.out_dir)
    out_root.mkdir(parents=True, exist_ok=True)

    pdfs = sorted([p for p in pdf_dir.glob("*.pdf")])
    if not pdfs:
        print(f"No PDFs found in {pdf_dir}.")
        return

    for p in pdfs:
        md_path = out_root / f"{p.stem}.md"
        if md_path.exists() and not args.overwrite:
            print(f"Skipping existing {md_path.name} (use --overwrite to replace)")
            continue
        try:
            extract_one(p, out_root, args.upload)
        except Exception as e:
            print(f"ERROR extracting {p.name}: {e}")

if __name__ == "__main__":
    main()