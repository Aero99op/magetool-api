"""
Audio Processing Router - Magetool
"""

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from typing import List, Optional
from pathlib import Path

from services.audio_service import AudioService

router = APIRouter()
audio_service = AudioService()

@router.post("/convert")
async def convert_audio(
    files: List[UploadFile] = File(...),
    target_format: str = Form(...)
):
    """Convert audio file(s) to target format"""
    if len(files) > 40:
        raise HTTPException(status_code=400, detail="Maximum 40 files allowed")
    
    results = []
    for file in files:
        result = await audio_service.convert_format(file, target_format)
        results.append(result)
    
    return {"success": True, "files": results}

@router.post("/trim")
async def trim_audio(
    file: UploadFile = File(...),
    start_time: float = Form(...),
    end_time: float = Form(...)
):
    """Trim audio file to specified time range"""
    result = await audio_service.trim(file, start_time, end_time)
    return {"success": True, "file": result}

@router.post("/identify")
async def identify_audio(files: List[UploadFile] = File(...)):
    """Identify audio name/metadata"""
    if len(files) > 40:
        raise HTTPException(status_code=400, detail="Maximum 40 files allowed")
    
    results = []
    for file in files:
        result = await audio_service.identify(file)
        results.append(result)
    
    return {"success": True, "results": results}

@router.post("/download")
async def download_audio(url: str = Form(...)):
    """Download audio from URL"""
    result = await audio_service.download_from_url(url)
    return {"success": True, "file": result}
