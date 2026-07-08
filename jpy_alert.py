import os
import requests
import statistics
from datetime import datetime, timedelta, timezone

# ===== 設定 (由 GitHub Secrets 讀取, 唔會外洩) =====
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]

# ===== 機構預測 (手動更新, 每 1-2 週一次) =====
# 上網睇分析師對 USD/JPY 未來 1 個月預測, 填低/高範圍
FORECAST_USDJPY_LOW = 150.0
FORECAST_USDJPY_HIGH = 158.0
FORECAST_UPDATED = "2026-07-07"
FORECAST_NOTE = "Reuters FX poll 中位"

BASE = "https://api.frankfurter.app"

def get_rates(days=30):
    """取近 N 日匯率, 回傳 (date, hkd_per_100jpy) 即 100 JPY = ? HKD"""
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=days + 5)
    url = f"{BASE}/{start}..{end}?from=HKD&to=JPY"
    r = requests.get(url, timeout=15)
    r.raise_for_status()
    data = r.json()["rates"]
    series = sorted((d, 100 / v["JPY"]) for d, v in data.items())
    return series

def get_usd_hkd():
    r = requests.get(f"{BASE}/latest?from=USD&to=HKD", timeout=15)
    r.raise_for_status()
    return r.json()["rates"]["HKD"]

def build_message(series):
    today_date, today_rate = series[-1]

    last7 = series[-7:]
    lines7 = []
    prev = None
    for d, v in last7:
        arrow = ""
        if prev is not None:
            arrow = " ▲" if v > prev else (" ▼" if v < prev else " ―")
        lines7.append(f"  {d}: 100 JPY = {v:.4f} HKD{arrow}")
        prev = v

    vals = [v for _, v in series]
    hi, lo = max(vals), min(vals)
    hi_date = [d for d, v in series if v == hi][0]
    lo_date = [d for d, v in series if v == lo][0]
    pos_pct = (today_rate - lo) / (hi - lo) * 100 if hi != lo else 50

    recent = sum(v for _, v in series[-3:]) / 3
    earlier = sum(v for _, v in series[-6:-3]) / 3
    diff_pct = (recent - earlier) / earlier * 100
    if diff_pct < -0.3:
        trend = f"📉 日元轉弱中 (換錢較抵) {diff_pct:+.2f}%"
    elif diff_pct > 0.3:
        trend = f"📈 日元轉強中 (換錢較貴) {diff_pct:+.2f}%"
    else:
        trend = f"➡️ 橫行 ({diff_pct:+.2f}%)"

    daily_returns = [
        (series[i][1] / series[i-1][1] - 1)
        for i in range(1, len(series))
    ]
    daily_std = statistics.pstdev(daily_returns) if len(daily_returns) > 1 else 0
    month_vol = daily_std * (30 ** 0.5)
    stat_low = today_rate * (1 - month_vol)
    stat_high = today_rate * (1 + month_vol)

    try:
        usd_hkd = get_usd_hkd()
        fc_a = 100 * usd_hkd / FORECAST_USDJPY_LOW
        fc_b = 100 * usd_hkd / FORECAST_USDJPY_HIGH
        fc_low, fc_high = min(fc_a, fc_b), max(fc_a, fc_b)
        forecast_block = (
            f"🏦 機構預測 (未來約 1 個月)\n"
            f"  100 JPY ≈ {fc_low:.4f} ~ {fc_high:.4f} HKD\n"
            f"  (USD/JPY {FORECAST_USDJPY_LOW:.0f}~{FORECAST_USDJPY_HIGH:.0f})\n"
            f"  來源: {FORECAST_NOTE}\n"
            f"  更新於: {FORECAST_UPDATED}\n\n"
        )
    except Exception:
        forecast_block = "🏦 機構預測: (USD/HKD 取數失敗, 略過)\n\n"

    msg = (
        f"🇯🇵 日元匯率通知\n"
        f"📅 {today_date}\n"
        f"━━━━━━━━━━━━━━\n"
        f"💴 當日匯率\n"
        f"  100 JPY = {today_rate:.4f} HKD  ⭐\n\n"
        f"📊 過去 7 日走勢\n"
        + "\n".join(lines7) + "\n\n"
        f"📈 近 30 日\n"
        f"  最抵: {lo:.4f} ({lo_date}) ← 日元最弱\n"
        f"  最貴: {hi:.4f} ({hi_date}) ← 日元最強\n"
        f"  當前位處: {pos_pct:.0f}% (0%=最抵, 100%=最貴)\n\n"
        f"🔮 趨勢\n  {trend}\n\n"
        + forecast_block +
        f"📐 統計外推 (基於近期波動)\n"
        f"  100 JPY ≈ {stat_low:.4f} ~ {stat_high:.4f} HKD\n"
        f"  (±1 標準差, 非預測)\n"
        f"━━━━━━━━━━━━━━\n"
        f"⚠️ 匯率無法預測未來, 以上僅供參考"
    )
    return msg

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": CHAT_ID, "text": text}, timeout=15)

def main():
    try:
        series = get_rates(30)
        msg = build_message(series)
        send_telegram(msg)
        print("已發送:\n", msg)
    except Exception as e:
        send_telegram(f"⚠️ 匯率通知失敗: {e}")
        print("錯誤:", e)

if __name__ == "__main__":
    main()
