@echo off
cd /d %~dp0
if not exist .venv ( python -m venv .venv )
call .venv\Scripts\activate
pip install -r requirements.txt
pip install -U "yt-dlp[default]"
streamlit run app.py --server.maxUploadSize 5000
pause
