"""
Image Processing Router - Magetool
"""

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse
from typing import List, Optional
from pathlib import Path
import uuid
import os

from services.image_service import ImageService

router = APIRouter()
image_service = ImageService()

TEMP_DIR = Path("./temp")

@router.post("/convert")
async def convert_image(
    files: List[UploadFile] = File(...),
    target_format: str = Form(...)
):
    """Convert image(s) to target format"""
    if len(files) > 40:
        raise HTTPException(status_code=400, detail="Maximum 40 files allowed")
    
    results = []
    for file in files:
        result = await image_service.convert_format(file, target_format)
        results.append(result)
    
    return {"success": True, "files": results}

@router.post("/to-pdf")
async def images_to_pdf(files: List[UploadFile] = File(...)):
    """Convert image(s) to PDF"""
    if len(files) > 40:
        raise HTTPException(status_code=400, detail="Maximum 40 files allowed")
    
    result = await image_service.to_pdf(files)
    return {"success": True, "file": result}

@router.post("/crop")
async def crop_image(
    file: UploadFile = File(...),
    x: int = Form(...),
    y: int = Form(...),
    width: int = Form(...),
    height: int = Form(...)
):
    """Crop an image with specified dimensions"""
    result = await image_service.crop(file, x, y, width, height)
    return {"success": True, "file": result}

@router.post("/remove-background")
async def remove_background(files: List[UploadFile] = File(...)):
    """Remove background from image(s) using AI"""
    if len(files) > 40:
        raise HTTPException(status_code=400, detail="Maximum 40 files allowed")
    
    results = []
    for file in files:
        result = await image_service.remove_background(file)
        results.append(result)
    
    return {"success": True, "files": results}

@router.post("/upscale")
async def upscale_image(
    files: List[UploadFile] = File(...),
    scale: int = Form(default=2)
):
    """Upscale image(s) by specified factor"""
    if len(files) > 40:
        raise HTTPException(status_code=400, detail="Maximum 40 files allowed")
    
    results = []
    for file in files:
        result = await image_service.upscale(file, scale)
        results.append(result)
    
    return {"success": True, "files": results}

@router.post("/resize")
async def resize_image(
    files: List[UploadFile] = File(...),
    width: int = Form(...),
    height: int = Form(...)
):
    """Resize image(s) to specified dimensions"""
    if len(files) > 40:
        raise HTTPException(status_code=400, detail="Maximum 40 files allowed")
    
    results = []
    for file in files:
        result = await image_service.resize(file, width, height)
        results.append(result)
    
    return {"success": True, "files": results}

@router.post("/passport")
async def create_passport_photo(
    file: UploadFile = File(...),
    size: str = Form(default="2x2")
):
    """Create passport-sized photo"""
    result = await image_service.create_passport_photo(file, size)
    return {"success": True, "file": result}

@router.post("/collage")
async def create_collage(
    files: List[UploadFile] = File(...),
    layout: str = Form(default="grid"),
    columns: int = Form(default=3)
):
    """Create a collage from multiple images"""
    if len(files) > 40:
        raise HTTPException(status_code=400, detail="Maximum 40 files allowed")
    
    result = await image_service.create_collage(files, layout, columns)
    return {"success": True, "file": result}

@router.post("/filter")
async def apply_filter(
    files: List[UploadFile] = File(...),
    filter_name: str = Form(...)
):
    """Apply filter to image(s)"""
    if len(files) > 40:
        raise HTTPException(status_code=400, detail="Maximum 40 files allowed")
    
    results = []
    for file in files:
        result = await image_service.apply_filter(file, filter_name)
        results.append(result)
    
    return {"success": True, "files": results}

@router.post("/ocr")
async def ocr_scan(files: List[UploadFile] = File(...)):
    """Extract text from image(s) using OCR"""
    if len(files) > 40:
        raise HTTPException(status_code=400, detail="Maximum 40 files allowed")
    
    results = []
    for file in files:
        result = await image_service.ocr_scan(file)
        results.append(result)
    
    return {"success": True, "results": results}

@router.post("/ai-check")
async def ai_image_check(files: List[UploadFile] = File(...)):
    """Check if image(s) are AI-generated"""
    if len(files) > 40:
        raise HTTPException(status_code=400, detail="Maximum 40 files allowed")
    
    results = []
    for file in files:
        result = await image_service.ai_check(file)
        results.append(result)
    
    return {"success": True, "results": results}
