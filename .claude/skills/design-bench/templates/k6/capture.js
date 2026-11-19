import exec from 'k6/execution';
import { Trend } from 'k6/metrics';

const latency = new Trend('bench_attempt_ms', true);

// An attempt includes a single response or timeout. Keep identifiers as metadata
// so k6 does not create a time series for each request. The native JSON output
// keeps the metadata alongside the observation.
export function recordAttempt(fields) {
  if (__ENV.BENCH_CAPTURE !== '1') return;
  const elapsed = (fields.observed_ms ?? Date.now()) - fields.sent_ms;
  const metadata = exec.vu.metrics.metadata;
  for (const [name, value] of Object.entries(fields)) {
    if (value !== undefined && value !== null) metadata[`bench_${name}`] = String(value);
  }
  try {
    latency.add(elapsed);
  } finally {
    for (const name of Object.keys(fields)) delete metadata[`bench_${name}`];
  }
}
