"""
API key pool manager for CHIDVI 555.

Handles:
- Multiple API keys
- Automatic key rotation
- Rate limit detection
- Health monitoring
- Transparent retry
- Failed key recovery

Ensures the assistant never shows rate limit errors to the user.
"""

from typing import List, Optional
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import threading
import time
from core.logging import get_logger
from core.event_bus import publish_event, EventType
from core.config import config

logger = get_logger(__name__)


class KeyStatus(Enum):
    """Status of an API key."""
    HEALTHY = "healthy"
    RATE_LIMITED = "rate_limited"
    FAILED = "failed"
    UNKNOWN = "unknown"


@dataclass
class APIKeyEntry:
    """Entry for an API key with metadata."""
    
    key: str
    status: KeyStatus = KeyStatus.UNKNOWN
    last_used: Optional[datetime] = None
    last_error: Optional[str] = None
    error_count: int = 0
    rate_limit_until: Optional[datetime] = None
    healthy_count: int = 0
    
    def is_available(self) -> bool:
        """Check if key is available for use."""
        if self.status == KeyStatus.HEALTHY:
            return True
        
        if self.status == KeyStatus.RATE_LIMITED:
            if self.rate_limit_until and datetime.now() > self.rate_limit_until:
                self.status = KeyStatus.HEALTHY
                logger.info(f"Key recovered from rate limit: {self.key[:10]}...")
                return True
            return False
        
        return False
    
    def mark_used(self):
        """Mark key as recently used."""
        self.last_used = datetime.now()
        self.status = KeyStatus.HEALTHY
        self.healthy_count += 1
        self.error_count = 0
    
    def mark_rate_limited(self, cooldown_minutes: int = 60):
        """Mark key as rate limited."""
        self.status = KeyStatus.RATE_LIMITED
        self.rate_limit_until = datetime.now() + timedelta(minutes=cooldown_minutes)
        self.error_count += 1
        logger.warning(
            f"Key rate limited: {self.key[:10]}... "
            f"(recovered at {self.rate_limit_until.strftime('%H:%M:%S')})"
        )
    
    def mark_failed(self, error: str):
        """Mark key as failed."""
        self.status = KeyStatus.FAILED
        self.last_error = error
        self.error_count += 1
        logger.warning(f"Key marked as failed: {self.key[:10]}... ({error})")


class APIKeyPool:
    """
    Manages a pool of API keys with automatic rotation.
    
    BEHAVIOR:
    - Maintains health status for each key
    - Automatically rotates through healthy keys
    - Detects rate limits and applies cooldown
    - Recovers failed keys after cooldown
    - Never exposes rate limit errors to user
    """
    
    def __init__(self, keys: List[str] = None):
        self._keys: List[APIKeyEntry] = []
        self._current_index = 0
        self._lock = threading.RLock()
        self._rotation_count = 0
        
        if keys is None:
            keys = config.get("api.gemini_keys", [])
        
        self._load_keys(keys)
    
    def _load_keys(self, keys: List[str]):
        """Load keys into the pool."""
        if not keys:
            logger.warning("No API keys configured")
            return
        
        # Remove duplicates and empty keys
        unique_keys = [k.strip() for k in set(keys) if k and k.strip()]
        
        for key in unique_keys:
            self._keys.append(APIKeyEntry(key=key))
        
        logger.info(f"Loaded {len(self._keys)} API keys")
    
    def get_next_key(self) -> Optional[str]:
        """
        Get the next available API key.
        
        Automatically rotates through healthy keys.
        Skips rate-limited keys.
        Returns None if no keys are available.
        """
        with self._lock:
            if not self._keys:
                logger.error("No API keys available")
                return None
            
            # Try to find a healthy key
            attempts = 0
            max_attempts = len(self._keys) * 2
            
            while attempts < max_attempts:
                entry = self._keys[self._current_index]
                self._current_index = (self._current_index + 1) % len(self._keys)
                attempts += 1
                
                if entry.is_available():
                    logger.debug(f"Using key: {entry.key[:10]}...")
                    return entry.key
            
            # If no healthy keys found, return the one with fewest errors
            logger.warning("All keys unavailable, using least-failed key")
            best_entry = min(self._keys, key=lambda e: e.error_count)
            return best_entry.key
    
    def mark_success(self, key: str):
        """Mark a key as successfully used."""
        with self._lock:
            for entry in self._keys:
                if entry.key == key:
                    entry.mark_used()
                    logger.debug(f"Key marked successful: {key[:10]}...")
                    
                    # Publish event
                    publish_event(EventType.GEMINI_API_ERROR, {
                        "type": "success",
                        "key_index": self._keys.index(entry),
                    }, async_mode=False)
                    break
    
    def mark_rate_limit(self, key: str, cooldown_minutes: int = 60):
        """Mark a key as rate limited."""
        with self._lock:
            for entry in self._keys:
                if entry.key == key:
                    entry.mark_rate_limited(cooldown_minutes)
                    
                    # Publish rotation event
                    publish_event(EventType.GEMINI_KEY_ROTATED, {
                        "reason": "rate_limit",
                        "key_index": self._keys.index(entry),
                        "next_key_available": self.get_next_key() is not None,
                    })
                    break
    
    def mark_failed(self, key: str, error: str):
        """Mark a key as failed."""
        with self._lock:
            for entry in self._keys:
                if entry.key == key:
                    entry.mark_failed(error)
                    
                    # Publish event
                    publish_event(EventType.GEMINI_API_ERROR, {
                        "type": "failed",
                        "error": error,
                        "key_index": self._keys.index(entry),
                    })
                    break
    
    def get_stats(self) -> dict:
        """Get pool statistics."""
        with self._lock:
            healthy = sum(1 for k in self._keys if k.status == KeyStatus.HEALTHY)
            rate_limited = sum(1 for k in self._keys if k.status == KeyStatus.RATE_LIMITED)
            failed = sum(1 for k in self._keys if k.status == KeyStatus.FAILED)
            
            return {
                "total_keys": len(self._keys),
                "healthy": healthy,
                "rate_limited": rate_limited,
                "failed": failed,
                "rotation_count": self._rotation_count,
                "keys": [
                    {
                        "key": f"{k.key[:10]}...",
                        "status": k.status.value,
                        "errors": k.error_count,
                        "last_used": k.last_used.isoformat() if k.last_used else None,
                    }
                    for k in self._keys
                ]
            }
    
    def reset_key(self, key: str):
        """Reset a failed key to unknown status."""
        with self._lock:
            for entry in self._keys:
                if entry.key == key:
                    entry.status = KeyStatus.UNKNOWN
                    entry.error_count = 0
                    logger.info(f"Reset key: {key[:10]}...")
                    break
    
    def add_key(self, key: str):
        """Add a new key to the pool (e.g., from config reload)."""
        with self._lock:
            # Check if already exists
            if any(e.key == key for e in self._keys):
                return
            
            self._keys.append(APIKeyEntry(key=key))
            logger.info(f"Added new key to pool: {key[:10]}...")


# Global pool instance
_pool: Optional[APIKeyPool] = None
_pool_lock = threading.Lock()


def get_api_key_pool() -> APIKeyPool:
    """Get the global API key pool."""
    global _pool
    
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                _pool = APIKeyPool()
    
    return _pool


# Convenience functions
def get_next_api_key() -> Optional[str]:
    """Get the next available API key."""
    return get_api_key_pool().get_next_key()


def mark_api_key_success(key: str):
    """Mark an API key as successfully used."""
    get_api_key_pool().mark_success(key)


def mark_api_key_rate_limited(key: str, cooldown_minutes: int = 60):
    """Mark an API key as rate limited."""
    get_api_key_pool().mark_rate_limit(key, cooldown_minutes)


def mark_api_key_failed(key: str, error: str):
    """Mark an API key as failed."""
    get_api_key_pool().mark_failed(key, error)


def get_api_pool_stats() -> dict:
    """Get API key pool statistics."""
    return get_api_key_pool().get_stats()
