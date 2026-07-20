"""
Production logging system for CHIDVI 555.

Replaces all print() statements with structured logging.
Supports multiple levels: DEBUG, INFO, WARNING, ERROR.
Can write to console and file.
"""

import logging
import logging.handlers
from pathlib import Path
from datetime import datetime
from typing import Optional
import sys


def _get_base_dir() -> Path:
    """Get the project root directory."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR = _get_base_dir()
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)


class ColoredFormatter(logging.Formatter):
    """Custom formatter with colors for console output."""
    
    # ANSI color codes
    COLORS = {
        'DEBUG': '\033[36m',      # Cyan
        'INFO': '\033[32m',       # Green
        'WARNING': '\033[33m',    # Yellow
        'ERROR': '\033[31m',      # Red
        'CRITICAL': '\033[41m',   # Red background
        'RESET': '\033[0m',
    }
    
    def format(self, record):
        levelname = record.levelname
        if sys.platform == 'win32':
            # Windows doesn't support ANSI colors well, use simpler format
            formatted = super().format(record)
        else:
            color = self.COLORS.get(levelname, self.COLORS['RESET'])
            reset = self.COLORS['RESET']
            
            # Format with color
            record.levelname = f"{color}{levelname}{reset}"
            formatted = super().format(record)
            record.levelname = levelname  # Restore original
        
        return formatted


class LoggerManager:
    """
    Centralized logging manager.
    
    Provides configured loggers for all modules.
    Handles file and console output.
    """
    
    _instance = None
    _loggers = {}
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(LoggerManager, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._setup_logging()
    
    def _setup_logging(self, debug: bool = False):
        """Set up the logging system."""
        level = logging.DEBUG if debug else logging.INFO
        
        # Root logger configuration
        root_logger = logging.getLogger()
        root_logger.setLevel(level)
        
        # Remove any existing handlers
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
        
        # Console handler (always INFO and above for console)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO if not debug else logging.DEBUG)
        console_formatter = ColoredFormatter(
            '[%(asctime)s] %(levelname)-8s %(name)s: %(message)s',
            datefmt='%H:%M:%S'
        )
        console_handler.setFormatter(console_formatter)
        root_logger.addHandler(console_handler)
        
        # File handler (all levels)
        log_file = LOG_DIR / f"chidvi_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setLevel(level)
        file_formatter = logging.Formatter(
            '[%(asctime)s] %(levelname)-8s %(name)s:%(lineno)d: %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)
        
        # Suppress noisy third-party loggers
        logging.getLogger('urllib3').setLevel(logging.WARNING)
        logging.getLogger('asyncio').setLevel(logging.WARNING)
        logging.getLogger('google').setLevel(logging.WARNING)
    
    def get_logger(self, name: str) -> logging.Logger:
        """Get or create a logger."""
        if name not in self._loggers:
            self._loggers[name] = logging.getLogger(name)
        return self._loggers[name]


# Global instance
logger_manager = LoggerManager()


def get_logger(name: str) -> logging.Logger:
    """Get a logger for a module."""
    return logger_manager.get_logger(name)
