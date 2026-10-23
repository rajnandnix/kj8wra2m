# Build from the repository root: docker build -f backend/Dockerfile .
# Stage 1 installs runtime dependencies into an isolated prefix.
FROM python:3.12-slim AS builder
WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Stage 2 is the runtime image: dependencies, app code and the committed data snapshot only.
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
RUN useradd --system --no-create-home --uid 10001 app
COPY --from=builder /install /usr/local
WORKDIR /srv
COPY backend/app ./backend/app
COPY data/app.db ./data/app.db
USER app
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
    CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"
CMD ["uvicorn", "app.main:app", "--app-dir", "backend", "--host", "0.0.0.0", "--port", "8000"]
