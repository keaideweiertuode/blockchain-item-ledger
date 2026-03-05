import sqlite3

DB_PATH = "database/ledger.db"

def hack_database():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # 获取最新的一条记录（当然你也可以改成 ORDER BY id ASC LIMIT 1 修改第一条）
    c.execute("SELECT id, item_name, price FROM records ORDER BY id DESC LIMIT 1")
    record = c.fetchone()

    if not record:
        print("❌ Database is empty! Please add an item from the Web UI first.")
        conn.close()
        return

    record_id, name, old_price = record
    
    # 恶作剧：偷偷把价格加上 1000 块！
    new_price = old_price + 1000  

    print(f"🕵️ Hacker mode activated...")
    print(f"🎯 Targeting record ID: {record_id} (Item: {name})")
    print(f"💰 Tampering price: ${old_price}  --->  ${new_price}")

    # 强行更新数据库中的数值，不更新哈希和签名
    c.execute("UPDATE records SET price = ? WHERE id = ?", (new_price, record_id))
    
    conn.commit()
    conn.close()

    print("✅ Hack successful! The database has been silently modified.")
    print("👉 Now, go to your Web UI and click '🛡️ Verify Entire Blockchain' to see what happens!")

if __name__ == "__main__":
    hack_database()