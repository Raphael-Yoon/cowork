"""
[개발4팀 바람길] 텔레그램 실시간 알림 발송 유틸리티 (send_telegram_alert.py)
- 매일 아침 관제 요약 및 오버트레이닝(과다 제동) 알림 전송
- Antigravity 및 시스템 스케줄러 연동
"""

import os
import requests
from typing import Optional

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8439778551:AAHMXpbmR1_JgxKDFGjNIUzH6YOSnXrJF5A")
DEFAULT_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "8587089093")


def send_message(html_text: str, chat_id: Optional[str] = None) -> bool:
    """텔레그램 메시지 발송"""
    target_chat = chat_id or DEFAULT_CHAT_ID
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": target_chat,
        "text": html_text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }
    try:
        resp = requests.post(url, json=payload, timeout=10)
        return resp.status_code == 200 and resp.json().get("ok", False)
    except Exception as e:
        print(f"[!] Telegram alert error: {e}")
        return False


def send_daily_briefing() -> bool:
    """일일 바람길 건강 요약 브리핑 발송"""
    from db_config import get_db

    with get_db() as db:
        # 최근 체성분
        cur = db.execute(
            """
            SELECT measure_date, weight_kg, skeletal_muscle_kg, body_fat_pct
            FROM body_composition
            ORDER BY measure_date DESC
            LIMIT 1
            """
        )
        b = cur.fetchone()

        from datetime import datetime, date, timedelta
        # 최신 일자 기준 7일 계산
        cur = db.execute("SELECT MAX(workout_date) FROM workouts")
        r = cur.fetchone()
        max_d = r[0] if r else date.today()
        if isinstance(max_d, str):
            max_d = datetime.strptime(max_d[:10], "%Y-%m-%d").date()
        cutoff_7d = (max_d - timedelta(days=6)).strftime("%Y-%m-%d")

        cur = db.execute(
            """
            SELECT 
                COUNT(DISTINCT w.workout_date),
                COUNT(s.id),
                COALESCE(SUM(s.distance_km), 0),
                COALESCE(SUM(s.total_kcal), 0)
            FROM workouts w
            JOIN workout_sessions s ON w.id = s.workout_id
            WHERE w.workout_date >= ?
            """,
            (cutoff_7d,),
        )
        w = cur.fetchone()

    msg = (
        "🍃 <b>[바람길 데일리 헬스 브리핑]</b>\n\n"
        f"🛡️ <b>골격근량 사수선</b>: <b>{b[2]}kg</b> (★ 35.0kg 유지 중)\n"
        f"⚖️ <b>최근 체중</b>: {b[1]}kg (체지방률 {b[3]}%)\n"
        f"⚡ <b>최근 7일 운동</b>: {w[0]}일 {w[1]}세션 / {float(w[2]):.1f}km ({int(w[3]):,} kcal)\n"
        "🩺 <b>11월 정기검진</b>: D-42 (HbA1c 5.7% ➔ 목표 5.5%)\n\n"
        "👉 <a href='https://health.snowball1566.com'>바람길 관제 대시보드 열기</a>"
    )
    return send_message(msg)


if __name__ == "__main__":
    print("[*] Sending test telegram alert...")
    success = send_daily_briefing()
    print("[+] Alert result:", success)
