# Build context is the repository root (see docker-compose.yml): `docker build -f app/Dockerfile .`

# --- builder: compile wheels once so the runtime image needs no compiler or network ----------
FROM python:3.12-slim AS builder
WORKDIR /build
COPY app/requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt

# --- runtime ---------------------------------------------------------------------------------
FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv
COPY --from=builder /wheels /wheels
COPY app/requirements.txt .
RUN pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt \
    && rm -rf /wheels requirements.txt \
    && useradd --system --uid 10001 --no-create-home appuser \
    && mkdir -p /var/log/app && chown appuser /var/log/app
COPY app ./app
USER appuser
EXPOSE 8000
HEALTHCHECK --interval=5s --timeout=3s --start-period=5s --retries=10 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=2)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
