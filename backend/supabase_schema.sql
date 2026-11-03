-- Run this in your Supabase SQL editor
-- Go to: supabase.com → Your Project → SQL Editor → New Query

CREATE TABLE traffic_analysis (
  id              BIGSERIAL PRIMARY KEY,
  created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  filename        TEXT,
  video_url       TEXT,
  video_public_id TEXT,
  processed_video_url TEXT,
  video_urls        JSONB,  -- NEW: per-lane source video URLs, e.g. {"North": "...", "South": "..."}
  video_public_ids  JSONB,  -- NEW: per-lane Cloudinary public IDs
  filenames         JSONB,  -- NEW: per-lane original filenames
  processed_video_urls JSONB,  -- NEW: per-lane annotated/output video URLs
  total_vehicles  INTEGER,
  lane_counts     JSONB,
  signal_decisions JSONB,
  segment_decisions JSONB,  -- full per-segment decision timeline for long videos
  frame_data      JSONB
);

-- Enable Row Level Security (optional but recommended)
ALTER TABLE traffic_analysis ENABLE ROW LEVEL SECURITY;

-- Allow all operations for anon key (for demo purposes)
CREATE POLICY "Allow all" ON traffic_analysis
  FOR ALL USING (true) WITH CHECK (true);

-- ── Migration for an EXISTING table (run this instead if you already
--    created traffic_analysis before these columns were added) ──
-- ALTER TABLE traffic_analysis ADD COLUMN IF NOT EXISTS segment_decisions JSONB;
-- ALTER TABLE traffic_analysis ADD COLUMN IF NOT EXISTS video_urls JSONB;
-- ALTER TABLE traffic_analysis ADD COLUMN IF NOT EXISTS video_public_ids JSONB;
-- ALTER TABLE traffic_analysis ADD COLUMN IF NOT EXISTS filenames JSONB;
-- ALTER TABLE traffic_analysis ADD COLUMN IF NOT EXISTS processed_video_urls JSONB;
