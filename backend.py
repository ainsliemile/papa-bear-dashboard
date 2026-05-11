import yfinance as yf
import pandas as pd
import requests
import json
import warnings
import io
import os
from bs4 import BeautifulSoup
from datetime import datetime
warnings.filterwarnings('ignore')

# ==========================================
# 1. 抓取邏輯 (維持不變，從 Excel 讀取)
# ==========================================
def get_0050_tickers():
    try:
        url = "https://www.yuantaetfs.com/product/detail/0050/ratio"
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=10)
        tables = pd.read_html(response.text)
        for t in tables:
            if '商品代碼' in t.columns:
                tickers = t['商品代碼'].astype(str).tolist()
                return [f"{t}.TW" for t in tickers if len(t) == 4 and t.isdigit()]
    except Exception as e:
        print(f"動態抓取 0050 失敗，切換為備用清單: {e}")
    return ["2330.TW", "2317.TW", "2454.TW", "2382.TW", "2308.TW"]

def get_sp100_tickers():
    try:
        url = 'https://en.wikipedia.org/wiki/S%26P_100'
        tables = pd.read_html(url)
        for t in tables:
            if 'Symbol' in t.columns:
                return t['Symbol'].str.replace('.', '-', regex=False).tolist()
    except Exception as e:
        print(f"動態抓取 S&P 100 失敗: {e}")
    return ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"]

def get_crypto_tickers():
    stablecoins = ['usdt', 'usdc', 'dai', 'fdusd', 'pyusd', 'usds', 'tusd', 'ustc']
    tickers = []
    try:
        url = "https://api.coingecko.com/api/v3/coins/markets"
        params = {'vs_currency': 'usd', 'order': 'market_cap_desc', 'per_page': 50}
        data = requests.get(url, params=params, timeout=10).json()
        for coin in data:
            if coin['symbol'].lower() not in stablecoins:
                tickers.append(f"{coin['symbol'].upper()}-USD")
            if len(tickers) == 30: break
    except Exception as e:
        print(f"動態抓取虛擬貨幣失敗: {e}")
        tickers = ["BTC-USD", "ETH-USD", "SOL-USD"]
    if "LUNC-USD" not in tickers:
        tickers.append("LUNC-USD")
    return tickers

def get_tickers_from_local_excel():
    file_path = "TrackingList.xlsx"
    print(f"\n=== 正在嘗試從本地檔案 {file_path} 讀取 A 欄標的 ===")
    
    categories_map = {
        "TW_STOCKS_0050": "台灣股票",
        "TW_ETFS": "台灣ETF",
        "US_STOCKS_SP100": "美國股票",
        "US_ETFS": "美國ETF",
        "CRYPTOCURRENCY": "虛擬貨幣"
    }
    
    result = {k: [] for k in categories_map.keys()}
    
    if not os.path.exists(file_path):
        print(f"⚠️ 找不到檔案: {file_path}，將使用備用清單機制。")
        return result

    try:
        excel_data = pd.read_excel(file_path, sheet_name=None, header=None)
        
        for cat_key, sheet_name in categories_map.items():
            if sheet_name in excel_data:
                df = excel_data[sheet_name]
                if len(df.columns) > 0:
                    raw_tickers = df.iloc[:, 0].astype(str).tolist()
                else:
                    raw_tickers = []
                    
                cleaned_tickers = []
                for val in raw_tickers:
                    val = str(val).strip().upper()
                    if val in ['NAN', '', 'NONE']: continue
                    if any('\u4e00' <= char <= '\u9fff' for char in val): continue
                    
                    if cat_key in ['TW_STOCKS_0050', 'TW_ETFS']:
                        if not val.endswith('.TW') and not val.endswith('.TWO'):
                            val = f"{val}.TW"
                    elif cat_key == 'CRYPTOCURRENCY':
                        if not val.endswith('-USD'):
                            val = f"{val}-USD"
                            
                    cleaned_tickers.append(val)
                result[cat_key] = list(set(cleaned_tickers))
                print(f"[{sheet_name}] 成功從本地 Excel 載入 {len(result[cat_key])} 檔")
    except Exception as e:
        print(f"讀取本地 Excel {file_path} 發生錯誤: {e}")
    return result

# 備用清單
TW_ETFS = ["0050.TW", "0056.TW"]
US_SECTORS = ["XLK"]
US_ETFS = ["VOO", "QQQ"]

# ==========================================
# 2. 動能計算核心演算法 (加入動態週期與還原權息)
# ==========================================
def calculate_historical_momentum(tickers, category_name):
    print(f"\n[{category_name}] 開始下載資料 (共 {len(tickers)} 檔)...")
    data = yf.download(tickers, period="2y", progress=False)
    if data.empty:
        return {}, []
    
    # 🌟 核心修改：使用 'Adj Close' 處理除權息與股票分割問題
    if isinstance(data.columns, pd.MultiIndex):
        if 'Adj Close' in data.columns.levels[0]:
            prices = data['Adj Close']
        else:
            prices = data['Close'] # 防呆：如果 API 沒給 Adj Close 就退回 Close
    else:
        # 單一標的的情況
        prices_col = 'Adj Close' if 'Adj Close' in data.columns else 'Close'
        prices = pd.DataFrame(data[prices_col], columns=[tickers[0]])
    
    prices = prices.ffill().resample('D').ffill()
    
    # 🌟 核心修改：依據不同市場屬性，設定最佳化動能週期 (日曆天)
    if category_name in ["TW_ETFS", "US_ETFS"]:
        p1, p2, p3 = 90, 180, 365  # ETF：看長線趨勢 (3, 6, 12 個月)
    elif category_name in ["TW_STOCKS_0050", "US_STOCKS_SP100"]:
        p1, p2, p3 = 30, 90, 180   # 股票：看中線爆發 (1, 3, 6 個月)
    elif category_name == "CRYPTOCURRENCY":
        p1, p2, p3 = 14, 30, 90    # 幣圈：看極短線動能 (2週, 1, 3 個月)
    else:
        p1, p2, p3 = 90, 180, 365

    print(f"[{category_name}] 使用動態週期: {p1}天, {p2}天, {p3}天")
    
    m1 = prices.pct_change(periods=p1)
    m2 = prices.pct_change(periods=p2)
    m3 = prices.pct_change(periods=p3)
    
    avg_momentum = (m1 + m2 + m3) / 3
    
    monthly_momentum = avg_momentum.resample('ME').last()
    last_12_months = monthly_momentum.tail(12)
    
    history_result = {}
    for date, row in last_12_months.iterrows():
        month_str = date.strftime('%Y-%m')
        valid_ranks = row.dropna().sort_values(ascending=False)
        top3 = valid_ranks.head(3)
        top3_list = [{"symbol": s, "momentum": round(v * 100, 2)} for s, v in top3.items()]
        history_result[month_str] = top3_list
        
    latest_row = avg_momentum.iloc[-1].dropna().sort_values(ascending=False)
    current_all = [{"symbol": s, "momentum": round(v * 100, 2)} for s, v in latest_row.items()]
        
    return history_result, current_all

# ==========================================
# 3. 主程式整合
# ==========================================
def main():
    print("=== Papa Bear 跨市場動能監控系統 (最佳化週期版) ===")
    
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
            if month not in final_json_data["history"]:
                final_json_data["history"][month] = {}
            final_json_data["history"][month][cat_key] = top3_list

    with open("momentum_history.json", 'w', encoding='utf-8') as f:
        json.dump(final_json_data, f, ensure_ascii=False, indent=4)
        
    with open("all_tickers.json", 'w', encoding='utf-8') as f:
        json.dump(tickers_list_data, f, ensure_ascii=False, indent=4)
        
    print("\n=== 執行完畢！資料已儲存 ===")

if __name__ == "__main__":
    main()
