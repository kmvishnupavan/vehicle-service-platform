# ==============================================================================
# Vehicle Service Platform - Production Frontend Dockerfile
# Multi-stage build: Node.js 20 build stage -> Nginx Alpine static server
# ==============================================================================

# Stage 1: Build production React application
FROM node:20-alpine AS builder

WORKDIR /app

# Accept build arguments for environment-specific public API URL and Supabase configs
ARG VITE_API_BASE_URL
ARG VITE_SUPABASE_URL
ARG VITE_SUPABASE_PUBLISHABLE_KEY

ENV VITE_API_BASE_URL=$VITE_API_BASE_URL \
    VITE_SUPABASE_URL=$VITE_SUPABASE_URL \
    VITE_SUPABASE_PUBLISHABLE_KEY=$VITE_SUPABASE_PUBLISHABLE_KEY \
    NODE_ENV=production

# Install dependencies including build tools (TypeScript & Vite)
COPY package.json package-lock.json ./
RUN npm ci --include=dev

# Copy source files
COPY tsconfig.json tsconfig.node.json vite.config.ts tailwind.config.js postcss.config.js index.html ./
COPY src ./src
COPY public ./public

# Build production bundle with TypeScript type-checking
RUN npm run build


# Stage 2: Serve production assets via lightweight Nginx Alpine
FROM nginx:alpine AS runner

# Remove default nginx static website
RUN rm -rf /usr/share/nginx/html/*

# Copy built static assets from builder stage
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy custom nginx SPA configuration with security headers
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Expose standard HTTP port
EXPOSE 80

# Healthcheck verifying Nginx serves the healthz endpoint
HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://localhost/healthz || exit 1

CMD ["nginx", "-g", "daemon off;"]
