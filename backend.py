import os
import glob
import json
import pandas as pd
import yfinance as yf
import numpy as np
from datetime import datetime
import warnings

warnings.filterwarnings('ignore')

def get_tickers_from_excel():
    """
    自動讀取目錄下 TrackingList 相關的 .xlsx 檔案，
    並依據工作表 (Sheet) 名稱建立分類字典。
    """
    categories = {}
    excel_files = glob.glob("*TrackingList*.xlsx")
    
    for file in excel_files:
        try:
            # 讀取 Excel 檔內的所有工作表 (sheet_name=None 會回傳一個 dict)
            xls = pd.read_excel(file, sheet_name=None)
            for sheet_name, df in xls.items():
                # 尋找包含股票代號的欄位 (支援多種常見命名)
                col = None
                for c in ['Symbol', 'Ticker', '代號', 'ticker', 'symbol']:
                    if c in df.columns:
                        col = c
                        break
                if not col and not df.empty:
                    col = df.columns[0] # 若找不到，預設抓第一欄
                
                if col:
                    # 清理資料並存入
                    tickers = df[col].dropna().astype(str).str.strip().tolist()
                    valid_tickers = [t for t in tickers if t]
                    if valid_tickers:
                        categories[sheet_name] = valid_tickers
        except Exception as e:
            print(f"Error reading {file}: {e}")
            
    return categories

def main():
    print("1. Parsing Excel files...")
    categories = get_tickers_from_excel()
    
    # 若找不到 Excel，嘗試讀取 all_tickers.json 作為備案
    if not categories and os.path.exists('all_tickers.json'):
        with open('all_tickers.json', 'r', encoding='utf-8') as f:
            categories = json.load(f)
            
    # 彙整所有獨立的股票代號
    all_tickers = set()
    for cat, tickers in categories.items():
        all_tickers.update(tickers)
        
    # 🔥 強制將大盤 SPY 加入下載清單，作為避險濾網計算基準
    all_tickers.add('SPY')
    all_tickers = list(all_tickers)
    
    print(f"2. Downloading data for {len(all_tickers)} tickers...")
    # 下載 1 年的歷史資料以確保能計算 6 個月回報率
    data = yf.download(all_tickers, period="1y", progress=False)['Close']
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)
        
    print("3. Calculating Momentum...")
    # 取每月月底的收盤價
    try:
        df_m = data.resample('ME').last()
    except:
        df_m = data.resample('M').last()
        
    # 計算 1個月、3個月、6個月的回報率
    ret1 = df_m.pct_change(1).iloc[-1]
    ret3 = df_m.pct_change(3).iloc[-1]
    ret6 = df_m.pct_change(6).iloc[-1]
    
    # 計算選股用的原始動能 (1+3+6)/3，轉為百分比
    mom_score = ((ret1 + ret3 + ret6) / 3) * 100
    
    # 🚨 計算系統核心預警濾網：SPY(1+3) 敏銳動能
    spy_fast_mom = 0.0
    if 'SPY' in df_m.columns:
        spy_fast_mom = ((ret1['SPY'] + ret3['SPY']) / 2) * 100

    print(f"🔥 最新 SPY(1+3) 避險濾網數值: {spy_fast_mom:.2f}%")
    
    print("4. Building JSON payload...")
    output_data = {
        "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "spy_1_3_momentum": float(spy_fast_mom) if not pd.isna(spy_fast_mom) else 0.0,
        "categories": {}
    }
    
    # 將計算結果分類包裝
    for cat, tickers in categories.items():
        cat_list = []
        for t in tickers:
            if t in df_m.columns and not pd.isna(mom_score.get(t)):
                cat_list.append({
                    "ticker": t,
                    "momentum": float(mom_score[t]),
                    "ret1": float(ret1[t] * 100) if not pd.isna(ret1.get(t)) else 0.0,
                    "ret3": float(ret3[t] * 100) if not pd.isna(ret3.get(t)) else 0.0,
                    "ret6": float(ret6[t] * 100) if not pd.isna(ret6.get(t)) else 0.0,
                    "price": float(df_m[t].iloc[-1]) if not pd.isna(df_m[t].iloc[-1]) else 0.0
                })
        # 依據動能分數由高到低排序 (Top 5 妖股會在最前面)
        cat_list.sort(key=lambda x: x['momentum'], reverse=True)
        output_data["categories"][cat] = cat_list
        
    # 寫入結果供前端 index.html 讀取
    with open('momentum_history.json', 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=4)
        
    print("✅ Success! momentum_history.json generated successfully.")

if __name__ == "__main__":
    main()
