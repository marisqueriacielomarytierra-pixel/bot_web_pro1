from flask import Flask, render_template_string, redirect
import sqlite3, datetime, time, threading
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from iqoptionapi.stable_api import IQ_Option

app = Flask(__name__)

# -------- CONFIG --------
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
def rsi(c):
    d = np.diff(c)
    g = np.where(d > 0, d, 0)
    l = np.where(d < 0, -d, 0)
    ag = np.mean(g[-14:])
    al = np.mean(l[-14:])
    rs = ag / (al if al != 0 else 1)
    return 100 - (100 / (1 + rs))

def ema(data, period=20):
    return np.convolve(data, np.ones(period)/period, mode='valid')

# -------- CONEXIÓN --------
IQ = IQ_Option(EMAIL, PASSWORD)
IQ.connect()

# -------- BOT --------
def bot():
    while True:
        try:
            # sincronizar vela
            segundos = int(time.time()) % 60
            time.sleep(60 - segundos)

            candles_1m = IQ.get_candles(PAR, 60, 50, time.time())
            candles_5m = IQ.get_candles(PAR, 300, 50, time.time())

            close_1m = np.array([x['close'] for x in candles_1m])
            open_1m = np.array([x['open'] for x in candles_1m])
            close_5m = np.array([x['close'] for x in candles_5m])

            rsi_1m = rsi(close_1m)
            rsi_5m = rsi(close_5m)

            ema_1m = ema(close_1m)[-1]
            precio = close_1m[-1]

            vela = close_1m[-1] - open_1m[-1]

            señal = None
            duracion = None

            # CALL PRO
            if (rsi_1m < 25 and rsi_5m < 35 and 
                precio > ema_1m and 
                vela > 0 and abs(vela) > 0.2):
                señal = "CALL"
                duracion = "1 MIN"

            # PUT PRO
            elif (rsi_1m > 75 and rsi_5m > 65 and 
                  precio < ema_1m and 
                  vela < 0 and abs(vela) > 0.2):
                señal = "PUT"
                duracion = "1 MIN"

            # 5 MIN (más fuerte)
            elif rsi_5m < 25:
                señal = "CALL"
                duracion = "5 MIN"

            elif rsi_5m > 75:
                señal = "PUT"
                duracion = "5 MIN"

            if señal:
                hora_entrada = (datetime.datetime.now() + datetime.timedelta(minutes=1)).strftime("%H:%M")

                conn = sqlite3.connect("trades.db")
                c = conn.cursor()
                c.execute("INSERT INTO trades (hora, par, tipo, duracion, resultado) VALUES (?,?,?,?,?)",
                          (hora_entrada, PAR, señal, duracion, "PENDIENTE"))
                conn.commit()
                conn.close()

        except Exception as e:
            print("Error:", e)

threading.Thread(target=bot, daemon=True).start()

# -------- GRÁFICO --------
def generar_grafico():
    candles = IQ.get_candles(PAR, 60, 100, time.time())
    df = pd.DataFrame(candles)
    df['time'] = pd.to_datetime(df['from'], unit='s')

    fig = go.Figure(data=[
        go.Candlestick(
            x=df['time'],
            open=df['open'],
            high=df['max'],
            low=df['min'],
            close=df['close']
        )
    ])

    trades = get_trades()

    for t in trades[:20]:
        color = "green" if t[3] == "CALL" else "red"
        symbol = "triangle-up" if t[3] == "CALL" else "triangle-down"

        fig.add_trace(go.Scatter(
            x=[df['time'].iloc[-1]],
            y=[df['close'].iloc[-1]],
            mode="markers",
            marker=dict(size=14, color=color, symbol=symbol),
            name=t[3]
        ))

    return fig.to_html(full_html=False)

# -------- FUNCIONES --------
def get_trades():
    conn = sqlite3.connect("trades.db")
    c = conn.cursor()
    c.execute("SELECT * FROM trades ORDER BY id DESC")
    data = c.fetchall()
    conn.close()
    return data

def winrate():
    data = get_trades()
    g = sum(1 for d in data if d[5]=="GANADA")
    p = sum(1 for d in data if d[5]=="PERDIDA")
    t = g+p
    return round((g/t)*100,2) if t>0 else 0

# -------- HTML --------
HTML = """
<h1 style="color:#00ffcc;">🔥 BOT TRADING PRO</h1>

<div>
{{grafico|safe}}
</div>

<h2>📊 Señales</h2>
<table border="1" style="color:white;background:black;">
<tr>
<th>Hora</th><th>Par</th><th>Tipo</th><th>Duración</th><th>Resultado</th><th>Acción</th>
</tr>

{% for t in trades %}
<tr>
<td>{{t[1]}}</td>
<td>{{t[2]}}</td>
<td>{{t[3]}}</td>
<td>{{t[4]}}</td>
<td>{{t[5]}}</td>
<td>
<a href="/g/{{t[0]}}">✅</a>
<a href="/p/{{t[0]}}">❌</a>
</td>
</tr>
{% endfor %}
</table>

<h2>📈 Winrate: {{win}}%</h2>
"""

# -------- RUTAS --------
@app.route("/")
def home():
    return render_template_string(
        HTML,
        trades=get_trades(),
        win=winrate(),
        grafico=generar_grafico()
    )

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

# -------- RUN --------
app.run(host="0.0.0.0", port=10000)
