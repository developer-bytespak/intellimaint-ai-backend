import fitz  # PyMuPDF
import pdfplumber
import shutil
import uuid
import os
import pandas as pd

class DocumentService:

    @staticmethod
    def extract_text_with_image_markers(file_path: str, output_dir: str):
        """Extract text from PDF and insert [IMAGE_N] markers where images appear."""
        pdf = fitz.open(file_path)
        full_text = ""
        image_files = []
        image_counter = 1
        
        for page_index, page in enumerate(pdf):
            page_text = page.get_text("text")
            
            # Get images on this page
            image_list = page.get_images(full=True)
            
            if image_list:
                # Insert image placeholders
                for img_index, img in enumerate(image_list):
                    xref = img[0]
                    pix = fitz.Pixmap(pdf, xref)
                    
                    # Handle CMYK images
                    if pix.n >= 5:
                        pix = fitz.Pixmap(fitz.csRGB, pix)
                    
                    img_path = os.path.join(output_dir, f"image_{image_counter}.png")
                    pix.save(img_path)
                    image_files.append(img_path)
                    
                    # Add placeholder in text
                    page_text += f"\n[IMAGE_{image_counter}]\n"
                    image_counter += 1
            
            full_text += page_text + "\n"
        
        pdf.close()
        return full_text, image_files

    @staticmethod
    def extract_tables_from_pdf(file_path: str):
        """Extract tables from PDF using pdfplumber."""
        tables_output = []
        with pdfplumber.open(file_path) as pdf:
            for page_num, page in enumerate(pdf.pages, start=1):
                tables = page.extract_tables()
                for tbl_index, table in enumerate(tables, start=1):
                    tables_output.append({
                        "page": page_num,
                        "table_index": tbl_index,
                        "rows": table
                    })
        return tables_output

    @staticmethod
    def extract_and_format_tables_from_pdf(file_path: str):
        """Extract tables from PDF and convert them into DataFrames for easy processing."""
        tables_output = []
        with pdfplumber.open(file_path) as pdf:
            for page_num, page in enumerate(pdf.pages, start=1):
                tables = page.extract_tables()

                for tbl_index, table in enumerate(tables, start=1):
                    # Convert the table into a pandas DataFrame for easier manipulation
                    if table:
                        df = pd.DataFrame(table[1:], columns=table[0])  # Use first row as columns
                        df = df.dropna(how="all", axis=0)  # Remove empty rows
                        tables_output.append({
                            "page": page_num,
                            "table_index": tbl_index,
                            "dataframe": df
                        })
        return tables_output
