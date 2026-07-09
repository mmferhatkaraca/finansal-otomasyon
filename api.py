# -*- coding: utf-8 -*-
"""Finansal Otomasyon v7.0 - FastAPI REST Servisi (API-KEY korumalı)"""

import os, json, secrets
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, HTTPException, UploadFile, File, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import pandas as pd
import io
from models import Rule, BankAccountDefinition, ExecutionStats
from engine_optimized import apply_rules, find_conflicting_rules, validate_columns
from db import Database

app = FastAPI(title="Finansal Otomasyon API v7.0", version="7.0.0")

# GÜVENLİK: CORS'u kısıtla. İzinli origin'leri ALLOWED_ORIGINS ortam değişkeninden al
# (virgülle ayrılmış). Tanımlı değilse hiçbir tarayıcı origin'ine izin verilmez.
_allowed = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed,           # "*" YOK — yalnızca açıkça izin verilenler
    allow_credentials=bool(_allowed),
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

db = Database()

# --- API ANAHTARI KORUMASI ---
# Anahtar ortam değişkeninden okunur: API_KEY. Tanımlı değilse API kilitlidir.
_API_KEY = os.environ.get("API_KEY", "")

def require_api_key(x_api_key: str = Header(default="", alias="X-API-Key")):
    """Her korumalı endpoint bu bağımlılığı kullanır. Geçersiz anahtar → 401."""
    if not _API_KEY:
        raise HTTPException(status_code=503, detail="API kapalı: sunucuda API_KEY tanımlı değil.")
    if not x_api_key or not secrets.compare_digest(x_api_key, _API_KEY):
        raise HTTPException(status_code=401, detail="Geçersiz veya eksik API anahtarı (X-API-Key).")
    return True

class RuleExecutionRequest(BaseModel):
    transactions: List[Dict[str, Any]]
    rules: Optional[List[Rule]] = None
    bank_accounts: Optional[List[BankAccountDefinition]] = None

@app.get("/")
def root():
    return {"status": "active", "version": "6.0.0", "db_online": db.online}

@app.post("/api/v1/process-transactions")
def process_transactions(payload: RuleExecutionRequest, _auth: bool = Depends(require_api_key)):
    if not payload.transactions:
        raise HTTPException(status_code=400, detail="İşlem listesi boş.")
    df = pd.DataFrame(payload.transactions)
    rules = payload.rules or (db.get_rules(1) if db.online else [])
    banks = payload.bank_accounts or (db.get_bank_accounts(1) if db.online else [])
    if isinstance(rules, list) and rules and isinstance(rules[0], dict):
        rules = [Rule(**r) for r in rules]
    if isinstance(banks, list) and banks and isinstance(banks[0], dict):
        banks = [BankAccountDefinition(**b) for b in banks]
    mapped_df, stats = apply_rules(df, rules, banks)
    return {"stats": stats.model_dump(), "records": mapped_df.fillna("").to_dict(orient="records")}

@app.post("/api/v1/process-excel")
async def process_excel(file: UploadFile = File(...), _auth: bool = Depends(require_api_key)):
    content = await file.read()
    if file.filename.endswith((".xlsx", ".xls")):
        df = pd.read_excel(io.BytesIO(content))
    elif file.filename.endswith(".csv"):
        df = pd.read_csv(io.BytesIO(content))
    else:
        raise HTTPException(status_code=400, detail="Desteklenmeyen format.")
    rules = [Rule(**r) for r in db.get_rules(1)] if db.online else []
    banks = [BankAccountDefinition(**b) for b in db.get_bank_accounts(1)] if db.online else []
    mapped_df, stats = apply_rules(df, rules, banks)
    return {"stats": stats.model_dump(), "records": mapped_df.fillna("").to_dict(orient="records")}
