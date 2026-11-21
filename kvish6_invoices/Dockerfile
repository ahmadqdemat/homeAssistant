FROM python:3.12-alpine

ENV PYTHONUNBUFFERED=1 \
    PIP_ROOT_USER_ACTION=ignore \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN pip install --no-cache-dir requests==2.32.3

COPY run.py /run.py

CMD ["python3", "/run.py"]
