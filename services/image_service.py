"""
Image Service - Magetool
Handles all image processing operations
"""

from fastapi import UploadFile
from PIL import Image, ImageFilter, ImageEnhance
from pathlib import Path
import uuid
import io
import os

# Lazy imports - only load heavy libraries when needed
REMBG_AVAILABLE = None
TESSERACT_AVAILABLE = None
CV2_AVAILABLE = None

def _get_rembg():
    global REMBG_AVAILABLE
    if REMBG_AVAILABLE is None:
        try:
            from rembg import remove as remove_bg
            REMBG_AVAILABLE = remove_bg
        except ImportError:
            REMBG_AVAILABLE = False
    return REMBG_AVAILABLE

def _get_tesseract():
    global TESSERACT_AVAILABLE
    if TESSERACT_AVAILABLE is None:
        try:
            import pytesseract
            TESSERACT_AVAILABLE = pytesseract
        except ImportError:
            TESSERACT_AVAILABLE = False
    return TESSERACT_AVAILABLE

def _get_cv2():
    global CV2_AVAILABLE
    if CV2_AVAILABLE is None:
        try:
            import cv2
            import numpy as np
            CV2_AVAILABLE = (cv2, np)
        except ImportError:
            CV2_AVAILABLE = False
    return CV2_AVAILABLE

TEMP_DIR = Path("./temp")

class ImageService:
    """Service for image processing operations"""
    
    SUPPORTED_FORMATS = ['png', 'jpg', 'jpeg', 'webp', 'gif', 'bmp', 'tiff', 'ico']
    
    FILTERS = {
        'blur': ImageFilter.BLUR,
        'contour': ImageFilter.CONTOUR,
        'detail': ImageFilter.DETAIL,
        'edge_enhance': ImageFilter.EDGE_ENHANCE,
        'emboss': ImageFilter.EMBOSS,
        'sharpen': ImageFilter.SHARPEN,
        'smooth': ImageFilter.SMOOTH,
    }
    
    PASSPORT_SIZES = {
        '2x2': (600, 600),      # US Passport (2x2 inches at 300dpi)
        '35x45': (413, 531),    # EU Passport (35x45mm at 300dpi)
        '35x35': (413, 413),    # India Passport
        '33x48': (390, 567),    # UK Passport
    }
    
    async def _save_uploaded_file(self, file: UploadFile) -> Path:
        """Save uploaded file to temp directory"""
        content = await file.read()
        suffix = Path(file.filename).suffix if file.filename else '.png'
        temp_path = TEMP_DIR / f"{uuid.uuid4()}{suffix}"
        temp_path.write_bytes(content)
        return temp_path
    
    async def convert_format(self, file: UploadFile, target_format: str) -> dict:
        """Convert image to target format"""
        target_format = target_format.lower().strip('.')
        if target_format not in self.SUPPORTED_FORMATS:
            return {"error": f"Unsupported format: {target_format}"}
        
        temp_path = await self._save_uploaded_file(file)
        
        try:
            img = Image.open(temp_path)
            if img.mode in ('RGBA', 'LA', 'P') and target_format in ('jpg', 'jpeg'):
                img = img.convert('RGB')
            
            output_filename = f"{uuid.uuid4()}.{target_format}"
            output_path = TEMP_DIR / output_filename
            img.save(output_path, format=target_format.upper() if target_format != 'jpg' else 'JPEG')
            
            return {
                "filename": output_filename,
                "original": file.filename,
                "format": target_format,
                "size": output_path.stat().st_size
            }
        finally:
            if temp_path.exists():
                os.remove(temp_path)
    
    async def to_pdf(self, files: list[UploadFile]) -> dict:
        """Convert images to PDF"""
        images = []
        temp_paths = []
        
        try:
            for file in files:
                temp_path = await self._save_uploaded_file(file)
                temp_paths.append(temp_path)
                img = Image.open(temp_path)
                if img.mode == 'RGBA':
                    img = img.convert('RGB')
                images.append(img)
            
            if not images:
                return {"error": "No valid images provided"}
            
            output_filename = f"{uuid.uuid4()}.pdf"
            output_path = TEMP_DIR / output_filename
            
            first_img = images[0]
            if len(images) > 1:
                first_img.save(output_path, save_all=True, append_images=images[1:])
            else:
                first_img.save(output_path)
            
            return {
                "filename": output_filename,
                "page_count": len(images),
                "size": output_path.stat().st_size
            }
        finally:
            for path in temp_paths:
                if path.exists():
                    os.remove(path)
    
    async def crop(self, file: UploadFile, x: int, y: int, width: int, height: int) -> dict:
        """Crop image with specified dimensions"""
        temp_path = await self._save_uploaded_file(file)
        
        try:
            img = Image.open(temp_path)
            cropped = img.crop((x, y, x + width, y + height))
            
            suffix = Path(file.filename).suffix if file.filename else '.png'
            output_filename = f"{uuid.uuid4()}{suffix}"
            output_path = TEMP_DIR / output_filename
            cropped.save(output_path)
            
            return {
                "filename": output_filename,
                "original": file.filename,
                "dimensions": {"width": width, "height": height},
                "size": output_path.stat().st_size
            }
        finally:
            if temp_path.exists():
                os.remove(temp_path)
    
    async def remove_background(self, file: UploadFile) -> dict:
        """Remove background using rembg AI"""
        remove_bg = _get_rembg()
        if not remove_bg:
            return {"error": "rembg not installed. Install with: pip install rembg"}
        
        temp_path = await self._save_uploaded_file(file)
        
        try:
            with open(temp_path, 'rb') as f:
                input_data = f.read()
            
            output_data = remove_bg(input_data)
            
            output_filename = f"{uuid.uuid4()}.png"
            output_path = TEMP_DIR / output_filename
            output_path.write_bytes(output_data)
            
            return {
                "filename": output_filename,
                "original": file.filename,
                "size": output_path.stat().st_size
            }
        finally:
            if temp_path.exists():
                os.remove(temp_path)
    
    async def upscale(self, file: UploadFile, scale: int = 2) -> dict:
        """Upscale image by specified factor using Lanczos resampling"""
        temp_path = await self._save_uploaded_file(file)
        
        try:
            img = Image.open(temp_path)
            new_size = (img.width * scale, img.height * scale)
            upscaled = img.resize(new_size, Image.Resampling.LANCZOS)
            
            suffix = Path(file.filename).suffix if file.filename else '.png'
            output_filename = f"{uuid.uuid4()}{suffix}"
            output_path = TEMP_DIR / output_filename
            upscaled.save(output_path)
            
            return {
                "filename": output_filename,
                "original": file.filename,
                "original_size": {"width": img.width, "height": img.height},
                "new_size": {"width": new_size[0], "height": new_size[1]},
                "scale": scale,
                "size": output_path.stat().st_size
            }
        finally:
            if temp_path.exists():
                os.remove(temp_path)
    
    async def resize(self, file: UploadFile, width: int, height: int) -> dict:
        """Resize image to specified dimensions"""
        temp_path = await self._save_uploaded_file(file)
        
        try:
            img = Image.open(temp_path)
            resized = img.resize((width, height), Image.Resampling.LANCZOS)
            
            suffix = Path(file.filename).suffix if file.filename else '.png'
            output_filename = f"{uuid.uuid4()}{suffix}"
            output_path = TEMP_DIR / output_filename
            resized.save(output_path)
            
            return {
                "filename": output_filename,
                "original": file.filename,
                "dimensions": {"width": width, "height": height},
                "size": output_path.stat().st_size
            }
        finally:
            if temp_path.exists():
                os.remove(temp_path)
    
    async def create_passport_photo(self, file: UploadFile, size: str = "2x2") -> dict:
        """Create passport-sized photo"""
        if size not in self.PASSPORT_SIZES:
            size = "2x2"
        
        target_size = self.PASSPORT_SIZES[size]
        temp_path = await self._save_uploaded_file(file)
        
        try:
            img = Image.open(temp_path)
            
            # Calculate aspect ratio and resize
            img_ratio = img.width / img.height
            target_ratio = target_size[0] / target_size[1]
            
            if img_ratio > target_ratio:
                new_height = target_size[1]
                new_width = int(new_height * img_ratio)
            else:
                new_width = target_size[0]
                new_height = int(new_width / img_ratio)
            
            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            # Center crop
            left = (new_width - target_size[0]) // 2
            top = (new_height - target_size[1]) // 2
            img = img.crop((left, top, left + target_size[0], top + target_size[1]))
            
            output_filename = f"{uuid.uuid4()}_passport.png"
            output_path = TEMP_DIR / output_filename
            img.save(output_path)
            
            return {
                "filename": output_filename,
                "original": file.filename,
                "size_type": size,
                "dimensions": {"width": target_size[0], "height": target_size[1]},
                "size": output_path.stat().st_size
            }
        finally:
            if temp_path.exists():
                os.remove(temp_path)
    
    async def create_collage(self, files: list[UploadFile], layout: str = "grid", columns: int = 3) -> dict:
        """Create a collage from multiple images"""
        images = []
        temp_paths = []
        
        try:
            for file in files:
                temp_path = await self._save_uploaded_file(file)
                temp_paths.append(temp_path)
                images.append(Image.open(temp_path))
            
            if not images:
                return {"error": "No valid images provided"}
            
            # Determine cell size based on largest image
            max_width = max(img.width for img in images)
            max_height = max(img.height for img in images)
            cell_size = (max_width, max_height)
            
            # Calculate grid dimensions
            rows = (len(images) + columns - 1) // columns
            
            # Create collage canvas
            collage = Image.new('RGB', (cell_size[0] * columns, cell_size[1] * rows), (255, 255, 255))
            
            for i, img in enumerate(images):
                row = i // columns
                col = i % columns
                
                # Resize image to fit cell while maintaining aspect ratio
                img.thumbnail(cell_size, Image.Resampling.LANCZOS)
                
                # Center image in cell
                x = col * cell_size[0] + (cell_size[0] - img.width) // 2
                y = row * cell_size[1] + (cell_size[1] - img.height) // 2
                
                if img.mode == 'RGBA':
                    collage.paste(img, (x, y), img)
                else:
                    collage.paste(img, (x, y))
            
            output_filename = f"{uuid.uuid4()}_collage.png"
            output_path = TEMP_DIR / output_filename
            collage.save(output_path)
            
            return {
                "filename": output_filename,
                "image_count": len(images),
                "layout": layout,
                "grid": {"rows": rows, "columns": columns},
                "size": output_path.stat().st_size
            }
        finally:
            for path in temp_paths:
                if path.exists():
                    os.remove(path)
    
    async def apply_filter(self, file: UploadFile, filter_name: str) -> dict:
        """Apply filter to image"""
        filter_name = filter_name.lower()
        temp_path = await self._save_uploaded_file(file)
        
        try:
            img = Image.open(temp_path)
            
            if filter_name in self.FILTERS:
                filtered = img.filter(self.FILTERS[filter_name])
            elif filter_name == 'grayscale':
                filtered = img.convert('L').convert('RGB')
            elif filter_name == 'sepia':
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                pixels = img.load()
                for i in range(img.width):
                    for j in range(img.height):
                        r, g, b = pixels[i, j]
                        tr = int(0.393 * r + 0.769 * g + 0.189 * b)
                        tg = int(0.349 * r + 0.686 * g + 0.168 * b)
                        tb = int(0.272 * r + 0.534 * g + 0.131 * b)
                        pixels[i, j] = (min(255, tr), min(255, tg), min(255, tb))
                filtered = img
            elif filter_name == 'brightness':
                enhancer = ImageEnhance.Brightness(img)
                filtered = enhancer.enhance(1.3)
            elif filter_name == 'contrast':
                enhancer = ImageEnhance.Contrast(img)
                filtered = enhancer.enhance(1.3)
            else:
                return {"error": f"Unknown filter: {filter_name}"}
            
            suffix = Path(file.filename).suffix if file.filename else '.png'
            output_filename = f"{uuid.uuid4()}{suffix}"
            output_path = TEMP_DIR / output_filename
            filtered.save(output_path)
            
            return {
                "filename": output_filename,
                "original": file.filename,
                "filter": filter_name,
                "size": output_path.stat().st_size
            }
        finally:
            if temp_path.exists():
                os.remove(temp_path)
    
    async def ocr_scan(self, file: UploadFile) -> dict:
        """Extract text from image using OCR"""
        pytesseract = _get_tesseract()
        if not pytesseract:
            return {"error": "pytesseract not installed. Install with: pip install pytesseract"}
        
        temp_path = await self._save_uploaded_file(file)
        
        try:
            img = Image.open(temp_path)
            text = pytesseract.image_to_string(img)
            
            return {
                "original": file.filename,
                "text": text.strip(),
                "char_count": len(text.strip())
            }
        finally:
            if temp_path.exists():
                os.remove(temp_path)
    
    async def ai_check(self, file: UploadFile) -> dict:
        """Check if image is AI-generated (basic heuristic analysis)"""
        cv2_result = _get_cv2()
        if not cv2_result:
            return {"error": "opencv not installed. Install with: pip install opencv-python-headless"}
        
        cv2, np = cv2_result
        temp_path = await self._save_uploaded_file(file)
        
        try:
            img = cv2.imread(str(temp_path))
            if img is None:
                return {"error": "Could not read image"}
            
            # Basic analysis metrics
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            
            # Noise analysis
            noise = cv2.Laplacian(gray, cv2.CV_64F).var()
            
            # Edge analysis
            edges = cv2.Canny(gray, 100, 200)
            edge_density = np.count_nonzero(edges) / edges.size
            
            # Color uniformity
            hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
            color_std = np.std(hsv[:, :, 0])
            
            # Simple heuristic (not a real AI detector)
            ai_score = 0
            if noise < 100:
                ai_score += 30  # Low noise might indicate AI
            if edge_density < 0.05:
                ai_score += 20  # Very smooth edges
            if color_std < 30:
                ai_score += 20  # Uniform colors
            
            return {
                "original": file.filename,
                "ai_probability": min(ai_score, 100),
                "analysis": {
                    "noise_level": float(noise),
                    "edge_density": float(edge_density),
                    "color_uniformity": float(color_std)
                },
                "note": "This is a basic heuristic analysis, not a definitive AI detection"
            }
        finally:
            if temp_path.exists():
                os.remove(temp_path)
