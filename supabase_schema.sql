-- ============================================================
-- FİNANSAL OTOMASYON SİSTEMİ v6.0
-- SUPABASE VERİTABANI ŞEMASI (TEMİZ KURULUM)
-- ============================================================
-- Kurulum: Supabase → SQL Editor → New Query → Yapıştır → Run
-- Sonra uygulamayı başlatın → admin/admin123 ile giriş yapın
-- ============================================================

-- 1. FİRMALAR
CREATE TABLE IF NOT EXISTS companies (
    id SERIAL PRIMARY KEY, name VARCHAR(200) NOT NULL, code VARCHAR(20) UNIQUE NOT NULL,
    tax_number VARCHAR(50) DEFAULT '', is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 2. KULLANICILAR
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY, username VARCHAR(50) UNIQUE NOT NULL, password_hash TEXT NOT NULL,
    full_name VARCHAR(100) DEFAULT '', role VARCHAR(20) DEFAULT 'user' CHECK (role IN ('admin', 'user', 'viewer')),
    is_active BOOLEAN DEFAULT true, created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(), last_login TIMESTAMP WITH TIME ZONE
);

-- 3. KULLANICI-FİRMA YETKİ
CREATE TABLE IF NOT EXISTS user_companies (
    id SERIAL PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE, UNIQUE(user_id, company_id)
);

-- 4. KURALLAR (Firma bazlı)
CREATE TABLE IF NOT EXISTS rules (
    id SERIAL PRIMARY KEY, company_id INTEGER NOT NULL DEFAULT 1 REFERENCES companies(id),
    name VARCHAR(200) NOT NULL, priority INTEGER DEFAULT 100, criteria JSONB DEFAULT '{}',
    target_account_code VARCHAR(50) NOT NULL, target_account_name VARCHAR(200) DEFAULT '',
    min_amount NUMERIC(15,2), max_amount NUMERIC(15,2), note TEXT DEFAULT '',
    is_active BOOLEAN DEFAULT true, created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(), created_by VARCHAR(50) DEFAULT 'system'
);

-- 5. BANKA HESAPLARI (Firma bazlı)
CREATE TABLE IF NOT EXISTS bank_accounts (
    id SERIAL PRIMARY KEY, company_id INTEGER NOT NULL DEFAULT 1 REFERENCES companies(id),
    bank_name VARCHAR(200) NOT NULL, account_code VARCHAR(50) NOT NULL, account_name VARCHAR(200) DEFAULT '',
    iban VARCHAR(50) DEFAULT '', currency VARCHAR(5) DEFAULT 'TL', created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 6. HESAP PLANI (Firma bazlı)
CREATE TABLE IF NOT EXISTS hesap_plani (
    id SERIAL PRIMARY KEY, company_id INTEGER NOT NULL DEFAULT 1 REFERENCES companies(id),
    hesap_kodu VARCHAR(50) NOT NULL, hesap_adi VARCHAR(300) DEFAULT '', detay_eh VARCHAR(20) DEFAULT 'Evet',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 7. DENETİM LOGLARI
CREATE TABLE IF NOT EXISTS audit_logs (
    id SERIAL PRIMARY KEY, username VARCHAR(50) NOT NULL, action VARCHAR(100) NOT NULL,
    detail TEXT DEFAULT '', level VARCHAR(20) DEFAULT 'INFO' CHECK (level IN ('INFO', 'WARNING', 'ERROR', 'SUCCESS')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 8. UYGULAMA VERİ DEPOSU (Fiş listesi - Firma bazlı)
CREATE TABLE IF NOT EXISTS app_data (
    key VARCHAR(100) NOT NULL, company_id INTEGER NOT NULL DEFAULT 1 REFERENCES companies(id),
    value JSONB NOT NULL, updated_by VARCHAR(50) DEFAULT 'system', updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    PRIMARY KEY (key, company_id)
);

-- İNDEKSLER
CREATE INDEX IF NOT EXISTS idx_rules_company ON rules(company_id);
CREATE INDEX IF NOT EXISTS idx_rules_priority ON rules(priority);
CREATE INDEX IF NOT EXISTS idx_bank_company ON bank_accounts(company_id);
CREATE INDEX IF NOT EXISTS idx_hesap_company ON hesap_plani(company_id);
CREATE INDEX IF NOT EXISTS idx_hesap_kodu ON hesap_plani(hesap_kodu);
CREATE INDEX IF NOT EXISTS idx_appdata_company ON app_data(company_id);
CREATE INDEX IF NOT EXISTS idx_usercomp_user ON user_companies(user_id);
CREATE INDEX IF NOT EXISTS idx_logs_date ON audit_logs(created_at DESC);

-- ROW LEVEL SECURITY
ALTER TABLE companies ENABLE ROW LEVEL SECURITY;
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_companies ENABLE ROW LEVEL SECURITY;
ALTER TABLE rules ENABLE ROW LEVEL SECURITY;
ALTER TABLE bank_accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE hesap_plani ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE app_data ENABLE ROW LEVEL SECURITY;

-- GÜVENLİK: Yalnızca service_role (backend anahtarı) erişebilir.
-- Public roller (anon/authenticated) bloklu. Ayrıntı ve sertleştirme: supabase_security.sql
CREATE POLICY "service_role_only" ON companies      FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_only" ON users          FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_only" ON user_companies FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_only" ON rules          FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_only" ON bank_accounts  FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_only" ON hesap_plani    FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_only" ON audit_logs     FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_only" ON app_data       FOR ALL TO service_role USING (true) WITH CHECK (true);

REVOKE ALL ON ALL TABLES IN SCHEMA public FROM anon, authenticated;

-- VARSAYILAN FİRMALAR
INSERT INTO companies (name, code, tax_number) VALUES
    ('A Firması', 'A', ''), ('B Firması', 'B', ''), ('C Firması', 'C', ''), ('D Firması', 'D', '')
ON CONFLICT (code) DO NOTHING;

-- TAMAMLANDI! Admin otomatik oluşur: admin / admin123
