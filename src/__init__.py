"""
Telegram Bot Package - AI-powered multi-account Telegram management system.

Modules:
  - database: SQLite database management and schema
  - config: Configuration loading and validation
"""

__version__ = "1.0.19"
__author__ = "Adrian"

import logging

# Configure package-level logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

# Export main classes
from .database import DatabaseManager, initialize_database_with_defaults
from .config import ConfigManager, get_config

__all__ = [
    'DatabaseManager',
    'initialize_database_with_defaults',
    'ConfigManager',
    'get_config',
]
