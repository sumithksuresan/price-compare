FROM python:3.12-slim

WORKDIR /app

RUN adduser --disabled-password --no-create-home appuser

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY scrapers/ scrapers/

RUN mkdir -p /data && chown appuser /data
VOLUME ["/data"]

USER appuser

ENV DB_PATH=/data/prices.db

EXPOSE 5002

CMD ["python", "-c", "import app; app.init_db(); app.app.run(host='0.0.0.0', port=5002)"]
