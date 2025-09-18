# services/job_queue_service.py

import json
import asyncio
from datetime import datetime
from typing import Optional, Dict, Any
from sqlmodel import Session, select

from models.job_queue import JobQueue, JobStatus, JobType
from utils.db import get_session


class JobQueueService:
    """Service for managing async job processing."""
    
    @staticmethod
    async def create_job(
        session: Session,
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
        session.add(job)
        session.commit()
        session.refresh(job)
        return job
    
    @staticmethod
    async def get_next_job(session: Session) -> Optional[JobQueue]:
        """Get the next pending job with highest priority."""
        statement = select(JobQueue).where(
            JobQueue.status == JobStatus.PENDING
        ).order_by(JobQueue.priority.desc(), JobQueue.created_at.asc())
        
        return session.exec(statement).first()
    
    @staticmethod
    async def update_job_status(
        session: Session,
        job_id: int,
        status: JobStatus,
        result: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None
    ) -> bool:
        """Update job status and result."""
        job = session.get(JobQueue, job_id)
        if not job:
            return False
        
        job.status = status
        job.updated_at = datetime.utcnow()
        
        if status == JobStatus.PROCESSING:
            job.started_at = datetime.utcnow()
        elif status == JobStatus.COMPLETED:
            job.completed_at = datetime.utcnow()
            if result:
                job.result = json.dumps(result)
        elif status == JobStatus.FAILED:
            job.error_message = error_message
            job.retry_count += 1
            
            # Retry if under max retries
            if job.retry_count < job.max_retries:
                job.status = JobStatus.PENDING
                job.updated_at = datetime.utcnow()
        
        session.add(job)
        session.commit()
        return True
    
    @staticmethod
    async def process_lecture_generation_job(session: Session, job: JobQueue) -> Dict[str, Any]:
        """Process a lecture generation job."""
        try:
            payload = json.loads(job.payload)
            
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
                session, job.id, JobStatus.COMPLETED, result
            )
            
            return result
            
        except Exception as e:
            await JobQueueService.update_job_status(
                session, job.id, JobStatus.FAILED, error_message=str(e)
            )
            raise e
    
    @staticmethod
    async def process_curriculum_processing_job(session: Session, job: JobQueue) -> Dict[str, Any]:
        """Process a curriculum processing job."""
        try:
            payload = json.loads(job.payload)
            
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
                session, job.id, JobStatus.COMPLETED, result
            )
            
            return result
            
        except Exception as e:
            await JobQueueService.update_job_status(
                session, job.id, JobStatus.FAILED, error_message=str(e)
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
                with Session(get_session().__next__()) as session:
                    job = await JobQueueService.get_next_job(session)
                    if job:
                        await self._process_job(session, job)
                    else:
                        await asyncio.sleep(5)  # Wait 5 seconds before checking again
            except Exception as e:
                print(f"Job processing error: {e}")
                await asyncio.sleep(10)
    
    async def _process_job(self, session: Session, job: JobQueue):
        """Process a single job."""
        try:
            await JobQueueService.update_job_status(
                session, job.id, JobStatus.PROCESSING
            )
            
            if job.job_type == JobType.LECTURE_GENERATION:
                await JobQueueService.process_lecture_generation_job(session, job)
            elif job.job_type == JobType.CURRICULUM_PROCESSING:
                await JobQueueService.process_curriculum_processing_job(session, job)
            else:
                raise ValueError(f"Unknown job type: {job.job_type}")
                
        except Exception as e:
            print(f"Error processing job {job.id}: {e}")
            await JobQueueService.update_job_status(
                session, job.id, JobStatus.FAILED, error_message=str(e)
            )
    
    def stop_processing(self):
        """Stop the job processing loop."""
        self.running = False
