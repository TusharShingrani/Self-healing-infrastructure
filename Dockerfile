ARG BASE=python:3.12-slim
FROM ${BASE}
ENV PYTHONPATH=/app/src PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY src /app/src
USER 10001:10001
CMD ["python", "-m", "platform_healer.agent"]
