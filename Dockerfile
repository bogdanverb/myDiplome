# Python + PostgreSQL
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

COPY init-db.sh ./
RUN chmod +x init-db.sh
CMD ./init-db.sh && python app.py