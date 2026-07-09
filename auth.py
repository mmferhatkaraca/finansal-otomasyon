# -*- coding: utf-8 -*-
"""Kimlik Doğrulama ve Oturum Yönetimi Modülü v7.0 - GÜVENLİK SERTLEŞTİRİLMİŞ

- bcrypt ile güçlü şifre hashleme (eski SHA-256 hash'lere geriye uyumlu, girişte otomatik yükseltme)
- Brute-force koruması (art arda hatalı denemede geçici kilit)
- Güçlü şifre politikası
- Offline backdoor KALDIRILDI (Supabase yoksa giriş yok)
- init_default_admin artık mevcut admin şifresini SIFIRLAMAZ
"""

import hashlib
import secrets
import time
import streamlit as st
from db import Database

try:
    import bcrypt
    HAS_BCRYPT = True
except ImportError:
    HAS_BCRYPT = False

# --- Brute-force ayarları ---
MAX_ATTEMPTS = 5          # bu kadar hatalı denemeden sonra kilit
LOCK_SECONDS = 300        # 5 dakika kilit
MIN_PASSWORD_LEN = 8      # güçlü şifre minimum uzunluk


# ==========================================================================
# ŞİFRELEME (bcrypt + eski hash'lere geriye uyumluluk)
# ==========================================================================
def hash_password(password: str) -> str:
    """Şifreyi bcrypt ile hash'ler. bcrypt yoksa güvenli fallback (PBKDF2)."""
    if HAS_BCRYPT:
        return "bcrypt$" + bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")
    # Fallback: PBKDF2-HMAC-SHA256 (SHA-256 tek turdan çok daha güçlü)
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 200_000).hex()
    return f"pbkdf2${salt}${dk}"


def _verify_legacy_sha256(password: str, stored_hash: str) -> bool:
    """Eski 'salt:hash' formatındaki SHA-256 hash'leri doğrular (geriye uyumluluk)."""
    try:
        salt, stored_hex = stored_hash.split(":")
        computed = hashlib.sha256(f"{salt}{password}".encode()).hexdigest()
        return secrets.compare_digest(computed, stored_hex)
    except (ValueError, AttributeError):
        return False


def verify_password(password: str, stored_hash: str) -> bool:
    """Şifreyi doğrular. bcrypt, pbkdf2 ve eski sha256 formatlarını destekler."""
    if not stored_hash:
        return False
    try:
        if stored_hash.startswith("bcrypt$"):
            if not HAS_BCRYPT:
                return False
            return bcrypt.checkpw(password.encode("utf-8"), stored_hash[len("bcrypt$"):].encode("utf-8"))
        if stored_hash.startswith("pbkdf2$"):
            _, salt, dk = stored_hash.split("$", 2)
            computed = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 200_000).hex()
            return secrets.compare_digest(computed, dk)
        # Eski format: "salt:hash" (SHA-256)
        return _verify_legacy_sha256(password, stored_hash)
    except Exception:
        return False


def needs_rehash(stored_hash: str) -> bool:
    """Hash eski/zayıf formatta mı? (bcrypt'e yükseltilmeli mi?)"""
    return not (stored_hash or "").startswith("bcrypt$")


def validate_password_strength(password: str) -> tuple:
    """Güçlü şifre kontrolü. (geçerli_mi, mesaj) döner."""
    if len(password) < MIN_PASSWORD_LEN:
        return False, f"Şifre en az {MIN_PASSWORD_LEN} karakter olmalı."
    if not any(c.isdigit() for c in password):
        return False, "Şifre en az bir rakam içermeli."
    if not any(c.isalpha() for c in password):
        return False, "Şifre en az bir harf içermeli."
    return True, ""


# ==========================================================================
# BRUTE-FORCE KORUMASI (session bazlı)
# ==========================================================================
def _get_attempts():
    return st.session_state.get("_login_attempts", 0), st.session_state.get("_lock_until", 0)


def _is_locked() -> tuple:
    attempts, lock_until = _get_attempts()
    now = time.time()
    if lock_until > now:
        return True, int(lock_until - now)
    return False, 0


def _register_failed_attempt():
    attempts = st.session_state.get("_login_attempts", 0) + 1
    st.session_state._login_attempts = attempts
    if attempts >= MAX_ATTEMPTS:
        st.session_state._lock_until = time.time() + LOCK_SECONDS
        st.session_state._login_attempts = 0  # sayacı sıfırla, kilit devrede


def _reset_attempts():
    st.session_state._login_attempts = 0
    st.session_state._lock_until = 0


# ==========================================================================
# GİRİŞ / ÇIKIŞ
# ==========================================================================
def login(username: str, password: str) -> dict:
    db = Database()
    # Offline backdoor KALDIRILDI: Supabase yoksa giriş yapılamaz.
    if not db.online:
        return None
    user = db.get_user(username)
    if user is None or not user.get("is_active", False):
        return None
    stored = user.get("password_hash", "")
    if not verify_password(password, stored):
        return None
    # Başarılı giriş: eski/zayıf hash ise bcrypt'e otomatik yükselt
    try:
        if needs_rehash(stored):
            db.update_user(user["id"], {"password_hash": hash_password(password)})
    except Exception:
        pass
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


def get_role() -> str:
    """Aktif kullanıcının rolü: 'admin', 'user' veya 'viewer'."""
    return get_current_user().get("role", "viewer")


def can_edit() -> bool:
    """Ekleme/silme/değiştirme yetkisi (admin + user). Viewer False döner."""
    return get_role() in ("admin", "user")


def is_viewer() -> bool:
    return get_role() == "viewer"


def init_default_admin():
    """Admin hesabı YOKSA oluşturur. Mevcut admin'in şifresini ASLA sıfırlamaz."""
    db = Database()
    if not db.online:
        return
    admin = db.get_user("admin")
    if admin is None:
        # İlk kurulum: geçici şifre. İlk girişte değiştirilmesi zorunlu tutulmalı.
        password_hash = hash_password("admin123")
        db.create_user("admin", password_hash, "Sistem Yöneticisi", "admin")
        db.add_log("system", "Admin Oluşturuldu", "Varsayılan admin (admin/admin123) - İLK GİRİŞTE ŞİFRE DEĞİŞTİRİN!", "WARNING")
    # NOT: else bloğu kaldırıldı — mevcut admin şifresi artık sıfırlanmıyor.


# ==========================================================================
# GİRİŞ SAYFASI
# ==========================================================================
def render_login_page():
    st.set_page_config(page_title="Finansal Otomasyon - Giriş", page_icon="🔐", layout="centered")
    st.markdown("""<style>
    .login-header { background: linear-gradient(135deg, #0F172A, #1E293B, #334155); color: white; padding: 2rem; border-radius: 16px; text-align: center; margin-bottom: 2rem; }
    .login-header h1 { margin: 0; font-size: 1.5rem; } .login-header p { margin: 0.5rem 0 0 0; color: #94A3B8; }
    @media screen and (max-width: 768px) { .login-header { padding: 1.5rem; } .login-header h1 { font-size: 1.2rem; } }
    </style>""", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown('<div class="login-header"><h1>🏢 Finansal Otomasyon Sistemi</h1><p>Kurumsal Muhasebe Eşleştirme v7.0</p></div>', unsafe_allow_html=True)

        db = Database()
        if not db.online:
            st.error("🔴 Veritabanı bağlantısı yok. Güvenlik nedeniyle giriş devre dışı. Lütfen yöneticiye başvurun.")
            return

        # Kilit kontrolü
        locked, remaining = _is_locked()
        if locked:
            dk = remaining // 60 + 1
            st.error(f"🔒 Çok fazla hatalı deneme. Güvenlik için hesap geçici olarak kilitlendi. ~{dk} dakika sonra tekrar deneyin.")
            return

        with st.form("login_form"):
            username = st.text_input("👤 Kullanıcı Adı")
            password = st.text_input("🔒 Şifre", type="password")
            st.write("")
            submitted = st.form_submit_button("🔐 Giriş Yap", type="primary", width="stretch")
            if submitted:
                if not username or not password:
                    st.error("⚠️ Kullanıcı adı ve şifre zorunludur.")
                else:
                    with st.spinner("Giriş yapılıyor..."):
                        user = login(username.strip(), password)
                    if user:
                        _reset_attempts()
                        st.session_state.user = user
                        st.session_state.logged_in = True
                        st.toast(f"✅ Hoş geldiniz, {user.get('full_name', username)}!", icon="🎉")
                        st.rerun()
                    else:
                        _register_failed_attempt()
                        attempts, _ = _get_attempts()
                        kalan = MAX_ATTEMPTS - attempts
                        # Başarısız giriş denemesini logla (güvenlik izi)
                        try:
                            db.add_log(username.strip()[:50], "Başarısız Giriş", "Hatalı kullanıcı adı/şifre denemesi", "WARNING")
                        except Exception:
                            pass
                        if kalan > 0:
                            st.error(f"❌ Geçersiz kullanıcı adı veya şifre. ({kalan} deneme hakkı kaldı)")
                        else:
                            st.error("🔒 Çok fazla hatalı deneme. Hesap geçici olarak kilitlendi.")
        st.caption("🟢 Supabase bağlı")
