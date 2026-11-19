// Open-loop load: requests start on a schedule that does not depend on how fast
// the system answers, the way independent clients behave. A request the generator
// could not start on time is counted as dropped, and a run with drops is not valid.
//
//   k6 run load.js -e TARGET=http://api:8080/v1/things -e RATE=200 -e DURATION=120s -e WARMUP=30s
//
// Shapes (SHAPE=): constant (default) | ramp (STEPS="50,100,200,400", each for DURATION)
//                  | spike (RATE for WARMUP, then PEAK for PEAK_FOR, then RATE for DURATION)
// Thresholds are the design's targets (P99_MS, ERR_RATE); k6 exits non-zero when one is missed.
// Only the `measure` part is judged; the warm-up is thrown away.
import http from 'k6/http';
import { check } from 'k6';
import { recordAttempt } from './capture.js';

const env = (k, d) => (__ENV[k] === undefined || __ENV[k] === '' ? d : __ENV[k]);
const RATE = +env('RATE', 50), DURATION = env('DURATION', '60s'), WARMUP = env('WARMUP', '15s');
const SHAPE = env('SHAPE', 'constant');
// Enough virtual users to hold RATE requests that each take up to MAX_LATENCY_S.
const VUS = Math.ceil(Math.max(RATE, +env('PEAK', 0), ...env('STEPS', '0').split(',').map(Number)) * +env('MAX_LATENCY_S', 2));
const secs = (s) => (s.endsWith('m') ? 60 * parseFloat(s) : parseFloat(s));

const arrival = (rate, duration, startTime) => ({
  executor: 'constant-arrival-rate', rate, timeUnit: '1s', duration, startTime,
  preAllocatedVUs: VUS, maxVUs: VUS,
});

const scenarios = {};
if (SHAPE === 'ramp') {
  // One step per rate, each its own scenario so each has its own numbers: step_0050, step_0100 …
  env('STEPS', '50,100,200').split(',').map(Number).forEach((r, i) => {
    scenarios['step_' + String(r).padStart(5, '0')] = arrival(r, DURATION, `${i * secs(DURATION)}s`);
  });
} else if (SHAPE === 'spike') {
  const peakFor = env('PEAK_FOR', '10s');
  if (parseFloat(WARMUP) > 0) scenarios.warmup = arrival(RATE, WARMUP, '0s');
  scenarios.measure = {
    executor: 'ramping-arrival-rate', startRate: +env('PEAK', RATE * 10), timeUnit: '1s', startTime: WARMUP,
    preAllocatedVUs: VUS, maxVUs: VUS,
    stages: [{ target: +env('PEAK', RATE * 10), duration: peakFor }, { target: RATE, duration: '0s' }, { target: RATE, duration: DURATION }],
  };
} else {
  if (parseFloat(WARMUP) > 0) scenarios.warmup = arrival(RATE, WARMUP, '0s');
  scenarios.measure = arrival(RATE, DURATION, WARMUP);
}

const thresholds = {};
for (const s of Object.keys(scenarios).filter((s) => s !== 'warmup')) {
  thresholds[`http_req_duration{scenario:${s}}`] = [`p(99)<${env('P99_MS', 1000)}`];
  thresholds[`http_req_failed{scenario:${s}}`] = [`rate<=${env('ERR_RATE', 0.001)}`];
  thresholds[`iterations{scenario:${s}}`] = ['count>0'];
  thresholds[`dropped_iterations{scenario:${s}}`] = ['count==0'];
}

export const options = {
  scenarios, thresholds,
  summaryTrendStats: ['min', 'med', 'avg', 'p(90)', 'p(95)', 'p(99)', 'p(99.9)', 'max', 'count'],
  discardResponseBodies: true,
};

let seq = 0;
export default function () {
  // TODO: the request a client of the design makes. Give each one a key the ledger can follow.
  const key = `${__VU}-${seq++}-${Date.now()}`;
  const url = env('TARGET', 'http://toxiproxy:9001/do?ms=5');
  // The key travels in headers, so the URL stays the same and k6 keeps one series, not one per request.
  const sent = Date.now();
  const res = http.get(url, { headers: { 'X-Bench-Key': key, 'X-Bench-Due': String(sent) } });
  recordAttempt({ request_id: key, sent_ms: sent, observed_ms: Date.now(), status: res.status });
  check(res, { 'status 2xx': (r) => r.status >= 200 && r.status < 300 });
}

// Writes /results/<OUT>: for a constant or spike run the judged part appears under
// the plain metric names; for a ramp each step keeps its scenario name.
export function handleSummary(data) {
  const metrics = {};
  for (const [name, m] of Object.entries(data.metrics)) {
    const tag = name.match(/^(.+)\{scenario:(.+)\}$/);
    if (!tag) continue;
    metrics[tag[2] === 'measure' ? tag[1] : `${tag[2]}.${tag[1]}`] = { values: m.values };
  }
  const failed = Object.entries(data.metrics).flatMap(([n, m]) =>
    Object.entries(m.thresholds || {}).filter(([, t]) => !t.ok).map(([t]) => `${n}: ${t}`));
  const out = { metrics, thresholds_failed: failed, state: data.state };
  const lines = Object.entries(metrics).filter(([n]) => /duration$|iterations$|failed$/.test(n))
    .map(([n, m]) => `  ${n}: ${JSON.stringify(m.values)}`).join('\n');
  return {
    [`/results/${env('OUT', 'k6.json')}`]: JSON.stringify(out, null, 1),
    stdout: `${lines}\n  thresholds failed: ${failed.length ? failed.join('; ') : 'none'}\n`,
  };
}
