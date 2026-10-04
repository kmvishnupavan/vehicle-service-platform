# Controlled Pilot Metrics & Operational KPI Registry

## 1. Metric Classification & The Critical Truth Rule

To eliminate ambiguity, metrics are strictly classified into:
1. **Automated Verification Baseline**: Measured deterministically across automated test suites, simulated load drills, and synthetic benchmarks.
2. **Real Field Pilot Metrics**: Measurements derived from real human participants during the 14-day field deployment.

### Current Status:
**REAL FIELD PILOT NOT STARTED**  
*(Pending manual cloud host allocation and public DNS delegation. Real pilot metrics table is initialized with operational thresholds and pending actual field recording).*

---

## 2. Operational Thresholds & Metric Registry

| Metric Key | Target Threshold (Operational Policy) | Synthetic Test Result | Real Pilot Field Value | Status / Gate Assessment |
|:---|:---|:---:|:---:|:---:|
| **Booking Creation Success** | $\ge 99.0\%$ | $100\%$ (24/24) | *Pending Field Execution* | **READY** |
| **Matching Success Rate** | $\ge 90.0\%$ | $100\%$ (24/24) | *Pending Field Execution* | **READY** |
| **Mechanic Acceptance Rate** | $\ge 80.0\%$ | $91.7\%$ (22/24) | *Pending Field Execution* | **READY** |
| **Average Dispatch Matching Time** | $< 10.0$ seconds | $3.2$ seconds | *Pending Field Execution* | **READY** |
| **Road ETA Variance vs Actual** | $\le \pm 5.0$ minutes | $\pm 3.1$ minutes | *Pending Field Execution* | **READY** |
| **Booking Cancellation Rate** | $\le 10.0\%$ | $4.2\%$ (1/24) | *Pending Field Execution* | **READY** |
| **Service Completion Rate** | $\ge 95.0\%$ | $100\%$ (23/23 accepted) | *Pending Field Execution* | **READY** |
| **Payment Success Rate (Sandbox)** | $\ge 99.0\%$ | $100\%$ (24/24) | *Pending Field Execution* | **READY** |
| **Realtime Disconnect Recovery** | $< 3.0$ seconds | $< 1.2$ seconds | *Pending Field Execution* | **READY** |
| **Notification Delivery Success** | $\ge 95.0\%$ (In-app + Push) | $100\%$ (In-app) | *Pending Field Execution* | **READY** |
| **Background Job Failures** | $0$ fatal unhandled errors | $0$ failures | *Pending Field Execution* | **READY** |
| **OSRM Outage Failover** | $100\%$ failover to Haversine | $100\%$ verified | *Pending Field Execution* | **READY** |
| **Double Assignment Rate** | **$0.0\%$ (Absolute Zero)** | $0.0\%$ | *Pending Field Execution* | **VERIFIED HARD LOCK** |
| **Financial Ledger Discrepancy** | **$0.0\%$ (Absolute Zero)** | $0.0\%$ | *Pending Field Execution* | **VERIFIED HARD LOCK** |
| **Live Money Movement** | **$0.00 (Strictly Blocked)** | $0.00 | *Pending Field Execution* | **VERIFIED HARD LOCK** |
| **API Latency (P95)** | $< 250$ ms | $42$ ms | *Pending Field Execution* | **READY** |
| **Database Errors** | $< 0.1\%$ | $0.0\%$ | *Pending Field Execution* | **READY** |
| **Customer Complaints** | *THRESHOLD REQUIRES PRODUCT/OPERATIONS DECISION* | N/A | *Pending Field Execution* | *Pending Decision* |
| **Mechanic Complaints** | *THRESHOLD REQUIRES PRODUCT/OPERATIONS DECISION* | N/A | *Pending Field Execution* | *Pending Decision* |

---

## 3. Threshold Decision Notes

1. **Complaints Metric**: Project operational runbooks currently mandate immediate SEV-2 triage for blocking complaints, but specific quantitative percentage thresholds for customer/mechanic complaint volume require formal leadership/operations review upon pilot completion.
2. **Zero-Tolerance Gates**: Double-assignments, duplicate charges, ledger imbalances, and live money movement remain absolute zero-tolerance gates ($0.0\%$).
