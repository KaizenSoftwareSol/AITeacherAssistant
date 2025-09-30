# services/job_queue_service.py

import json
import asyncio
from datetime import datetime
from typing import Optional, Dict, Any

from models.job_queue import JobQueue, JobStatus, JobType
from utils.db import get_db


class JobQueueService:
    """Service for managing async job processing."""
    
    @staticmethod
    async def create_job(
        db,
        job_type: JobType,
        payload: Dict[str, Any],
        priority: int = 0,
        max_retries: int = 3
    ) -> JobQueue:
        """Create a new job in the queue."""
        job = JobQueue(
            job_type=job_type,
            payload=json.dumps(payload),
            priority=priority,
            max_retries=max_retries,
            status=JobStatus.PENDING
        )
        # Create job in Supabase
        job_result = db.create_record("job_queue", job.dict())
        return JobQueue(**job_result)
        return job
    
    @staticmethod
    async def get_next_job(db) -> Optional[JobQueue]:
        """Get the next pending job with highest priority."""
        job_data = db.get_record_by_id("job_queue", {"status": JobStatus.PENDING}, order_by="priority DESC, created_at ASC")
        return JobQueue(**job_data) if job_data else None
        ).order_by(JobQueue.priority.desc(), JobQueue.created_at.asc())
        
        return JobQueue(**job_data) if job_data else None
    
    @staticmethod
    async def update_job_status(
        db,
        job_id: int,
        status: JobStatus,
        result: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None
    ) -> bool:
        """Update job status and result."""
        job_data = db.get_record_by_id("job_queue", job_id)
        if not job:
            return False
        
        job_data["status"] = status
        job.updated_at = datetime.utcnow()
        
        if status == JobStatus.PROCESSING:
            job_data["started_at"] = datetime.utcnow()
        elif status == JobStatus.COMPLETED:
            job_data["completed_at"] = datetime.utcnow()
            if result:
                job_data["result"] = json.dumps(result)
        elif status == JobStatus.FAILED:
            job_data["error_message"] = error_message
            job.retry_count += 1
            
            # Retry if under max retries
            if job_data["retry_count"] < job_data["max_retries"]:
                job_data["status"] = JobStatus.PENDING
                job_data["updated_at"] = datetime.utcnow()
        
        updated_job = db.update_record("job_queue", job_id, job_data)
        return JobQueue(**updated_job) if updated_job else None
        return True
    
    @staticmethod
    async def process_lecture_generation_job(db, job: JobQueue) -> Dict[str, Any]:
        """Process a lecture generation job."""
        try:
            payload = json.loads(job_data["payload"])
            
            # Extract job parameters
            course_id = payload.get("course_id")
            teacher_id = payload.get("teacher_id")
            chapter = payload.get("chapter")
            book_reference = payload.get("book_reference")
            
            # TODO: Implement actual lecture generation logic
            # This would call the AI generation service
            
            # For now, return a mock result
            result = {
                "lecture_id": 1,
                "status": "generated",
                "content_length": 1500,
                "processing_time": 30.5
            }
            
            await JobQueueService.update_job_status(
                db, job_id, JobStatus.COMPLETED, result
            )
            
            return result
            
        except Exception as e:
            await JobQueueService.update_job_status(
                db, job_id, JobStatus.FAILED, error_message=str(e)
            )
            raise e
    
    @staticmethod
    async def process_curriculum_processing_job(db, job: JobQueue) -> Dict[str, Any]:
        """Process a curriculum processing job."""
        try:
            payload = json.loads(job_data["payload"])
            
            # Extract job parameters
            course_id = payload.get("course_id")
            curriculum_content = payload.get("curriculum_content")
            
            # TODO: Implement curriculum processing logic
            # This would parse and structure the curriculum content
            
            result = {
                "course_id": course_id,
                "status": "processed",
                "chapters_identified": 12,
                "processing_time": 45.2
            }
            
            await JobQueueService.update_job_status(
                db, job_id, JobStatus.COMPLETED, result
            )
            
            return result
            
        except Exception as e:
            await JobQueueService.update_job_status(
                db, job_id, JobStatus.FAILED, error_message=str(e)
            )
            raise e


class JobProcessor:
    """Background job processor."""
    
    def __init__(self):
        self.running = False
    
    async def start_processing(self):
        """Start the job processing loop."""
        self.running = True
        while self.running:
            try:
                job = await JobQueueService.get_next_job(db)
                if job:
                    await self._process_job(db, job)
                    else:
                        await asyncio.sleep(5)  # Wait 5 seconds before checking again
            except Exception as e:
                print(f"Job processing error: {e}")
                await asyncio.sleep(10)
    
    async def _process_job(self, db, job: JobQueue):
        """Process a single job."""
        try:
            await JobQueueService.update_job_status(
                db, job_id, JobStatus.PROCESSING
            )
            
            if job.job_type == JobType.LECTURE_GENERATION:
                await JobQueueService.process_lecture_generation_job(db, job)
            elif job.job_type == JobType.CURRICULUM_PROCESSING:
                await JobQueueService.process_curriculum_processing_job(db, job)
            else:
                raise ValueError(f"Unknown job type: {job.job_type}")
                
        except Exception as e:
            print(f"Error processing job {job.id}: {e}")
            await JobQueueService.update_job_status(
                db, job_id, JobStatus.FAILED, error_message=str(e)
            )
    
    def stop_processing(self):
        """Stop the job processing loop."""
        self.running = False
