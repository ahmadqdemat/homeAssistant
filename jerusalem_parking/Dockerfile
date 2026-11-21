FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PIP_ROOT_USER_ACTION=ignore \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

RUN apt-get update \
 && apt-get install -y --no-install-recommends libatomic1 xvfb xauth fonts-noto-core fonts-dejavu-core ca-certificates \
 && pip install --no-cache-dir playwright==1.65.2 requests==2.32.3 \
 && playwright install --with-deps chromium \
 && rm -rf /var/lib/apt/lists/*

COPY run.py /run.py

CMD ["python3", "/run.py"]
