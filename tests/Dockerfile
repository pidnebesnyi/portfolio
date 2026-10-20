# Build context is the repository root. The Playwright base image is used from the start so
# the UI suite (phase 2) runs in the same container with browsers preinstalled.
FROM mcr.microsoft.com/playwright/python:v1.49.1-noble
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /work
COPY requirements-test.txt .
RUN pip install --no-cache-dir -r requirements-test.txt
COPY pyproject.toml ./
COPY tests ./tests
CMD ["pytest", "-m", "not quarantine", "-n", "auto"]
