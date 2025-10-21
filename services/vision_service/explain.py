"""Vision-language models (BLIP-2, LLaVA)"""

class VisionExplainer:
    def __init__(self):
        self.model = None
    
    def explain_image(self, image_path: str, question: str = None):
        """Generate explanation for image"""
        return {"explanation": ""}

