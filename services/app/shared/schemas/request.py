from pydantic import BaseModel
from typing import Optional

class OrchestrationRequest(BaseModel):
    query: str
    user_id: str
    session_id: Optional[str] = None
    context: Optional[dict] = None

