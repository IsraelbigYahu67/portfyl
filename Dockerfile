# syntax=docker/dockerfile:1

# ---- Stage 1: build the React frontend ----------------------------------------
FROM node:22-alpine AS frontend
WORKDIR /app/frontend
# Install from the lockfile first for better layer caching.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
# Build the SPA -> /app/frontend/dist. Firebase web config is public client
# config (protected by Firebase's authorized-domains + security rules, not
# secrecy) but Vite still needs it at BUILD time, not runtime -- and
# .dockerignore deliberately excludes .env* from the build context, so these
# come in as build args instead (pass with `docker build --build-arg ...`).
ARG VITE_FIREBASE_API_KEY
ARG VITE_FIREBASE_AUTH_DOMAIN
ARG VITE_FIREBASE_PROJECT_ID
ARG VITE_FIREBASE_APP_ID
ARG VITE_PORTFYL_EDITION=cloud
ENV VITE_PORTFYL_EDITION=$VITE_PORTFYL_EDITION \
    VITE_FIREBASE_API_KEY=$VITE_FIREBASE_API_KEY \
    VITE_FIREBASE_AUTH_DOMAIN=$VITE_FIREBASE_AUTH_DOMAIN \
    VITE_FIREBASE_PROJECT_ID=$VITE_FIREBASE_PROJECT_ID \
    VITE_FIREBASE_APP_ID=$VITE_FIREBASE_APP_ID
COPY frontend/ ./
RUN npm run build:cloud

# ---- Stage 2: Python backend + built SPA (runtime) ----------------------------
FROM python:3.14-slim AS runtime
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORTFYL_EDITION=cloud \
    PORT=8080
WORKDIR /app

# Backend deps first (layer cached unless requirements.txt changes).
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# Backend source. snowball.db / .env / __pycache__ are kept out via .dockerignore,
# so no data or secrets are baked into the image. The cloud edition's database
# is Neon PostgreSQL, reached at runtime via DATABASE_URL -- nothing DB-related
# is baked into the image or mounted as a volume.
COPY backend/ ./backend/

# Drop the built SPA where FastAPI looks for it: backend/main.py serves
# ../frontend/dist (Section 4), i.e. /app/frontend/dist here.
COPY --from=frontend /app/frontend/dist ./frontend/dist

# Run from the backend dir (mirrors local dev; `main:app` is importable here).
WORKDIR /app/backend
EXPOSE 8080

# Production server: no --reload, bind 0.0.0.0 on the PORT Cloud Run provides
# (default 8080). --proxy-headers so the app trusts Cloud Run's TLS termination.
# DATABASE_URL (Neon PostgreSQL) is required at runtime -- see database.py's
# DatabaseSettings.from_env, which fails closed without it. Because Postgres
# (not single-writer SQLite) is the database, this image is safe to run with
# more than one Cloud Run instance/revision at once; see deploy/cloudrun.md.
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080} --proxy-headers --forwarded-allow-ips '*'"]
