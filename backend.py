import yfinance as yf
import pandas as pd
import requests
import json
import warnings
from bs4 import BeautifulSoup
from datetime import datetime
warnings.filterwarnings('ignore') # 隱藏 pandas 未來版本警告

# ==========================================
# 1. 動態抓取與靜態清單定義區
# ==========================================

def get_0050_tickers():
    """動態抓取 0050 成分股，若失敗則使用靜態完整清單"""
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
    
    # 備用 0050 完整清單 (市值前 50 大)
    return [
        "2330.TW", "2317.TW", "2454.TW", "2382.TW", "2308.TW", "2881.TW", "2412.TW", "2882.TW", "2303.TW", "2891.TW",
        "3711.TW", "2886.TW", "2884.TW", "1216.TW", "2885.TW", "2002.TW", "2892.TW", "3231.TW", "2880.TW", "2345.TW",
        "2357.TW", "2379.TW", "2883.TW", "5880.TW", "2301.TW", "3045.TW", "2912.TW", "2395.TW", "2887.TW", "2603.TW",
        "1301.TW", "1303.TW", "2327.TW", "2207.TW", "2890.TW", "6669.TW", "3034.TW", "2352.TW", "4904.TW", "5871.TW",
        "1101.TW", "2408.TW", "2353.TW", "6505.TW", "2609.TW", "1590.TW", "1326.TW", "9910.TW", "2801.TW", "5876.TW"
    ]

def get_sp100_tickers():
    """從維基百科抓取 S&P 100 成分股"""
    try:
        url = 'https://en.wikipedia.org/wiki/S%26P_100'
        tables = pd.read_html(url)
        for t in tables:
            if 'Symbol' in t.columns:
                return t['Symbol'].str.replace('.', '-', regex=False).tolist()
    except Exception as e:
        print(f"動態抓取 S&P 100 失敗，切換為備用清單: {e}")
    
    # 備用 S&P 100 核心龍頭清單 (節錄)
    return ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "BRK-B", "UNH", "JPM", "LLY", "V", "MA", "AVGO", "HD", "PG", "COST", "ABBV", "ADBE", "CRM"]

def get_crypto_tickers():
    """透過 CoinGecko 抓取前 30 大虛擬貨幣，排除穩定幣"""
    stablecoins = ['usdt', 'usdc', 'dai', 'fdusd', 'pyusd', 'usds', 'tusd', 'ustc']
    tickers = []
    try:
        url = "https://api.coingecko.com/api/v3/coins/markets"
        params = {'vs_currency': 'usd', 'order': 'market_cap_desc', 'per_page': 50}
        data = requests.get(url, params=params, timeout=10).json()
        
        for coin in data:
            if coin['symbol'].lower() not in stablecoins:
                tickers.append(f"{coin['symbol'].upper()}-USD")
            if len(tickers) == 30: 
                break
    except Exception as e:
        print(f"動態抓取虛擬貨幣失敗，切換為備用清單: {e}")
        tickers = ["BTC-USD", "ETH-USD", "BNB-USD", "SOL-USD", "XRP-USD", "ADA-USD", "DOGE-USD", "AVAX-USD", "TRX-USD", "DOT-USD", "LINK-USD", "MATIC-USD", "TON-USD", "SHIB-USD", "LTC-USD"]
    
    # 強制加入 LUNC
    if "LUNC-USD" not in tickers:
        tickers.append("LUNC-USD")
    return tickers

# 完整靜態清單定義
TW_ETFS = [
    # 藍籌與市值
    "006208.TW", "0051.TW", "00692.TW", "00850.TW", "00922.TW", "00923.TW", "00646.TW",
    # 科技與半導體
    "0052.TW", "0053.TW", "00830.TW", "00891.TW", "00892.TW", "00927.TW", "00757.TW", "00662.TW", "00935.TW", "00881.TW",
    # 高股息與低波
    "00713.TW", "00878.TW", "00919.TW", "00929.TW", "00915.TW", "0056.TW", "00934.TW", "00940.TW",
    # 能源、商品與原物料
    "00642U.TW", "00763U.TW", "00635U.TW", "00738U.TW", "00730.TW", "00938.TW",
    # 海外、債券與房地產
    "00679B.TW", "00751B.TW", "00720B.TW", "00712.TW", "00937B.TW", "00687B.TW", "00661.TW", "00652.TW", "00660.TW"
]

US_SECTORS = ["XLK", "XLF", "XLV", "XLY", "XLP", "XLE", "XLI", "XLB", "XLU", "XLRE", "XLC"]

US_ETFS = [
    # 核心與風格
    "VOO", "VTI", "QQQ", "VTV", "VUG", "IWM", "VIOV", "VIOG", "VEA", "VWO", "VGK", "EWJ", "MCHI", "AAXJ", "DIA",
    # 特定產業與主題
    "SMH", "IBB", "KRE", "XHB", "VNQ", "XME", "PICK", "LIT", "TAN", "BOTZ", "CLOU", "CIBR", "WCLD", "HACK", "MJ",
    # AI與能源基礎設施 (受惠於資料中心電力需求)
    "UTES", "GRID", "NLR", "URNM",
    # 礦業(實體產出)
    "GDX", "GDXJ", "SIL", "SILJ", "SLVR",
    # 商品與避險債券
    "IAU", "SLV", "PDBC", "USO", "DBA", "BND", "TLT", "IEF", "TIP", "BIL",
    # 槓桿型
    "TQQQ", "UPRO", "SOXL", "TNA", "TECL", "FNGU", "UGL", "YINN", "TMF", "LABU"
]


# ==========================================
# 2. 動能計算核心演算法 (Papa Bear)
# ==========================================

def calculate_historical_momentum(tickers, category_name):
    print(f"\n[{category_name}] 開始下載資料 (共 {len(tickers)} 檔)...")
    # 為了計算過去12個月的「12個月動能」，我們需要 2 年 (24個月) 的歷史資料
    data = yf.download(tickers, period="2y", progress=False)
    
    if data.empty:
        print("下載資料失敗！")
        return {}, []
        
    # 如果只有一檔標的，yfinance 不會回傳 MultiIndex，需做防呆處理
    if isinstance(data.columns, pd.MultiIndex):
        prices = data['Close']
    else:
        prices = pd.DataFrame(data['Close'], columns=[tickers[0]])
        
    # 填補空缺值 (避免停牌或剛上市標的報錯)
    prices = prices.ffill()

    # ==========================================
    # 核心修改：統一時間軸為「日曆天」，解決加密貨幣與股市交易日不同的問題
    # 將資料重取樣為每一天 (D)，遇到休市日則沿用前一天的價格
    # ==========================================
    prices = prices.resample('D').ffill()

    print(f"[{category_name}] 計算 3, 6, 12 個月動能指標...")
    # 使用日曆天數計算報酬率 (3個月=90天, 6個月=180天, 12個月=365天)
    m3 = prices.pct_change(periods=90)
    m6 = prices.pct_change(periods=180)
    m12 = prices.pct_change(periods=365)
    
    # 計算 Papa Bear 動能公式: (3M + 6M + 12M) / 3
    avg_momentum = (m3 + m6 + m12) / 3
    
    # 將資料重取樣為「每個月底」 (ME = Month End)
    monthly_momentum = avg_momentum.resample('ME').last()
    
    # 取最近 12 個月的資料
    last_12_months = monthly_momentum.tail(12)
    
    history_result = {}
    
    for date, row in last_12_months.iterrows():
        month_str = date.strftime('%Y-%m')
        # 移除 NaN 值並降冪排序
        valid_ranks = row.dropna().sort_values(ascending=False)
        
        # 取前三名
        top3 = valid_ranks.head(3)
        
        # 格式化輸出清單
        top3_list = []
        for symbol, val in top3.items():
            top3_list.append({
                "symbol": symbol,
                "momentum": round(val * 100, 2) # 轉換為百分比並取到小數第二位
            })
        
        history_result[month_str] = top3_list
        
    # ==========================================
    # 核心修改：新增當月所有標的完整排名
    # 取資料集最後一天的所有動能數據
    # ==========================================
    latest_row = avg_momentum.iloc[-1].dropna().sort_values(ascending=False)
    current_all = []
    for symbol, val in latest_row.items():
        current_all.append({
            "symbol": symbol,
            "momentum": round(val * 100, 2)
        })
        
    return history_result, current_all

# ==========================================
# 3. 主程式整合
# ==========================================

def main():
    print("=== Papa Bear 跨市場動能監控系統開始執行 ===")
    
    # 彙整 5 大類別清單
    categories = {
        "TW_STOCKS_0050": get_0050_tickers(),
        "TW_ETFS": TW_ETFS,
        "US_STOCKS_SP100": get_sp100_tickers() + US_SECTORS,
        "US_ETFS": US_ETFS,
        "CRYPTOCURRENCY": get_crypto_tickers()
    }
    
    # 修改輸出的 JSON 結構，分為歷史與當月完整名單
    final_json_data = {
        "history": {},
        "current_all": {}
    }
    
    # 依序計算每一個類別
    for cat_key, tickers in categories.items():
        # 清除可能重複的代碼
        unique_tickers = list(set(tickers))
        
        history_res, current_all_res = calculate_historical_momentum(unique_tickers, cat_key)
        
        # 填入當月完整排名
        final_json_data["current_all"][cat_key] = current_all_res
        
        # 重組歷史資料結構：以月份為主鍵，再分子類別
        for month, top3_list in history_res.items():
            if month not in final_json_data["history"]:
                final_json_data["history"][month] = {}
            final_json_data["history"][month][cat_key] = top3_list

    # 將結果寫入 JSON 檔案供前端網頁讀取
    output_filename = "momentum_history.json"
    with open(output_filename, 'w', encoding='utf-8') as f:
        json.dump(final_json_data, f, ensure_ascii=False, indent=4)
        
    print(f"\n=== 執行完畢！結果已儲存至 {output_filename} ===")
    
    # 預覽最近一個月的結果
    latest_month = sorted(final_json_data["history"].keys())[-1]
    print(f"\n[預覽] 最新月份 ({latest_month}) 前三名:")
    print(json.dumps(final_json_data["history"][latest_month], indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
