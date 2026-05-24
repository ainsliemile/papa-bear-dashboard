import yfinance as yf
import pandas as pd
import numpy as np
import requests
import json
import warnings
import io
import os
import re
import time
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from datetime import datetime

warnings.filterwarnings('ignore')

session = requests.Session()
retry = Retry(connect=3, backoff_factor=0.5)
adapter = HTTPAdapter(max_retries=retry)
session.mount('http://', adapter)
session.mount('https://', adapter)
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
})

# ==========================================
# 1. 抓取邏輯 (信任 Excel 版)
# ==========================================
def get_0050_tickers():
    return ["2330.TW", "2317.TW", "2454.TW", "2382.TW", "2308.TW"]

def get_sp100_tickers():
    return ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"]

def get_crypto_tickers():
    return ["BTC-USD", "ETH-USD", "SOL-USD"]

def get_tickers_from_local_excel():
    file_path = "TrackingList.xlsx"
    print(f"\n=== 正在嘗試從本地檔案 {file_path} 讀取 A 欄標的 ===")
    
    categories_map = {
        "TW_STOCKS_0050": ["台灣股票", "台股", "台灣50"],
        "TW_ETFS": ["台灣ETF", "台股ETF"],
        "US_STOCKS_SP100": ["美國股票", "美股"],
        "US_ETFS": ["美國ETF", "美股ETF"],
        "CRYPTOCURRENCY": ["虛擬貨幣", "加密貨幣", "加密幣"]
    }
    result = {k: [] for k in categories_map.keys()}
    
    if not os.path.exists(file_path):
        print(f"⚠️ 找不到檔案: {file_path}")
        return result
        
    try:
        excel_data = pd.read_excel(file_path, sheet_name=None, header=None)
        
        for cat_key, allowed_names in categories_map.items():
            matched_sheet = None
            for sheet in excel_data.keys():
                if any(name in str(sheet).replace(" ", "") for name in allowed_names):
                    matched_sheet = sheet
                    break
                    
            if matched_sheet:
                df = excel_data[matched_sheet]
                raw_tickers = df.iloc[:, 0].astype(str).tolist() if len(df.columns) > 0 else []
                cleaned_tickers = []
                
                for val in raw_tickers:
                    val = str(val).strip().upper()
                    if val in ['NAN', '', 'NONE', 'NULL', 'LIST', 'NOTE', '代碼', '標的']: continue
                    
                    match = re.search(r'[A-Z0-9\.\-\^]+', val)
                    if not match: continue
                    ticker = match.group(0)
                    
                    if ticker in ['LIST', 'NOTE']: continue
                    
                    if cat_key in ['TW_STOCKS_0050', 'TW_ETFS']:
                        if not ticker.endswith('.TW') and not ticker.endswith('.TWO'): 
                            ticker = f"{ticker}.TW"
                    elif cat_key == 'CRYPTOCURRENCY':
                        if not ticker.endswith('-USD'): 
                            ticker = f"{ticker}-USD"
                        
                    cleaned_tickers.append(ticker)
                    
                result[cat_key] = list(set(cleaned_tickers))
                print(f"[{matched_sheet}] 成功從 Excel 載入 {len(result[cat_key])} 檔")
    except Exception as e:
        print(f"讀取 Excel 發生錯誤: {e}")
    return result

TW_ETFS = ["0050.TW", "0056.TW"]
US_SECTORS = ["XLK"]
US_ETFS = ["VOO", "QQQ"]

# ==========================================
# 2. 核心技術：超穩定 Ticker.history 
# ==========================================
def download_robustly(tickers):
    print(f"   -> 準備「超穩定安全下載」 {len(tickers)} 檔標的資料...")
    all_prices = {}
    
    for i, ticker in enumerate(tickers, 1):
        try:
            tkr = yf.Ticker(ticker)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                data = tkr.history(period="2y", auto_adjust=True)
            
            if data.empty or 'Close' not in data.columns:
                fallback_ticker = None
                
                if ticker.endswith('.TW'):
                    fallback_ticker = ticker.replace('.TW', '.TWO')
                elif not ticker.endswith('.TW') and not ticker.endswith('.TWO') and '.' in ticker:
                    fallback_ticker = ticker.replace('.', '-')

                if fallback_ticker:
                    tkr_fallback = yf.Ticker(fallback_ticker)
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore")
                        data = tkr_fallback.history(period="2y", auto_adjust=True)
                    
                    if not data.empty and 'Close' in data.columns:
                        ticker = fallback_ticker

            if not data.empty and 'Close' in data.columns:
                p = data['Close']
                if isinstance(p, pd.DataFrame):
                    p = p.iloc[:, 0]
                
                if p.index.tz is not None:
                    p.index = p.index.tz_localize(None)
                    
                all_prices[ticker] = p
            else:
                pass 
                
        except Exception:
            pass 
            
        time.sleep(0.1) 
        
    if not all_prices:
        return pd.DataFrame()
        
    final_prices = pd.DataFrame(all_prices)
    print(f"      ✅ 成功下載 {len(final_prices.columns)} 檔有效歷史數據！")
    return final_prices

# ==========================================
# 3. 動能計算核心演算法
# ==========================================
def calculate_historical_momentum(tickers, category_name):
    print(f"\n[{category_name}] 開始處理...")
    
    prices = download_robustly(tickers)
    
    if prices.empty or prices.shape[1] == 0:
        print(f"⚠️ 警告：{category_name} 抓不到任何價格資料！")
        return {}, []
    
    prices = prices.ffill().resample('D').ffill()
    
    if category_name in ["TW_ETFS", "US_ETFS", "TW_STOCKS_0050", "US_STOCKS_SP100"]: p1, p2, p3 = 30, 90, 180
    elif category_name == "CRYPTOCURRENCY": p1, p2, p3 = 14, 30, 90
    else: p1, p2, p3 = 30, 90, 180

    m1 = prices.pct_change(periods=p1)
    m2 = prices.pct_change(periods=p2)
    m3 = prices.pct_change(periods=p3)
    
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        avg_momentum_values = np.nanmean([m1.values, m2.values, m3.values], axis=0)
        
    avg_momentum = pd.DataFrame(avg_momentum_values, index=prices.index, columns=prices.columns)
    
    monthly_momentum = avg_momentum.resample('ME').last()
    last_12_months = monthly_momentum.tail(12)
    
    history_result = {}
    for date, row in last_12_months.iterrows():
        month_str = date.strftime('%Y-%m')
        valid_ranks = row.dropna().sort_values(ascending=False)
        history_result[month_str] = [{"symbol": s, "momentum": round(v * 100, 2)} for s, v in valid_ranks.items()]
        
    latest_row = avg_momentum.iloc[-1].dropna().sort_values(ascending=False)
    current_all = [{"symbol": s, "momentum": round(v * 100, 2)} for s, v in latest_row.items()]
        
    return history_result, current_all

# ==========================================
# 4. 輔助函數：計算大盤濾網 (1+3月動能)
# ==========================================
def calc_filter_momentum(ticker, name):
    print(f"\n=== 計算大盤防護濾網 {name} ({ticker}) ===")
    data = download_robustly([ticker])
    fast_mom = 0.0
    if not data.empty and ticker in data.columns:
        monthly = data[ticker].resample('ME').last()
        try:
            if len(monthly) >= 4:
                m1 = monthly.pct_change(periods=1).iloc[-1]
                m3 = monthly.pct_change(periods=3).iloc[-1]
                fast_mom = ((m1 + m3) / 2) * 100
                print(f"🔥 最新 {name} 濾網: {fast_mom:.2f}%")
        except Exception as e:
            print(f"計算 {name} 發生錯誤: {e}")
    return round(fast_mom, 2)

# ==========================================
# 5. 主程式整合
# ==========================================
def main():
    print("=== Papa Bear 跨市場動能監控系統 (SPY+0050+SOX+TWII 濾網版) ===")
    
    excel_data = get_tickers_from_local_excel()
    fallback_categories = {
        "TW_STOCKS_0050": get_0050_tickers(),
        "TW_ETFS": TW_ETFS,
        "US_STOCKS_SP100": get_sp100_tickers(),
        "US_ETFS": US_ETFS,
        "CRYPTOCURRENCY": get_crypto_tickers()
    }
    
    categories = {}
    for cat_key in fallback_categories.keys():
        if excel_data and len(excel_data.get(cat_key, [])) > 0:
            categories[cat_key] = excel_data[cat_key]
        else:
            categories[cat_key] = fallback_categories[cat_key]
    
    final_json_data = {
        "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "history": {}, 
        "current_all": {}
    }
    tickers_list_data = {}
    global_history = {}
    global_current = []
    
    for cat_key, tickers in categories.items():
        unique_tickers = sorted(list(set(tickers)))
        tickers_list_data[cat_key] = unique_tickers
        
        history_res, current_all_res = calculate_historical_momentum(unique_tickers, cat_key)
        final_json_data["current_all"][cat_key] = current_all_res
        global_current.extend(current_all_res)
        
        for month, all_list in history_res.items():
            if month not in final_json_data["history"]: 
                final_json_data["history"][month] = {}
            if month not in global_history:
                global_history[month] = []
                
            final_json_data["history"][month][cat_key] = all_list[:3]
            global_history[month].extend(all_list)

    # 計算綜合排名
    global_current_sorted = sorted(global_current, key=lambda x: x['momentum'], reverse=True)
    final_json_data["current_all"]["ALL_ASSETS"] = global_current_sorted[:30] 
    for month, items in global_history.items():
        sorted_items = sorted(items, key=lambda x: x['momentum'], reverse=True)
        final_json_data["history"][month]["ALL_ASSETS"] = sorted_items[:10]

    # 🚀 加入四個大盤指標濾網 (1+3月動能)
    final_json_data["spy_1_3_momentum"] = calc_filter_momentum("SPY", "標普500")
    final_json_data["sox_1_3_momentum"] = calc_filter_momentum("^SOX", "費城半導體")
    final_json_data["tw_0050_1_3_momentum"] = calc_filter_momentum("0050.TW", "台灣50")
    final_json_data["twii_1_3_momentum"] = calc_filter_momentum("^TWII", "台灣加權")

    with open("momentum_history.json", 'w', encoding='utf-8') as f:
        json.dump(final_json_data, f, ensure_ascii=False, indent=4)
        
    with open("all_tickers.json", 'w', encoding='utf-8') as f:
        json.dump(tickers_list_data, f, ensure_ascii=False, indent=4)
        
    print("\n=== 執行完畢！資料已成功儲存 ===")

if __name__ == "__main__":
    main()
