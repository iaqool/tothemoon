-- Полная схема базы данных для Tothemoon Lead Gen Pipeline

-- 1. Таблица проектов
CREATE TABLE IF NOT EXISTS public.projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    ticker TEXT,
    website TEXT,
    mcap NUMERIC DEFAULT 0,
    chain TEXT,
    source TEXT NOT NULL, -- CoinGecko, CMC, ICO Drops
    status TEXT DEFAULT 'not_contacted', -- not_contacted, contacted, replied, follow_up, no_response
    is_priority BOOLEAN DEFAULT false, -- True для Solana, TON, Base
    is_upcoming BOOLEAN DEFAULT false,
    launch_date TIMESTAMP WITH TIME ZONE,
    launchpad TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()),
    -- Уникальный индекс, чтобы не добавлять один и тот же проект с одним блокчейном дважды
    CONSTRAINT unique_project_chain UNIQUE (name, chain)
);

ALTER TABLE public.projects ADD COLUMN IF NOT EXISTS is_upcoming BOOLEAN DEFAULT false;
ALTER TABLE public.projects ADD COLUMN IF NOT EXISTS launch_date TIMESTAMP WITH TIME ZONE;
ALTER TABLE public.projects ADD COLUMN IF NOT EXISTS launchpad TEXT;

-- 2. Таблица контактов
CREATE TABLE IF NOT EXISTS public.contacts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES public.projects(id) ON DELETE CASCADE,
    platform TEXT NOT NULL, -- Telegram, X, Email, LinkedIn
    value TEXT NOT NULL, -- @username, email@domain.com
    role TEXT, -- Founder, BD, Admin и т.д.
    contact_name TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()),
    -- Нельзя добавить один и тот же контакт дважды
    CONSTRAINT unique_contact UNIQUE (project_id, platform, value)
);

ALTER TABLE public.contacts ADD COLUMN IF NOT EXISTS contact_name TEXT;
ALTER TABLE public.outreach_logs ADD COLUMN IF NOT EXISTS raw_payload JSONB;

-- 3. Таблица логов аутрича
CREATE TABLE IF NOT EXISTS public.outreach_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    contact_id UUID REFERENCES public.contacts(id) ON DELETE CASCADE,
    stage TEXT NOT NULL, -- Stage 1 (Cold), Follow-up 1, Follow-up 2, Stage 2 (Offer)
    message_sent TEXT,
    sent_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()),
    response TEXT,
    raw_payload JSONB
);

-- Функция для обновления updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Триггеры для автоматического обновления updated_at
CREATE TRIGGER update_projects_updated_at
    BEFORE UPDATE ON public.projects
    FOR EACH ROW
    EXECUTE PROCEDURE update_updated_at_column();

-- Индексы для быстрого поиска
CREATE INDEX IF NOT EXISTS idx_projects_status ON public.projects(status);
CREATE INDEX IF NOT EXISTS idx_projects_priority ON public.projects(is_priority);
CREATE INDEX IF NOT EXISTS idx_projects_upcoming ON public.projects(is_upcoming);
CREATE INDEX IF NOT EXISTS idx_projects_launch_date ON public.projects(launch_date);
CREATE INDEX IF NOT EXISTS idx_contacts_project_id ON public.contacts(project_id);
CREATE INDEX IF NOT EXISTS idx_outreach_logs_contact_id ON public.outreach_logs(contact_id);
CREATE INDEX IF NOT EXISTS idx_outreach_logs_sent_at ON public.outreach_logs(sent_at);
CREATE INDEX IF NOT EXISTS idx_outreach_logs_stage ON public.outreach_logs(stage);

-- Row Level Security (enable but allow anon access for dashboard)
ALTER TABLE public.projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.contacts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.outreach_logs ENABLE ROW LEVEL SECURITY;

CREATE POLICY "anon_read_projects" ON public.projects FOR SELECT USING (true);
CREATE POLICY "anon_insert_projects" ON public.projects FOR INSERT WITH CHECK (true);
CREATE POLICY "anon_update_projects" ON public.projects FOR UPDATE USING (true) WITH CHECK (true);

CREATE POLICY "anon_read_contacts" ON public.contacts FOR SELECT USING (true);
CREATE POLICY "anon_insert_contacts" ON public.contacts FOR INSERT WITH CHECK (true);

CREATE POLICY "anon_read_outreach_logs" ON public.outreach_logs FOR SELECT USING (true);
CREATE POLICY "anon_insert_outreach_logs" ON public.outreach_logs FOR INSERT WITH CHECK (true);

-- 4. Таблица сигналов из Telegram каналов
CREATE TABLE IF NOT EXISTS public.tg_signals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    channel_username TEXT NOT NULL,
    channel_title TEXT NOT NULL,
    message_id BIGINT NOT NULL,
    message_text TEXT DEFAULT '',
    signal_type TEXT NOT NULL DEFAULT 'noise', -- tge_listing, activity, long_term, noise
    ai_summary TEXT,
    project_name TEXT,
    ticker TEXT,
    chain TEXT,
    relevance_score INTEGER DEFAULT 0, -- 1-10
    message_date TIMESTAMP WITH TIME ZONE,
    is_added_to_leads BOOLEAN DEFAULT false,
    project_links JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()),
    CONSTRAINT unique_tg_signal UNIQUE (channel_username, message_id)
);

ALTER TABLE public.tg_signals ADD COLUMN IF NOT EXISTS project_links JSONB;

CREATE INDEX IF NOT EXISTS idx_tg_signals_type ON public.tg_signals(signal_type);
CREATE INDEX IF NOT EXISTS idx_tg_signals_date ON public.tg_signals(message_date);
CREATE INDEX IF NOT EXISTS idx_tg_signals_relevance ON public.tg_signals(relevance_score);

ALTER TABLE public.tg_signals ENABLE ROW LEVEL SECURITY;
CREATE POLICY "anon_read_tg_signals" ON public.tg_signals FOR SELECT USING (true);
CREATE POLICY "anon_insert_tg_signals" ON public.tg_signals FOR INSERT WITH CHECK (true);
CREATE POLICY "anon_update_tg_signals" ON public.tg_signals FOR UPDATE USING (true) WITH CHECK (true);
