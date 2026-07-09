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
- 🔐 **Güvenlik (v7.0)**: bcrypt şifreleme + brute-force kilidi + güçlü şifre politikası
  - 🔑 Şifreler **bcrypt** ile hash'lenir (eski SHA-256 hesaplar girişte otomatik yükseltilir)
  - 🚫 5 hatalı denemede **5 dakika hesap kilidi** (brute-force koruması)
  - 💪 Güçlü şifre zorunlu (min 8 karakter, harf + rakam)
  - 🛑 Offline backdoor kaldırıldı — DB yoksa giriş yok; admin şifresi artık sıfırlanmaz
  - 🌐 REST API (`api.py`) **X-API-Key** ile korumalı + kısıtlı CORS
  - 🗄️ Supabase **RLS** sertleştirme: `supabase_security.sql` (yalnızca service_role erişir)
- 🔐 Kullanıcı giriş sistemi + rol bazlı yetkilendirme (admin/user/viewer)
  - 👑 **Admin**: tam yetki + Sistem Logları + Yönetim paneli
  - 👤 **User**: fiş/kural/banka/hesap planı ekleme-silme + Zirve (Loglar/Yönetim yok)
  - 👁️ **Viewer**: sadece görüntüleme + indirme (XLSX/Zirve); ekleme/silme yok
  - 👤 **Profilim**: her kullanıcı kendi ad ve şifresini değiştirir (admin herkese müdahale eder)
- 🏭 Çok firma desteği (A, B, C, D firmaları)
- 📊 Detaylı filtreleme paneli
- ⚡ Hızlı kural ekleme (satıra tıklayarak)
- 📝 Kural düzenleme/silme/toplu işlemler
- 📈 Kural performans raporu + test modu + otomatik öneri
- 🧾 Zirve muhasebe fiş aktarımı (aylara bölünmüş, tarih sıralı)
  - ⚖️ Aktarım öncesi denge & veri kalitesi kontrolü (fiş dengesi, tarihsiz/sıfır/eksik satır uyarıları)
  - 📄 Çoklu çıktı formatı: Excel (.xlsx), CSV (.csv, ; ayraç + BOM), Zirve TXT (.txt, sekme ayraçlı)
  - 🔢 Benzersiz fiş numarası: ÖNEK + YIL + AY + sıra (farklı yılların aynı ayı artık çakışmaz)
- 🗂️ Firma bazlı hesap planı
- 💾 DB'de kalıcı veri (Excel yüklemeye gerek yok)
- 📱 Mobil uyumlu arayüz
- 👥 Firma bazlı yetkilendirme
