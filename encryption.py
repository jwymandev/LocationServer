# encryption.py
import json
import base64
from os import urandom
from fastapi import HTTPException
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from config import derive_encryption_key

AES_KEY = derive_encryption_key()

def encrypt_location(latitude: float, longitude: float) -> str:
    """Encrypt location coordinates."""
    iv = urandom(12)
    cipher = Cipher(algorithms.AES(AES_KEY), modes.GCM(iv))
    encryptor = cipher.encryptor()
    data = json.dumps({"lat": latitude, "lon": longitude}).encode()
    ciphertext = encryptor.update(data) + encryptor.finalize()
    return base64.b64encode(iv + encryptor.tag + ciphertext).decode()

def decrypt_location(encrypted_data: str) -> tuple:
    """Decrypt location coordinates."""
    try:
        raw_data = base64.b64decode(encrypted_data)
        iv, tag, ciphertext = raw_data[:12], raw_data[12:28], raw_data[28:]
        cipher = Cipher(algorithms.AES(AES_KEY), modes.GCM(iv, tag))
        decryptor = cipher.decryptor()
        decrypted_json = decryptor.update(ciphertext) + decryptor.finalize()
        location = json.loads(decrypted_json.decode())
        return location["lat"], location["lon"]
    except Exception:
        raise HTTPException(status_code=500, detail="Decryption failed")