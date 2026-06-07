# -*- coding: utf-8 -*-
"""
IT 감사팀 Top 10 추천 종목 저장 유틸리티
기준 문서: cowork/Report/audit_logic.md

AI가 분석·결정한 추천 종목을 Neon DB의 audit_recommendations 테이블에 저장.

사용법:
    python cowork/audit_save.py recommendations.json
    python cowork/audit_save.py recommendations.json --date 2026-05-10
"""
import argparse
import json
import os
import psycopg2
import psycopg2.extras
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# trade/.env 로드
env_path = Path(__file__).resolve().parents[1] / 'trade' / '.env'
load_dotenv(env_path)
DATABASE_URL = os.getenv('DATABASE_URL')


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

    # Neon DB audit_recommendations 저장
    if not DATABASE_URL:
        print("[오류] DATABASE_URL 환경 변수가 설정되지 않아 DB 저장을 건너뜁니다.")
        return

    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.DictCursor)
        cursor = conn.cursor()
        
        # 전체를 다 비우지 않고 해당 추천 유형만 삭제 후 추가
        cursor.execute("DELETE FROM audit_recommendations WHERE rec_type = %s", (rec_type,))
        
        for r in records:
            item_rec_type = r.get('rec_type', rec_type)
            cursor.execute("""
                INSERT INTO audit_recommendations
                    (code, name, current_price, target_price, upside, opinion, data_date, created_at, score, roe, debt, reason, news_summary, rec_type)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                r['code'], r['name'], float(r['current_price']), float(r['target_price']),
                float(r['upside']), '', data_date, now_str, float(r['score']),
                float(r.get('roe', 0)), float(r.get('debt', 0)), r.get('reason', ''), r.get('news_summary', ''),
                item_rec_type
            ))
        conn.commit()
        conn.close()
        print(f"[완료] Neon DB audit_recommendations 테이블 적재 성공! (타입: {rec_type})")
    except Exception as e:
        print(f"[오류] Neon DB audit_recommendations 적재 실패: {e}")


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
