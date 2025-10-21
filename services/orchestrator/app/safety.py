"""Safety and guardrails for AI responses"""

class SafetyGuardrails:
    def __init__(self):
        self.blocked_terms = []
    
    def check_input(self, text: str) -> bool:
        """Check if input passes safety checks"""
        return True
    
    def check_output(self, text: str) -> bool:
        """Check if output passes safety checks"""
        return True

