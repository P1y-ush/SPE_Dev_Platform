FROM python:3.10-slim

WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ .
COPY k8s/ /k8s/

ENV K8S_TEMPLATES_DIR=/k8s

EXPOSE 5002

CMD ["python", "app.py"]
