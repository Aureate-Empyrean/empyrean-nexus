FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/backend
WORKDIR /app
COPY requirements.lock LICENSE README.md ./
RUN pip install --no-cache-dir -r requirements.lock
COPY backend ./backend
COPY frontend ./frontend
COPY protocol ./protocol
COPY examples/example-module/manifest.json ./examples/example-module/manifest.json
COPY deploy/broker-entrypoint.py ./deploy/broker-entrypoint.py
RUN mkdir /data && chown 10001:10001 /data
USER 10001:10001
CMD ["uvicorn", "nexus.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "12333", "--no-proxy-headers", "--no-access-log"]
