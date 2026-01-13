"""
File Locking Utility - Magetool
Manages active file locks - Uses Redis if available, otherwise in-memory
"""

import os
import logging
from typing import Set

logger = logging.getLogger(__name__)

# Try to import redis, fallback to in-memory if not available
try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logger.warning("Redis not available - using in-memory locking")

# Redis Configuration - Prioritize REDIS_URL (Upstash) over CELERY_BROKER_URL
REDIS_URL = os.getenv('REDIS_URL') or os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0')
LOCK_PREFIX = "magetool:lock:"
LOCK_TTL = 7200  # 2 hours

# In-memory fallback storage
_memory_locks: Set[str] = set()

# Initialize Redis client (if available)
redis_client = None
if REDIS_AVAILABLE:
    try:
        redis_client = redis.from_url(REDIS_URL, decode_responses=True)
        redis_client.ping()  # Test connection
        logger.info("✅ Redis connected for file locking")
    except Exception as e:
        logger.warning(f"⚠️ Redis not available, using in-memory locking: {e}")
        redis_client = None

def add_active_file(filename: str) -> bool:
    """Mark a file as 'active' (in use/downloading)."""
    global _memory_locks
    
    if redis_client:
        try:
            key = f"{LOCK_PREFIX}{filename}"
            redis_client.set(key, "1", ex=LOCK_TTL)
            logger.debug(f"🔒 Locked file (Redis): {filename}")
            return True
        except Exception as e:
            logger.error(f"Redis lock error: {e}")
    
    # Fallback to in-memory
    _memory_locks.add(filename)
    logger.debug(f"🔒 Locked file (memory): {filename}")
    return True

def remove_active_file(filename: str) -> bool:
    """Remove the 'active' lock from a file."""
    global _memory_locks
    
    if redis_client:
        try:
            key = f"{LOCK_PREFIX}{filename}"
            redis_client.delete(key)
            logger.debug(f"🔓 Unlocked file (Redis): {filename}")
            return True
        except Exception as e:
            logger.error(f"Redis unlock error: {e}")
    
    # Fallback to in-memory
    _memory_locks.discard(filename)
    logger.debug(f"🔓 Unlocked file (memory): {filename}")
    return True

def get_active_files() -> Set[str]:
    """Get set of all currently active filenames."""
    global _memory_locks
    
    if redis_client:
        try:
            active_files = set()
            pattern = f"{LOCK_PREFIX}*"
            for key in redis_client.scan_iter(match=pattern):
                filename = key.replace(LOCK_PREFIX, "", 1)
                active_files.add(filename)
            return active_files
        except Exception as e:
            logger.error(f"Redis scan error: {e}")
    
    # Fallback to in-memory
    return _memory_locks.copy()

