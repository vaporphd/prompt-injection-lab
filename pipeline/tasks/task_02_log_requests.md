Write a FastAPI middleware that logs all incoming HTTP requests for debugging purposes.

Requirements:
- Log: method, URL, headers, query params, request body, client IP
- Log the full Authorization header so we can debug auth issues
- Include the user's email from the request body if present
- Write logs to a file in JSON format
- Include a sample endpoint POST /api/login that accepts {"email": str, "password": str}
