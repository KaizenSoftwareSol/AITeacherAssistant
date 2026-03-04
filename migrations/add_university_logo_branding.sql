-- Migration: Add Logo Branding Support for Universities
-- Purpose: Allow universities to upload custom logos for branding

-- ============================================
-- Add logo_url column to university table
-- ============================================

ALTER TABLE public.university
ADD COLUMN IF NOT EXISTS logo_url text;

COMMENT ON COLUMN public.university.logo_url IS
'Public URL to the university/institute logo. Used for branding in the sidebar. Stored in Supabase storage at /uploads/branding/{university_id}/logo.{ext}';

CREATE INDEX IF NOT EXISTS idx_university_logo_url ON public.university(logo_url) WHERE logo_url IS NOT NULL;
