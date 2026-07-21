# SenseMinds 360 - single image, run as api / worker / migrate via compose command.
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Install PINNED dependencies first (reproducible layer, changes rarely), then
# the package itself with deps already satisfied. Building from requirements.lock
# rather than pyproject's open ranges is what protects the reproducible-output
# guarantee — a rebuild cannot silently pull a newer numpy/scipy/scikit-learn.
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock

COPY pyproject.toml ./
COPY senseminds ./senseminds
RUN pip install --no-cache-dir --no-deps .

# Run from source so the Alembic migration scripts (non-package files) are present.
ENV PYTHONPATH=/app \
    SENSEMINDS_ARTIFACT_ROOT=/data/artifacts \
    PYTHONUNBUFFERED=1

EXPOSE 8000

# Default role: the API. Overridden per service in docker-compose.
CMD ["uvicorn", "senseminds.api.asgi:app", "--host", "0.0.0.0", "--port", "8000"]
