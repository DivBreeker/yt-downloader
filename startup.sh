#!/bin/bash
echo "Installing FFmpeg for yt-dlp muxing..."
apt-get update && apt-get install -y ffmpeg

echo "Starting Gunicorn server..."
gunicorn -w 4 -k uvicorn.workers.UvicornWorker main:app
