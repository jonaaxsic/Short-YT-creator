FROM python:3.11-slim

WORKDIR /app
ENV HOST=0.0.0.0
ENV PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY web ./web
COPY README.md .

EXPOSE 7860
CMD ["python", "-m", "app", "7860"]
