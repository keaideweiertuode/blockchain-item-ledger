import os
import sqlite3
import hashlib
import shutil
from datetime import datetime
from nacl.signing import SigningKey

DB_PATH = "database/ledger.db"
IMAGE_DIR = "images"
PRIVATE_KEY_PATH = "keys/private.key"

os.makedirs(IMAGE_DIR, exist_ok=True)

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

def add_record(category, name, quantity, price, note, image_path):
    timestamp = datetime.utcnow().isoformat()
    image_hash = sha256_file(image_path)

    # 复制图片并重命名为hash
    new_image_path = f"{IMAGE_DIR}/{image_hash}.jpg"
    if not os.path.exists(new_image_path):
        shutil.copy(image_path, new_image_path)

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # 获取上一条记录的哈希，如果为空说明是创世区块 (Genesis Block)
    c.execute("SELECT record_hash FROM records ORDER BY id DESC LIMIT 1")
    last_record = c.fetchone()
    previous_hash = last_record[0] if last_record else "0" * 64

    # 组合当前数据并计算 record_hash (加入 previous_hash)
    record_data = f"{timestamp}{category}{name}{quantity}{price}{note}{image_hash}{previous_hash}"
    record_hash = sha256_text(record_data)

    # 签名
    with open(PRIVATE_KEY_PATH, "rb") as f:
        signing_key = SigningKey(f.read())
    signature = signing_key.sign(record_hash.encode()).signature.hex()

    # 插入数据库
    c.execute("""
    INSERT INTO records 
    (timestamp, category, item_name, quantity, price, note, 
     image_hash, previous_hash, record_hash, signature)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (timestamp, category, name, quantity, price, note, image_hash, previous_hash, record_hash, signature))

    conn.commit()
    conn.close()
    return record_hash