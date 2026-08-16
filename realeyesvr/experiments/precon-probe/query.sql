-- DuckDB over the JSONL log. No server, no schema migration, no load step.
--   duckdb -c ".read query.sql"

CREATE OR REPLACE VIEW facts AS
  SELECT * FROM read_json_auto('facts.jsonl', union_by_name=true);

-- 1. every tag the model found, and where it came from
SELECT tag,
       source.sheet AS sheet,
       source.rev   AS rev,
       attrs
FROM facts
WHERE type = 'equipment_schedule_row'
ORDER BY tag;

-- 2. supersession: the current assertion for each tag is the newest one.
--    This is why the log is append-only -- nothing is ever overwritten,
--    and "what did we believe at DD" stays answerable.
CREATE OR REPLACE VIEW current_equipment AS
  SELECT * FROM (
    SELECT *, row_number() OVER (
             PARTITION BY tag ORDER BY effective DESC, source.rev DESC
           ) AS rn
    FROM facts WHERE type = 'equipment_schedule_row'
  ) WHERE rn = 1;

-- 3. tags whose values changed between revisions -- the re-pricing list
SELECT tag, count(DISTINCT attrs::VARCHAR) AS distinct_values, count(*) AS assertions
FROM facts
WHERE type = 'equipment_schedule_row'
GROUP BY tag
HAVING count(DISTINCT attrs::VARCHAR) > 1
ORDER BY distinct_values DESC;

-- 4. pages the extractor choked on -- your rework queue
SELECT source.page AS page, error
FROM facts WHERE type = 'extraction_error'
ORDER BY page;

-- 5. coverage skeleton: left join current equipment against a scope list
--    you maintain by hand at first (scope.csv: tag,package).
--    Orphans are where the money leaks.
-- SELECT e.tag, s.package
-- FROM current_equipment e
-- LEFT JOIN read_csv_auto('scope.csv') s USING (tag)
-- WHERE s.package IS NULL;
