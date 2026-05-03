FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir fastapi uvicorn openai python-dotenv

COPY challenge/ challenge/

EXPOSE 8080

CMD ["uvicorn", "challenge.app:app", "--host", "0.0.0.0", "--port", "8080"]
