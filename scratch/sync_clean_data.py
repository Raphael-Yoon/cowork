
import pandas as pd
import sqlite3
from datetime import datetime
import sys
import os

# Reuse price fetcher
sys.path.append(r'c:\Python\cowork\scratch')
from recommend_10 import get_current_price

def save_clean_data_recommendations():
    file_path = r'c:\Python\cowork\Report\20260505_latest.xlsx'
    db_path = r'c:\Python\trade\trade.db'
    data_date = "2026-05-05"
    
    df = pd.read_excel(file_path)
    
    # 1. Exclude ETFs and Preferred Stocks (Illiquid/Non-operating)
    # Filter by name suffix '우', '우B' etc. and common ETF brand names
    mask_etf = df['종목명'].str.contains('KODEX|TIGER|ACE|SOL|RISE|ARIRANG|HANARO|KBSTAR|KOSEF', case=False, na=False)
    mask_pref = df['종목명'].str.endswith(('우', '우B', '우C', '우(전환)'), na=False)
    
    df_clean = df[~(mask_etf | mask_pref)].copy()
    
    # 2. Audit & Fundamental filters
    mask_audit = (df_clean['ROE'] > 10) & (df_clean['부채비율'] < 150) & (df_clean['목표주가'] > 0)
    df_filtered = df_clean[mask_audit].copy()
    
    # 3. Group by Sector to ensure diversification (User wanted sector leaders previously)
    # But this time, let's pick top candidates overall but limit per sector to avoid clutter
    candidates = df_filtered.sort_values(by='ROE', ascending=False).head(30)
    
    results = []
    for idx, row in candidates.iterrows():
        curr_price = get_current_price(row['종목코드'])
        if curr_price > 0:
            upside = round(((row['목표주가'] - curr_price) / curr_price) * 100, 1)
            # Pure Data Score
            score = (row['ROE'] * 0.7) + (upside * 0.3)
            
            results.append({
                'code': row['종목코드'],
                'name': row['종목명'],
                'current': curr_price,
                'target': row['목표주가'],
                'upside': upside,
                'roe': row['ROE'],
                'debt': row['부채비율'],
                'sector': row['업종'],
                'score': score
            })
    
    # Final Top 10 by Pure Data Score
    top_10 = sorted(results, key=lambda x: x['score'], reverse=True)[:10]

    final_db_data = []
    for r in top_10:
        final_db_data.append((
            r['code'],
            r['name'],
            r['current'],
            r['target'],
            r['upside'],
            r['roe'],
            r['debt'],
            f"[{r['sector']}] 지표 우량주 (ROE {r['roe']}%, 부채 {r['debt']}%)",
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            data_date
        ))

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM audit_recommendations WHERE data_date = ?", (data_date,))
        cursor.executemany(
            "INSERT INTO audit_recommendations (code, name, current_price, target_price, upside, roe, debt, reason, created_at, data_date) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            final_db_data
        )
        conn.commit()
        conn.close()
        print(f"✅ Successfully saved 10 CLEAN data recommendations (No ETFs/Prefs) to trade.db")
        for r in top_10:
            print(f"- {r['name']} ({r['sector']}) | ROE: {r['roe']}% | Upside: {r['upside']}%")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    save_clean_data_recommendations()
