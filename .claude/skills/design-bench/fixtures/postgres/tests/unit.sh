set -euo pipefail
source src/enqueue.sh

validate_ticket ticket-123 1
validate_ticket ticket-123 999
for invalid in 'invalid key' 'invalid;key' ''; do
  if validate_ticket "$invalid" 5; then exit 1; fi
done
for invalid in 0 -1 1000 two; do
  if validate_ticket ticket-123 "$invalid"; then exit 1; fi
done
echo 'Passed unit tests for valid and invalid ticket inputs'
