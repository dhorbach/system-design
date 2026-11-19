BEGIN;
WITH added AS (
  INSERT INTO tickets (key) VALUES (:'ticket')
  ON CONFLICT DO NOTHING
  RETURNING key
)
INSERT INTO reservations (ticket, capacity)
SELECT key, :capacity FROM added;
COMMIT;
