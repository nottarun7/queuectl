"""
Utility functions for QueueCTL
Helper functions for command execution, logging, and common operations
"""

import subprocess
import logging
import os
import signal
from typing import Tuple, Optional
from datetime import datetime


def setup_logging(log_level: str = "INFO") -> logging.Logger:
    """Setup logging configuration"""
    logger = logging.getLogger("queuectl")
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    
    # Console handler
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    
    return logger


def execute_command(command: str, timeout: int = 300) -> Tuple[int, str, str]:
    """
    Execute a shell command and return exit code, stdout, stderr
    
    Args:
        command: Shell command to execute
        timeout: Command timeout in seconds
    
    Returns:
        Tuple of (exit_code, stdout, stderr)
    """
    logger = logging.getLogger("queuectl")
    
    try:
        # Execute command in shell
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        
        return (result.returncode, result.stdout, result.stderr)
        
    except subprocess.TimeoutExpired:
        logger.error(f"Command timed out after {timeout} seconds: {command}")
        return (-1, "", f"Command timed out after {timeout} seconds")
    
    except Exception as e:
        logger.error(f"Error executing command: {command} - {str(e)}")
        return (-1, "", str(e))


def format_datetime(dt_string: Optional[str]) -> str:
    """Format ISO datetime string to readable format"""
    if not dt_string:
        return "N/A"
    
    try:
        dt = datetime.fromisoformat(dt_string)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, AttributeError):
        return dt_string


def format_duration(start: Optional[str], end: Optional[str]) -> str:
    """Calculate and format duration between two ISO datetime strings"""
    if not start or not end:
        return "N/A"
    
    try:
        start_dt = datetime.fromisoformat(start)
        end_dt = datetime.fromisoformat(end)
        duration = end_dt - start_dt
        
        total_seconds = int(duration.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        if hours > 0:
            return f"{hours}h {minutes}m {seconds}s"
        elif minutes > 0:
            return f"{minutes}m {seconds}s"
        else:
            return f"{seconds}s"
    except (ValueError, AttributeError):
        return "N/A"


def get_pid_file() -> str:
    """Get path to PID file for worker processes"""
    return "workers.pid"


def save_worker_pids(pids: list):
    """Save worker PIDs to file"""
    pid_file = get_pid_file()
    with open(pid_file, 'w') as f:
        f.write('\n'.join(map(str, pids)))


def load_worker_pids() -> list:
    """Load worker PIDs from file"""
    pid_file = get_pid_file()
    if not os.path.exists(pid_file):
        return []
    
    try:
        with open(pid_file, 'r') as f:
            pids = [int(line.strip()) for line in f if line.strip()]
        return pids
    except (ValueError, IOError):
        return []


def clear_worker_pids():
    """Clear worker PID file"""
    pid_file = get_pid_file()
    if os.path.exists(pid_file):
        os.remove(pid_file)


def is_process_running(pid: int) -> bool:
    """Check if a process is running"""
    try:
        # On Windows, use a different approach
        if os.name == 'nt':
            # Windows: Try to open the process
            import ctypes
            kernel32 = ctypes.windll.kernel32
            PROCESS_QUERY_INFORMATION = 0x0400
            handle = kernel32.OpenProcess(PROCESS_QUERY_INFORMATION, False, pid)
            if handle:
                kernel32.CloseHandle(handle)
                return True
            return False
        else:
            # Unix: send signal 0
            os.kill(pid, 0)
            return True
    except (OSError, AttributeError):
        return False


def terminate_process(pid: int, timeout: int = 5) -> bool:
    """
    Terminate a process gracefully, with force kill as fallback
    
    Args:
        pid: Process ID to terminate
        timeout: Seconds to wait before force kill
    
    Returns:
        True if process was terminated
    """
    if not is_process_running(pid):
        return True
    
    try:
        if os.name == 'nt':
            # Windows: Use taskkill
            subprocess.run(['taskkill', '/F', '/PID', str(pid)], 
                         capture_output=True)
        else:
            # Unix: Send SIGTERM, then SIGKILL if needed
            os.kill(pid, signal.SIGTERM)
            
            # Wait for process to terminate
            import time
            for _ in range(timeout * 10):
                if not is_process_running(pid):
                    return True
                time.sleep(0.1)
            
            # Force kill if still running
            os.kill(pid, signal.SIGKILL)
        
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def truncate_string(s: str, max_length: int = 50) -> str:
    """Truncate string to max length with ellipsis"""
    if len(s) <= max_length:
        return s
    return s[:max_length-3] + "..."


def validate_job_data(job_data: dict) -> Tuple[bool, Optional[str]]:
    """
    Validate job data structure
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not isinstance(job_data, dict):
        return False, "Job data must be a dictionary"
    
    if 'id' not in job_data:
        return False, "Job data must contain 'id' field"
    
    if 'command' not in job_data:
        return False, "Job data must contain 'command' field"
    
    if not isinstance(job_data['id'], str) or not job_data['id']:
        return False, "Job 'id' must be a non-empty string"
    
    if not isinstance(job_data['command'], str) or not job_data['command']:
        return False, "Job 'command' must be a non-empty string"
    
    return True, None
