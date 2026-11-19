validate_ticket() {
  local key="$1" capacity="$2"
  [[ "$key" =~ ^[a-z0-9-]+$ && "$capacity" =~ ^[1-9][0-9]{0,2}$ ]]
}

enqueue() {
  local key="$1" capacity="$2"
  validate_ticket "$key" "$capacity" || return 2
  psql -q -v ON_ERROR_STOP=1 -v ticket="$key" -v capacity="$capacity" \
    -f "$(dirname "${BASH_SOURCE[0]}")/enqueue.sql"
}
