-- UP
-- One covering index for the reads that scan the whole attribution history.
--
-- The opportunity-learning scoreboard, the verdict tables and the evidence
-- combination all select a date range of `opportunity_attributions` and nothing
-- else. Every row of that table is inside the 14-day window the reads ask for,
-- so the range is the table, and each read was a 25 MB heap scan on a container
-- limited to 768 MB and half a CPU. Measured on a throwaway postgres:16 with the
-- same settings and a table of the same shape (11,253 rows, see
-- docs/changes/2026-09-15_research-evidence-and-postgres.md):
--
--   select *, order by      Gather Merge, 2 workers, external merge sort
--                           spilling 8.8 MB + 7.7 MB to disk, 0.9-1.3 s
--   only the columns read   sequential scan, no sort, no temporary files, 4.4 ms
--   the same, with this     index-only scan, 0 heap fetches, 132 buffers, 2.7 ms
--
-- The included columns are the ones the aggregations and the evidence
-- combination actually read, so the heap is not touched at all. The index is
-- about 1 MB against the table's 25 MB.
--
-- This creates no rows and changes no existing index; the old indexes stay for
-- the queries that filter by horizon or classification.

create index if not exists idx_attributions_opened_cover
  on opportunity_attributions (opened_at, horizon_minutes)
  include (opportunity_id, symbol, direction, classification, net_return_pct, signed_return_pct, entry_regime);

-- DOWN
drop index if exists idx_attributions_opened_cover;
