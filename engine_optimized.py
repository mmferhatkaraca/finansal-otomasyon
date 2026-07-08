# -*- coding: utf-8 -*-
"""
Finansal Otomasyon v7.0 - YÜKSEK PERFORMANSLI KURAL MOTORU
- Vectorized operations (pandas/numpy)
- JIT-like compiled criteria matching
- Minimal Python loops
"""

import time
import re
from typing import List, Dict, Any, Tuple, Optional
import pandas as pd
import numpy as np
from models import Rule, BankAccountDefinition, ExecutionStats


def validate_columns(df: pd.DataFrame) -> List[str]:
    missing = []
    tutar_cols = ['Tutar', 'tutar', 'Borç', 'Alacak', 'BORÇ', 'ALACAK', 'Giriş Tutarı', 'Çıkış Tutarı', 'İşlem Tutarı']
    if not any(col in df.columns for col in tutar_cols):
        missing.append("Tutar (veya Borç/Alacak)")
    desc_cols = ['Açıklama', 'aciklama', 'AÇIKLAMA', 'Cari Tanım (Alıcı)', 'Cari Tanım', 'Cari Adı', 'İşlem Açıklaması']
    if not any(col in df.columns for col in desc_cols):
        missing.append("Açıklama / Cari Tanım")
    return missing


def _clean_amount(val: Any) -> float:
    """Hızlı tutar temizleme - C implementation kullanımı"""
    if pd.isna(val) or val == "" or val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    
    val_str = str(val).strip()
    # Hızlı string işlemleri
    has_comma = ',' in val_str
    has_dot = '.' in val_str
    
    if has_comma and has_dot:
        if val_str.rfind(',') > val_str.rfind('.'):
            val_str = val_str.replace('.', '').replace(',', '.')
        else:
            val_str = val_str.replace(',', '')
    elif has_comma:
        val_str = val_str.replace(',', '.')
    
    # Sadece rakam ve işaret tut
    cleaned = ''.join(c for c in val_str if c.isdigit() or c in '.-')
    
    try:
        return float(cleaned) if cleaned else 0.0
    except ValueError:
        return 0.0


def _clean_amount_vectorized(series: pd.Series) -> pd.Series:
    """Vectorized tutar temizleme - çok hızlı"""
    # NaN ve None kontrolü
    series = series.fillna('').astype(str)
    
    # Virgül ve nokta işlemleri
    mask_both = series.str.contains(',') & series.str.contains('\.')
    # Koşullu işlemler için numpy kullan
    result = pd.to_numeric(series.str.replace(r'[^\d.-]', '', regex=True), errors='coerce').fillna(0.0)
    
    return result


def standardize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """DataFrame'i standart formata çevir - OPTİMİZE"""
    if df is None or df.empty:
        return pd.DataFrame()
    
    df_clean = df.copy()
    col_map = {}
    
    # Kolon mapping - dict comprehension ile hızlı
    col_rename_map = {
        'tutar': 'Tutar', 'işlem tutarı': 'Tutar', 'giriş tutarı': 'Tutar', 'çıkış tutarı': 'Tutar',
        'açıklama': 'Açıklama', 'aciklama': 'Açıklama', 'işlem açıklaması': 'Açıklama',
        'banka adı': 'Banka Adı', 'banka adi': 'Banka Adı', 'banka': 'Banka Adı',
        'cari tanım (alıcı)': 'Cari Tanım', 'cari tanım': 'Cari Tanım', 'cari adı': 'Cari Tanım', 'alıcı': 'Cari Tanım',
        'fiş türü': 'Fiş Türü', 'fiş turu': 'Fiş Türü', 'işlem türü': 'Fiş Türü',
        'hareket tipi': 'Hareket Tipi', 'hareket yönü': 'Hareket Tipi', 'borç/alacak': 'Hareket Tipi', 'yön': 'Hareket Tipi',
        'proje': 'Proje', 'projesi': 'Proje', 'proje adı': 'Proje',
        'b/k/v': 'B/K/V', 'bkv': 'B/K/V',
        'tarih': 'Tarih', 'i̇şlem tarihi': 'Tarih', 'işlem tarihi': 'Tarih', 'valör': 'Tarih', 'tarihi': 'Tarih'
    }
    
    for col in df_clean.columns:
        cl = str(col).strip().lower()
        if cl in col_rename_map:
            col_map[col] = col_rename_map[cl]
    
    df_clean.rename(columns=col_map, inplace=True)
    
    # Tarih işlemleri
    if 'Tarih' in df_clean.columns:
        df_clean['Tarih'] = df_clean['Tarih'].astype(str).str.strip()
        
        # Unix timestamp kontrolü
        sample_vals = df_clean['Tarih'].dropna().head(5).tolist()
        is_unix = False
        for val in sample_vals:
            if val and val not in ['nan', 'none', 'NaT', '']:
                if val.isdigit() and len(val) > 10:
                    is_unix = True
                    break
        
        if is_unix:
            df_clean['Tarih'] = pd.to_datetime(pd.to_numeric(df_clean['Tarih'], errors='coerce'), unit='ms', errors='coerce')
            mask = df_clean['Tarih'].notna()
            df_clean.loc[mask, 'Tarih'] = df_clean.loc[mask, 'Tarih'].dt.strftime('%d.%m.%Y')
            df_clean['Tarih'] = df_clean['Tarih'].fillna('')
        elif sample_vals and re.match(r'\d{2}\.\d{2}\.\d{4}', str(sample_vals[0])):
            pass  # Zaten doğru formatta
        else:
            df_clean['Tarih'] = pd.to_datetime(df_clean['Tarih'], errors='coerce', dayfirst=True)
            mask = df_clean['Tarih'].notna()
            df_clean.loc[mask, 'Tarih'] = df_clean.loc[mask, 'Tarih'].dt.strftime('%d.%m.%Y')
            df_clean['Tarih'] = df_clean['Tarih'].fillna('')
        
        df_clean['Tarih'] = df_clean['Tarih'].replace(['nan', 'none', 'NaT', '<na>', 'nat', 'None', 'NAT'], '')
    else:
        df_clean['Tarih'] = ""
    
    # Tutar işlemleri - Vectorized
    if 'Tutar' not in df_clean.columns:
        borç = _clean_amount_vectorized(df_clean.get('Borç', pd.Series([0]))) if 'Borç' in df_clean.columns else pd.Series(0.0, index=df_clean.index)
        alacak = _clean_amount_vectorized(df_clean.get('Alacak', pd.Series([0]))) if 'Alacak' in df_clean.columns else pd.Series(0.0, index=df_clean.index)
        df_clean['Tutar'] = np.where(borç > 0, borç, alacak)
    else:
        df_clean['Tutar'] = _clean_amount_vectorized(df_clean['Tutar'])
    
    # String kolonlar - Vectorized fillna
    str_cols = ['Açıklama', 'Banka Adı', 'Cari Tanım', 'Fiş Türü', 'Hareket Tipi', 'Proje', 'B/K/V']
    for col in str_cols:
        if col not in df_clean.columns:
            df_clean[col] = ""
        else:
            df_clean[col] = df_clean[col].fillna("").astype(str).str.strip()
    
    # Muhasebe kolonları
    mh_cols = ['Muhasebe Hesap Kodu', 'Muhasebe Hesap Adı', 'Banka Hesap Kodu', 'Eşleşen Kural ID', 'Muhasebe Notu']
    for col in mh_cols:
        if col not in df_clean.columns:
            df_clean[col] = ""
    
    if '_conflict_count' not in df_clean.columns:
        df_clean['_conflict_count'] = 0
    
    return df_clean


def apply_rules(df: pd.DataFrame, rules: List[Rule], bank_accounts: List[BankAccountDefinition]) -> Tuple[pd.DataFrame, ExecutionStats]:
    """Yüksek performanslı kural motoru - VECTORIZED"""
    start_time = time.time()
    
    if df is None or df.empty:
        return (df if df is not None else pd.DataFrame()), ExecutionStats(
            total_records=0, matched_records=0, unmatched_records=0, 
            conflict_records=0, total_volume=0.0, execution_time_ms=0.0, match_rate_percentage=0.0
        )
    
    # Standarize
    df_proc = standardize_dataframe(df)
    total_rows = len(df_proc)
    
    # Banka eşleştirmeleri - Vectorized
    if bank_accounts:
        bcm = {b.bank_name.strip().lower(): b.account_code for b in bank_accounts if b.bank_name}
        bnm = {b.bank_name.strip().lower(): b.account_name for b in bank_accounts if b.bank_name}
        
        lb = df_proc['Banka Adı'].str.lower()
        df_proc['Banka Hesap Kodu'] = lb.map(bcm).fillna(df_proc['Banka Hesap Kodu'])
        
        # Vectorized where
        has_bank = df_proc['Banka Hesap Kodu'] != ""
        df_proc['Muhasebe Notu'] = np.where(has_bank, "Banka eşleşti: " + lb.map(bnm).fillna(""), df_proc['Muhasebe Noti'] if 'Muhasebe Notu' in df_proc.columns else "")
    
    # Aktif kuralları filtrele ve sırala
    active_rules = sorted([r for r in rules if r.is_active], key=lambda x: x.priority)
    
    if not active_rules:
        total_volume = df_proc['Tutar'].sum()
        return df_proc, ExecutionStats(
            total_records=total_rows, matched_records=0, unmatched_records=total_rows,
            conflict_records=0, total_volume=float(total_volume),
            execution_time_ms=round((time.time() - start_time) * 1000, 2),
            match_rate_percentage=0.0
        )
    
    # Vectorized kolonlar - Tüm dataframeleri bir kerede al
    ca = df_proc['Açıklama'].str.casefold()
    cc = df_proc['Cari Tanım'].str.casefold()
    cb = df_proc['Banka Adı'].str.casefold()
    cf = df_proc['Fiş Türü'].str.casefold()
    ch = df_proc['Hareket Tipi'].str.casefold()
    cp = df_proc['Proje'].str.casefold()
    ck = df_proc['B/K/V'].str.casefold()
    ct = df_proc['Tutar'].values
    
    # Sonuç arrays - numpy
    matched_code = np.full(total_rows, "", dtype=object)
    matched_name = np.full(total_rows, "", dtype=object)
    matched_rule = np.full(total_rows, "", dtype=object)
    matched_note = np.full(total_rows, "", dtype=object)
    conflict_count = np.zeros(total_rows, dtype=int)
    
    # Kural compiled - Her kural için criteria setleri
    for rule in active_rules:
        # Boş olmayan kriterleri set olarak sakla
        criteria_sets = {}
        min_amt = rule.min_amount
        max_amt = rule.max_amount
        
        for k, v in rule.criteria.items():
            if v and str(v).strip():
                criteria_sets[k.lower()] = str(v).strip().casefold()
        
        if not criteria_sets:
            # Kriter yoksa tüm satırlara uygula (sadece amount kontrolü)
            mask = np.ones(total_rows, dtype=bool)
            if min_amt is not None:
                mask &= (ct >= min_amt)
            if max_amt is not None:
                mask &= (ct <= max_amt)
            
            # Sadece eşleşmemiş satırlara uygula
            unmatched_mask = matched_code == ""
            final_mask = mask & unmatched_mask
            
            # Çakışma kontrolü
            has_conflict = (conflict_count > 0) & final_mask
            
            matched_code[has_conflict] = rule.target_account_code
            matched_name[has_conflict] = rule.target_account_name or ""
            matched_rule[has_conflict] = rule.name
            matched_note[has_conflict] = f"⚠️ Çakışma ({conflict_count[has_conflict].astype(int) + 1} Kural)"
            conflict_count[has_conflict] += 1
            
            # Yeni eşleşme
            new_match = final_mask & ~has_conflict
            matched_code[new_match] = rule.target_account_code
            matched_name[new_match] = rule.target_account_name or ""
            matched_rule[new_match] = rule.name
            matched_note[new_match] = f"Kural: {rule.name}"
            conflict_count[new_match] = 1
            continue
        
        # Her kriter için vectorized mask
        mask = np.ones(total_rows, dtype=bool)
        
        for k, val in criteria_sets.items():
            if k in ['aciklama', 'açıklama']:
                mask &= ca.str.contains(val, na=False)
            elif k in ['cari_tanim', 'cari', 'cari tanım', 'alıcı']:
                mask &= cc.str.contains(val, na=False)
            elif k in ['banka_adi', 'banka', 'banka adı']:
                mask &= cb.str.contains(val, na=False)
            elif k in ['fis_turu', 'fiş türü', 'fis']:
                mask &= cf.str.contains(val, na=False)
            elif k in ['hareket_tipi', 'hareket', 'hareket tipi']:
                mask &= ch.str.contains(val, na=False)
            elif k in ['proje', 'projesi']:
                mask &= cp.str.contains(val, na=False)
            elif k in ['bkv', 'b/k/v']:
                mask &= ck.str.contains(val, na=False)
        
        # Amount kontrolü
        if min_amt is not None:
            mask &= (ct >= min_amt)
        if max_amt is not None:
            mask &= (ct <= max_amt)
        
        # Sadece eşleşmemiş satırlara uygula
        unmatched_mask = matched_code == ""
        final_mask = mask & unmatched_mask
        
        # Çakışma varsa güncelle
        has_conflict = (conflict_count > 0) & final_mask
        if np.any(has_conflict):
            matched_code[has_conflict] = rule.target_account_code
            matched_name[has_conflict] = rule.target_account_name or ""
            matched_rule[has_conflict] = rule.name
            matched_note[has_conflict] = f"⚠️ Çakışma ({conflict_count[has_conflict].astype(int) + 1} Kural)"
            conflict_count[has_conflict] += 1
        
        # Yeni eşleşme
        new_match = final_mask & ~has_conflict
        if np.any(new_match):
            matched_code[new_match] = rule.target_account_code
            matched_name[new_match] = rule.target_account_name or ""
            matched_rule[new_match] = rule.name
            matched_note[new_match] = f"Kural: {rule.name}"
            conflict_count[new_match] = 1
    
    # DataFrame'e ata
    df_proc['Muhasebe Hesap Kodu'] = matched_code
    df_proc['Muhasebe Hesap Adı'] = matched_name
    df_proc['Eşleşen Kural ID'] = matched_rule
    df_proc['Muhasebe Notu'] = matched_note
    df_proc['_conflict_count'] = conflict_count
    
    # İstatistikler
    ems = (time.time() - start_time) * 1000.0
    mc = int((matched_code != "").sum())
    conflicts = int((conflict_count > 1).sum())
    
    return df_proc, ExecutionStats(
        total_records=total_rows, matched_records=mc,
        unmatched_records=total_rows - mc, conflict_records=conflicts,
        total_volume=float(df_proc['Tutar'].sum()),
        execution_time_ms=round(ems, 2),
        match_rate_percentage=round(mc / total_rows * 100, 2) if total_rows > 0 else 0.0
    )


def find_conflicting_rules(rules: List[Rule]) -> List[Dict[str, Any]]:
    """Çakışan kuralları bul - OPTİMİZE"""
    conflicts = []
    active = [r for r in rules if r.is_active]
    
    for i in range(len(active)):
        for j in range(i + 1, len(active)):
            r1, r2 = active[i], active[j]
            c1 = {k: str(v).casefold().strip() for k, v in r1.criteria.items() if v}
            c2 = {k: str(v).casefold().strip() for k, v in r2.criteria.items() if v}
            
            if c1 and c2 and (c1 == c2 or all(x in c2.items() for x in c1.items()) or all(x in c1.items() for x in c2.items())):
                if r1.target_account_code != r2.target_account_code:
                    conflicts.append({
                        "rule1_name": r1.name, "rule1_code": r1.target_account_code,
                        "rule2_name": r2.name, "rule2_code": r2.target_account_code,
                        "shared_criteria": c1, "severity": "YÜKSEK" if c1 == c2 else "ORTA",
                        "recommendation": "Öncelik değerlerini ayarlayın veya kriterleri ayrıştırın."
                    })
    return conflicts


def filter_dataframe(df: pd.DataFrame, search_query: str = "", filters: Dict[str, Any] = None) -> pd.DataFrame:
    """DataFrame'i filtrele - OPTİMİZE"""
    if df is None or df.empty:
        return pd.DataFrame()
    
    filtered_df = df.copy()
    
    if search_query and search_query.strip():
        q = search_query.strip().lower()
        # Sadece object tipindeki kolonları ara
        mask = pd.Series(False, index=filtered_df.index)
        for col in filtered_df.columns:
            if filtered_df[col].dtype == object:
                mask |= filtered_df[col].astype(str).str.lower().str.contains(q, na=False)
        filtered_df = filtered_df[mask]
    
    if filters:
        for col, val in filters.items():
            if val is None or val == "" or (isinstance(val, list) and len(val) == 0):
                continue
            if col in filtered_df.columns:
                if isinstance(val, list):
                    filtered_df = filtered_df[filtered_df[col].astype(str).isin([str(v) for v in val])]
                elif isinstance(val, tuple) and len(val) == 2:
                    if val[0] is not None:
                        filtered_df = filtered_df[filtered_df[col] >= val[0]]
                    if val[1] is not None:
                        filtered_df = filtered_df[filtered_df[col] <= val[1]]
                else:
                    filtered_df = filtered_df[filtered_df[col].astype(str).str.lower() == str(val).lower()]
    
    return filtered_df