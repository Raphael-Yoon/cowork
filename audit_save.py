# -*- coding: utf-8 -*-
"""
IT 감사팀 추천 종목 DB 저장 유틸리티
기준 문서: cowork/Report/audit_logic.md

AI가 분석·결정한 추천 종목을 trade.db에 저장하는 역할만 담당.

사용법:
    python cowork/audit_save.py recommendations.json
    python cowork/audit_save.py recommendations.json --date 2026-05-10
"""
import argparse
import json
import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[1] / 'trade' / 'trade.db'


def save(records: list[dict], data_date: str):
    """
    records 형식:
    [
        {
            "code":          "005930",
            "name":          "삼성전자",
            "current_price": 268500,
            "target_price":  310800,
            "upside":        15.8,
            "roe":           63.0,
            "debt":          29.9,
            "score":         78.5,
            "reason":        "[반도체] 뉴스:실적·최고 | ROE 63.0% | 수급 외인+3444660/기관-844124"
        },
        ...
    ]
    """
    if not records:
        print("[오류] 저장할 데이터가 없습니다.")
        return

    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    db_rows = [
        (
            r['code'], r['name'],
            float(r['current_price']), float(r['target_price']),
            float(r['upside']), float(r['roe']), float(r['debt']),
            r['reason'], float(r.get('score', 0.0)),
            r.get('news_summary', ''),
            now_str, data_date
        )
        for r in records
    ]

    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    cursor.execute("DELETE FROM audit_recommendations WHERE data_date = ?", (data_date,))
    cursor.executemany(
        "INSERT OR REPLACE INTO audit_recommendations "
        "(code, name, current_price, target_price, upside, roe, debt, reason, score, news_summary, created_at, data_date) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        db_rows
    )
    conn.commit()
    conn.close()

    print(f"[완료] {len(db_rows)}개 종목 저장 완료 (data_date={data_date})")
    for r in records:
        print(f"   [{r['code']}] {r['name']}  상승여력 {r['upside']:.1f}%")


def main():
    parser = argparse.ArgumentParser(description='IT 감사팀 추천 종목 DB 저장')
    parser.add_argument('json_file', help='추천 종목 JSON 파일 경로')
    parser.add_argument('--date', default=datetime.now().strftime('%Y-%m-%d'),
                        help='기준일 (기본값: 오늘, 형식: YYYY-MM-DD)')
    args = parser.parse_args()

    json_path = Path(args.json_file)
    if not json_path.exists():
        print(f"[오류] 파일을 찾을 수 없습니다: {json_path}")
        return

    with open(json_path, encoding='utf-8') as f:
        records = json.load(f)

    save(records, args.date)


if __name__ == '__main__':
    main()
