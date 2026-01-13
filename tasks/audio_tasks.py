"""
Audio Tasks - Celery background jobs for audio processing
"""

from celery_app import celery_app
from services.audio_service import AudioService
import logging

logger = logging.getLogger(__name__)
audio_service = AudioService()


@celery_app.task(bind=True, name='tasks.audio_tasks.convert_audio')
def convert_audio_task(self, input_path: str, target_format: str):
    """Background task for audio format conversion"""
    try:
        self.update_state(state='PROCESSING', meta={'progress': 20, 'message': 'Converting...'})
        
        result = audio_service.convert_format_sync(input_path, target_format)
        
        self.update_state(state='PROCESSING', meta={'progress': 100, 'message': 'Complete!'})
        
        return {'success': True, 'file': result}
    except Exception as e:
        logger.error(f"Convert audio task failed: {e}")
        return {'success': False, 'error': str(e)}


@celery_app.task(bind=True, name='tasks.audio_tasks.trim_audio')
def trim_audio_task(self, input_path: str, start_time: float, end_time: float):
    """Background task for audio trimming"""
    try:
        self.update_state(state='PROCESSING', meta={'progress': 30, 'message': 'Trimming audio...'})
        
        result = audio_service.trim_sync(input_path, start_time, end_time)
        
        self.update_state(state='PROCESSING', meta={'progress': 100, 'message': 'Complete!'})
        
        return {'success': True, 'file': result}
    except Exception as e:
        logger.error(f"Trim audio task failed: {e}")
        return {'success': False, 'error': str(e)}
