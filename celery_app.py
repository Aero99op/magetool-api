"""
Celery Application - Magetool
Background task processing with Redis broker
"""

import os
from celery import Celery

# Get broker URL from environment - prioritize REDIS_URL (Upstash)
REDIS_URL = os.getenv('REDIS_URL') or os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0')
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL

# Create Celery app
celery_app = Celery(
    'magetool',
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
    include=['tasks.image_tasks', 'tasks.video_tasks', 'tasks.audio_tasks', 'tasks.file_tasks']
)

# Celery configuration
celery_app.conf.update(
    # Serialization
    task_serializer='json',
    result_serializer='json',
    accept_content=['json'],
    
    # Result expiration (1 hour)
    result_expires=3600,
    
    # Task settings
    task_track_started=True,
    task_time_limit=600,  # 10 minutes max per task
    task_soft_time_limit=540,  # 9 minutes soft limit
    
    # Worker settings
    worker_prefetch_multiplier=1,
    worker_concurrency=4,
    
    # Beat scheduler for periodic tasks
    beat_schedule={
        'cleanup-temp-files': {
            'task': 'tasks.cleanup_tasks.cleanup_old_files',
            'schedule': 600.0,  # Every 10 minutes
        },
    },
)

# Task routing (optional - for scaling)
celery_app.conf.task_routes = {
    'tasks.video_tasks.*': {'queue': 'heavy'},
    'tasks.image_tasks.*': {'queue': 'default'},
    'tasks.audio_tasks.*': {'queue': 'default'},
    'tasks.file_tasks.*': {'queue': 'default'},
}
