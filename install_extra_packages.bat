@echo off
cd /d "%~dp0"
echo Installing the few extra packages Miko Stitch needs...
python -m pip install requests ddgs ollama yt-dlp numpy pillow edge-tts sounddevice pygame faster-whisper beautifulsoup4 lxml
pause
