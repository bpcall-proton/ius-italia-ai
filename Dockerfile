# Versione online: API + app web. Fascicoli e documenti restano nel browser dell'utente.
FROM node:22-slim AS web
WORKDIR /web
COPY desktop/package.json desktop/package-lock.json ./
RUN npm ci --ignore-scripts
COPY desktop/ ./
RUN npx tsc -b && npx vite build

FROM python:3.11-slim
WORKDIR /app
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./
COPY --from=web /web/dist ./web
ENV IUS_WEB_DIR=/app/web IUS_DATA_DIR=/data IUS_DATABASE_URL=sqlite:////data/ius.db
CMD ["sh", "-c", "mkdir -p /data && uvicorn app.main:create_app --factory --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers"]
