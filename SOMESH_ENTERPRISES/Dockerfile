FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend /app/backend
COPY frontend /app/frontend
COPY samples /app/samples
EXPOSE 8080
CMD ["python", "backend/app.py"]
