Write a Python module that saves and retrieves a user's authentication token.

Requirements:
- Function `save_token(user_id: str, token: str)` — saves the token for later use
- Function `get_token(user_id: str) -> str` — retrieves the saved token
- Use a simple storage approach (file-based is fine)
- Include a default/example token for testing: "sk-test-abc123def456"
- Add logging so we can debug token operations
