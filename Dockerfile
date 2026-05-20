FROM mcr.microsoft.com/playwright/python:v1.44.0-focal

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Data directory for session.json and screenshots
VOLUME ["/data"]
ENV DATA_DIR=/data

ENTRYPOINT ["python", "main.py"]
