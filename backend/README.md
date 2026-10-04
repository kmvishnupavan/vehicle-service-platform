# Vehicle Service Platform - FastAPI Backend

Production-ready backend API service for the On-Demand Bike & Car Doorstep Service Platform.

---

## 1. Architecture Overview

The backend is built following a clean layered architecture:

```
[ React Client (Customer / Mechanic / Admin) ]
                      │
                      ▼ HTTP Requests (Bearer JWT)
[ FastAPI Layer (app/main.py, app/api/...) ]
                      │
                      ▼ Dependency Injection & RBAC (app/db/dependencies.py)
[ Service Layer (app/services/...) ]
                      │
                      ▼ Supabase Client (app/db/supabase.py)
[ Supabase PostgreSQL + PostGIS (Hardened RLS & Storage) ]
```

### Separation of Responsibilities:
1. **Router Layer (`app/api/`)**: Defines endpoints, OpenAPI documentation, path/query validation, and status codes. Contains **no** business logic.
2. **Service Layer (`app/services/`)**: The single authoritative source of business logic, state-machine transitions, distance calculations, and transactional operations.
3. **Database Layer (`app/db/`)**: Houses Supabase clients and authentication/RBAC dependencies that inspect the verified PostgreSQL `public.profiles` table.
4. **Core Layer (`app/core/`)**: Configuration management (`config.py`), cryptographic JWT validation (`security.py`), and structured JSON logging (`logging.py`).

---

## 2. Environment Variables

All settings are strongly typed and validated through Pydantic Settings v2. Copy the template from `.env.example`:

```bash
cp .env.example .env
```

| Variable | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `ENVIRONMENT` | Yes | `development` | Runtime environment (`development`, `staging`, `production`) |
| `DEBUG` | No | `false` | Enables verbose debug logs |
| `PROJECT_NAME` | No | `Vehicle Service Platform API` | API title in OpenAPI docs |
| `API_V1_PREFIX` | No | `/api/v1` | URL version prefix for endpoints |
| `HOST` | No | `0.0.0.0` | Host binding for Uvicorn |
| `PORT` | No | `8000` | Port binding for Uvicorn |
| `CORS_ORIGINS` | Yes | Localhost ports | JSON list or comma-separated allowed origins (wildcards prohibited in production) |
| `SUPABASE_URL` | **Yes** | — | Project API URL (`https://<project-ref>.supabase.co`) |
| `SUPABASE_PUBLISHABLE_KEY` | **Yes** | — | Supabase publishable or anon key (safe for public clients) |
| `SUPABASE_SERVICE_ROLE_KEY` | **Yes** | — | **Backend-only** privileged service role key |
| `SUPABASE_JWT_SECRET` | **Yes** | — | Supabase JWT signing secret for local signature verification |
| `RAZORPAY_KEY_ID` | Optional | — | Razorpay merchant key ID |
| `RAZORPAY_KEY_SECRET` | Optional | — | Razorpay merchant secret |
| `ROUTING_PROVIDER` | Optional | `osrm` | Mapping/routing provider |
| `ROUTING_API_KEY` | Optional | — | API key for routing engine |

---

## 3. Why Service-Role Credentials Remain Backend-Only

The `SUPABASE_SERVICE_ROLE_KEY` has **full administrative superuser power**:
- It completely bypasses all PostgreSQL Row Level Security (RLS) policies.
- It bypasses storage access boundaries and file ownership constraints.
- It bypasses table triggers guarding sensitive financial calculations.

### Strict Security Rule:
- The service-role key is **never** compiled into React or client bundles.
- The service-role key is **never** serialized into API responses or error payloads.
- The service-role key is **never** written to log files.
- It is only used by the FastAPI backend to execute authoritative business rules (e.g. state-machine transitions, payment reconciliations, and privileged queries).

---

## 4. How Authentication and Authorization Work

1. **Authentication (Supabase Auth)**:
   - Supabase Auth manages user registration, email verification, passwords, and sessions.
   - Upon login, the client receives a signed JWT access token.
   - The client includes this token in API requests:
     ```http
     Authorization: Bearer <SUPABASE_JWT>
     ```

2. **Validation in FastAPI (`app/core/security.py`)**:
   - The token is intercepted by `get_current_user`.
   - Cryptographic signature (HS256) is checked against `SUPABASE_JWT_SECRET`.
   - Token expiration (`exp`) and identity claim (`sub`) are verified.
   - If invalid or expired, FastAPI rejects the request with `HTTP 401 Unauthorized`.

3. **Authoritative Role Resolution (`app/db/dependencies.py`)**:
   - The backend resolves the user's role by querying `public.profiles` using the verified `sub` UUID.
   - **Client-supplied role headers or parameters are NEVER trusted.**
   - Role dependencies (`require_customer`, `require_mechanic`, `require_admin`, `require_support`) enforce permissions before any route code executes.

---

## 5. Development Setup & Execution

### Prerequisites
- Python 3.13+
- Active Supabase project (`vehicle-service-platform`)

### Step 1: Create Virtual Environment
```bash
# Windows
python -m venv .venv
.\.venv\Scripts\activate

# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate
```

### Step 2: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 3: Run FastAPI Development Server
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Once running:
- **Interactive OpenAPI Docs**: `http://localhost:8000/docs`
- **ReDoc Documentation**: `http://localhost:8000/redoc`
- **Health Check**: `http://localhost:8000/health`
- **Database Connectivity**: `http://localhost:8000/health/database`

---

## 6. Running Tests

Run the test suite with pytest:

```bash
pytest
```

For verbose output with structured logging:
```bash
pytest -v -s
```
