# -*- coding: utf-8 -*-
"""
IT 감사팀 Top 10 추천 종목 저장 유틸리티
기준 문서: cowork/Report/audit_logic.md

AI가 분석·결정한 추천 종목을 SQLite tr_audit_recommendations 테이블에 저장.

사용법:
    python cowork/audit_save.py recommendations.json
    python cowork/audit_save.py recommendations.json --date 2026-05-10
"""
import argparse
import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path

SQLITE_PATH = str(Path(__file__).resolve().parents[1] / 'trade' / 'trade.db')


def save(records: list[dict], data_date: str, rec_type: str = 'momentum'):
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
            "reason":        "[반도체] 뉴스:실적·최고 | ROE 63.0% | 수급 외인+/기관-",
            "news_summary":  "...",
            "rec_type":      "value"
        },
        ...
    ]
    """
    if not records:
        print("[오류] 저장할 데이터가 없습니다.")
        return

    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    print(f"[완료] {len(records)}개 종목 DB 적재 시작 (추천유형: {rec_type})")
    for r in records:
        print(f"   [{r['code']}] {r['name']}  상승여력 {r['upside']:.1f}%")

    try:
        from dotenv import load_dotenv
        COWORK_DIR = Path(__file__).resolve().parent
        TRADE_DIR = COWORK_DIR.parent / 'trade'
        load_dotenv(TRADE_DIR / '.env')
        database_url = os.getenv('DATABASE_URL')

        db_type = 'sqlite'
        if database_url and database_url.startswith('postgresql'):
            import psycopg2
            import psycopg2.extras
            conn = psycopg2.connect(database_url, cursor_factory=psycopg2.extras.DictCursor)
            cursor = conn.cursor()
            db_type = 'postgres'
        elif database_url and database_url.startswith('mysql'):
            import pymysql
            from urllib.parse import urlparse
            parsed = urlparse(database_url)
            conn = pymysql.connect(
                host=parsed.hostname or '127.0.0.1',
                port=parsed.port or 3306,
                user=parsed.username or 'root',
                password=parsed.password or '',
                database=parsed.path.lstrip('/') if parsed.path else 'trade',
                charset='utf8mb4',
                cursorclass=pymysql.cursors.DictCursor
            )
            cursor = conn.cursor()
            db_type = 'mysql'
        else:
            conn = sqlite3.connect(SQLITE_PATH)
            cursor = conn.cursor()
            db_type = 'sqlite'

        placeholder = '?' if db_type == 'sqlite' else '%s'

        # 해당 추천 유형만 삭제 후 추가
        cursor.execute(f"DELETE FROM tr_audit_recommendations WHERE rec_type = {placeholder}", (rec_type,))

        for r in records:
            item_rec_type = r.get('rec_type', rec_type)
            item_data_date = r.get('data_date', data_date)
            cursor.execute(f"""
                INSERT INTO tr_audit_recommendations
                    (code, name, current_price, target_price, upside, opinion, data_date, created_at,
                     score, roe, debt, reason, news_summary, rec_type, one_liner, disc_json)
                VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})
            """, (
                r['code'], r['name'], float(r['current_price']), float(r['target_price']),
                float(r['upside']), '', item_data_date, now_str, float(r['score']),
                float(r.get('roe', 0)), float(r.get('debt', 0)), r.get('reason', ''),
                r.get('news_summary', '[]'), item_rec_type, r.get('one_liner', ''),
                r.get('disc_json', '[]')
            ))

        conn.commit()
        conn.close()
        print(f"[완료] {db_type.upper()} tr_audit_recommendations 테이블 적재 성공! (타입: {rec_type})")
    except Exception as e:
        print(f"[오류] {db_type.upper()} audit_recommendations 적재 실패: {e}")


def main():
    parser = argparse.ArgumentParser(description='IT 감사팀 Top 10 추천 종목 저장')
    parser.add_argument('json_file', help='추천 종목 JSON 파일 경로')
    parser.add_argument('--date', default=datetime.now().strftime('%Y-%m-%d'),
                        help='기준일 (기본값: 오늘, 형식: YYYY-MM-DD)')
    parser.add_argument('--type', default='momentum', choices=['momentum', 'value'],
                        help='추천 유형 (momentum 또는 value)')
    args = parser.parse_args()

    json_path = Path(args.json_file)
    if not json_path.exists():
        print(f"[오류] 파일을 찾을 수 없습니다: {json_path}")
        return

    with open(json_path, encoding='utf-8') as f:
        records = json.load(f)

    if isinstance(records, dict) and 'stocks' in records:
        records = records['stocks']

    save(records, args.date, args.type)


if __name__ == '__main__':
    main()
