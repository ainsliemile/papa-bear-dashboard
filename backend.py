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
from datetime import datetime, timezone, timedelta

warnings.filterwarnings('ignore')

session = requests.Session()
retry = Retry(connect=3, backoff_factor=0.5)
adapter = HTTPAdapter(max_retries=retry)
session.mount('http://', adapter)
session.mount('https://', adapter)
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
})

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
        # 🔥 加入 dtype=str，強制將所有儲存格讀成文字，避免數字被 pandas 加上 .0
        excel_data = pd.read_excel(file_path, sheet_name=None, header=None, dtype=str)
        
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
                    
                    # 🔥 二重防護：如果發現結尾有 .0，直接切除
                    if val.endswith('.0'):
                        val = val[:-2]
                        
                    if val in ['NAN', '', 'NONE', 'NULL', 'LIST', 'NOTE', '代碼', '標的']: continue
                    
                    match = re.search(r'[A-Z0-9\.\-]+', val)
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

def download_robustly(tickers):
    print(f"   -> 準備「超穩定安全下載」 {len(tickers)} 檔標的資料...")
    all_prices = {}
    
    for i, ticker in enumerate(tickers, 1):
        try:
            tkr = yf.Ticker(ticker)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                data = tkr.history(period="2y", auto_adjust=True)
            
            # 🔥 智能後綴轉換與正名機制
            actual_ticker = ticker
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
                        # 成功抓到備用代號，將真實代號更新為 .TWO (或其他 fallback)
                        actual_ticker = fallback_ticker

            if not data.empty and 'Close' in data.columns:
                p = data['Close']
                if isinstance(p, pd.DataFrame):
                    p = p.iloc[:, 0]
                
                if p.index.tz is not None:
                    p.index = p.index.tz_localize(None)
                    
                # 使用確定有資料的 actual_ticker (.TW 或 .TWO) 儲存
                all_prices[actual_ticker] = p
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

def calculate_historical_momentum(tickers, category_name):
    print(f"\n[{category_name}] 開始處理...")
    
    prices = download_robustly(tickers)
    
    if prices.empty or prices.shape[1] == 0:
        print(f"⚠️ 警告：{category_name} 抓不到任何價格資料！")
        return {}, []
    
    # 使用「每月最後一個交易日」還原收盤價結算
    monthly_prices = prices.resample('ME').last()
    
    # 嚴格計算 1個月、3個月、6個月的「月底對月底」動能
    m1 = monthly_prices.pct_change(periods=1)
    m3 = monthly_prices.pct_change(periods=3)
    m6 = monthly_prices.pct_change(periods=6)
    
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        avg_momentum_values = np.nanmean([m1.values, m3.values, m6.values], axis=0)
        
    monthly_momentum = pd.DataFrame(avg_momentum_values, index=monthly_prices.index, columns=monthly_prices.columns)
    last_12_months = monthly_momentum.tail(12)
    
    history_result = {}
    for date, row in last_12_months.iterrows():
        month_str = date.strftime('%Y-%m')
        valid_ranks = row.dropna().sort_values(ascending=False)
        month_data = []
        for s, v in valid_ranks.items():
            price = monthly_prices.at[date, s]
            price_val = round(price, 2) if pd.notna(price) else 0.0
            month_data.append({"symbol": s, "momentum": round(v * 100, 2), "price": price_val})
        history_result[month_str] = month_data
        
    latest_row = monthly_momentum.iloc[-1].dropna().sort_values(ascending=False)
    latest_date = monthly_momentum.index[-1]
    current_all = []
    for s, v in latest_row.items():
        price = monthly_prices.at[latest_date, s]
        price_val = round(price, 2) if pd.notna(price) else 0.0
        current_all.append({"symbol": s, "momentum": round(v * 100, 2), "price": price_val})
        
    return history_result, current_all

# 🔥 新增輔助模組：專門用來計算四大指數的 1+3 濾網
def calc_filter_momentum(ticker, name):
    print(f"\n=== 計算大盤防護濾網 {name}(1+3月) ===")
    data = download_robustly([ticker])
    fast_mom = 0.0
    if not data.empty and ticker in data.columns:
        monthly = data[ticker].resample('ME').last()
        try:
            m1 = monthly.pct_change(periods=1).iloc[-1]
            m3 = monthly.pct_change(periods=3).iloc[-1]
            fast_mom = ((m1 + m3) / 2) * 100
            print(f"🔥 最新 {name} 濾網: {fast_mom:.2f}%")
        except: pass
    return round(fast_mom, 2)

def main():
    print("=== Papa Bear 跨市場動能監控系統 (綜合排名版) ===")
    
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
    
    # 強制設定為台灣時間 (UTC+8)
    tw_tz = timezone(timedelta(hours=8))
    
    final_json_data = {
        "update_time": datetime.now(tw_tz).strftime("%Y-%m-%d %H:%M"), 
        "spy_1_3_momentum": 0.0,
        "spy_1_3_momentum": 0.0, 
        "tw_0050_1_3_momentum": 0.0,
        "sox_1_3_momentum": 0.0,  
        "twii_1_3_momentum": 0.0, 
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
            final_json_data["history"][month][cat_key] = all_list[:5]
            global_history[month].extend(all_list)

    global_current_sorted = sorted(global_current, key=lambda x: x['momentum'], reverse=True)
    final_json_data["current_all"]["ALL_ASSETS"] = global_current_sorted[:30] 
    
    for month, items in global_history.items():
        sorted_items = sorted(items, key=lambda x: x['momentum'], reverse=True)
        final_json_data["history"][month]["ALL_ASSETS"] = sorted_items[:10]

    # 🔥 統一呼叫模組，計算四個大盤指標
    final_json_data["spy_1_3_momentum"] = calc_filter_momentum("SPY", "標普500 (SPY)")
    final_json_data["tw_0050_1_3_momentum"] = calc_filter_momentum("0050.TW", "台灣50 (0050)")
    final_json_data["sox_1_3_momentum"] = calc_filter_momentum("^SOX", "費城半導體 (^SOX)")
    final_json_data["twii_1_3_momentum"] = calc_filter_momentum("^TWII", "台灣加權 (^TWII)")

    # 寫入更新後的 JSON 資料
    with open("momentum_history.json", 'w', encoding='utf-8') as f:
        json.dump(final_json_data, f, ensure_ascii=False, indent=4)
        
    with open("all_tickers.json", 'w', encoding='utf-8') as f:
        json.dump(tickers_list_data, f, ensure_ascii=False, indent=4)
        
    print("\n=== 執行完畢！資料已成功儲存 ===")

if __name__ == "__main__":
    main()
