from pydantic import BaseModel
from typing import List

class JobResponse(BaseModel):
    jobId: str
    fileName: str
    status: str

class BatchResponse(BaseModel):
    batchId: str
    jobs: List[JobResponse]
    status: str
