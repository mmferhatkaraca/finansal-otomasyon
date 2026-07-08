# -*- coding: utf-8 -*-
"""
Finansal Otomasyon v6.0 - Yüksek Performanslı Kural Motoru
"""

import time
import re
from typing import List, Dict, Any, Tuple
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
    if pd.isna(val) or val == "" or val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    val_str = str(val).strip()
    if ',' in val_str and '.' in val_str:
        if val_str.rfind(',') > val_str.rfind('.'):
            val_str = val_str.replace('.', '').replace(',', '.')
        else:
            val_str = val_str.replace(',', '')
    elif ',' in val_str:
        val_str = val_str.replace(',', '.')
    cleaned = re.sub(r'[^\d.-]', '', val_str)
    try:
        return float(cleaned) if cleaned else 0.0
    except ValueError:
        return 0.0


def standardize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    df_clean = df.copy()
    col_map = {}
    for col in df_clean.columns:
        cl = str(col).strip().lower()
        if cl in ['tutar', 'işlem tutarı', 'giriş tutarı', 'çıkış tutarı']:
            col_map[col] = 'Tutar'
        elif cl in ['açıklama', 'aciklama', 'işlem açıklaması']:
            col_map[col] = 'Açıklama'
        elif cl in ['banka adı', 'banka adi', 'banka']:
            col_map[col] = 'Banka Adı'
        elif cl in ['cari tanım (alıcı)', 'cari tanım (alıcı)sı', 'cari tanım', 'cari adı', 'alıcı']:
            col_map[col] = 'Cari Tanım'
        elif cl in ['fiş türü', 'fiş turu', 'islem turu', 'işlem türü']:
            col_map[col] = 'Fiş Türü'
        elif cl in ['hareket tipi', 'hareket yönü', 'borç/alacak', 'yön']:
            col_map[col] = 'Hareket Tipi'
        elif cl in ['proje', 'projesi', 'proje adı']:
            col_map[col] = 'Proje'
        elif cl in ['b/k/v', 'bkv']:
            col_map[col] = 'B/K/V'
        elif cl in ['tarih', 'i̇şlem tarihi', 'işlem tarihi', 'valör', 'tarihi', 'date', 'zaman']:
            col_map[col] = 'Tarih'
    df_clean.rename(columns=col_map, inplace=True)
    if 'Tarih' in df_clean.columns:
        # Tarih kolonunu string'e çevir
        df_clean['Tarih'] = df_clean['Tarih'].astype(str).str.strip()
        
        # Tarih formatını kontrol et (ilk non-empty değeri bul)
        sample = ""
        for val in df_clean['Tarih']:
            if val and val not in ['nan', 'none', 'NaT', '']:
                sample = val
                break
        
        # Unix timestamp (milisaniye) kontrolü
        if sample.isdigit() and len(sample) > 10:
            # Milisaniye → datetime
            df_clean['Tarih'] = pd.to_numeric(df_clean['Tarih'], errors='coerce')
            dt = pd.to_datetime(df_clean['Tarih'], unit='ms', errors='coerce')
            mask = dt.notna()
            df_clean.loc[mask, 'Tarih'] = dt[mask].dt.strftime('%d.%m.%Y')
            df_clean['Tarih'] = df_clean['Tarih'].fillna('')
        # DD.MM.YYYY formatındaysa parse etme
        elif re.match(r'\d{2}\.\d{2}\.\d{4}', sample):
            pass  # Zaten doğru formatta
        # YYYY-MM-DD veya diğer formatlar
        else:
            # Otomatik parse
            dt = pd.to_datetime(df_clean['Tarih'], errors='coerce', dayfirst=True)
            mask = dt.notna()
            df_clean.loc[mask, 'Tarih'] = dt[mask].dt.strftime('%d.%m.%Y')
            df_clean['Tarih'] = df_clean['Tarih'].fillna('')
        
        # NaN/NaT değerleri boş string yap
        df_clean['Tarih'] = df_clean['Tarih'].replace(['nan', 'none', 'NaT', '<na>', 'nat', 'None', 'NAT'], '')
    else:
        df_clean['Tarih'] = ""
    if 'Tutar' not in df_clean.columns:
        borc = df_clean['Borç'].apply(_clean_amount) if 'Borç' in df_clean.columns else pd.Series(0.0, index=df_clean.index)
        alacak = df_clean['Alacak'].apply(_clean_amount) if 'Alacak' in df_clean.columns else pd.Series(0.0, index=df_clean.index)
        df_clean['Tutar'] = np.where(borc > 0, borc, alacak)
    else:
        df_clean['Tutar'] = df_clean['Tutar'].apply(_clean_amount)
    for col in ['Açıklama', 'Banka Adı', 'Cari Tanım', 'Fiş Türü', 'Hareket Tipi', 'Proje', 'B/K/V']:
        if col not in df_clean.columns:
            df_clean[col] = ""
        else:
            df_clean[col] = df_clean[col].fillna("").astype(str).str.strip()
    for col in ['Muhasebe Hesap Kodu', 'Muhasebe Hesap Adı', 'Banka Hesap Kodu', 'Eşleşen Kural ID', 'Muhasebe Notu']:
        if col not in df_clean.columns:
            df_clean[col] = ""
    if '_conflict_count' not in df_clean.columns:
        df_clean['_conflict_count'] = 0
    
    # KOLON SIRASI (Excel'deki gibi)
    desired_order = [
        'Proje', 'Muhasebe', 'Banka Adı', 'Cari Tanım', 'Unnamed: 4',
        'Fiş Türü', 'Fiş No', 'Tarih', 'Özel Kod', 'Özel Kod 3',
        'Borç', 'Alacak', 'Dövizli Borç', 'Dövizli Alacak', 'Hareket Sayısı',
        'Açıklama', 'Tutar', 'Hareket Tipi', 'B/K/V',
        'Muhasebe Hesap Kodu', 'Muhasebe Hesap Adı', 'Banka Hesap Kodu',
        'Eşleşen Kural ID', 'Muhasebe Notu', '_conflict_count'
    ]
    
    # Mevcut kolonları sırala (varsa)
    existing_cols = [col for col in desired_order if col in df_clean.columns]
    other_cols = [col for col in df_clean.columns if col not in desired_order]
    
    df_clean = df_clean[existing_cols + other_cols]
    
    return df_clean


def apply_rules(df: pd.DataFrame, rules: List[Rule], bank_accounts: List[BankAccountDefinition]) -> Tuple[pd.DataFrame, ExecutionStats]:
    start_time = time.time()
    if df is None or df.empty:
        return (df if df is not None else pd.DataFrame()), ExecutionStats(total_records=0, matched_records=0, unmatched_records=0, conflict_records=0, total_volume=0.0, execution_time_ms=0.0, match_rate_percentage=0.0)
    
    df_proc = standardize_dataframe(df)
    total_rows = len(df_proc)
    
    # DEBUG: İlk satırın kolonlarını ve değerlerini göster
    if total_rows > 0:
        print(f"[ENGINE] Kolonlar: {list(df_proc.columns)}")
        print(f"[ENGINE] İlk satır Banka: '{df_proc['Banka Adı'].iloc[0]}'")
        print(f"[ENGINE] İlk satır Cari: '{df_proc['Cari Tanım'].iloc[0]}'")
        print(f"[ENGINE] İlk satır Fiş: '{df_proc['Fiş Türü'].iloc[0]}'")
        print(f"[ENGINE] İlk satır Hareket: '{df_proc['Hareket Tipi'].iloc[0]}'")
        print(f"[ENGINE] İlk satır Proje: '{df_proc['Proje'].iloc[0]}'")
    
    print(f"[ENGINE] {len(rules)} kural var")
    for i, r in enumerate(rules[:3]):  # İlk 3 kuralı göster
        print(f"[ENGINE] Kural {i+1}: {r.name}")
        print(f"[ENGINE]   Kriterler: {r.criteria}")
    
    if bank_accounts:
        bcm = {b.bank_name.strip().lower(): b.account_code for b in bank_accounts if b.bank_name}
        bnm = {b.bank_name.strip().lower(): b.account_name for b in bank_accounts if b.bank_name}
        lb = df_proc['Banka Adı'].str.lower()
        df_proc['Banka Hesap Kodu'] = lb.map(bcm).fillna(df_proc['Banka Hesap Kodu'])
        df_proc['Muhasebe Notu'] = np.where(df_proc['Banka Hesap Kodu'] != "", "Banka eşleşti: " + lb.map(bnm).fillna(""), df_proc['Muhasebe Notu'])
    
    active_rules = sorted([r for r in rules if r.is_active], key=lambda x: x.priority)
    if not active_rules:
        return df_proc, ExecutionStats(total_records=total_rows, matched_records=0, unmatched_records=total_rows, conflict_records=0, total_volume=float(df_proc['Tutar'].sum()), execution_time_ms=round((time.time()-start_time)*1000, 2), match_rate_percentage=0.0)
    
    ca = df_proc['Açıklama'].str.casefold().tolist()
    cc = df_proc['Cari Tanım'].str.casefold().tolist()
    cb = df_proc['Banka Adı'].str.casefold().tolist()
    cf = df_proc['Fiş Türü'].str.casefold().tolist()
    ch = df_proc['Hareket Tipi'].str.casefold().tolist()
    cp = df_proc['Proje'].str.casefold().tolist()
    ck = df_proc['B/K/V'].str.casefold().tolist()
    ct = df_proc['Tutar'].tolist()
    
    rc = [""] * total_rows
    rn = [""] * total_rows
    ri = [""] * total_rows
    rno = [""] * total_rows
    rco = [0] * total_rows
    
    compiled = []
    for r in active_rules:
        cd = {}
        for k, v in r.criteria.items():
            if v and str(v).strip():
                cd[k.lower()] = str(v).strip().casefold()  # casefold kullan
        compiled.append({'rule': r, 'criteria': cd, 'min_amt': r.min_amount, 'max_amt': r.max_amount})
        print(f"[ENGINE] Compiled kriterler: {cd}")
    
    # İlk 5 satır için debug
    debug_count = min(5, total_rows)
    for i in range(debug_count):
        print(f"[ENGINE] Satır {i}: Banka='{cb[i]}', Cari='{cc[i]}', Fiş='{cf[i]}', Hareket='{ch[i]}', Proje='{cp[i]}'")
    
    for i in range(total_rows):
        tv, av, cv, bv, fv, hv, pv, kv = ct[i], ca[i], cc[i], cb[i], cf[i], ch[i], cp[i], ck[i]
        matched = []
        for item in compiled:
            r, crit = item['rule'], item['criteria']
            if item['min_amt'] is not None and tv < item['min_amt']: continue
            if item['max_amt'] is not None and tv > item['max_amt']: continue
            ok = True
            for k, val in crit.items():
                if k in ['aciklama', 'açıklama']:
                    if val not in av: ok = False; break
                elif k in ['cari_tanim', 'cari', 'cari tanım', 'alıcı']:
                    if val not in cv: ok = False; break
                elif k in ['banka_adi', 'banka', 'banka adı']:
                    if val not in bv: ok = False; break
                elif k in ['fis_turu', 'fiş türü', 'fis']:
                    if val not in fv: ok = False; break
                elif k in ['hareket_tipi', 'hareket', 'hareket tipi']:
                    if val != hv and val not in hv: ok = False; break
                elif k in ['proje', 'projesi']:
                    if val not in pv: ok = False; break
                elif k in ['bkv', 'b/k/v']:
                    if val not in kv: ok = False; break
                elif k == 'regex':
                    try:
                        if not re.search(val, av + " " + cv, re.IGNORECASE): ok = False; break
                    except re.error: ok = False; break
            if ok:
                matched.append(r)
        if len(matched) == 1:
            b = matched[0]
            rc[i], rn[i], ri[i], rno[i], rco[i] = b.target_account_code, b.target_account_name or "", b.name, f"Kural: {b.name}", 1
        elif len(matched) > 1:
            b = matched[0]
            rc[i], rn[i], ri[i], rco[i] = b.target_account_code, b.target_account_name or "", b.name, len(matched)
            rno[i] = f"⚠️ Çakışma ({len(matched)} Kural): {', '.join([r.name for r in matched[:3]])}"
    
    df_proc['Muhasebe Hesap Kodu'] = rc
    df_proc['Muhasebe Hesap Adı'] = rn
    df_proc['Eşleşen Kural ID'] = ri
    df_proc['Muhasebe Notu'] = rno
    df_proc['_conflict_count'] = rco
    
    ems = (time.time() - start_time) * 1000.0
    mc = sum(1 for c in rc if c != "")
    return df_proc, ExecutionStats(total_records=total_rows, matched_records=mc, unmatched_records=total_rows-mc, conflict_records=sum(1 for c in rco if c > 1), total_volume=float(df_proc['Tutar'].sum()), execution_time_ms=round(ems, 2), match_rate_percentage=round(mc/total_rows*100, 2) if total_rows > 0 else 0.0)


def find_conflicting_rules(rules: List[Rule]) -> List[Dict[str, Any]]:
    conflicts = []
    active = [r for r in rules if r.is_active]
    for i in range(len(active)):
        for j in range(i + 1, len(active)):
            r1, r2 = active[i], active[j]
            c1 = {k: str(v).casefold().strip() for k, v in r1.criteria.items() if v}
            c2 = {k: str(v).casefold().strip() for k, v in r2.criteria.items() if v}
            if c1 and c2 and (c1 == c2 or all(x in c2.items() for x in c1.items()) or all(x in c1.items() for x in c2.items())):
                if r1.target_account_code != r2.target_account_code:
                    conflicts.append({"rule1_name": r1.name, "rule1_code": r1.target_account_code, "rule2_name": r2.name, "rule2_code": r2.target_account_code, "shared_criteria": c1, "severity": "YÜKSEK" if c1 == c2 else "ORTA", "recommendation": "Öncelik değerlerini ayarlayın veya kriterleri ayrıştırın."})
    return conflicts


def filter_dataframe(df: pd.DataFrame, search_query: str = "", filters: Dict[str, Any] = None) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    filtered_df = df.copy()
    if search_query and search_query.strip():
        q = search_query.strip().lower()
        mask = pd.Series(False, index=filtered_df.index)
        for col in filtered_df.columns:
            if filtered_df[col].dtype == object:
                mask |= filtered_df[col].astype(str).str.lower().str.contains(q, na=False)
        filtered_df = filtered_df[mask]
    if filters:
        for col, val in filters.items():
            if val is None or val == "" or (isinstance(val, list) and len(val) == 0): continue
            if col in filtered_df.columns:
                if isinstance(val, list):
                    filtered_df = filtered_df[filtered_df[col].astype(str).isin([str(v) for v in val])]
                elif isinstance(val, tuple) and len(val) == 2:
                    if val[0] is not None: filtered_df = filtered_df[filtered_df[col] >= val[0]]
                    if val[1] is not None: filtered_df = filtered_df[filtered_df[col] <= val[1]]
                else:
                    filtered_df = filtered_df[filtered_df[col].astype(str).str.lower() == str(val).lower()]
    return filtered_df
