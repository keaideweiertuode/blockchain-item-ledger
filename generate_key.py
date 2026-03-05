from nacl.signing import SigningKey
import os

os.makedirs("keys", exist_ok=True)

signing_key = SigningKey.generate()
verify_key = signing_key.verify_key

with open("keys/private.key", "wb") as f:
    f.write(signing_key.encode())

with open("keys/public.key", "wb") as f:
    f.write(verify_key.encode())

print("Keys generated")