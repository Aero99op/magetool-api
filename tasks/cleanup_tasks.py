"""
Cleanup Tasks - Celery Beat scheduled tasks for auto-cleanup
"""

from celery_app import celery_app
from utils.cleanup import get_cleanup_manager
from pathlib import Path
import logging

logger = logging.getLogger(__name__)
TEMP_DIR = Path("./temp")


@celery_app.task(name='tasks.cleanup_tasks.cleanup_old_files')
def cleanup_old_files():
    """Scheduled task to clean old files (runs every 10 minutes via Beat)"""
    try:
        cleanup_manager = get_cleanup_manager(TEMP_DIR)
        result = cleanup_manager.run_cleanup()
        
        if result['total_deleted'] > 0:
            logger.info(f"🧹 Cleanup: deleted {result['total_deleted']} files, folder now {result['current_size_mb']:.1f}MB")
        
        return result
    except Exception as e:
        logger.error(f"Cleanup task failed: {e}")
        return {'error': str(e)}


@celery_app.task(name='tasks.cleanup_tasks.cleanup_specific_file')
def cleanup_specific_file(filename: str, delay_seconds: int = 60):
    """Delete a specific file after a delay (called after download)"""
    import time
    time.sleep(delay_seconds)
    
    file_path = TEMP_DIR / filename
    if file_path.exists():
        try:
            file_path.unlink()
            logger.info(f"🗑️ Deleted after delay: {filename}")
            return {'deleted': True, 'filename': filename}
        except Exception as e:
            logger.error(f"Failed to delete {filename}: {e}")
            return {'deleted': False, 'error': str(e)}
    
    return {'deleted': False, 'reason': 'File not found'}
