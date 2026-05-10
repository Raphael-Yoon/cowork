
import pandas as pd
import sqlite3
from datetime import datetime
import sys
import os

# Reuse the price fetcher
sys.path.append(r'c:\Python\cowork\scratch')
from recommend_10 import get_current_price

def save_sector_leader_recommendations():
    file_path = r'c:\Python\cowork\Report\20260505_latest.xlsx'
    db_path = r'c:\Python\trade\trade.db'
    data_date = "2026-05-05"
    
    df = pd.read_excel(file_path)
    
    # Audit filters
    mask = (df['ROE'] > 10) & (df['부채비율'] < 200) & (df['목표주가'] > 0)
    df_filtered = df[mask].copy()
    
    # Group by sector and get the best ROE stock in each sector
    # This ensures "Leaders" like Samsung/Hynix are picked if they are the best in their sector
    sector_leaders = df_filtered.loc[df_filtered.groupby('업종')['ROE'].idxmax()]
    
    # Sort these leaders by ROE (to pick the 10 most attractive sectors)
    top_10_leaders = sector_leaders.sort_values(by='ROE', ascending=False).head(10)
    
    results = []
    for idx, row in top_10_leaders.iterrows():
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
                f"{row['업종']} 섹터 대장주 (ROE {row['ROE']}%, 부채 {row['부채비율']}%)",
                datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                data_date
            ))

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM audit_recommendations WHERE data_date = ?", (data_date,))
        cursor.executemany(
            "INSERT INTO audit_recommendations (code, name, current_price, target_price, upside, roe, debt, reason, created_at, data_date) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            results
        )
        conn.commit()
        conn.close()
        print(f"✅ Successfully saved {len(results)} sector-leader recommendations to trade.db")
        for r in results:
            print(f"- {r[1]} ({r[7]})")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    save_sector_leader_recommendations()
