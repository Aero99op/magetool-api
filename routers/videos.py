"""
Video Processing Router - Magetool
"""

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import StreamingResponse
from typing import List, Optional
from pathlib import Path
import asyncio
import json

from services.video_service import VideoService

router = APIRouter()
video_service = VideoService()

@router.post("/convert")
async def convert_video(
    files: List[UploadFile] = File(...),
    target_format: str = Form(...)
):
    """Convert video(s) to target format"""
    if len(files) > 40:
        raise HTTPException(status_code=400, detail="Maximum 40 files allowed")
    
    results = []
    for file in files:
        result = await video_service.convert_format(file, target_format)
        results.append(result)
    
    return {"success": True, "files": results}

@router.post("/youtube-download")
async def download_youtube(url: str = Form(...)):
    """Download video from YouTube"""
    result = await video_service.download_youtube(url)
    return {"success": True, "file": result}

@router.get("/youtube-download-stream")
async def download_youtube_stream(url: str):
    """Stream YouTube download with real-time progress via SSE"""
    
    async def generate():
        async for progress in video_service.download_youtube_with_progress(url):
            yield f"data: {json.dumps(progress)}\n\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )

@router.post("/instagram-download")
async def download_instagram(url: str = Form(...)):
    """Download video from Instagram"""
    result = await video_service.download_instagram(url)
    return {"success": True, "file": result}

@router.get("/instagram-download-stream")
async def download_instagram_stream(url: str):
    """Stream Instagram download with real-time progress via SSE"""
    
    async def generate():
        async for progress in video_service.download_instagram_with_progress(url):
            yield f"data: {json.dumps(progress)}\n\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )

@router.post("/shorts-download")
async def download_shorts(url: str = Form(...)):
    """Download YouTube Shorts"""
    result = await video_service.download_shorts(url)
    return {"success": True, "file": result}

@router.get("/shorts-download-stream")
async def download_shorts_stream(url: str):
    """Stream YouTube Shorts download with real-time progress via SSE"""
    
    async def generate():
        async for progress in video_service.download_youtube_with_progress(url):
            yield f"data: {json.dumps(progress)}\n\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )

@router.post("/reels-download")
async def download_reels(url: str = Form(...)):
    """Download Instagram Reels"""
    result = await video_service.download_reels(url)
    return {"success": True, "file": result}

@router.get("/reels-download-stream")
async def download_reels_stream(url: str):
    """Stream Instagram Reels download with real-time progress via SSE"""
    
    async def generate():
        async for progress in video_service.download_instagram_with_progress(url):
            yield f"data: {json.dumps(progress)}\n\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )

@router.post("/extract-audio")
async def extract_audio(files: List[UploadFile] = File(...)):
    """Extract audio from video(s)"""
    if len(files) > 40:
        raise HTTPException(status_code=400, detail="Maximum 40 files allowed")
    
    results = []
    for file in files:
        result = await video_service.extract_audio(file)
        results.append(result)
    
    return {"success": True, "files": results}

@router.post("/ai-identify")
async def ai_identify_video(files: List[UploadFile] = File(...)):
    """Check if video(s) are AI-generated"""
    if len(files) > 40:
        raise HTTPException(status_code=400, detail="Maximum 40 files allowed")
    
    results = []
    for file in files:
        result = await video_service.ai_identify(file)
        results.append(result)
    
    return {"success": True, "results": results}

