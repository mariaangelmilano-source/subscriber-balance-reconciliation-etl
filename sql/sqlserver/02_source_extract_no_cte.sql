-- Extraction queries run against the production sources (read-only, no CTEs allowed).
-- Minimal columns only; the ETL streams the result in chunks.

-- Mediation stores events as key/value rows. Pull only the 3 attributes the balance needs.
SELECT event_id, attr_name, attr_value
FROM mediation.usage_attrs
WHERE attr_name IN ('msisdn', 'event_day', 'cost')
  AND event_id IN (SELECT event_id FROM mediation.usage_attrs
                   WHERE attr_name = 'event_day' AND attr_value = @day)
ORDER BY event_id;

-- Alternative pivot on the source side when allowed: conditional aggregation, still without CTEs.
SELECT event_id,
       MAX(CASE WHEN attr_name = 'msisdn'    THEN attr_value END) AS msisdn,
       MAX(CASE WHEN attr_name = 'event_day' THEN attr_value END) AS event_day,
       MAX(CASE WHEN attr_name = 'cost'      THEN attr_value END) AS cost
FROM mediation.usage_attrs
WHERE attr_name IN ('msisdn', 'event_day', 'cost')
GROUP BY event_id;
