"""
Audio Service - Magetool
Handles all audio processing operations
"""

from fastapi import UploadFile
from pathlib import Path
import uuid
import os
import subprocess

# Optional imports with fallbacks
try:
    from pydub import AudioSegment
    PYDUB_AVAILABLE = True
except ImportError:
    PYDUB_AVAILABLE = False

try:
    from mutagen import File as MutagenFile
    from mutagen.easyid3 import EasyID3
    MUTAGEN_AVAILABLE = True
except ImportError:
    MUTAGEN_AVAILABLE = False

try:
    import yt_dlp
    YTDLP_AVAILABLE = True
except ImportError:
    YTDLP_AVAILABLE = False

TEMP_DIR = Path("./temp")

class AudioService:
    """Service for audio processing operations"""
    
    SUPPORTED_FORMATS = ['mp3', 'wav', 'ogg', 'flac', 'aac', 'm4a', 'wma']
    
    async def _save_uploaded_file(self, file: UploadFile) -> Path:
        """Save uploaded file to temp directory"""
        content = await file.read()
        suffix = Path(file.filename).suffix if file.filename else '.mp3'
        temp_path = TEMP_DIR / f"{uuid.uuid4()}{suffix}"
        temp_path.write_bytes(content)
        return temp_path
    
    async def convert_format(self, file: UploadFile, target_format: str) -> dict:
        """Convert audio to target format using pydub"""
        target_format = target_format.lower().strip('.')
        if target_format not in self.SUPPORTED_FORMATS:
            return {"error": f"Unsupported format: {target_format}"}
        
        if not PYDUB_AVAILABLE:
            return {"error": "pydub not installed. Install with: pip install pydub"}
        
        temp_path = await self._save_uploaded_file(file)
        
        try:
            # Determine input format
            input_format = temp_path.suffix.lower().strip('.')
            if input_format == 'mp3':
                audio = AudioSegment.from_mp3(temp_path)
            elif input_format == 'wav':
                audio = AudioSegment.from_wav(temp_path)
            elif input_format == 'ogg':
                audio = AudioSegment.from_ogg(temp_path)
            elif input_format == 'flac':
                audio = AudioSegment.from_file(temp_path, format='flac')
            else:
                audio = AudioSegment.from_file(temp_path)
            
            output_filename = f"{uuid.uuid4()}.{target_format}"
            output_path = TEMP_DIR / output_filename
            
            # Specialized handling for problematic formats
            export_args = {}
            target_format_lower = target_format.lower()
            
            if target_format_lower == 'm4a':
                export_args = {
                    'format': 'ipod',
                    'parameters': ["-strict", "-2"]  # For experimental codecs if needed
                }
            elif target_format_lower == 'aac':
                 export_args = {
                    'format': 'adts', # ADTS container for raw AAC
                    'parameters': ["-strict", "-2"]
                }
            elif target_format_lower == 'wma':
                 export_args = {
                    'format': 'asf',  # WMA usually lives in ASF container
                    'codec': 'wmav2'  # Standard WMA codec
                }
            else:
                export_args = {'format': target_format}
                
            audio.export(output_path, **export_args)
            
            return {
                "filename": output_filename,
                "original": file.filename,
                "format": target_format,
                "duration_ms": len(audio),
                "size": output_path.stat().st_size
            }
        except Exception as e:
            return {"error": str(e)}
        finally:
            if temp_path.exists():
                os.remove(temp_path)
    
    async def trim(self, file: UploadFile, start_time: float, end_time: float) -> dict:
        """Trim audio to specified time range (in seconds)"""
        if not PYDUB_AVAILABLE:
            return {"error": "pydub not installed. Install with: pip install pydub"}
        
        temp_path = await self._save_uploaded_file(file)
        
        try:
            audio = AudioSegment.from_file(temp_path)
            
            # Convert seconds to milliseconds
            start_ms = int(start_time * 1000)
            end_ms = int(end_time * 1000)
            
            if start_ms < 0 or end_ms > len(audio) or start_ms >= end_ms:
                return {"error": "Invalid time range"}
            
            trimmed = audio[start_ms:end_ms]
            
            suffix = Path(file.filename).suffix if file.filename else '.mp3'
            output_filename = f"{uuid.uuid4()}{suffix}"
            output_path = TEMP_DIR / output_filename
            
            output_format = suffix.lower().strip('.')
            if output_format not in self.SUPPORTED_FORMATS:
                output_format = 'mp3'
            
            trimmed.export(output_path, format=output_format)
            
            return {
                "filename": output_filename,
                "original": file.filename,
                "original_duration_ms": len(audio),
                "trimmed_duration_ms": len(trimmed),
                "start_time": start_time,
                "end_time": end_time,
                "size": output_path.stat().st_size
            }
        except Exception as e:
            return {"error": str(e)}
        finally:
            if temp_path.exists():
                os.remove(temp_path)
    
    async def identify(self, file: UploadFile) -> dict:
        """Identify audio metadata"""
        temp_path = await self._save_uploaded_file(file)
        
        try:
            metadata = {
                "original": file.filename,
                "title": None,
                "artist": None,
                "album": None,
                "duration": None,
                "bitrate": None,
            }
            
            if MUTAGEN_AVAILABLE:
                try:
                    audio = MutagenFile(temp_path, easy=True)
                    if audio:
                        metadata["duration"] = getattr(audio.info, 'length', None)
                        metadata["bitrate"] = getattr(audio.info, 'bitrate', None)
                        
                        if hasattr(audio, 'tags') and audio.tags:
                            metadata["title"] = audio.tags.get('title', [None])[0]
                            metadata["artist"] = audio.tags.get('artist', [None])[0]
                            metadata["album"] = audio.tags.get('album', [None])[0]
                except:
                    pass
            
            if PYDUB_AVAILABLE and metadata["duration"] is None:
                try:
                    audio = AudioSegment.from_file(temp_path)
                    metadata["duration"] = len(audio) / 1000.0  # Convert ms to seconds
                except:
                    pass
            
            return metadata
        finally:
            if temp_path.exists():
                os.remove(temp_path)
    
    async def download_from_url(self, url: str) -> dict:
        """Download audio from URL using yt-dlp"""
        if not YTDLP_AVAILABLE:
            return {"error": "yt-dlp not installed. Install with: pip install yt-dlp"}
        
        output_filename = f"{uuid.uuid4()}.mp3"
        output_path = TEMP_DIR / output_filename
        
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': str(output_path.with_suffix('')),
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
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
            'geo_bypass': True,
            'nocheckcertificate': True,
        }

        # Cookie Bypass - The Real Fix
        cookies_env = os.environ.get("YOUTUBE_COOKIES")
        cookies_file_path = None
        
        if cookies_env:
            try:
                cookies_file_path = TEMP_DIR / f"cookies_{uuid.uuid4()}.txt"
                if os.path.isfile(cookies_env):
                    ydl_opts['cookiefile'] = cookies_env
                else:
                    # Replace CRLF with LF
                    clean_cookies = cookies_env.replace('\r\n', '\n').replace('\r', '\n')
                    cookies_file_path.write_text(clean_cookies, encoding='utf-8')
                    ydl_opts['cookiefile'] = str(cookies_file_path)
            except Exception as e:
                pass
        else:
             # Only use Android client if NO cookies
            ydl_opts['extractor_args'] = {
                'youtube': {
                    'player_client': ['android', 'web'],
                    'player_skip': ['webpage', 'configs'],
                }
            }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                title = info.get('title', 'Unknown')
                duration = info.get('duration', 0)
            
            # Check for output file
            if not output_path.exists():
                # yt-dlp might add .mp3 extension
                mp3_path = output_path.with_suffix('.mp3')
                if mp3_path.exists():
                    output_path = mp3_path
                    output_filename = mp3_path.name
            
            return {
                "filename": output_filename,
                "title": title,
                "duration": duration,
                "size": output_path.stat().st_size if output_path.exists() else 0
            }
        except Exception as e:
            return {"error": str(e)}
        finally:
            # Cleanup cookies file
            if cookies_file_path and cookies_file_path.exists():
                try:
                    os.remove(cookies_file_path)
                except:
                    pass
