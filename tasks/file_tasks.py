"""
File Tasks - Celery background jobs for file processing
"""

from celery_app import celery_app
from services.file_service import FileService
import logging

logger = logging.getLogger(__name__)
file_service = FileService()


@celery_app.task(bind=True, name='tasks.file_tasks.merge_pdfs')
def merge_pdfs_task(self, input_paths: list):
    """Background task for PDF merging"""
    try:
        total = len(input_paths)
        self.update_state(state='PROCESSING', meta={'progress': 10, 'message': f'Merging {total} PDFs...'})
        
        result = file_service.merge_pdfs_sync(input_paths)
        
        self.update_state(state='PROCESSING', meta={'progress': 100, 'message': 'Complete!'})
        
        return {'success': True, 'file': result}
    except Exception as e:
        logger.error(f"Merge PDFs task failed: {e}")
        return {'success': False, 'error': str(e)}


@celery_app.task(bind=True, name='tasks.file_tasks.ocr_scan')
def ocr_scan_task(self, input_path: str):
    """Background task for OCR scanning"""
    try:
        self.update_state(state='PROCESSING', meta={'progress': 20, 'message': 'Scanning document...'})
        
        result = file_service.ocr_scan_sync(input_path)
        
        self.update_state(state='PROCESSING', meta={'progress': 100, 'message': 'Complete!'})
        
        return {'success': True, 'result': result}
    except Exception as e:
        logger.error(f"OCR scan task failed: {e}")
        return {'success': False, 'error': str(e)}
