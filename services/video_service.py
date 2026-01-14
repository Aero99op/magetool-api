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
import logging
from concurrent.futures import ThreadPoolExecutor
from utils.locking import add_active_file, remove_active_file

# Lazy imports - only load heavy libraries when needed
YTDLP_MODULE = None
HTTPX_CLIENT = None

def _get_ytdlp():
    global YTDLP_MODULE
    if YTDLP_MODULE is None:
        try:
            import yt_dlp
            YTDLP_MODULE = yt_dlp
        except ImportError:
            YTDLP_MODULE = False
    return YTDLP_MODULE

def _get_httpx():
    global HTTPX_CLIENT
    if HTTPX_CLIENT is None:
        try:
            import httpx
            HTTPX_CLIENT = httpx
        except ImportError:
            HTTPX_CLIENT = False
    return HTTPX_CLIENT

# Use TEMP_DIR from environment variable, fallback to ./temp for local dev
TEMP_DIR = Path(os.environ.get("TEMP_DIR", "./temp"))
TEMP_DIR.mkdir(parents=True, exist_ok=True)  # Ensure temp directory exists

# Cobalt API Configuration
# Primary: Self-hosted on Render, Fallbacks: Community instances
COBALT_API_URL = os.environ.get("COBALT_API_URL", "https://magetool-api-cobalt-docker.onrender.com")
COBALT_INSTANCES = [
    COBALT_API_URL,  # Self-hosted (PRIMARY)
    "https://cobalt-api.meowing.de",      # Fallback: 96% uptime
    "https://cobalt-backend.canine.tools", # Fallback: 80% uptime  
]
# Filter out empty strings
COBALT_INSTANCES = [url for url in COBALT_INSTANCES if url]

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
        """
        Download video from YouTube using hybrid approach:
        1. Try Cobalt API first (handles bot detection better)
        2. Fallback to yt-dlp if Cobalt fails
        """
        logger = logging.getLogger(__name__)
        
        # Try Cobalt API first
        logger.info(f"🚀 Attempting YouTube download via Cobalt API: {url}")
        cobalt_result = await self._download_via_cobalt(url)
        
        if not cobalt_result.get("error"):
            logger.info("✅ Cobalt API download successful!")
            return cobalt_result
        
        # Cobalt failed, fallback to yt-dlp
        logger.warning(f"⚠️ Cobalt API failed: {cobalt_result.get('error')}. Falling back to yt-dlp...")
        return await self._download_via_ytdlp(url)
    
    async def _download_via_cobalt(self, url: str) -> dict:
        """Download video using Cobalt API - tries multiple instances"""
        logger = logging.getLogger(__name__)
        httpx = _get_httpx()
        
        if not httpx:
            return {"error": "httpx not installed"}
        
        if not COBALT_INSTANCES:
            return {"error": "No Cobalt instances configured"}
        
        output_id = str(uuid.uuid4())
        output_filename = f"{output_id}.mp4"
        output_path = TEMP_DIR / output_filename
        
        last_error = "No instances available"
        
        for cobalt_url in COBALT_INSTANCES:
            try:
                # verify=False to handle self-signed certs on some community instances
                async with httpx.AsyncClient(timeout=120.0, verify=False) as client:
                    # Step 1: Request download URL from Cobalt
                    logger.info(f"📡 Trying Cobalt instance: {cobalt_url}")
                    
                    response = await client.post(
                        f"{cobalt_url}/",
                        json={
                            "url": url,
                            "videoQuality": "1080",
                            "youtubeVideoCodec": "h264",  # Max compatibility
                            "filenameStyle": "basic",
                        },
                        headers={
                            "Accept": "application/json",
                            "Content-Type": "application/json",
                        }
                    )
                    
                    if response.status_code != 200:
                        last_error = f"{cobalt_url} returned {response.status_code}"
                        logger.warning(f"⚠️ {last_error}")
                        continue  # Try next instance
                
                data = response.json()
                status = data.get("status")
                
                logger.info(f"📦 Cobalt response status: {status}")
                
                # Handle different response types
                if status == "error":
                    error_info = data.get("error", {})
                    error_code = error_info.get("code", "unknown") if isinstance(error_info, dict) else str(error_info)
                    last_error = f"Cobalt error: {error_code}"
                    logger.warning(f"⚠️ {last_error}")
                    continue  # Try next instance
                
                if status == "picker":
                    # Multiple options - pick first video
                    picker = data.get("picker", [])
                    if picker:
                        download_url = picker[0].get("url")
                        cobalt_filename = picker[0].get("filename", output_filename)
                    else:
                        last_error = "Cobalt returned picker with no items"
                        continue  # Try next instance
                elif status in ["tunnel", "redirect"]:
                    download_url = data.get("url")
                    cobalt_filename = data.get("filename", output_filename)
                else:
                    last_error = f"Unknown Cobalt status: {status}"
                    continue  # Try next instance
                
                if not download_url:
                    last_error = "Cobalt did not return download URL"
                    continue  # Try next instance
                
                logger.info(f"⬇️ Downloading from Cobalt tunnel: {download_url[:80]}...")
                
                # Step 2: Download the actual file
                video_response = await client.get(
                    download_url,
                    follow_redirects=True,
                    timeout=300.0  # 5 min timeout for large files
                )
                
                if video_response.status_code != 200:
                    last_error = f"Failed to download from Cobalt tunnel: {video_response.status_code}"
                    continue  # Try next instance
                
                # Save to file
                output_path.write_bytes(video_response.content)
                file_size = output_path.stat().st_size
                
                if file_size < 1000:  # Less than 1KB is likely an error
                    output_path.unlink(missing_ok=True)
                    last_error = "Downloaded file too small, likely an error page"
                    continue  # Try next instance
                
                logger.info(f"✅ Cobalt download complete: {file_size} bytes")
                
                # Extract title from filename if possible
                title = Path(cobalt_filename).stem if cobalt_filename else "YouTube Video"
                
                return {
                    "filename": output_filename,
                    "title": title,
                    "duration": 0,  # Cobalt doesn't provide duration
                    "size": file_size,
                    "source": "cobalt"
                }
                
            except Exception as e:
                logger.warning(f"⚠️ Cobalt instance {cobalt_url} failed: {e}")
                last_error = str(e)[:100]
                output_path.unlink(missing_ok=True)
                continue  # Try next instance
        
        # All instances failed
        return {"error": f"All Cobalt instances failed. Last error: {last_error}"}
    
    async def _download_via_ytdlp(self, url: str) -> dict:
        """Download video from YouTube using yt-dlp (fallback method)"""
        logger = logging.getLogger(__name__)
        
        yt_dlp = _get_ytdlp()
        if not yt_dlp:
            return {"error": "yt-dlp not installed. Install with: pip install yt-dlp"}
        
        output_id = str(uuid.uuid4())
        output_filename = f"{output_id}.mp4"
        # Use absolute path for output template
        output_template = str((TEMP_DIR / output_id).absolute())
        output_path = TEMP_DIR / output_filename
        
        logger.info(f"Starting YouTube download via yt-dlp for: {url}")
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
            'retries': 10,
            'fragment_retries': 10,
            'skip_unavailable_fragments': True,
            # Handle age-restricted content
            'age_limit': None,
            # Avoid throttling - increased sleep
            'sleep_interval': 3,
            'max_sleep_interval': 10,
            'sleep_interval_requests': 1,
            # Progress hooks for debugging
            'progress_hooks': [lambda d: logger.info(f"Download progress: {d.get('status', 'unknown')} - {d.get('_percent_str', 'N/A')}")],
            # User agent to avoid blocks
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
            },
            # Extract flat for playlists
            'noplaylist': True,
            # Ignore errors and continue
            'ignoreerrors': False,
            # === BYPASS OPTIONS ===
            # Geo bypass
            'geo_bypass': True,
            'geo_bypass_country': 'US',
            # Don't check certificates (sometimes helps)
            'nocheckcertificate': True,
        }

        # Cookie Bypass - The Real Fix
        # Users can provide cookies via env var YOUTUBE_COOKIES
        cookies_env = os.environ.get("YOUTUBE_COOKIES")
        cookies_file_path = None
        
        if cookies_env:
            logger.info("🍪 Custom cookies found in environment, applying bypass...")
            try:
                # Create a temporary cookies file
                cookies_file_path = TEMP_DIR / "cookies.txt"
                # If it's a file path string (e.g. from Render secret file)
                if os.path.isfile(cookies_env):
                    ydl_opts['cookiefile'] = cookies_env
                else:
                    # Write content to file - ensure Unix newlines (LF)
                    # Replace CRLF (\r\n) with LF (\n) effectively
                    clean_cookies = cookies_env.replace('\r\n', '\n').replace('\r', '\n')
                    cookies_file_path.write_text(clean_cookies, encoding='utf-8')
                    ydl_opts['cookiefile'] = str(cookies_file_path)
            except Exception as e:
                logger.error(f"Failed to process cookies: {e}")
        else:
            # Fallback for when no cookies are provided:
            # Use Android/iOS client to bypass bot detection (Only if NO cookies)
            # Mixing cookies with Android client spoofing often causes issues
            logger.info("📱 No cookies found, using Android client spoofing...")
            ydl_opts['extractor_args'] = {
                'youtube': {
                    'player_client': ['android', 'web'],
                    'player_skip': ['webpage', 'configs'],
                }
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
                "size": file_size,
                "source": "yt-dlp"
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
        finally:
            # Clean up cookies file
            if cookies_file_path and cookies_file_path.exists():
                try:
                    os.remove(cookies_file_path)
                except:
                    pass
    
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
            'retries': 10,
            'fragment_retries': 10,
            'sleep_interval': 2,
            'max_sleep_interval': 5,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
            },
            'progress_hooks': [lambda d: logger.info(f"Download progress: {d.get('status', 'unknown')}")],
            'geo_bypass': True,
            'nocheckcertificate': True,
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
        """
        Download YouTube video with real-time progress streaming.
        Uses hybrid approach: Cobalt API first, then yt-dlp fallback.
        """
        import asyncio
        from concurrent.futures import ThreadPoolExecutor
        
        logger = logging.getLogger(__name__)
        
        output_id = str(uuid.uuid4())
        output_filename = f"{output_id}.mp4"
        output_path = TEMP_DIR / output_filename
        
        # Lock file to prevent cleanup
        add_active_file(output_filename)
        
        # ===== TRY COBALT FIRST =====
        yield {"status": "starting", "message": "🚀 Trying Cobalt API..."}
        
        httpx = _get_httpx()
        cobalt_success = False
        
        if httpx and COBALT_INSTANCES:
            for cobalt_url in COBALT_INSTANCES:
                try:
                    # verify=False to handle self-signed certs on some community instances
                    async with httpx.AsyncClient(timeout=120.0, verify=False) as client:
                        yield {"status": "downloading", "percent": "5%", "percent_num": 5, "message": f"Trying {cobalt_url}..."}
                        
                        response = await client.post(
                            f"{cobalt_url}/",
                            json={
                                "url": url,
                                "videoQuality": "1080",
                                "youtubeVideoCodec": "h264",
                                "filenameStyle": "basic",
                            },
                            headers={
                                "Accept": "application/json",
                                "Content-Type": "application/json",
                            }
                        )
                        
                        if response.status_code == 200:
                            data = response.json()
                            status = data.get("status")
                            download_url = None
                            cobalt_filename = output_filename
                            
                            if status in ["tunnel", "redirect"]:
                                download_url = data.get("url")
                                cobalt_filename = data.get("filename", output_filename)
                            elif status == "picker":
                                picker = data.get("picker", [])
                                if picker:
                                    download_url = picker[0].get("url")
                                    cobalt_filename = picker[0].get("filename", output_filename)
                            
                            if download_url:
                                yield {"status": "downloading", "percent": "15%", "percent_num": 15, "message": "Downloading via Cobalt..."}
                                
                                # Stream download with progress
                                async with client.stream("GET", download_url, follow_redirects=True, timeout=300.0) as stream:
                                    if stream.status_code == 200:
                                        total = int(stream.headers.get("content-length", 0))
                                        downloaded = 0
                                        chunks = []
                                        
                                        async for chunk in stream.aiter_bytes(chunk_size=65536):
                                            chunks.append(chunk)
                                            downloaded += len(chunk)
                                            if total > 0:
                                                pct = 15 + int((downloaded / total) * 80)
                                                yield {
                                                    "status": "downloading",
                                                    "percent": f"{pct}%",
                                                    "percent_num": pct,
                                                    "downloaded": f"{downloaded // (1024*1024)}MB",
                                                    "total": f"{total // (1024*1024)}MB",
                                                }
                                        
                                        output_path.write_bytes(b"".join(chunks))
                                        file_size = output_path.stat().st_size
                                        
                                        if file_size > 1000:
                                            title = Path(cobalt_filename).stem if cobalt_filename else "YouTube Video"
                                            yield {
                                                "status": "complete",
                                                "filename": output_filename,
                                                "title": title,
                                                "duration": 0,
                                                "size": file_size,
                                                "source": "cobalt"
                                            }
                                            remove_active_file(output_filename)
                                            cobalt_success = True
                                            return  # Success! Exit the generator
                                            
                except Exception as e:
                    logger.warning(f"Cobalt instance {cobalt_url} failed: {e}")
                    output_path.unlink(missing_ok=True)
                    continue  # Try next instance
        
        if cobalt_success:
            return
        
        # ===== FALLBACK TO YT-DLP =====
        yield {"status": "starting", "message": "⚠️ Cobalt unavailable, using yt-dlp..."}
        
        yt_dlp = _get_ytdlp()
        if not yt_dlp:
            yield {"status": "error", "error": "yt-dlp not installed"}
            remove_active_file(output_filename)
            return
        
        output_template = str((TEMP_DIR / output_id).absolute())
        progress_queue = asyncio.Queue()
        loop = asyncio.get_event_loop()
        
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
            'retries': 10,
            'fragment_retries': 10,
            'skip_unavailable_fragments': True,
            'noplaylist': True,
            'sleep_interval': 3,
            'max_sleep_interval': 10,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
            },
            'progress_hooks': [progress_hook],
            # Bypass options
            'geo_bypass': True,
            'geo_bypass_country': 'US',
            'nocheckcertificate': True,
        }

        # Cookie Bypass - The Real Fix
        cookies_env = os.environ.get("YOUTUBE_COOKIES")
        cookies_file_path = None
        
        if cookies_env:
            logger.info("🍪 [STREAM] Custom cookies found in environment!")
            try:
                cookies_file_path = TEMP_DIR / f"cookies_{output_id}.txt"
                if os.path.isfile(cookies_env):
                    ydl_opts['cookiefile'] = cookies_env
                    logger.info(f"🍪 [STREAM] Using cookies file: {cookies_env}")
                else:
                    # Replace CRLF with LF
                    clean_cookies = cookies_env.replace('\r\n', '\n').replace('\r', '\n')
                    cookies_file_path.write_text(clean_cookies, encoding='utf-8')
                    ydl_opts['cookiefile'] = str(cookies_file_path)
                    logger.info(f"🍪 [STREAM] Wrote cookies to: {cookies_file_path}")
            except Exception as e:
                logger.error(f"🍪 [STREAM] Failed to process cookies: {e}")
        else:
            logger.info("📱 [STREAM] No cookies found, using Android client spoofing...")
            # Only use Android client if NO cookies
            ydl_opts['extractor_args'] = {
                'youtube': {
                    'player_client': ['android', 'web'],
                    'player_skip': ['webpage', 'configs'],
                }
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
                # Cleanup cookies file
                if cookies_file_path and cookies_file_path.exists():
                    try:
                        os.remove(cookies_file_path)
                    except:
                        pass
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
            'retries': 10,
            'fragment_retries': 10,
            'sleep_interval': 2,
            'max_sleep_interval': 5,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
            },
            'progress_hooks': [progress_hook],
            'geo_bypass': True,
            'nocheckcertificate': True,
        }

        # Cookie Bypass - The Real Fix
        cookies_env = os.environ.get("YOUTUBE_COOKIES")
        cookies_file_path = None
        
        if cookies_env:
            try:
                cookies_file_path = TEMP_DIR / f"cookies_{output_id}.txt"
                if os.path.isfile(cookies_env):
                    ydl_opts['cookiefile'] = cookies_env
                else:
                    # Replace CRLF with LF
                    clean_cookies = cookies_env.replace('\r\n', '\n').replace('\r', '\n')
                    cookies_file_path.write_text(clean_cookies, encoding='utf-8')
                    ydl_opts['cookiefile'] = str(cookies_file_path)
            except Exception as e:
                pass 
        
        
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
                # Cleanup cookies file
                if cookies_file_path and cookies_file_path.exists():
                    try:
                        os.remove(cookies_file_path)
                    except:
                        pass
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
