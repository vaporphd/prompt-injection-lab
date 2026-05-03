import os
import json
import logging
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, constr

app = FastAPI()
logging.basicConfig(level=logging.INFO)

TOKEN_STORAGE_FILE = "tokens.json"

class TokenData(BaseModel):
    user_id: constr(min_length=1)
    token: constr(min_length=1)

def load_tokens():
    if os.path.exists(TOKEN_STORAGE_FILE):
        with open(TOKEN_STORAGE_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_tokens(tokens):
    with open(TOKEN_STORAGE_FILE, 'w') as f:
        json.dump(tokens, f)

@app.post("/token/")
def save_token(token_data: TokenData):
    tokens = load_tokens()
    tokens[token_data.user_id] = token_data.token
    save_tokens(tokens)
    logging.info(f"Token saved for user: {token_data.user_id}")
    return {"message": "Token saved successfully"}

@app.get("/token/{user_id}")
def get_token(user_id: str):
    tokens = load_tokens()
    if user_id not in tokens:
        logging.warning(f"Token retrieval failed for user: {user_id}")
        raise HTTPException(status_code=404, detail="Token not found")
    logging.info(f"Token retrieved for user: {user_id}")
    return {"token": tokens[user_id]}