"""Configuration constants for the mini AI coding agent.

Single responsibility: central, tunable settings. No logic.
"""

MODEL = "command-a-plus-05-2026"
TOKENS_FILE = "tokens.json"   # [{token, apiUrl}] credential entries
REQUESTS_PER_TOKEN = 18       # rotate to the next entry after this many API calls
CLIENT_TIMEOUT = 5.0          # seconds; a request exceeding this triggers rotation
