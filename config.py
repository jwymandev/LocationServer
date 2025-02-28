# config.py
import os
import ssl
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

def get_db_config():
    """Return database configuration from environment variables."""
    return {
        'host': os.getenv('DB_HOST'),
        'port': int(os.getenv('DB_PORT', 5432)),
        'database': os.getenv('DB_NAME'),
        'user': os.getenv('DB_USER'),
        'password': os.getenv('DB_PASSWORD')
    }

def get_ssl_context():
    """Create and return SSL context for database connections."""
    ca_cert_content = os.getenv('DB_CA_CERT')
    if not ca_cert_content:
        raise Exception("Missing required environment variable: DB_CA_CERT")
    
    ssl_context = ssl.create_default_context(cadata=ca_cert_content)
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    
    return ssl_context

def get_api_key():
    """Get API key from environment variables."""
    api_key = os.getenv("API_KEY")
    if not api_key:
        raise Exception("Missing required environment variable: API_KEY")
    return api_key

def derive_encryption_key():
    """Derive encryption key from environment variable."""
    key = os.getenv('ENCRYPTION_KEY')
    if not key:
        raise Exception("Missing required environment variable: ENCRYPTION_KEY")
    
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"static_salt",  # Consider making this configurable
        iterations=100000
    )
    return kdf.derive(key.encode())

def get_rocketchat_base_url():
    """Get Rocket.Chat base URL from environment variables."""
    base_url = os.getenv("ROCKETCHAT_BASE_URL")
    if not base_url:
        raise Exception("Missing required environment variable: ROCKETCHAT_BASE_URL")
    return base_url