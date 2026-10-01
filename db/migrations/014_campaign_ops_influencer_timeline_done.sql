-- Independent visual tracking; legacy workflow completion remains unchanged.
ALTER TABLE campaign_ops_influencer_planning_steps
    ADD COLUMN IF NOT EXISTS done boolean NOT NULL DEFAULT false;
