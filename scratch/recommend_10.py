
import pandas as pd
import requests
from bs4 import BeautifulSoup
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

file_path = r'c:\Python\cowork\Report\20260505_latest.xlsx'
df = pd.read_excel(file_path)

# Filter for safe stocks (Audit Team style)
mask = (df['ROE'] > 15) & (df['부채비율'] < 150) & (df['목표주가'] > 0)
candidates = df[mask].sort_values(by='ROE', ascending=False).head(20)

results = []
for idx, row in candidates.iterrows():
    curr_price = get_current_price(row['종목코드'])
    if curr_price > 0:
        upside = ((row['목표주가'] - curr_price) / curr_price) * 100
        results.append({
            'name': row['종목명'],
            'code': row['종목코드'],
            'roe': row['ROE'],
            'debt': row['부채비율'],
            'current': curr_price,
            'target': row['목표주가'],
            'upside': upside,
            'audit': '적정(예상)' # We assume since it's in the list
        })

# Sort by upside potential
final_10 = sorted(results, key=lambda x: x['upside'], reverse=True)[:10]

for s in final_10:
    print(f"{s['name']}({s['code']}) | 현재가: {s['current']:,} | 목표가: {s['target']:,} | 상승여력: {s['upside']:.1f}% | ROE: {s['roe']}% | 부채: {s['debt']}%")
