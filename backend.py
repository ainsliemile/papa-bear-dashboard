import yfinance as yf
import pandas as pd
import numpy as np
import requests
import json
import warnings
import io
import os
import re
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from datetime import datetime

warnings.filterwarnings('ignore')

# 建立給一般網頁用的 Session
session = requests.Session()
retry = Retry(connect=3, backoff_factor=0.5)
adapter = HTTPAdapter(max_retries=retry)
session.mount('http://', adapter)
session.mount('https://', adapter)
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
})

# ==========================================
# 1. 抓取邏輯 (強化 Excel 解析)
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
        print(f"⚠️ 找不到檔案: {file_path}，將使用備用清單。")
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
                    if val in ['NAN', '', 'NONE', 'NULL']: continue
                    
                    match = re.search(r'[A-Z0-9\.\-]+', val)
                    if not match: continue
                    ticker = match.group(0)
                    
                    if cat_key in ['TW_STOCKS_0050', 'TW_ETFS']:
                        if not ticker.endswith('.TW') and not ticker.endswith('.TWO'): ticker = f"{ticker}.TW"
                    elif cat_key == 'CRYPTOCURRENCY':
                        if not ticker.endswith('-USD'): ticker = f"{ticker}-USD"
                        
                    cleaned_tickers.append(ticker)
                    
                result[cat_key] = list(set(cleaned_tickers))
                print(f"[{matched_sheet}] 成功從 Excel 載入 {len(result[cat_key])} 檔")
            else:
                print(f"⚠️ 找不到符合 {allowed_names[0]} 的工作表")
    except Exception as e:
        print(f"讀取 Excel 發生錯誤: {e}")
    return result

TW_ETFS = ["0050.TW", "0056.TW"]
US_SECTORS = ["XLK"]
US_ETFS = ["VOO", "QQQ"]

# ==========================================
# 2. 核心技術：一次性批次下載 (Bulk Download) 避開阻擋
# ==========================================
def download_robustly(tickers):
    print(f"   -> 準備「一次性批次下載」 {len(tickers)} 檔標的資料...")
    try:
        # yf.download 支援一次傳入 list，Yahoo 只會算 1 次請求，能完美避開防機器人阻擋
        data = yf.download(tickers, period="2y", progress=False)
        
        if data.empty:
            print("      ⚠️ 無資料回傳")
            return pd.DataFrame()
            
        if isinstance(data.columns, pd.MultiIndex):
            # 取出 Adj Close 或是 Close 欄位
            if 'Adj Close' in data.columns.get_level_values(0):
                p = data['Adj Close']
            elif 'Close' in data.columns.get_level_values(0):
                p = data['Close']
            else:
                p = data.iloc[:, data.columns.get_level_values(0) == data.columns.get_level_values(0)[0]]
        else:
            # 如果只有單一檔，yfinance 不會給 MultiIndex
            p_col = 'Adj Close' if 'Adj Close' in data.columns else 'Close'
            if p_col in data.columns:
                p = pd.DataFrame(data[p_col])
                p.columns = [tickers[0]]
            else:
                p = data

        # 確保取出來的是 DataFrame 並且數值正確
        if isinstance(p, pd.Series):
            p = pd.DataFrame(p)
            p.columns = [tickers[0]]

        # 強制轉為數值，並過濾掉全部都是 NaN 的無效標的（例如打錯代碼的）
        p = p.apply(pd.to_numeric, errors='coerce')
        p.dropna(axis=1, how='all', inplace=True)
        print(f"      ✅ 成功下載 {len(p.columns)} 檔有效歷史數據！")
        return p
        
    except Exception as e:
        print(f"      ❌ 批次下載失敗 ({e})")
        return pd.DataFrame()

# ==========================================
# 3. 動能計算核心演算法 (智能容錯版)
# ==========================================
def calculate_historical_momentum(tickers, category_name):
    print(f"\n[{category_name}] 開始處理 (清單共 {len(tickers)} 檔)...")
    
    prices = download_robustly(tickers)
    
    if prices.empty or prices.shape[1] == 0:
        print(f"⚠️ 警告：{category_name} 抓不到任何價格資料！")
        return {}, []
    
    prices = prices.ffill().resample('D').ffill()
    
    if category_name in ["TW_ETFS", "US_ETFS"]: p1, p2, p3 = 90, 180, 365
    elif category_name in ["TW_STOCKS_0050", "US_STOCKS_SP100"]: p1, p2, p3 = 30, 90, 180
    elif category_name == "CRYPTOCURRENCY": p1, p2, p3 = 14, 30, 90
    else: p1, p2, p3 = 90, 180, 365

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
        top3 = valid_ranks.head(3)
        history_result[month_str] = [{"symbol": s, "momentum": round(v * 100, 2)} for s, v in top3.items()]
        
    latest_row = avg_momentum.iloc[-1].dropna().sort_values(ascending=False)
    current_all = [{"symbol": s, "momentum": round(v * 100, 2)} for s, v in latest_row.items()]
        
    return history_result, current_all

# ==========================================
# 4. 主程式整合
# ==========================================
def main():
    print("=== Papa Bear 跨市場動能監控系統 (終極批次下載版) ===")
    
    excel_data = get_tickers_from_local_excel()
    fallback_categories = {
        "TW_STOCKS_0050": get_0050_tickers(),
        "TW_ETFS": TW_ETFS,
        "US_STOCKS_SP100": get_sp100_tickers() + US_SECTORS,
        "US_ETFS": US_ETFS,
        "CRYPTOCURRENCY": get_crypto_tickers()
    }
    
    categories = {}
    for cat_key in fallback_categories.keys():
        if excel_data and len(excel_data.get(cat_key, [])) > 0:
            categories[cat_key] = excel_data[cat_key]
        else:
            categories[cat_key] = fallback_categories[cat_key]
    
    final_json_data = {"history": {}, "current_all": {}}
    tickers_list_data = {}
    
    for cat_key, tickers in categories.items():
        unique_tickers = sorted(list(set(tickers)))
        tickers_list_data[cat_key] = unique_tickers
        
        history_res, current_all_res = calculate_historical_momentum(unique_tickers, cat_key)
        final_json_data["current_all"][cat_key] = current_all_res
        
        for month, top3_list in history_res.items():
            if month not in final_json_data["history"]: final_json_data["history"][month] = {}
            final_json_data["history"][month][cat_key] = top3_list

    with open("momentum_history.json", 'w', encoding='utf-8') as f:
        json.dump(final_json_data, f, ensure_ascii=False, indent=4)
        
    with open("all_tickers.json", 'w', encoding='utf-8') as f:
        json.dump(tickers_list_data, f, ensure_ascii=False, indent=4)
        
    print("\n=== 執行完畢！資料已成功儲存 ===")

if __name__ == "__main__":
    main()
