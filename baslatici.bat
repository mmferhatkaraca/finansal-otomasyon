@echo off
title Finansal Otomasyon v6.0
color 0B
echo.
echo ================================================
echo   Finansal Otomasyon Sistemi v6.0
echo ================================================
echo.
python --version >nul 2>&1
if errorlevel 1 (
    echo HATA: Python bulunamadi! https://python.org
    pause
    exit /b
)
echo Bagimliliklar yukleniyor...
pip install -r requirements.txt -q
echo.
echo Uygulama baslatiliyor...
streamlit run app.py --server.port=8501
pause
