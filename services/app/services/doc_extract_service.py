import fitz   # PyMuPDF
import os
import pdfplumber


class DocumentService:

    @staticmethod
    def extract_text_from_pdf(file_path: str) -> str:
        """Extract all text from a PDF file."""
        full_text = ""

        with fitz.open(file_path) as pdf:
            for page in pdf:
                full_text += page.get_text()

        return full_text

    @staticmethod
    def extract_images_from_pdf(file_path: str, output_dir: str):
        """Extract all embedded images from a PDF file."""
        pdf = fitz.open(file_path)
        image_files = []

        for page_index, page in enumerate(pdf):
            image_list = page.get_images(full=True)

            for img_index, img in enumerate(image_list):
                xref = img[0]
                pix = fitz.Pixmap(pdf, xref)

                # Handle CMYK images
                if pix.n >= 5:
                    pix = fitz.Pixmap(fitz.csRGB, pix)

                img_path = os.path.join(output_dir, f"page{page_index+1}_img{img_index+1}.png")
                pix.save(img_path)
                image_files.append(img_path)

        return image_files

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
