import yfinance as yf
import pandas as pd
import numpy as np
import requests
import json
import warnings
import os
import time
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from datetime import datetime

warnings.filterwarnings('ignore')

session = requests.Session()
retry = Retry(connect=3, backoff_factor=0.5)
adapter = HTTPAdapter(max_retries=retry)
session.mount('https://', adapter)
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
})

def get_tickers_from_csv():
    """修正後的 CSV 讀取邏輯，確保檔名匹配正確"""
    print("\n=== 正在讀取 CSV 標的清單 ===")
    
    # 請確保 GitHub 專案根目錄下的檔案名稱與此處完全一致
    csv_map = {
        "TW_STOCKS_0050": "TrackingList.xlsx - 台灣股票.csv",
        "TW_ETFS": "TrackingList.xlsx - 台灣ETF.csv",
        "US_STOCKS_SP100": "TrackingList.xlsx - 美國股票.csv",
        "US_ETFS": "TrackingList.xlsx - 美國ETF.csv",
        "CRYPTOCURRENCY": "TrackingList.xlsx - 虛擬貨幣.csv"
    }
    
    result = {}
    for cat, filename in csv_map.items():
        if os.path.exists(filename):
            try:
                # 讀取 CSV
                df = pd.read_csv(filename)
                
                # 自動判斷代碼所在的欄位 (假設通常在第一欄或標題包含 Ticker/代碼)
                tickers = df.iloc[:, 0].dropna().astype(str).tolist()
                
                cleaned = []
                for t in tickers:
                    t = t.strip().upper()
                    # 過濾無效內容
                    if len(t) < 2 or t in ['SYMBOL', 'NAN', '代碼']: continue
                    
                    # 統一加入後綴
                    if cat in ['TW_STOCKS_0050', 'TW_ETFS'] and not t.endswith(('.TW', '.TWO')):
                        t += '.TW'
                    elif cat == 'CRYPTOCURRENCY' and not t.endswith(('-USD', '-USDT')):
                        t += '-USD'
                    
                    cleaned.append(t)
                
                result[cat] = list(set(cleaned))
                print(f"✅ 成功載入 {cat}: {len(cleaned)} 檔")
            except Exception as e:
                print(f"⚠️ 讀取 {filename} 失敗: {e}")
        else:
            print(f"❌ 找不到檔案: {filename}")
            
    return result

def download_robustly(tickers):
    print(f"   -> 執行下載: {len(tickers)} 檔...")
    all_prices = {}
    for ticker in tickers:
        try:
            tkr = yf.Ticker(ticker)
            # 下載近兩年資料
            data = tkr.history(period="2y", auto_adjust=True)
            if not data.empty:
                all_prices[ticker] = data['Close']
        except Exception: 
            continue
        time.sleep(0.05)
    return pd.DataFrame(all_prices)

def calculate_momentum(tickers, cat_key):
    prices = download_robustly(tickers)
    if prices.empty: return {}, []
    
    # 月線頻率計算
    monthly = prices.resample('ME').last()
    m1 = monthly.pct_change(periods=1)
    m3 = monthly.pct_change(periods=3)
    m6 = monthly.pct_change(periods=6)
    mom = ((m1 + m3 + m6) / 3) * 100
    
    history = {}
    # 計算最近 12 個月的歷史資料
    for date in mom.tail(12).index:
        month_str = date.strftime('%Y-%m')
        row = mom.loc[date].dropna().sort_values(ascending=False)
        history[month_str] = [{"symbol": s, "momentum": round(v, 2)} for s, v in row.head(5).items()]
    
    current = [{"symbol": s, "momentum": round(v, 2)} for s, v in mom.iloc[-1].dropna().sort_values(ascending=False).items()]
    return history, current

def main():
    # 讀取清單
    categories = get_tickers_from_csv()
    
    final_json = {
        "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 
        "history": {}, 
        "current_all": {}
    }
    
    for cat_key, tickers in categories.items():
        if not tickers: continue
        hist, curr = calculate_momentum(tickers, cat_key)
        final_json["current_all"][cat_key] = curr
        for month, items in hist.items():
            if month not in final_json["history"]: final_json["history"][month] = {}
            final_json["history"][month][cat_key] = items
            
    with open("momentum_history.json", 'w', encoding='utf-8') as f:
        json.dump(final_json, f, ensure_ascii=False, indent=4)
    print("\n✅ 更新完成，已存入 momentum_history.json")

if __name__ == "__main__":
    main()
