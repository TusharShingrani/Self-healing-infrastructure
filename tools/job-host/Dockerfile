FROM python:3.12-slim
RUN pip install --no-cache-dir psycopg2-binary==2.9.11
WORKDIR /app
COPY app.py /app/app.py
COPY banking.py bank-ca.crt /app/
COPY policy_witness.py /app/policy_witness.py
USER 10001:10001
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
CMD ["python", "/app/app.py"]
