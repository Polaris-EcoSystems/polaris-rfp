# Python + FastAPI backend image (ECS)
FROM python:3.11-slim-bookworm


ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

ENV LOG_LEVEL=info
WORKDIR /app

# System deps for python wheels + Playwright/Chromium runtime deps
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates \
      curl \
      wget \
      gnupg \
      git \
      gh \
      libnss3 \
      libatk1.0-0 \
      libatk-bridge2.0-0 \
      libdrm2 \
      libxkbcommon0 \
      libxcomposite1 \
      libxdamage1 \
      libxfixes3 \
      libxrandr2 \
      libgbm1 \
      libasound2 \
      libpangocairo-1.0-0 \
      libpango-1.0-0 \
      libcairo2 \
      libgtk-3-0 \
      libx11-xcb1 \
      libx11-6 \
      libxcb1 \
      libxext6 \
      libxrender1 \
      libglib2.0-0 \
      fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN python -m pip install --upgrade pip && python -m pip install -r /app/requirements.txt
RUN python -m playwright install chromium

COPY app /app/app

# Create non-root user
RUN useradd -m -u 1001 appuser
USER appuser

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/', timeout=2).read(); print('ok')"

# Gunicorn + Uvicorn worker for production (use ECS-provided PORT)
# Log everything to stdout/stderr so the ECS awslogs driver ships it to CloudWatch:
# - access logs (HTTP request/response)
# - error logs
# - app stdout/stderr from workers
CMD ["sh", "-c", "gunicorn -k uvicorn.workers.UvicornWorker -w ${WEB_CONCURRENCY:-2} -b 0.0.0.0:${PORT:-8080} --log-level ${LOG_LEVEL:-info} --access-logfile - --error-logfile - --capture-output --access-logformat '%(h)s %(l)s %(u)s %(t)s \"%(r)s\" %(s)s %(b)s \"%(f)s\" \"%(a)s\"' app.main:app"]
