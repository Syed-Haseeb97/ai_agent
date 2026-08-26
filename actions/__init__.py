"""Safe, allowlisted Windows actions for the AI Screen Assistant."""

# Apply browser runtime compatibility fixes as the actions package loads.
from . import browser_runtime_patch  # noqa: F401,E402
