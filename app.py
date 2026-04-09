from flask import Flask, render_template_string, redirect
import sqlite3, datetime, time, threading
import numpy as np
from iqoptionapi.stable_api import IQ_Option

app = Flask(__name__)

EMAIL = "maryarojas343@gmail.com"
PASSWORD = "Arell9."
PAR = "ETHUSD"

# -------- DB --------
def init_db():
    conn = sqlite3.connect("trades.db")
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        hora TEXT,
        tipo TEXT,
        resultado TEXT
    )
    """)
    conn.commit()
    conn.close()

init_db()

# -------- BOT --------
IQ = IQ_Option(EMAIL, PASSWORD)
IQ.connect()

def rsi(c):
    d = np.diff(c)
    g = np.where(d > 0, d, 0)
    l = np.where(d < 0, -d, 0)
    ag = np.mean(g[-14:])
    al = np.mean(l[-14:])
    rs = ag / (al if al != 0 else 1)
    return 100 - (100 / (1 + rs))

def bot():
    while True:
        try:
            candles = IQ.get_candles(PAR, 60, 50, time.time())
            c = np.array([x['close'] for x in candles])

            r = rsi(c)
            señal = None

            if r < 30:
                señal = "CALL"
            elif r > 70:
                señal = "PUT"

            if señal:
                conn = sqlite3.connect("trades.db")
                cdb = conn.cursor()
                cdb.execute("INSERT INTO trades (hora, tipo, resultado) VALUES (?,?,?)",
                            (datetime.datetime.now().strftime("%H:%M:%S"), señal, "PENDIENTE"))
                conn.commit()
                conn.close()

        except:
            pass

        time.sleep(60)

threading.Thread(target=bot, daemon=True).start()

# -------- HTML --------
HTML = """
<meta http-equiv="refresh" content="5">

<h1>🔥 TRADING PANEL PRO</h1>

<!-- TradingView Widget -->
<div id="tv_chart"></div>
<script src="https://s3.tradingview.com/tv.js"></script>
<script>
new TradingView.widget({
  "container_id": "tv_chart",
  "symbol": "BINANCE:ETHUSDT",
  "interval": "1",
  "width": "100%",
  "height": 400
});
</script>

<h2>📊 Señales</h2>
<table border="1">
<tr><th>Hora</th><th>Tipo</th><th>Resultado</th><th>Acción</th></tr>

{% for t in trades %}
<tr>
<td>{{t[1]}}</td>
<td>{{t[2]}}</td>
<td>{{t[3]}}</td>
<td>
<a href="/g/{{t[0]}}">✅</a>
<a href="/p/{{t[0]}}">❌</a>
</td>
</tr>
{% endfor %}
</table>

<h2>📈 Winrate: {{win}}%</h2>
"""

def get_trades():
    conn = sqlite3.connect("trades.db")
    c = conn.cursor()
    c.execute("SELECT * FROM trades ORDER BY id DESC")
    data = c.fetchall()
    conn.close()
    return data

def winrate():
    data = get_trades()
    g = sum(1 for d in data if d[3]=="GANADA")
    p = sum(1 for d in data if d[3]=="PERDIDA")
    t = g+p
    return round((g/t)*100,2) if t>0 else 0

@app.route("/")
def home():
    return render_template_string(HTML, trades=get_trades(), win=winrate())

@app.route("/g/<int:id>")
def g(id):
    conn = sqlite3.connect("trades.db")
    c = conn.cursor()
    c.execute("UPDATE trades SET resultado='GANADA' WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return redirect("/")

@app.route("/p/<int:id>")
def p(id):
    conn = sqlite3.connect("trades.db")
    c = conn.cursor()
    c.execute("UPDATE trades SET resultado='PERDIDA' WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return redirect("/")

app.run(host="0.0.0.0", port=10000)