# -*- coding: utf-8 -*-
"""
Supabase Veritabanı Bağlantı Modülü v7.0 - PERFORMANS OPTİMİZE EDİLMİŞ
- Batch operations
- Connection pooling
- Caching
- Minimal round-trips
"""

import os
import math
from typing import List, Dict, Any, Optional
from functools import lru_cache
import threading

# Lazy import for Streamlit
_st = None
def _get_st():
    global _st
    if _st is None:
        try:
            import streamlit as st
            _st = st
        except ImportError:
            pass
    return _st


def get_supabase_client() -> Optional[Any]:
    """Tekil Supabase client - connection pooling"""
    if hasattr(get_supabase_client, '_client'):
        return get_supabase_client._client
    
    try:
        st_instance = _get_st()
        if st_instance:
            url = st_instance.secrets.get("SUPABASE_URL", "")
            key = st_instance.secrets.get("SUPABASE_KEY", "")
        else:
            url, key = "", ""
    except Exception:
        url, key = "", ""
    
    if not url or not key:
        url = os.environ.get("SUPABASE_URL", "")
        key = os.environ.get("SUPABASE_KEY", "")
    
    if not url or not key:
        return None
    
    try:
        from supabase import create_client
        client = create_client(url, key)
        get_supabase_client._client = client
        return client
    except Exception as e:
        print(f"Supabase bağlantı hatası: {e}")
        return None


def _clean_value(v):
    """Herhangi bir Python değerini JSON-uyumlu hale getirir."""
    if v is None:
        return ""
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return ""
    if hasattr(v, 'isoformat'):
        return str(v)
    if hasattr(v, 'item'):
        return v.item()
    return v


def _clean_dict(d: Dict) -> Dict:
    """Dictionary'deki tüm değerleri JSON-uyumlu hale getirir."""
    return {k: _clean_value(v) for k, v in d.items()}


class Database:
    """Çok firmalı Supabase veritabanı işlemleri - PERFORMANS OPTİMİZE"""
    
    # Sınıf seviyesinde cache
    _cache: Dict[str, Any] = {}
    _cache_lock = threading.Lock()
    _cache_ttl = 30  # Saniye
    
    def __init__(self):
        self.client = get_supabase_client()
        self.online = self.client is not None
    
    def _get_cached(self, key: str) -> Optional[Any]:
        """Cache kontrolü"""
        with self._cache_lock:
            if key in self._cache:
                entry = self._cache[key]
                if entry['expire'] > time.time():
                    return entry['data']
                else:
                    del self._cache[key]
        return None
    
    def _set_cached(self, key: str, data: Any, ttl: int = None):
        """Cache ayarla"""
        with self._cache_lock:
            self._cache[key] = {
                'data': data,
                'expire': time.time() + (ttl or self._cache_ttl)
            }
    
    def invalidate_cache(self, pattern: str = None):
        """Cache'i invalidate et"""
        with self._cache_lock:
            if pattern:
                for k in list(self._cache.keys()):
                    if pattern in k:
                        del self._cache[k]
            else:
                self._cache.clear()
    
    # =========================================================================
    # FİRMA İŞLEMLERİ (Cache'li)
    # =========================================================================
    def get_companies(self, use_cache: bool = True) -> List[Dict]:
        cache_key = "companies"
        if use_cache:
            cached = self._get_cached(cache_key)
            if cached is not None:
                return cached
        
        if not self.online:
            return []
        try:
            result = self.client.table("companies").select("*").eq("is_active", True).order("name").execute()
            data = result.data or []
            self._set_cached(cache_key, data, ttl=60)
            return data
        except Exception as e:
            print(f"Firma listesi hatası: {e}")
            return []
    
    def create_company(self, name: str, code: str, tax_number: str = "") -> bool:
        if not self.online:
            return False
        try:
            self.client.table("companies").insert({"name": name, "code": code, "tax_number": tax_number, "is_active": True}).execute()
            self.invalidate_cache("companies")
            return True
        except Exception as e:
            print(f"Firma oluşturma hatası: {e}")
            return False
    
    def update_company(self, company_id: int, updates: Dict) -> bool:
        if not self.online:
            return False
        try:
            self.client.table("companies").update(updates).eq("id", company_id).execute()
            self.invalidate_cache("companies")
            return True
        except Exception as e:
            print(f"Firma güncelleme hatası: {e}")
            return False
    
    def delete_company(self, company_id: int) -> bool:
        if not self.online:
            return False
        try:
            for tbl in ["rules", "bank_accounts", "hesap_plani", "app_data"]:
                self.client.table(tbl).delete().eq("company_id", company_id).execute()
            self.client.table("companies").delete().eq("id", company_id).execute()
            self.invalidate_cache("companies")
            return True
        except Exception as e:
            print(f"Firma silme hatası: {e}")
            return False
    
    # =========================================================================
    # KULLANICI-FİRMA YETKİLENDİRME
    # =========================================================================
    def get_user_companies(self, user_id: int) -> List[int]:
        if not self.online:
            return []
        try:
            result = self.client.table("user_companies").select("company_id").eq("user_id", user_id).execute()
            return [r["company_id"] for r in (result.data or [])]
        except Exception as e:
            print(f"Kullanıcı firma yetki hatası: {e}")
            return []
    
    def set_user_companies(self, user_id: int, company_ids: List[int]) -> bool:
        if not self.online:
            return False
        try:
            self.client.table("user_companies").delete().eq("user_id", user_id).execute()
            if company_ids:
                batch_data = [{"user_id": user_id, "company_id": cid} for cid in company_ids]
                self.client.table("user_companies").insert(batch_data).execute()
            return True
        except Exception as e:
            print(f"Kullanıcı firma yetki ayarlama hatası: {e}")
            return False
    
    def get_allowed_companies(self, user_id: int, role: str) -> List[Dict]:
        all_companies = self.get_companies()
        if role == "admin":
            return all_companies
        allowed_ids = self.get_user_companies(user_id)
        if not allowed_ids:
            return all_companies
        return [c for c in all_companies if c["id"] in allowed_ids]
    
    # =========================================================================
    # KULLANICI İŞLEMLERİ
    # =========================================================================
    def get_user(self, username: str) -> Optional[Dict]:
        if not self.online:
            return None
        try:
            result = self.client.table("users").select("*").eq("username", username).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            print(f"Kullanıcı okuma hatası: {e}")
            return None
    
    def get_all_users(self) -> List[Dict]:
        if not self.online:
            return []
        try:
            result = self.client.table("users").select("*").order("created_at").execute()
            return result.data or []
        except Exception as e:
            print(f"Kullanıcı listesi hatası: {e}")
            return []
    
    def create_user(self, username: str, password_hash: str, full_name: str = "", role: str = "user") -> bool:
        if not self.online:
            return False
        try:
            self.client.table("users").insert({"username": username, "password_hash": password_hash, "full_name": full_name, "role": role, "is_active": True}).execute()
            return True
        except Exception as e:
            print(f"Kullanıcı oluşturma hatası: {e}")
            return False
    
    def update_user(self, user_id: int, updates: Dict) -> bool:
        if not self.online:
            return False
        try:
            self.client.table("users").update(updates).eq("id", user_id).execute()
            return True
        except Exception as e:
            print(f"Kullanıcı güncelleme hatası: {e}")
            return False
    
    def delete_user(self, user_id: int) -> bool:
        if not self.online:
            return False
        try:
            self.client.table("users").delete().eq("id", user_id).execute()
            return True
        except Exception as e:
            print(f"Kullanıcı silme hatası: {e}")
            return False
    
    # =========================================================================
    # KURAL İŞLEMLERİ (Firma bazlı) - BATCH OPERATIONS
    # =========================================================================
    def get_rules(self, company_id: int = 1, use_cache: bool = True) -> List[Dict]:
        cache_key = f"rules_{company_id}"
        if use_cache:
            cached = self._get_cached(cache_key)
            if cached is not None:
                return cached
        
        if not self.online:
            return []
        try:
            result = self.client.table("rules").select("*").eq("company_id", company_id).order("priority").execute()
            data = result.data or []
            self._set_cached(cache_key, data, ttl=20)
            return data
        except Exception as e:
            print(f"Kural okuma hatası: {e}")
            return []
    
    def save_rules(self, rules_data: List[Dict], company_id: int = 1) -> bool:
        if not self.online:
            return False
        try:
            # Önce sil, sonra batch insert
            self.client.table("rules").delete().eq("company_id", company_id).execute()
            
            if not rules_data:
                self.invalidate_cache(f"rules_{company_id}")
                return True
            
            # Batch insert - 100'er gruplar halinde
            cleaned_data = []
            for rule in rules_data:
                clean = {k: v for k, v in rule.items() if k not in ['id', 'created_at']}
                clean['company_id'] = company_id
                cleaned_data.append(clean)
            
            # Supabase batch insert (tek seferde)
            self.client.table("rules").insert(cleaned_data).execute()
            self.invalidate_cache(f"rules_{company_id}")
            return True
        except Exception as e:
            print(f"Kural kaydetme hatası: {e}")
            return False
    
    # =========================================================================
    # BANKA HESABI İŞLEMLERİ (Firma bazlı) - BATCH
    # =========================================================================
    def get_bank_accounts(self, company_id: int = 1, use_cache: bool = True) -> List[Dict]:
        cache_key = f"bank_accounts_{company_id}"
        if use_cache:
            cached = self._get_cached(cache_key)
            if cached is not None:
                return cached
        
        if not self.online:
            return []
        try:
            result = self.client.table("bank_accounts").select("*").eq("company_id", company_id).order("bank_name").execute()
            data = result.data or []
            self._set_cached(cache_key, data, ttl=20)
            return data
        except Exception as e:
            print(f"Banka okuma hatası: {e}")
            return []
    
    def save_bank_accounts(self, accounts_data: List[Dict], company_id: int = 1) -> bool:
        if not self.online:
            return False
        try:
            self.client.table("bank_accounts").delete().eq("company_id", company_id).execute()
            
            if not accounts_data:
                self.invalidate_cache(f"bank_accounts_{company_id}")
                return True
            
            cleaned_data = [{k: v for k, v in acc.items() if k not in ['id']} for acc in accounts_data]
            for acc in cleaned_data:
                acc['company_id'] = company_id
            
            # Batch insert - tek seferde
            self.client.table("bank_accounts").insert(cleaned_data).execute()
            self.invalidate_cache(f"bank_accounts_{company_id}")
            return True
        except Exception as e:
            print(f"Banka kaydetme hatası: {e}")
            return False
    
    # =========================================================================
    # LOG İŞLEMLERİ (Background - async olabilir)
    # =========================================================================
    def add_log(self, username: str, action: str, detail: str, level: str = "INFO") -> bool:
        if not self.online:
            return False
        try:
            self.client.table("audit_logs").insert({"username": username, "action": action, "detail": detail, "level": level}).execute()
            return True
        except Exception as e:
            print(f"Log hatası: {e}")
            return False
    
    def get_logs(self, limit: int = 200) -> List[Dict]:
        if not self.online:
            return []
        try:
            result = self.client.table("audit_logs").select("*").order("created_at", desc=True).limit(limit).execute()
            return result.data or []
        except Exception as e:
            print(f"Log okuma hatası: {e}")
            return []
    
    # =========================================================================
    # HESAP PLANI İŞLEMLERİ (Firma bazlı) - OPTİMİZE
    # =========================================================================
    def get_hesap_plani(self, company_id: int = 1, use_cache: bool = True) -> List[Dict]:
        """Pagination ile TÜM hesap planını çeker - OPTİMİZE EDİLMİŞ"""
        cache_key = f"hesap_plani_{company_id}"
        if use_cache:
            cached = self._get_cached(cache_key)
            if cached is not None:
                return cached
        
        if not self.online:
            return []
        try:
            # Daha büyük page size = daha az round-trip
            all_data = []
            offset = 0
            page_size = 1000  # Daha büyük batch
            
            while True:
                result = self.client.table("hesap_plani").select("*").eq("company_id", company_id).order("hesap_kodu").range(offset, offset + page_size - 1).execute()
                batch = result.data or []
                all_data.extend(batch)
                if len(batch) < page_size:
                    break
                offset += page_size
            
            self._set_cached(cache_key, all_data, ttl=60)
            print(f"[DB] Hesap planı: {len(all_data)} kayıt (tek cache)")
            return all_data
        except Exception as e:
            print(f"Hesap planı okuma hatası: {e}")
            return []
    
    def save_hesap_plani(self, hesap_data: List[Dict], company_id: int = 1) -> bool:
        """Batch insert ile hesap planı kaydetme"""
        if not self.online:
            return False
        try:
            self.client.table("hesap_plani").delete().eq("company_id", company_id).execute()
            
            if not hesap_data:
                self.invalidate_cache(f"hesap_plani_{company_id}")
                return True
            
            # Tüm datayı tek seferde insert et (Supabase bunu halleder)
            cleaned_data = [{k: v for k, v in row.items() if k not in ['id']} for row in hesap_data]
            for row in cleaned_data:
                row['company_id'] = company_id
            
            # 500'er gruplar halinde insert (memory friendly)
            batch_size = 500
            for i in range(0, len(cleaned_data), batch_size):
                batch = cleaned_data[i:i + batch_size]
                self.client.table("hesap_plani").insert(batch).execute()
            
            self.invalidate_cache(f"hesap_plani_{company_id}")
            return True
        except Exception as e:
            print(f"Hesap planı kaydetme hatası: {e}")
            return False
    
    # =========================================================================
    # FİŞ LİSTESİ İŞLEMLERİ (Firma bazlı) - OPTİMİZE
    # =========================================================================
    def save_raw_data(self, df_dict: List[Dict], company_id: int = 1, username: str = "system") -> bool:
        """Fiş listesini JSON olarak DB'ye kaydeder."""
        if not self.online:
            return False
        try:
            clean_data = [_clean_dict(row) for row in df_dict]
            self.client.table("app_data").upsert({
                "key": "raw_transactions",
                "company_id": company_id,
                "value": clean_data,
                "updated_by": username
            }).execute()
            return True
        except Exception as e:
            print(f"Fiş listesi kaydetme hatası: {e}")
            return False
    
    def load_raw_data(self, company_id: int = 1, use_cache: bool = True) -> Optional[Dict]:
        cache_key = f"raw_data_{company_id}"
        if use_cache:
            cached = self._get_cached(cache_key)
            if cached is not None:
                return cached
        
        if not self.online:
            return None
        try:
            result = self.client.table("app_data").select("value, updated_at, updated_by").eq("key", "raw_transactions").eq("company_id", company_id).execute()
            data = result.data[0] if result.data else None
            if data:
                self._set_cached(cache_key, data, ttl=30)
            return data
        except Exception as e:
            print(f"Fiş listesi okuma hatası: {e}")
            return None
    
    def delete_raw_data(self, company_id: int = 1) -> bool:
        if not self.online:
            return False
        try:
            self.client.table("app_data").delete().eq("key", "raw_transactions").eq("company_id", company_id).execute()
            self.invalidate_cache(f"raw_data_{company_id}")
            return True
        except Exception as e:
            print(f"Fiş listesi silme hatası: {e}")
            return False
    
    def check_connection(self) -> bool:
        if not self.online:
            return False
        try:
            self.client.table("companies").select("id").limit(1).execute()
            return True
        except Exception:
            return False


# Zaman için import
import time