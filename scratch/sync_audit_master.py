
import pandas as pd
import sqlite3
import requests
from bs4 import BeautifulSoup
import urllib.parse
from datetime import datetime
import sys
import os
import time

# Reuse price fetcher
sys.path.append(r'c:\Python\cowork\scratch')
from recommend_10 import get_current_price

POSITIVE_KEYWORDS = ['수주', '실적', '최고', '돌파', '성장', '계약', '호조', '흑자', '공급', 'M&A', '상승', '확대']
NEGATIVE_KEYWORDS = ['적자', '하락', '우려', '소송', '횡령', '배임', '위기', '악화', '축소', '취소', '검찰', '조사']

def get_news_sentiment(query):
    try:
        encoded_query = urllib.parse.quote(query.encode('euc-kr'))
        url = f"https://finance.naver.com/news/news_search.naver?q={encoded_query}"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
        soup = BeautifulSoup(res.content.decode('euc-kr', 'replace'), 'html.parser')
        titles = [a.get_text() for a in soup.select('.newsList dt a, .newsList dd a')]
        if not titles: return 50, "뉴스 없음"
        
        raw_score = 0
        matches = []
        for title in titles[:10]:
            for kw in POSITIVE_KEYWORDS:
                if kw in title:
                    raw_score += 1
                    matches.append(kw)
            for kw in NEGATIVE_KEYWORDS:
                if kw in title:
                    raw_score -= 1
                    matches.append(f"!{kw}")
        
        norm_score = 50 + (raw_score * 10)
        norm_score = max(0, min(100, norm_score))
        summary = ", ".join(list(set(matches))) if matches else "중립"
        return norm_score, summary
    except:
        return 50, "오류"

def save_audit_master_recommendations():
    file_path = r'c:\Python\cowork\Report\20260505_latest.xlsx'
    db_path = r'c:\Python\trade\trade.db'
    data_date = "2026-05-05"
    
    df = pd.read_excel(file_path)
    
    # 1. Clean Data (No ETFs, No Prefs)
    mask_noise = df['종목명'].str.contains('KODEX|TIGER|ACE|SOL|RISE|ARIRANG|HANARO|KBSTAR|KOSEF', case=False, na=False) | \
                 df['종목명'].str.endswith(('우', '우B', '우C', '우(전환)'), na=False)
    df_clean = df[~mask_noise].copy()
    
    # 2. Audit Filter (Quality Base)
    mask_audit = (df_clean['ROE'] > 10) & (df_clean['부채비율'] < 150) & (df_clean['목표주가'] > 0)
    df_filtered = df_clean[mask_audit].copy()
    
    # 3. Supply Scoring (Foreigner Priority)
    df_filtered['f_rank'] = df_filtered['외국인순매수'].rank(pct=True) * 100
    df_filtered['i_rank'] = df_filtered['기관순매수'].rank(pct=True) * 100
    
    # 4. Momentum Calculation (Annual Range Position)
    # Score 0-100 based on where price is in 52-week range
    def calc_momentum(row, curr):
        low = row['52주최저가']
        high = row['52주최고가']
        if high > low:
            return ((curr - low) / (high - low)) * 100
        return 50

    # Candidate pool
    candidates = df_filtered.sort_values(by='ROE', ascending=False).head(20)
    
    results = []
    for idx, row in candidates.iterrows():
        name = row['종목명']
        curr_price = get_current_price(row['종목코드'])
        news_score, news_sum = get_news_sentiment(name)
        
        if curr_price > 0:
            upside = round(((row['목표주가'] - curr_price) / curr_price) * 100, 1)
            momentum = calc_momentum(row, curr_price)
            
            if upside > 0:
                # Master Score Logic
                # ROE(40%) + Foreigner(20%) + Inst(5%) + Momentum(15%) + Upside(10%) + News(10%)
                final_score = (row['ROE'] * 0.4) + \
                              (row['f_rank'] * 0.20) + \
                              (row['i_rank'] * 0.05) + \
                              (momentum * 0.15) + \
                              (min(100, upside) * 0.10) + \
                              (news_score * 0.10)
                
                # Directional Penalty: Foreigner Selling
                if row['외국인순매수'] < 0:
                    final_score -= 15
                
                results.append({
                    'code': row['종목코드'],
                    'name': name,
                    'current': curr_price,
                    'target': row['목표주가'],
                    'upside': upside,
                    'roe': row['ROE'],
                    'debt': row['부채비율'],
                    'sector': row['업종'],
                    'news_sum': news_sum,
                    'f_buy': row['외국인순매수'],
                    'score': final_score
                })
        time.sleep(0.2)
    
    top_10 = sorted(results, key=lambda x: x['score'], reverse=True)[:10]

    final_db_data = []
    for r in top_10:
        f_status = "외인집중" if r['f_buy'] > 0 else "외인매도"
        final_db_data.append((
            r['code'],
            r['name'],
            r['current'],
            r['target'],
            r['upside'],
            r['roe'],
            r['debt'],
            f"[{r['sector']}] {f_status}/모멘텀 분석 ({r['news_sum']}) | ROE {r['roe']}%",
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
        print(f"✅ Audit Master Recommendations (Financials+Supply+Momentum+News) Saved.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    save_audit_master_recommendations()
