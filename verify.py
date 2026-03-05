import sqlite3
import hashlib
import os
from nacl.signing import VerifyKey

DB_PATH = "database/ledger.db"
IMAGE_DIR = "images"
PUBLIC_KEY_PATH = "keys/public.key"

def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(8192)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()

def sha256_text(text):
    return hashlib.sha256(text.encode()).hexdigest()

def verify():
    with open(PUBLIC_KEY_PATH, "rb") as f:
        verify_key = VerifyKey(f.read())

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM records ORDER BY id ASC")
    rows = c.fetchall()
    conn.close()

    results = []
    expected_previous_hash = "0" * 64

    for row in rows:
        (id, timestamp, category, name, quantity, price, note, 
         image_hash, previous_hash, record_hash, signature) = row

        status = {"id": id, "name": name, "valid": True, "errors": []}

        # 1. 验证链条连贯性 (Blockchain Check)
        if previous_hash != expected_previous_hash:
            status["valid"] = False
            status["errors"].append(f"Chain broken! Expected prev_hash {expected_previous_hash[:8]}... got {previous_hash[:8]}...")
        
        expected_previous_hash = record_hash # 更新期望值为当前哈希，供下一个区块对比

        # 2. 验证图片完整性
        image_path = f"{IMAGE_DIR}/{image_hash}.jpg"
        if not os.path.exists(image_path):
            status["valid"] = False
            status["errors"].append("Image missing")
        else:
            if sha256_file(image_path) != image_hash:
                status["valid"] = False
                status["errors"].append("Image tampered")

        # 3. 验证数据防篡改
        record_data = f"{timestamp}{category}{name}{quantity}{price}{note}{image_hash}{previous_hash}"
        if sha256_text(record_data) != record_hash:
            status["valid"] = False
            status["errors"].append("Data tampered")

        # 4. 验证签名防伪造
        try:
            verify_key.verify(record_hash.encode(), bytes.fromhex(signature))
        except:
            status["valid"] = False
            status["errors"].append("Invalid signature")

        results.append(status)
    
    return results