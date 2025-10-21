"""OCR using PaddleOCR/Tesseract"""

class OCRProcessor:
    def __init__(self):
        self.engine = None
    
    def extract_text(self, image_path: str):
        """Extract text from image"""
        return {"text": "", "confidence": 0.0}

