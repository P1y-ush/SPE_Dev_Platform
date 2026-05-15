FROM eclipse-temurin:17

WORKDIR /app

COPY . .

RUN apt-get update && \
    apt-get install -y python3 python3-pip && \
    pip3 install flask --break-system-packages

EXPOSE 8082

CMD ["python3", "app.py"]
