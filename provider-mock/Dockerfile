FROM python:3.12-slim AS builder
WORKDIR /build
COPY requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv
COPY --from=builder /wheels /wheels
COPY requirements.txt .
RUN pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt \
    && rm -rf /wheels requirements.txt \
    && useradd --system --uid 10001 --no-create-home appuser
COPY main.py .
USER appuser
EXPOSE 8081
HEALTHCHECK --interval=5s --timeout=3s --start-period=3s --retries=10 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8081/health', timeout=2)"
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8081"]
