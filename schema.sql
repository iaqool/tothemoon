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

-- 3. Таблица логов аутрича
CREATE TABLE IF NOT EXISTS public.outreach_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    contact_id UUID REFERENCES public.contacts(id) ON DELETE CASCADE,
    stage TEXT NOT NULL, -- Stage 1 (Cold), Follow-up 1, Follow-up 2, Stage 2 (Offer)
    message_sent TEXT,
    sent_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()),
    response TEXT
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
CREATE INDEX idx_projects_status ON public.projects(status);
CREATE INDEX idx_projects_priority ON public.projects(is_priority);
CREATE INDEX idx_projects_upcoming ON public.projects(is_upcoming);
CREATE INDEX idx_projects_launch_date ON public.projects(launch_date);
CREATE INDEX idx_contacts_project_id ON public.contacts(project_id);
