from flask import Flask, render_template, request, redirect, flash, send_from_directory
import os
import sqlite3
import ledger
import verify
import math
import io
import csv
from flask import Response

app = Flask(__name__)
app.secret_key = "super_secret_key" # 用于 flash 消息，生产环境中请换成随机复杂字符串
DB_PATH = "database/ledger.db"
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def get_records(search_query="", category_filter="", page=1, per_page=6):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # 基础查询语句
    query = "SELECT * FROM records WHERE 1=1"
    count_query = "SELECT COUNT(*) FROM records WHERE 1=1"
    params = []

    # 处理过滤条件
    if category_filter:
        query += " AND category = ?"
        count_query += " AND category = ?"
        params.append(category_filter)

    if search_query:
        query += " AND item_name LIKE ?"
        count_query += " AND item_name LIKE ?"
        params.append(f"%{search_query}%")

    # 1. 计算总记录数，用于判断总页数
    c.execute(count_query, params)
    total_records = c.fetchone()[0]
    total_pages = math.ceil(total_records / per_page) if total_records > 0 else 1

    # 2. 加入分页限制 (LIMIT 和 OFFSET)
    query += " ORDER BY id DESC LIMIT ? OFFSET ?"
    offset = (page - 1) * per_page
    params.extend([per_page, offset])

    c.execute(query, params)
    rows = c.fetchall()
    conn.close()
    
    return rows, total_pages

def get_categories():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # 获取所有不为空的不重复类目
    c.execute("SELECT DISTINCT category FROM records WHERE category IS NOT NULL AND category != ''")
    categories = [row[0] for row in c.fetchall()]
    conn.close()
    return categories

@app.route("/")
def index():
    # 获取 URL 参数，page 默认为 1
    search = request.args.get("search", "")
    category = request.args.get("category", "")
    page = request.args.get("page", 1, type=int)
    per_page = 6
    
    # 获取当页数据和总页数
    records, total_pages = get_records(search, category, page, per_page)
    categories = get_categories()
    
    return render_template(
        "index.html", 
        records=records, 
        categories=categories, 
        current_search=search, 
        current_category=category,
        current_page=page,
        total_pages=total_pages
    )

@app.route("/add", methods=["POST"])
def add():
    category = request.form["category"]
    name = request.form["name"]
    quantity = int(request.form["quantity"])
    price = float(request.form["price"])
    note = request.form["note"]
    
    # 处理图片上传
    if "image" not in request.files:
        flash("No image uploaded!", "danger")
        return redirect("/")
        
    file = request.files["image"]
    if file.filename == "":
        flash("No selected file", "danger")
        return redirect("/")

    temp_path = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(temp_path)

    try:
        # 调用区块链写入逻辑
        record_hash = ledger.add_record(category, name, quantity, price, note, temp_path)
        flash(f"Item registered successfully! Hash: {record_hash[:16]}...", "success")
    except Exception as e:
        flash(f"Error: {str(e)}", "danger")
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path) # 清理临时文件

    return redirect("/")

@app.route("/verify_chain")
def verify_chain():
    results = verify.verify()
    # 检查是否有任何错误
    all_valid = all(r["valid"] for r in results)
    if all_valid:
        flash("Blockchain verified! All records are safe and untampered.", "success")
    else:
        for r in results:
            if not r["valid"]:
                flash(f"Record {r['id']} ({r['name']}) is COMPROMISED: {', '.join(r['errors'])}", "danger")
    return redirect("/")

@app.route("/export")
def export_csv():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # 按 ID 升序导出，符合时间的先后顺序
    c.execute("SELECT * FROM records ORDER BY id ASC")
    rows = c.fetchall()
    
    # 获取数据库的列名（表头）
    column_names = [description[0] for description in c.description]
    conn.close()

    # 在内存中创建 CSV
    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow(column_names) # 写入表头
    cw.writerows(rows)        # 写入数据
    
    output = si.getvalue()
    
    # 返回并触发浏览器下载
    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=ledger_export.csv"}
    )

@app.route("/images/<filename>")
def get_image(filename):
    return send_from_directory("images", filename)

if __name__ == "__main__":
    app.run(debug=True, port=5000)