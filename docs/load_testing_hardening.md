# Backend Load-Testing Hardening

This backend now includes load-testing hardening features:

## Implemented
- Request correlation IDs via `X-Request-ID`.
- Prometheus-style metrics endpoint at `GET /api/v1/metrics`.
- Readiness probe at `GET /api/v1/ready`.
- Request-id-aware performance/query logs.
- Reduced high-volume DB debug prints under load.

## New/Relevant Environment Variables
- `LOG_LEVEL` (default: `INFO`)
- `LOG_TO_STDOUT` (default: `true`)
- `VERBOSE_DB_LOGS` (default: `false`)

## Health Endpoints
- `GET /api/v1/health` -> liveness
- `GET /api/v1/ready` -> readiness checks for Supabase clients/cache
- `GET /api/v1/metrics` -> plain text metrics for scraping

## Notes for Load Tests
- Send a unique `X-Request-ID` per virtual user/request when possible.
- Correlate frontend failures with backend logs by `rid=...`.
- Keep `VERBOSE_DB_LOGS=false` for stress/soak to avoid log noise.
