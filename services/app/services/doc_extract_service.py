# import os
# import re
# from typing import List, Dict, Tuple, Optional

# import fitz  # PyMuPDF
# import pdfplumber
# import pandas as pd

# from ..shared.database import get_db


# class DocumentService:

#     # ------------------------------------
#     # Better table detection
#     # ------------------------------------
#     @staticmethod
#     def is_table_text_block(block_text: str) -> bool:
#         """
#         Detect table-like text blocks to avoid duplication.
#         Detects patterns like:

#         ID
#         Name
#         Value
#         1
#         Alpha
#         123
#         """
#         lines = [l.strip() for l in block_text.splitlines() if l.strip()]

#         # Need at least 4 lines (minimum table structure)
#         if len(lines) < 4:
#             return False



#         # Check for common table header words
#         table_headers = ['id', 'name', 'value', 'column', 'row', 'data', 'item', 'no', 'number']
#         first_lines_lower = [l.lower() for l in lines[:5]]

#         header_match = sum(1 for h in table_headers for line in first_lines_lower if h in line)
#         if header_match >= 2:
#             # If we have table-like headers, check if body has numeric patterns
#             numeric_count = sum(1 for l in lines if any(c.isdigit() for c in l))
#             if numeric_count >= len(lines) * 0.3:  # 30% lines should have numbers
#                 return True

#         # Check if many lines are single words or very short (table cell characteristic)
#         single_word_count = sum(1 for l in lines if len(l.split()) == 1)
#         if single_word_count >= len(lines) * 0.6:  # 60% are single words
#             return True

#         # Check for alternating pattern: text, text, number, text, text, number
#         numeric_lines = [i for i, l in enumerate(lines) if l.replace('.', '').replace(',', '').isdigit()]
#         if len(numeric_lines) >= 2:
#             if len(lines) >= 6:
#                 every_third = all(i % 3 == 2 for i in numeric_lines[:min(3, len(numeric_lines))])
#                 if every_third:
#                     return True

#         return False

#     # ------------------------------------
#     # Extract text with improved table filtering
#     # ------------------------------------
    
#     @staticmethod
#     def extract_text_with_image_markers(
#         file_path: str, 
#         output_dir: str
#     ) -> Tuple[str, List[str]]:
#         """
#         Extract text in reading order, skip table-like blocks,
#         avoid duplicate text blocks, and save images with markers.
#         """

#         full_text = ""
#         image_files: List[str] = []
#         image_counter = 1

#         seen_blocks = set()      # Prevent duplicate text blocks
#         image_seen = {}          # Prevent duplicate image extraction

#         with fitz.open(file_path) as pdf:
#             total_pages = len(pdf)
            
#             for page_index, page in enumerate(pdf):
#                 blocks = page.get_text("dict")["blocks"]
#                 page_num = page_index + 1

#                 page_output_lines = [f"# Page {page_num}", ""]

#                 # -------------------------
#                 # TEXT BLOCKS
#                 # -------------------------
#                 for b in blocks:
#                     if "lines" not in b:
#                         continue

#                     block_line_texts = []
#                     block_max_font = 0.0

#                     for line in b["lines"]:
#                         line_text_parts = []
#                         line_max_font = 0.0

#                         for span in line["spans"]:
#                             txt = span.get("text", "").strip()
#                             if not txt:
#                                 continue
#                             font_size = span.get("size", 0.0)
#                             if font_size > line_max_font:
#                                 line_max_font = font_size
#                             line_text_parts.append(txt)

#                         if line_text_parts:
#                             joined_line_text = " ".join(line_text_parts).strip()
#                             if joined_line_text:
#                                 block_line_texts.append(joined_line_text)
#                                 if line_max_font > block_max_font:
#                                     block_max_font = line_max_font

#                     if not block_line_texts:
#                         continue

#                     block_text = "\n".join(block_line_texts)

#                     # Skip duplicate text blocks
#                     if block_text in seen_blocks:
#                         continue
#                     seen_blocks.add(block_text)

#                     # Table detection
#                     if DocumentService.is_table_text_block(block_text):
#                         page_output_lines.append("[TABLE_PLACEHOLDER]")
#                         page_output_lines.append("")
#                         continue

#                     # Heading detection
#                     for line_text in block_line_texts:
#                         if block_max_font >= 18:
#                             page_output_lines.append(f"# {line_text}")
#                             page_output_lines.append("")
#                         elif 14 <= block_max_font < 18:
#                             page_output_lines.append(f"## {line_text}")
#                             page_output_lines.append("")
#                         elif 12 <= block_max_font < 14:
#                             page_output_lines.append(f"### {line_text}")
#                             page_output_lines.append("")
#                         else:
#                             page_output_lines.append(line_text)

#                     page_output_lines.append("")

#                 # -------------------------
#                 # IMAGE EXTRACTION
#                 # -------------------------
#                 image_list = page.get_images(full=True)

#                 for img in image_list:
#                     xref = img[0]

#                     # If image already extracted → reuse same number
#                     if xref in image_seen:
#                         page_output_lines.append(f"[IMAGE:{image_seen[xref]}]")
#                         page_output_lines.append("")
#                         continue

#                     # Extract new image
#                     try:
#                         pix = fitz.Pixmap(pdf, xref)
#                     except Exception:
#                         continue

#                     try:
#                         # Safe handling when pix.colorspace is None
#                         if pix.colorspace is None:
#                             try:
#                                 pix = fitz.Pixmap(fitz.csRGB, pix)
#                             except:
#                                 continue  # skip images we can't convert

#                         # Convert CMYK, Indexed, Alpha → RGB
#                         elif pix.colorspace and (pix.colorspace.n not in (1, 3) or pix.alpha):
#                             try:
#                                 pix = pix.copy(colorspace=fitz.csRGB, alpha=False)
#                             except:
#                                 continue

#                         # Save image
#                         img_path = os.path.join(output_dir, f"image_{image_counter}.png")
#                         pix.save(img_path)

#                         image_files.append(img_path)
#                         image_seen[xref] = image_counter

#                         # Use compact marker form
#                         page_output_lines.append(f"[IMAGE:{image_counter}]")
#                         page_output_lines.append("")

#                         image_counter += 1

#                     finally:
#                         pix = None

#                 # -------------------------
#                 # NORMALIZE PAGE OUTPUT
#                 # -------------------------
#                 full_text += "\n".join(page_output_lines) + "\n\n"

#         return full_text, image_files



#     # ------------------------------------
#     # Extract Tables
#     # ------------------------------------
#     @staticmethod
#     def extract_and_format_tables_from_pdf(
#         file_path: str
#     ) -> List[Dict]:
#         """Extract tables using pdfplumber."""
#         output: List[Dict] = []

#         with pdfplumber.open(file_path) as pdf:
#             total_pages = len(pdf.pages)
            
#             for page_index, page in enumerate(pdf.pages, start=1):
#                 tables = page.extract_tables()

#                 for tbl_index, table in enumerate(tables, start=1):
#                     if not table or len(table) < 2:
#                         continue

#                     df = pd.DataFrame(table[1:], columns=table[0])
#                     df = df.dropna(how="all")

#                     if df.empty:
#                         continue

#                     output.append({
#                         "page": page_index,
#                         "table_index": tbl_index,
#                         "columns": list(df.columns),
#                         "rows": df.values.tolist(),
#                     })

#         return output

#     # ------------------------------------
#     # Upload images
#     # ------------------------------------
#     @staticmethod
#     def upload_images_to_supabase(
#         image_paths: List[str],
#         bucket_name: str = "pics"
#     ) -> List[Dict[str, str]]:
#         """Upload images to Supabase storage."""
#         db = get_db()
#         uploaded: List[Dict[str, str]] = []
#         total_images = len(image_paths)

#         for idx, img_path in enumerate(image_paths, start=1):
#             file_name = os.path.basename(img_path)

#             try:
#                 with open(img_path, "rb") as f:
#                     data = f.read()

#                 unique_name = f"{os.path.splitext(file_name)[0]}_{os.urandom(4).hex()}.png"

#                 db.storage.from_(bucket_name).upload(
#                     path=unique_name,
#                     file=data,
#                     file_options={"content-type": "image/png"},
#                 )

#                 url = db.storage.from_(bucket_name).get_public_url(unique_name)

#                 uploaded.append({
#                     "image_number": idx,
#                     "url": url,
#                     "filename": unique_name,
#                 })
#             except Exception as e:
#                 uploaded.append({
#                     "image_number": idx,
#                     "url": f"[UPLOAD_FAILED_{idx}]",
#                     "filename": file_name,
#                     "error": str(e),
#                 })

#         return uploaded

#     # ------------------------------------
#     # Replace image markers
#     # ------------------------------------
#     @staticmethod
#     def replace_placeholders_with_urls(text: str, images: List[Dict]) -> str:
#         """
#         Replace IMAGE:n and [IMAGE:n] markers with a readable block including URL.
#         Accepts both formats to remain backward compatible.
#         """
#         # Replace both 'IMAGE:3' and '[IMAGE:3]' tokens
#         for img in images:
#             # accept either format when searching
#             marker_plain = f"IMAGE:{img['image_number']}"
#             marker_bracket = f"[IMAGE:{img['image_number']}]"
#             replacement = f"\nimage: {img['image_number']}\nurl: {img['url']}\n"
#             # Prefer replacing bracketed first, then plain
#             text = text.replace(marker_bracket, replacement)
#             text = text.replace(marker_plain, replacement)
#         return text

#     # ------------------------------------
#     # Merge text and tables
#     # ------------------------------------
#     @staticmethod
#     def create_unified_content(text: str, tables: List[Dict]) -> str:
#         """Build final output with tables at correct positions."""
#         final: List[str] = ["# Extracted PDF Content", ""]

#         pages = text.split("# Page ")

#         for chunk in pages:
#             chunk = chunk.strip()
#             if not chunk:
#                 continue

#             lines = chunk.splitlines()
#             page_header = lines[0].strip()
#             body_lines = lines[1:]

#             final.append(f"# Page {page_header}")
#             final.append("")

#             # Get tables for this page
#             try:
#                 page_num = int(page_header)
#                 page_tables = [t for t in tables if t["page"] == page_num]
#             except ValueError:
#                 page_tables = []

#             # Insert tables at placeholders
#             table_inserted_count = 0

#             for line in body_lines:
#                 if line.strip() == "[TABLE_PLACEHOLDER]" and table_inserted_count < len(page_tables):
#                     t = page_tables[table_inserted_count]
#                     final.append("")
#                     final.append(f"table: Table {t['table_index']}")
#                     final.append(f"columns: {', '.join(str(c) for c in t['columns'])}")
#                     final.append("rows:")
#                     for row in t["rows"]:
#                         final.append(", ".join(str(x) for x in row))
#                     final.append("")
#                     table_inserted_count += 1
#                 else:
#                     final.append(line)

#             # Add remaining tables at end of page
#             for t in page_tables[table_inserted_count:]:
#                 final.append("")
#                 final.append(f"table: Table {t['table_index']}")
#                 final.append(f"columns: {', '.join(str(c) for c in t['columns'])}")
#                 final.append("rows:")
#                 for row in t["rows"]:
#                     clean_row = [str(x).strip() if x else "" for x in row]
#                     final.append(", ".join(clean_row))

#                 final.append("")

#             final.append("")

#         return "\n".join(final)

#     # ------------------------------------
#     # Delete images utility
#     # ------------------------------------
#     @staticmethod
#     def delete_images_from_supabase(
#         image_urls: List[str],
#         bucket_name: str = "pics"
#     ) -> Dict[str, any]:
#         """Delete images from Supabase storage."""
#         db = get_db()
#         deleted = []
#         failed = []

#         for url in image_urls:
#             try:
#                 filename = url.split("/")[-1]
#                 db.storage.from_(bucket_name).remove([filename])
#                 deleted.append(filename)
#             except Exception as e:
#                 failed.append({"url": url, "error": str(e)})

#         return {
#             "deleted_count": len(deleted),
#             "failed_count": len(failed),
#             "deleted": deleted,
#             "failed": failed,
#         }

#     # ------------------------------------
#     # Normalize page lines
#     # ------------------------------------
#     @staticmethod
#     def normalize_page_lines(lines: List[str]) -> List[str]:
#         """
#         Normalize page output lines:
#         - Remove '# Page N' lines
#         - Collapse sequences of short lines into a single paragraph
#         - Preserve heading lines (starting with '#')
#         - Normalize image markers to '[IMAGE:n]'
#         - Preserve '[TABLE_PLACEHOLDER]'
#         """
#         out: List[str] = []
#         buffer: List[str] = []

#         def flush_buffer():
#             nonlocal buffer
#             if buffer:
#                 joined = " ".join(l for l in buffer if l)
#                 if joined.strip():
#                     out.append(joined.strip())
#                 buffer = []

#         for raw in lines:
#             line = raw.strip()

#             # Skip page markers
#             if re.match(r'^#\s*Page\s+\d+', line, re.IGNORECASE):
#                 flush_buffer()
#                 continue

#             # Heading lines: flush buffer, keep heading as a line
#             if line.startswith("#"):
#                 flush_buffer()
#                 out.append(line)
#                 continue

#             # Table placeholder: flush and keep
#             if line.startswith("[TABLE_PLACEHOLDER]"):
#                 flush_buffer()
#                 out.append("[TABLE_PLACEHOLDER]")
#                 continue

#             # Normalize image markers (either "IMAGE:1" or "[IMAGE:1]" -> "[IMAGE:1]")
#             m = re.match(r'^\[?IMAGE:?\s*([0-9]+)\]?$', line, re.IGNORECASE)
#             if m:
#                 flush_buffer()
#                 out.append(f"[IMAGE:{int(m.group(1))}]")
#                 continue

#             # Blank line: flush buffer and preserve a single blank
#             if line == "":
#                 flush_buffer()
#                 out.append("")
#                 continue

#             # Short-line accumulation heuristic
#             words = line.split()
#             if len(words) <= 6:
#                 # accumulate short lines; likely soft-wrapped
#                 buffer.append(line)
#             else:
#                 # longer lines: attach to buffer if any, otherwise emit directly
#                 if buffer:
#                     buffer.append(line)
#                     flush_buffer()
#                 else:
#                     out.append(line)

#         # flush remaining
#         flush_buffer()

#         # Collapse multiple blank lines into single blank
#         final: List[str] = []
#         prev_blank = False
#         for l in out:
#             if l == "":
#                 if not prev_blank:
#                     final.append("")
#                     prev_blank = True
#             else:
#                 final.append(l)
#                 prev_blank = False

#         return final


import os
import re
from typing import List, Dict, Tuple, Optional

import fitz  # PyMuPDF
import pdfplumber
import pandas as pd

from ..shared.database import get_db


class DocumentService:

    # ------------------------------------
    # Better table detection
    # ------------------------------------
    @staticmethod
    def is_table_text_block(block_text: str) -> bool:
        """
        Detect table-like text blocks to avoid duplication.
        Detects patterns like:

        ID
        Name
        Value
        1
        Alpha
        123
        """
        lines = [l.strip() for l in block_text.splitlines() if l.strip()]

        # Need at least 4 lines (minimum table structure)
        if len(lines) < 4:
            return False



        # Check for common table header words
        table_headers = ['id', 'name', 'value', 'column', 'row', 'data', 'item', 'no', 'number']
        first_lines_lower = [l.lower() for l in lines[:5]]

        header_match = sum(1 for h in table_headers for line in first_lines_lower if h in line)
        if header_match >= 2:
            # If we have table-like headers, check if body has numeric patterns
            numeric_count = sum(1 for l in lines if any(c.isdigit() for c in l))
            if numeric_count >= len(lines) * 0.3:  # 30% lines should have numbers
                return True

        # Check if many lines are single words or very short (table cell characteristic)
        single_word_count = sum(1 for l in lines if len(l.split()) == 1)
        if single_word_count >= len(lines) * 0.6:  # 60% are single words
            return True

        # Check for alternating pattern: text, text, number, text, text, number
        numeric_lines = [i for i, l in enumerate(lines) if l.replace('.', '').replace(',', '').isdigit()]
        if len(numeric_lines) >= 2:
            if len(lines) >= 6:
                every_third = all(i % 3 == 2 for i in numeric_lines[:min(3, len(numeric_lines))])
                if every_third:
                    return True

        return False

    # ------------------------------------
    # Extract text with improved table filtering
    # ------------------------------------
    
    @staticmethod
    def extract_text_with_image_markers(
        file_path: str, 
        output_dir: str
    ) -> Tuple[str, List[str]]:
        """
        Extract text in reading order, skip table-like blocks,
        avoid duplicate text blocks, and save images with markers.
        """

        full_text = ""
        image_files: List[str] = []
        image_counter = 1

        seen_blocks = set()      # Prevent duplicate text blocks
        image_seen = {}          # Prevent duplicate image extraction

        with fitz.open(file_path) as pdf:
            total_pages = len(pdf)
            
            for page_index, page in enumerate(pdf):
                blocks = page.get_text("dict")["blocks"]
                page_num = page_index + 1

                page_output_lines = [f"# Page {page_num}", ""]

                # -------------------------
                # TEXT BLOCKS
                # -------------------------
                for b in blocks:
                    if "lines" not in b:
                        continue

                    block_line_texts = []
                    block_max_font = 0.0

                    for line in b["lines"]:
                        line_text_parts = []
                        line_max_font = 0.0

                        for span in line["spans"]:
                            txt = span.get("text", "").strip()
                            if not txt:
                                continue
                            font_size = span.get("size", 0.0)
                            if font_size > line_max_font:
                                line_max_font = font_size
                            line_text_parts.append(txt)

                        if line_text_parts:
                            joined_line_text = " ".join(line_text_parts).strip()
                            if joined_line_text:
                                block_line_texts.append(joined_line_text)
                                if line_max_font > block_max_font:
                                    block_max_font = line_max_font

                    if not block_line_texts:
                        continue

                    block_text = "\n".join(block_line_texts)

                    # Skip duplicate text blocks
                    if block_text in seen_blocks:
                        continue
                    seen_blocks.add(block_text)

                    # Table detection
                    if DocumentService.is_table_text_block(block_text):
                        page_output_lines.append("[TABLE_PLACEHOLDER]")
                        page_output_lines.append("")
                        continue

                    # Heading detection
                    for line_text in block_line_texts:
                        if block_max_font >= 18:
                            page_output_lines.append(f"# {line_text}")
                            page_output_lines.append("")
                        elif 14 <= block_max_font < 18:
                            page_output_lines.append(f"## {line_text}")
                            page_output_lines.append("")
                        elif 12 <= block_max_font < 14:
                            page_output_lines.append(f"### {line_text}")
                            page_output_lines.append("")
                        else:
                            page_output_lines.append(line_text)

                    page_output_lines.append("")

                # -------------------------
                # IMAGE EXTRACTION
                # -------------------------
                image_list = page.get_images(full=True)

                for img in image_list:
                    xref = img[0]

                    # If image already extracted → reuse same number
                    if xref in image_seen:
                        page_output_lines.append(f"[IMAGE:{image_seen[xref]}]")
                        page_output_lines.append("")
                        continue

                    # Extract new image
                    try:
                        pix = fitz.Pixmap(pdf, xref)

                        # 🚨 HARD GUARD (THIS FIXES YOUR ERROR)
                        if pix.colorspace is None:
                            continue  # skip broken / mask images
                        
                        # # Fix: Ensure pixmap is RGB/Grayscale before saving as PNG
                        # # If CMYK (n=4) or other formats, convert to RGB
                        # if pix.n - pix.alpha < 3:  # Grayscale or less
                        #     pix = fitz.Pixmap(fitz.csRGB, pix)
                        # elif pix.n >= 4: # CMYK
                        #     pix = fitz.Pixmap(fitz.csRGB, pix)

                        # Convert everything to RGB safely
                        if pix.n >= 4 or pix.alpha:
                            pix = fitz.Pixmap(fitz.csRGB, pix)
                            
                        # Save image
                        img_path = os.path.join(output_dir, f"image_{image_counter}.png")
                        pix.save(img_path)

                        image_files.append(img_path)
                        image_seen[xref] = image_counter

                        # Use compact marker form
                        page_output_lines.append(f"[IMAGE:{image_counter}]")
                        page_output_lines.append("")

                        image_counter += 1
                    
                    except Exception as e:
                        print("⚠️ Image skipped:", e)
                        continue

                    finally:
                        pix = None

                # -------------------------
                # NORMALIZE PAGE OUTPUT
                # -------------------------
                full_text += "\n".join(page_output_lines) + "\n\n"

        return full_text, image_files



    # ------------------------------------
    # Extract Tables
    # ------------------------------------
    @staticmethod
    def extract_and_format_tables_from_pdf(
        file_path: str
    ) -> List[Dict]:
        """Extract tables using pdfplumber."""
        output: List[Dict] = []

        with pdfplumber.open(file_path) as pdf:
            total_pages = len(pdf.pages)
            
            for page_index, page in enumerate(pdf.pages, start=1):
                tables = page.extract_tables()

                for tbl_index, table in enumerate(tables, start=1):
                    if not table or len(table) < 2:
                        continue

                    df = pd.DataFrame(table[1:], columns=table[0])
                    df = df.dropna(how="all")

                    if df.empty:
                        continue

                    output.append({
                        "page": page_index,
                        "table_index": tbl_index,
                        "columns": list(df.columns),
                        "rows": df.values.tolist(),
                    })

        return output

    # ------------------------------------
    # Upload images
    # ------------------------------------
    @staticmethod
    def upload_images_to_supabase(
        image_paths: List[str],
        bucket_name: str = "pics"
    ) -> List[Dict[str, str]]:
        """Upload images to Supabase storage."""
        db = get_db()
        uploaded: List[Dict[str, str]] = []
        total_images = len(image_paths)

        for idx, img_path in enumerate(image_paths, start=1):
            file_name = os.path.basename(img_path)

            try:
                with open(img_path, "rb") as f:
                    data = f.read()

                unique_name = f"{os.path.splitext(file_name)[0]}_{os.urandom(4).hex()}.png"

                db.storage.from_(bucket_name).upload(
                    path=unique_name,
                    file=data,
                    file_options={"content-type": "image/png"},
                )

                url = db.storage.from_(bucket_name).get_public_url(unique_name)

                uploaded.append({
                    "image_number": idx,
                    "url": url,
                    "filename": unique_name,
                })
            except Exception as e:
                uploaded.append({
                    "image_number": idx,
                    "url": f"[UPLOAD_FAILED_{idx}]",
                    "filename": file_name,
                    "error": str(e),
                })

        return uploaded

    # ------------------------------------
    # Replace image markers
    # ------------------------------------
    @staticmethod
    def replace_placeholders_with_urls(text: str, images: List[Dict]) -> str:
        """
        Replace IMAGE:n and [IMAGE:n] markers with a readable block including URL.
        Accepts both formats to remain backward compatible.
        """
        # Replace both 'IMAGE:3' and '[IMAGE:3]' tokens
        for img in images:
            # accept either format when searching
            marker_plain = f"IMAGE:{img['image_number']}"
            marker_bracket = f"[IMAGE:{img['image_number']}]"
            replacement = f"\nimage: {img['image_number']}\nurl: {img['url']}\n"
            # Prefer replacing bracketed first, then plain
            text = text.replace(marker_bracket, replacement)
            text = text.replace(marker_plain, replacement)
        return text

    # ------------------------------------
    # Merge text and tables
    # ------------------------------------
    @staticmethod
    def create_unified_content(text: str, tables: List[Dict]) -> str:
        """Build final output with tables at correct positions."""
        final: List[str] = ["# Extracted PDF Content", ""]

        pages = text.split("# Page ")

        for chunk in pages:
            chunk = chunk.strip()
            if not chunk:
                continue

            lines = chunk.splitlines()
            page_header = lines[0].strip()
            body_lines = lines[1:]

            final.append(f"# Page {page_header}")
            final.append("")

            # Get tables for this page
            try:
                page_num = int(page_header)
                page_tables = [t for t in tables if t["page"] == page_num]
            except ValueError:
                page_tables = []

            # Insert tables at placeholders
            table_inserted_count = 0

            for line in body_lines:
                if line.strip() == "[TABLE_PLACEHOLDER]" and table_inserted_count < len(page_tables):
                    t = page_tables[table_inserted_count]
                    final.append("")
                    final.append(f"table: Table {t['table_index']}")
                    final.append(f"columns: {', '.join(str(c) for c in t['columns'])}")
                    final.append("rows:")
                    for row in t["rows"]:
                        final.append(", ".join(str(x) for x in row))
                    final.append("")
                    table_inserted_count += 1
                else:
                    final.append(line)

            # Add remaining tables at end of page
            for t in page_tables[table_inserted_count:]:
                final.append("")
                final.append(f"table: Table {t['table_index']}")
                final.append(f"columns: {', '.join(str(c) for c in t['columns'])}")
                final.append("rows:")
                for row in t["rows"]:
                    clean_row = [str(x).strip() if x else "" for x in row]
                    final.append(", ".join(clean_row))

                final.append("")

            final.append("")

        return "\n".join(final)

    # ------------------------------------
    # Delete images utility
    # ------------------------------------
    @staticmethod
    def delete_images_from_supabase(
        image_urls: List[str],
        bucket_name: str = "pics"
    ) -> Dict[str, any]:
        """Delete images from Supabase storage."""
        db = get_db()
        deleted = []
        failed = []

        for url in image_urls:
            try:
                filename = url.split("/")[-1]
                db.storage.from_(bucket_name).remove([filename])
                deleted.append(filename)
            except Exception as e:
                failed.append({"url": url, "error": str(e)})

        return {
            "deleted_count": len(deleted),
            "failed_count": len(failed),
            "deleted": deleted,
            "failed": failed,
        }

    # ------------------------------------
    # Normalize page lines
    # ------------------------------------
    @staticmethod
    def normalize_page_lines(lines: List[str]) -> List[str]:
        """
        Normalize page output lines:
        - Remove '# Page N' lines
        - Collapse sequences of short lines into a single paragraph
        - Preserve heading lines (starting with '#')
        - Normalize image markers to '[IMAGE:n]'
        - Preserve '[TABLE_PLACEHOLDER]'
        """
        out: List[str] = []
        buffer: List[str] = []

        def flush_buffer():
            nonlocal buffer
            if buffer:
                joined = " ".join(l for l in buffer if l)
                if joined.strip():
                    out.append(joined.strip())
                buffer = []

        for raw in lines:
            line = raw.strip()

            # Skip page markers
            if re.match(r'^#\s*Page\s+\d+', line, re.IGNORECASE):
                flush_buffer()
                continue

            # Heading lines: flush buffer, keep heading as a line
            if line.startswith("#"):
                flush_buffer()
                out.append(line)
                continue

            # Table placeholder: flush and keep
            if line.startswith("[TABLE_PLACEHOLDER]"):
                flush_buffer()
                out.append("[TABLE_PLACEHOLDER]")
                continue

            # Normalize image markers (either "IMAGE:1" or "[IMAGE:1]" -> "[IMAGE:1]")
            m = re.match(r'^\[?IMAGE:?\s*([0-9]+)\]?$', line, re.IGNORECASE)
            if m:
                flush_buffer()
                out.append(f"[IMAGE:{int(m.group(1))}]")
                continue

            # Blank line: flush buffer and preserve a single blank
            if line == "":
                flush_buffer()
                out.append("")
                continue

            # Short-line accumulation heuristic
            words = line.split()
            if len(words) <= 6:
                # accumulate short lines; likely soft-wrapped
                buffer.append(line)
            else:
                # longer lines: attach to buffer if any, otherwise emit directly
                if buffer:
                    buffer.append(line)
                    flush_buffer()
                else:
                    out.append(line)

        # flush remaining
        flush_buffer()

        # Collapse multiple blank lines into single blank
        final: List[str] = []
        prev_blank = False
        for l in out:
            if l == "":
                if not prev_blank:
                    final.append("")
                    prev_blank = True
            else:
                final.append(l)
                prev_blank = False

        return final