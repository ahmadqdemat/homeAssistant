FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

RUN pip install --no-cache-dir playwright==1.65.2 requests==2.32.3 \
 && playwright install --with-deps chromium \
 && apt-get update \
 && apt-get install -y --no-install-recommends xvfb xauth fonts-noto-core fonts-dejavu-core \
 && rm -rf /var/lib/apt/lists/*

COPY run.py /run.py

CMD ["python3", "/run.py"]
