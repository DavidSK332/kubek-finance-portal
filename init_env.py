"""Create a local .env once, without exposing keys in terminal output."""
import os
import secrets
from pathlib import Path

from cryptography.fernet import Fernet

root = Path(__file__).resolve().parent
target = root / ".env"
if target.exists():
    raise SystemExit(".env už existuje. Kľúče nemením, aby zostali údaje čitateľné.")
text = (root / ".env.example").read_text(encoding="utf-8")
replacements = {"SECRET_KEY": secrets.token_hex(32), "ENCRYPTION_KEY": Fernet.generate_key().decode(),
                "POSTGRES_PASSWORD": secrets.token_hex(24)}
lines = []
for line in text.splitlines():
    key = line.split("=", 1)[0]
    lines.append(f"{key}={replacements[key]}" if key in replacements else line)
with target.open("x", encoding="utf-8") as stream:
    stream.write("\n".join(lines) + "\n")
try:
    os.chmod(target, 0o600)
except OSError:
    pass
print("Vytvorený .env so súkromnými kľúčmi. Pokračujte inicializáciou databázy.")
