"""
File Processing Router - Magetool
"""

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from typing import List, Optional
from pathlib import Path

from services.file_service import FileService

router = APIRouter()
file_service = FileService()

@router.post("/convert")
async def convert_file(
    files: List[UploadFile] = File(...),
    target_format: str = Form(...)
):
    """Convert file(s) to target format"""
    if len(files) > 40:
        raise HTTPException(status_code=400, detail="Maximum 40 files allowed")
    
    results = []
    for file in files:
        result = await file_service.convert_format(file, target_format)
        results.append(result)
    
    return {"success": True, "files": results}

@router.post("/ocr")
async def ocr_file(files: List[UploadFile] = File(...)):
    """Extract text from file(s) using OCR"""
    if len(files) > 40:
        raise HTTPException(status_code=400, detail="Maximum 40 files allowed")
    
    results = []
    for file in files:
        result = await file_service.ocr_scan(file)
        results.append(result)
    
    return {"success": True, "results": results}

@router.post("/edit")
async def edit_file(
    file: UploadFile = File(...),
    content: str = Form(...)
):
    """Edit file content"""
    result = await file_service.edit_content(file, content)
    return {"success": True, "file": result}

@router.post("/merge-pdf")
async def merge_pdfs(files: List[UploadFile] = File(...)):
    """Merge multiple PDFs into one"""
    if len(files) > 40:
        raise HTTPException(status_code=400, detail="Maximum 40 files allowed")
    
    result = await file_service.merge_pdfs(files)
    return {"success": True, "file": result}

@router.post("/split-pdf")
async def split_pdf(
    file: UploadFile = File(...),
    pages: str = Form(...)
):
    """Split PDF by page ranges"""
    result = await file_service.split_pdf(file, pages)
    return {"success": True, "files": result}
