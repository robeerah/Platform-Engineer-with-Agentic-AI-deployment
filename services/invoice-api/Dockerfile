FROM python:3.12-slim

ARG APP_VERSION=dev
ARG HEALTHY=true
ENV APP_VERSION=${APP_VERSION} \
    HEALTHY=${HEALTHY} \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt && useradd --create-home --uid 10001 app
COPY app.py .
USER app

EXPOSE 8080
# One worker keeps the in-memory demo state and metrics in a single process.
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "4", "app:app"]
