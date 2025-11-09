"""
Core queue logic for QueueCTL
Handles job enqueueing, state transitions, and DLQ management
"""

import json
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta

from .storage import Storage, JobState
from .config import get_config


class Queue:
    """Job queue manager"""
    
    def __init__(self, storage: Optional[Storage] = None):
        """Initialize queue with storage backend"""
        self.config = get_config()
        self.storage = storage or Storage(self.config.db_path)
    
    def enqueue(self, job_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Enqueue a new job
        
        Args:
            job_data: Dictionary with 'id' and 'command' keys
        
        Returns:
            Dictionary with success status and message
        """
        job_id = job_data.get('id')
        command = job_data.get('command')
        
        if not job_id or not command:
            return {
                'success': False,
                'message': 'Job must have "id" and "command" fields'
            }
        
        # Get max_retries from job data or use config default
        max_retries = job_data.get('max_retries', self.config.max_retries)
        
        # Extract metadata (any additional fields)
        metadata = {k: v for k, v in job_data.items() 
                   if k not in ['id', 'command', 'max_retries']}
        
        success = self.storage.enqueue_job(
            job_id=job_id,
            command=command,
            max_retries=max_retries,
            metadata=metadata if metadata else None
        )
        
        if success:
            return {
                'success': True,
                'message': f'Job {job_id} enqueued successfully',
                'job_id': job_id
            }
        else:
            return {
                'success': False,
                'message': f'Job {job_id} already exists'
            }
    
    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get job details by ID"""
        return self.storage.get_job(job_id)
    
    def list_jobs(self, state: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """
        List jobs, optionally filtered by state
        
        Args:
            state: Filter by job state (pending, processing, completed, failed, dlq)
            limit: Maximum number of jobs to return
        
        Returns:
            List of job dictionaries
        """
        return self.storage.list_jobs(state=state, limit=limit)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get queue statistics"""
        job_stats = self.storage.get_job_stats()
        worker_stats = self.storage.list_workers()
        
        return {
            'jobs': job_stats,
            'total_jobs': sum(job_stats.values()),
            'workers': {
                'active': len([w for w in worker_stats if w['status'] == 'active']),
                'total': len(worker_stats)
            }
        }
    
    def retry_job(self, job_id: str) -> Dict[str, Any]:
        """
        Retry a failed or DLQ job
        
        Args:
            job_id: Job ID to retry
        
        Returns:
            Dictionary with success status and message
        """
        job = self.storage.get_job(job_id)
        
        if not job:
            return {
                'success': False,
                'message': f'Job {job_id} not found'
            }
        
        if job['state'] not in [JobState.FAILED, JobState.DLQ]:
            return {
                'success': False,
                'message': f'Job {job_id} is in state "{job["state"]}" and cannot be retried'
            }
        
        # Reset job to pending state
        success = self.storage.update_job_state(
            job_id=job_id,
            state=JobState.PENDING,
            error_message=None,
            worker_id=None
        )
        
        if success:
            return {
                'success': True,
                'message': f'Job {job_id} moved back to pending queue'
            }
        else:
            return {
                'success': False,
                'message': f'Failed to retry job {job_id}'
            }
    
    def handle_job_success(self, job_id: str, worker_id: str) -> bool:
        """Mark job as completed"""
        return self.storage.update_job_state(
            job_id=job_id,
            state=JobState.COMPLETED,
            error_message=None,
            worker_id=worker_id
        )
    
    def handle_job_failure(self, job_id: str, error_message: str, 
                          worker_id: str) -> Dict[str, Any]:
        """
        Handle job failure with retry logic
        
        Returns:
            Dictionary with action taken (retry or dlq)
        """
        job = self.storage.get_job(job_id)
        
        if not job:
            return {'action': 'error', 'message': 'Job not found'}
        
        attempts = job['attempts'] + 1
        max_retries = job['max_retries']
        
        if attempts >= max_retries:
            # Move to DLQ
            self.storage.move_to_dlq(job_id, error_message)
            return {
                'action': 'dlq',
                'message': f'Job {job_id} moved to DLQ after {attempts} attempts'
            }
        else:
            # Schedule retry with exponential backoff
            backoff_delay = self.config.calculate_backoff_delay(attempts)
            next_retry_at = (datetime.utcnow() + timedelta(seconds=backoff_delay)).isoformat()
            
            self.storage.increment_job_attempts(
                job_id=job_id,
                next_retry_at=next_retry_at,
                error_message=error_message
            )
            
            return {
                'action': 'retry',
                'message': f'Job {job_id} will retry in {backoff_delay} seconds',
                'attempts': attempts,
                'max_retries': max_retries,
                'next_retry_at': next_retry_at
            }
    
    def get_dlq_jobs(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get all jobs in Dead Letter Queue"""
        return self.storage.list_jobs(state=JobState.DLQ, limit=limit)
    
    def clear_completed_jobs(self, older_than_days: int = 7) -> int:
        """
        Clear completed jobs older than specified days
        
        Returns:
            Number of jobs cleared
        """
        # This would require additional storage method
        # For now, return 0 as placeholder
        return 0
    
    def close(self):
        """Close storage connection"""
        self.storage.close()
