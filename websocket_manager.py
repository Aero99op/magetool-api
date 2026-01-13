"""
WebSocket Manager - Magetool
Real-time progress updates for file processing
"""

from fastapi import WebSocket
from typing import Dict
import asyncio
import json
import logging

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manage WebSocket connections for real-time progress updates"""
    
    def __init__(self):
        # Map task_id to WebSocket connection
        self.active_connections: Dict[str, WebSocket] = {}
        # Map task_id to progress data
        self.task_progress: Dict[str, dict] = {}
    
    async def connect(self, task_id: str, websocket: WebSocket):
        """Accept and store a new WebSocket connection"""
        await websocket.accept()
        self.active_connections[task_id] = websocket
        logger.info(f"WebSocket connected for task: {task_id}")
        
        # Send initial status if exists
        if task_id in self.task_progress:
            await self.send_progress(task_id, **self.task_progress[task_id])
    
    def disconnect(self, task_id: str):
        """Remove a WebSocket connection"""
        self.active_connections.pop(task_id, None)
        self.task_progress.pop(task_id, None)
        logger.info(f"WebSocket disconnected for task: {task_id}")
    
    async def send_progress(
        self, 
        task_id: str, 
        progress: int, 
        status: str,
        message: str = "",
        result: dict = None
    ):
        """Send progress update to connected client"""
        data = {
            "task_id": task_id,
            "progress": progress,
            "status": status,
            "message": message,
            "result": result
        }
        
        # Store progress
        self.task_progress[task_id] = data
        
        # Send if connected
        if task_id in self.active_connections:
            try:
                await self.active_connections[task_id].send_json(data)
                logger.debug(f"Progress sent: {task_id} - {progress}%")
            except Exception as e:
                logger.error(f"Failed to send progress: {e}")
                self.disconnect(task_id)
    
    async def broadcast_progress(self, task_id: str, progress: int, status: str, message: str = ""):
        """Broadcast progress (wrapper for Celery tasks)"""
        await self.send_progress(task_id, progress, status, message)
    
    def get_connection_count(self) -> int:
        """Get number of active connections"""
        return len(self.active_connections)
    
    def is_connected(self, task_id: str) -> bool:
        """Check if a task has an active connection"""
        return task_id in self.active_connections


# Global manager instance
manager = ConnectionManager()


def get_manager() -> ConnectionManager:
    """Get the global WebSocket manager instance"""
    return manager
