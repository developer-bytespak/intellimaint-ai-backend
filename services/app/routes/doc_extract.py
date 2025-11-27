import fitz  # PyMuPDF
import pdfplumber
import shutil
import uuid
import os
import pandas as pd
from fastapi import APIRouter, UploadFile, File, HTTPException
from typing import List, Dict

router = APIRouter()

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

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
            image_list = page.get_images(full=True)
            
            if image_list:
                for img_index, img in enumerate(image_list):
                    xref = img[0]
                    pix = fitz.Pixmap(pdf, xref)
                    
                    if pix.n >= 5:
                        pix = fitz.Pixmap(fitz.csRGB, pix)
                    
                    img_path = os.path.join(output_dir, f"image_{image_counter}.png")
                    pix.save(img_path)
                    image_files.append(img_path)
                    page_text += f"\n[IMAGE_{image_counter}]\n"
                    image_counter += 1
            
            full_text += page_text + "\n"
        
        pdf.close()
        return full_text, image_files

    @staticmethod
    def extract_and_format_tables_from_pdf(file_path: str) -> List[Dict]:
        """Extract tables from PDF and convert them into DataFrames for easy processing."""
        tables_output = []
        with pdfplumber.open(file_path) as pdf:
            for page_num, page in enumerate(pdf.pages, start=1):
                tables = page.extract_tables()

                for tbl_index, table in enumerate(tables, start=1):
                    if table:
                        df = pd.DataFrame(table[1:], columns=table[0])
                        df = df.dropna(how="all", axis=0)
                        tables_output.append({
                            "page": page_num,
                            "table_index": tbl_index,
                            "dataframe": df.to_dict(orient="records")
                        })
        return tables_output


@router.post("/extract/full")
async def extract_text_and_images(file: UploadFile = File(...)):
    """Extract text, images, and tables from a PDF."""
    if not file.filename.endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Invalid file format. Only PDF files are allowed.")
    
    temp_name = f"{uuid.uuid4()}.pdf"
    file_path = os.path.join(UPLOAD_DIR, temp_name)

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    image_dir = os.path.join(UPLOAD_DIR, f"img_{uuid.uuid4()}")
    os.makedirs(image_dir, exist_ok=True)

    try:
        # Extract Text with Image Placeholders
        text_with_placeholders, extracted_images = DocumentService.extract_text_with_image_markers(file_path, image_dir)
        clean_text = text_with_placeholders.replace("\u0000", "")  # Remove null characters

        # Extract Tables and Format Them into DataFrames
        extracted_tables = DocumentService.extract_and_format_tables_from_pdf(file_path)
    finally:
        # Clean up the uploaded files
        os.remove(file_path)
        shutil.rmtree(image_dir)

    return {
        "filename": file.filename,
        "text": clean_text,
        "total_images": len(extracted_images),
        "images": extracted_images,
        "tables": extracted_tables
    }
