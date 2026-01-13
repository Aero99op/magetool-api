"""
Auto-Cleanup System - Magetool
Handles automatic cleanup of temporary files
"""

import os
import asyncio
from pathlib import Path
from datetime import datetime, timedelta
import logging
from .locking import get_active_files

logger = logging.getLogger(__name__)

# Configuration
MAX_FILE_AGE_MINUTES = 30  # Delete files older than 30 minutes
MAX_TEMP_SIZE_MB = 5000  # 5GB max temp folder size
CLEANUP_INTERVAL_SECONDS = 600  # Run cleanup every 10 minutes


class CleanupManager:
    """Manages automatic cleanup of temporary files"""
    
    def __init__(self, temp_dir: Path):
        self.temp_dir = temp_dir
        self._running = False
    
    def get_folder_size(self) -> int:
        """Get total size of temp folder in bytes"""
        total = 0
        try:
            for file in self.temp_dir.iterdir():
                if file.is_file():
                    total += file.stat().st_size
        except Exception as e:
            logger.error(f"Error calculating folder size: {e}")
        return total
    
    def get_folder_size_mb(self) -> float:
        """Get total size of temp folder in MB"""
        return self.get_folder_size() / (1024 * 1024)
    
    def cleanup_old_files(self) -> int:
        """Delete files older than MAX_FILE_AGE_MINUTES. Returns count deleted."""
        deleted = 0
        cutoff = datetime.now() - timedelta(minutes=MAX_FILE_AGE_MINUTES)
        
        try:
            for file in self.temp_dir.iterdir():
                if file.is_file() and file.name != '.gitkeep':
                    try:
                        file_time = datetime.fromtimestamp(file.stat().st_mtime)
                        if file_time < cutoff:
                            file.unlink()
                            deleted += 1
                            logger.info(f"🧹 Deleted old file: {file.name}")
                    except Exception as e:
                        logger.error(f"Error deleting {file.name}: {e}")
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
        
        return deleted
    
    def cleanup_for_space(self) -> int:
        """Delete oldest files if folder exceeds MAX_TEMP_SIZE_MB. Returns count deleted."""
        deleted = 0
        total_size = self.get_folder_size()
        max_bytes = MAX_TEMP_SIZE_MB * 1024 * 1024
        
        if total_size <= max_bytes:
            return 0
        
        try:
            # Sort files by modification time (oldest first)
            files = sorted(
                [f for f in self.temp_dir.iterdir() if f.is_file() and f.name != '.gitkeep'],
                key=lambda f: f.stat().st_mtime
            )
            
            # Get currently active files (locked)
            active_files = get_active_files()
            
            for file in files:
                if total_size <= max_bytes:
                    break
                
                # Skip if file is currently active/locked
                if file.name in active_files:
                    logger.debug(f"🔒 Skipping cleanup for locked file: {file.name}")
                    continue
                    
                try:
                    size = file.stat().st_size
                    file.unlink()
                    total_size -= size
                    deleted += 1
                    logger.info(f"🗑️ Deleted for space: {file.name}")
                except Exception as e:
                    logger.error(f"Error deleting {file.name}: {e}")
        except Exception as e:
            logger.error(f"Error during space cleanup: {e}")
        
        return deleted
    
    def run_cleanup(self) -> dict:
        """Run full cleanup cycle"""
        old_deleted = self.cleanup_old_files()
        space_deleted = self.cleanup_for_space()
        
        return {
            "old_files_deleted": old_deleted,
            "space_files_deleted": space_deleted,
            "total_deleted": old_deleted + space_deleted,
            "current_size_mb": self.get_folder_size_mb()
        }
    
    async def start_background_cleanup(self):
        """Start background cleanup task"""
        self._running = True
        logger.info(f"🧹 Cleanup started (every {CLEANUP_INTERVAL_SECONDS}s, max age {MAX_FILE_AGE_MINUTES}min)")
        
        while self._running:
            await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
            result = self.run_cleanup()
            if result["total_deleted"] > 0:
                logger.info(f"🧹 Cleanup: deleted {result['total_deleted']} files, folder now {result['current_size_mb']:.1f}MB")
    
    def stop(self):
        """Stop background cleanup"""
        self._running = False


def delete_file_after_download(temp_dir: Path, filename: str, delay_seconds: int = 60):
    """
    Schedule file deletion after download.
    Call this after user downloads a file.
    """
    async def delayed_delete():
        await asyncio.sleep(delay_seconds)
        file_path = temp_dir / filename
        if file_path.exists():
            try:
                file_path.unlink()
                logger.info(f"🗑️ Deleted after download: {filename}")
            except Exception as e:
                logger.error(f"Error deleting {filename}: {e}")
    
    asyncio.create_task(delayed_delete())


# Singleton instance
_cleanup_manager = None

def get_cleanup_manager(temp_dir: Path) -> CleanupManager:
    """Get or create cleanup manager instance"""
    global _cleanup_manager
    if _cleanup_manager is None:
        _cleanup_manager = CleanupManager(temp_dir)
    return _cleanup_manager
