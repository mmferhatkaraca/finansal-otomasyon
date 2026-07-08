# 🏢 Finansal Otomasyon Sistemi v6.0

Çok firmalı, kullanıcı girişli, Supabase destekli kurumsal banka ekstre muhasebe eşleştirme platformu.

## 🚀 Kurulum

### 1. Supabase
1. [supabase.com](https://supabase.com) → Hesap aç → New Project
2. SQL Editor → `supabase_schema.sql` yapıştır → Run
3. Settings → API → URL ve Key kopyala

### 2. Secrets
`.streamlit/secrets.toml.example` dosyasını kopyalayıp `secrets.toml` olarak kaydet:
```toml
SUPABASE_URL = "https://XXXXXXX.supabase.co"
SUPABASE_KEY = "eyJhbGciOi..."
```

### 3. Çalıştır
```bash
# Windows: baslatici.bat'a çift tıkla
# Mac/Linux:
pip install -r requirements.txt
streamlit run app.py
```

### 4. Giriş
```
Kullanıcı: admin
Şifre:     admin123
```
⚠️ İlk girişten sonra şifreyi değiştirin!

## 📁 Dosya Yapısı
```
v6_final/
├── app.py                  # Ana uygulama (Login + 8 modül)
├── auth.py                 # Kimlik doğrulama
├── db.py                   # Supabase bağlantı (pagination + JSON temizlik)
├── engine_optimized.py     # Kural motoru
├── models.py               # Pydantic modelleri
├── requirements.txt        # Bağımlılıklar
├── supabase_schema.sql     # DB şeması
├── baslatici.bat           # Windows başlatıcı
├── start.sh                # Mac/Linux başlatıcı
├── Procfile                # Railway deploy
├── railway.toml            # Railway config
├── .gitignore
└── .streamlit/
    ├── config.toml
    └── secrets.toml.example
```

## 🎯 v6.0 Özellikleri
- 🔐 Kullanıcı giriş sistemi (admin/user/viewer)
- 🏭 Çok firma desteği (A, B, C, D firmaları)
- 📊 Detaylı filtreleme paneli
- ⚡ Hızlı kural ekleme (satıra tıklayarak)
- 📝 Kural düzenleme/silme/toplu işlemler
- 📈 Kural performans raporu + test modu + otomatik öneri
- 🧾 Zirve muhasebe fiş aktarımı (aylara bölünmüş, tarih sıralı)
- 🗂️ Firma bazlı hesap planı
- 💾 DB'de kalıcı veri (Excel yüklemeye gerek yok)
- 📱 Mobil uyumlu arayüz
- 👥 Firma bazlı yetkilendirme
