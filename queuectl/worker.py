"""
Worker process management for QueueCTL
Handles job execution, retry logic, and graceful shutdown
"""

import time
import signal
import sys
import os
import multiprocessing
from typing import Optional
import logging

from .storage import Storage, JobState
from .queue import Queue
from .config import get_config
from .utils import execute_command, setup_logging, save_worker_pids


class Worker:
    """Worker process for executing jobs"""
    
    def __init__(self, worker_id: str, queue: Optional[Queue] = None):
        """Initialize worker"""
        self.worker_id = worker_id
        self.config = get_config()
        self.queue = queue or Queue()
        self.storage = self.queue.storage
        self.running = True
        self.logger = setup_logging(self.config.get("log_level", "INFO"))
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        self.logger.info(f"Worker {self.worker_id} received shutdown signal")
        self.running = False
    
    def start(self, exit_on_idle: bool = False, max_idle_seconds: int = 10):
        """Start worker loop

        Args:
            exit_on_idle: if True, exit the worker when the queue stays empty
                for `max_idle_seconds` seconds.
            max_idle_seconds: maximum seconds of idle time before exiting when
                exit_on_idle is True.
        """
        pid = os.getpid()
        self.logger.info(f"Worker {self.worker_id} started (PID: {pid})")
        
        # Register worker
        self.storage.register_worker(self.worker_id, pid)
        
        last_heartbeat = time.time()
        poll_interval = self.config.worker_poll_interval
        heartbeat_interval = self.config.worker_heartbeat_interval
        idle_start = None
        
        try:
            while self.running:
                # Update heartbeat periodically
                current_time = time.time()
                if current_time - last_heartbeat >= heartbeat_interval:
                    self.storage.update_worker_heartbeat(self.worker_id)
                    last_heartbeat = current_time
                
                # Get next job
                job = self.storage.get_next_pending_job(self.worker_id)
                
                if job:
                    # Reset idle timer when work is found
                    idle_start = None
                    self._process_job(job)
                else:
                    # No jobs available, consider exiting if requested
                    if exit_on_idle:
                        if idle_start is None:
                            idle_start = time.time()
                        else:
                            idle_time = time.time() - idle_start
                            # Check actual pending jobs count to avoid racey exits
                            try:
                                stats = self.storage.get_job_stats()
                                pending = stats.get(JobState.PENDING, 0)
                            except Exception:
                                pending = 0

                            if pending == 0 and idle_time >= max_idle_seconds:
                                self.logger.info(
                                    f"Worker {self.worker_id} exiting after {int(idle_time)}s idle"
                                )
                                break

                    # Sleep briefly before next poll
                    time.sleep(poll_interval)
        
        except Exception as e:
            self.logger.error(f"Worker {self.worker_id} encountered error: {str(e)}")
        
        finally:
            # Cleanup
            self.logger.info(f"Worker {self.worker_id} shutting down")
            self.storage.deregister_worker(self.worker_id)
            self.queue.close()
    
    def _process_job(self, job: dict):
        """Process a single job"""
        job_id = job['id']
        command = job['command']
        
        self.logger.info(f"Worker {self.worker_id} processing job {job_id}: {command}")
        
        # Execute command
        timeout = self.config.job_timeout
        exit_code, stdout, stderr = execute_command(command, timeout=timeout)
        
        if exit_code == 0:
            # Job succeeded
            self.logger.info(f"Job {job_id} completed successfully")
            self.queue.handle_job_success(job_id, self.worker_id)
        else:
            # Job failed
            error_message = f"Exit code {exit_code}: {stderr[:500]}"
            self.logger.warning(f"Job {job_id} failed: {error_message}")
            
            result = self.queue.handle_job_failure(
                job_id=job_id,
                error_message=error_message,
                worker_id=self.worker_id
            )
            
            self.logger.info(f"Job {job_id}: {result['message']}")


class WorkerManager:
    """Manages multiple worker processes"""
    
    def __init__(self):
        """Initialize worker manager"""
        self.config = get_config()
        self.logger = setup_logging(self.config.get("log_level", "INFO"))
        self.processes = []
    
    def start_workers(self, count: int = 1) -> dict:
        """
        Start multiple worker processes
        
        Args:
            count: Number of workers to start
        
        Returns:
            Dictionary with success status and worker info
        """
        if count < 1:
            return {
                'success': False,
                'message': 'Worker count must be at least 1'
            }
        
        self.logger.info(f"Starting {count} worker(s)")
        
        pids = []
        for i in range(count):
            worker_id = f"worker-{i+1}-{int(time.time())}"
            
            # Create worker process as daemon so parent can exit immediately
            process = multiprocessing.Process(
                target=self._run_worker,
                args=(worker_id,),
                daemon=True  # Allow parent to exit without waiting
            )
            process.start()
            
            # Don't keep reference to process object to allow it to run independently
            pids.append(process.pid)
            
            self.logger.info(f"Started worker {worker_id} (PID: {process.pid})")
        
        # Save PIDs to file for later stop command
        save_worker_pids(pids)
        
        # Return immediately without joining processes
        return {
            'success': True,
            'message': f'Started {count} worker(s)',
            'pids': pids
        }
    
    def _run_worker(self, worker_id: str, exit_on_idle: bool = False, max_idle_seconds: int = 10):
        """Run worker in separate process"""
        worker = Worker(worker_id)
        worker.start(exit_on_idle=exit_on_idle, max_idle_seconds=max_idle_seconds)
    
    def stop_workers(self) -> dict:
        """
        Stop all running workers gracefully
        
        Returns:
            Dictionary with success status and stopped worker count
        """
        from .utils import load_worker_pids, is_process_running, terminate_process, clear_worker_pids
        
        pids = load_worker_pids()
        
        if not pids:
            return {
                'success': True,
                'message': 'No workers to stop',
                'stopped': 0
            }
        
        self.logger.info(f"Stopping {len(pids)} worker(s)")
        
        stopped = 0
        for pid in pids:
            if is_process_running(pid):
                self.logger.info(f"Stopping worker PID {pid}")
                if terminate_process(pid, timeout=10):
                    stopped += 1
                    self.logger.info(f"Worker PID {pid} stopped")
                else:
                    self.logger.warning(f"Failed to stop worker PID {pid}")
            else:
                self.logger.info(f"Worker PID {pid} not running")
        
        # Clear PID file
        clear_worker_pids()
        
        return {
            'success': True,
            'message': f'Stopped {stopped} worker(s)',
            'stopped': stopped
        }
    
    def get_worker_status(self) -> dict:
        """
        Get status of all workers
        
        Returns:
            Dictionary with worker status information
        """
        from .utils import load_worker_pids, is_process_running
        
        pids = load_worker_pids()
        storage = Storage(self.config.db_path)
        
        try:
            workers_db = storage.list_workers()
            
            active_pids = [pid for pid in pids if is_process_running(pid)]
            
            return {
                'registered_workers': len(workers_db),
                'tracked_pids': len(pids),
                'active_pids': len(active_pids),
                'workers': workers_db,
                'pids': active_pids
            }
        finally:
            storage.close()


def worker_main():
    """Entry point for starting workers from CLI"""
    if len(sys.argv) < 2:
        print("Usage: worker_main <worker_id>")
        sys.exit(1)
    
    worker_id = sys.argv[1]
    worker = Worker(worker_id)
    worker.start()


if __name__ == "__main__":
    worker_main()
