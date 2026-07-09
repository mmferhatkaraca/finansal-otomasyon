# -*- coding: utf-8 -*-
"""
Finansal Dashboard & Otomasyon Sistemi v6.0
Kullanıcı Girişli, Supabase Destekli, Çok Firmalı, Kurumsal Web Dashboard
"""

import os, re, json, time, zipfile
from datetime import datetime
from io import BytesIO
import pandas as pd
import numpy as np
import streamlit as st

from models import Rule, BankAccountDefinition, ExecutionStats, User
from engine_optimized import apply_rules, find_conflicting_rules, validate_columns, standardize_dataframe
from db import Database
from auth import (render_login_page, login, logout, is_logged_in, get_current_user,
                  is_admin, init_default_admin, hash_password, verify_password)

try:
    from streamlit_option_menu import option_menu
    HAS_OPTION_MENU = True
except ImportError:
    HAS_OPTION_MENU = False

# ==============================================================================
# 1. SAYFA AYARLARI + CSS
# ==============================================================================
st.set_page_config(page_title="Finansal Otomasyon v6.0", page_icon="🏢", layout="wide", initial_sidebar_state="expanded")

CUSTOM_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
.main-header { background: linear-gradient(135deg, #0F172A 0%, #1E293B 50%, #334155 100%); color: #FFFFFF; padding: 1.5rem 2rem; border-radius: 12px; margin-bottom: 1.5rem; box-shadow: 0 10px 25px -5px rgba(0,0,0,0.1); border-left: 6px solid #3B82F6; }
.main-header h1 { margin: 0; font-size: 1.75rem; font-weight: 700; color: #F8FAFC; }
.main-header p { margin: 0.25rem 0 0 0; font-size: 0.9rem; color: #94A3B8; }
.kpi-container { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 1rem; margin-bottom: 1.5rem; }
.kpi-card { background: #fff; border: 1px solid #E2E8F0; border-radius: 12px; padding: 1.25rem; box-shadow: 0 4px 6px rgba(0,0,0,0.05); }
.kpi-card:hover { transform: translateY(-2px); box-shadow: 0 10px 15px rgba(0,0,0,0.08); }
.kpi-card-title { font-size: 0.85rem; font-weight: 600; color: #64748B; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.5rem; }
.kpi-card-value { font-size: 1.6rem; font-weight: 700; color: #0F172A; }
.kpi-card-sub { font-size: 0.75rem; color: #10B981; font-weight: 500; margin-top: 0.25rem; }
@media screen and (max-width: 768px) { .main-header { padding: 1rem; } .main-header h1 { font-size: 1.25rem; } .kpi-container { grid-template-columns: 1fr; } .kpi-card { padding: 0.75rem; } [data-testid="column"] { width: 100% !important; flex: 1 1 100% !important; } }
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# ==============================================================================
# 2. GİRİŞ KONTROLÜ
# ==============================================================================
init_default_admin()
if not is_logged_in():
    render_login_page()
    st.stop()

current_user = get_current_user()
db = Database()

# ==============================================================================
# 3. SESSION STATE + FİRMA YÖNETİMİ
# ==============================================================================
def load_company_data(cid):
    """Belirli bir firma için tüm verileri DB'den yükler."""
    if db.online:
        rules_data = db.get_rules(cid)
        st.session_state.rules = [Rule(**r) for r in rules_data] if rules_data else []
        print(f"[LOAD] Firma {cid}: {len(st.session_state.rules)} kural yüklendi")
        
        banks_data = db.get_bank_accounts(cid)
        st.session_state.bank_accounts = [BankAccountDefinition(**b) for b in banks_data] if banks_data else []
        
        hp_data = db.get_hesap_plani(cid)
        st.session_state.hesap_plani = pd.DataFrame(hp_data).rename(columns={'hesap_kodu': 'Hesap Kodu', 'hesap_adi': 'Hesap Adı', 'detay_eh': 'Detay E/H'}) if hp_data else pd.DataFrame()
        
        st.session_state.logs = db.get_logs(200)
        
        # Fiş listesini DB'den yükle
        st.session_state.raw_df = None
        st.session_state.mapped_df = None
        st.session_state.stats = None
        raw_data = db.load_raw_data(cid)
        if raw_data and raw_data.get("value"):
            try:
                st.session_state.raw_df = pd.DataFrame(raw_data["value"])
                print(f"[LOAD] Fiş listesi yüklendi: {len(st.session_state.raw_df)} satır")
            except Exception as e:
                print(f"[LOAD] Fiş listesi DataFrame hatası: {e}")
        else:
            print(f"[LOAD] Fiş listesi DB'de yok")
        
        # Motor çalıştır
        if st.session_state.raw_df is not None:
            mapped_df, stats = apply_rules(st.session_state.raw_df, st.session_state.rules, st.session_state.bank_accounts)
            st.session_state.mapped_df = mapped_df
            st.session_state.stats = stats
            print(f"[LOAD] Motor çalıştı: {stats.matched_records}/{stats.total_records} eşleşti (%{stats.match_rate_percentage:.1f})")
        
        st.session_state.pop('hp_cache_key', None)
    else:
        # Offline mode - tüm değişkenleri başlat
        if 'rules' not in st.session_state:
            st.session_state.rules = []
        if 'bank_accounts' not in st.session_state:
            st.session_state.bank_accounts = []
        if 'hesap_plani' not in st.session_state:
            st.session_state.hesap_plani = pd.DataFrame()
        if 'logs' not in st.session_state:
            st.session_state.logs = []
        if 'raw_df' not in st.session_state:
            st.session_state.raw_df = None
        if 'mapped_df' not in st.session_state:
            st.session_state.mapped_df = None
        if 'stats' not in st.session_state:
            st.session_state.stats = None

def init_session_state():
    """Session state'i başlat - tüm değişkenleri initialize et"""
    if '_df_key' not in st.session_state:
        st.session_state._df_key = 0
    if 'current_company_id' not in st.session_state:
        st.session_state.current_company_id = 1
    if 'current_company_name' not in st.session_state:
        st.session_state.current_company_name = ""
    if '_last_company_id' not in st.session_state:
        st.session_state._last_company_id = None
    
    # Tüm data değişkenlerini başlat
    if 'rules' not in st.session_state:
        st.session_state.rules = []
    if 'bank_accounts' not in st.session_state:
        st.session_state.bank_accounts = []
    if 'hesap_plani' not in st.session_state:
        st.session_state.hesap_plani = pd.DataFrame()
    if 'logs' not in st.session_state:
        st.session_state.logs = []
    if 'raw_df' not in st.session_state:
        st.session_state.raw_df = None
    if 'mapped_df' not in st.session_state:
        st.session_state.mapped_df = None
    if 'stats' not in st.session_state:
        st.session_state.stats = None
    
    cid = st.session_state.current_company_id
    if st.session_state._last_company_id != cid:
        load_company_data(cid)
        st.session_state._last_company_id = cid

init_session_state()

def save_to_db():
    """DB'ye kaydet - optimize edilmiş"""
    cid = st.session_state.current_company_id
    if db.online:
        db.save_rules([r.model_dump() for r in st.session_state.rules], cid)
        db.save_bank_accounts([b.model_dump() for b in st.session_state.bank_accounts], cid)


def save_bank_account_to_db(bank_account: BankAccountDefinition):
    """Tek banka hesabı ekle - çok hızlı"""
    cid = st.session_state.current_company_id
    if db.online:
        db.add_bank_account(bank_account.model_dump(), cid)


def save_rule_to_db(rule: Rule):
    """Tek kural ekle - çok hızlı"""
    cid = st.session_state.current_company_id
    if db.online:
        db.add_rule(rule.model_dump(), cid)

def add_log(action, detail, level="INFO"):
    username = current_user.get("username", "system")
    st.session_state.logs.insert(0, {"time": datetime.now().strftime("%H:%M:%S"), "action": action, "detail": detail, "level": level, "username": username})
    if db.online:
        db.add_log(username, action, detail, level)

def rerun_motor():
    """Motoru yeniden çalıştır ve sayfayı yenile."""
    # DB'den güncel kuralları yükle (session state senkronize olsun)
    cid = st.session_state.current_company_id
    if db.online:
        rules_data = db.get_rules(cid)
        if rules_data:
            st.session_state.rules = [Rule(**r) for r in rules_data]
        banks_data = db.get_bank_accounts(cid)
        if banks_data:
            st.session_state.bank_accounts = [BankAccountDefinition(**b) for b in banks_data]
    
    raw_df = st.session_state.raw_df
    rules_count = len(st.session_state.rules)
    print(f"[MOTOR] raw_df: {'YOK (None)' if raw_df is None else f'{len(raw_df)} satır'}, Kurallar: {rules_count}")
    if raw_df is not None:
        mapped_df, stats = apply_rules(raw_df, st.session_state.rules, st.session_state.bank_accounts)
        st.session_state.mapped_df = mapped_df
        st.session_state.stats = stats
        print(f"[MOTOR] Sonuç: {stats.matched_records}/{stats.total_records} eşleşti (%{stats.match_rate_percentage:.1f})")
    else:
        print("[MOTOR] ⚠️ raw_df None! Fiş listesi yüklenmemiş.")
    st.rerun()

# ==============================================================================
# 4. HESAP LİSTESİ YARDIMCILARI
# ==============================================================================
# --- Türkçe alfabetik sıralama yardımcıları ---
_TR_ALPHABET = "aAbBcCçÇdDeEfFgGğĞhHıIiİjJkKlLmMnNoOöÖpPrRsSşŞtTuUüÜvVyYzZ"
_TR_RANK = {ch: i for i, ch in enumerate(_TR_ALPHABET)}

def tr_sort_key(s):
    """Türkçe alfabeye göre, büyük/küçük harf duyarsız sıralama anahtarı."""
    return [_TR_RANK.get(ch, 1000 + ord(ch)) for ch in str(s)]

def tr_sorted(iterable):
    """Bir listeyi Türkçe alfabetik sıraya dizer (Ç, Ğ, İ, Ö, Ş, Ü doğru yerde)."""
    return sorted(iterable, key=tr_sort_key)


@st.cache_data(show_spinner=False)
def get_sorted_account_list(df_hp):
    if df_hp is None or df_hp.empty or "Hesap Kodu" not in df_hp.columns or "Hesap Adı" not in df_hp.columns:
        return [""], {}
    df_temp = df_hp.copy()
    if "Detay E/H" in df_temp.columns:
        # Sadece "Detay = Evet" olan hesaplar listelensin (whitelist).
        include = ['evet', 'e', 'yes', 'true', '1', 'aktif', 'var', 'y']
        df_temp = df_temp[df_temp["Detay E/H"].astype(str).str.strip().str.lower().isin(include)]
    df_temp["Hesap Kodu"] = df_temp["Hesap Kodu"].fillna("").astype(str).str.strip()
    df_temp["Hesap Adı"] = df_temp["Hesap Adı"].fillna("").astype(str).str.strip()
    df_temp = df_temp[df_temp["Hesap Kodu"] != ""]
    df_temp = df_temp[~df_temp["Hesap Kodu"].str.lower().isin(['nan', 'none', '<na>', 'nat', ''])]
    df_temp = df_temp[df_temp["Hesap Kodu"].str.contains(r'[0-9A-Za-z]', na=False)]
    def sort_key(c):
        # Sayısal parçaları sayı olarak (100 > 20 doğru), metin parçalarını Türkçe alfabeye göre sırala
        parts = re.split(r'[\s\.\-_]+', str(c))
        key_parts = []
        for p in parts:
            if p.isdigit():
                key_parts.append(f"{int(p):010d}")
            else:
                key_parts.append("".join(f"{r:04d}" for r in tr_sort_key(p)))
        return ".".join(key_parts)
    df_temp["_sort"] = df_temp["Hesap Kodu"].apply(sort_key)
    df_sorted = df_temp.sort_values("_sort").reset_index(drop=True)
    liste = [""] + (df_sorted["Hesap Kodu"] + " - " + df_sorted["Hesap Adı"]).tolist()
    code_idx = {kod: i+1 for i, kod in enumerate(df_sorted["Hesap Kodu"])}
    return liste, code_idx

def get_hesap_secenekleri():
    hp = st.session_state.hesap_plani
    cid = st.session_state.get('current_company_id', 1)
    current_key = f"c{cid}_empty" if hp.empty else f"c{cid}_{len(hp)}_{hash(tuple(hp['Hesap Kodu'].tolist()))}"
    if st.session_state.get('hp_cache_key') != current_key:
        st.session_state.hp_list, st.session_state.hp_idx = get_sorted_account_list(hp)
        st.session_state.hp_cache_key = current_key
    return st.session_state.get('hp_list', [""]), st.session_state.get('hp_idx', {})

def render_account_selector(label, key_prefix, default_code=""):
    hesap_list, code_idx = get_hesap_secenekleri()
    if len(hesap_list) <= 1:
        t_code = st.text_input(f"{label} Kodu*", value=default_code, key=f"{key_prefix}_code")
        t_name = st.text_input(f"{label} Adı", value="", key=f"{key_prefix}_name")
        return t_code.strip(), t_name.strip()
    def_idx = code_idx.get(default_code, 0) if default_code else 0
    secilen = st.selectbox(f"{label}*", options=hesap_list, index=min(def_idx, len(hesap_list)-1), key=f"{key_prefix}_sel")
    t_code = secilen.split(" - ")[0].strip() if secilen else ""
    t_name = secilen.split(" - ", 1)[1].strip() if " - " in secilen else ""
    return t_code, t_name

# ==============================================================================
# 5. SOL MENÜ (Sidebar)
# ==============================================================================
with st.sidebar:
    user_name = current_user.get("full_name", current_user.get("username", "Kullanıcı"))
    user_role = current_user.get("role", "user")
    st.markdown(f"### 🏢 **Finansal Otomasyon v6**")
    st.markdown(f"👤 **{user_name}** `({user_role})`")
    st.caption(f"{'🟢 Supabase' if db.online else '🔴 Offline'}")
    st.markdown("---")
    
    # FİRMA SEÇİCİ
    if db.online:
        uid = current_user.get("id", 0)
        companies = db.get_allowed_companies(uid, user_role)
        if companies:
            comp_names = [f"{c['name']} ({c['code']})" for c in companies]
            cur_idx = next((i for i, c in enumerate(companies) if c['id'] == st.session_state.current_company_id), 0)
            sel = st.selectbox("🏭 Firma", comp_names, index=cur_idx, key="company_select")
            sel_comp = companies[comp_names.index(sel)]
            if sel_comp['id'] != st.session_state.current_company_id:
                st.session_state.current_company_id = sel_comp['id']
                st.session_state.current_company_name = sel_comp['name']
                st.session_state._df_key += 1
                load_company_data(sel_comp['id'])
                st.session_state._last_company_id = sel_comp['id']
                st.rerun()
            st.caption(f"🏭 **{sel_comp['name']}**")
        else:
            st.warning("⚠️ Firma tanımlı değil.")
    st.markdown("---")
    
    menu_options = ["📊 İşlem Merkezi", "🏦 Banka Eşleştirmeleri", "📝 Kural Yöneticisi", "📈 Kural Analizi", "🧾 Zirve Aktarım", "🗂️ Resmi Hesap Listesi", "📜 Sistem Logları"]
    menu_icons = ["bar-chart-line-fill", "bank2", "sliders", "graph-up-arrow", "file-earmark-spreadsheet", "folder2-open", "journal-text"]
    if is_admin():
        menu_options.append("👥 Yönetim")
        menu_icons.append("people-fill")
    if HAS_OPTION_MENU:
        menu = option_menu(None, menu_options, icons=menu_icons, default_index=0, styles={"container": {"padding": "0!important"}, "icon": {"color": "#3B82F6"}, "nav-link": {"font-size": "0.85rem", "margin": "3px 0", "border-radius": "8px"}, "nav-link-selected": {"background-color": "#1E293B", "color": "#FFF"}})
    else:
        menu = st.radio("Modüller", menu_options, label_visibility="collapsed")
    
    st.markdown("---")
    st.subheader("📂 Veri Aktarımı")
    uploaded_file = st.file_uploader("Yeni Ekstre Yükle", type=['xlsx', 'xls', 'csv'])
    
    if st.button("🔄 Motoru Çalıştır", type="primary", width="stretch"):
        if st.session_state.raw_df is not None:
            with st.spinner("İşleniyor..."):
                mapped_df, stats = apply_rules(st.session_state.raw_df, st.session_state.rules, st.session_state.bank_accounts)
                st.session_state.mapped_df = mapped_df
                st.session_state.stats = stats
            add_log("Motor Çalıştırıldı", f"{len(mapped_df)} satır", "INFO")
            st.toast("⚡ Motor tamamlandı!", icon="⚡")
            st.rerun()
        else:
            st.warning("Ekstre dosyası yükleyin.")
    
    if uploaded_file:
        # Aynı dosyayı tekrar işlemeyi önle
        uploaded_name = uploaded_file.name
        last_uploaded = st.session_state.get('_last_uploaded_file', '')
        
        if uploaded_name != last_uploaded:
            try:
                fb = uploaded_file.read()
                df_new = pd.read_excel(BytesIO(fb)) if uploaded_file.name.endswith(('.xlsx', '.xls')) else pd.read_csv(BytesIO(fb))
                st.session_state.raw_df = df_new
                st.session_state._last_uploaded_file = uploaded_name
                cid = st.session_state.current_company_id
                if db.online:
                    # Tarihleri DD.MM.YYYY formatına çevir (Unix timestamp dahil)
                    df_for_json = df_new.copy()
                    if 'Tarih' in df_for_json.columns:
                        _tser = df_for_json['Tarih'].astype(str).str.strip()
                        sample = ""
                        for _v in _tser:
                            if _v and _v not in ['nan', 'none', 'NaT', '', 'None', '<NA>']:
                                sample = _v
                                break

                        # Unix timestamp (milisaniye) kontrolü
                        if sample.isdigit() and len(sample) > 10:
                            dt = pd.to_datetime(pd.to_numeric(df_for_json['Tarih'], errors='coerce'), unit='ms', errors='coerce')
                        # DD.MM.YYYY / DD/MM/YYYY → gün önce
                        elif re.match(r'^\d{1,2}[./]\d{1,2}[./]\d{2,4}', sample):
                            dt = pd.to_datetime(_tser, errors='coerce', dayfirst=True)
                        # YYYY-MM-DD gibi ISO / yıl-önce → dayfirst KULLANMA (gün-ay ters olmasın)
                        elif re.match(r'^\d{4}[-./]\d{1,2}[-./]\d{1,2}', sample):
                            dt = pd.to_datetime(_tser, errors='coerce', dayfirst=False)
                        else:
                            dt = pd.to_datetime(_tser, errors='coerce', dayfirst=True)

                        df_for_json['Tarih'] = df_for_json['Tarih'].astype(object)
                        mask = dt.notna()
                        df_for_json.loc[mask, 'Tarih'] = dt[mask].dt.strftime('%d.%m.%Y')
                    
                    db.save_raw_data(df_for_json.to_dict(orient="records"), cid, current_user.get("username", "system"))
                mapped_df, stats = apply_rules(df_new, st.session_state.rules, st.session_state.bank_accounts)
                st.session_state.mapped_df = mapped_df
                st.session_state.stats = stats
                add_log("Dosya Yüklendi", f"{uploaded_file.name} ({len(df_new)} satır)", "SUCCESS")
                st.toast(f"✅ '{uploaded_file.name}' yüklendi!", icon="🎉")
                st.rerun()
            except Exception as e:
                st.error(f"Dosya hatası: {e}")
    
    if st.session_state.raw_df is not None:
        st.caption(f"📋 Yüklü: **{len(st.session_state.raw_df)}** satır")
        if st.button("🗑️ Fiş Listesini Temizle", width="stretch"):
            st.session_state.raw_df = None
            st.session_state.mapped_df = None
            st.session_state.stats = None
            if db.online:
                db.delete_raw_data(st.session_state.current_company_id)
            add_log("Fiş Listesi Temizlendi", "Kullanıcı", "WARNING")
            st.rerun()
    
    st.markdown("---")
    st.caption(f"⚡ Kural: **{len([r for r in st.session_state.rules if r.is_active])}** | 🏦 Banka: **{len(st.session_state.bank_accounts)}**")
    if st.button("🚪 Çıkış Yap", width="stretch"):
        logout()
        st.rerun()

# ==============================================================================
# 6. HIZLI KURAL EKLEME DIALOG
# ==============================================================================
@st.dialog("⚡ Hızlı Kural Ekle", width="large")
def hizli_kural_dialog(row_data):
    def get_val(keys, default=""):
        for k in keys:
            if k in row_data.index:
                val = str(row_data[k])
                if val.lower() not in ['nan', 'none', '<na>', 'nat', '']:
                    return val.strip()
        return default
    
    def_cari = get_val(['Cari Tanım', 'Cari Tanım (Alıcı)'])
    def_banka = get_val(['Banka Adı'])
    def_proje = get_val(['Proje'])
    def_bkv = get_val(['B/K/V'])
    def_fis = get_val(['Fiş Türü'])
    def_aciklama = get_val(['Açıklama'])
    def_hareket = get_val(['Hareket Tipi'])
    def_tutar = get_val(['Tutar'], "0")
    def_tarih = get_val(['Tarih'])
    
    st.markdown(f"""<div style="background:#F8FAFC;border:1px solid #CBD5E1;border-radius:8px;padding:12px;margin-bottom:16px;">
        <div style="display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px;font-size:0.85rem;">
            <div><b>Tarih:</b> {def_tarih or '-'}</div>
            <div><b>Banka:</b> <span style="color:#2563EB;font-weight:600">{def_banka or '-'}</span></div>
            <div><b>Hareket:</b> {def_hareket or '-'}</div>
            <div><b>Tutar:</b> <span style="color:#059669;font-weight:700">{def_tutar} ₺</span></div>
        </div>
        <div style="margin-top:6px;font-size:0.85rem;"><b>Cari:</b> {def_cari or '-'}<br><b>Açıklama:</b> <i>{def_aciklama or '-'}</i></div>
    </div>""", unsafe_allow_html=True)
    
    st.markdown("##### 🎯 Hedef Muhasebe Hesabı")
    t_code, t_name = render_account_selector("Hesap Kodu", f"hizli_{row_data.name}", get_val(['Muhasebe Hesap Kodu']))
    st.markdown("##### ⚙️ Kural Adı ve Öncelik")
    c1, c2 = st.columns([3, 1])
    with c1: r_name = st.text_input("Kural Adı*", value=f"Hızlı - {def_cari[:25] if def_cari else (def_aciklama[:25] if def_aciklama else 'Yeni')}", key="hk_name")
    with c2: r_priority = st.number_input("Öncelik", value=50, step=1, key="hk_prio")
    st.markdown("##### 🔍 Eşleşme Kriterleri")
    k1, k2 = st.columns(2)
    with k1:
        c_cari = st.text_input("Cari Tanım", value=def_cari, key="hk_cari")
        c_banka = st.text_input("Banka Adı", value=def_banka, key="hk_banka")
        c_proje = st.text_input("Proje", value=def_proje, key="hk_proje")
        r_min = st.text_input("Min Tutar (₺)", value="", key="hk_min")
    with k2:
        c_aciklama = st.text_input("Açıklama", value=def_aciklama, key="hk_acik")
        c_fis = st.text_input("Fiş Türü", value=def_fis, key="hk_fis")
        c_bkv = st.text_input("B/K/V", value=def_bkv, key="hk_bkv")
        r_max = st.text_input("Max Tutar (₺)", value="", key="hk_max")
    h_opts = ["", "GELEN", "GIDEN", "KARISIK", "YOK"]
    try: h_idx = h_opts.index(def_hareket.upper()) if def_hareket.upper() in h_opts else 0
    except: h_idx = 0
    c_hareket = st.selectbox("Hareket Tipi", options=h_opts, index=h_idx, key="hk_hareket")
    
    st.write("")
    btn1, btn2 = st.columns([1, 2])
    with btn1:
        if st.button("❌ İptal", width="stretch"):
            st.session_state._df_key += 1
            for key in list(st.session_state.keys()):
                if key.startswith("hizli_") or key.startswith("hk_"):
                    del st.session_state[key]
            st.rerun()
    with btn2:
        if st.button("💾 Kaydet ve Uygula", type="primary", width="stretch"):
            if r_name and t_code:
                try:
                    mn = float(r_min.replace(',', '.')) if r_min.strip() else None
                    mx = float(r_max.replace(',', '.')) if r_max.strip() else None
                except ValueError:
                    st.error("Tutar sayısal olmalıdır!"); return
                new_rule = Rule(name=r_name, priority=int(r_priority),
                    criteria={"proje": c_proje, "banka_adi": c_banka, "cari_tanim": c_cari, "bkv": c_bkv, "fis_turu": c_fis, "aciklama": c_aciklama, "hareket_tipi": c_hareket},
                    target_account_code=t_code, target_account_name=t_name, min_amount=mn, max_amount=mx,
                    note="Hızlı Kural", created_by=current_user.get("username", ""))
                st.session_state.rules.append(new_rule)
                save_to_db()
                add_log("Hızlı Kural Eklendi", f"{r_name} -> {t_code}", "SUCCESS")
                # Dialog kapat + Motor çalıştır
                st.session_state._df_key += 1
                for key in list(st.session_state.keys()):
                    if key.startswith("hizli_") or key.startswith("hk_"):
                        del st.session_state[key]
                if st.session_state.raw_df is not None:
                    mapped_df, stats = apply_rules(st.session_state.raw_df, st.session_state.rules, st.session_state.bank_accounts)
                    st.session_state.mapped_df = mapped_df
                    st.session_state.stats = stats
                st.toast(f"✅ '{r_name}' eklendi!", icon="🎉")
                st.rerun()
            else:
                st.error("⚠️ Kural Adı ve Hedef Hesap Kodu zorunludur!")

# ==============================================================================
# 7. İŞLEM MERKEZİ
# ==============================================================================
if menu == "📊 İşlem Merkezi":
    st.markdown('<div class="main-header"><h1>📊 İşlem Merkezi</h1><p>Filtreleme, hızlı kural ekleme ve muhasebeleştirme.</p></div>', unsafe_allow_html=True)
    if st.session_state.mapped_df is not None and not st.session_state.mapped_df.empty:
        df = st.session_state.mapped_df.copy()
        stats = st.session_state.stats
        conflict_col = df['_conflict_count'].fillna(0).astype(int) if '_conflict_count' in df.columns else pd.Series(0, index=df.index)
        hesap_bos = df['Muhasebe Hesap Kodu'].astype(str).str.strip().str.lower().isin(["", "nan", "none"])
        df.insert(0, 'Durum', np.where(conflict_col > 1, "🟡 Çakışma", np.where(hesap_bos, "⚪ Bekliyor", "🟢 Hazır")))
        total = stats.total_records if stats else len(df)
        matched = stats.matched_records if stats else len(df[df['Durum']=='🟢 Hazır'])
        unmatched = stats.unmatched_records if stats else len(df[df['Durum']=='⚪ Bekliyor'])
        conflicts = stats.conflict_records if stats else len(df[df['Durum']=='🟡 Çakışma'])
        toplam_hacim = stats.total_volume if stats else float(df['Tutar'].sum())
        match_rate = stats.match_rate_percentage if stats else (matched/total*100 if total>0 else 0)
        st.markdown(f"""<div class="kpi-container">
            <div class="kpi-card"><div class="kpi-card-title">📝 Toplam</div><div class="kpi-card-value">{total:,}</div></div>
            <div class="kpi-card"><div class="kpi-card-title">🟢 Hazır</div><div class="kpi-card-value" style="color:#10B981">{matched:,}</div><div class="kpi-card-sub">%{match_rate:.1f}</div></div>
            <div class="kpi-card"><div class="kpi-card-title">⚪ Bekliyor</div><div class="kpi-card-value" style="color:#F59E0B">{unmatched:,}</div></div>
            <div class="kpi-card"><div class="kpi-card-title">🟡 Çakışma</div><div class="kpi-card-value" style="color:#EF4444">{conflicts:,}</div></div>
            <div class="kpi-card"><div class="kpi-card-title">💰 Hacim</div><div class="kpi-card-value" style="color:#3B82F6">{toplam_hacim:,.2f} ₺</div></div>
        </div>""", unsafe_allow_html=True)
        st.progress(match_rate / 100.0, text=f"🚀 **%{match_rate:.1f}** Tamamlandı")
        
        # FİLTRELEME
        with st.expander("🔍 **Detaylı Filtreleme**", expanded=True):
            f1, f2, f3 = st.columns([2, 3, 2])
            with f1: durum_f = st.multiselect("📌 Durum", ["🟢 Hazır", "⚪ Bekliyor", "🟡 Çakışma"], default=[], placeholder="Tümü")
            with f2: arama = st.text_input("🔎 Genel Arama", placeholder="Akbank, fatura, Mega...")
            with f3:
                h_opts_f = sorted([str(x) for x in df['Hareket Tipi'].unique() if str(x).strip()]) if 'Hareket Tipi' in df.columns else []
                hareket_f = st.multiselect("🔄 Hareket", h_opts_f, default=[], placeholder="Tümü")
            f4, f5, f6, f7 = st.columns(4)
            with f4: banka_f = st.multiselect("🏦 Banka", tr_sorted([str(x) for x in df['Banka Adı'].unique() if str(x).strip()]) if 'Banka Adı' in df.columns else [], placeholder="Tümü")
            with f5: fis_f = st.multiselect("📑 Fiş", tr_sorted([str(x) for x in df['Fiş Türü'].unique() if str(x).strip()]) if 'Fiş Türü' in df.columns else [], placeholder="Tümü")
            with f6: proje_f = st.multiselect("🎯 Proje", tr_sorted([str(x) for x in df['Proje'].unique() if str(x).strip()]) if 'Proje' in df.columns else [], placeholder="Tümü")
            with f7:
                mn_a = float(df['Tutar'].min()) if 'Tutar' in df.columns and not df['Tutar'].empty else 0.0
                mx_a = float(df['Tutar'].max()) if 'Tutar' in df.columns and not df['Tutar'].empty else 1.0
                tutar_f = st.slider("💵 Tutar (₺)", mn_a, mx_a, (mn_a, mx_a), step=100.0) if mn_a < mx_a else (mn_a, mx_a)
            ca1, ca2, ca3, ca4 = st.columns([2, 2, 3, 1])
            with ca1: k_kolon = st.selectbox("🎯 Kolon", ["(Seçilmedi)", "Açıklama", "Cari Tanım", "Muhasebe Hesap Kodu"])
            with ca2: k_op = st.selectbox("⚙️ Op", ["İçerir", "Başlar", "Biter", "Tam Eşleşir", "İçermez"])
            with ca3: k_deger = st.text_input("✍️ Değer", placeholder="Aranacak kelime...")
            with ca4:
                st.write(""); st.write("")
                if st.button("🔄 Sıfırla", width="stretch"): st.rerun()
        
        dd = df.copy()
        if durum_f: dd = dd[dd['Durum'].isin(durum_f)]
        if arama and arama.strip():
            q = arama.strip().lower()
            sc = [c for c in dd.columns if dd[c].dtype == object]
            if sc:
                comb = dd[sc[0]].astype(str)
                for c in sc[1:]: comb = comb + "|" + dd[c].astype(str)
                dd = dd[comb.str.lower().str.contains(q, na=False)]
        if hareket_f: dd = dd[dd['Hareket Tipi'].astype(str).isin(hareket_f)]
        if banka_f: dd = dd[dd['Banka Adı'].astype(str).isin(banka_f)]
        if fis_f: dd = dd[dd['Fiş Türü'].astype(str).isin(fis_f)]
        if proje_f: dd = dd[dd['Proje'].astype(str).isin(proje_f)]
        if tutar_f and len(tutar_f) == 2: dd = dd[(dd['Tutar'] >= tutar_f[0]) & (dd['Tutar'] <= tutar_f[1])]
        if k_kolon != "(Seçilmedi)" and k_deger and k_deger.strip():
            cs = dd[k_kolon].astype(str); v = k_deger.strip()
            if k_op == "İçerir": dd = dd[cs.str.contains(v, case=False, na=False)]
            elif k_op == "Başlar": dd = dd[cs.str.lower().str.startswith(v.lower(), na=False)]
            elif k_op == "Biter": dd = dd[cs.str.lower().str.endswith(v.lower(), na=False)]
            elif k_op == "Tam Eşleşir": dd = dd[cs.str.lower() == v.lower()]
            elif k_op == "İçermez": dd = dd[~cs.str.contains(v, case=False, na=False)]
        
        b1, b2 = st.columns([7, 3])
        with b1: st.markdown(f"**⚡ Gösterilen:** `{len(dd):,}` / `{len(df):,}`")
        with b2:
            out = BytesIO()
            dd.drop(columns=[c for c in ["Durum","_conflict_count"] if c in dd.columns], errors="ignore").to_excel(out, index=False, engine="openpyxl")
            st.download_button("📥 XLSX İndir", data=out.getvalue(), file_name=f"islenmis_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary", width="stretch")
        
        st.caption("💡 Satıra tıklayarak hızlı kural ekleyebilirsiniz!")
        event = st.dataframe(dd, height=580, width="stretch", key=f"main_df_{st.session_state._df_key}", on_select="rerun", selection_mode="single-row",
            column_config={"Durum": st.column_config.TextColumn("Durum", width="small"), "Tutar": st.column_config.NumberColumn("Tutar (₺)", format="%.2f ₺"),
                "Tarih": st.column_config.TextColumn("Tarih", width="small"), "Banka Adı": st.column_config.TextColumn("Banka", width="medium"),
                "Cari Tanım": st.column_config.TextColumn("Cari", width="large"), "Açıklama": st.column_config.TextColumn("Açıklama", width="large"),
                "Muhasebe Hesap Kodu": st.column_config.TextColumn("Muh. Kodu", width="medium"), "Muhasebe Hesap Adı": st.column_config.TextColumn("Muh. Adı", width="large"),
                "Eşleşen Kural ID": st.column_config.TextColumn("Kural", width="medium")})
        if len(event.selection.rows) > 0:
            hizli_kural_dialog(dd.iloc[event.selection.rows[0]])
    else:
        st.info("👈 Sol menüden ekstre yükleyin. DB'de kayıtlı veri varsa otomatik gelir.")

# ==============================================================================
# 8-14. DİĞER MODÜLLER (Banka, Kural, Analiz, Zirve, Hesap, Log, Yönetim)
# ==============================================================================
elif menu == "🏦 Banka Eşleştirmeleri":
    st.markdown('<div class="main-header"><h1>🏦 Banka Eşleştirmeleri</h1></div>', unsafe_allow_html=True)
    eslesmis = [b.bank_name.strip() for b in st.session_state.bank_accounts]
    yeni = tr_sorted([str(b).strip() for b in (st.session_state.raw_df["Banka Adı"].dropna().unique().tolist() if st.session_state.raw_df is not None and "Banka Adı" in st.session_state.raw_df.columns else []) if str(b).strip() and str(b).strip() not in eslesmis]) if st.session_state.raw_df is not None else []
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("➕ Yeni Eşleştirme")
        with st.form("bank_form", clear_on_submit=True):
            if yeni:
                st.info(f"💡 Eşleşmemiş **{len(yeni)}** banka")
                b_name = st.selectbox("Banka Seçin", [""] + yeni)
            else:
                b_name = st.text_input("Banka Adı")
            t_code, t_name = render_account_selector("Hesap Kodu", "bank_map")
            if st.form_submit_button("Eşleştir", type="primary", width="stretch"):
                if b_name and t_code:
                    new_bank = BankAccountDefinition(bank_name=b_name.strip(), account_code=t_code, account_name=t_name)
                    st.session_state.bank_accounts.append(new_bank)
                    # Sadece yeni banka hesabını ekle - çok hızlı!
                    save_bank_account_to_db(new_bank)
                    add_log("Banka Eşleştirildi", f"{b_name} -> {t_code}", "SUCCESS")
                    st.toast(f"✅ '{b_name}' eşleştirildi!", icon="🏦")
                    rerun_motor()
    with c2:
        st.subheader(f"📋 Kayıtlı ({len(st.session_state.bank_accounts)})")
        if st.session_state.bank_accounts:
            st.dataframe(pd.DataFrame([{"Banka": b.bank_name, "Kod": b.account_code, "Hesap": b.account_name} for b in st.session_state.bank_accounts]), height=400, width="stretch")
            if st.button("🗑️ Tümünü Temizle", width="stretch"):
                st.session_state.bank_accounts = []
                # DB'den tüm banka hesaplarını sil
                if db.online:
                    db.client.table("bank_accounts").delete().eq("company_id", st.session_state.current_company_id).execute()
                rerun_motor()

elif menu == "📝 Kural Yöneticisi":
    st.markdown('<div class="main-header"><h1>📝 Kural Yöneticisi</h1></div>', unsafe_allow_html=True)
    
    @st.dialog("✏️ Kuralı Düzenle", width="large")
    def kural_duzenle(idx):
        r = st.session_state.rules[idx]
        c1, c2, c3 = st.columns([3,1,1])
        with c1: e_name = st.text_input("Kural Adı*", value=r.name, key="dlg_n")
        with c2: e_prio = st.number_input("Öncelik", value=r.priority, step=1, key="dlg_p")
        with c3: st.write(""); st.write(""); e_active = st.checkbox("Aktif", value=r.is_active, key="dlg_a")
        k1, k2 = st.columns(2)
        with k1:
            e_proje = st.text_input("Proje", value=r.criteria.get('proje',''), key="dlg_pr")
            e_banka = st.text_input("Banka", value=r.criteria.get('banka_adi',''), key="dlg_b")
            e_cari = st.text_input("Cari", value=r.criteria.get('cari_tanim',''), key="dlg_c")
            e_bkv = st.text_input("B/K/V", value=r.criteria.get('bkv',''), key="dlg_bk")
        with k2:
            e_fis = st.text_input("Fiş", value=r.criteria.get('fis_turu',''), key="dlg_f")
            e_acik = st.text_input("Açıklama", value=r.criteria.get('aciklama',''), key="dlg_ac")
            h_opts = ["","GELEN","GIDEN","KARISIK","YOK"]
            e_har = st.selectbox("Hareket", h_opts, index=h_opts.index(r.criteria.get('hareket_tipi','')) if r.criteria.get('hareket_tipi','') in h_opts else 0, key="dlg_h")
        e_code, e_name_acc = render_account_selector("Hedef Hesap", f"edit_{idx}", r.target_account_code)
        a1, a2 = st.columns(2)
        with a1: e_min = st.text_input("Min ₺", value=str(r.min_amount) if r.min_amount else "", key="dlg_mn")
        with a2: e_max = st.text_input("Max ₺", value=str(r.max_amount) if r.max_amount else "", key="dlg_mx")
        btn1, btn2 = st.columns([1,2])
        with btn1:
            if st.button("❌ İptal", width="stretch"): st.rerun()
        with btn2:
            if st.button("💾 Güncelle", type="primary", width="stretch"):
                if e_name and e_code:
                    try:
                        mn = float(e_min.replace(',','.')) if e_min.strip() else None
                        mx = float(e_max.replace(',','.')) if e_max.strip() else None
                    except: st.error("Tutar sayısal!"); return
                    st.session_state.rules[idx] = Rule(name=e_name, priority=int(e_prio),
                        criteria={"proje":e_proje,"banka_adi":e_banka,"cari_tanim":e_cari,"bkv":e_bkv,"fis_turu":e_fis,"aciklama":e_acik,"hareket_tipi":e_har},
                        target_account_code=e_code, target_account_name=e_name_acc, min_amount=mn, max_amount=mx, is_active=e_active, created_by=current_user.get("username",""))
                    # DB'den tüm kuralları sil ve yeniden kaydet
                    if db.online:
                        db.client.table("rules").delete().eq("company_id", st.session_state.current_company_id).execute()
                        if st.session_state.rules:
                            db.save_rules([r.model_dump() for r in st.session_state.rules], st.session_state.current_company_id)
                    add_log("Kural Güncellendi", e_name, "SUCCESS")
                    st.toast(f"✅ '{e_name}' güncellendi!", icon="✏️")
                    rerun_motor()
    
    tab_list, tab_add, tab_conflict = st.tabs(["📋 Mevcut Kurallar", "➕ Kural Ekle", "⚡ Çakışma"])
    with tab_list:
        if st.session_state.rules:
            rule_data = []
            for idx, r in enumerate(st.session_state.rules):
                rule_data.append({"_idx": idx, "Seç": False, "D": "🟢" if r.is_active else "🔴", "Önc": r.priority, "Kural Adı": r.name, "Hedef Kod": r.target_account_code,
                    "Hedef Hesap": r.target_account_name or "", "Proje": r.criteria.get('proje','') or "", "Banka": r.criteria.get('banka_adi','') or "",
                    "Cari": r.criteria.get('cari_tanim','') or "", "Açıklama": r.criteria.get('aciklama','') or "", "Fiş": r.criteria.get('fis_turu','') or "",
                    "Hareket": r.criteria.get('hareket_tipi','') or "", "B/K/V": r.criteria.get('bkv','') or "",
                    "Min ₺": f"{r.min_amount:,.2f}" if r.min_amount else "", "Max ₺": f"{r.max_amount:,.2f}" if r.max_amount else ""})
            df_rules = pd.DataFrame(rule_data)
            edited = st.data_editor(df_rules.drop(columns=["_idx"]), height=500, width="stretch", disabled=[c for c in df_rules.columns if c != "Seç"])
            secilen = [int(df_rules.iloc[i]["_idx"]) for i, row in edited.iterrows() if row.get("Seç")]
            st.markdown("---")
            bc1, bc2, bc3 = st.columns([2,2,2])
            with bc1:
                if secilen and st.button(f"🗑️ {len(secilen)} Sil", type="primary", width="stretch"):
                    for i in sorted(secilen, reverse=True): st.session_state.rules.pop(i)
                    # DB'den tüm kuralları sil ve yeniden kaydet
                    if db.online:
                        db.client.table("rules").delete().eq("company_id", st.session_state.current_company_id).execute()
                        if st.session_state.rules:
                            db.save_rules([r.model_dump() for r in st.session_state.rules], st.session_state.current_company_id)
                    rerun_motor()
            with bc2:
                kl = [f"{i+1}. {r.name}" for i, r in enumerate(st.session_state.rules)]
                sec = st.selectbox("✏️ Düzenle", ["(Seçin...)"] + kl, key="edit_sel")
                if sec != "(Seçin...)" and st.button("✏️ Düzenle", width="stretch"): kural_duzenle(kl.index(sec))
            with bc3:
                if st.button("🗑️ TÜMÜNÜ Sil", width="stretch"):
                    st.session_state.rules = []
                    # DB'den tüm kuralları sil
                    if db.online:
                        db.client.table("rules").delete().eq("company_id", st.session_state.current_company_id).execute()
                    rerun_motor()
        else:
            st.info("Henüz kural yok.")
    with tab_add:
        with st.form("add_rule", clear_on_submit=True):
            c1, c2 = st.columns([3,1])
            r_name = c1.text_input("Kural Adı*"); r_prio = c2.number_input("Öncelik", value=50, step=1)
            k1, k2 = st.columns(2)
            with k1: c_proje = st.text_input("Proje"); c_banka = st.text_input("Banka"); c_cari = st.text_input("Cari"); c_bkv = st.text_input("B/K/V")
            with k2: c_fis = st.text_input("Fiş"); c_acik = st.text_input("Açıklama"); c_har = st.selectbox("Hareket", ["","GELEN","GIDEN","KARISIK","YOK"])
            t_code, t_name = render_account_selector("Hedef Hesap", "add_rule")
            a1, a2 = st.columns(2)
            with a1: r_min = st.text_input("Min ₺")
            with a2: r_max = st.text_input("Max ₺")
            if st.form_submit_button("🚀 Ekle", type="primary", width="stretch"):
                if r_name and t_code:
                    try:
                        mn = float(r_min.replace(',','.')) if r_min.strip() else None
                        mx = float(r_max.replace(',','.')) if r_max.strip() else None
                    except: st.error("Tutar sayısal!"); st.stop()
                    new_rule = Rule(name=r_name, priority=int(r_prio),
                        criteria={"proje":c_proje,"banka_adi":c_banka,"cari_tanim":c_cari,"bkv":c_bkv,"fis_turu":c_fis,"aciklama":c_acik,"hareket_tipi":c_har},
                        target_account_code=t_code, target_account_name=t_name, min_amount=mn, max_amount=mx, created_by=current_user.get("username",""))
                    st.session_state.rules.append(new_rule)
                    # Sadece yeni kuralı ekle - çok hızlı!
                    save_rule_to_db(new_rule)
                    add_log("Kural Eklendi", r_name, "SUCCESS")
                    st.toast(f"✅ '{r_name}' eklendi!", icon="🚀")
                    rerun_motor()
    with tab_conflict:
        conflicts = find_conflicting_rules(st.session_state.rules)
        if conflicts:
            st.warning(f"⚠️ {len(conflicts)} çakışma!")
            for c in conflicts:
                with st.expander(f"🔴 {c['rule1_name']} 🆚 {c['rule2_name']}"):
                    st.markdown(f"- **{c['rule1_name']}** → `{c['rule1_code']}`\n- **{c['rule2_name']}** → `{c['rule2_code']}`")
        else:
            st.success("🎉 Çakışma yok!")

elif menu == "📈 Kural Analizi":
    st.markdown('<div class="main-header"><h1>📈 Kural Analizi & Test</h1></div>', unsafe_allow_html=True)
    tab1, tab2, tab3 = st.tabs(["📊 Performans", "🧪 Test", "🤖 Öneri"])
    with tab1:
        if st.session_state.mapped_df is not None and st.session_state.rules:
            mapped = st.session_state.mapped_df
            perf = [{"Kural": r.name, "Kod": r.target_account_code, "Eşleşen": len(mapped[mapped['Eşleşen Kural ID'].astype(str).str.strip() == r.name]),
                "Hacim": f"{mapped[mapped['Eşleşen Kural ID'].astype(str).str.strip() == r.name]['Tutar'].sum():,.2f} ₺"} for r in st.session_state.rules]
            st.dataframe(pd.DataFrame(perf), width="stretch")
        else: st.info("Veri yükleyin.")
    with tab2:
        if st.session_state.raw_df is not None:
            raw_std = standardize_dataframe(st.session_state.raw_df.copy())
            with st.form("test_form"):
                tk1, tk2 = st.columns(2)
                with tk1: t_cari = st.text_input("Cari"); t_banka = st.text_input("Banka"); t_acik = st.text_input("Açıklama")
                with tk2: t_fis = st.text_input("Fiş"); t_har = st.selectbox("Hareket", ["","GELEN","GIDEN"]); t_proje = st.text_input("Proje")
                if st.form_submit_button("🔍 Test Et", type="primary", width="stretch"):
                    mask = pd.Series(True, index=raw_std.index)
                    if t_cari: mask &= raw_std['Cari Tanım'].str.lower().str.contains(t_cari.lower(), na=False)
                    if t_banka: mask &= raw_std['Banka Adı'].str.lower().str.contains(t_banka.lower(), na=False)
                    if t_acik: mask &= raw_std['Açıklama'].str.lower().str.contains(t_acik.lower(), na=False)
                    if t_fis: mask &= raw_std['Fiş Türü'].str.lower().str.contains(t_fis.lower(), na=False)
                    if t_har: mask &= raw_std['Hareket Tipi'].str.lower().str.contains(t_har.lower(), na=False)
                    if t_proje: mask &= raw_std['Proje'].str.lower().str.contains(t_proje.lower(), na=False)
                    sonuc = raw_std[mask]
                    st.metric("Eşleşen", f"{len(sonuc):,} / {len(raw_std):,}")
                    if len(sonuc) > 0: st.dataframe(sonuc.head(30), width="stretch")
        else: st.info("Veri yükleyin.")
    with tab3:
        if st.session_state.mapped_df is not None:
            eslesmemis = st.session_state.mapped_df[st.session_state.mapped_df['Muhasebe Hesap Kodu'].astype(str).str.strip() == ""]
            if len(eslesmemis) > 0:
                st.info(f"{len(eslesmemis)} eşleşmemiş satır analiz ediliyor...")
                oneriler = []
                if 'Cari Tanım' in eslesmemis.columns:
                    cc = eslesmemis[eslesmemis['Cari Tanım'].astype(str).str.strip()!=""].groupby('Cari Tanım').agg(Sayi=('Tutar','count'), Tutar=('Tutar','sum')).sort_values('Sayi', ascending=False).head(10)
                    for cari, row in cc.iterrows():
                        if row['Sayi'] >= 2: oneriler.append({"Tip": "👤 Cari", "Desen": cari[:50], "Satır": int(row['Sayi']), "Tutar": f"{row['Tutar']:,.2f} ₺"})
                if oneriler: st.dataframe(pd.DataFrame(oneriler), width="stretch")
                else: st.success("Belirgin desen yok.")
            else: st.success("🎉 Tümü eşleştirilmiş!")
        else: st.info("Veri yükleyin.")

elif menu == "🧾 Zirve Aktarım":
    st.markdown('<div class="main-header"><h1>🧾 Zirve Fiş Aktarımı</h1><p>Aylara bölünmüş Zirve muhasebe fiş formatı.</p></div>', unsafe_allow_html=True)
    if st.session_state.mapped_df is not None:
        df_h = st.session_state.mapped_df[st.session_state.mapped_df['Muhasebe Hesap Kodu'].astype(str).str.strip() != ""].copy()
        if len(df_h) == 0:
            st.warning("Hazır satır yok.")
        else:
            # Tarih parse ve ay extraction
            if 'Borç' not in df_h.columns:
                ba = df_h.apply(lambda r: (0.0, float(r.get('Tutar',0))) if 'GIDEN' in str(r.get('Hareket Tipi','')).upper() or 'GİDEN' in str(r.get('Hareket Tipi','')).upper() else (float(r.get('Tutar',0)), 0.0), axis=1, result_type='expand')
                df_h['Borç'] = ba[0]; df_h['Alacak'] = ba[1]
            df_h['_dt'] = pd.to_datetime(df_h['Tarih'], dayfirst=True, errors='coerce')
            df_h = df_h.sort_values('_dt', ascending=True, na_position='last').reset_index(drop=True)
            df_h['_ay'] = df_h['_dt'].dt.month.fillna(-1).astype(int)
            df_h['_yil'] = df_h['_dt'].dt.year.fillna(0).astype(int)
            
            aylar = sorted(df_h['_ay'].unique())
            ay_ad = {1:"Ocak",2:"Şubat",3:"Mart",4:"Nisan",5:"Mayıs",6:"Haziran",7:"Temmuz",8:"Ağustos",9:"Eylül",10:"Ekim",11:"Kasım",12:"Aralık",-1:"Tarihsiz"}
            
            # AY SEÇİCİ
            st.subheader("📅 Aktarılacak Ayları Seçin")
            ay_options = [f"{ay} - {ay_ad.get(ay, 'Bilinmeyen')}" for ay in aylar]
            selected_aylar = st.multiselect("Aylar (boş = tüm aylar)", options=ay_options, default=[], help="Hangi ayları aktarmak istediğinizi seçin. Boş bırakırsanız tüm aylar aktarılır.")
            
            # Seçilen ayları parse et
            if selected_aylar:
                selected_ay_ids = [int(sel.split(" - ")[0]) for sel in selected_aylar]
                df_h = df_h[df_h['_ay'].isin(selected_ay_ids)]
                st.info(f"✅ {len(df_h)} satır seçildi ({len(selected_ay_ids)} ay)")
            
            if len(df_h) == 0:
                st.warning("Seçilen aylarda satır yok.")
            else:
                # =====================================================================
                # DENGE & VERİ KALİTESİ KONTROLÜ - #6
                # =====================================================================
                st.subheader("⚖️ Denge ve Veri Kontrolü")
                # Banka hareketi özeti. NOT: Banka girişi ile çıkışı EŞİT OLMAK ZORUNDA DEĞİLDİR;
                # aradaki fark dönemin net para hareketidir (giren - çıkan).
                toplam_borc = float(df_h['Borç'].sum())     # banka girişleri (borç)
                toplam_alacak = float(df_h['Alacak'].sum()) # banka çıkışları (alacak)
                net_hareket = round(toplam_borc - toplam_alacak, 2)

                mc1, mc2, mc3 = st.columns(3)
                mc1.metric("Banka Girişi (Borç)", f"{toplam_borc:,.2f} ₺")
                mc2.metric("Banka Çıkışı (Alacak)", f"{toplam_alacak:,.2f} ₺")
                mc3.metric("Net Hareket (Giriş − Çıkış)", f"{net_hareket:,.2f} ₺")
                st.caption("ℹ️ Giriş ve çıkış eşit olmak zorunda değildir; fark, dönemin net para hareketidir.")

                # Zirve çift-kayıt: her satır iki kayıt üretir (borç/alacak ters çevrilir),
                # bu nedenle üretilecek fişte toplam Borçlu = toplam Alacaklı olur (yapısal denge).
                fis_borclu = toplam_borc + toplam_alacak    # üretilecek fişteki toplam borçlu
                fis_alacakli = toplam_alacak + toplam_borc  # üretilecek fişteki toplam alacaklı
                st.caption(f"🧾 Oluşturulacak fiş — Toplam Borçlu: **{fis_borclu:,.2f} ₺** = Toplam Alacaklı: **{fis_alacakli:,.2f} ₺** (çift kayıt gereği eşit).")

                # Veri kalitesi denetimleri (asıl önemli olanlar)
                tarihsiz_sayi = int((df_h['_ay'] == -1).sum())
                sifir_sayi = int(((df_h['Borç'] == 0) & (df_h['Alacak'] == 0)).sum())
                bankasiz_sayi = int((df_h['Banka Hesap Kodu'].astype(str).str.strip() == "").sum()) if 'Banka Hesap Kodu' in df_h.columns else 0
                cift_yon = int(((df_h['Borç'] != 0) & (df_h['Alacak'] != 0)).sum())

                sorunlar = []
                if tarihsiz_sayi > 0:
                    sorunlar.append(f"🗓️ **{tarihsiz_sayi}** satırın tarihi okunamadı ('Tarihsiz' grubuna düştü).")
                if sifir_sayi > 0:
                    sorunlar.append(f"0️⃣ **{sifir_sayi}** satırın hem borç hem alacak tutarı sıfır.")
                if bankasiz_sayi > 0:
                    sorunlar.append(f"🏦 **{bankasiz_sayi}** satırda Banka Hesap Kodu boş (çift kaydın bir tarafı eksik olur).")
                if cift_yon > 0:
                    sorunlar.append(f"↔️ **{cift_yon}** satırda hem borç hem alacak dolu (yön belirsiz).")

                if not sorunlar:
                    st.success("✅ Veri temiz. Aktarıma hazır.")
                else:
                    st.warning("⚠️ Aktarım öncesi kontrol edilmesi önerilen noktalar:")
                    for m in sorunlar:
                        st.markdown(f"- {m}")

                st.divider()
                st.success(f"✅ {len(df_h)} satır aktarıma hazır.")

                # =====================================================================
                # AYARLAR: Fiş No öneki + Format seçici - #7, #8
                # =====================================================================
                col_a, col_b = st.columns(2)
                with col_a:
                    prefix = st.text_input("Fiş No Öneki", value="BNK", help="Fiş numaraları: ÖNEK + YIL(4) + AY(2) + sıra(9) → örn. BNK202604000000001")
                with col_b:
                    export_format = st.selectbox("📄 Çıktı Formatı", ["Excel (.xlsx)", "CSV (.csv)", "Zirve TXT (.txt)"], help="Zirve sürümünüz Excel kabul etmiyorsa CSV veya TXT deneyin.")

                if st.button("🧾 Oluştur ve İndir", type="primary", width="stretch"):
                    buf = BytesIO(); sayac = {}
                    aylar_to_export = sorted(df_h['_ay'].unique())
                    # Benzersizlik denetimi için üretilen tüm fiş noları topla
                    uretilen_fno = set()
                    toplam_satir = 0
                    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
                        for ay in aylar_to_export:
                            rows = []
                            for _, row in df_h[df_h['_ay'] == ay].iterrows():
                                # Fiş no: ÖNEK + YIL(4 hane) + AY(2 hane) + sıra(9 hane) → örn. BNK202604000000001
                                yil = int(row.get('_yil', 0))
                                yil4 = f"{yil:04d}" if yil > 0 else "0000"
                                anahtar = (yil4, ay)
                                sayac[anahtar] = sayac.get(anahtar, 0) + 1
                                fno = f"{prefix}{yil4}{ay:02d}{sayac[anahtar]:09d}"
                                uretilen_fno.add(fno)
                                rows.append({"Hesap Kodu": str(row.get("Banka Hesap Kodu","")), "Evrak Tarihi": str(row.get("Tarih","")), "Evrak No": fno, "B.T.": 8, "Vergi/TC No": "", "Açıklama": str(row.get("Açıklama","")), "Para Birimi": "", "Döviz Tutarı": "", "Borçlu": float(row.get("Borç",0)), "Alacaklı": float(row.get("Alacak",0)), "Belge Türü Açıklaması (B.Türü 8 İse)": "Banka Aktarım", "Ödeme Şekli": ""})
                                rows.append({"Hesap Kodu": str(row.get("Muhasebe Hesap Kodu","")), "Evrak Tarihi": str(row.get("Tarih","")), "Evrak No": fno, "B.T.": 8, "Vergi/TC No": "", "Açıklama": str(row.get("Açıklama","")), "Para Birimi": "", "Döviz Tutarı": "", "Borçlu": float(row.get("Alacak",0)), "Alacaklı": float(row.get("Borç",0)), "Belge Türü Açıklaması (B.Türü 8 İse)": "Banka Aktarım", "Ödeme Şekli": ""})
                            if rows:
                                toplam_satir += len(rows)
                                df_out = pd.DataFrame(rows)
                                dosya_kok = f"{ay:02d}_{ay_ad.get(ay,'')}_Aktarim"
                                if export_format.startswith("Excel"):
                                    eb = BytesIO(); df_out.to_excel(eb, index=False)
                                    zf.writestr(f"{dosya_kok}.xlsx", eb.getvalue())
                                elif export_format.startswith("CSV"):
                                    # Türkçe/Zirve uyumu: ; ayraç, UTF-8 BOM, virgül ondalık
                                    csv_str = df_out.to_csv(index=False, sep=';', decimal=',')
                                    zf.writestr(f"{dosya_kok}.csv", ("\ufeff" + csv_str).encode("utf-8"))
                                else:  # Zirve TXT — sekme ayraçlı, başlıksız (klasik içe aktarım formatı)
                                    txt_str = df_out.to_csv(index=False, header=False, sep='\t', decimal=',')
                                    zf.writestr(f"{dosya_kok}.txt", txt_str.encode("utf-8"))
                    buf.seek(0)

                    # Benzersizlik doğrulaması (aynı fiş no birden fazla anahtara denk gelmesin)
                    if len(uretilen_fno) == sum(sayac.values()):
                        st.success(f"✅ {len(aylar_to_export)} ay oluşturuldu • {toplam_satir} kayıt • {len(uretilen_fno)} benzersiz fiş no.")
                    else:
                        st.error("⚠️ Fiş no çakışması tespit edildi! Öneki değiştirip tekrar deneyin.")
                    add_log("Zirve Aktarımı", f"{len(aylar_to_export)} ay, {toplam_satir} kayıt, format={export_format}", "SUCCESS")

                    ext_map = {"Excel (.xlsx)": "xlsx", "CSV (.csv)": "csv", "Zirve TXT (.txt)": "txt"}
                    st.download_button("📥 ZIP İndir", data=buf.getvalue(), file_name=f"Zirve_{ext_map[export_format]}_{datetime.now().strftime('%Y%m%d')}.zip", mime="application/zip", type="primary", width="stretch")
    else:
        st.info("Veri yükleyin.")

elif menu == "🗂️ Resmi Hesap Listesi":
    st.markdown('<div class="main-header"><h1>🗂️ Hesap Planı</h1></div>', unsafe_allow_html=True)
    hp_file = st.file_uploader("Hesap Planı Yükle", type=['xlsx','xls','csv'])
    if hp_file:
        try:
            fb = hp_file.read()
            df_hp = pd.read_excel(BytesIO(fb), usecols=[0,1,2], dtype=str) if hp_file.name.endswith(('.xlsx','.xls')) else pd.read_csv(BytesIO(fb), usecols=[0,1,2], dtype=str)
            df_hp.columns = ['Hesap Kodu','Hesap Adı','Detay E/H']
            df_hp = df_hp.dropna(subset=['Hesap Kodu'])
            st.session_state.hesap_plani = df_hp
            cid = st.session_state.current_company_id
            if db.online:
                hp_list = [{"hesap_kodu": str(r.get("Hesap Kodu","")), "hesap_adi": str(r.get("Hesap Adı","")), "detay_eh": str(r.get("Detay E/H","Evet"))} for _, r in df_hp.iterrows()]
                db.save_hesap_plani(hp_list, cid)
            st.session_state.pop('hp_cache_key', None)
            add_log("Hesap Planı Yüklendi", f"{len(df_hp)} kayıt", "SUCCESS")
            st.toast(f"✅ {len(df_hp)} hesap yüklendi!", icon="🗂️")
            st.rerun()
        except Exception as e: st.error(f"Hata: {e}")
    if not st.session_state.hesap_plani.empty:
        st.caption(f"📋 Toplam: **{len(st.session_state.hesap_plani)}** kayıt")
        st.dataframe(st.session_state.hesap_plani, height=500, width="stretch")

elif menu == "📜 Sistem Logları":
    st.markdown('<div class="main-header"><h1>📜 Sistem Logları</h1></div>', unsafe_allow_html=True)
    if st.session_state.logs: st.dataframe(pd.DataFrame(st.session_state.logs), height=550, width="stretch")
    else: st.info("Henüz log yok.")

elif menu == "👥 Yönetim":
    if not is_admin(): st.error("⛔ Yetkiniz yok."); st.stop()
    st.markdown('<div class="main-header"><h1>👥 Yönetim Paneli</h1></div>', unsafe_allow_html=True)
    all_comp = db.get_companies() if db.online else []
    tab_u, tab_au, tab_c = st.tabs(["📋 Kullanıcılar", "➕ Kullanıcı Ekle", "🏭 Firmalar"])
    with tab_u:
        for u in (db.get_all_users() if db.online else []):
            with st.expander(f"{'🟢' if u.get('is_active') else '🔴'} {u['username']} - {u.get('full_name','')} ({u.get('role','user')})"):
                c1, c2, c3 = st.columns(3)
                nn = c1.text_input("Ad", value=u.get('full_name',''), key=f"u{u['id']}n")
                nr = c2.selectbox("Rol", ["admin","user","viewer"], index=["admin","user","viewer"].index(u.get('role','user')), key=f"u{u['id']}r")
                na = c3.checkbox("Aktif", value=u.get('is_active',True), key=f"u{u['id']}a")
                np_ = st.text_input("Yeni Şifre (boş=değiştirme)", type="password", key=f"u{u['id']}p")
                sc = []
                if all_comp and u.get('role') != 'admin':
                    st.markdown("##### 🏭 Firma Yetkisi")
                    cur_ids = db.get_user_companies(u['id'])
                    opts = [f"{c['name']} ({c['code']})" for c in all_comp]
                    defs = [opts[i] for i, c in enumerate(all_comp) if c['id'] in cur_ids]
                    sc = st.multiselect("Firma (boş=tümü)", opts, default=defs, key=f"u{u['id']}c")
                bc1, bc2 = st.columns(2)
                with bc1:
                    if st.button("💾 Güncelle", key=f"u{u['id']}s"):
                        upd = {"full_name": nn, "role": nr, "is_active": na}
                        if np_: upd["password_hash"] = hash_password(np_)
                        db.update_user(u['id'], upd)
                        if all_comp and u.get('role') != 'admin':
                            db.set_user_companies(u['id'], [c['id'] for c in all_comp if f"{c['name']} ({c['code']})" in sc])
                        st.toast(f"✅ {u['username']} güncellendi!"); st.rerun()
                with bc2:
                    if u['username'] != 'admin' and st.button("🗑️ Sil", key=f"u{u['id']}d"):
                        db.delete_user(u['id']); st.rerun()
    with tab_au:
        with st.form("add_user", clear_on_submit=True):
            c1, c2 = st.columns(2); nu = c1.text_input("Kullanıcı Adı*"); nf = c2.text_input("Tam Ad")
            c3, c4 = st.columns(2); npw = c3.text_input("Şifre*", type="password"); nrl = c4.selectbox("Rol", ["user","admin","viewer"])
            snc = []
            if all_comp and nrl != 'admin':
                opts = [f"{c['name']} ({c['code']})" for c in all_comp]
                snc = st.multiselect("Firma Yetkisi (boş=tümü)", opts)
            if st.form_submit_button("➕ Ekle", type="primary", width="stretch"):
                if nu and npw:
                    if db.get_user(nu): st.error("Mevcut!")
                    else:
                        db.create_user(nu, hash_password(npw), nf, nrl)
                        if all_comp and nrl != 'admin' and snc:
                            new_u = db.get_user(nu)
                            if new_u: db.set_user_companies(new_u['id'], [c['id'] for c in all_comp if f"{c['name']} ({c['code']})" in snc])
                        st.toast(f"✅ '{nu}' eklendi!", icon="👤"); st.rerun()
    with tab_c:
        with st.form("add_comp", clear_on_submit=True):
            fc1, fc2, fc3 = st.columns(3)
            cn = fc1.text_input("Firma Adı*"); cc = fc2.text_input("Kod*"); ct = fc3.text_input("Vergi No")
            if st.form_submit_button("➕ Firma Ekle", type="primary", width="stretch"):
                if cn and cc:
                    if db.create_company(cn, cc, ct): st.toast(f"✅ '{cn}' eklendi!", icon="🏭"); st.rerun()
                    else: st.error("Kod benzersiz olmalı!")
        st.markdown("---")
        for comp in all_comp:
            with st.expander(f"🏭 {comp['name']} ({comp['code']})"):
                ec1, ec2, ec3 = st.columns(3)
                en = ec1.text_input("Ad", value=comp['name'], key=f"c{comp['id']}n")
                ec = ec2.text_input("Kod", value=comp['code'], key=f"c{comp['id']}c")
                et = ec3.text_input("Vergi", value=comp.get('tax_number',''), key=f"c{comp['id']}t")
                ea = st.checkbox("Aktif", value=comp.get('is_active',True), key=f"c{comp['id']}a")
                bc1, bc2 = st.columns(2)
                with bc1:
                    if st.button("💾 Güncelle", key=f"c{comp['id']}s"):
                        db.update_company(comp['id'], {"name":en,"code":ec,"tax_number":et,"is_active":ea}); st.rerun()
                with bc2:
                    if st.button("🗑️ Sil", key=f"c{comp['id']}d"):
                        db.delete_company(comp['id']); st.rerun()
