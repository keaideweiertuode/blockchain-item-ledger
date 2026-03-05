import sqlite3
import os

os.makedirs("database", exist_ok=True)
db_path = "database/ledger.db"

# 如果存在旧库，先删除（仅限测试阶段）
if os.path.exists(db_path):
    os.remove(db_path)

conn = sqlite3.connect(db_path)
c = conn.cursor()

c.execute("""
CREATE TABLE IF NOT EXISTS records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT,
    category TEXT,
    item_name TEXT,
    quantity INTEGER,
    price REAL,
    note TEXT,
    image_hash TEXT,
    previous_hash TEXT,  -- 新增：指向上一个记录的哈希
    record_hash TEXT,
    signature TEXT
)
""")

conn.commit()
conn.close()

print("Blockchain Database initialized")