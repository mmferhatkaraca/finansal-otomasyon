#!/bin/bash
echo "================================"
echo "  Finansal Otomasyon v6.0"
echo "================================"
if ! command -v python3 &> /dev/null; then
    echo "HATA: Python3 bulunamadi!"
    exit 1
fi
pip3 install -r requirements.txt -q
streamlit run app.py --server.port=8501
