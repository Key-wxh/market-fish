"""
小溪 Unified Server — Flask on :8600
Merges: CEO Dashboard (was :8600 http.server) + 小溪 API (was :8602 Flask)

Routes (order matters! special → generic):
  GET  /                          → CEO Dashboard (template.html + dashboard_data.json)
  GET  /api/summary               → Today's summary
  GET  /api/stats                 → Detailed stats
  GET  /api/trends/<table>        → Trend data
  GET  /api/dashboard             → dashboard_data.json
  GET  /api/messages              → Message board GET
  POST /api/messages              → Message board POST
  GET  /api/insights              → AI insights
  GET|POST /api/<table>           → Generic CRUD (finance/health/life/work/contacts/knowledge/goals)
  DELETE /api/<table>/<id>       → Delete row
  GET  /app/<page>.html           → App WebView pages (from dashboard/app/)
  GET  /app/assets/<file>         → Static assets (CSS/JS)
  GET  /proto/<path>              → Legacy prototype files
  GET  /<path>.html               → Dashboard standalone HTML files
"""
import json
import sqlite3
import os
import sys
import hmac
import hashlib
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from functools import wraps

# Load .env before anything else (manual parse — PM2 doesn't pass env)
_env_path = Path(__file__).parent.parent / ".env"
if _env_path.exists():
    for _line in _env_path.read_text().strip().split("\n"):
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ[_k.strip()] = _v.strip().strip('"').strip("'")

from flask import Flask, request, jsonify, send_from_directory

# ── Config ──
BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR))  # 确保 engine 模块可导入
DB_PATH = str(BASE_DIR / "data_lake" / "xiaoxi.db")
DASHBOARD_DIR = str(BASE_DIR / "dashboard")
APP_DIR = str(BASE_DIR / "dashboard" / "app")
DATA_PATH = BASE_DIR / "dashboard" / "dashboard_data.json"
TPL_PATH = BASE_DIR / "dashboard" / "template.html"
MSG_PATH = BASE_DIR / "dashboard" / "messages.json"
TZ = timezone(timedelta(hours=8))

ALLOWED_TABLES = ['finance', 'health', 'life', 'work', 'contacts', 'knowledge', 'goals']

# ── Finance v2 Auth Config ──
FINANCE_SECRET = os.environ.get('FINANCE_SECRET', 'keystart-finance-2026')
ADMIN_PASSWORD = 'Key2026MF!'
ADMIN_PASSWORD_HASH = hashlib.sha256(ADMIN_PASSWORD.encode()).hexdigest()
TOKEN_TTL = 86400  # 24 hours

app = Flask(__name__)

# ── DB Helpers ──
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def init_db():
    db = get_db()
    db.executescript("""
        CREATE TABLE IF NOT EXISTS finance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL,
            category TEXT,
            amount REAL NOT NULL,
            note TEXT,
            contact TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS health (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            htype TEXT NOT NULL,
            subtype TEXT,
            value TEXT,
            note TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS life (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ltype TEXT NOT NULL,
            content TEXT,
            tags TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS work (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wtype TEXT NOT NULL,
            name TEXT,
            status TEXT,
            revenue REAL DEFAULT 0,
            cost REAL DEFAULT 0,
            note TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            relationship TEXT,
            last_contact TEXT,
            notes TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS knowledge (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ktype TEXT NOT NULL,
            title TEXT,
            content TEXT,
            tags TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS goals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            target TEXT,
            progress TEXT,
            year INTEGER,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE INDEX IF NOT EXISTS idx_finance_date ON finance(created_at);
        CREATE INDEX IF NOT EXISTS idx_health_date ON health(created_at);
        CREATE INDEX IF NOT EXISTS idx_life_date ON life(created_at);

        -- Finance v2 tables
        CREATE TABLE IF NOT EXISTS entities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            type TEXT DEFAULT 'company',
            tax_id TEXT,
            notes TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS fixed_costs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity TEXT NOT NULL,
            product TEXT,
            item TEXT NOT NULL,
            amount REAL NOT NULL,
            currency TEXT DEFAULT 'CNY',
            billing_cycle TEXT DEFAULT 'monthly',
            next_bill_date TEXT,
            is_active INTEGER DEFAULT 1,
            notes TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS cost_sync_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sync_date TEXT NOT NULL,
            source_file TEXT NOT NULL,
            records_created INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            UNIQUE(sync_date, source_file)
        );
    """)
    db.commit()
    db.close()

def list_table(table, limit=100):
    db = get_db()
    rows = db.execute(f"SELECT * FROM {table} ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    db.close()
    return [dict(r) for r in rows]

def insert_row(table, data):
    db = get_db()
    cols = ', '.join(data.keys())
    placeholders = ', '.join(['?' for _ in data])
    db.execute(f"INSERT INTO {table} ({cols}) VALUES ({placeholders})", list(data.values()))
    db.commit()
    row_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    db.close()
    return row_id

# ── Message Board Helpers ──
def load_msgs():
    if MSG_PATH.exists():
        return json.loads(MSG_PATH.read_text())
    return {"messages": []}

def save_msgs(msgs):
    MSG_PATH.write_text(json.dumps(msgs, ensure_ascii=False, indent=2))

# ═══════════════════════════════════════════
# Dashboard Route (was :8600)
# ═══════════════════════════════════════════

@app.route('/')
@app.route('/index.html')
def dashboard():
    """CEO Dashboard — inject dashboard_data.json into template.html"""
    try:
        data_json = DATA_PATH.read_text()
    except FileNotFoundError:
        data_json = '{"generated_at":"no data","sections":{}}'
    if TPL_PATH.exists():
        html = TPL_PATH.read_text(encoding="utf-8").replace("__DATA_PLACEHOLDER__", data_json)
    else:
        html = f"<html><body><h1>Keystart AI</h1><pre>{data_json}</pre></body></html>"
    return html, 200, {"Content-Type": "text/html; charset=utf-8"}

# ── Market Intel ──
INTEL_PATH = BASE_DIR / "data_lake" / "gold" / "market_intel.html"

@app.route('/intel')
def market_intel():
    """Market intelligence daily report"""
    try:
        html = INTEL_PATH.read_text(encoding="utf-8")
        return html, 200, {"Content-Type": "text/html; charset=utf-8"}
    except FileNotFoundError:
        return "<h1>市场情报</h1><p>今日报告尚未生成，请稍后再试。</p>", 200

# ═══════════════════════════════════════════
# Message Board Routes
# ═══════════════════════════════════════════

@app.route('/api/messages', methods=['GET'])
def get_messages():
    msgs = load_msgs()
    return jsonify(msgs)

@app.route('/api/messages', methods=['POST'])
def post_message():
    data = request.get_json() or {}
    text = data.get('text', '').strip()
    author = data.get('author', 'CEO')
    if not text:
        return jsonify({"error": "empty"}), 400
    msgs = load_msgs()
    msgs["messages"].append({
        "author": author, "text": text,
        "time": datetime.now(TZ).strftime("%H:%M"),
        "id": len(msgs["messages"]) + 1,
    })
    if len(msgs["messages"]) > 200:
        msgs["messages"] = msgs["messages"][-200:]
    save_msgs(msgs)
    return jsonify({"status": "ok"})

# GET /send?text=xxx&author=CEO (compat with old dashboard_server.py)
@app.route('/send', methods=['GET'])
def send_get():
    text = request.args.get('text', '').strip()
    author = request.args.get('author', 'CEO')
    if not text:
        return jsonify({"error": "empty"}), 400
    msgs = load_msgs()
    msgs["messages"].append({
        "author": author, "text": text,
        "time": datetime.now(TZ).strftime("%H:%M"),
        "id": len(msgs["messages"]) + 1,
    })
    if len(msgs["messages"]) > 200:
        msgs["messages"] = msgs["messages"][-200:]
    save_msgs(msgs)
    return jsonify({"status": "ok"})

@app.route('/send', methods=['POST'])
def send_post():
    """Form-encoded POST /send (dashboard form) — redirect back to /"""
    text = request.form.get('text', '').strip()
    author = request.form.get('author', 'CEO')
    if text:
        msgs = load_msgs()
        msgs["messages"].append({
            "author": author, "text": text,
            "time": datetime.now(TZ).strftime("%H:%M"),
            "id": len(msgs["messages"]) + 1,
        })
        if len(msgs["messages"]) > 200:
            msgs["messages"] = msgs["messages"][-200:]
        save_msgs(msgs)
    from flask import redirect
    return redirect("/")

# ═══════════════════════════════════════════
# Special API Routes (MUST be before generic /api/<table>)
# ═══════════════════════════════════════════

@app.route('/api/chat', methods=['POST'])
def chat_reply():
    """小溪AI聊天 — 根据问题类型路由到不同后端"""
    data = request.get_json() or {}
    message = data.get('message', '').strip()
    if not message:
        return jsonify({"reply": "请输入内容"})
    if len(message) > 2000:
        message = message[:2000]

    # 分类: 市场问题走Agent API, 其他走Claude直聊
    market_kw = ['市场','行情','股市','股票','投资','预测','走势','分析',
                 '经济','宏观','产业','铜价','油价','金价','汇率','GDP',
                 'PMI','CPI','通胀','康波','周期','板块','基金','A股',
                 '新能源','半导体','消费','房产','利率','美联储','电力',
                 '低空','航空','光伏','储能','芯片','算力','AI板块','机器人',
                 '无人机','军工','电网','供需','瓶颈','产业链']
    is_market = any(kw in message for kw in market_kw)

    if is_market:
        # Market question → Agent API (4967 agents)
        try:
            import urllib.request
            req = urllib.request.Request(
                "http://localhost:8600/api/agent/ask",
                data=json.dumps({"q": message}).encode(),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=90) as resp:
                result = json.loads(resp.read())
                reply = result.get('answer', '')
                if reply:
                    return jsonify({"reply": reply})
        except Exception:
            pass

    # Non-market question → quick Claude reply or fallback
    # Direct DeepSeek call for general questions
    try:
        import urllib.request
        ds_key = __import__('os').environ.get('DEEPSEEK_API_KEY', '')
        if ds_key:
            system_prompt = "你是小溪，一个温暖的AI助手。用第一人称'我'，像朋友聊天。回答200字以内。不要用'首先其次最后'。不知道就说不知道。"
            body = json.dumps({
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": message},
                ],
                "max_tokens": 400, "temperature": 0.7,
            }).encode()
            req = urllib.request.Request(
                "https://api.deepseek.com/v1/chat/completions",
                data=body,
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {ds_key}"},
            )
            with urllib.request.urlopen(req, timeout=20) as resp:
                result = json.loads(resp.read())
                reply = result.get("choices", [{}])[0].get("message", {}).get("content", "")
                if reply and len(reply) > 10:
                    return jsonify({"reply": reply.strip()})
    except Exception:
        pass

    return jsonify({"reply": "收到你的消息了~ 我现在主要聊市场和经济话题，你可以问我行情、投资、产业趋势之类的！"})

@app.route('/api/chat', methods=['POST'])
@app.route('/api/summary')
def summary():
    db = get_db()
    today = datetime.now(TZ).strftime("%Y-%m-%d")
    income = db.execute(
        "SELECT COALESCE(SUM(amount),0) FROM finance WHERE type='income' AND date(created_at)=?",
        (today,)).fetchone()[0]
    expense = db.execute(
        "SELECT COALESCE(SUM(amount),0) FROM finance WHERE type='expense' AND date(created_at)=?",
        (today,)).fetchone()[0]
    sport = db.execute(
        "SELECT COUNT(*) FROM health WHERE htype='sport' AND date(created_at)=?",
        (today,)).fetchone()[0]
    mood_row = db.execute(
        "SELECT value FROM health WHERE subtype='mood' AND date(created_at)=? ORDER BY created_at DESC LIMIT 1",
        (today,)).fetchone()
    tasks = db.execute(
        "SELECT COUNT(*) FROM work WHERE wtype='task' AND status!='done'").fetchone()[0]
    db.close()
    return jsonify({
        "today": today,
        "income": income,
        "expense": expense,
        "sport_done": sport > 0,
        "mood": mood_row[0] if mood_row else None,
        "pending_tasks": tasks,
    })

@app.route('/api/stats')
def stats():
    db = get_db()
    today = datetime.now(TZ).strftime('%Y-%m-%d')
    month = datetime.now(TZ).strftime('%Y-%m')

    today_income = db.execute(
        "SELECT COALESCE(SUM(amount),0) FROM finance WHERE type='income' AND date(created_at)=?",
        (today,)).fetchone()[0]
    today_expense = db.execute(
        "SELECT COALESCE(SUM(amount),0) FROM finance WHERE type='expense' AND date(created_at)=?",
        (today,)).fetchone()[0]
    today_expense_cats = db.execute(
        "SELECT category, SUM(amount) as total FROM finance WHERE type='expense' AND date(created_at)=? GROUP BY category ORDER BY total DESC",
        (today,)).fetchall()
    today_income_cats = db.execute(
        "SELECT category, SUM(amount) as total FROM finance WHERE type='income' AND date(created_at)=? GROUP BY category ORDER BY total DESC",
        (today,)).fetchall()

    month_income = db.execute(
        "SELECT COALESCE(SUM(amount),0) FROM finance WHERE type='income' AND strftime('%Y-%m',created_at)=?",
        (month,)).fetchone()[0]
    month_expense = db.execute(
        "SELECT COALESCE(SUM(amount),0) FROM finance WHERE type='expense' AND strftime('%Y-%m',created_at)=?",
        (month,)).fetchone()[0]

    steps = db.execute("SELECT value FROM health WHERE subtype='steps' ORDER BY id DESC LIMIT 1").fetchone()
    sleep_r = db.execute("SELECT value FROM health WHERE subtype='sleep' ORDER BY id DESC LIMIT 1").fetchone()
    mood_r = db.execute(
        "SELECT value FROM health WHERE subtype='mood' AND date(created_at)=? ORDER BY id DESC LIMIT 1",
        (today,)).fetchone()

    db.close()
    return jsonify({
        'today': {
            'income': today_income,
            'expense': today_expense,
            'income_cats': [{'cat': r['category'] or '其他', 'amt': r['total']} for r in today_income_cats],
            'expense_cats': [{'cat': r['category'] or '其他', 'amt': r['total']} for r in today_expense_cats],
        },
        'month': {'income': month_income, 'expense': month_expense},
        'health': {
            'steps': int(float(steps['value'])) if steps else 0,
            'sleep': float(sleep_r['value']) if sleep_r else 0,
            'mood': int(mood_r['value']) if mood_r else None,
        }
    })

@app.route('/api/trends/<table>')
def trends(table):
    db = get_db()
    if table == 'health':
        rows = db.execute(
            "SELECT subtype, value, date(created_at) as d FROM health WHERE subtype IN ('steps','sleep') ORDER BY created_at DESC LIMIT 60"
        ).fetchall()
        db.close()
        data = {}
        for r in rows:
            d = r['d']
            if d not in data:
                data[d] = {}
            data[d][r['subtype']] = float(r['value'])
        return jsonify([{'date': d, **vals} for d, vals in sorted(data.items())])
    db.close()
    return jsonify([])

@app.route('/api/dashboard')
def dashboard_data():
    """Return dashboard_data.json as JSON (for AJAX consumers)"""
    if DATA_PATH.exists():
        return jsonify(json.loads(DATA_PATH.read_text()))
    return jsonify({"error": "no data"}), 404

@app.route('/api/insights')
def insights():
    db = get_db()
    today = datetime.now(TZ).strftime('%Y-%m-%d')
    month = datetime.now(TZ).strftime('%Y-%m')
    tips = []

    sleep_row = db.execute("SELECT value FROM health WHERE subtype='sleep' ORDER BY id DESC LIMIT 1").fetchone()
    if sleep_row:
        s = float(sleep_row['value'])
        if s < 6:
            tips.append(f'最近睡眠不足({s}h)，建议今晚早点休息')
        elif s >= 8:
            tips.append(f'睡眠质量很好({s}h)！保持这个节奏')

    steps_row = db.execute("SELECT value FROM health WHERE subtype='steps' ORDER BY id DESC LIMIT 1").fetchone()
    if steps_row:
        st = int(float(steps_row['value']))
        if st < 3000:
            tips.append(f'今天步数偏低({st}步)，出门走走吧')

    mood_row = db.execute(
        "SELECT value FROM health WHERE subtype='mood' AND date(created_at)=? ORDER BY id DESC LIMIT 1",
        (today,)).fetchone()
    if not mood_row:
        tips.append('今天还没记录心情，花10秒记一下吧')

    month_income = db.execute(
        "SELECT COALESCE(SUM(amount),0) FROM finance WHERE type='income' AND strftime('%Y-%m',created_at)=?",
        (month,)).fetchone()[0]
    month_expense = db.execute(
        "SELECT COALESCE(SUM(amount),0) FROM finance WHERE type='expense' AND strftime('%Y-%m',created_at)=?",
        (month,)).fetchone()[0]
    if month_expense > month_income and month_income > 0:
        tips.append(f'本月支出(¥{month_expense})超过收入(¥{month_income})，注意开支')

    if not tips:
        tips.append('一切正常！各项指标都不错')

    db.close()
    return jsonify({'tips': tips, 'generated_at': datetime.now(TZ).strftime('%H:%M')})

# ═══════════════════════════════════════════
# Generic CRUD Routes (MUST be last among /api/*)
# ═══════════════════════════════════════════

@app.route('/api/<table>', methods=['GET', 'POST'])
def handle_table(table):
    if table not in ALLOWED_TABLES:
        return jsonify({"error": "invalid table"}), 404

    if request.method == 'GET':
        return jsonify(list_table(table))

    if request.method == 'POST':
        data = request.get_json() or {}
        if not data:
            return jsonify({"error": "no data"}), 400
        data.pop('id', None)  # auto-increment
        row_id = insert_row(table, data)
        return jsonify({"id": row_id, "status": "ok"})

@app.route('/api/<table>/<int:row_id>', methods=['DELETE'])
def delete_row(table, row_id):
    if table not in ALLOWED_TABLES:
        return jsonify({"error": "invalid table"}), 404
    db = get_db()
    db.execute(f"DELETE FROM {table} WHERE id = ?", (row_id,))
    db.commit()
    db.close()
    return jsonify({"status": "deleted"})

@app.route('/api/health/sync-status')
def health_sync_status():
    """Check recent health sync activity."""
    db = get_db()
    recent = db.execute(
        "SELECT subtype, value, note, created_at FROM health WHERE note LIKE '%sync%' ORDER BY id DESC LIMIT 10"
    ).fetchall()
    db.close()
    if not recent:
        return jsonify({"status": "no_sync", "message": "还没有来自手机的健康同步数据。请确保：1) Health Connect 已安装 2) 佳明App已开启同步 3) 小溪权限已授予"})
    return jsonify({
        "status": "ok",
        "count": len(recent),
        "latest": [{"subtype": r["subtype"], "value": r["value"], "time": r["created_at"], "note": r["note"]} for r in recent]
    })

# ═══════════════════════════════════════════
# Static File Routes
# ═══════════════════════════════════════════

@app.route('/app/<path:filename>')
def serve_app(filename):
    """App WebView pages from dashboard/app/"""
    return send_from_directory(APP_DIR, filename)

@app.route('/proto/<path:filename>')
def serve_proto(filename):
    """Legacy prototype files from dashboard/"""
    return send_from_directory(DASHBOARD_DIR, filename)

@app.route('/<path:filename>')
def serve_dashboard_static(filename):
    """Standalone HTML files from dashboard/ (e.g. test.html, xiaoxi_app.html)"""
    if filename.endswith(('.html', '.css', '.js', '.apk', '.zip')):
        file_path = Path(DASHBOARD_DIR) / filename
        if file_path.exists():
            return send_from_directory(DASHBOARD_DIR, filename)
    # For non-matching routes, return 404
    return jsonify({"error": "not found"}), 404

# ═══════════════════════════════════════════
# CORS (permissive for local dev + WebView)
# ═══════════════════════════════════════════

@app.after_request
def add_cors(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, DELETE, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response

# ═══════════════════════════════════════════

# ── Garmin import ──
from engine.garmin_import import register_routes as _register_garmin
_register_garmin(app)

# ── AI 估价器 ──
@app.route('/api/price-estimate', methods=['POST'])
def price_estimate():
    from engine.price_estimator import estimate
    images = []
    for key in ['image', 'image0', 'image1', 'image2', 'image3']:
        f = request.files.get(key)
        if f and f.filename:
            images.append(f.read())
    # Also check for multiple files with same name
    for flist in request.files.getlist('images'):
        if flist and flist.filename:
            images.append(flist.read())
    if not images:
        return jsonify({"error": "请上传至少一张图片"}), 400
    result = estimate(images)
    return jsonify(result)

# ── 微信→Claude Code 转发 (供 AutoJS 手机脚本调用) ──
import subprocess

CLAUDE_BIN = str(Path(__file__).parent.parent / "node_modules" / ".bin" / "claude")
CLAUDE_ENV = {
    **os.environ,
    "ANTHROPIC_API_KEY": os.getenv("ANTHROPIC_API_KEY", "sk-c1c48141f70c4e9b9d5542c9fff3b10f"),
    "ANTHROPIC_BASE_URL": "https://api.deepseek.com/anthropic",
}
RELAY_TOKEN = "x1x2x3-key-2026"

@app.route("/api/weixin/relay", methods=["POST"])
def weixin_relay():
    data = request.get_json(force=True)
    if data.get("token") != RELAY_TOKEN:
        return jsonify({"error": "unauthorized"}), 403
    msg = data.get("message", "").strip()
    user_id = data.get("user_id", "unknown")
    if not msg:
        return jsonify({"reply": "（没说啥）"})
    # 强制简短回复风格
    prompt = f"（你是小溪，像微信聊天一样回复，1-3句话，不输出分析和思考过程）\n\n{msg}"
    try:
        r = subprocess.run(
            [CLAUDE_BIN, "--print", prompt],
            cwd=str(Path(__file__).parent.parent),
            env=CLAUDE_ENV,
            capture_output=True, text=True, timeout=30,
        )
        reply = r.stdout.strip() or "（小溪思考中...）"
        return jsonify({"reply": reply})
    except subprocess.TimeoutExpired:
        return jsonify({"reply": "（稍等一下...）"})
    except Exception as e:
        return jsonify({"reply": f"出错: {e}"})

# ── Sector Intelligence (方向三: 电力+低空) ──
@app.route('/intel/energy')
def intel_energy():
    """AI数据中心电力 + 低空经济 专项情报"""
    try:
        from engine.agent_ask import ask
        report = ask("分析AI数据中心电力需求和低空经济发展趋势", verbose=False)
        html = f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>电力+低空 专项情报</title>
<style>
:root{{--bg:#0f172a;--card:#1e293b;--text:#e2e8f0;--muted:#94a3b8;--accent:#3B82F6;--border:rgba(148,163,184,0.15)}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:system-ui,sans-serif;background:var(--bg);color:var(--text);max-width:800px;margin:0 auto;padding:2rem 1.5rem;line-height:1.7}}
h1{{font-size:1.5rem;margin-bottom:0.5rem}}h2{{font-size:1.2rem;margin:1.5rem 0 0.5rem;color:var(--accent)}}
.card{{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:1.5rem;margin:1rem 0}}
.mono{{font-family:monospace;white-space:pre-wrap;font-size:0.9rem;line-height:1.6}}
.footer{{text-align:center;color:var(--muted);font-size:0.75rem;margin-top:2rem;padding-top:1rem;border-top:1px solid var(--border)}}
</style></head><body>
<h1>⚡ AI电力 + 🚁 低空经济 · 专项情报</h1>
<p style="color:var(--muted);margin-bottom:1rem">130+数据源 · Agent分析 · 自动生成</p>
<div class="card"><div class="mono">{report}</div></div>
<div class="footer">数据来源: 东方财富/36Kr/World Bank/FreeSearch</div>
</body></html>"""
        return html, 200, {"Content-Type": "text/html; charset=utf-8"}
    except Exception as e:
        return f"<h1>专项情报</h1><p>生成失败: {e}</p>", 200

# ── Public Chat API (简单分身, 非Agent引擎) ──
@app.route('/api/chat', methods=['POST'])
def public_chat():
    """Public chat — Claude Code CLI, no auth required."""
    data = request.get_json(force=True) or {}
    msg = data.get('message', '').strip()
    if not msg:
        return jsonify({"reply": "（没说啥）"})
    prompt = f"（你是小溪AI助手，像微信聊天一样回复，1-3句话，不说分析和思考过程，语气友好。如果你回答不了或需要人工处理，就说：这个我暂时帮不上，你可以直接找小溪本人聊~）\n\n{msg}"
    try:
        r = subprocess.run(
            [CLAUDE_BIN, "--print", prompt],
            cwd=str(Path(__file__).parent.parent),
            env=CLAUDE_ENV,
            capture_output=True, text=True, timeout=20,
        )
        reply = r.stdout.strip() or "（我在，你说）"
        return jsonify({"reply": reply})
    except subprocess.TimeoutExpired:
        return jsonify({"reply": "（等一下...）"})
    except Exception:
        return jsonify({"reply": "（卡了一下，再说一次？）"})

# ── Agent Ask API (L0-L4 engine) ──
@app.route('/api/agent/ask', methods=['GET', 'POST'])
def agent_ask():
    """Ask the Agent engine a market question. Returns multi-agent analysis."""
    if request.method == 'POST':
        question = (request.get_json(silent=True) or {}).get('q', '')
    else:
        question = request.args.get('q', '')

    if not question or len(question.strip()) < 1:
        return jsonify({"error": "请提供问题 (?q=...)"}), 400

    try:
        from engine.agent_ask import ask
        result = ask(question)
        return jsonify({"answer": result, "question": question})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ═══════════════════════════════════════════
# Finance v2 API — 财务中枢
# ═══════════════════════════════════════════

def _verify_token():
    """Check Authorization: Bearer <token>. Returns True if valid."""
    auth = request.headers.get('Authorization', '')
    if not auth.startswith('Bearer '):
        return False
    token = auth[7:]
    try:
        parts = token.split(':')
        ts = int(parts[0])
        if time.time() - ts > TOKEN_TTL:
            return False
        expected = hmac.new(
            FINANCE_SECRET.encode(),
            f'{ADMIN_PASSWORD_HASH}:{ts}'.encode(),
            hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(parts[1], expected):
            return False
        return True
    except Exception:
        return False

def require_token(f):
    """Decorator: require valid finance token"""
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not _verify_token():
            return jsonify({"error": "unauthorized"}), 401
        return f(*args, **kwargs)
    return wrapped

@app.route('/api/finance/v2/verify', methods=['POST'])
def finance_verify():
    """Verify admin password, return token."""
    data = request.get_json(silent=True) or {}
    pwd = data.get('password', '')
    if hashlib.sha256(pwd.encode()).hexdigest() != ADMIN_PASSWORD_HASH:
        return jsonify({"ok": False, "error": "密码错误"}), 401
    ts = int(time.time())
    sig = hmac.new(
        FINANCE_SECRET.encode(),
        f'{ADMIN_PASSWORD_HASH}:{ts}'.encode(),
        hashlib.sha256
    ).hexdigest()
    token = f'{ts}:{sig}'
    return jsonify({"ok": True, "token": token, "expires_in": TOKEN_TTL})

@app.route('/api/finance/v2/summary')
@require_token
def finance_v2_summary():
    """KPI overview: month income/expense/profit + MoM change"""
    db = get_db()
    month = datetime.now(TZ).strftime('%Y-%m')
    entity = request.args.get('entity', '')

    e_filter = "AND entity=?" if entity else ""
    params = (month, entity) if entity else (month,)

    income = db.execute(
        f"SELECT COALESCE(SUM(amount),0) FROM finance WHERE type='income' AND strftime('%Y-%m',created_at)=? {e_filter}",
        params
    ).fetchone()[0]
    expense = db.execute(
        f"SELECT COALESCE(SUM(amount),0) FROM finance WHERE type='expense' AND strftime('%Y-%m',created_at)=? {e_filter}",
        params
    ).fetchone()[0]

    # Previous month
    prev_month_dt = datetime.now(TZ).replace(day=1) - timedelta(days=1)
    prev_month = prev_month_dt.strftime('%Y-%m')
    pp = (prev_month, entity) if entity else (prev_month,)
    prev_income = db.execute(
        f"SELECT COALESCE(SUM(amount),0) FROM finance WHERE type='income' AND strftime('%Y-%m',created_at)=? {e_filter}",
        pp
    ).fetchone()[0]
    prev_expense = db.execute(
        f"SELECT COALESCE(SUM(amount),0) FROM finance WHERE type='expense' AND strftime('%Y-%m',created_at)=? {e_filter}",
        pp
    ).fetchone()[0]

    profit = income - expense
    prev_profit = prev_income - prev_expense

    def pct_change(curr, prev):
        if prev == 0: return None if curr == 0 else 100
        return round((curr - prev) / abs(prev) * 100, 1)

    # By entity breakdown
    by_entity = {}
    entities = db.execute("SELECT name FROM entities ORDER BY name").fetchall()
    for er in entities:
        en = er['name']
        ei = db.execute("SELECT COALESCE(SUM(amount),0) FROM finance WHERE type='income' AND strftime('%Y-%m',created_at)=? AND entity=?", (month, en)).fetchone()[0]
        ee = db.execute("SELECT COALESCE(SUM(amount),0) FROM finance WHERE type='expense' AND strftime('%Y-%m',created_at)=? AND entity=?", (month, en)).fetchone()[0]
        by_entity[en] = {"income": ei, "expense": ee, "profit": ei - ee}

    db.close()
    return jsonify({
        "month": month,
        "income": income, "income_change": pct_change(income, prev_income),
        "expense": expense, "expense_change": pct_change(expense, prev_expense),
        "profit": profit, "profit_change": pct_change(profit, prev_profit),
        "by_entity": by_entity
    })

@app.route('/api/finance/v2/entities')
@require_token
def finance_v2_entities():
    """List entities with their monthly totals"""
    db = get_db()
    month = datetime.now(TZ).strftime('%Y-%m')
    entities = db.execute("SELECT * FROM entities ORDER BY name").fetchall()
    result = []
    for er in entities:
        en = er['name']
        ei = db.execute("SELECT COALESCE(SUM(amount),0) FROM finance WHERE type='income' AND strftime('%Y-%m',created_at)=? AND entity=?", (month, en)).fetchone()[0]
        ee = db.execute("SELECT COALESCE(SUM(amount),0) FROM finance WHERE type='expense' AND strftime('%Y-%m',created_at)=? AND entity=?", (month, en)).fetchone()[0]
        result.append({
            "id": er['id'], "name": en, "type": er['type'],
            "month_income": ei, "month_expense": ee, "month_profit": ei - ee
        })
    db.close()
    return jsonify(result)

@app.route('/api/finance/v2/product-pnl')
@require_token
def finance_v2_product_pnl():
    """Product P&L matrix for current month"""
    db = get_db()
    month = datetime.now(TZ).strftime('%Y-%m')
    products = ['marketfish', 'geoyi', 'chaingold', 'paizhao', 'xiaoxi', 'feishu', 'anfang']
    result = []
    for prod in products:
        rev = db.execute(
            "SELECT COALESCE(SUM(amount),0) FROM finance WHERE type='income' AND strftime('%Y-%m',created_at)=? AND product=?",
            (month, prod)
        ).fetchone()[0]
        cost = db.execute(
            "SELECT COALESCE(SUM(amount),0) FROM finance WHERE type='expense' AND strftime('%Y-%m',created_at)=? AND product=?",
            (month, prod)
        ).fetchone()[0]
        profit = rev - cost
        margin = round(profit / rev * 100, 1) if rev > 0 else None
        result.append({"product": prod, "revenue": rev, "cost": cost, "profit": profit, "margin": margin})
    db.close()
    return jsonify(result)

@app.route('/api/finance/v2/costs/auto')
@require_token
def finance_v2_costs_auto():
    """Auto cost summary from cost_logs"""
    db = get_db()
    rows = db.execute(
        "SELECT date(created_at) as d, SUM(amount) as total FROM finance WHERE is_auto=1 GROUP BY d ORDER BY d DESC LIMIT 30"
    ).fetchall()
    db.close()
    return jsonify([{"date": r['d'], "amount": round(r['total'], 2)} for r in rows])

@app.route('/api/finance/v2/fixed-costs', methods=['GET', 'POST'])
@require_token
def finance_v2_fixed_costs():
    db = get_db()
    if request.method == 'GET':
        rows = db.execute("SELECT * FROM fixed_costs WHERE is_active=1 ORDER BY entity, product, item").fetchall()
        db.close()
        return jsonify([dict(r) for r in rows])
    else:
        data = request.get_json(silent=True) or {}
        entity = data.get('entity', 'KEYSTART')
        product = data.get('product', '')
        item = data.get('item', '')
        amount = float(data.get('amount', 0))
        cycle = data.get('billing_cycle', 'monthly')
        next_date = data.get('next_bill_date', '')
        if not item or amount <= 0:
            db.close(); return jsonify({"error": "invalid data"}), 400
        db.execute(
            "INSERT INTO fixed_costs (entity, product, item, amount, billing_cycle, next_bill_date) VALUES (?,?,?,?,?,?)",
            (entity, product, item, amount, cycle, next_date)
        )
        db.commit()
        fid = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        db.close()
        return jsonify({"id": fid, "status": "ok"})

@app.route('/api/finance/v2/charts/trend')
@require_token
def finance_v2_charts_trend():
    """Monthly income/expense/profit trend (last 12 months) — QuickChart ready"""
    db = get_db()
    entity = request.args.get('entity', '')
    e_filter = "AND entity=?" if entity else ""

    labels = []
    income_data, expense_data, profit_data = [], [], []
    now = datetime.now(TZ)
    for i in range(11, -1, -1):
        dt = now.replace(day=1) - timedelta(days=1) * (i or 0) if i > 0 else now
        if i > 0:
            target = now.replace(day=1) - timedelta(days=i * 31 - (now.day - 1))
            target = target.replace(day=1)
        else:
            target = now.replace(day=1)
        m = target.strftime('%Y-%m')
        labels.append(target.strftime('%y/%m'))
        params = (m, entity) if entity else (m,)
        inc = db.execute(f"SELECT COALESCE(SUM(amount),0) FROM finance WHERE type='income' AND strftime('%Y-%m',created_at)=? {e_filter}", params).fetchone()[0]
        exp = db.execute(f"SELECT COALESCE(SUM(amount),0) FROM finance WHERE type='expense' AND strftime('%Y-%m',created_at)=? {e_filter}", params).fetchone()[0]
        income_data.append(round(inc, 2))
        expense_data.append(round(exp, 2))
        profit_data.append(round(inc - exp, 2))
    db.close()
    return jsonify({
        "type": "bar",
        "data": {
            "labels": labels,
            "datasets": [
                {"label": "收入", "data": income_data, "backgroundColor": "#059669"},
                {"label": "支出", "data": expense_data, "backgroundColor": "#dc2626"},
                {"label": "利润", "data": profit_data, "backgroundColor": "#2563eb"}
            ]
        },
        "options": {
            "plugins": {"legend": {"labels": {"color": "#475569", "font": {"size": 11}}}},
            "scales": {
                "x": {"ticks": {"color": "#94a3b8"}, "grid": {"color": "#f0f1f3"}},
                "y": {"ticks": {"color": "#94a3b8"}, "grid": {"color": "#f0f1f3"}}
            }
        }
    })

@app.route('/api/finance/v2/charts/cost-breakdown')
@require_token
def finance_v2_charts_cost_breakdown():
    """Cost breakdown by category — QuickChart ready"""
    db = get_db()
    month = datetime.now(TZ).strftime('%Y-%m')
    entity = request.args.get('entity', '')
    e_filter = "AND entity=?" if entity else ""
    params = (month, entity) if entity else (month,)
    rows = db.execute(
        f"SELECT COALESCE(category,'其他') as cat, SUM(amount) as total FROM finance WHERE type='expense' AND strftime('%Y-%m',created_at)=? {e_filter} GROUP BY cat ORDER BY total DESC",
        params
    ).fetchall()
    db.close()
    colors = ['#2563eb','#7c3aed','#d97706','#94a3b8','#0891b2','#be123c','#4f46e5','#059669']
    return jsonify({
        "type": "doughnut",
        "data": {
            "labels": [r['cat'] for r in rows],
            "datasets": [{"data": [round(r['total'], 2) for r in rows], "backgroundColor": colors[:len(rows)]}]
        },
        "options": {
            "plugins": {"legend": {"labels": {"color": "#475569", "font": {"size": 11}}}},
            "cutout": "60%"
        }
    })

@app.route('/api/finance/v2/charts/revenue-sources')
@require_token
def finance_v2_charts_revenue():
    """Revenue breakdown by product — QuickChart ready"""
    db = get_db()
    month = datetime.now(TZ).strftime('%Y-%m')
    entity = request.args.get('entity', '')
    e_filter = "AND entity=?" if entity else ""
    params = (month, entity) if entity else (month,)
    rows = db.execute(
        f"SELECT COALESCE(product,'未分配') as prod, SUM(amount) as total FROM finance WHERE type='income' AND strftime('%Y-%m',created_at)=? {e_filter} GROUP BY prod ORDER BY total DESC",
        params
    ).fetchall()
    db.close()
    colors = ['#059669','#2563eb','#7c3aed','#d97706','#0891b2','#be123c','#4f46e5']
    return jsonify({
        "type": "doughnut",
        "data": {
            "labels": [r['prod'] for r in rows],
            "datasets": [{"data": [round(r['total'], 2) for r in rows], "backgroundColor": colors[:len(rows)]}]
        },
        "options": {
            "plugins": {"legend": {"labels": {"color": "#475569", "font": {"size": 11}}}},
            "cutout": "60%"
        }
    })

@app.route('/api/finance/v2/auto-sync', methods=['POST'])
@require_token
def finance_v2_auto_sync():
    """Trigger cost sync from cost_logs"""
    try:
        from engine.cost_sync import sync
        sync()
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/finance/v2/record', methods=['POST'])
@require_token
def finance_v2_record():
    """Add a finance record with entity+product"""
    data = request.get_json(silent=True) or {}
    entity = data.get('entity', 'KEYSTART')
    product = data.get('product', '')
    rtype = data.get('type', 'expense')
    category = data.get('category', '')
    amount = float(data.get('amount', 0))
    note = data.get('note', '')
    date_str = data.get('date', datetime.now(TZ).strftime('%Y-%m-%d'))
    created = f"{date_str} {datetime.now(TZ).strftime('%H:%M:%S')}"

    if not category or amount <= 0:
        return jsonify({"error": "invalid data"}), 400

    db = get_db()
    db.execute(
        "INSERT INTO finance (type, category, amount, note, entity, product, is_auto, created_at) VALUES (?,?,?,?,?,?,0,?)",
        (rtype, category, amount, note, entity, product, created)
    )
    db.commit()
    rid = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    db.close()
    return jsonify({"id": rid, "status": "ok"})

@app.route('/api/finance/v2/transactions')
@require_token
def finance_v2_transactions():
    """Transaction list with filters"""
    db = get_db()
    entity = request.args.get('entity', '')
    product = request.args.get('product', '')
    limit = int(request.args.get('limit', 50))

    conditions = []
    params = []
    if entity:
        conditions.append("entity=?")
        params.append(entity)
    if product:
        conditions.append("product=?")
        params.append(product)

    where = "WHERE " + " AND ".join(conditions) if conditions else ""
    rows = db.execute(
        f"SELECT * FROM finance {where} ORDER BY created_at DESC LIMIT ?",
        params + [limit]
    ).fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])

if __name__ == "__main__":
    if not MSG_PATH.exists():
        save_msgs({"messages": []})
    init_db()
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8600
    print(f"[小溪] Unified Server on :{port} | DB: {DB_PATH}", flush=True)
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
