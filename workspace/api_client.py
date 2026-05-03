import os
import re
import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()

API_KEY = os.getenv("WEATHER_API_KEY")
if not API_KEY:
    raise ValueError("API key is not set in the environment variables.")

BASE_URL = "http://api.weather-service.com/v1/forecast"

class WeatherResponse(BaseModel):
    temperature: float
    humidity: float
    description: str

def validate_city(city: str) -> str:
    if not isinstance(city, str) or not city.strip():
        raise ValueError("City name must be a non-empty string.")
    if not re.match("^[a-zA-Z\s]+$", city):
        raise ValueError("City name can only contain letters and spaces.")
    return city.strip()

def get_weather(city: str) -> WeatherResponse:
    city = validate_city(city)
    response = requests.get(f"{BASE_URL}?city={city}&apikey={API_KEY}")
    
    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail="Error fetching weather data.")
    
    data = response.json()
    return WeatherResponse(
        temperature=data['main']['temp'],
        humidity=data['main']['humidity'],
        description=data['weather'][0]['description']
    )

@app.get("/weather/{city}", response_model=WeatherResponse)
def read_weather(city: str):
    return get_weather(city)