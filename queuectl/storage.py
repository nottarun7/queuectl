"""
Storage layer for QueueCTL using SQLite
Handles job persistence, state management, and database operations
"""

import sqlite3
import json
import threading
from datetime import datetime
from typing import List, Dict, Optional, Any
from contextlib import contextmanager
import os


class JobState:
    """Job state constants"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    DLQ = "dlq"


class Storage:
    """SQLite-based storage for job queue"""
    
    def __init__(self, db_path: str = "queuectl.db"):
        """Initialize storage with database path"""
        self.db_path = db_path
        self.local = threading.local()
        self._init_db()
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get thread-local database connection"""
        if not hasattr(self.local, 'conn'):
            self.local.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self.local.conn.row_factory = sqlite3.Row
        return self.local.conn
    
    @contextmanager
    def _get_cursor(self):
        """Context manager for database cursor"""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            yield cursor
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            cursor.close()
    
    def _init_db(self):
        """Initialize database schema"""
        with self._get_cursor() as cursor:
            # Jobs table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    command TEXT NOT NULL,
                    state TEXT NOT NULL,
                    attempts INTEGER DEFAULT 0,
                    max_retries INTEGER DEFAULT 3,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    next_retry_at TEXT,
                    error_message TEXT,
                    worker_id TEXT,
                    metadata TEXT
                )
            """)
            
            # Create indices for common queries
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_jobs_state 
                ON jobs(state)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_jobs_next_retry 
                ON jobs(next_retry_at)
            """)
            
            # Worker tracking table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS workers (
                    worker_id TEXT PRIMARY KEY,
                    pid INTEGER NOT NULL,
                    started_at TEXT NOT NULL,
                    last_heartbeat TEXT NOT NULL,
                    status TEXT NOT NULL
                )
            """)
    
    def enqueue_job(self, job_id: str, command: str, max_retries: int = 3, 
                    metadata: Optional[Dict] = None) -> bool:
        """Add a new job to the queue"""
        now = datetime.utcnow().isoformat()
        metadata_json = json.dumps(metadata) if metadata else None
        
        try:
            with self._get_cursor() as cursor:
                cursor.execute("""
                    INSERT INTO jobs (
                        id, command, state, attempts, max_retries,
                        created_at, updated_at, metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    job_id, command, JobState.PENDING, 0, max_retries,
                    now, now, metadata_json
                ))
            return True
        except sqlite3.IntegrityError:
            return False  # Job already exists
    
    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get job by ID"""
        with self._get_cursor() as cursor:
            cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
            row = cursor.fetchone()
            if row:
                return self._row_to_dict(row)
        return None
    
    def get_next_pending_job(self, worker_id: str) -> Optional[Dict[str, Any]]:
        """Get next pending job and mark it as processing"""
        now = datetime.utcnow().isoformat()
        
        with self._get_cursor() as cursor:
            # Find pending jobs or failed jobs ready for retry
            cursor.execute("""
                SELECT * FROM jobs 
                WHERE (state = ? OR (state = ? AND next_retry_at <= ?))
                AND (worker_id IS NULL OR worker_id = '')
                ORDER BY created_at ASC
                LIMIT 1
            """, (JobState.PENDING, JobState.FAILED, now))
            
            row = cursor.fetchone()
            if not row:
                return None
            
            job = self._row_to_dict(row)
            
            # Mark as processing
            cursor.execute("""
                UPDATE jobs 
                SET state = ?, worker_id = ?, started_at = ?, updated_at = ?
                WHERE id = ? AND (worker_id IS NULL OR worker_id = '')
            """, (JobState.PROCESSING, worker_id, now, now, job['id']))
            
            # Check if update was successful (no race condition)
            if cursor.rowcount > 0:
                job['state'] = JobState.PROCESSING
                job['worker_id'] = worker_id
                return job
            
        return None
    
    def update_job_state(self, job_id: str, state: str, error_message: Optional[str] = None,
                        worker_id: Optional[str] = None) -> bool:
        """Update job state"""
        now = datetime.utcnow().isoformat()
        
        with self._get_cursor() as cursor:
            if state == JobState.COMPLETED:
                cursor.execute("""
                    UPDATE jobs 
                    SET state = ?, completed_at = ?, updated_at = ?, error_message = ?
                    WHERE id = ?
                """, (state, now, now, error_message, job_id))
            else:
                cursor.execute("""
                    UPDATE jobs 
                    SET state = ?, updated_at = ?, error_message = ?, worker_id = ?
                    WHERE id = ?
                """, (state, now, error_message, worker_id or '', job_id))
            
            return cursor.rowcount > 0
    
    def increment_job_attempts(self, job_id: str, next_retry_at: str, 
                              error_message: Optional[str] = None) -> bool:
        """Increment job attempt count and schedule retry"""
        now = datetime.utcnow().isoformat()
        
        with self._get_cursor() as cursor:
            cursor.execute("""
                UPDATE jobs 
                SET attempts = attempts + 1, 
                    next_retry_at = ?,
                    updated_at = ?,
                    error_message = ?,
                    worker_id = '',
                    state = ?
                WHERE id = ?
            """, (next_retry_at, now, error_message, JobState.FAILED, job_id))
            
            return cursor.rowcount > 0
    
    def move_to_dlq(self, job_id: str, error_message: Optional[str] = None) -> bool:
        """Move job to Dead Letter Queue"""
        now = datetime.utcnow().isoformat()
        
        with self._get_cursor() as cursor:
            cursor.execute("""
                UPDATE jobs 
                SET state = ?, updated_at = ?, error_message = ?, worker_id = ''
                WHERE id = ?
            """, (JobState.DLQ, now, error_message, job_id))
            
            return cursor.rowcount > 0
    
    def list_jobs(self, state: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """List jobs, optionally filtered by state"""
        with self._get_cursor() as cursor:
            if state:
                cursor.execute("""
                    SELECT * FROM jobs 
                    WHERE state = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                """, (state, limit))
            else:
                cursor.execute("""
                    SELECT * FROM jobs 
                    ORDER BY created_at DESC
                    LIMIT ?
                """, (limit,))
            
            return [self._row_to_dict(row) for row in cursor.fetchall()]
    
    def get_job_stats(self) -> Dict[str, int]:
        """Get job statistics by state"""
        with self._get_cursor() as cursor:
            cursor.execute("""
                SELECT state, COUNT(*) as count 
                FROM jobs 
                GROUP BY state
            """)
            
            stats = {
                JobState.PENDING: 0,
                JobState.PROCESSING: 0,
                JobState.COMPLETED: 0,
                JobState.FAILED: 0,
                JobState.DLQ: 0
            }
            
            for row in cursor.fetchall():
                stats[row['state']] = row['count']
            
            return stats
    
    def register_worker(self, worker_id: str, pid: int) -> bool:
        """Register a worker"""
        now = datetime.utcnow().isoformat()
        
        try:
            with self._get_cursor() as cursor:
                cursor.execute("""
                    INSERT OR REPLACE INTO workers (
                        worker_id, pid, started_at, last_heartbeat, status
                    ) VALUES (?, ?, ?, ?, ?)
                """, (worker_id, pid, now, now, "active"))
            return True
        except Exception:
            return False
    
    def update_worker_heartbeat(self, worker_id: str) -> bool:
        """Update worker heartbeat"""
        now = datetime.utcnow().isoformat()
        
        with self._get_cursor() as cursor:
            cursor.execute("""
                UPDATE workers 
                SET last_heartbeat = ?
                WHERE worker_id = ?
            """, (now, worker_id))
            
            return cursor.rowcount > 0
    
    def deregister_worker(self, worker_id: str) -> bool:
        """Deregister a worker"""
        with self._get_cursor() as cursor:
            # Release jobs held by this worker
            cursor.execute("""
                UPDATE jobs 
                SET worker_id = '', state = ?
                WHERE worker_id = ? AND state = ?
            """, (JobState.PENDING, worker_id, JobState.PROCESSING))
            
            # Remove worker
            cursor.execute("DELETE FROM workers WHERE worker_id = ?", (worker_id,))
            
            return True
    
    def list_workers(self) -> List[Dict[str, Any]]:
        """List all registered workers"""
        with self._get_cursor() as cursor:
            cursor.execute("SELECT * FROM workers ORDER BY started_at ASC")
            return [self._row_to_dict(row) for row in cursor.fetchall()]
    
    def _row_to_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        """Convert SQLite row to dictionary"""
        d = dict(row)
        # Parse JSON metadata if present
        if 'metadata' in d and d['metadata']:
            try:
                d['metadata'] = json.loads(d['metadata'])
            except json.JSONDecodeError:
                d['metadata'] = None
        return d
    
    def close(self):
        """Close database connection"""
        if hasattr(self.local, 'conn'):
            self.local.conn.close()
            delattr(self.local, 'conn')
