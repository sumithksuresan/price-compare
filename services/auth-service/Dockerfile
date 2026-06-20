FROM python:3.12-slim

WORKDIR /app

RUN adduser --disabled-password --no-create-home appuser

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

RUN mkdir -p /data && chown appuser /data
VOLUME ["/data"]

USER appuser

ENV FLASK_APP=app.py
ENV DB_PATH=/data/auth.db

EXPOSE 5001

CMD ["python", "-c", "import app; app.init_db(); app.app.run(host='0.0.0.0', port=5001)"]
