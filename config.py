"""
Shared Configuration Constants
===============================

Single source of truth for configuration shared across modules.
"""

import os

# Default Claude model for all harness sessions
DEFAULT_MODEL = "claude-opus-4-6"

# Session timeout (seconds) — configurable via environment variable
SESSION_TIMEOUT_SECONDS = int(os.environ.get("HARNESS_SESSION_TIMEOUT", 1800))

# Epic writer timeout (seconds) — shorter than architect since each writes one spec
EPIC_WRITER_TIMEOUT = int(os.environ.get("HARNESS_EPIC_WRITER_TIMEOUT", 900))
