# # doc_extract_service.py

# import fitz  # PyMuPDF
# import pdfplumber
# import os
# import pandas as pd
# from typing import List, Dict
# from ..shared.database import get_db


# class DocumentService:

#     @staticmethod
#     def extract_text_with_image_markers(file_path: str, output_dir: str):
#         """Extract text from PDF and insert [IMAGE_N] markers where images appear."""
#         pdf = fitz.open(file_path)
#         full_text = ""
#         image_files = []
#         image_counter = 1

#         for page_index, page in enumerate(pdf):
#             page_text = page.get_text("text")

#             # Extract images
#             image_list = page.get_images(full=True)

#             for img_index, img in enumerate(image_list):
#                 xref = img[0]
#                 pix = fitz.Pixmap(pdf, xref)

#                 # Fix CMYK
#                 if pix.n >= 5:
#                     pix = fitz.Pixmap(fitz.csRGB, pix)

#                 img_path = os.path.join(output_dir, f"image_{image_counter}.png")
#                 pix.save(img_path)
#                 image_files.append(img_path)

#                 # Insert placeholder
#                 page_text += f"\n[IMAGE_{image_counter}]\n"
#                 image_counter += 1

#             full_text += page_text + "\n"

#         pdf.close()
#         return full_text, image_files

#     @staticmethod
#     def extract_and_format_tables_from_pdf(file_path: str):
#         """Extract tables from PDF and format them as JSON-serializable rows."""
#         tables_output = []

#         with pdfplumber.open(file_path) as pdf:
#             for page_num, page in enumerate(pdf.pages, start=1):
#                 tables = page.extract_tables()

#                 for tbl_index, table in enumerate(tables, start=1):
#                     if table:
#                         # Convert to DataFrame
#                         df = pd.DataFrame(table[1:], columns=table[0])

#                         # Remove empty rows
#                         df = df.dropna(how="all", axis=0)

#                         # ✅ FIX: Skip tables that ended up with no data rows
#                         if df.empty:
#                             continue

#                         # Convert DataFrame to list of dicts for DB (JSON-friendly)
#                         tables_output.append({
#                             "page": page_num,
#                             "table_index": tbl_index,
#                             "data": df.to_dict(orient="records")
#                         })
#         return tables_output

#     @staticmethod
#     def upload_images_to_supabase(image_paths: List[str], bucket_name: str = "pics") -> List[Dict[str, str]]:
#         """
#         Upload images to Supabase storage bucket and return their public URLs.

#         Args:
#             image_paths: List of local image file paths
#             bucket_name: Supabase storage bucket name (default: "pics")

#         Returns:
#             List of dicts with image_number and url
#         """
#         db = get_db()
#         uploaded_images = []

#         for idx, img_path in enumerate(image_paths, start=1):
#             file_name = os.path.basename(img_path)
#             try:
#                 # Read image file
#                 with open(img_path, 'rb') as f:
#                     file_data = f.read()

#                 # Generate unique filename
#                 unique_name = f"{os.path.splitext(file_name)[0]}_{os.urandom(8).hex()}.png"

#                 # Upload to Supabase storage
#                 response = db.storage.from_(bucket_name).upload(
#                     path=unique_name,
#                     file=file_data,
#                     file_options={"content-type": "image/png"}
#                 )

#                 # Get public URL
#                 public_url = db.storage.from_(bucket_name).get_public_url(unique_name)

#                 uploaded_images.append({
#                     "image_number": idx,
#                     "url": public_url,
#                     "filename": unique_name
#                 })

#             except Exception as e:
#                 print(f"Error uploading {img_path}: {str(e)}")
#                 # Add placeholder if upload fails
#                 uploaded_images.append({
#                     "image_number": idx,
#                     "url": f"[UPLOAD_FAILED_{idx}]",
#                     "filename": file_name,
#                     "error": str(e)
#                 })

#         return uploaded_images

#     @staticmethod
#     def replace_placeholders_with_urls(text: str, image_data: List[Dict[str, str]]) -> str:
#         """
#         Replace [IMAGE_N] placeholders with actual Supabase URLs.

#         Args:
#             text: Text containing [IMAGE_N] placeholders
#             image_data: List of dicts with image_number and url

#         Returns:
#             Text with placeholders replaced by URLs
#         """
#         modified_text = text

#         for img in image_data:
#             image_num = img["image_number"]
#             url = img["url"]

#             # Replace [IMAGE_N] with the actual URL
#             placeholder = f"[IMAGE_{image_num}]"
#             modified_text = modified_text.replace(placeholder, url)

#         return modified_text

#     @staticmethod
#     def format_tables_as_markdown(tables: List[Dict]) -> str:
#         """
#         Convert extracted tables into markdown format.

#         Args:
#             tables: List of table dicts with page, table_index, and data

#         Returns:
#             Markdown formatted string of all tables
#         """
#         if not tables:
#             return ""

#         markdown_output = ""

#         for table in tables:
#             # Skip empty tables
#             if not table.get("data") or len(table["data"]) == 0:
#                 continue

#             page = table.get("page", "")
#             table_idx = table.get("table_index", "")
#             data = table["data"]

#             # Add table header
#             markdown_output += f"\n\n[TABLE - Page {page}, Table {table_idx}]\n"

#             # Get column names
#             columns = list(data[0].keys())

#             # Create header row
#             header = "| " + " | ".join(columns) + " |"
#             separator = "|" + "|".join(["---" for _ in columns]) + "|"

#             markdown_output += header + "\n" + separator + "\n"

#             # Add data rows
#             for row in data:
#                 values = [str(row.get(col, "")) for col in columns]
#                 markdown_output += "| " + " | ".join(values) + " |\n"

#             markdown_output += "\n"

#         return markdown_output

#     @staticmethod
#     def create_unified_content(text: str, tables: List[Dict]) -> str:
#         """
#         Merge text with tables at appropriate positions.

#         Args:
#             text: Main text content with image URLs
#             tables: List of extracted tables

#         Returns:
#             Single unified text document with embedded tables
#         """
#         if not tables or all(not t.get("data") for t in tables):
#             return text

#         # Split text by pages (assuming page breaks exist)
#         lines = text.split('\n')
#         result = []

#         # Group tables by page
#         tables_by_page = {}
#         for table in tables:
#             page = table.get("page", 1)
#             if page not in tables_by_page:
#                 tables_by_page[page] = []
#             tables_by_page[page].append(table)

#         for line in lines:
#             result.append(line)

#             # Check if this line contains a page number
#             if line.strip().isdigit():
#                 page_num = int(line.strip())

#                 # Insert tables for this page
#                 if page_num in tables_by_page:
#                     for table in tables_by_page[page_num]:
#                         if table.get("data"):
#                             table_md = DocumentService.format_tables_as_markdown([table])
#                             result.append(table_md)

#         return '\n'.join(result)

#     @staticmethod
#     def delete_images_from_supabase(image_urls: List[str], bucket_name: str = "pics") -> Dict[str, any]:
#         """
#         Delete images from Supabase storage bucket.

#         Args:
#             image_urls: List of public URLs to delete
#             bucket_name: Supabase storage bucket name

#         Returns:
#             Dict with deletion results
#         """
#         db = get_db()
#         deleted = []
#         failed = []

#         for url in image_urls:
#             try:
#                 # Extract filename from URL
#                 filename = url.split('/')[-1]

#                 # Delete from storage
#                 response = db.storage.from_(bucket_name).remove([filename])
#                 deleted.append(filename)

#             except Exception as e:
#                 failed.append({"url": url, "error": str(e)})

#         return {
#             "deleted_count": len(deleted),
#             "failed_count": len(failed),
#             "deleted": deleted,
#             "failed": failed
#         }

#     @staticmethod
#     def convert_to_ifixit_style(pages: List[Dict]) -> str:
#         """
#         Convert extracted PDF content into iFixit-style step-by-step markdown.

#         Args:
#             pages: List of dicts containing page, text, tables, images

#         Returns:
#             Markdown string in iFixit style
#         """

#         md = "# PDF Extraction — iFixit Style Guide\n\n"

#         for page in pages:
#             pnum = page["page"]

#             md += f"## Step {pnum} — Page {pnum}\n\n"

#             # Add page text
#             if page["text"].strip():
#                 md += page["text"].strip() + "\n\n"

#             # Add tables
#             for tbl_index, table in enumerate(page.get("tables", []), start=1):
#                 if not table:
#                     continue
#                 md += f"### Table {tbl_index}\n"

#                 # Convert table into markdown
#                 columns = table[0]
#                 md += "| " + " | ".join(columns) + " |\n"
#                 md += "|" + "|".join(["---" for _ in columns]) + "|\n"

#                 for row in table[1:]:
#                     md += "| " + " | ".join(row) + " |\n"
#                 md += "\n"

#             # Add images
#             for img in page.get("images", []):
#                 md += f"![Page {pnum} Image]({img})\n\n"

#         return md

#     @staticmethod
#     def build_page_wise_data(text: str, tables: List[Dict], image_urls: List[Dict]) -> List[Dict]:
#         """
#         Convert raw unified content into page-wise structured content for iFixit formatting.
#         NOTE: This currently uses a simple 'Sample Page' splitter as per original implementation.
#         """
#         pages = []
#         text_pages = text.split("Sample Page")  # very easy way

#         # Fix first empty chunk
#         if len(text_pages) > 0 and text_pages[0].strip() == "":
#             text_pages = text_pages[1:]

#         for idx, chunk in enumerate(text_pages, start=1):
#             txt = "Sample Page" + chunk

#             # Filter tables by current page
#             page_tables = []
#             for t in tables:
#                 if t.get("page") == idx and t.get("data"):
#                     data_rows = t["data"]

#                     # ✅ SAFETY: Ensure there is at least one row
#                     if not isinstance(data_rows, list) or len(data_rows) == 0:
#                         continue

#                     first_row = data_rows[0]
#                     if not isinstance(first_row, dict):
#                         continue

#                     rows = []
#                     cols = list(first_row.keys())
#                     rows.append(cols)
#                     for row in data_rows:
#                         rows.append([str(row.get(c, "")) for c in cols])
#                     page_tables.append(rows)

#             # Filter images by current page
#             # NOTE: Original implementation assumes image_number == page index.
#             # Keeping behavior for backward compatibility.
#             page_images = [i["url"] for i in image_urls if i.get("image_number") == idx]

#             pages.append({
#                 "page": idx,
#                 "text": txt,
#                 "tables": page_tables,
#                 "images": page_images
#             })

#         return pages

import os
from typing import List, Dict, Tuple

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
    def extract_text_with_image_markers(file_path: str, output_dir: str) -> Tuple[str, List[str]]:
        """
        Extract text in reading order, skip table-like blocks,
        and save images to output_dir with IMAGE:n markers in the text.
        """
        full_text = ""
        image_files: List[str] = []
        image_counter = 1

        # Use context manager so PDF is ALWAYS closed (even on error)
        with fitz.open(file_path) as pdf:

            for page_index, page in enumerate(pdf):
                blocks = page.get_text("dict")["blocks"]
                page_num = page_index + 1

                page_output_lines = [f"# Page {page_num}", ""]

                # ---- TEXT BLOCKS ----
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

                    # Skip table-like blocks and mark with placeholder
                    if DocumentService.is_table_text_block(block_text):
                        page_output_lines.append("[TABLE_PLACEHOLDER]")
                        page_output_lines.append("")
                        continue

                    # Heading detection based on font size
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

                # ---- IMAGES ----
                image_list = page.get_images(full=True)
                for img in image_list:
                    xref = img[0]

                    try:
                        pix = fitz.Pixmap(pdf, xref)
                    except Exception:
                        continue

                    try:
                        # Robust colorspace fix:
                        # - convert anything that's not Gray/RGB
                        # - drop alpha channels into RGB
                        if pix.colorspace is None:
                            pix_converted = fitz.Pixmap(fitz.csRGB, pix)
                            pix = pix_converted
                        else:
                            if pix.colorspace.n not in (1, 3) or pix.alpha:
                                pix_converted = fitz.Pixmap(fitz.csRGB, pix)
                                pix = pix_converted

                        img_path = os.path.join(output_dir, f"image_{image_counter}.png")
                        pix.save(img_path)

                        image_files.append(img_path)

                        page_output_lines.append(f"IMAGE:{image_counter}")
                        page_output_lines.append("")

                        image_counter += 1

                    finally:
                        # Ensure pixmap is freed
                        pix = None

                full_text += "\n".join(page_output_lines) + "\n\n"

        return full_text, image_files

    # ------------------------------------
    # Extract Tables
    # ------------------------------------
    @staticmethod
    def extract_and_format_tables_from_pdf(file_path: str) -> List[Dict]:
        """Extract tables using pdfplumber."""
        output: List[Dict] = []

        with pdfplumber.open(file_path) as pdf:
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
        """Replace IMAGE:n markers with formatted image references."""
        for img in images:
            marker = f"IMAGE:{img['image_number']}"
            replacement = f"\nimage: {img['image_number']}\nurl: {img['url']}\n"
            text = text.replace(marker, replacement)
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
                    final.append(", ".join(str(x) for x in row))
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
