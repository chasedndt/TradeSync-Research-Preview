-- Store the latest bounded StrikeZone browser-research receipt beside the
-- existing quant-lab documents. The payload is advisory evidence only.

alter table sz_documents drop constraint if exists sz_documents_kind_check;

alter table sz_documents
  add constraint sz_documents_kind_check
  check (kind in (
    'scorecards',
    'health',
    'methodology',
    'assumptions',
    'fleet_health',
    'research_evidence'
  ));

-- DOWN
delete from sz_documents where kind = 'research_evidence';
alter table sz_documents drop constraint if exists sz_documents_kind_check;
alter table sz_documents
  add constraint sz_documents_kind_check
  check (kind in ('scorecards', 'health', 'methodology', 'assumptions', 'fleet_health'));
