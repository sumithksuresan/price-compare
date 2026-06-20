FROM python:3.12-slim

WORKDIR /app

RUN adduser --disabled-password --no-create-home appuser

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY templates/ templates/
COPY static/ static/

USER appuser

ENV FLASK_APP=app.py

EXPOSE 5000

CMD ["python", "app.py"]
