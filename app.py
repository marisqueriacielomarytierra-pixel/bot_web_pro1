from flask import Flask, render_template_string, jsonify
import sqlite3, datetime, time, threading
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from iqoptionapi.stable_api import IQ_Option

app = Flask(__name__)

# -------- CONFIG --------
EMAIL = ""        # maryarojas343@gmail.com
PASSWORD = ""     # Arell9.
PAR = "ETHUSD"

# -------- DB --------
def init_db():
    conn = sqlite3.connect("trades.db")
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        hora TEXT,
        par TEXT,
        tipo TEXT,
        duracion TEXT,
        resultado TEXT
    )
    """)
    conn.commit()
    conn.close()
init_db()

# -------- INDICADORES --------
def rsi(series, period=14):
    delta = series.diff()
    up = delta.clip(lower=0)
    down = -1*delta.clip(upper=0)
    ma_up = up.rolling(period).mean()
    ma_down = down.rolling(period).mean()
    rs = ma_up / ma_down.replace(0,1)
    return 100 - (100 / (1 + rs))

def ema(series, period=20):
    return series.ewm(span=period, adjust=False).mean()

# -------- CONEXIÓN --------
IQ = IQ_Option(EMAIL, PASSWORD)
IQ.connect()

# -------- BOT 5 MIN --------
def bot():
    while True:
        try:
            candles_5m = IQ.get_candles(PAR, 300, 50, time.time())
            df = pd.DataFrame(candles_5m)
            df['time'] = pd.to_datetime(df['from'], unit='s')
            df['close'] = df['close'].astype(float)
            df['rsi'] = rsi(df['close'])
            df['ema'] = ema(df['close'])
            df.dropna(inplace=True)

            if df.empty:
                time.sleep(5)
                continue

            ultima = df.iloc[-1]
            rsi_val = ultima['rsi']
            ema_val = ultima['ema']
            precio = ultima['close']
            vela = ultima['close'] - ultima['open']

            señal = None
            duracion = "5 MIN"

            if rsi_val < 40 and precio > ema_val and vela > 0.01:
                señal = "CALL"
            elif rsi_val > 60 and precio < ema_val and vela < -0.01:
                señal = "PUT"

            if señal:
                hora_entrada = (datetime.datetime.now() + datetime.timedelta(minutes=1)).strftime("%H:%M")
                conn = sqlite3.connect("trades.db")
                c = conn.cursor()
                c.execute("INSERT INTO trades (hora, par, tipo, duracion, resultado) VALUES (?,?,?,?,?)",
                          (hora_entrada, PAR, señal, duracion, "PENDIENTE"))
                conn.commit()
                conn.close()
            time.sleep(5)
        except Exception as e:
            print("Error:", e)
            time.sleep(5)

threading.Thread(target=bot, daemon=True).start()

# -------- FUNCIONES --------
def get_trades(limit=20):
    conn = sqlite3.connect("trades.db")
    c = conn.cursor()
    c.execute("SELECT * FROM trades ORDER BY id DESC LIMIT ?", (limit,))
    data = c.fetchall()
    conn.close()
    return data

def winrate():
    data = get_trades(1000)
    g = sum(1 for d in data if d[5]=="GANADA")
    p = sum(1 for d in data if d[5]=="PERDIDA")
    t = g+p
    return round((g/t)*100,2) if t>0 else 0

def generar_grafico():
    candles = IQ.get_candles(PAR, 300, 100, time.time())
    df = pd.DataFrame(candles)
    df['time'] = pd.to_datetime(df['from'], unit='s')
    fig = go.Figure(data=[
        go.Candlestick(
            x=df['time'],
            open=df['open'],
            high=df['max'],
            low=df['min'],
            close=df['close'],
            increasing_line_color='green',
            decreasing_line_color='red'
        )
    ])
    trades = get_trades()
    for t in trades:
        color = "green" if t[3]=="CALL" else "red"
        symbol = "triangle-up" if t[3]=="CALL" else "triangle-down"
        fig.add_trace(go.Scatter(
            x=[df['time'].iloc[-1]],
            y=[df['close'].iloc[-1]],
            mode="markers",
            marker=dict(size=16, color=color, symbol=symbol),
            name=t[3]
        ))
    fig.update_layout(template="plotly_dark", height=600)
    return fig.to_html(full_html=False)

# -------- RUTAS --------
HTML = """
<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<title>BOT 5MIN TRADING PRO</title>
<script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
<style>
body {background:#111;color:white;font-family:sans-serif;text-align:center;}
table {width:100%;border-collapse:collapse;}
th, td {padding:10px;}
th {background:#222;}
tr:nth-child(even){background:#1a1a1a;}
tr:hover{background:#333;}
a {text-decoration:none;font-weight:bold;}
</style>
</head>
<body>
<h1 style="color:#00ffcc;">🔥 BOT 5MIN TRADING PRO</h1>
<div id="grafico">{{grafico|safe}}</div>

<h2>📊 Señales Recientes</h2>
<table id="tabla">
<tr><th>Hora</th><th>Par</th><th>Tipo</th><th>Duración</th><th>Resultado</th><th>Acción</th></tr>
{% for t in trades %}
<tr>
<td>{{t[1]}}</td>
<td>{{t[2]}}</td>
<td style="color:{% if t[3]=='CALL' %}#00ff00{% else %}#ff0000{% endif %};font-weight:bold">{{t[3]}}</td>
<td>{{t[4]}}</td>
<td>{{t[5]}}</td>
<td>
<a href="/g/{{t[0]}}" style="color:green;font-size:20px;">✅</a>
<a href="/p/{{t[0]}}" style="color:red;font-size:20px;">❌</a>
</td>
</tr>
{% endfor %}
</table>

<h2>📈 Winrate: <span id="win">{{win}}</span>%</h2>

<script>
async function actualizar() {
    const res = await fetch('/datos');
    const data = await res.json();
    document.getElementById('tabla').innerHTML = data.tabla;
    document.getElementById('win').innerText = data.win;
    document.getElementById('grafico').innerHTML = data.grafico;
}
setInterval(actualizar, 5000);
</script>
</body>
</html>
"""

@app.route("/")
def home():
    return render_template_string(
        HTML,
        trades=get_trades(),
        win=winrate(),
        grafico=generar_grafico()
    )

@app.route("/datos")
def datos():
    trades = get_trades()
    tabla_html = '<tr><th>Hora</th><th>Par</th><th>Tipo</th><th>Duración</th><th>Resultado</th><th>Acción</th></tr>'
    for t in trades:
        color = "#00ff00" if t[3]=="CALL" else "#ff0000"
        tabla_html += f'<tr><td>{t[1]}</td><td>{t[2]}</td><td style="color:{color};font-weight:bold">{t[3]}</td><td>{t[4]}</td><td>{t[5]}</td><td><a href="/g/{t[0]}" style="color:green;font-size:20px;">✅</a> <a href="/p/{t[0]}" style="color:red;font-size:20px;">❌</a></td></tr>'
    return jsonify({
        "tabla": tabla_html,
        "win": winrate(),
        "grafico": generar_grafico()
    })

@app.route("/g/<int:id>")
def g(id):
    conn = sqlite3.connect("trades.db")
    c = conn.cursor()
    c.execute("UPDATE trades SET resultado='GANADA' WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return '', 204

@app.route("/p/<int:id>")
def p(id):
    conn = sqlite3.connect("trades.db")
    c = conn.cursor()
    c.execute("UPDATE trades SET resultado='PERDIDA' WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return '', 204

app.run(host="0.0.0.0", port=10000)
