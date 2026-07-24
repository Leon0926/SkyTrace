// SkyTrace load generator.
//
// Open-loop, constant-arrival-rate synthetic telemetry generator for the
// receiver's HTTP ingestion endpoints. Uses k6's ramping-arrival-rate
// executor so throughput is decoupled from response latency: under
// saturation, requests still fire at the target rate and slow responses
// show up as increased latency/errors rather than silently reducing
// offered load (avoids coordinated omission).
//
// Each request body carries "_lt_sent_ns" (epoch nanoseconds at send
// time). It rides through receiver -> Kafka -> storage untouched (the
// schemas don't forbid extra properties) and storage uses it to record
// end-to-end pipeline latency in the skytrace_e2e_latency_seconds
// histogram. See storage/app.py and scripts/loadtest/README.md.
//
// Usage:
//   k6 run scripts/loadtest/generate_telemetry.js
//       # runs the quick-smoke-test defaults below, no flags needed
//   k6 run scripts/loadtest/generate_telemetry.js \
//       -e RATE=500 -e DURATION=5m -e RAMP_TIME=30s -e BASE_URL=http://localhost:8080
//       # override any of them for a real run
//
// Env vars (all optional; defaults below are a quick, low-risk smoke test
// against a stack on localhost -- bump RATE/RAMP_TIME/DURATION for an
// actual sustained-throughput run, see scripts/loadtest/README.md):
//   BASE_URL   http://localhost:8080   receiver base URL (no trailing slash)
//   RATE       20                      target sustained requests/sec
//   RAMP_TIME  10s                     time to ramp from 0 to RATE
//   DURATION   30s                     time to hold steady at RATE
//   PRE_VUS    20                      VUs pre-allocated for the ramp
//   MAX_VUS    (RATE * 2, min 50)      hard cap on VUs k6 may spawn
//   ARRIVAL_MIX 0.8                    fraction of requests that are
//                                      location readings vs time-until-arrival

import http from 'k6/http';
import { check } from 'k6';
import { Counter } from 'k6/metrics';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8080';
const RATE = parseInt(__ENV.RATE || '20', 10);
const RAMP_TIME = __ENV.RAMP_TIME || '10s';
const DURATION = __ENV.DURATION || '30s';
const PRE_VUS = parseInt(__ENV.PRE_VUS || '20', 10);
const MAX_VUS = parseInt(__ENV.MAX_VUS || String(Math.max(RATE * 2, 50)), 10);
const ARRIVAL_MIX = parseFloat(__ENV.ARRIVAL_MIX || '0.8');

const httpErrors = new Counter('lt_http_errors');

export const options = {
  scenarios: {
    telemetry: {
      executor: 'ramping-arrival-rate',
      startRate: 0,
      timeUnit: '1s',
      preAllocatedVUs: PRE_VUS,
      maxVUs: MAX_VUS,
      stages: [
        { target: RATE, duration: RAMP_TIME },
        { target: RATE, duration: DURATION },
      ],
    },
  },
  thresholds: {
    // Don't fail the run automatically; we read Grafana for the real
    // verdict. This just keeps a visible marker in the k6 summary.
    lt_http_errors: ['count>=0'],
  },
};

// Fixed-prefix UUID + a small zero-padded numeric suffix (1-200),
// matching the real traffic pattern: a fleet of ~200 aircraft that each
// send many readings, rather than a fresh random UUID per message.
function flightId() {
  const n = Math.floor(randRange(1, 201));
  return `d290f1ee-6c54-4b01-90e6-d70174${String(n).padStart(6, '0')}`;
}

function nowNs() {
  // k6/JS only exposes millisecond wall-clock resolution; pad to ns.
  // This bounds e2e latency measurement precision at ~1ms, which is
  // negligible against the 10ms-30s range this histogram targets.
  return BigInt(Date.now()) * 1000000n;
}

// storage/app.py parses "timestamp" with Python's datetime.fromisoformat(),
// and storage's Docker image runs Ubuntu 22.04 -> Python 3.10, whose
// fromisoformat() cannot parse a trailing "Z" (only Python 3.11+ can) --
// it needs an explicit numeric UTC offset. JS's toISOString() emits "Z",
// so swap it for "+00:00" and pad millisecond precision to microseconds
// to match real traffic's format, e.g. "2024-08-29T09:12:33.001000+00:00".
function isoOffset(date) {
  return date.toISOString().slice(0, -1) + '000+00:00';
}

function randRange(min, max) {
  return min + Math.random() * (max - min);
}

// Cruise-altitude-biased location reading. Kept strictly inside the
// anomaly_detector thresholds (0-45000 ft) with margin: anomaly_detector
// has no try/except around its Kafka consumer loop and a triggered
// altitude anomaly hits a pre-existing KeyError bug (payload['client_id']
// vs the schema's flight_id) that permanently kills its consumer thread.
// Values here intentionally never breach [0, 45000].
function locationReadingBody() {
  return {
    flight_id: flightId(),
    latitude: randRange(-90, 90),
    longitude: randRange(-180, 180),
    altitude: randRange(500, 42000),
    timestamp: isoOffset(new Date()),
    _lt_sent_ns: nowNs().toString(),
  };
}

// time_difference_in_ms kept well inside [-300000, 300000] for the same
// reason as altitude above. date_created mirrors real traffic's payload
// shape; storage ignores it (it stamps its own date_created server-side).
function timeUntilArrivalBody() {
  const now = new Date();
  const eta = new Date(now.getTime() + randRange(5 * 60000, 4 * 3600000));
  const actual = new Date(eta.getTime() + randRange(-120000, 120000));
  return {
    flight_id: flightId(),
    estimated_arrival_time: isoOffset(eta),
    actual_arrival_time: isoOffset(actual),
    timestamp: isoOffset(now),
    time_difference_in_ms: Math.round(randRange(-250000, 250000)),
    date_created: isoOffset(now),
    _lt_sent_ns: nowNs().toString(),
  };
}

export default function () {
  const isLocation = Math.random() < ARRIVAL_MIX;
  const path = isLocation ? '/receiver/readings/location' : '/receiver/readings/time-until-arrival';
  const body = isLocation ? locationReadingBody() : timeUntilArrivalBody();

  const res = http.post(`${BASE_URL}${path}`, JSON.stringify(body), {
    headers: { 'Content-Type': 'application/json' },
    tags: { endpoint: isLocation ? 'location' : 'time_until_arrival' },
  });

  const ok = check(res, { 'status is 201': (r) => r.status === 201 });
  if (!ok) {
    httpErrors.add(1);
  }
}
