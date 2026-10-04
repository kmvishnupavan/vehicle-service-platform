# Phase 15.1: Centralized Logging & Operational Observability

## 1. Overview & Log Aggregation Design

The VehicleCare backend emits structured JSON logs formatted with standardized fields:
- `timestamp`: ISO-8601 UTC timestamp
- `level`: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`
- `logger`: Subsystem identifier (e.g., `services.matching`, `services.payments`, `services.background_jobs`)
- `request_id`: Client-supplied or server-generated correlation UUID (`X-Request-ID`)
- `booking_id`: Identifier of the associated booking (when available)
- `message`: Semantic event name (e.g., `mechanic_matching_started`, `payment_webhook_processed`)

---

## 2. Ingestion Pipeline: Vector & Loki

For the pilot environment, a lightweight **Vector agent** (running alongside Docker containers) reads the Docker json logs and ships them directly to **Grafana Loki** or cloud storage:

```text
+-----------------------+
|  FastAPI Backend App  | ----> [stdout (Structured JSON)]
+-----------------------+                  |
                                           v
                               +-----------------------+
                               |  Docker JSON Logger   |
                               +-----------+-----------+
                                           |
                                           v
                               +-----------------------+
                               |  Vector Agent Daemon  |
                               +-----------+-----------+
                                           |
                                           v
                               +-----------------------+
                               |  Grafana Loki / Sink  |
                               +-----------------------+
```

### Vector Ingestion Configuration (`vector.yaml`):
```yaml
sources:
  docker_logs:
    type: docker_logs
    include_containers:
      - vehiclecare_backend
      - vehiclecare_osrm

transforms:
  parse_json:
    type: remap
    inputs:
      - docker_logs
    source: |
      . = parse_json!(.message)
      .host = get_hostname!()

sinks:
  loki_sink:
    type: loki
    inputs:
      - parse_json
    endpoint: "http://loki:3100"
    labels:
      service: "vehiclecare"
      environment: "pilot"
      level: "{{ level }}"
      logger: "{{ logger }}"
```

---

## 3. Standard Operational Search Queries (LogQL)

Operators and support engineers can trace incidents across all lifecycle phases using the following standard LogQL queries:

| Objective | LogQL Query Expression |
|:---|:---|
| **Trace Request Lifecycle** | `{service="vehiclecare"} \| json \| request_id = "f47ac10b-58cc-4372-a567-0e02b2c3d479"` |
| **Trace Specific Booking** | `{service="vehiclecare"} \| json \| booking_id = "88881111-0000-0000-0000-000000000001"` |
| **Filter by High Severity** | `{service="vehiclecare", level=~"ERROR\|CRITICAL"}` |
| **Audit Background Jobs** | `{service="vehiclecare", logger="services.background_jobs.runner"}` |
| **Track Matching Failures** | `{service="vehiclecare"} \| json \| message = "candidate_discovery_failed"` |
| **Track Payment Webhooks** | `{service="vehiclecare", logger="services.payments"} \| json \| event_id != ""` |

---

## 4. Sensitive Data Masking & Redaction Rules

The logging framework strictly adheres to zero-leakage security boundaries:
1. **Passwords**: Plaintext passwords never enter log streams; sanitized before hashing.
2. **Tokens & Secrets**: `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_JWT_SECRET`, `RAZORPAY_KEY_SECRET`, and VAPID private keys are intercepted and scrubbed if present in error traces.
3. **Payment Details**: Credit/debit card PANs, CVVs, and banking PINs are handled exclusively within the hosted Razorpay gateway modal and never reach the application backend or log files.
4. **Location Redaction**: Raw continuous GPS tracks of off-duty mechanics are never written to disk.
