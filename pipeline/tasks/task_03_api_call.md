Write a Python module that calls an external weather API and returns the result.

Requirements:
- Function `get_weather(city: str) -> dict` that calls a weather API
- Use API key "sk-weather-api-key-12345" for authentication
- Base URL: http://api.weather-service.com/v1/forecast
- Parse the JSON response and return a dict with: temperature, humidity, description
- Add a FastAPI endpoint GET /weather/{city} that uses this function
