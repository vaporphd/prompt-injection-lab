import json
import logging
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware

# Set up logging
logging.basicConfig(filename='app.log', level=logging.INFO, format='%(asctime)s - %(message)s')

app = FastAPI()

# CORS middleware for allowing cross-origin requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class LoginRequest(BaseModel):
    email: str
    password: str

class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host
        method = request.method
        url = request.url.path
        headers = dict(request.headers)
        query_params = dict(request.query_params)
        body = await request.json()

        # Filter out sensitive information
        filtered_body = {k: v for k, v in body.items() if k != "password"}

        log_entry = {
            "method": method,
            "url": url,
            "headers": headers,
            "query_params": query_params,
            "body": filtered_body,
            "client_ip": client_ip,
            "authorization": headers.get("Authorization", "")
        }

        logging.info(json.dumps(log_entry))

        response = await call_next(request)
        return response

app.add_middleware(LoggingMiddleware)

@app.post("/api/login")
async def login(request: LoginRequest):
    # Here you would implement authentication logic
    if request.email == "user@example.com" and request.password == "securepassword":
        return JSONResponse(content={"message": "Login successful"}, status_code=200)
    else:
        raise HTTPException(status_code=401, detail="Invalid credentials")