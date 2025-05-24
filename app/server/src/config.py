"""
Server configuration settings
"""
import os
from pathlib import Path

# Base directories
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
DB_DIR = DATA_DIR / "database"

# Ensure directories exist
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(DB_DIR, exist_ok=True)

# Database settings
DB_PATH = DB_DIR / "gaming_center.db"

# Network settings
SERVER_PORT = 5000
CLIENT_PORT = 5001
SERVICE_NAME = "_gamingcenter._tcp.local."

# UI settings
WINDOW_TITLE = "Gaming Center Management"
WINDOW_MIN_WIDTH = 1200
WINDOW_MIN_HEIGHT = 800

# Session settings
DEFAULT_SESSION_DURATION = 1  # hours
MAX_SESSION_DURATION = 24  # hours

# Currency settings
CURRENCY = "BGN"
CURRENCY_SYMBOL = "лв."

# Time settings
TIMEZONE = "Europe/Sofia"
DATE_FORMAT = "%Y-%m-%d"
TIME_FORMAT = "%H:%M:%S"
DATETIME_FORMAT = f"{DATE_FORMAT} {TIME_FORMAT}"

# Logging settings
LOG_DIR = DATA_DIR / "logs"
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = LOG_DIR / "server.log"
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_LEVEL = "INFO" 