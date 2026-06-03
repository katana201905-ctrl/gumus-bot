import sys
sys.stdout.reconfigure(encoding='utf-8')
import yfinance as yf
import pandas as pd
import requests
import time
import schedule
from datetime import datetime
from ta.momentum import RSIIndicator
from ta.trend import MACD, EMAIndicator
from flask import Flask
import threading
import os

app = Flask(__name__)

TELEGRAM_TOKEN = "8183785389:AAFi_CZUtlGKxzzp5cP0x6dO4r4EFuEBOiw"
CHAT_ID = "6062776989"

@app.route('/')
def home():
    return "🤖 Gümüş Analiz Botu Aktif ve Çalışıyor!"

def send_telegram_message(message):
    if not CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Telegram mesajı gönderilirken hata oluştu: {e}")

def get_silver_data():
    for attempt in range(3):
        try:
            ticker_xag = yf.Ticker("SI=F")
            df_xag = ticker_xag.history(period="5d", interval="15m")
            time.sleep(1)
            ticker_try = yf.Ticker("USDTRY=X")
            df_try = ticker_try.history(period="5d", interval="15m")
            
            if df_xag.empty or df_try.empty:
                time.sleep(2)
                continue
                
            df_xag.index = df_xag.index.tz_convert('UTC')
            df_try.index = df_try.index.tz_convert('UTC')
            
            df_try = df_try.reindex(df_xag.index, method='ffill')
            
            df_xag['Gram_Close'] = (df_xag['Close'] * df_try['Close']) / 31.1035
            df_xag['Gram_High'] = (df_xag['High'] * df_try['High']) / 31.1035
            df_xag['Gram_Low'] = (df_xag['Low'] * df_try['Low']) / 31.1035
            df_xag['Gram_Open'] = (df_xag['Open'] * df_try['Open']) / 31.1035
            
            return df_xag
        except Exception as e:
            time.sleep(2)
    return None

def analyze_candles(df):
    if len(df) < 2:
        return "Mum verisi yetersiz."
        
    last_candle = df.iloc[-1]
    prev_candle = df.iloc[-2]
    
    body = abs(last_candle['Gram_Close'] - last_candle['Gram_Open'])
    upper_shadow = last_candle['Gram_High'] - max(last_candle['Gram_Close'], last_candle['Gram_Open'])
    lower_shadow = min(last_candle['Gram_Close'], last_candle['Gram_Open']) - last_candle['Gram_Low']
    
    total_range = last_candle['Gram_High'] - last_candle['Gram_Low']
    if total_range == 0: total_range = 0.0001
    
    if body < (total_range * 0.1):
        return "⚖️ DOJI MUMU (Kararsız piyasa yön arıyor)"
    elif lower_shadow > (body * 2) and upper_shadow < (body * 0.5):
        return "🔨 ÇEKİÇ MUMU (Alıcılar baskın, yükseliş sinyali)"
    elif prev_candle['Gram_Close'] < prev_candle['Gram_Open'] and \
         last_candle['Gram_Close'] > last_candle['Gram_Open'] and \
         last_candle['Gram_Close'] > prev_candle['Gram_Open'] and \
         last_candle['Gram_Open'] < prev_candle['Gram_Close']:
        return "📈 YUTAN BOĞA MUMU (Güçlü Yükseliş Sinyali!)"
    elif prev_candle['Gram_Close'] > prev_candle['Gram_Open'] and \
         last_candle['Gram_Close'] < last_candle['Gram_Open'] and \
         last_candle['Gram_Close'] < prev_candle['Gram_Open'] and \
         last_candle['Gram_Open'] > prev_candle['Gram_Close']:
        return "📉 YUTAN AYI MUMU (Güçlü Düşüş Sinyali!)"
    else:
        if last_candle['Gram_Close'] > last_candle['Gram_Open']:
            return "🟩 Yeşil Mum (Alıcılar Kontrolde)"
        else:
            return "🟥 Kırmızı Mum (Satıcılar Kontrolde)"

def get_support_resistance(df):
    # Son 5 günlük genel tabloya bakarak pivot hesaplıyoruz
    period_high = df['Gram_High'].max()
    period_low = df['Gram_Low'].min()
    current_close = df.iloc[-1]['Gram_Close']
    
    pivot = (period_high + period_low + current_close) / 3
    r1 = (pivot * 2) - period_low # 1. Direnç
    s1 = (pivot * 2) - period_high # 1. Destek
    return r1, s1

def analyze_and_report():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Piyasalar analiz ediliyor...")
    df = get_silver_data()
    if df is None:
        return

    df['RSI'] = RSIIndicator(close=df['Gram_Close'], window=14).rsi()
    macd_indicator = MACD(close=df['Gram_Close'], window_fast=12, window_slow=26, window_sign=9)
    df['MACD_12_26_9'] = macd_indicator.macd()
    df['MACDs_12_26_9'] = macd_indicator.macd_signal()
    df['EMA_9'] = EMAIndicator(close=df['Gram_Close'], window=9).ema_indicator()
    df['EMA_21'] = EMAIndicator(close=df['Gram_Close'], window=21).ema_indicator()

    last_row = df.iloc[-1]
    current_price = last_row['Gram_Close']
    rsi_value = last_row.get('RSI', 50)
    macd_line = last_row.get('MACD_12_26_9', 0)
    macd_signal = last_row.get('MACDs_12_26_9', 0)
    ema_9 = last_row.get('EMA_9', 0)
    ema_21 = last_row.get('EMA_21', 0)

    candle_msg = analyze_candles(df)
    r1, s1 = get_support_resistance(df)

    trend_msg = "Yatay Seyir ➡️"
    action_msg = "Beklemede Kal ⏳"
    
    if pd.notna(ema_9) and pd.notna(ema_21) and pd.notna(macd_line) and pd.notna(macd_signal):
        if ema_9 > ema_21 and macd_line > macd_signal:
            trend_msg = "Yükseliş İvmesi Var 📈 (Yukarı Yönlü)"
            if pd.notna(rsi_value) and rsi_value < 70:
                action_msg = "ALIM FIRSATI OLABİLİR 🟢"
            else:
                action_msg = "DİKKAT: Şişkinlik var, dirençten dönebilir! ⚠️"
                
        elif ema_9 < ema_21 and macd_line < macd_signal:
            trend_msg = "Düşüş İvmesi Var 📉 (Aşağı Yönlü)"
            if pd.notna(rsi_value) and rsi_value > 30:
                action_msg = "DÜŞÜŞ DEVAM EDİYOR, UZAK DUR 🔴"
            else:
                action_msg = "DİP SEVİYELER - DESTEKTEN SEKME BEKLENEBİLİR 🟡"

    rsi_yorum = "Normal seviye"
    if pd.notna(rsi_value):
        if rsi_value >= 70:
            rsi_yorum = "Aşırı Alım Bölgesinde 🔴"
        elif rsi_value <= 30:
            rsi_yorum = "Aşırı Satım Bölgesinde 🟢"
    else:
        rsi_value = 0

    message = f"""
<b>📊 GÜMÜŞ ANALİZ RAPORU</b>

💰 <b>Anlık Fiyat:</b> {current_price:.2f} TL (Gram)
📉 <b>Trend Durumu:</b> {trend_msg}
🕯️ <b>Mum Analizi:</b> {candle_msg}

🛡️ <b>Destek & Direnç Seviyeleri:</b>
🔺 Direnç (Hedef): {r1:.2f} TL <i>(Kırılırsa uçuşa geçer)</i>
🔻 Destek (Kalkan): {s1:.2f} TL <i>(Düşerse buradan seker)</i>

⚠️ <b>RSI Değeri:</b> {rsi_value:.1f} ({rsi_yorum})
💡 <b>Botun Yorumu:</b> <b>{action_msg}</b>
"""
    send_telegram_message(message)

def bot_loop():
    analyze_and_report()
    schedule.every(15).minutes.do(analyze_and_report)
    while True:
        schedule.run_pending()
        time.sleep(1)

bot_thread = threading.Thread(target=bot_loop, daemon=True)
bot_thread.start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
