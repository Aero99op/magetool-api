"""
File Validation & Security - Magetool
Handles MIME validation, size limits, and filename sanitization
"""

import re
import uuid
from pathlib import Path
from typing import Optional

# Try to import python-magic
try:
    import magic
    MAGIC_AVAILABLE = True
except ImportError:
    MAGIC_AVAILABLE = False

# Allowed MIME types by category
ALLOWED_MIMES = {
    'image': [
        'image/png', 'image/jpeg', 'image/webp', 'image/gif', 
        'image/bmp', 'image/tiff', 'image/x-icon'
    ],
    'video': [
        'video/mp4', 'video/x-msvideo', 'video/x-matroska', 
        'video/quicktime', 'video/webm', 'video/x-flv', 'video/x-ms-wmv'
    ],
    'audio': [
        'audio/mpeg', 'audio/wav', 'audio/x-wav', 'audio/ogg', 
        'audio/flac', 'audio/aac', 'audio/mp4', 'audio/x-m4a'
    ],
    'document': [
        'application/pdf',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'text/plain', 'text/markdown', 'application/json',
        'text/html', 'text/css', 'application/javascript'
    ]
}

# Extension to MIME mapping for basic validation
EXT_TO_CATEGORY = {
    # Images
    'png': 'image', 'jpg': 'image', 'jpeg': 'image', 'webp': 'image',
    'gif': 'image', 'bmp': 'image', 'tiff': 'image', 'ico': 'image',
    # Videos
    'mp4': 'video', 'avi': 'video', 'mkv': 'video', 'mov': 'video',
    'webm': 'video', 'flv': 'video', 'wmv': 'video',
    # Audio
    'mp3': 'audio', 'wav': 'audio', 'ogg': 'audio', 'flac': 'audio',
    'aac': 'audio', 'm4a': 'audio', 'wma': 'audio',
    # Documents
    'pdf': 'document', 'docx': 'document', 'txt': 'document',
    'md': 'document', 'json': 'document', 'html': 'document',
    'css': 'document', 'js': 'document'
}

# Size limits
MAX_FILE_SIZE_MB = 500  # 500MB per file
MAX_TOTAL_SIZE_MB = 20000  # 20GB total (40 files × 500MB)
MAX_FILES = 40


def get_file_mime(content: bytes) -> Optional[str]:
    """Get MIME type from file content"""
    if not MAGIC_AVAILABLE:
        return None
    try:
        return magic.from_buffer(content[:2048], mime=True)
    except Exception:
        return None


def validate_mime_type(content: bytes, expected_category: str) -> dict:
    """
    Validate that file content matches expected category
    Returns: {"valid": bool, "mime": str, "error": str|None}
    """
    if not MAGIC_AVAILABLE:
        # If magic not available, skip MIME check
        return {"valid": True, "mime": "unknown", "error": None}
    
    mime = get_file_mime(content)
    if not mime:
        return {"valid": False, "mime": None, "error": "Could not determine file type"}
    
    allowed = ALLOWED_MIMES.get(expected_category, [])
    if mime not in allowed:
        return {
            "valid": False, 
            "mime": mime, 
            "error": f"File type '{mime}' not allowed for {expected_category}"
        }
    
    return {"valid": True, "mime": mime, "error": None}


def validate_file_size(size_bytes: int, filename: str = "") -> dict:
    """
    Validate file size
    Returns: {"valid": bool, "size_mb": float, "error": str|None}
    """
    size_mb = size_bytes / (1024 * 1024)
    
    if size_mb > MAX_FILE_SIZE_MB:
        return {
            "valid": False,
            "size_mb": size_mb,
            "error": f"File '{filename}' is {size_mb:.1f}MB, max allowed is {MAX_FILE_SIZE_MB}MB"
        }
    
    return {"valid": True, "size_mb": size_mb, "error": None}


def validate_batch_size(files_count: int, total_bytes: int) -> dict:
    """
    Validate batch upload limits
    Returns: {"valid": bool, "error": str|None}
    """
    if files_count > MAX_FILES:
        return {
            "valid": False,
            "error": f"Too many files: {files_count}, max allowed is {MAX_FILES}"
        }
    
    total_mb = total_bytes / (1024 * 1024)
    if total_mb > MAX_TOTAL_SIZE_MB:
        return {
            "valid": False,
            "error": f"Total size {total_mb:.1f}MB exceeds limit of {MAX_TOTAL_SIZE_MB}MB"
        }
    
    return {"valid": True, "error": None}


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename to prevent path traversal and other attacks
    """
    if not filename:
        return f"{uuid.uuid4().hex[:16]}.bin"
    
    # Get extension
    parts = filename.rsplit('.', 1)
    name = parts[0] if parts else filename
    ext = parts[1].lower() if len(parts) > 1 else ''
    
    # Remove path traversal attempts
    name = name.replace("..", "").replace("/", "").replace("\\", "")
    
    # Keep only safe characters (alphanumeric, dash, underscore)
    name = re.sub(r'[^a-zA-Z0-9_-]', '_', name)
    
    # Remove multiple underscores
    name = re.sub(r'_+', '_', name).strip('_')
    
    # Limit length
    if len(name) > 50:
        name = name[:50]
    
    # If name is empty after sanitization, generate one
    if not name:
        name = uuid.uuid4().hex[:16]
    
    # Validate extension
    if ext and ext in EXT_TO_CATEGORY:
        return f"{name}.{ext}"
    elif ext:
        # Unknown extension - keep but limit length
        ext = re.sub(r'[^a-zA-Z0-9]', '', ext)[:10]
        return f"{name}.{ext}" if ext else name
    
    return name


def get_category_from_extension(filename: str) -> Optional[str]:
    """Get expected category from file extension"""
    if not filename or '.' not in filename:
        return None
    ext = filename.rsplit('.', 1)[-1].lower()
    return EXT_TO_CATEGORY.get(ext)


def validate_file(content: bytes, filename: str, expected_category: Optional[str] = None) -> dict:
    """
    Complete file validation
    Returns: {
        "valid": bool,
        "errors": list[str],
        "sanitized_name": str,
        "mime": str|None,
        "size_mb": float,
        "category": str|None
    }
    """
    errors = []
    
    # 1. Sanitize filename
    sanitized = sanitize_filename(filename)
    
    # 2. Validate size
    size_check = validate_file_size(len(content), filename)
    if not size_check["valid"]:
        errors.append(size_check["error"])
    
    # 3. Determine category
    category = expected_category or get_category_from_extension(filename)
    
    # 4. Validate MIME type
    mime = None
    if category and MAGIC_AVAILABLE:
        mime_check = validate_mime_type(content, category)
        mime = mime_check.get("mime")
        if not mime_check["valid"]:
            errors.append(mime_check["error"])
    
    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "sanitized_name": sanitized,
        "mime": mime,
        "size_mb": size_check.get("size_mb", 0),
        "category": category
    }


def validate_batch_mime(files: list, expected_category: str) -> dict:
    """
    Validate MIME types for a batch of files (up to 40).
    Returns: {
        "valid": bool,
        "total_files": int,
        "valid_files": list[str],
        "invalid_files": list[dict],  # [{filename, error}]
        "total_size_mb": float
    }
    """
    if len(files) > MAX_FILES:
        return {
            "valid": False,
            "error": f"Too many files: {len(files)}, max allowed is {MAX_FILES}",
            "total_files": len(files),
            "valid_files": [],
            "invalid_files": [],
            "total_size_mb": 0
        }
    
    valid_files = []
    invalid_files = []
    total_size = 0
    
    for file_data in files:
        filename = file_data.get("filename", "unknown")
        content = file_data.get("content", b"")
        
        # Validate individual file
        result = validate_file(content, filename, expected_category)
        total_size += result.get("size_mb", 0)
        
        if result["valid"]:
            valid_files.append(result["sanitized_name"])
        else:
            invalid_files.append({
                "filename": filename,
                "errors": result["errors"],
                "detected_mime": result.get("mime", "unknown")
            })
    
    return {
        "valid": len(invalid_files) == 0,
        "total_files": len(files),
        "valid_files": valid_files,
        "invalid_files": invalid_files,
        "total_size_mb": round(total_size, 2)
    }

