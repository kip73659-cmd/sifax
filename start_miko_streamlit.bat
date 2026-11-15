@echo off
cd /d "%~dp0"
echo Installing Streamlit if needed...
python -m pip install streamlit
echo.
echo Miko in Streamlit. This PC: http://localhost:8501   Other devices: http://YOUR-PC-IP:8501
echo Keep this window open. Close it to quit.
python -m streamlit run miko_streamlit.py --server.address 0.0.0.0 --server.port 8501 --server.headless true
pause
