# Versioned Matching Policy Governance

## 1. Overview
Matching policy governance moves multi-factor ranking weights from hardcoded constants into versioned database records (`public.matching_policies`). This allows operational tuning, A/B testing of heuristic weights, and historical auditability.

---

## 2. Policy Schema & Weight Invariants
All policy rows must satisfy a database `CHECK` constraint:
$$\sum w_i = w_{proximity} + w_{rating} + w_{availability} + w_{reliability} + w_{workload} + w_{acceptance} = 1.000$$

### Default Active Policy (v1.0)
- `proximity_weight`: `0.300` (30%)
- `rating_weight`: `0.200` (20%)
- `availability_weight`: `0.150` (15%)
- `reliability_weight`: `0.150` (15%)
- `workload_weight`: `0.100` (10%)
- `acceptance_weight`: `0.100` (10%)
- `max_concurrent_jobs`: 1
- `offer_timeout_seconds`: 60
- `max_offer_attempts`: 3

---

## 3. Atomic Policy Activation
Only one policy may be active at any given time. This is enforced by:
1. A partial unique index: `CREATE UNIQUE INDEX uq_matching_policies_active ON public.matching_policies(is_active) WHERE is_active = true;`
2. `MatchingPolicyService.activate_policy()` performs an atomic database update:
   - Deactivates all existing active policies (`is_active = false`).
   - Sets target version `is_active = true` and `activated_at = now()`.
   - Records an entry in `public.audit_logs`.
   - Invalidates in-memory policy cache with thread-safe lock.
