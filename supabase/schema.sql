-- ==============================================================================
-- TechnoFunda Swing Bot - Supabase Database Schema
-- Run this script in your Supabase project's SQL Editor (Dashboard > SQL Editor)
-- ==============================================================================

-- 1. Create table for system status and pipeline execution logs
CREATE TABLE IF NOT EXISTS public.system_status (
    id TEXT PRIMARY KEY DEFAULT 'current',
    status TEXT NOT NULL DEFAULT 'idle',
    last_run TEXT,
    portfolio_capital NUMERIC DEFAULT 10000.0,
    deployment_per_trade NUMERIC DEFAULT 5000.0,
    price_ceiling NUMERIC DEFAULT 600.0,
    fundamental_watchlist_count INTEGER DEFAULT 0,
    final_trade_triggers_count INTEGER DEFAULT 0,
    logs JSONB DEFAULT '[]'::jsonb,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- 2. Create table for fundamental watchlist
CREATE TABLE IF NOT EXISTS public.watchlist (
    symbol TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    price NUMERIC,
    market_cap NUMERIC,
    roce NUMERIC,
    pe NUMERIC,
    data_source TEXT DEFAULT 'Screener.in',
    volume_spike_multiplier NUMERIC,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- 3. Create table for final actionable swing trade triggers
CREATE TABLE IF NOT EXISTS public.triggers (
    symbol TEXT PRIMARY KEY,
    company_name TEXT NOT NULL,
    live_price NUMERIC NOT NULL,
    dma_vol BIGINT,
    latest_vol BIGINT,
    volume_spike_multiplier NUMERIC,
    support_zone NUMERIC,
    resistance_zone NUMERIC,
    recommended_entry NUMERIC,
    stop_loss NUMERIC,
    target_price NUMERIC,
    risk_reward_ratio TEXT DEFAULT '1:2.2',
    recommended_shares INTEGER,
    capital_deployed NUMERIC,
    max_risk NUMERIC,
    portfolio_risk_pct NUMERIC,
    under_600 TEXT DEFAULT 'YES',
    volume_breakout TEXT DEFAULT 'YES',
    action_badge TEXT DEFAULT 'Ready for EOD Trade',
    roce NUMERIC,
    pe NUMERIC,
    market_cap NUMERIC,
    is_ready BOOLEAN DEFAULT TRUE,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- 4. Create table for cached candlestick & volume chart data
CREATE TABLE IF NOT EXISTS public.stock_charts (
    symbol TEXT PRIMARY KEY,
    candles JSONB NOT NULL DEFAULT '[]'::jsonb,
    volumes JSONB NOT NULL DEFAULT '[]'::jsonb,
    dma_volumes JSONB NOT NULL DEFAULT '[]'::jsonb,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- 5. Enable Row Level Security (RLS) on all tables
ALTER TABLE public.system_status ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.watchlist ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.triggers ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.stock_charts ENABLE ROW LEVEL SECURITY;

-- 6. RLS Policies: Allow PUBLIC READ access (so Vercel frontend can display data)
DROP POLICY IF EXISTS "Allow public read access to system_status" ON public.system_status;
CREATE POLICY "Allow public read access to system_status"
    ON public.system_status FOR SELECT
    TO anon, authenticated
    USING (true);

DROP POLICY IF EXISTS "Allow public read access to watchlist" ON public.watchlist;
CREATE POLICY "Allow public read access to watchlist"
    ON public.watchlist FOR SELECT
    TO anon, authenticated
    USING (true);

DROP POLICY IF EXISTS "Allow public read access to triggers" ON public.triggers;
CREATE POLICY "Allow public read access to triggers"
    ON public.triggers FOR SELECT
    TO anon, authenticated
    USING (true);

DROP POLICY IF EXISTS "Allow public read access to stock_charts" ON public.stock_charts;
CREATE POLICY "Allow public read access to stock_charts"
    ON public.stock_charts FOR SELECT
    TO anon, authenticated
    USING (true);

-- 7. RLS Policies: Allow write/update/delete with service_role or authenticated key (backend & github actions)
DROP POLICY IF EXISTS "Allow full access with service_role to system_status" ON public.system_status;
CREATE POLICY "Allow full access with service_role to system_status"
    ON public.system_status FOR ALL
    TO service_role, authenticated
    USING (true)
    WITH CHECK (true);

DROP POLICY IF EXISTS "Allow full access with service_role to watchlist" ON public.watchlist;
CREATE POLICY "Allow full access with service_role to watchlist"
    ON public.watchlist FOR ALL
    TO service_role, authenticated
    USING (true)
    WITH CHECK (true);

DROP POLICY IF EXISTS "Allow full access with service_role to triggers" ON public.triggers;
CREATE POLICY "Allow full access with service_role to triggers"
    ON public.triggers FOR ALL
    TO service_role, authenticated
    USING (true)
    WITH CHECK (true);

DROP POLICY IF EXISTS "Allow full access with service_role to stock_charts" ON public.stock_charts;
CREATE POLICY "Allow full access with service_role to stock_charts"
    ON public.stock_charts FOR ALL
    TO service_role, authenticated
    USING (true)
    WITH CHECK (true);

-- 8. Seed initial default status row
INSERT INTO public.system_status (id, status, last_run, logs)
VALUES (
    'current',
    'idle',
    'System Initialized',
    '["System ready. Run pipeline to populate Supabase database."]'::jsonb
)
ON CONFLICT (id) DO NOTHING;
