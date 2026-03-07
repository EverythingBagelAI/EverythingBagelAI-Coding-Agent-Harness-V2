"""
Linear Configuration
====================

Centralised Linear API key retrieval and shared constants.
"""

import os


def get_linear_api_key() -> str:
    """Retrieve the Linear API key from environment, raising a clear error if missing."""
    key = os.environ.get("LINEAR_API_KEY", "")
    if not key:
        raise EnvironmentError(
            "LINEAR_API_KEY environment variable is not set. "
            "Get your key from Linear Settings → API."
        )
    return key
