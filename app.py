from flask import Flask, render_template, request, redirect, flash, send_from_directory, Response, send_file
import os
import sqlite3
import ledger
import verify
import math
import io
import csv
import qrcode

app = Flask(__name__)
app.secret_key = "super_secret_key"
DB_PATH = "database/ledger.db"
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def get_records(search_query="", category_filter="", page=1, per_page=6):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # 过滤掉系统状态区块
    query = "SELECT * FROM records WHERE category != 'SYSTEM'"
    count_query = "SELECT COUNT(*) FROM records WHERE category != 'SYSTEM'"
    params = []

    if category_filter:
        query += " AND category = ?"
        count_query += " AND category = ?"
        params.append(category_filter)
    if search_query:
        # 💡 修改点：用括号把 OR 逻辑包起来，同时匹配名称或哈希
        query += " AND (item_name LIKE ? OR record_hash LIKE ?)"
        count_query += " AND (item_name LIKE ? OR record_hash LIKE ?)"
        params.extend([f"%{search_query}%", f"%{search_query}%"])
        
    c.execute(count_query, params)
    total_records = c.fetchone()[0]
    total_pages = math.ceil(total_records / per_page) if total_records > 0 else 1

    query += " ORDER BY id DESC LIMIT ? OFFSET ?"
    params.extend([per_page, (page - 1) * per_page])
    c.execute(query, params)
    rows = c.fetchall()
    conn.close()
    return rows, total_pages

def get_categories():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT DISTINCT category FROM records WHERE category IS NOT NULL AND category != '' AND category != 'SYSTEM'")
    categories = [row[0] for row in c.fetchall()]
    conn.close()
    return categories

def get_dashboard_data():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM records")
    all_records = c.fetchall()
    conn.close()

    # 💡 修复点：这里必须重新初始化这个集合，否则 Pylance 会报错
    consumed_hashes = set()
    for r in all_records:
        # 💡 修复点：确保使用的是 item_name
        if r["category"] == "SYSTEM" and r["item_name"] == "STATUS_UPDATE" and "[CONSUMED]" in r["note"]:
            target = r["note"].split("[CONSUMED] ")[1].strip()
            consumed_hashes.add(target)

    total_value = 0
    total_items = 0
    for r in all_records:
        if r["category"] == "SYSTEM" or r["record_hash"] in consumed_hashes:
            continue
        total_value += r["quantity"] * r["price"]
        total_items += r["quantity"]

    return {"total_value": total_value, "total_items": total_items, "consumed_hashes": consumed_hashes}

@app.route("/")
def index():
    search = request.args.get("search", "")
    category = request.args.get("category", "")
    page = request.args.get("page", 1, type=int)
    
    records, total_pages = get_records(search, category, page, per_page=6)
    categories = get_categories()
    dash_data = get_dashboard_data()
    
    return render_template(
        "index.html", records=records, categories=categories, 
        current_search=search, current_category=category,
        current_page=page, total_pages=total_pages, dash_data=dash_data
    )

@app.route("/add", methods=["POST"])
def add():
    category = request.form["category"]
    name = request.form["name"]
    quantity = int(request.form["quantity"])
    price = float(request.form["price"])
    note = request.form["note"]
    
    file = request.files.get("image")
    if not file or file.filename == "":
        flash("Image is required!", "danger")
        return redirect("/")

    temp_path = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(temp_path)

    try:
        record_hash = ledger.add_record(category, name, quantity, price, note, temp_path)
        flash(f"Item registered! Hash: {record_hash[:16]}...", "success")
    except Exception as e:
        flash(f"Error: {str(e)}", "danger")
    finally:
        if os.path.exists(temp_path): os.remove(temp_path)

    return redirect("/")

@app.route("/consume/<record_hash>", methods=["POST"])
def consume_item(record_hash):
    try:
        ledger.update_status(record_hash, "CONSUMED")
        flash("✅ Item status updated to Sold/Consumed in the blockchain!", "success")
    except Exception as e:
        flash(f"Error: {str(e)}", "danger")
    return redirect("/")

@app.route("/qr/<record_hash>")
def generate_qr(record_hash):
    img = qrcode.make(f"Ledger Hash:\n{record_hash}")
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return send_file(buf, mimetype='image/png')

@app.route("/export")
def export_csv():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM records ORDER BY id ASC")
    rows = c.fetchall()
    column_names = [description[0] for description in c.description]
    conn.close()

    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow(column_names)
    cw.writerows(rows)
    return Response(si.getvalue(), mimetype="text/csv", headers={"Content-Disposition": "attachment;filename=ledger.csv"})

@app.route("/verify_chain")
def verify_chain():
    results = verify.verify()
    if all(r["valid"] for r in results):
        flash("Blockchain verified! All records are safe and untampered.", "success")
    else:
        for r in results:
            if not r["valid"]: flash(f"Record {r['id']} COMPROMISED: {', '.join(r['errors'])}", "danger")
    return redirect("/")

@app.route("/images/<filename>")
def get_image(filename):
    return send_from_directory("images", filename)

if __name__ == "__main__":
    app.run(debug=True, port=5000)