from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
import yt_dlp
import os
import uuid
import time
import asyncio

app = FastAPI(title="Azure YouTube Downloader API")

# Allow CORS for the frontend to connect
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"]
)

# Request Models
class VideoRequest(BaseModel):
    url: str

class DownloadRequest(BaseModel):
    url: str
    format_id: str

def cleanup_file(filepath: str):
    """Background task to remove the file after it's been downloaded."""
    try:
        # Wait a bit to ensure the OS has released the file lock
        time.sleep(5)
        if os.path.exists(filepath):
            os.remove(filepath)
            print(f"Cleaned up temporary file: {filepath}")
    except Exception as e:
        print(f"Error cleaning up file {filepath}: {e}")

@app.get("/")
def read_root():
    return {"status": "ok", "message": "YouTube Downloader API is running"}

@app.post("/api/get-info")
async def get_video_info(request: VideoRequest):
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'nocheckcertificate': True,
            'geo_bypass': True,
            'socket_timeout': 10,
            'cookiefile': 'youtube.com_cookies.txt',
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(request.url, download=False)
            
            # Filter and organize formats
            formats = []
            for f in info.get('formats', []):
                vcodec = f.get('vcodec')
                acodec = f.get('acodec')
                
                # Filter out storyboards
                if vcodec != 'none' or acodec != 'none':
                    # Determine type
                    if vcodec != 'none' and acodec != 'none':
                        stream_type = 'Combined'
                    elif vcodec != 'none' and acodec == 'none':
                        stream_type = 'Video Only'
                    elif vcodec == 'none' and acodec != 'none':
                        stream_type = 'Audio Only'
                    else:
                        continue
                        
                    # Calculate human-readable size
                    filesize = f.get('filesize') or f.get('filesize_approx')
                    if filesize:
                        size_mb = round(filesize / (1024 * 1024), 2)
                        size_str = f"{size_mb} MB"
                    else:
                        size_str = "Unknown Size"
                        
                    formats.append({
                        'id': f.get('format_id'),
                        'ext': f.get('ext'),
                        'quality': f.get('format_note') or f.get('resolution') or 'Audio',
                        'height': f.get('height') or 0,
                        'size': size_str,
                        'url': f.get('url'),
                        'type': stream_type
                    })

            return {
                "title": info.get('title'),
                "thumbnail": info.get('thumbnail'),
                "duration": info.get('duration'),
                "formats": formats
            }
    except Exception as e:
        import traceback
        with open("yt_error.log", "a", encoding="utf-8") as file:
            file.write(f"Get Info Error: {str(e)}\n{traceback.format_exc()}\n\n")
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/download")
async def download_video(request: DownloadRequest, background_tasks: BackgroundTasks):
    try:
        # Create a unique filename prefix
        download_id = str(uuid.uuid4())
        
        # Ensure downloads directory exists
        os.makedirs("downloads", exist_ok=True)
        
        output_template = f"downloads/{download_id}.%(ext)s"
        
        # Determine if we need to mux video and audio
        format_selector = request.format_id
        
        # We need to fetch info again to check codecs of the requested format
        ydl_opts_info = {'quiet': True, 'no_warnings': True, 'cookiefile': 'youtube.com_cookies.txt'}
        needs_mux = False
        
        with yt_dlp.YoutubeDL(ydl_opts_info) as ydl:
           info = ydl.extract_info(request.url, download=False)
           for f in info.get('formats', []):
               if f.get('format_id') == request.format_id:
                   vcodec = f.get('vcodec')
                   acodec = f.get('acodec')
                   if vcodec != 'none' and acodec == 'none':
                       needs_mux = True
                       break
        
        if needs_mux:
             format_selector = f"{request.format_id}+bestaudio[ext=m4a]/bestaudio/best"

        import logging
        logging.basicConfig(level=logging.DEBUG)
        
        class MyLogger(object):
            def debug(self, msg):
                print(f"[yt-dlp DEBUG] {msg}")
            def warning(self, msg):
                print(f"[yt-dlp WARNING] {msg}")
            def error(self, msg):
                print(f"[yt-dlp ERROR] {msg}")

        ydl_opts = {
            'format': format_selector,
            'outtmpl': output_template,
            'quiet': False,
            'verbose': True,
            'logger': MyLogger(),
            'cookiefile': 'youtube.com_cookies.txt',
            'merge_output_format': 'mp4', # Force MP4 if merging
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Download and mux
            ydl.download([request.url])
            
            # Find the final combined file
            downloaded_files = [f for f in os.listdir("downloads") if f.startswith(download_id)]
            
            if not downloaded_files:
                raise Exception("Download failed, output file not found")
                
            # Usually there's only one combined file left if merge is successful
            # Sort by extension to prefer .mp4 over .webm if multiple exist unexpectedly
            downloaded_files.sort(key=lambda x: x.endswith('.mp4'), reverse=True)
            filename = downloaded_files[0]
            file_path = f"downloads/{filename}"
            
            # Give it a nice name for the user download
            video_title = info.get('title', 'Video')
            # Sanitize title for filename
            safe_title = "".join([c for c in video_title if c.isalpha() or c.isdigit() or c==' ']).rstrip()
            download_filename = f"{safe_title}.{filename.split('.')[-1]}"
            
            # Schedule file deletion after Response is sent
            background_tasks.add_task(cleanup_file, file_path)
            
            return FileResponse(
                path=file_path, 
                filename=download_filename,
                media_type="application/octet-stream"
            )
            
    except Exception as e:
        with open("yt_error.log", "a", encoding="utf-8") as file:
            file.write(f"Download Error: {str(e)}\n\n")
        raise HTTPException(status_code=500, detail=str(e))
