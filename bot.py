from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)
import yfinance as yf
from prophet import Prophet
import pandas as pd
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
import feedparser
import datetime

TELEGRAM_TOKEN = '7722555638:AAF0ioO4jD0_sWUoWfr1NeXvDTiZ0NzXWVo'

COMMODITY_SYMBOLS = {
    'Crude Oil': 'CL=F',
    'USD/INR': 'USDINR=X'
}

def fetch_headlines(name):
    url = f"https://news.google.com/rss/search?q={name}+stock&hl=en-IN&gl=IN&ceid=IN:en"
    feed = feedparser.parse(url)
    return [entry.title for entry in feed.entries[:5]]

def analyze_sentiment(headlines):
    analyzer = SentimentIntensityAnalyzer()
    scores = [analyzer.polarity_scores(h)['compound'] for h in headlines if h]
    return round(sum(scores)/len(scores), 3) if scores else 0

def detect_symbol_type(symbol):
    if symbol.endswith('=X'):
        return 'forex'
    elif symbol.startswith('^'):
        return 'index'
    elif '.' not in symbol:
        return symbol + '.NS'
    return symbol

def prepare_data(symbol):
    try:
        df = yf.download(symbol, period="6mo", interval="1d", auto_adjust=True, progress=False)
        if df.empty:
            print(f"❌ No data for {symbol}")
            return None
        df = df.reset_index()
        df = df[['Date', 'Close']]
        df.columns = ['ds', 'y']
        df['y'] = pd.to_numeric(df['y'], errors='coerce')
        df.dropna(inplace=True)
        return df if not df.empty else None
    except Exception as e:
        print(f"❌ Error preparing data for {symbol}: {e}")
        return None

def predict_today(df):
    model = Prophet(daily_seasonality=True)
    model.fit(df)
    future = model.make_future_dataframe(periods=1)
    forecast = model.predict(future)
    today = pd.to_datetime(datetime.datetime.now().date())
    forecast_today = forecast[forecast['ds'] == today]
    if forecast_today.empty:
        forecast_today = forecast.tail(1)
    return forecast_today.iloc[0]

def get_commodity_prices():
    indicators = {}
    for name, symbol in COMMODITY_SYMBOLS.items():
        try:
            data = yf.download(symbol, period="1d", interval="1h", progress=False)
            indicators[name] = round(data['Close'][-1], 2)
        except:
            indicators[name] = "N/A"
    return indicators

# === Async Handlers ===

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Welcome to 📈 Smart Stock Bot!\n"
        "Use /predict SYMBOL\nExamples:\n"
        "/predict TCS\n/predict USDINR=X\n/predict ^NSEI"
    )

async def predict(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ Please provide a stock/index/forex symbol. Example: /predict INFY or /predict ^NSEI")
        return

    raw = context.args[0].upper().strip()
    symbol = detect_symbol_type(raw)
    name = raw.replace('.NS', '').replace('=X', '').replace('^', '')

    await update.message.reply_text(f"⏳ Analyzing {raw}...")

    df = prepare_data(symbol)
    if df is None:
        await update.message.reply_text(f"❌ Unable to fetch or process data for {raw}.")
        return

    try:
        forecast = predict_today(df)
        headlines = fetch_headlines(name)
        sentiment = analyze_sentiment(headlines)
        indicators = get_commodity_prices()
        adjusted_yhat = round(forecast['yhat'] * (1 + sentiment * 0.01), 2)

        ticker = yf.Ticker(symbol)
        info = ticker.info

        message = f"""
📊 Prediction for {raw} ({info.get('longName', 'N/A')})
🗓 Date: {forecast['ds'].date()}
💰 Estimated: ₹{round(forecast['yhat'], 2)}
⬇️ Low: ₹{round(forecast['yhat_lower'], 2)}
⬆️ High: ₹{round(forecast['yhat_upper'], 2)}
✨ Adjusted (sentiment): ₹{adjusted_yhat}
🧠 Sentiment: {sentiment}

📌 Info:
- Sector: {info.get('sector', 'N/A')}
- Industry: {info.get('industry', 'N/A')}
- Market Cap: ₹{info.get('marketCap', 'N/A')}
- P/E Ratio: {info.get('trailingPE', 'N/A')}
- Dividend: {info.get('dividendYield', 'N/A')}
- 52W H/L: ₹{info.get('fiftyTwoWeekHigh', 'N/A')} / ₹{info.get('fiftyTwoWeekLow', 'N/A')}
- Day H/L/Open: ₹{info.get('dayHigh', 'N/A')} / ₹{info.get('dayLow', 'N/A')} / ₹{info.get('open', 'N/A')}
- Beta: {info.get('beta', 'N/A')}

🌍 Market Indicators:
""" + "\n".join([f"• {k}: {v}" for k, v in indicators.items()])

        await update.message.reply_text(message)

        if headlines:
            await update.message.reply_text("📰 News:\n" + "\n".join([f"• {h}" for h in headlines]))

    except Exception as e:
        await update.message.reply_text(f"❌ Error during prediction: {e}")

# === Main Application ===

def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("predict", predict))
    app.run_polling()

if __name__ == '__main__':
    main()
