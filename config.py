"""
Shared Configuration Constants
===============================

Single source of truth for configuration shared across modules.
"""

import os

# Default Claude model for all harness sessions
DEFAULT_MODEL = "claude-opus-4-5-20251101"

# Session timeout (seconds) — configurable via environment variable
SESSION_TIMEOUT_SECONDS = int(os.environ.get("HARNESS_SESSION_TIMEOUT", 1800))
