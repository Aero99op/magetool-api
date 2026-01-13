---
title: Magetool API
emoji: 🛠️
colorFrom: purple
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
---

# Magetool API - File Manipulation Hub

Backend API for Magetool - an all-in-one file manipulation tool.

## Features
- 🎥 Video Downloads (YouTube, Instagram, Shorts, Reels)
- 🖼️ Image Processing (Convert, Crop, Remove Background)
- 🔊 Audio Extraction & Conversion
- 📄 PDF Operations (Merge, Split, OCR)

## API Endpoints
- `GET /api/health` - Health check
- `POST /api/videos/youtube-download` - Download YouTube video
- `GET /api/videos/youtube-download-stream` - Download with SSE progress

## Frontend
The frontend is deployed separately on Vercel.
