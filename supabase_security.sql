-- ============================================================================
-- FINANSAL OTOMASYON v7.0 - GÜVENLİK / RLS SERTLEŞTİRME
-- ============================================================================
-- Bu dosyayı Supabase > SQL Editor'de çalıştırın.
--
-- MANTIK:
-- Uygulama Supabase'e tek bir servis anahtarıyla bağlanır ve yetki kontrolünü
-- (admin/user/viewer) uygulama katmanında yapar. Bu nedenle en güvenli yapı:
--   * RLS her tabloda AÇIK kalır
--   * Eski "herkese izin ver (USING true)" politikaları KALDIRILIR
--   * Sadece service_role (backend anahtarı) erişebilir
--   * anon / authenticated (public) roller tamamen BLOKLANIR
--
-- ⚠️ ÖNEMLİ: Uygulamanız .streamlit/secrets.toml içinde SUPABASE_KEY olarak
-- **service_role** anahtarını kullanmalıdır (anon key DEĞİL). Aksi halde
-- uygulama veriye erişemez. service_role anahtarını ASLA tarayıcıya/istemciye
-- göndermeyin; yalnızca sunucu tarafında (Streamlit backend) tutun.
-- ============================================================================

-- 1) RLS'i tüm tablolarda etkinleştir (zaten açıksa sorun olmaz)
ALTER TABLE companies       ENABLE ROW LEVEL SECURITY;
ALTER TABLE users           ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_companies  ENABLE ROW LEVEL SECURITY;
ALTER TABLE rules           ENABLE ROW LEVEL SECURITY;
ALTER TABLE bank_accounts   ENABLE ROW LEVEL SECURITY;
ALTER TABLE hesap_plani     ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_logs      ENABLE ROW LEVEL SECURITY;
ALTER TABLE app_data        ENABLE ROW LEVEL SECURITY;

-- 2) Eski "allow_all" (herkese açık) politikalarını kaldır
DROP POLICY IF EXISTS "allow_all_companies" ON companies;
DROP POLICY IF EXISTS "allow_all_users"     ON users;
DROP POLICY IF EXISTS "allow_all_usercomp"  ON user_companies;
DROP POLICY IF EXISTS "allow_all_rules"     ON rules;
DROP POLICY IF EXISTS "allow_all_bank"      ON bank_accounts;
DROP POLICY IF EXISTS "allow_all_hesap"     ON hesap_plani;
DROP POLICY IF EXISTS "allow_all_logs"      ON audit_logs;
DROP POLICY IF EXISTS "allow_all_appdata"   ON app_data;

-- 3) Sadece service_role erişebilsin (backend anahtarı). Public roller bloklu.
--    service_role RLS'i zaten bypass eder; yine de açık politika ile netleştiriyoruz.
DO $$
DECLARE
    t text;
    tbls text[] := ARRAY['companies','users','user_companies','rules',
                         'bank_accounts','hesap_plani','audit_logs','app_data'];
BEGIN
    FOREACH t IN ARRAY tbls LOOP
        EXECUTE format(
            'CREATE POLICY "service_role_only" ON %I FOR ALL TO service_role USING (true) WITH CHECK (true);',
            t
        );
    END LOOP;
END $$;

-- 4) anon ve authenticated (public/tarayıcı) rollerinden tüm izinleri geri al
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM anon, authenticated;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM anon, authenticated;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM anon, authenticated;

-- 5) İleride oluşturulacak nesneler için de varsayılan izinleri kıs
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM anon, authenticated;

-- ============================================================================
-- DOĞRULAMA: Aşağıdaki sorgu her tablo için yalnızca 'service_role_only'
-- politikasını göstermeli (allow_all_* kalmamalı):
--   SELECT tablename, policyname, roles FROM pg_policies WHERE schemaname='public';
-- ============================================================================
