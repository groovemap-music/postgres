-- Collation probe: read-only. Run under the old and the new image against the same data directory;
-- every line but server= must match. amcheck raises (and psql stops) on any index inconsistency.
\pset tuples_only on
\pset format unaligned
SELECT 'server=' || current_setting('server_version');
SELECT 'datcollate=' || datcollate || ' datctype=' || datctype || ' provider=' || datlocprovider::text || ' collversion=' || coalesce(datcollversion, '-') FROM pg_database WHERE datname = current_database();
SELECT 'rows=' || count(*) FROM collation_probe;
SELECT 'sort_md5=' || md5(string_agg(t, E'\x01' ORDER BY t, id)) FROM collation_probe;
SELECT 'sort_lower_md5=' || md5(string_agg(lower(t), E'\x01' ORDER BY lower(t), id)) FROM collation_probe;
SET enable_seqscan = off; SET enable_bitmapscan = off; SET enable_sort = off;
SELECT 'index_order_md5=' || md5(string_agg(t, E'\x01')) FROM (SELECT t FROM collation_probe ORDER BY t) s;
RESET enable_seqscan; RESET enable_bitmapscan; RESET enable_sort;
SELECT 'first12=' || string_agg(quote_literal(t), ',' ORDER BY t, id) FROM (SELECT t, id FROM collation_probe WHERE id <= 79 ORDER BY t, id LIMIT 12) s;
SELECT 'cmp a<B=' || ('a' < 'B') || ' a<A=' || ('a' < 'A') || ' é<f=' || ('é' < 'f') || ' Z<a=' || ('Z' < 'a');
SELECT 'amcheck ' || c.relname || '=ok'
FROM pg_class c, LATERAL (SELECT bt_index_parent_check(c.oid, heapallindexed => true, rootdescend => true)) checked
WHERE c.relname IN ('collation_probe_t', 'collation_probe_t_lower', 'collation_probe_pkey') ORDER BY c.relname;
