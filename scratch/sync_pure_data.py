
import pandas as pd
import sqlite3
from datetime import datetime
import sys
import os

# Reuse price fetcher
sys.path.append(r'c:\Python\cowork\scratch')
from recommend_10 import get_current_price

def save_pure_data_recommendations():
    file_path = r'c:\Python\cowork\Report\20260505_latest.xlsx'
    db_path = r'c:\Python\trade\trade.db'
    data_date = "2026-05-05"
    
    df = pd.read_excel(file_path)
    
    # Audit & Fundamental filters (Objective Criteria)
    # ROE > 15 (High profitability), Debt < 150 (Safety), Target > 0 (Analyst Coverage)
    mask = (df['ROE'] > 15) & (df['부채비율'] < 150) & (df['목표주가'] > 0)
    df_filtered = df[mask].copy()
    
    # Calculate a balanced "Audit Score" 
    # (ROE is the most important for an Auditor, but we need some upside)
    # Note: Upside requires current price, which we'll fetch for a larger candidate pool
    candidates = df_filtered.sort_values(by='ROE', ascending=False).head(30)
    
    results = []
    for idx, row in candidates.iterrows():
        curr_price = get_current_price(row['종목코드'])
        if curr_price > 0:
            upside = round(((row['목표주가'] - curr_price) / curr_price) * 100, 1)
            # Pure Data Score: Weight ROE heavily for stability, but reward upside
            score = (row['ROE'] * 0.8) + (upside * 0.2)
            
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
            f"데이터 종합 점수 상위주 (ROE {r['roe']}%, 부채 {r['debt']}%, 상승여력 {r['upside']}%)",
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
        print(f"✅ Successfully saved 10 PURE DATA-DRIVEN recommendations to trade.db")
        for r in top_10:
            print(f"- {r['name']} (Score: {r['score']:.1f}, ROE: {r['roe']}%)")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    save_pure_data_recommendations()
