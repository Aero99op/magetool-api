"""
Image Tasks - Celery background jobs for image processing
"""

from celery_app import celery_app
from services.image_service import ImageService
from pathlib import Path
import logging

logger = logging.getLogger(__name__)
image_service = ImageService()


@celery_app.task(bind=True, name='tasks.image_tasks.convert_image')
def convert_image_task(self, input_path: str, target_format: str):
    """Background task for image format conversion"""
    try:
        self.update_state(state='PROCESSING', meta={'progress': 10})
        
        # Simulate progress updates
        self.update_state(state='PROCESSING', meta={'progress': 50})
        
        # Process
        result = image_service.convert_format_sync(input_path, target_format)
        
        self.update_state(state='PROCESSING', meta={'progress': 100})
        
        return {'success': True, 'file': result}
    except Exception as e:
        logger.error(f"Convert image task failed: {e}")
        return {'success': False, 'error': str(e)}


@celery_app.task(bind=True, name='tasks.image_tasks.remove_background')
def remove_background_task(self, input_path: str):
    """Background task for AI background removal"""
    try:
        self.update_state(state='PROCESSING', meta={'progress': 10, 'message': 'Loading AI model...'})
        
        self.update_state(state='PROCESSING', meta={'progress': 30, 'message': 'Processing image...'})
        
        result = image_service.remove_background_sync(input_path)
        
        self.update_state(state='PROCESSING', meta={'progress': 100, 'message': 'Complete!'})
        
        return {'success': True, 'file': result}
    except Exception as e:
        logger.error(f"Remove background task failed: {e}")
        return {'success': False, 'error': str(e)}


@celery_app.task(bind=True, name='tasks.image_tasks.batch_convert')
def batch_convert_task(self, input_paths: list, target_format: str):
    """Background task for batch image conversion"""
    results = []
    total = len(input_paths)
    
    for i, path in enumerate(input_paths):
        try:
            progress = int((i / total) * 100)
            self.update_state(
                state='PROCESSING', 
                meta={'progress': progress, 'message': f'Processing {i+1}/{total}'}
            )
            
            result = image_service.convert_format_sync(path, target_format)
            results.append({'success': True, 'file': result})
        except Exception as e:
            results.append({'success': False, 'error': str(e)})
    
    return {'success': True, 'files': results}
