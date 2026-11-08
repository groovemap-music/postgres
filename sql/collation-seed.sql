-- Collation fixture: mixed case, accents, ligatures, punctuation, digits, CJK, emoji and 50k pseudo-random
-- strings, with btree indexes on the text and on lower(text), built under the image being replaced.
CREATE EXTENSION IF NOT EXISTS amcheck;
CREATE TABLE collation_probe (id bigserial PRIMARY KEY, t text NOT NULL);
INSERT INTO collation_probe (t) VALUES
 ('a'),('A'),('á'),('Á'),('à'),('ä'),('b'),('B'),('ab'),('Ab'),('aB'),('a b'),('a-b'),('a_b'),('a.b'),('a''b'),
 ('1'),('10'),('2'),('02'),('Zebra'),('zebra'),('Éclair'),('eclair'),('éclair'),('ñ'),('n'),('o'),('ø'),('Ø'),
 ('ß'),('ss'),('straße'),('strasse'),(''),(' '),('  a'),('Ω'),('ω'),('日本'),('中文'),('한국어'),('Ñandú'),('Nandu'),
 ('Beyoncé'),('Beyonce'),('The Beatles'),('the beatles'),('Björk'),('Bjork'),('Sigur Rós'),('Motörhead'),('Mötley Crüe'),
 ('!!!'),('#1 Hits'),('(hed) p.e.'),('...And You Will Know Us'),('*NSYNC'),('+44'),('-M-'),('@'),('~'),('ÆON'),('Æ'),('ae'),
 ('ﬁ'),('fi'),('Ⅻ'),('½'),('😀'),('Ǆ'),('İ'),('ı'),('i'),('I');
-- 50k pseudo-random strings drawn from Latin, Latin-1, Latin Extended, Greek, Cyrillic and punctuation
INSERT INTO collation_probe (t)
SELECT string_agg(chr((ARRAY[32,45,46,39,48,65,97,192,224,256,880,1040,1072])[1 + (abs(hashint4(g * 31 + k)) % 13)]
                      + abs(hashint4(g * 17 + k * 7)) % 26), '' ORDER BY k)
FROM generate_series(1, 50000) g, generate_series(1, 1 + g % 12) k
GROUP BY g;
CREATE INDEX collation_probe_t ON collation_probe (t);
CREATE INDEX collation_probe_t_lower ON collation_probe (lower(t));
ANALYZE collation_probe;
