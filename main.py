"""
Magetool Backend - FastAPI Application
All-in-One File Manipulation Hub
"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from contextlib import asynccontextmanager
import os
import shutil
import asyncio
import logging
import subprocess
from pathlib import Path

# Import routers
from routers import images, videos, audio, files

# Import utils
from utils.cleanup import get_cleanup_manager, delete_file_after_download
from utils.validation import MAX_TOTAL_SIZE_MB, MAX_FILES, MAX_FILE_SIZE_MB

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Temp directory for processed files
TEMP_DIR = Path(os.environ.get("TEMP_DIR", "./temp"))
# Create temp directory immediately (needed for StaticFiles mount)
TEMP_DIR.mkdir(exist_ok=True)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage app lifecycle - create temp dir on startup, cleanup on shutdown"""
    TEMP_DIR.mkdir(exist_ok=True)
    
    # Start background cleanup task
    cleanup_manager = get_cleanup_manager(TEMP_DIR)
    cleanup_task = asyncio.create_task(cleanup_manager.start_background_cleanup())
    
    # Auto-update yt-dlp on startup
    try:
        logger.info("🔄 Checking for yt-dlp updates...")
        process = subprocess.run(
            ["pip", "install", "--upgrade", "yt-dlp"], 
            capture_output=True, 
            text=True,
            timeout=30  # 30 seconds timeout to prevent hanging
        )
        if process.returncode == 0:
            logger.info(f"✅ yt-dlp updated: {process.stdout.strip().splitlines()[-1] if process.stdout else 'Success'}")
        else:
            logger.warning(f"⚠️ Failed to update yt-dlp: {process.stderr}")
    except subprocess.TimeoutExpired:
        logger.warning(f"⚠️ yt-dlp update timed out - using cached version")
    except Exception as e:
        logger.error(f"❌ Error updating yt-dlp: {e}")
    
    logger.info("🚀 Magetool API started")
    logger.info(f"📁 Temp directory: {TEMP_DIR.absolute()}")
    
    yield
    
    # Stop cleanup on shutdown
    cleanup_manager.stop()
    cleanup_task.cancel()
    
    # Final cleanup
    if TEMP_DIR.exists():
        shutil.rmtree(TEMP_DIR)
        TEMP_DIR.mkdir(exist_ok=True)
    
    logger.info("👋 Magetool API stopped")

app = FastAPI(
    title="Magetool API",
    description="All-in-One File Manipulation Hub",
    version="1.0.0",
    lifespan=lifespan
)

# CORS configuration - Allow all origins for HF Spaces (Vercel frontend connects here)
# For stricter control, set ALLOWED_ORIGINS env var
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*").split(",") if os.getenv("ALLOWED_ORIGINS") else ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request size limit middleware
@app.middleware("http")
async def validate_request_size(request: Request, call_next):
    """Validate upload size before processing"""
    content_type = request.headers.get("content-type", "")
    
    if request.method == "POST" and "multipart/form-data" in content_type:
        content_length = request.headers.get("content-length")
        if content_length:
            size_mb = int(content_length) / (1024 * 1024)
            if size_mb > MAX_TOTAL_SIZE_MB:
                return JSONResponse(
                    status_code=413,
                    content={
                        "success": False,
                        "error": f"Upload too large: {size_mb:.1f}MB, max allowed is {MAX_TOTAL_SIZE_MB}MB"
                    }
                )
    
    return await call_next(request)

# Mount temp directory for file serving
app.mount("/temp", StaticFiles(directory=str(TEMP_DIR)), name="temp")

# Include routers
app.include_router(images.router, prefix="/api/images", tags=["Images"])
app.include_router(videos.router, prefix="/api/videos", tags=["Videos"])
app.include_router(audio.router, prefix="/api/audio", tags=["Audio"])
app.include_router(files.router, prefix="/api/files", tags=["Files"])

@app.get("/")
async def root():
    return {"message": "Welcome to Magetool API", "version": "1.0.0"}

@app.get("/api/health")
async def health_check():
    cleanup_manager = get_cleanup_manager(TEMP_DIR)
    return {
        "status": "healthy",
        "temp_dir": str(TEMP_DIR.absolute()),
        "temp_size_mb": round(cleanup_manager.get_folder_size_mb(), 2),
        "limits": {
            "max_file_size_mb": MAX_FILE_SIZE_MB,
            "max_total_size_mb": MAX_TOTAL_SIZE_MB,
            "max_files": MAX_FILES
        }
    }

@app.get("/api/download/{filename}")
async def download_file(filename: str, download_name: str = None):
    """Download a processed file from temp directory with optional custom filename"""
    logger.info(f"📥 Download request: filename={filename}, download_name={download_name}")
    file_path = TEMP_DIR / filename
    
    # Fuzzy matching if exact file doesn't exist
    if not file_path.exists():
        # Try to find a file starting with the filename (uuid)
        potential_matches = list(TEMP_DIR.glob(f"{filename}.*"))
        if potential_matches:
            file_path = potential_matches[0]
        else:
            raise HTTPException(status_code=404, detail="File not found")
    
    # Schedule deletion after download (60 seconds delay)
    # Use the original filename requested for cleanup reference if possible, or the found one
    delete_file_after_download(TEMP_DIR, file_path.name, delay_seconds=60)
    
    # Determine the final filename to serve
    # If download_name is provided, use it. 
    # If not, use the actual filename found on disk (which includes extension)
    served_filename = download_name if download_name else file_path.name
    
    # If download_name was provided, ensure it has the correct extension
    if download_name and file_path.suffix:
        # Check if download_name already ends with the correct extension (case-insensitive)
        if not download_name.lower().endswith(file_path.suffix.lower()):
            served_filename = f"{download_name}{file_path.suffix}"
        else:
            served_filename = download_name

    logger.info(f"📤 Serving file: {served_filename} from {file_path} (suffix={file_path.suffix})")

    # === Extension Fix for Playwright Artifacts / Missing Extensions ===
    # If file has no suffix, try to detect it
    if not Path(served_filename).suffix and file_path.exists():
        try:
            # Read first 32 bytes to check magic numbers
            with open(file_path, 'rb') as f:
                header = f.read(32)
            
            new_suffix = None
            
            # Common file signatures
            if header.startswith(b'\xff\xd8\xff'):
                new_suffix = '.jpg'
            elif header.startswith(b'\x89PNG\r\n\x1a\n'):
                new_suffix = '.png'
            elif header.startswith(b'GIF87a') or header.startswith(b'GIF89a'):
                new_suffix = '.gif'
            elif header.startswith(b'%PDF'):
                new_suffix = '.pdf'
            elif header.startswith(b'ID3') or header.startswith(b'\xff\xfb') or header.startswith(b'\xff\xf3') or header.startswith(b'\xff\xf2'):
                new_suffix = '.mp3'
            elif header[4:12] == b'ftypmp42' or header[4:12] == b'ftypisom' or header[4:12] == b'ftypMSNV':
                new_suffix = '.mp4'
            elif header.startswith(b'\x1aE\xdf\xa3'):
                new_suffix = '.mkv'
            elif header.startswith(b'RIFF') and header[8:12] == b'WEBP':
                new_suffix = '.webp'
            
            if new_suffix:
                logger.info(f"🔍 Detected file type from header: {new_suffix}")
                
                # update served filename
                served_filename = f"{served_filename}{new_suffix}"
                
                # OPTIONAL: Rename the original file to fix specific peristence issue
                # We only rename if it's a UUID-like file to avoid messing up specific user files
                # if 'playwright' in str(file_path) or len(file_path.name) > 30:
                try:
                    new_path = file_path.with_suffix(new_suffix)
                    if not new_path.exists():
                        os.rename(file_path, new_path)
                        file_path = new_path
                        logger.info(f"✅ Renamed extension-less file to: {file_path.name}")
                except Exception as e:
                    logger.warning(f"⚠️ Could not rename file: {e}")
        except Exception as e:
            logger.error(f"❌ Error detecting file type: {e}")
            
    # Re-guess media type after potential fix
    import mimetypes
    media_type, _ = mimetypes.guess_type(served_filename)
    if not media_type:
        media_type = "application/octet-stream"

    return FileResponse(
        path=file_path,
        filename=served_filename,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{served_filename}"'}
    )

@app.delete("/api/cleanup/{filename}")
async def cleanup_file(filename: str):
    """Delete a specific file from temp directory"""
    file_path = TEMP_DIR / filename
    if file_path.exists():
        os.remove(file_path)
        return {"message": f"File {filename} deleted"}
    return {"message": "File not found"}

@app.post("/api/cleanup/run")
async def run_cleanup():
    """Manually trigger cleanup"""
    cleanup_manager = get_cleanup_manager(TEMP_DIR)
    result = cleanup_manager.run_cleanup()
    return {
        "success": True,
        "message": f"Deleted {result['total_deleted']} files",
        "current_size_mb": round(result['current_size_mb'], 2)
    }


# ==================== WebSocket & Task APIs ====================

from fastapi import WebSocket, WebSocketDisconnect

# Import WebSocket manager (lazy to avoid circular imports)
_ws_manager = None
def get_ws_manager():
    global _ws_manager
    if _ws_manager is None:
        from websocket_manager import manager
        _ws_manager = manager
    return _ws_manager

# Import Celery app for task status
_celery_app = None
def get_celery_app():
    global _celery_app
    if _celery_app is None:
        try:
            from celery_app import celery_app
            _celery_app = celery_app
        except Exception:
            _celery_app = None
    return _celery_app


@app.websocket("/ws/task/{task_id}")
async def websocket_task_progress(websocket: WebSocket, task_id: str):
    """WebSocket endpoint for real-time task progress"""
    manager = get_ws_manager()
    await manager.connect(task_id, websocket)
    try:
        while True:
            # Keep connection alive, receive any client messages
            data = await websocket.receive_text()
            # Client can send "ping" to keep alive
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(task_id)
    except Exception:
        manager.disconnect(task_id)


@app.get("/api/task/{task_id}/status")
async def get_task_status(task_id: str):
    """Get status of a background Celery task"""
    celery = get_celery_app()
    if not celery:
        return {"error": "Celery not configured", "status": "UNAVAILABLE"}
    
    try:
        result = celery.AsyncResult(task_id)
        
        response = {
            "task_id": task_id,
            "status": result.state,
            "ready": result.ready(),
        }
        
        if result.state == 'PROCESSING':
            response["progress"] = result.info.get('progress', 0) if result.info else 0
            response["message"] = result.info.get('message', '') if result.info else ''
        elif result.ready():
            response["result"] = result.result
        elif result.state == 'FAILURE':
            response["error"] = str(result.result)
        
        return response
    except Exception as e:
        return {"task_id": task_id, "error": str(e)}


@app.get("/api/ws/connections")
async def get_ws_connections():
    """Get number of active WebSocket connections"""
    manager = get_ws_manager()
    return {"active_connections": manager.get_connection_count()}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
