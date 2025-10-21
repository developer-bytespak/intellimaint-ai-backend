from pydantic import BaseModel
from typing import Any

class ServiceResponse(BaseModel):
    status: str
    data: Any
    error: str | None = None

