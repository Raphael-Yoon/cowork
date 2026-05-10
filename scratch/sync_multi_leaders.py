
import pandas as pd
import sqlite3
from datetime import datetime
import sys
import os

# Reuse price fetcher
sys.path.append(r'c:\Python\cowork\scratch')
from recommend_10 import get_current_price

def save_sector_multi_leader_recommendations():
    file_path = r'c:\Python\cowork\Report\20260505_latest.xlsx'
    db_path = r'c:\Python\trade\trade.db'
    data_date = "2026-05-05"
    
    df = pd.read_excel(file_path)
    
    # Audit filters
    mask = (df['ROE'] > 5) & (df['부채비율'] < 250) & (df['목표주가'] > 0)
    df_filtered = df[mask].copy()
    
    # Identify top 5 sectors by average ROE (Sector Momentum)
    sector_scores = df_filtered.groupby('업종')['ROE'].mean().sort_values(ascending=False).head(5).index.tolist()
    
    # Also ensure Semiconductor and Shipbuilding are included even if not in top 5 (user's specific interest)
    important_sectors = ['반도체와반도체장비', '조선', '화장품']
    target_sectors = list(dict.fromkeys(sector_scores + important_sectors))[:6] # Top 6 sectors
    
    results = []
    for sector in target_sectors:
        # Pick top 2 leaders by ROE in each sector
        sector_stocks = df_filtered[df_filtered['업종'] == sector].sort_values(by='ROE', ascending=False).head(2)
        
        for idx, row in sector_stocks.iterrows():
            curr_price = get_current_price(row['종목코드'])
            if curr_price > 0:
                upside = round(((row['목표주가'] - curr_price) / curr_price) * 100, 1)
                results.append((
                    row['종목코드'],
                    row['종목명'],
                    curr_price,
                    row['목표주가'],
                    upside,
                    row['ROE'],
                    row['부채비율'],
                    f"[{sector}] 산업 리딩 우량주 (ROE {row['ROE']}%)",
                    datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    data_date
                ))
    
    # Limit to top 10 total
    final_results = results[:10]

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM audit_recommendations WHERE data_date = ?", (data_date,))
        cursor.executemany(
            "INSERT INTO audit_recommendations (code, name, current_price, target_price, upside, roe, debt, reason, created_at, data_date) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            final_results
        )
        conn.commit()
        conn.close()
        print(f"✅ Successfully saved {len(final_results)} sector-leader recommendations (Multi-Pick) to trade.db")
        for r in final_results:
            print(f"- {r[1]} ({r[7]})")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    save_sector_multi_leader_recommendations()
