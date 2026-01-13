"""
Video Tasks - Celery background jobs for video processing
"""

from celery_app import celery_app
from services.video_service import VideoService
import logging

logger = logging.getLogger(__name__)
video_service = VideoService()


@celery_app.task(bind=True, name='tasks.video_tasks.convert_video')
def convert_video_task(self, input_path: str, target_format: str):
    """Background task for video format conversion"""
    try:
        self.update_state(state='PROCESSING', meta={'progress': 10, 'message': 'Starting conversion...'})
        
        # FFmpeg conversion (this is the heavy operation)
        self.update_state(state='PROCESSING', meta={'progress': 30, 'message': 'Encoding video...'})
        
        result = video_service.convert_format_sync(input_path, target_format)
        
        self.update_state(state='PROCESSING', meta={'progress': 100, 'message': 'Complete!'})
        
        return {'success': True, 'file': result}
    except Exception as e:
        logger.error(f"Convert video task failed: {e}")
        return {'success': False, 'error': str(e)}


@celery_app.task(bind=True, name='tasks.video_tasks.download_youtube')
def download_youtube_task(self, url: str):
    """Background task for YouTube video download"""
    try:
        self.update_state(state='PROCESSING', meta={'progress': 10, 'message': 'Fetching video info...'})
        
        self.update_state(state='PROCESSING', meta={'progress': 30, 'message': 'Downloading...'})
        
        result = video_service.download_youtube_sync(url)
        
        self.update_state(state='PROCESSING', meta={'progress': 100, 'message': 'Complete!'})
        
        return {'success': True, 'file': result}
    except Exception as e:
        logger.error(f"YouTube download task failed: {e}")
        return {'success': False, 'error': str(e)}


@celery_app.task(bind=True, name='tasks.video_tasks.extract_audio')
def extract_audio_task(self, input_path: str):
    """Background task for audio extraction"""
    try:
        self.update_state(state='PROCESSING', meta={'progress': 20, 'message': 'Extracting audio...'})
        
        result = video_service.extract_audio_sync(input_path)
        
        self.update_state(state='PROCESSING', meta={'progress': 100, 'message': 'Complete!'})
        
        return {'success': True, 'file': result}
    except Exception as e:
        logger.error(f"Extract audio task failed: {e}")
        return {'success': False, 'error': str(e)}
