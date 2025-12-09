from typing import Dict, Optional
from datetime import datetime
import uuid


class ProgressTracker:
    """In-memory progress tracking for PDF extraction jobs"""
    
    _jobs: Dict[str, Dict] = {}  # job_id -> progress data
    
    # Milestones for each API call: 1st call = 25%, 2nd = 50%, 3rd = 75%, 4th = 100%
    API_MILESTONES = [25, 50, 75, 100]
    
    # Step weights for overall progress calculation
    STEP_WEIGHTS = {
        "text_extraction": 60,    # 60% of total
        "table_extraction": 20,    # 20% of total
        "image_upload": 15,        # 15% of total
        "unified_content": 5       # 5% of total
    }
    
    @classmethod
    def create_job(cls, total_pages: int = 0) -> str:
        """Create new job and return job_id"""
        job_id = str(uuid.uuid4())
        cls._jobs[job_id] = {
            "job_id": job_id,
            "status": "processing",  # processing, completed, failed
            "progress": 0,  # 0-100
            "current_page": 0,
            "total_pages": total_pages,
            "current_step": "initializing",
            "step_progress": {
                "text_extraction": 0,    # 0-100 for this step
                "table_extraction": 0,
                "image_upload": 0,
                "unified_content": 0
            },
            "data": None,  # Will store final extracted content
            "error": None,
            "api_call_count": 0,  # Track number of API calls made
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }
        return job_id
    
    @classmethod
    def update_step_progress(cls, job_id: str, step: str, step_progress: int):
        """
        Update progress for a specific step
        step: "text_extraction", "table_extraction", "image_upload", "unified_content"
        step_progress: 0-100 for that step
        """
        if job_id not in cls._jobs:
            return
        
        # Update step progress
        cls._jobs[job_id]["step_progress"][step] = min(step_progress, 100)
        cls._jobs[job_id]["current_step"] = step
        
        # Calculate overall progress
        overall = 0
        for step_name, weight in cls.STEP_WEIGHTS.items():
            step_pct = cls._jobs[job_id]["step_progress"].get(step_name, 0)
            overall += (step_pct * weight) / 100
        
        cls._jobs[job_id]["progress"] = int(overall)
        cls._jobs[job_id]["updated_at"] = datetime.now().isoformat()
    
    @classmethod
    def update_text_extraction_progress(cls, job_id: str, current_page: int, total_pages: int):
        """Update text extraction progress (page by page)"""
        if job_id not in cls._jobs:
            return
        
        # Calculate step progress (0-100)
        step_progress = int((current_page / total_pages) * 100) if total_pages > 0 else 0
        
        cls._jobs[job_id]["current_page"] = current_page
        cls._jobs[job_id]["total_pages"] = total_pages
        
        # Update overall progress
        cls.update_step_progress(job_id, "text_extraction", step_progress)
    
    @classmethod
    def mark_completed(cls, job_id: str, data: str):
        """Mark job as completed with final data"""
        if job_id not in cls._jobs:
            return
        
        cls._jobs[job_id].update({
            "status": "completed",
            "progress": 100,
            "data": data,
            "current_step": "completed",
            "updated_at": datetime.now().isoformat()
        })
    
    @classmethod
    def mark_failed(cls, job_id: str, error: str):
        """Mark job as failed"""
        if job_id not in cls._jobs:
            return
        
        cls._jobs[job_id].update({
            "status": "failed",
            "error": error,
            "updated_at": datetime.now().isoformat()
        })
    
    @classmethod
    def get_progress(cls, job_id: str) -> Optional[Dict]:
        """Get current progress for a job"""
        return cls._jobs.get(job_id)
    
    @classmethod
    def check_and_increment_api_call(cls, job_id: str) -> tuple[bool, int]:
        """
        Check if progress should be returned and increment call count if milestone reached
        Returns (should_return, api_call_count)
        - should_return: True if progress >= milestone for next call
        - api_call_count: current call count (after increment if milestone reached)
        """
        if job_id not in cls._jobs:
            return (False, 0)
        
        current_call_count = cls._jobs[job_id].get("api_call_count", 0)
        current_progress = cls._jobs[job_id].get("progress", 0)
        
        # If all milestones passed, always return
        if current_call_count >= len(cls.API_MILESTONES):
            return (True, current_call_count)
        
        # Get expected milestone for next API call (0-indexed)
        # Call 1 (count=0) should return at 25%, Call 2 (count=1) at 50%, etc.
        expected_milestone = cls.API_MILESTONES[current_call_count]
        
        # Check if progress has reached the expected milestone
        if current_progress >= expected_milestone:
            # Increment call count only when milestone is reached
            cls._jobs[job_id]["api_call_count"] = current_call_count + 1
            return (True, current_call_count + 1)
        
        # Milestone not reached yet, don't increment
        return (False, current_call_count)
    
    @classmethod
    def cleanup_old_jobs(cls, max_age_hours: int = 24):
        """Clean up old completed jobs (optional)"""
        from datetime import datetime, timedelta
        cutoff = datetime.now() - timedelta(hours=max_age_hours)
        
        to_remove = []
        for job_id, job_data in cls._jobs.items():
            if job_data["status"] in ["completed", "failed"]:
                updated = datetime.fromisoformat(job_data["updated_at"])
                if updated < cutoff:
                    to_remove.append(job_id)
        
        for job_id in to_remove:
            del cls._jobs[job_id]

