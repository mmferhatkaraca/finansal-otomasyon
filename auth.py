# -*- coding: utf-8 -*-
"""Kimlik Doğrulama ve Oturum Yönetimi Modülü v6.0"""

import hashlib
import secrets
import streamlit as st
from db import Database

def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    hashed = hashlib.sha256(f"{salt}{password}".encode()).hexdigest()
    return f"{salt}:{hashed}"

def verify_password(password: str, stored_hash: str) -> bool:
    try:
        salt, stored_hex = stored_hash.split(":")
        computed = hashlib.sha256(f"{salt}{password}".encode()).hexdigest()
        return computed == stored_hex
    except (ValueError, AttributeError):
        return False

def login(username: str, password: str) -> dict:
    db = Database()
    if not db.online:
        if username == "admin" and password == "admin123":
            return {"id": 0, "username": "admin", "full_name": "Yönetici (Offline)", "role": "admin", "is_active": True}
        return None
    user = db.get_user(username)
    if user is None or not user.get("is_active", False):
        return None
    if not verify_password(password, user.get("password_hash", "")):
        return None
    db.add_log(username, "Giriş Yapıldı", f"{username} sisteme giriş yaptı", "SUCCESS")
    return user

def logout():
    if "user" in st.session_state:
        username = st.session_state.user.get("username", "bilinmiyor")
        db = Database()
        db.add_log(username, "Çıkış Yapıldı", f"{username} çıkış yaptı", "INFO")
    for key in list(st.session_state.keys()):
        if key not in ['rules', 'bank_accounts', 'hesap_plani']:
            del st.session_state[key]
    st.session_state.user = None
    st.session_state.logged_in = False

def is_logged_in() -> bool:
    return st.session_state.get("logged_in", False)

def get_current_user() -> dict:
    return st.session_state.get("user", {})

def is_admin() -> bool:
    return get_current_user().get("role", "") == "admin"

def init_default_admin():
    db = Database()
    if not db.online:
        return
    admin = db.get_user("admin")
    if admin is None:
        password_hash = hash_password("admin123")
        db.create_user("admin", password_hash, "Sistem Yöneticisi", "admin")
        db.add_log("system", "Admin Oluşturuldu", "Varsayılan admin (admin/admin123)", "SUCCESS")
    else:
        stored_hash = admin.get("password_hash", "")
        if not verify_password("admin123", stored_hash):
            new_hash = hash_password("admin123")
            db.update_user(admin["id"], {"password_hash": new_hash})

def render_login_page():
    st.set_page_config(page_title="Finansal Otomasyon - Giriş", page_icon="🔐", layout="centered")
    st.markdown("""<style>
    .login-header { background: linear-gradient(135deg, #0F172A, #1E293B, #334155); color: white; padding: 2rem; border-radius: 16px; text-align: center; margin-bottom: 2rem; }
    .login-header h1 { margin: 0; font-size: 1.5rem; } .login-header p { margin: 0.5rem 0 0 0; color: #94A3B8; }
    @media screen and (max-width: 768px) { .login-header { padding: 1.5rem; } .login-header h1 { font-size: 1.2rem; } }
    </style>""", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown('<div class="login-header"><h1>🏢 Finansal Otomasyon Sistemi</h1><p>Kurumsal Muhasebe Eşleştirme v6.0</p></div>', unsafe_allow_html=True)
        with st.form("login_form"):
            username = st.text_input("👤 Kullanıcı Adı")
            password = st.text_input("🔒 Şifre", type="password")
            st.write("")
            if st.form_submit_button("🔐 Giriş Yap", type="primary", width="stretch"):
                if not username or not password:
                    st.error("⚠️ Kullanıcı adı ve şifre zorunludur.")
                else:
                    with st.spinner("Giriş yapılıyor..."):
                        user = login(username.strip(), password)
                        if user:
                            st.session_state.user = user
                            st.session_state.logged_in = True
                            st.toast(f"✅ Hoş geldiniz, {user.get('full_name', username)}!", icon="🎉")
                            st.rerun()
                        else:
                            st.error("❌ Geçersiz kullanıcı adı veya şifre.")
        st.caption("💡 Varsayılan: `admin` / `admin123`")
        db = Database()
        st.caption("🟢 Supabase bağlı" if db.online else "🔴 Offline (admin/admin123)")
