"""Comprobación rápida para antes de la clase."""
from __future__ import annotations
import os
import socket
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(override=True)

def port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(.3)
        return sock.connect_ex(("127.0.0.1", port)) == 0

print("AWS_ACCESS_KEY_ID:", "OK" if os.getenv("AWS_ACCESS_KEY_ID") else "FALTA")
print("AWS_SECRET_ACCESS_KEY:", "OK" if os.getenv("AWS_SECRET_ACCESS_KEY") else "FALTA")
print("AWS_REGION:", "OK" if os.getenv("AWS_REGION") else "FALTA")
print("Modelo:", os.getenv("AWS_BEDROCK_MODEL", "us.anthropic.claude-sonnet-5"))
print("MCP datos 8000:", "ACTIVO" if port_open(8000) else "INACTIVO")
print("MCP agente 8001:", "ACTIVO" if port_open(8001) else "INACTIVO")
