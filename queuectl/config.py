"""
Configuration management for QueueCTL
Handles retry policies, backoff settings, and system configuration
"""

import json
import os
from typing import Dict, Any, Optional


class Config:
    """Configuration manager for QueueCTL"""
    
    # Default configuration
    DEFAULTS = {
        "max_retries": 3,
        "backoff_base": 2,
        "backoff_max_delay": 3600,  # 1 hour max
        "worker_poll_interval": 1,  # seconds
        "worker_heartbeat_interval": 5,  # seconds
        "job_timeout": 300,  # 5 minutes default timeout
        "db_path": "queuectl.db",
        "log_level": "INFO"
    }
    
    def __init__(self, config_file: str = "queuectl.config.json"):
        """Initialize configuration"""
        self.config_file = config_file
        self.config = self._load_config()
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from file or use defaults"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    user_config = json.load(f)
                    # Merge with defaults
                    config = self.DEFAULTS.copy()
                    config.update(user_config)
                    return config
            except (json.JSONDecodeError, IOError):
                # If config file is corrupted, use defaults
                return self.DEFAULTS.copy()
        return self.DEFAULTS.copy()
    
    def _save_config(self) -> bool:
        """Save configuration to file"""
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=2)
            return True
        except IOError:
            return False
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value"""
        return self.config.get(key, default)
    
    def set(self, key: str, value: Any) -> bool:
        """Set configuration value and persist"""
        # Validate certain keys
        if key in ["max_retries", "backoff_base", "worker_poll_interval", 
                   "worker_heartbeat_interval", "job_timeout", "backoff_max_delay"]:
            try:
                value = int(value) if not isinstance(value, int) else value
                if value < 0:
                    raise ValueError("Value must be non-negative")
            except (ValueError, TypeError):
                return False
        
        self.config[key] = value
        return self._save_config()
    
    def get_all(self) -> Dict[str, Any]:
        """Get all configuration values"""
        return self.config.copy()
    
    def reset(self, key: Optional[str] = None) -> bool:
        """Reset configuration to defaults"""
        if key:
            if key in self.DEFAULTS:
                self.config[key] = self.DEFAULTS[key]
                return self._save_config()
            return False
        else:
            self.config = self.DEFAULTS.copy()
            return self._save_config()
    
    def calculate_backoff_delay(self, attempts: int) -> int:
        """Calculate exponential backoff delay in seconds"""
        base = self.get("backoff_base", 2)
        max_delay = self.get("backoff_max_delay", 3600)
        
        delay = base ** attempts
        return min(delay, max_delay)
    
    @property
    def max_retries(self) -> int:
        """Get max retries setting"""
        return self.get("max_retries", 3)
    
    @property
    def db_path(self) -> str:
        """Get database path"""
        return self.get("db_path", "queuectl.db")
    
    @property
    def worker_poll_interval(self) -> int:
        """Get worker poll interval"""
        return self.get("worker_poll_interval", 1)
    
    @property
    def worker_heartbeat_interval(self) -> int:
        """Get worker heartbeat interval"""
        return self.get("worker_heartbeat_interval", 5)
    
    @property
    def job_timeout(self) -> int:
        """Get job timeout"""
        return self.get("job_timeout", 300)


# Global config instance
_config_instance = None


def get_config() -> Config:
    """Get global config instance"""
    global _config_instance
    if _config_instance is None:
        _config_instance = Config()
    return _config_instance
