# Phase 15.1: Pilot DNS & TLS Configuration

## 1. Domain & DNS Strategy

Target Primary Domain: **`vehiclecare.app`**  
Target API Subdomain: **`api.vehiclecare.app`**  

### Current Status:
- **Domain State**: Reserved / Configured in application code and CORS whitelist.
- **Live DNS State**: **NOT YET ROUTED** (Public registrar delegation to pilot VPS pending physical server allocation).
- **Public HTTPS State**: **NOT LIVE ON PUBLIC INTERNET** (Local development operates over HTTP; Cloud staging database uses Supabase TLS).

---

## 2. Required DNS Record Table

The following records must be provisioned at the domain registrar / DNS provider (e.g., Cloudflare, Route53, Namecheap) upon allocating the cloud host IP (`203.0.113.10` used below as representative public IP):

| Type | Name / Host | Target / Value | TTL | Purpose |
|:---|:---|:---|:---|:---|
| **A** | `@` (`vehiclecare.app`) | `203.0.113.10` | 300s | Frontend SPA web traffic |
| **A** | `api` (`api.vehiclecare.app`) | `203.0.113.10` | 300s | FastAPI backend REST API |
| **CNAME** | `www` | `vehiclecare.app` | 300s | Canonical www redirect |
| **CAA** | `@` | `0 issue "letsencrypt.org"` | 3600s | Authorize Let's Encrypt issuance |
| **TXT** | `@` | `v=spf1 -all` | 3600s | Email security protection |

---

## 3. TLS Termination & Certificate Lifecycle

### Provider Selection:
**Let's Encrypt via Certbot (Automated ACME v2)**
- Automated HTTP-01 challenge via Nginx ACME webroot (`/.well-known/acme-challenge/`).
- Automated cron renewal twice daily via `certbot renew --quiet --deploy-hook "nginx -s reload"`.

### Nginx SSL Configuration Specification:
```nginx
# HTTP to HTTPS Strict 301 Permanent Redirect
server {
    listen 80;
    listen [::]:80;
    server_name vehiclecare.app www.vehiclecare.app api.vehiclecare.app;

    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location / {
        return 301 https://$host$request_uri;
    }
}

# HTTPS Server Block (vehiclecare.app)
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name vehiclecare.app;

    ssl_certificate /etc/letsencrypt/live/vehiclecare.app/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/vehiclecare.app/privkey.pem;
    ssl_session_timeout 1d;
    ssl_session_cache shared:SSL:10m;
    ssl_session_tickets off;

    # Modern TLS profile (TLS 1.2 and TLS 1.3 only)
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;

    # Security Headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Permissions-Policy "geolocation=(self), camera=(), microphone=()" always;

    root /usr/share/nginx/html;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }
}

# HTTPS Server Block (api.vehiclecare.app)
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name api.vehiclecare.app;

    ssl_certificate /etc/letsencrypt/live/vehiclecare.app/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/vehiclecare.app/privkey.pem;

    location / {
        proxy_pass http://backend:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Request-ID $request_id;
    }
}
```

---

## 4. Web Push & WebSocket (WSS) Compatibility

1. **Web Push HTTPS Mandate**: Browser Notification API (`navigator.serviceWorker.register` and `PushManager.subscribe`) strictly enforces an active HTTPS context. Once public TLS is provisioned on `vehiclecare.app`, native push notifications will be fully operational.
2. **WebSocket / WSS Passthrough**: Supabase Realtime connections connect directly via WSS to `https://dfigtryvvujhwuiyzdvs.supabase.co/realtime/v1/websocket`, natively supported over HTTPS with valid certificate authority verification.

---

## 5. Verification Commands for Live Deployment

```bash
# 1. Verify DNS A Record Propagation
dig +short A vehiclecare.app
dig +short A api.vehiclecare.app

# 2. Verify TLS Handshake & Certificate Expiry
openssl s_client -connect vehiclecare.app:443 -servername vehiclecare.app < /dev/null 2>/dev/null | openssl x509 -noout -dates -issuer

# 3. Verify HTTP to HTTPS 301 Redirect
curl -I http://vehiclecare.app

# 4. Verify HSTS Header
curl -s -I https://vehiclecare.app | grep -i "strict-transport-security"
```
