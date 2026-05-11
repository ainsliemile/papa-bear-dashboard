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
# 1. 動態抓取與靜態清單定義區
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
    return [
        "2330.TW", "2317.TW", "2454.TW", "2382.TW", "2308.TW", "2881.TW", "2412.TW", "2882.TW", "2303.TW", "2891.TW",
        "3711.TW", "2886.TW", "2884.TW", "1216.TW", "2885.TW", "2002.TW", "2892.TW", "3231.TW", "2880.TW", "2345.TW",
        "2357.TW", "2379.TW", "2883.TW", "5880.TW", "2301.TW", "3045.TW", "2912.TW", "2395.TW", "2887.TW", "2603.TW",
        "1301.TW", "1303.TW", "2327.TW", "2207.TW", "2890.TW", "6669.TW", "3034.TW", "2352.TW", "4904.TW", "5871.TW",
        "1101.TW", "2408.TW", "2353.TW", "6505.TW", "2609.TW", "1590.TW", "1326.TW", "9910.TW", "2801.TW", "5876.TW"
    ]

def get_sp100_tickers():
    try:
        url = 'https://en.wikipedia.org/wiki/S%26P_100'
        tables = pd.read_html(url)
        for t in tables:
            if 'Symbol' in t.columns:
                return t['Symbol'].str.replace('.', '-', regex=False).tolist()
    except Exception as e:
        print(f"動態抓取 S&P 100 失敗，切換為備用清單: {e}")
    return ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "BRK-B", "UNH", "JPM", "LLY", "V", "MA", "AVGO", "HD", "PG", "COST", "ABBV", "ADBE", "CRM"]

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
        print(f"動態抓取虛擬貨幣失敗，切換為備用清單: {e}")
        tickers = ["BTC-USD", "ETH-USD", "BNB-USD", "SOL-USD", "XRP-USD", "ADA-USD", "DOGE-USD", "AVAX-USD", "TRX-USD", "DOT-USD", "LINK-USD", "MATIC-USD", "TON-USD", "SHIB-USD", "LTC-USD"]
    if "LUNC-USD" not in tickers:
        tickers.append("LUNC-USD")
    return tickers

def get_tickers_from_local_excel():
    """直接從 GitHub 儲存庫內的 TrackingList.xlsx 讀取標的清單"""
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
        # 使用 pandas 讀取 Excel 檔案，讀取所有工作表
        excel_data = pd.read_excel(file_path, sheet_name=None, header=None)
        
        for cat_key, sheet_name in categories_map.items():
            if sheet_name in excel_data:
                df = excel_data[sheet_name]
                
                # 因為 A1 通常是標題，我們從 A 欄讀取所有資料，稍後再過濾
                # 假設資料在第一欄 (index 0)
                if len(df.columns) > 0:
                    raw_tickers = df.iloc[:, 0].astype(str).tolist()
                else:
                    raw_tickers = []
                    
                cleaned_tickers = []
                for val in raw_tickers:
                    val = str(val).strip().upper()
                    
                    # 排除空值與無效字串 (包含可能為標題的 "NAN")
                    if val in ['NAN', '', 'NONE']: continue
                    # 排除任何含有中文字的欄位 (過濾掉 A1 的標題或註解)
                    if any('\u4e00' <= char <= '\u9fff' for char in val): continue
                    
                    # 依據不同類別做代碼正規化 (自動補後綴)
                    if cat_key in ['TW_STOCKS_0050', 'TW_ETFS']:
                        if not val.endswith('.TW') and not val.endswith('.TWO'):
                            val = f"{val}.TW"
                    elif cat_key == 'CRYPTOCURRENCY':
                        if not val.endswith('-USD'):
                            val = f"{val}-USD"
                            
                    cleaned_tickers.append(val)
                    
                # 去除重複項
                result[cat_key] = list(set(cleaned_tickers))
                print(f"[{sheet_name}] 成功從本地 Excel A 欄載入 {len(result[cat_key])} 檔標的")
            else:
                 print(f"⚠️ 在 {file_path} 中找不到名為 '{sheet_name}' 的工作表。")

    except Exception as e:
        print(f"讀取本地 Excel {file_path} 時發生錯誤: {e}")
            
    return result

# 備用清單
TW_ETFS = ["006208.TW", "0051.TW", "00692.TW", "00850.TW", "00922.TW", "00923.TW", "00646.TW", "0052.TW", "0053.TW", "00830.TW", "00891.TW", "00892.TW", "00927.TW", "00757.TW", "00662.TW", "00935.TW", "00881.TW", "00713.TW", "00878.TW", "00919.TW", "00929.TW", "00915.TW", "0056.TW", "00934.TW", "00940.TW", "00642U.TW", "00763U.TW", "00635U.TW", "00738U.TW", "00730.TW", "00938.TW", "00679B.TW", "00751B.TW", "00720B.TW", "00712.TW", "00937B.TW", "00687B.TW", "00661.TW", "00652.TW", "00660.TW"]
US_SECTORS = ["XLK", "XLF", "XLV", "XLY", "XLP", "XLE", "XLI", "XLB", "XLU", "XLRE", "XLC"]
US_ETFS = ["VOO", "VTI", "QQQ", "VTV", "VUG", "IWM", "VIOV", "VIOG", "VEA", "VWO", "VGK", "EWJ", "MCHI", "AAXJ", "DIA", "SMH", "IBB", "KRE", "XHB", "VNQ", "XME", "PICK", "LIT", "TAN", "BOTZ", "CLOU", "CIBR", "WCLD", "HACK", "MJ", "UTES", "GRID", "NLR", "URNM", "GDX", "GDXJ", "SIL", "SILJ", "SLVR", "IAU", "SLV", "PDBC", "USO", "DBA", "BND", "TLT", "IEF", "TIP", "BIL", "TQQQ", "UPRO", "SOXL", "TNA", "TECL", "FNGU", "UGL", "YINN", "TMF", "LABU"]

# ==========================================
# 2. 動能計算核心演算法
# ==========================================
def calculate_historical_momentum(tickers, category_name):
    print(f"\n[{category_name}] 開始下載資料 (共 {len(tickers)} 檔)...")
    data = yf.download(tickers, period="2y", progress=False)
    if data.empty:
        return {}, []
    if isinstance(data.columns, pd.MultiIndex):
        prices = data['Close']
    else:
        prices = pd.DataFrame(data['Close'], columns=[tickers[0]])
    
    prices = prices.ffill().resample('D').ffill()
    m3 = prices.pct_change(periods=90)
    m6 = prices.pct_change(periods=180)
    m12 = prices.pct_change(periods=365)
    avg_momentum = (m3 + m6 + m12) / 3
    
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
# 3. 主程式整合與資料匯出
# ==========================================
def main():
    print("=== Papa Bear 跨市場動能監控系統開始執行 ===")
    
    # 優先嘗試從本地 Excel 檔案讀取
    excel_data = get_tickers_from_local_excel()
    
    # 備用機制 (Fallback) 的預設爬蟲與名單
    fallback_categories = {
        "TW_STOCKS_0050": get_0050_tickers(),
        "TW_ETFS": TW_ETFS,
        "US_STOCKS_SP100": get_sp100_tickers() + US_SECTORS,
        "US_ETFS": US_ETFS,
        "CRYPTOCURRENCY": get_crypto_tickers()
    }
    
    categories = {}
    for cat_key in fallback_categories.keys():
        # 如果 Excel 有成功抓到該類別資料 (>0)，就使用 Excel；否則使用備用機制
        if excel_data and len(excel_data.get(cat_key, [])) > 0:
            categories[cat_key] = excel_data[cat_key]
        else:
            print(f"使用備用機制載入 [{cat_key}]")
            categories[cat_key] = fallback_categories[cat_key]
    
    final_json_data = {"history": {}, "current_all": {}}
    tickers_list_data = {} # 儲存標的清單用
    
    for cat_key, tickers in categories.items():
        unique_tickers = sorted(list(set(tickers)))
        tickers_list_data[cat_key] = unique_tickers # 存入清單
        
        history_res, current_all_res = calculate_historical_momentum(unique_tickers, cat_key)
        final_json_data["current_all"][cat_key] = current_all_res
        
        for month, top3_list in history_res.items():
            if month not in final_json_data["history"]:
                final_json_data["history"][month] = {}
            final_json_data["history"][month][cat_key] = top3_list

    # 1. 儲存動能資料
    with open("momentum_history.json", 'w', encoding='utf-8') as f:
        json.dump(final_json_data, f, ensure_ascii=False, indent=4)
        
    # 2. 儲存標的清單 (供網頁顯示驗證)
    with open("all_tickers.json", 'w', encoding='utf-8') as f:
        json.dump(tickers_list_data, f, ensure_ascii=False, indent=4)
        
    print("\n=== 執行完畢！資料已儲存 ===")

if __name__ == "__main__":
    main()
