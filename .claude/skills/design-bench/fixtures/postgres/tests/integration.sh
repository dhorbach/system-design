set -euo pipefail
source /app/enqueue.sh
psql -q -v ON_ERROR_STOP=1 -f /app/schema.sql

enqueue same-ticket 3 &
first=$!
enqueue same-ticket 3 &
second=$!
wait "$first"
wait "$second"
[[ "$(psql -Atqc "SELECT count(*) FROM tickets WHERE key = 'same-ticket'")" == 1 ]]
[[ "$(psql -Atqc "SELECT capacity FROM reservations WHERE ticket = 'same-ticket'")" == 3 ]]

if failure=$(enqueue invalid-reservation 17 2>&1); then
  echo 'Expected the storage constraint to reject this reservation' >&2
  exit 1
fi
[[ "$failure" == *reservations_capacity_check* ]]
[[ "$(psql -Atqc "SELECT count(*) FROM tickets WHERE key = 'invalid-reservation'")" == 0 ]]
echo 'Passed PostgreSQL concurrent retry and transaction rollback tests'
