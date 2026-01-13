"""
Video Service - Magetool
Handles all video processing operations
"""

from fastapi import UploadFile
from pathlib import Path
import uuid
import os
import subprocess
import json
from concurrent.futures import ThreadPoolExecutor
from utils.locking import add_active_file, remove_active_file

# Lazy imports - only load heavy libraries when needed
YTDLP_MODULE = None

def _get_ytdlp():
    global YTDLP_MODULE
    if YTDLP_MODULE is None:
        try:
            import yt_dlp
            YTDLP_MODULE = yt_dlp
        except ImportError:
            YTDLP_MODULE = False
    return YTDLP_MODULE

TEMP_DIR = Path("./temp")

class VideoService:
    """Service for video processing operations"""
    
    SUPPORTED_FORMATS = ['mp4', 'avi', 'mkv', 'mov', 'webm', 'flv', 'wmv']
    
    async def _save_uploaded_file(self, file: UploadFile) -> Path:
        """Save uploaded file to temp directory"""
        content = await file.read()
        suffix = Path(file.filename).suffix if file.filename else '.mp4'
        temp_path = TEMP_DIR / f"{uuid.uuid4()}{suffix}"
        temp_path.write_bytes(content)
        return temp_path
    
    def _get_ffmpeg_path(self) -> str:
        """Get FFmpeg executable path"""
        return "ffmpeg"  # Assumes ffmpeg is in PATH
    
    async def convert_format(self, file: UploadFile, target_format: str) -> dict:
        """Convert video to target format using FFmpeg"""
        target_format = target_format.lower().strip('.')
        if target_format not in self.SUPPORTED_FORMATS:
            return {"error": f"Unsupported format: {target_format}"}
        
        temp_path = await self._save_uploaded_file(file)
        
        try:
            output_filename = f"{uuid.uuid4()}.{target_format}"
            output_path = TEMP_DIR / output_filename
            
            cmd = [
                self._get_ffmpeg_path(),
                '-i', str(temp_path),
                '-y',  # Overwrite output
                str(output_path)
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                return {"error": f"FFmpeg error: {result.stderr[:500]}"}
            
            return {
                "filename": output_filename,
                "original": file.filename,
                "format": target_format,
                "size": output_path.stat().st_size
            }
        finally:
            if temp_path.exists():
                os.remove(temp_path)
    
    async def download_youtube(self, url: str) -> dict:
        """Download video from YouTube using yt-dlp"""
        import logging
        logger = logging.getLogger(__name__)
        
        yt_dlp = _get_ytdlp()
        if not yt_dlp:
            return {"error": "yt-dlp not installed. Install with: pip install yt-dlp"}
        
        output_id = str(uuid.uuid4())
        output_filename = f"{output_id}.mp4"
        # Use absolute path for output template
        output_template = str((TEMP_DIR / output_id).absolute())
        output_path = TEMP_DIR / output_filename
        
        logger.info(f"Starting YouTube download for: {url}")
        logger.info(f"Output template: {output_template}")
        
        ydl_opts = {
            # Format selection - try multiple fallbacks
            'format': 'bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/bestvideo[height<=1080]+bestaudio/best[height<=1080]/best',
            'outtmpl': output_template + '.%(ext)s',
            'merge_output_format': 'mp4',
            # Don't suppress output - we need to see errors
            'quiet': False,
            'no_warnings': False,
            'verbose': True,
            # Handle rate limiting and retries
            'retries': 3,
            'fragment_retries': 3,
            'skip_unavailable_fragments': True,
            # Handle age-restricted content
            'age_limit': None,
            # Avoid throttling
            'sleep_interval': 1,
            'max_sleep_interval': 5,
            # Progress hooks for debugging
            'progress_hooks': [lambda d: logger.info(f"Download progress: {d.get('status', 'unknown')} - {d.get('_percent_str', 'N/A')}")],
            # User agent to avoid blocks
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            },
            # Extract flat for playlists
            'noplaylist': True,
            # Ignore errors and continue
            'ignoreerrors': False,
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                logger.info("Extracting video info...")
                info = ydl.extract_info(url, download=True)
                title = info.get('title', 'Unknown')
                duration = info.get('duration', 0)
                logger.info(f"Downloaded: {title} (duration: {duration}s)")
            
            # Find the actual output file - check multiple extensions
            found_file = None
            for ext in ['.mp4', '.webm', '.mkv', '.m4a', '.mp3']:
                check_path = TEMP_DIR / f"{output_id}{ext}"
                logger.info(f"Checking for file: {check_path}")
                if check_path.exists():
                    logger.info(f"Found file: {check_path}")
                    found_file = check_path
                    break
            
            # Also check if yt-dlp added something extra to filename
            if not found_file:
                for file in TEMP_DIR.iterdir():
                    if file.stem.startswith(output_id):
                        logger.info(f"Found file with prefix: {file}")
                        found_file = file
                        break
            
            if not found_file:
                # List all files in temp for debugging
                all_files = list(TEMP_DIR.iterdir())
                logger.error(f"File not found! Temp directory contents: {[f.name for f in all_files]}")
                return {"error": "Download completed but file not found. Check server logs for details."}
            
            # Rename to .mp4 if needed
            final_path = TEMP_DIR / output_filename
            if found_file != final_path:
                if found_file.suffix != '.mp4':
                    # If it's not mp4, we may need to convert or just rename
                    os.rename(found_file, final_path)
                else:
                    final_path = found_file
                    output_filename = found_file.name
            
            file_size = final_path.stat().st_size
            logger.info(f"Final file: {final_path}, size: {file_size} bytes")
            
            return {
                "filename": output_filename,
                "title": title,
                "duration": duration,
                "size": file_size
            }
        except yt_dlp.utils.DownloadError as e:
            error_msg = str(e)
            logger.error(f"yt-dlp DownloadError: {error_msg}")
            
            # Provide helpful error messages
            if 'DRM' in error_msg or 'drm' in error_msg.lower():
                return {"error": "This video is DRM protected and cannot be downloaded. Try a different video."}
            elif 'Private video' in error_msg:
                return {"error": "This video is private and cannot be accessed."}
            elif 'Video unavailable' in error_msg:
                return {"error": "This video is unavailable or has been removed."}
            elif 'age' in error_msg.lower():
                return {"error": "This video is age-restricted. Login may be required."}
            elif 'Sign in' in error_msg:
                return {"error": "This video requires login to access."}
            else:
                return {"error": f"Download failed: {error_msg[:200]}"}
        except Exception as e:
            logger.exception(f"Unexpected error downloading YouTube video: {e}")
            return {"error": f"Unexpected error: {str(e)[:200]}"}
    
    async def download_instagram(self, url: str) -> dict:
        """Download video from Instagram using yt-dlp"""
        import logging
        logger = logging.getLogger(__name__)
        
        yt_dlp = _get_ytdlp()
        if not yt_dlp:
            return {"error": "yt-dlp not installed. Install with: pip install yt-dlp"}
        
        output_id = str(uuid.uuid4())
        output_filename = f"{output_id}.mp4"
        output_template = str((TEMP_DIR / output_id).absolute())
        
        logger.info(f"Starting Instagram download for: {url}")
        
        ydl_opts = {
            'format': 'best[ext=mp4]/best',
            'outtmpl': output_template + '.%(ext)s',
            'quiet': False,
            'no_warnings': False,
            'verbose': True,
            'retries': 3,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            },
            'progress_hooks': [lambda d: logger.info(f"Download progress: {d.get('status', 'unknown')}")],
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                logger.info("Extracting Instagram video info...")
                info = ydl.extract_info(url, download=True)
                title = info.get('title', 'Instagram Video') if info else 'Instagram Video'
                logger.info(f"Downloaded: {title}")
            
            # Find the actual output file
            found_file = None
            for ext in ['.mp4', '.webm', '.mkv', '.m4a']:
                check_path = TEMP_DIR / f"{output_id}{ext}"
                if check_path.exists():
                    logger.info(f"Found file: {check_path}")
                    found_file = check_path
                    break
            
            if not found_file:
                for file in TEMP_DIR.iterdir():
                    if file.stem.startswith(output_id):
                        found_file = file
                        break
            
            if not found_file:
                all_files = list(TEMP_DIR.iterdir())
                logger.error(f"File not found! Temp directory contents: {[f.name for f in all_files]}")
                return {"error": "Download completed but file not found. Check server logs."}
            
            # Rename to .mp4 if needed
            final_path = TEMP_DIR / output_filename
            if found_file != final_path:
                os.rename(found_file, final_path)
            
            file_size = final_path.stat().st_size
            logger.info(f"Final file: {final_path}, size: {file_size} bytes")
            
            return {
                "filename": output_filename,
                "title": title,
                "size": file_size
            }
        except yt_dlp.utils.DownloadError as e:
            error_msg = str(e)
            logger.error(f"yt-dlp DownloadError (Instagram): {error_msg}")
            
            if 'login' in error_msg.lower() or 'Log in' in error_msg:
                return {"error": "Instagram requires login to access this content. Try a public post."}
            elif 'Private' in error_msg or 'private' in error_msg.lower():
                return {"error": "This is a private Instagram post."}
            elif 'not found' in error_msg.lower() or '404' in error_msg:
                return {"error": "Instagram post not found or has been deleted."}
            else:
                return {"error": f"Instagram download failed: {error_msg[:200]}"}
        except Exception as e:
            logger.exception(f"Unexpected error downloading Instagram video: {e}")
            return {"error": f"Unexpected error: {str(e)[:200]}"}
    
    async def download_shorts(self, url: str) -> dict:
        """Download YouTube Shorts (uses same method as YouTube)"""
        return await self.download_youtube(url)
    
    async def download_reels(self, url: str) -> dict:
        """Download Instagram Reels (uses same method as Instagram)"""
        return await self.download_instagram(url)
    
    async def download_youtube_with_progress(self, url: str):
        """Download YouTube video with real-time progress streaming"""
        import logging
        import asyncio
        from concurrent.futures import ThreadPoolExecutor
        
        logger = logging.getLogger(__name__)
        yt_dlp = _get_ytdlp()
        
        if not yt_dlp:
            yield {"status": "error", "error": "yt-dlp not installed"}
            return
        
        output_id = str(uuid.uuid4())
        output_filename = f"{output_id}.mp4"
        output_template = str((TEMP_DIR / output_id).absolute())
        
        # Lock file to prevent cleanup
        add_active_file(output_filename)
        
        # Progress state shared between threads
        progress_queue = asyncio.Queue()
        
        def progress_hook(d):
            """Called by yt-dlp with download progress"""
            status = d.get('status', 'unknown')
            
            if status == 'downloading':
                progress_data = {
                    "status": "downloading",
                    "percent": d.get('_percent_str', '0%').strip(),
                    "percent_num": float(d.get('downloaded_bytes', 0)) / float(d.get('total_bytes', 1) or 1) * 100,
                    "speed": d.get('_speed_str', 'N/A'),
                    "eta": d.get('_eta_str', 'N/A'),
                    "downloaded": d.get('_downloaded_bytes_str', '0B'),
                    "total": d.get('_total_bytes_str', 'Unknown'),
                }
                asyncio.run_coroutine_threadsafe(progress_queue.put(progress_data), loop)
            elif status == 'finished':
                asyncio.run_coroutine_threadsafe(
                    progress_queue.put({"status": "processing", "message": "Merging video and audio..."}),
                    loop
                )
# ... code continues ...
        
        ydl_opts = {
            'format': 'bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/bestvideo[height<=1080]+bestaudio/best[height<=1080]/best',
            'outtmpl': output_template + '.%(ext)s',
            'merge_output_format': 'mp4',
            'quiet': True,
            'no_warnings': True,
            'retries': 3,
            'fragment_retries': 3,
            'skip_unavailable_fragments': True,
            'noplaylist': True,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            },
            'progress_hooks': [progress_hook],
        }
        
        loop = asyncio.get_event_loop()
        result_holder = {"result": None, "error": None, "title": "Unknown"}
        
        def run_download():
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    result_holder["title"] = info.get('title', 'Unknown')
                    result_holder["duration"] = info.get('duration', 0)
                    result_holder["result"] = "success"
            except yt_dlp.utils.DownloadError as e:
                result_holder["error"] = str(e)
            except Exception as e:
                result_holder["error"] = str(e)
            finally:
                asyncio.run_coroutine_threadsafe(progress_queue.put(None), loop)
        
        # Start download in thread
        executor = ThreadPoolExecutor(max_workers=1)
        executor.submit(run_download)
        
        # Yield initial status
        yield {"status": "starting", "message": "Fetching video information..."}
        
        # Stream progress updates
        while True:
            try:
                progress = await asyncio.wait_for(progress_queue.get(), timeout=0.5)
                if progress is None:
                    break
                yield progress
            except asyncio.TimeoutError:
                continue
        
        executor.shutdown(wait=True)
        
        # Start of error and result handling...
        # We need to unlock if error happens
        if result_holder["error"]:
            error_msg = result_holder["error"]
            remove_active_file(output_filename) # Unlock on error
            if 'DRM' in error_msg or 'drm' in error_msg.lower():
                yield {"status": "error", "error": "This video is DRM protected and cannot be downloaded."}
            # ... (rest of error handling)
            elif 'Private video' in error_msg:
                yield {"status": "error", "error": "This video is private."}
            elif 'Video unavailable' in error_msg:
                yield {"status": "error", "error": "This video is unavailable or has been removed."}
            else:
                yield {"status": "error", "error": f"Download failed: {error_msg[:200]}"}
            return
        
        # Find the output file
        found_file = None
        for ext in ['.mp4', '.webm', '.mkv']:
            check_path = TEMP_DIR / f"{output_id}{ext}"
            if check_path.exists():
                found_file = check_path
                break
        
        if not found_file:
            for file in TEMP_DIR.iterdir():
                if file.stem.startswith(output_id):
                    found_file = file
                    break
        
        if not found_file:
            yield {"status": "error", "error": "Download completed but file not found."}
            return
        
        # Rename to .mp4 if needed
        final_path = TEMP_DIR / output_filename
        if found_file != final_path:
            os.rename(found_file, final_path)
        
        file_size = final_path.stat().st_size
        
        yield {
            "status": "complete",
            "filename": output_filename,
            "title": result_holder.get("title", "Unknown"),
            "duration": result_holder.get("duration", 0),
            "size": file_size
        }
        
        # Unlock after successful completion (cleanup logic will eventually delete it after user downloads, or delayed delete kicks in)
        # But for 'locking' purposes, it is no longer being WRITTEN to.
        # So we can remove the lock. The 'Janitor' cleans old files.
        remove_active_file(output_filename)
    
    async def download_instagram_with_progress(self, url: str):
        """Download Instagram video with real-time progress streaming"""
        import logging
        import asyncio
        from concurrent.futures import ThreadPoolExecutor
        
        logger = logging.getLogger(__name__)
        yt_dlp = _get_ytdlp()
        
        if not yt_dlp:
            yield {"status": "error", "error": "yt-dlp not installed"}
            return
        
        output_id = str(uuid.uuid4())
        output_filename = f"{output_id}.mp4"
        output_template = str((TEMP_DIR / output_id).absolute())
        
        # Lock file
        add_active_file(output_filename)
        
        progress_queue = asyncio.Queue()
        loop = asyncio.get_event_loop()
        
        def progress_hook(d):
            status = d.get('status', 'unknown')
            if status == 'downloading':
                progress_data = {
                    "status": "downloading",
                    "percent": d.get('_percent_str', '0%').strip(),
                    "percent_num": float(d.get('downloaded_bytes', 0)) / float(d.get('total_bytes', 1) or 1) * 100,
                    "speed": d.get('_speed_str', 'N/A'),
                    "downloaded": d.get('_downloaded_bytes_str', '0B'),
                }
                asyncio.run_coroutine_threadsafe(progress_queue.put(progress_data), loop)
            elif status == 'finished':
                asyncio.run_coroutine_threadsafe(
                    progress_queue.put({"status": "processing", "message": "Finalizing..."}),
                    loop
                )
        
        ydl_opts = {
            'format': 'best[ext=mp4]/best',
            'outtmpl': output_template + '.%(ext)s',
            'quiet': True,
            'no_warnings': True,
            'retries': 3,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            },
            'progress_hooks': [progress_hook],
        }
        
        result_holder = {"result": None, "error": None, "title": "Instagram Video"}
        
        def run_download():
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    result_holder["title"] = info.get('title', 'Instagram Video') if info else 'Instagram Video'
                    result_holder["result"] = "success"
            except yt_dlp.utils.DownloadError as e:
                result_holder["error"] = str(e)
            except Exception as e:
                result_holder["error"] = str(e)
            finally:
                asyncio.run_coroutine_threadsafe(progress_queue.put(None), loop)
        
        executor = ThreadPoolExecutor(max_workers=1)
        executor.submit(run_download)
        
        yield {"status": "starting", "message": "Fetching video information..."}
        
        while True:
            try:
                progress = await asyncio.wait_for(progress_queue.get(), timeout=0.5)
                if progress is None:
                    break
                yield progress
            except asyncio.TimeoutError:
                continue
        
        executor.shutdown(wait=True)
        
        if result_holder["error"]:
            error_msg = result_holder["error"]
            remove_active_file(output_filename) # Unlock on error
            if 'login' in error_msg.lower():
                yield {"status": "error", "error": "Instagram requires login to access this content."}
            elif 'Private' in error_msg or 'private' in error_msg.lower():
                yield {"status": "error", "error": "This is a private Instagram post."}
            else:
                yield {"status": "error", "error": f"Download failed: {error_msg[:200]}"}
            return
        
        # Find output file
        found_file = None
        for ext in ['.mp4', '.webm', '.mkv']:
            check_path = TEMP_DIR / f"{output_id}{ext}"
            if check_path.exists():
                found_file = check_path
                break
        
        if not found_file:
            for file in TEMP_DIR.iterdir():
                if file.stem.startswith(output_id):
                    found_file = file
                    break
        
        if not found_file:
            yield {"status": "error", "error": "Download completed but file not found."}
            return
        
        final_path = TEMP_DIR / output_filename
        if found_file != final_path:
            os.rename(found_file, final_path)
        
        file_size = final_path.stat().st_size
        
        yield {
            "status": "complete",
            "filename": output_filename,
            "title": result_holder.get("title", "Instagram Video"),
            "size": file_size
        }
        
        # Unlock after successful completion
        remove_active_file(output_filename)

    async def extract_audio(self, file: UploadFile) -> dict:
        """Extract audio from video"""
        temp_path = await self._save_uploaded_file(file)
        
        try:
            output_filename = f"{uuid.uuid4()}.mp3"
            output_path = TEMP_DIR / output_filename
            
            cmd = [
                self._get_ffmpeg_path(),
                '-i', str(temp_path),
                '-vn',  # No video
                '-acodec', 'libmp3lame',
                '-ab', '192k',
                '-y',
                str(output_path)
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                return {"error": f"FFmpeg error: {result.stderr[:500]}"}
            
            return {
                "filename": output_filename,
                "original": file.filename,
                "format": "mp3",
                "size": output_path.stat().st_size
            }
        finally:
            if temp_path.exists():
                os.remove(temp_path)
    
    async def ai_identify(self, file: UploadFile) -> dict:
        """Basic AI detection for videos (frame analysis)"""
        temp_path = await self._save_uploaded_file(file)
        
        try:
            # Basic metadata analysis
            cmd = [
                'ffprobe',
                '-v', 'quiet',
                '-print_format', 'json',
                '-show_format',
                '-show_streams',
                str(temp_path)
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                return {"error": "Could not analyze video"}
            
            try:
                metadata = json.loads(result.stdout)
            except:
                metadata = {}
            
            # Extract basic info
            format_info = metadata.get('format', {})
            streams = metadata.get('streams', [])
            
            video_stream = next((s for s in streams if s.get('codec_type') == 'video'), {})
            
            return {
                "original": file.filename,
                "ai_probability": 50,  # Placeholder - real detection would need ML model
                "analysis": {
                    "codec": video_stream.get('codec_name', 'unknown'),
                    "resolution": f"{video_stream.get('width', 0)}x{video_stream.get('height', 0)}",
                    "duration": float(format_info.get('duration', 0)),
                    "bitrate": int(format_info.get('bit_rate', 0))
                },
                "note": "Video AI detection requires specialized ML models"
            }
        finally:
            if temp_path.exists():
                os.remove(temp_path)
