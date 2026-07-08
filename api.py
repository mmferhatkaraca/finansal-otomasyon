# -*- coding: utf-8 -*-
"""Finansal Otomasyon v6.0 - FastAPI REST Servisi"""

import os, json
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import pandas as pd
import io
from models import Rule, BankAccountDefinition, ExecutionStats
from engine_optimized import apply_rules, find_conflicting_rules, validate_columns
from db import Database

app = FastAPI(title="Finansal Otomasyon API v6.0", version="6.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

db = Database()

class RuleExecutionRequest(BaseModel):
    transactions: List[Dict[str, Any]]
    rules: Optional[List[Rule]] = None
    bank_accounts: Optional[List[BankAccountDefinition]] = None

@app.get("/")
def root():
    return {"status": "active", "version": "6.0.0", "db_online": db.online}

@app.post("/api/v1/process-transactions")
def process_transactions(payload: RuleExecutionRequest):
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
async def process_excel(file: UploadFile = File(...)):
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
