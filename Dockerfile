FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

RUN useradd --create-home --uid 1000 sachintech
COPY --chown=sachintech:sachintech . .
RUN mkdir -p /app/.runtime && chown sachintech:sachintech /app/.runtime

USER sachintech

ENV HARNESS_HOST=0.0.0.0 \
    HARNESS_PORT=8502
EXPOSE 8502

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os,urllib.request as u; u.build_opener(u.ProxyHandler({})).open(f'http://127.0.0.1:{os.environ[\"HARNESS_PORT\"]}/api/config', timeout=4)"

CMD ["python", "server.py"]
