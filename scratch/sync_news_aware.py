
import io
import sqlite3
import time
import urllib.parse
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

import sys
sys.path.append(str(Path(__file__).resolve().parents[2] / 'trade'))
from drive_sync import get_drive_service

POSITIVE_KEYWORDS = ['수주', '실적', '최고', '돌파', '성장', '계약', '호조', '흑자', '공급', 'M&A', '상승', '확대']
NEGATIVE_KEYWORDS = ['적자', '하락', '우려', '소송', '횡령', '배임', '위기', '악화', '축소', '취소', '검찰', '조사']

DB_PATH = Path(__file__).resolve().parents[2] / 'trade' / 'trade.db'
REPORT_FILENAME = '20260505_latest'


def load_report_from_drive():
    """Google Drive에서 재무 보고서를 검색하여 DataFrame으로 반환"""
    service = get_drive_service()

    query = f"name = '{REPORT_FILENAME}' and trashed = false"
    results = service.files().list(q=query, fields="files(id, name, mimeType)").execute()
    items = results.get('files', [])

    if not items:
        raise FileNotFoundError(f"Google Drive에서 '{REPORT_FILENAME}' 파일을 찾을 수 없습니다.")

    file = items[0]
    print(f"파일 발견: {file['name']} (ID: {file['id']})")

    if file['mimeType'] == 'application/vnd.google-apps.spreadsheet':
        request = service.files().export_media(
            fileId=file['id'],
            mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    else:
        request = service.files().get_media(fileId=file['id'])

    return pd.read_excel(io.BytesIO(request.execute()))


def get_current_price(code):
    try:
        url = f"https://finance.naver.com/item/main.naver?code={code}"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
        soup = BeautifulSoup(res.text, 'html.parser')
        price_tag = soup.select_one(".no_today .blind")
        if price_tag:
            return int(price_tag.text.replace(',', ''))
    except:
        pass
    return 0


def get_news_momentum(query):
    try:
        encoded_query = urllib.parse.quote(query.encode('euc-kr'))
        url = f"https://finance.naver.com/news/news_search.naver?q={encoded_query}"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
        soup = BeautifulSoup(res.content.decode('euc-kr', 'replace'), 'html.parser')

        titles = [a.get_text() for a in soup.select('.newsList dt a, .newsList dd a')]
        if not titles:
            return 0, "뉴스 없음"

        score = 0
        matches = []
        for title in titles[:10]:
            for kw in POSITIVE_KEYWORDS:
                if kw in title:
                    score += 1
                    matches.append(kw)
            for kw in NEGATIVE_KEYWORDS:
                if kw in title:
                    score -= 1
                    matches.append(f"!{kw}")

        final_score = max(-5, min(5, score))
        summary = ", ".join(list(set(matches))) if matches else "중립"
        return final_score, summary
    except:
        return 0, "오류"


def save_news_aware_recommendations():
    data_date = "2026-05-05"

    print("Google Drive에서 재무 보고서 로드 중...")
    df = load_report_from_drive()

    # ETF/우선주 제거
    mask_etf = df['종목명'].str.contains('KODEX|TIGER|ACE|SOL|RISE|ARIRANG|HANARO|KBSTAR|KOSEF', case=False, na=False)
    mask_pref = df['종목명'].str.endswith(('우', '우B', '우C', '우(전환)'), na=False)
    df_clean = df[~(mask_etf | mask_pref)].copy()

    # 재무 건전성 필터
    mask_audit = (df_clean['ROE'] > 10) & (df_clean['부채비율'] < 150) & (df_clean['목표주가'] > 0)
    candidates = df_clean[mask_audit].sort_values(by='ROE', ascending=False).head(20)

    results = []
    for _, row in candidates.iterrows():
        name = row['종목명']
        print(f"Analyzing {name}...")
        curr_price = get_current_price(row['종목코드'])
        news_score, news_sum = get_news_momentum(name)

        if curr_price > 0:
            upside = round(((row['목표주가'] - curr_price) / curr_price) * 100, 1)
            if upside > 0:
                final_score = (row['ROE'] * 0.6) + (upside * 0.2) + (news_score * 5)
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
                    'score': final_score
                })
        time.sleep(0.5)

    top_10 = sorted(results, key=lambda x: x['score'], reverse=True)[:10]

    final_db_data = [
        (
            r['code'], r['name'], r['current'], r['target'], r['upside'],
            r['roe'], r['debt'],
            f"[{r['sector']}] 뉴스 모멘텀 반영 ({r['news_sum']}) | ROE {r['roe']}%",
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            data_date
        )
        for r in top_10
    ]

    try:
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        cursor.execute("DELETE FROM audit_recommendations WHERE data_date = ?", (data_date,))
        cursor.executemany(
            "INSERT INTO audit_recommendations "
            "(code, name, current_price, target_price, upside, roe, debt, reason, created_at, data_date) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            final_db_data
        )
        conn.commit()
        conn.close()
        print(f"✅ News-Aware Recommendations Saved. ({len(top_10)}개)")
    except Exception as e:
        print(f"DB 저장 오류: {e}")


if __name__ == "__main__":
    save_news_aware_recommendations()
