
import pandas as pd
import requests
from bs4 import BeautifulSoup
import sqlite3
from datetime import datetime
import sys
import os

def get_current_price(code):
    try:
        url = f"https://finance.naver.com/item/main.naver?code={code}"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
        soup = BeautifulSoup(res.text, 'html.parser')
        price_tag = soup.select_one(".no_today .blind")
        if price_tag:
            return int(price_tag.text.replace(',', ''))
    except: pass
    return 0

def save_audit_recommendations():
    file_path = r'c:\Python\cowork\Report\20260505_latest.xlsx'
    db_path = r'c:\Python\trade\trade.db'
    
    if not os.path.exists(file_path):
        print("Excel file not found.")
        return

    df = pd.read_excel(file_path)
    # Stability-first filter
    mask = (df['ROE'] > 15) & (df['부채비율'] < 150) & (df['목표주가'] > 0)
    candidates = df[mask].sort_values(by='ROE', ascending=False).head(20)

    data_date = "2026-05-05" # 파일명에서 추출한 데이터 기준일
    results = []
    for idx, row in candidates.iterrows():
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
                f"고ROE({row['ROE']}%), 저부채({row['부채비율']}%)의 재무 건전 우량주",
                datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                data_date
            ))

    # Sort by upside and pick top 10
    final_10 = sorted(results, key=lambda x: x[4], reverse=True)[:10]

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        # 해당 일자의 추천 데이터가 이미 있으면 중복 방지를 위해 삭제 후 삽입
        cursor.execute("DELETE FROM audit_recommendations WHERE data_date = ?", (data_date,))
        cursor.executemany(
            "INSERT INTO audit_recommendations (code, name, current_price, target_price, upside, roe, debt, reason, created_at, data_date) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            final_10
        )
        conn.commit()
        conn.close()
        print(f"✅ Successfully saved {len(final_10)} recommendations to trade.db")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    save_audit_recommendations()
