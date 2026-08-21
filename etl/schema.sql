-- ============================================================================
-- AdvancedHadith unified schema (ARCH ÃÂÃÂÃÂÃÂ§6.2) ÃÂÃÂ¢ÃÂÃÂÃÂÃÂ Postgres 16 + Apache AGE
-- Idempotent: safe to re-run (IF NOT EXISTS everywhere).
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS unaccent;
-- AGE is created by ops/init_local_ext.sql (or the Railway bootstrap); graph
-- objects are created in Phase 6.

-- ----------------------------------------------------------------------------
-- works & editions
-- A "work" is the abstract book (e.g. ÃÂÃÂÃÂÃÂµÃÂÃÂÃÂÃÂ­ÃÂÃÂÃÂÃÂÃÂÃÂÃÂÃÂ­ ÃÂÃÂÃÂÃÂ§ÃÂÃÂÃÂÃÂÃÂÃÂÃÂÃÂ¨ÃÂÃÂÃÂÃÂ®ÃÂÃÂÃÂÃÂ§ÃÂÃÂÃÂÃÂ±ÃÂÃÂÃÂÃÂ); an "edition" is one
-- source's copy of it (sunna crawl, Shamela CSV, hadith_struct archive page set).
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS works (
    work_id      serial PRIMARY KEY,
    title_ar     text NOT NULL,
    title_norm   text NOT NULL,
    author_ar    text,
    author_norm  text,
    kind         text NOT NULL DEFAULT 'other',  -- matn|rijal|sharh|atraf|service|other
    notes        text
);
CREATE INDEX IF NOT EXISTS works_title_trgm ON works USING gin (title_norm gin_trgm_ops);

CREATE TABLE IF NOT EXISTS editions (
    edition_id     serial PRIMARY KEY,
    work_id        int NOT NULL REFERENCES works,
    source         text NOT NULL,             -- sunna | hadith_struct | shamela
    source_book_id int,                       -- hadith.db books.id / shamela bkid / null
    title_ar       text NOT NULL,
    section_name   text,
    book_type      text,                      -- matn | service | page-archive
    passage_count  int DEFAULT 0,
    meta           jsonb DEFAULT '{}'::jsonb,
    UNIQUE (source, source_book_id)
);
CREATE INDEX IF NOT EXISTS editions_work ON editions (work_id);

-- ----------------------------------------------------------------------------
-- toc_nodes: per-edition hierarchical table of contents
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS toc_nodes (
    toc_node_id    bigserial PRIMARY KEY,
    edition_id     int NOT NULL REFERENCES editions,
    source_node_id bigint,                    -- hadith.db toc.node_id
    parent_id      bigint,                    -- references toc_nodes.toc_node_id (nullable root)
    title          text NOT NULL,
    title_norm     text NOT NULL DEFAULT '',
    is_leaf        boolean NOT NULL DEFAULT false,
    ord            int NOT NULL DEFAULT 0,
    depth          int NOT NULL DEFAULT 0,
    UNIQUE (edition_id, source_node_id)
);
CREATE INDEX IF NOT EXISTS toc_edition_parent ON toc_nodes (edition_id, parent_id, ord);

-- ----------------------------------------------------------------------------
-- passages: the single text-unit table for all three sources (ÃÂÃÂÃÂÃÂ§6.1 principle 1)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS passages (
    passage_id     bigserial PRIMARY KEY,
    edition_id     int NOT NULL REFERENCES editions,
    source         text NOT NULL,             -- sunna | hadith_struct | shamela (denormalized for filters)
    source_page_id bigint NOT NULL,           -- matn.main_id / pages.page_id / hadith_struct ord
    seq            int NOT NULL,              -- reading order within the edition
    kind           text NOT NULL DEFAULT 'page',  -- unit | page
    hadith_num     text,
    part           text,                      -- ÃÂÃÂÃÂÃÂ¬ÃÂÃÂÃÂÃÂ²ÃÂÃÂÃÂÃÂ¡
    page           text,                      -- ÃÂÃÂÃÂÃÂµÃÂÃÂÃÂÃÂÃÂÃÂÃÂÃÂ­ÃÂÃÂÃÂÃÂ© (printed)
    toc_node_id    bigint,                    -- nearest TOC anchor when known
    text_raw       text NOT NULL DEFAULT '',  -- original (tashkeel preserved)
    text_norm      text NOT NULL DEFAULT '',  -- project-standard normalization
    html           text,                      -- original HTML when the source had it
    meta           jsonb DEFAULT '{}'::jsonb, -- {prev_id,next_id,hno,sora,aya,...}
    tsv            tsvector GENERATED ALWAYS AS (to_tsvector('simple', text_norm)) STORED,
    UNIQUE (edition_id, source_page_id)
);
CREATE INDEX IF NOT EXISTS passages_edition_seq ON passages (edition_id, seq);
CREATE INDEX IF NOT EXISTS passages_tsv ON passages USING gin (tsv);
CREATE INDEX IF NOT EXISTS passages_hadith_num ON passages (edition_id, hadith_num)
    WHERE hadith_num IS NOT NULL;

-- ----------------------------------------------------------------------------
-- subjects (global thematic tree from hadith.db) + links to passages
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS subjects (
    subject_id     bigserial PRIMARY KEY,
    source_node_id bigint UNIQUE,             -- hadith.db subjects.node_id
    parent_id      bigint,                    -- references subjects.subject_id
    title          text NOT NULL,
    title_norm     text NOT NULL DEFAULT '',
    is_leaf        boolean NOT NULL DEFAULT false,
    ord            int NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS subjects_parent ON subjects (parent_id, ord);
CREATE INDEX IF NOT EXISTS subjects_title_trgm ON subjects USING gin (title_norm gin_trgm_ops);

CREATE TABLE IF NOT EXISTS subject_links (
    subject_id  bigint NOT NULL REFERENCES subjects,
    passage_id  bigint NOT NULL REFERENCES passages,
    ord         int DEFAULT 0,
    PRIMARY KEY (subject_id, passage_id)
);
CREATE INDEX IF NOT EXISTS subject_links_passage ON subject_links (passage_id);

-- ----------------------------------------------------------------------------
-- narrators (ÃÂÃÂÃÂÃÂ±ÃÂÃÂÃÂÃÂ¬ÃÂÃÂÃÂÃÂ§ÃÂÃÂÃÂÃÂ ÃÂÃÂÃÂÃÂ§ÃÂÃÂÃÂÃÂÃÂÃÂÃÂÃÂ­ÃÂÃÂÃÂÃÂ¯ÃÂÃÂÃÂÃÂÃÂÃÂÃÂÃÂ«) ÃÂÃÂ¢ÃÂÃÂÃÂÃÂ populated in Phase 6
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS narrators (
    narrator_id   serial PRIMARY KEY,
    canonical_ar  text NOT NULL,
    canonical_norm text NOT NULL,
    translit      text,
    kunya         text,
    laqab         text,
    generation    text,                       -- companion | tabii | ...
    death_year_h  int,
    bio_summary   text,
    meta          jsonb DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS narrators_norm_trgm ON narrators USING gin (canonical_norm gin_trgm_ops);

CREATE TABLE IF NOT EXISTS narrator_aliases (
    alias_id     bigserial PRIMARY KEY,
    narrator_id  int NOT NULL REFERENCES narrators,
    alias_ar     text NOT NULL,
    alias_norm   text NOT NULL,
    alias_kind   text DEFAULT 'name',         -- name | kunya | laqab | nasab | nisba
    translit     text,
    src_passage  bigint,                      -- provenance
    UNIQUE (narrator_id, alias_norm, alias_kind)
);
CREATE INDEX IF NOT EXISTS aliases_norm_trgm ON narrator_aliases USING gin (alias_norm gin_trgm_ops);
CREATE INDEX IF NOT EXISTS aliases_norm ON narrator_aliases (alias_norm);

CREATE TABLE IF NOT EXISTS narrator_assessments (
    assessment_id bigserial PRIMARY KEY,
    narrator_id   int NOT NULL REFERENCES narrators,
    critic        text,                       -- e.g. ÃÂÃÂÃÂÃÂ§ÃÂÃÂÃÂÃÂ¨ÃÂÃÂÃÂÃÂ ÃÂÃÂÃÂÃÂ­ÃÂÃÂÃÂÃÂ¨ÃÂÃÂÃÂÃÂ§ÃÂÃÂÃÂÃÂ
    grade         text,                       -- e.g. ÃÂÃÂÃÂÃÂ«ÃÂÃÂÃÂÃÂÃÂÃÂÃÂÃÂ©
    quote         text,
    src_passage   bigint REFERENCES passages,
    meta          jsonb DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS assessments_narrator ON narrator_assessments (narrator_id);

-- isnad chains extracted from passages (Phase 6)
CREATE TABLE IF NOT EXISTS isnad_chains (
    chain_id    bigserial PRIMARY KEY,
    passage_id  bigint NOT NULL REFERENCES passages,
    ord         int NOT NULL DEFAULT 0,       -- multiple chains per passage possible
    confidence  real DEFAULT 0,
    extractor   text,                         -- rule | llm | model version
    meta        jsonb DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS chains_passage ON isnad_chains (passage_id);

CREATE TABLE IF NOT EXISTS isnad_links (
    chain_id     bigint NOT NULL REFERENCES isnad_chains,
    pos          int NOT NULL,                -- 0 = collector side
    mention_ar   text NOT NULL,
    mention_norm text NOT NULL,
    verb         text,                        -- ÃÂÃÂÃÂÃÂ­ÃÂÃÂÃÂÃÂ¯ÃÂÃÂÃÂÃÂ«ÃÂÃÂÃÂÃÂÃÂÃÂÃÂÃÂ§ | ÃÂÃÂÃÂÃÂ£ÃÂÃÂÃÂÃÂ®ÃÂÃÂÃÂÃÂ¨ÃÂÃÂÃÂÃÂ±ÃÂÃÂÃÂÃÂÃÂÃÂÃÂÃÂ§ | ÃÂÃÂÃÂÃÂ¹ÃÂÃÂÃÂÃÂ ...
    narrator_id  int REFERENCES narrators,    -- resolved entity (nullable until resolution)
    confidence   real DEFAULT 0,
    PRIMARY KEY (chain_id, pos)
);
CREATE INDEX IF NOT EXISTS isnad_links_narrator ON isnad_links (narrator_id);
CREATE INDEX IF NOT EXISTS isnad_links_mention ON isnad_links (mention_norm);

-- ----------------------------------------------------------------------------
-- translations (ÃÂÃÂÃÂÃÂ§11) ÃÂÃÂ¢ÃÂÃÂÃÂÃÂ object/field/language grid with review workflow
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS translations (
    obj_type   text NOT NULL,                 -- passage | work | toc | subject | narrator
    obj_id     bigint NOT NULL,
    field      text NOT NULL,                 -- text | title | bio ...
    lang       text NOT NULL,
    text       text NOT NULL,
    status     text NOT NULL DEFAULT 'machine',   -- machine | reviewed | approved
    source     text NOT NULL DEFAULT 'gemini-2.5-flash', -- kalimat | gemini-2.5-flash | human
    src_hash   text,                          -- hash of the Arabic source at translation time
    meta       jsonb DEFAULT '{}'::jsonb,     -- kalimat_id, source_book, grade_en, ...
    reviewed_by text,
    created_at timestamptz DEFAULT now(),
    updated_at timestamptz DEFAULT now(),
    PRIMARY KEY (obj_type, obj_id, field, lang)
);

-- ----------------------------------------------------------------------------
-- job ledgers: manual, resumable, idempotent pipelines
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS embedding_jobs (
    passage_id   bigint NOT NULL REFERENCES passages,
    chunk_no     int NOT NULL,
    edition_id   int NOT NULL,
    content_hash text NOT NULL,
    status       text NOT NULL DEFAULT 'pending',  -- pending|embedded|failed|skipped
    embedded_at  timestamptz,
    PRIMARY KEY (passage_id, chunk_no)
);
CREATE INDEX IF NOT EXISTS embjobs_edition ON embedding_jobs (edition_id, status);

CREATE TABLE IF NOT EXISTS translation_jobs (
    obj_type text NOT NULL, obj_id bigint NOT NULL, field text NOT NULL, lang text NOT NULL,
    status   text NOT NULL DEFAULT 'pending',      -- pending|done|failed
    batch_id uuid,
    error    text,
    created_at timestamptz DEFAULT now(),
    PRIMARY KEY (obj_type, obj_id, field, lang)
);

CREATE TABLE IF NOT EXISTS indexing_jobs (
    edition_id      int NOT NULL REFERENCES editions,
    indexer_version text NOT NULL,
    status          text NOT NULL DEFAULT 'pending', -- pending|running|review|done|failed
    stats           jsonb,
    started_at      timestamptz, finished_at timestamptz,
    PRIMARY KEY (edition_id, indexer_version)
);

CREATE TABLE IF NOT EXISTS training_examples (
    example_id  bigserial PRIMARY KEY,
    task        text NOT NULL,                -- indexing | diacritization | pos
    source_ref  jsonb NOT NULL,
    input_text  text NOT NULL,
    labels      jsonb NOT NULL,
    origin      text NOT NULL,                -- auto | rule | reviewed
    created_at  timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS passage_annotations (
    passage_id bigint NOT NULL REFERENCES passages,
    layer      text NOT NULL,                 -- segments|pos|ner|diacritized|dependency|constituency|morphology|roots
    engine     text NOT NULL,                 -- farasa|camel|alkhalil|neural
    version    text NOT NULL,
    payload    jsonb NOT NULL,
    created_at timestamptz DEFAULT now(),
    PRIMARY KEY (passage_id, layer, engine, version)
);

-- ----------------------------------------------------------------------------
-- users & personal items (JWT auth)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    user_id    serial PRIMARY KEY,
    email      text UNIQUE NOT NULL,
    pw_hash    text NOT NULL,
    is_admin   boolean NOT NULL DEFAULT false,
    verified   boolean NOT NULL DEFAULT false,
    created_at timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS user_items (
    item_id    bigserial PRIMARY KEY,
    user_id    int NOT NULL REFERENCES users,
    kind       text NOT NULL,                 -- favourite | note | saved_search
    ref        jsonb NOT NULL,                -- {passage_id} | {query,filters} ...
    body       text,
    created_at timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS user_items_user ON user_items (user_id, kind);

-- ----------------------------------------------------------------------------
-- ETL bookkeeping
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS etl_state (
    step       text PRIMARY KEY,
    status     text NOT NULL DEFAULT 'pending',
    detail     jsonb DEFAULT '{}'::jsonb,
    updated_at timestamptz DEFAULT now()
);

-- hadith grades (ÃÂÃÂÃÂÃÂÃÂÃÂ­ÃÂÃÂ / ÃÂÃÂÃÂÃÂÃÂÃÂ¤ / ÃÂÃÂÃÂÃÂÃÂÃÂ­ÃÂÃÂ ...) from book convention, Kalimat, or scholars
CREATE TABLE IF NOT EXISTS hadith_grades (
    passage_id  bigint PRIMARY KEY REFERENCES passages ON DELETE CASCADE,
    grade_ar    text,
    grade_norm  text,                     -- sahih|hasan_sahih|hasan|gharib|daif|maqbul|mawdu|other
    source      text NOT NULL,            -- book-convention|matn-text|kalimat|scholar|manual
    meta        jsonb DEFAULT '{}'::jsonb,
    updated_at  timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS grades_norm ON hadith_grades (grade_norm);
-- sanad/matn boundary as a raw-text offset (matn highlighting)
ALTER TABLE isnad_chains ADD COLUMN IF NOT EXISTS sanad_end_raw int;

-- hadith type classification (ÃÂÃÂÃÂ¹ ÃÂ§ÃÂÃÂ­ÃÂ¯ÃÂÃÂ«): qudsi / marfu (qawli|fili) /
-- mawquf / maqtu Ã¢ÂÂ rule classifier over the matn opening + narrator generation
CREATE TABLE IF NOT EXISTS hadith_types (
    passage_id  bigint PRIMARY KEY REFERENCES passages ON DELETE CASCADE,
    type_norm   text NOT NULL,             -- qudsi|marfu_qawli|marfu_fili|marfu|mawquf|maqtu
    type_ar     text NOT NULL,
    method      text NOT NULL DEFAULT 'rule-0.1',
    confidence  real DEFAULT 0,
    updated_at  timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS hadith_types_norm ON hadith_types (type_norm);

-- manual narrator-graph curation (admin console). Overrides layered on the
-- edges derived from isnad_links; the isnad data itself is never destroyed.
CREATE TABLE IF NOT EXISTS narrator_edges_manual (
    edge_id    bigserial PRIMARY KEY,
    student_id int NOT NULL REFERENCES narrators(narrator_id) ON DELETE CASCADE,
    teacher_id int NOT NULL REFERENCES narrators(narrator_id) ON DELETE CASCADE,
    action     text NOT NULL CHECK (action IN ('add', 'remove')),
    weight     int DEFAULT 1,
    note       text,
    created_by text,
    created_at timestamptz DEFAULT now(),
    UNIQUE (student_id, teacher_id, action)
);
CREATE TABLE IF NOT EXISTS admin_audit (
    audit_id    bigserial PRIMARY KEY,
    action      text NOT NULL,
    payload     jsonb NOT NULL DEFAULT '{}'::jsonb,
    admin_email text,
    created_at  timestamptz DEFAULT now()
);

-- hadith origination timeline (ops/analyze_timeline.py; docs/HADITH_TIMELINE_ANALYSIS.md)
-- year axis is hijri; negative years = before the hijra (بعثة = -13)
CREATE TABLE IF NOT EXISTS timeline_events (
    event_key text PRIMARY KEY,
    title_ar  text NOT NULL,
    year_ah   smallint NOT NULL,
    era       text NOT NULL                -- meccan|prophetic|rashidun|umayyad
);
CREATE TABLE IF NOT EXISTS hadith_dates (
    passage_id    bigint PRIMARY KEY REFERENCES passages ON DELETE CASCADE,
    year_min      smallint,                -- origination window (inclusive)
    year_max      smallint,
    year_best     smallint,                -- specific year when a dated event matched
    basis         text NOT NULL,           -- event|companion|event+companion|season
    event_key     text REFERENCES timeline_events,
    season        text,                    -- ramadan|hajj|eid
    companion_key text,
    companion_ar  text,
    confidence    real NOT NULL,
    method        text NOT NULL DEFAULT 'rule-0.1'
);
CREATE INDEX IF NOT EXISTS hadith_dates_year ON hadith_dates (year_best);
CREATE INDEX IF NOT EXISTS hadith_dates_event ON hadith_dates (event_key);
CREATE INDEX IF NOT EXISTS hadith_dates_season ON hadith_dates (season);
CREATE INDEX IF NOT EXISTS hadith_dates_companion ON hadith_dates (companion_key);

-- ----------------------------------------------------------------------------
-- shamela unitization: hadith-level identifiers over page-archive editions
-- (ops/unitize_shamela.py). Global unit id = 'S<bkid>:<hadith_seq>'.
-- Rebuilt deterministically per environment; never copied by serial id.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS shamela_units (
    unit_id          bigserial PRIMARY KEY,
    edition_id       int NOT NULL REFERENCES editions ON DELETE CASCADE,
    bkid             int NOT NULL,             -- shamela source_book_id (stable)
    hadith_seq       int NOT NULL,             -- unique per book, reading order
    hadith_num       text,                     -- printed number (may repeat/miss)
    start_passage_id bigint NOT NULL REFERENCES passages ON DELETE CASCADE,
    end_passage_id   bigint NOT NULL REFERENCES passages ON DELETE CASCADE,
    start_off        int NOT NULL,             -- raw-text offset on start page
    end_off          int NOT NULL,             -- raw-text offset on end page
    sanad_end_off    int,                      -- neural structure boundary (raw)
    meta             jsonb NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (edition_id, hadith_seq)
);
CREATE INDEX IF NOT EXISTS shamela_units_num  ON shamela_units (edition_id, hadith_num);
CREATE INDEX IF NOT EXISTS shamela_units_page ON shamela_units (start_passage_id);

-- crosswalk: aljam3 hadith unit -> shamela unit (permanent traceability)
CREATE TABLE IF NOT EXISTS unit_map (
    aljam3_passage_id bigint PRIMARY KEY REFERENCES passages ON DELETE CASCADE,
    unit_id           bigint REFERENCES shamela_units ON DELETE SET NULL,
    bkid              int NOT NULL,
    hadith_seq        int NOT NULL,
    hadith_num        text,
    method            text NOT NULL,           -- hnum+overlap | hnum | manual
    confidence        real,
    matched_at        timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS unit_map_unit ON unit_map (unit_id);
