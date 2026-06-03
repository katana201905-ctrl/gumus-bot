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

# Flask uygulamasını başlatalım (Render/Koyeb gibi yerlerde uykudan uyanık kalması için web sunucusu şarttır)
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
            # SI=F -> Gümüş Ons / USD (COMEX)
            ticker_xag = yf.Ticker("SI=F")
            df_xag = ticker_xag.history(period="5d", interval="15m")
            
            time.sleep(1) # Yahoo engellemesini önlemek için kısa bir bekleme
            
            # USDTRY=X -> USD / TL kuru
            ticker_try = yf.Ticker("USDTRY=X")
            df_try = ticker_try.history(period="5d", interval="15m")
            
            if df_xag.empty or df_try.empty:
                print(f"Veri boş geldi, tekrar deneniyor ({attempt + 1}/3)...")
                time.sleep(2)
                continue
                
            # Zaman dilimlerini eşitleyelim (UTC)
            df_xag.index = df_xag.index.tz_convert('UTC')
            df_try.index = df_try.index.tz_convert('UTC')
            
            # Döviz kurunu gümüş zaman dilimlerine göre hizalayalım (boşlukları doldurarak)
            df_try = df_try.reindex(df_xag.index, method='ffill')
            
            # ONS Fiyatı * Dolar Kuru / 31.1035 = Gram Gümüş (TL)
            df_xag['Gram_Close'] = (df_xag['Close'] * df_try['Close']) / 31.1035
            df_xag['Gram_High'] = (df_xag['High'] * df_try['High']) / 31.1035
            df_xag['Gram_Low'] = (df_xag['Low'] * df_try['Low']) / 31.1035
            df_xag['Gram_Open'] = (df_xag['Open'] * df_try['Open']) / 31.1035
            
            return df_xag
        except Exception as e:
            print(f"Veri çekme hatası (Deneme {attempt + 1}/3): {e}")
            time.sleep(2)
    return None

def analyze_and_report():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Piyasalar analiz ediliyor...")
    df = get_silver_data()
    if df is None:
        return

    # İndikatörleri Hesapla (Yeni ta kütüphanesi kullanarak)
    # 1. RSI (14)
    df['RSI'] = RSIIndicator(close=df['Gram_Close'], window=14).rsi()
    
    # 2. MACD (12, 26, 9)
    macd_indicator = MACD(close=df['Gram_Close'], window_fast=12, window_slow=26, window_sign=9)
    df['MACD_12_26_9'] = macd_indicator.macd()
    df['MACDs_12_26_9'] = macd_indicator.macd_signal()
    
    # 3. EMA (9 ve 21)
    df['EMA_9'] = EMAIndicator(close=df['Gram_Close'], window=9).ema_indicator()
    df['EMA_21'] = EMAIndicator(close=df['Gram_Close'], window=21).ema_indicator()

    # Son veriyi al (Analiz edilecek anlık durum)
    last_row = df.iloc[-1]
    
    current_price = last_row['Gram_Close']
    rsi_value = last_row.get('RSI', 50)
    macd_line = last_row.get('MACD_12_26_9', 0)
    macd_signal = last_row.get('MACDs_12_26_9', 0)
    
    ema_9 = last_row.get('EMA_9', 0)
    ema_21 = last_row.get('EMA_21', 0)

    # --- DURUM ANALİZİ ---
    trend_msg = "Yatay Seyir ➡️"
    action_msg = "Beklemede Kal ⏳"
    
    # Trend Yönü (EMA ve MACD)
    if pd.notna(ema_9) and pd.notna(ema_21) and pd.notna(macd_line) and pd.notna(macd_signal):
        if ema_9 > ema_21 and macd_line > macd_signal:
            trend_msg = "Yükseliş İvmesi Var 📈 (Yukarı Yönlü)"
            if pd.notna(rsi_value) and rsi_value < 70:
                action_msg = "ALIM FIRSATI OLABİLİR 🟢"
            else:
                action_msg = "DİKKAT: Şişkinlik var, tepeden alma! ⚠️"
                
        elif ema_9 < ema_21 and macd_line < macd_signal:
            trend_msg = "Düşüş İvmesi Var 📉 (Aşağı Yönlü)"
            if pd.notna(rsi_value) and rsi_value > 30:
                action_msg = "DÜŞÜŞ DEVAM EDİYOR, UZAK DUR 🔴"
            else:
                action_msg = "DİP SEVİYELER - TEPKİ ALIMI GELEBİLİR 🟡"

    # RSI Yorumu
    rsi_yorum = "Normal seviye"
    if pd.notna(rsi_value):
        if rsi_value >= 70:
            rsi_yorum = "Aşırı Alım Bölgesinde (Düşüş gelebilir!) 🔴"
        elif rsi_value <= 30:
            rsi_yorum = "Aşırı Satım Bölgesinde (Yükseliş başlayabilir!) 🟢"
    else:
        rsi_value = 0

    # Mesajı Hazırla
    message = f"""
<b>📊 GÜMÜŞ ANALİZ RAPORU</b>

💰 <b>Anlık Fiyat:</b> {current_price:.2f} TL (Gram)
📉 <b>Trend Durumu:</b> {trend_msg}
⚠️ <b>RSI Değeri:</b> {rsi_value:.1f} ({rsi_yorum})
💡 <b>Botun Yorumu:</b> <b>{action_msg}</b>

<i>Not: Banka makas aralığını mutlaka göz önünde bulundurunuz.</i>
"""
    print("Mesaj gönderiliyor:\n", message)
    send_telegram_message(message)

def bot_loop():
    print("🤖 Gümüş Analiz Botu Döngüsü Başlatıldı!")
    # İlk çalıştırma
    analyze_and_report()
    
    # 15 dakikada bir çalıştır
    schedule.every(15).minutes.do(analyze_and_report)
    
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    # Botu ayrı bir thread (iş parçacığı) olarak başlatalım ki web sunucusunu engellemesin
    bot_thread = threading.Thread(target=bot_loop, daemon=True)
    bot_thread.start()
    
    # Port ayarını bulut sunucusundan alalım (Render/Koyeb otomatik PORT atar)
    port = int(os.environ.get("PORT", 8080))
    # Flask sunucusunu başlatalım
    app.run(host="0.0.0.0", port=port)
