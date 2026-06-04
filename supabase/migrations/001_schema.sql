-- =========================================================
-- MarketLens schema migration 001
-- Run via scripts/setup_db.py or Supabase SQL editor
-- =========================================================

-- ─── profiles ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.profiles (
  id         uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  name       text,
  email      text,
  phone      text,
  country    text,
  is_admin   boolean NOT NULL DEFAULT false,
  is_active  boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  last_seen  timestamptz
);

-- ─── analyses ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.analyses (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id    uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  asset_type text NOT NULL,
  asset      text NOT NULL,
  score      integer,
  bias       text,
  last_price text,
  data       jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

-- ─── indexes ─────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_analyses_user_id    ON public.analyses(user_id);
CREATE INDEX IF NOT EXISTS idx_analyses_created_at ON public.analyses(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_analyses_asset_type ON public.analyses(asset_type);

-- ─── row-level security ──────────────────────────────────
ALTER TABLE public.profiles  ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.analyses  ENABLE ROW LEVEL SECURITY;

-- Drop existing policies before recreating
DROP POLICY IF EXISTS "profiles_own"       ON public.profiles;
DROP POLICY IF EXISTS "profiles_admin_all" ON public.profiles;
DROP POLICY IF EXISTS "analyses_own"       ON public.analyses;
DROP POLICY IF EXISTS "analyses_admin_all" ON public.analyses;

-- profiles: user sees own row; admin sees all
CREATE POLICY "profiles_own" ON public.profiles
  FOR ALL
  USING (auth.uid() = id);

CREATE POLICY "profiles_admin_all" ON public.profiles
  FOR ALL
  USING (
    EXISTS (
      SELECT 1 FROM public.profiles p
      WHERE p.id = auth.uid() AND p.is_admin = true
    )
  );

-- analyses: user sees own rows; admin sees all
CREATE POLICY "analyses_own" ON public.analyses
  FOR ALL
  USING (auth.uid() = user_id);

CREATE POLICY "analyses_admin_all" ON public.analyses
  FOR ALL
  USING (
    EXISTS (
      SELECT 1 FROM public.profiles p
      WHERE p.id = auth.uid() AND p.is_admin = true
    )
  );

-- ─── trigger: enforce 15-analysis limit per user ─────────
CREATE OR REPLACE FUNCTION public.enforce_analysis_limit()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER AS $$
BEGIN
  DELETE FROM public.analyses
  WHERE id IN (
    SELECT id FROM public.analyses
    WHERE user_id = NEW.user_id
    ORDER BY created_at DESC
    OFFSET 15
  );
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_enforce_analysis_limit ON public.analyses;
CREATE TRIGGER trg_enforce_analysis_limit
  AFTER INSERT ON public.analyses
  FOR EACH ROW EXECUTE FUNCTION public.enforce_analysis_limit();

-- ─── trigger: auto-create profile on new user ────────────
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER AS $$
BEGIN
  INSERT INTO public.profiles (id, name, email)
  VALUES (
    NEW.id,
    COALESCE(
      NEW.raw_user_meta_data->>'name',
      split_part(NEW.email, '@', 1)
    ),
    NEW.email
  )
  ON CONFLICT (id) DO NOTHING;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_handle_new_user ON auth.users;
CREATE TRIGGER trg_handle_new_user
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();
