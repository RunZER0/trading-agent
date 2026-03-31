# ── Stage 1: Build React frontend ────────────────────────
FROM node:20-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
# API calls go to /api on the same origin
ENV VITE_API_URL=/api
RUN npm run build

# ── Stage 2: Python backend ───────────────────────────────
FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ .
# Copy built frontend into a known location
COPY --from=frontend-build /app/frontend/dist ./frontend_dist
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
