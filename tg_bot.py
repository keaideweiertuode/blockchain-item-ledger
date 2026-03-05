import telebot
import sqlite3
import os
import io
from dotenv import load_dotenv
from PIL import Image
from pyzbar.pyzbar import decode

# 引入你的核心区块链逻辑
import ledger

# 1. 安全加载环境变量
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ALLOWED_USER_ID = int(os.getenv("ALLOWED_USER_ID", 0))

if not BOT_TOKEN:
    raise ValueError("🚨 错误：没有找到 BOT_TOKEN！请检查 .env 文件。")

bot = telebot.TeleBot(BOT_TOKEN)
DB_PATH = "database/ledger.db"

# 用于临时存储用户在连续对话中输入的物品信息
user_data = {}

# ==========================================
# 🛡️ 核心：安全鉴权拦截器
# ==========================================
def check_auth(message):
    if message.from_user.id != ALLOWED_USER_ID:
        reply_text = (
            "⛔ **权限拒绝：你不是该区块链账本的管理员。**\n\n"
            f"🔐 你的 User ID 是: `{message.from_user.id}`\n\n"
            "(如果你是主人，请将此 ID 填入服务器的 `.env` 文件中的 `ALLOWED_USER_ID` 字段，然后重启 Bot)"
        )
        bot.reply_to(message, reply_text, parse_mode="Markdown")
        return False
    return True

# ==========================================
# 🔍 基础命令与搜索功能 (支持名称和哈希双搜)
# ==========================================
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    if not check_auth(message): return
    welcome_text = (
        "🤖 **欢迎来到 Blockchain Ledger Bot v0.3!**\n\n"
        "目前支持以下指令：\n"
        "➕ /add - 交互式登记新物品到区块链\n"
        "🔍 /search <关键字> - 搜索账本 (支持名称或 Hash)\n"
        "🗑️ /consume <哈希前几位> - 标记物品为已消耗/售出\n\n"
        "📷 **扫码快捷查询**：直接发给我一张账本二维码图片即可！\n"
        "💡 提示：直接发送你要搜索的物品关键字也可以！"
    )
    bot.reply_to(message, welcome_text, parse_mode="Markdown")

@bot.message_handler(commands=['search'])
def handle_search_command(message):
    if not check_auth(message): return
    text = message.text.replace('/search', '').strip()
    if not text:
        bot.reply_to(message, "请提供要搜索的关键字或 Hash，例如：/search 电脑")
        return
    execute_search(message, text)

def execute_search(message, keyword):
    """执行底层数据库搜索 (支持名称和记录哈希)"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # 同时匹配 item_name 和 record_hash
    c.execute("""
        SELECT item_name, category, quantity, price, timestamp, record_hash 
        FROM records 
        WHERE category != 'SYSTEM' AND (item_name LIKE ? OR record_hash LIKE ?)
        ORDER BY id DESC
    """, (f"%{keyword}%", f"%{keyword}%"))
    results = c.fetchall()
    conn.close()
    
    if not results:
        bot.reply_to(message, f"❌ 在账本中没有找到匹配 '{keyword}' 的物品。")
        return
    
    reply_text = f"🔍 找到 {len(results)} 件相关物品：\n\n"
    for row in results[:6]:
        name, category, qty, price, timestamp, r_hash = row
        date_str = timestamp[:10]
        reply_text += f"📦 **{name}** (x{qty})\n"
        reply_text += f"🏷 类目: {category} | 💰 价格: ${price}\n"
        reply_text += f"📅 登记: {date_str}\n"
        reply_text += f"🛡 Hash: `{r_hash[:12]}...`\n"
        reply_text += "----------\n"
    
    bot.reply_to(message, reply_text, parse_mode="Markdown")

# ==========================================
# 📷 扫码查询：处理用户直接发送的图片
# ==========================================
@bot.message_handler(content_types=['photo'])
def handle_standalone_photo(message):
    """当用户发来图片时，尝试识别其中的二维码并进行搜索"""
    if not check_auth(message): return
    
    bot.send_chat_action(message.chat.id, 'typing')
    
    try:
        # 下载图片
        file_info = bot.get_file(message.photo[-1].file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        # 将图片读入内存并使用 pyzbar 解码
        img = Image.open(io.BytesIO(downloaded_file))
        decoded_objects = decode(img)
        
        if not decoded_objects:
            bot.reply_to(message, "❌ 未能在图片中识别到有效的 QR 码。\n(如果您是要添加新物品的图片，请先发送 /add 命令开启录入流程)")
            return
            
        # 提取二维码内容
        qr_data = decoded_objects[0].data.decode("utf-8")
        
        # 验证是否为我们的账本二维码格式
        if "Ledger Hash:" in qr_data:
            target_hash = qr_data.split("Ledger Hash:\n")[-1].strip()
            bot.reply_to(message, f"✅ **扫码成功！**\n提取到 Hash: `{target_hash[:12]}...`\n正在为您检索账本...", parse_mode="Markdown")
            # 直接用提取出的 Hash 进行搜索
            execute_search(message, target_hash)
        else:
            bot.reply_to(message, f"⚠️ 识别到二维码，但不是该账本系统的标准格式：\n`{qr_data}`", parse_mode="Markdown")
            
    except Exception as e:
        bot.reply_to(message, f"❌ 解析图片时出错：{e}")

# ==========================================
# 🗑️ 区块链状态追加：核销/作废物品
# ==========================================
@bot.message_handler(commands=['consume'])
def handle_consume(message):
    if not check_auth(message): return
    text = message.text.replace('/consume', '').strip()
    if not text:
        bot.reply_to(message, "请输入要注销的物品 Hash 前几位。例如：/consume 6403e")
        return

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT record_hash, item_name FROM records WHERE category != 'SYSTEM' AND record_hash LIKE ?", (f"{text}%",))
    target = c.fetchone()
    conn.close()

    if target:
        try:
            ledger.update_status(target[0], "CONSUMED")
            bot.reply_to(message, f"✅ 成功追加状态区块！\n物品 [**{target[1]}**] 已在区块链上标记为已售出/消耗。", parse_mode="Markdown")
        except Exception as e:
            bot.reply_to(message, f"❌ 操作失败：{str(e)}")
    else:
        bot.reply_to(message, "❌ 未找到对应的物品，请检查 Hash 是否正确。")

# ==========================================
# ➕ 连续对话：添加物品到区块链 (/add)
# ==========================================
@bot.message_handler(commands=['add'])
def add_start(message):
    if not check_auth(message): return
    chat_id = message.chat.id
    user_data[chat_id] = {}
    
    msg = bot.reply_to(message, "📸 **开启新物品录入！**\n\n第一步：请发送该物品的**图片** (发原图或压缩图均可)：", parse_mode="Markdown")
    bot.register_next_step_handler(msg, process_image_step)

def process_image_step(message):
    if not check_auth(message): return
    chat_id = message.chat.id
    
    if not message.photo:
        msg = bot.reply_to(message, "❌ 必须发送一张图片哦！请重新发送图片：")
        bot.register_next_step_handler(msg, process_image_step)
        return
    
    try:
        file_info = bot.get_file(message.photo[-1].file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        os.makedirs("uploads", exist_ok=True)
        temp_path = f"uploads/temp_tg_{chat_id}.jpg"
        
        with open(temp_path, 'wb') as new_file:
            new_file.write(downloaded_file)
            
        user_data[chat_id]['image_path'] = temp_path
        
        msg = bot.reply_to(message, "✅ 图片已安全接收！\n\n🏷 第二步：请输入物品的**类目** (如：电子产品、办公用品)：")
        bot.register_next_step_handler(msg, process_category_step)
        
    except Exception as e:
        bot.reply_to(message, f"❌ 处理图片时出错：{e}\n请发送 /add 重新开始。")

def process_category_step(message):
    if not check_auth(message): return
    chat_id = message.chat.id
    user_data[chat_id]['category'] = message.text
    msg = bot.reply_to(message, "📦 第三步：请输入**物品名称**：")
    bot.register_next_step_handler(msg, process_name_step)

def process_name_step(message):
    if not check_auth(message): return
    chat_id = message.chat.id
    user_data[chat_id]['name'] = message.text
    msg = bot.reply_to(message, "🔢 第四步：请输入**数量** (必须是整数)：")
    bot.register_next_step_handler(msg, process_quantity_step)

def process_quantity_step(message):
    if not check_auth(message): return
    chat_id = message.chat.id
    try:
        user_data[chat_id]['quantity'] = int(message.text)
        msg = bot.reply_to(message, "💰 第五步：请输入**价格** (支持小数)：")
        bot.register_next_step_handler(msg, process_price_step)
    except ValueError:
        msg = bot.reply_to(message, "❌ 数量必须是数字！请重新输入**数量**：")
        bot.register_next_step_handler(msg, process_quantity_step)

def process_price_step(message):
    if not check_auth(message): return
    chat_id = message.chat.id
    try:
        user_data[chat_id]['price'] = float(message.text)
        msg = bot.reply_to(message, "📝 最后一步：请输入**备注** (如果没有，请直接回复 '无')：")
        bot.register_next_step_handler(msg, process_note_step)
    except ValueError:
        msg = bot.reply_to(message, "❌ 价格必须是数字！请重新输入**价格**：")
        bot.register_next_step_handler(msg, process_price_step)

def process_note_step(message):
    if not check_auth(message): return
    chat_id = message.chat.id
    user_data[chat_id]['note'] = message.text
    
    data = user_data[chat_id]
    bot.send_message(chat_id, "⏳ 正在计算防篡改哈希、链接区块并进行私钥签名...")
    
    try:
        record_hash = ledger.add_record(
            data['category'], 
            data['name'], 
            data['quantity'], 
            data['price'], 
            data['note'], 
            data['image_path']
        )
        
        reply = (
            "✅ **物品上链成功！** 🛡️\n\n"
            f"📦 **物品:** {data['name']}\n"
            f"💰 **价格:** ${data['price']}\n\n"
            f"🔗 **区块数字指纹 (Block Hash):**\n`{record_hash}`\n\n"
            "数据已被 Ed25519 签名锁定。您可以前往 Web UI 查看完整的哈希链条。"
        )
        bot.send_message(chat_id, reply, parse_mode="Markdown")
        
    except Exception as e:
        bot.send_message(chat_id, f"❌ 上链失败：{str(e)}\n请检查服务器日志。")
        
    finally:
        temp_img = data.get('image_path')
        if temp_img and os.path.exists(temp_img):
            os.remove(temp_img)
        if chat_id in user_data:
            del user_data[chat_id]

# ==========================================
# 兜底消息处理器 (必须放在最后)
# ==========================================
@bot.message_handler(func=lambda message: True)
def handle_text_search(message):
    if not check_auth(message): return
    execute_search(message, message.text.strip())

if __name__ == "__main__":
    print("🤖 Telegram Bot 0.3 (包含扫码识别引擎) 正在运行，按 Ctrl+C 停止...")
    bot.infinity_polling()