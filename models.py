# -*- coding: utf-8 -*-
"""Finansal Otomasyon v6.0 - Pydantic Veri Modelleri"""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime

class Rule(BaseModel):
    id: Optional[int] = None
    name: str = Field(..., description="Kural adı")
    priority: int = Field(default=100)
    criteria: Dict[str, Any] = Field(default_factory=dict)
    target_account_code: str = Field(...)
    target_account_name: Optional[str] = Field(default="")
    min_amount: Optional[float] = Field(default=None)
    max_amount: Optional[float] = Field(default=None)
    note: Optional[str] = Field(default="")
    is_active: bool = Field(default=True)
    created_at: Optional[str] = Field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    created_by: Optional[str] = Field(default="system")

class BankAccountDefinition(BaseModel):
    id: Optional[int] = None
    bank_name: str = Field(...)
    account_code: str = Field(...)
    account_name: Optional[str] = Field(default="")
    iban: Optional[str] = Field(default="")
    currency: str = Field(default="TL")

class User(BaseModel):
    id: Optional[int] = None
    username: str = Field(...)
    full_name: str = Field(default="")
    role: str = Field(default="user")
    is_active: bool = Field(default=True)
    created_at: Optional[str] = None
    last_login: Optional[str] = None

class FilterCriterion(BaseModel):
    column: str = Field(...)
    operator: str = Field(...)
    value: Any = Field(...)

class LogEntry(BaseModel):
    timestamp: str = Field(default_factory=lambda: datetime.now().strftime("%H:%M:%S"))
    action: str = Field(...)
    detail: str = Field(...)
    level: str = Field(default="INFO")

class ExecutionStats(BaseModel):
    total_records: int
    matched_records: int
    unmatched_records: int
    conflict_records: int
    total_volume: float
    execution_time_ms: float
    match_rate_percentage: float
