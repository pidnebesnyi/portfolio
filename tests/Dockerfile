# Build context is the repository root. The Playwright base image carries the browsers; its tag
# must equal the playwright version pinned in requirements-test.txt (1.49.1).
FROM mcr.microsoft.com/playwright/python:v1.49.1-noble
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /work
COPY requirements-test.txt .
RUN pip install --no-cache-dir -r requirements-test.txt
COPY pyproject.toml .test_durations ./
COPY tests ./tests
CMD ["pytest", "-m", "not quarantine", "-n", "auto"]
