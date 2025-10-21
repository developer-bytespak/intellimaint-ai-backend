"""Object detection models (YOLOv8, SAM)"""

class YOLODetector:
    def __init__(self):
        self.model = None
    
    def detect(self, image_path: str):
        """Detect objects in image"""
        return {"objects": []}

class SAMSegmentor:
    def __init__(self):
        self.model = None
    
    def segment(self, image_path: str):
        """Segment image using SAM"""
        return {"segments": []}

