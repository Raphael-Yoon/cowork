"""
[개발4팀 바람길] 헬스케어 관제 대시보드 코어 서버 (healthy.py)
- 포트: 5005 (전사 5호 공식 서비스)
- 프레임워크: Flask + Jinja2 + Chart.js
- 데이터베이스: 전사 표준 db_config.py 연동 (MySQL 'healthy' 및 SQLite 'healthy.db' 완벽 호환)
- 운영 모드: Read-Only 초경량 고속 렌더링 관제 시스템
"""

import json
import os
from datetime import datetime, date, timedelta
from pathlib import Path
from flask import Flask, render_template, jsonify, request, send_from_directory

from db_config import get_db, DB_TYPE

_BASE_DIR = Path(__file__).resolve().parent

app = Flask(
    __name__,
    template_folder=str(_BASE_DIR / "templates"),
    static_folder=str(_BASE_DIR / "static"),
)
app.config["JSON_AS_ASCII"] = False


def _get_max_workout_date(db) -> date:
    """최신 운동 기록 일자를 date 객체로 반환"""
    cur = db.execute("SELECT MAX(workout_date) FROM workouts")
    row = cur.fetchone()
    val = row[0] if row else None
    if isinstance(val, str):
        return datetime.strptime(val, "%Y-%m-%d").date()
    elif isinstance(val, (datetime, date)):
        return val if isinstance(val, date) else val.date()
    return date.today()


@app.route("/")
def index():
    """메인 대시보드 뷰"""
    return render_template("index.html")


@app.route("/manifest.json")
def manifest():
    """PWA 매니페스트"""
    return send_from_directory(str(_BASE_DIR / "static"), "manifest.json")


@app.route("/api/summary")
def api_summary():
    """상단 핵심 KPI 요약 카드 데이터"""
    with get_db() as db:
        # 1. 최근 체성분
        cur = db.execute(
            """
            SELECT measure_date, weight_kg, skeletal_muscle_kg, body_fat_pct, bmi, is_dehydrated, notes
            FROM body_composition
            ORDER BY measure_date DESC
            LIMIT 1
            """
        )
        latest_body = cur.fetchone()

        # 직전 체성분 (변화량 계산)
        cur = db.execute(
            """
            SELECT weight_kg, skeletal_muscle_kg, body_fat_pct
            FROM body_composition
            ORDER BY measure_date DESC
            LIMIT 1 OFFSET 1
            """
        )
        prev_body = cur.fetchone()

        # 2. 최근 7일 운동 통계 (MySQL/SQLite 공통 파라미터 바인딩)
        max_d = _get_max_workout_date(db)
        cutoff_7d = (max_d - timedelta(days=6)).strftime("%Y-%m-%d")

        cur = db.execute(
            """
            SELECT 
                COUNT(DISTINCT w.workout_date) AS active_days,
                COUNT(s.id) AS session_count,
                COALESCE(SUM(s.distance_km), 0) AS total_distance,
                COALESCE(SUM(s.total_kcal), 0) AS total_kcal,
                COALESCE(SUM(s.active_kcal), 0) AS active_kcal,
                COALESCE(SUM(s.duration_seconds), 0) AS total_duration_seconds
            FROM workouts w
            JOIN workout_sessions s ON w.id = s.workout_id
            WHERE w.workout_date >= ?
            """,
            (cutoff_7d,),
        )
        week_stats = cur.fetchone()

        # 3. 전체 누적 운동 통계
        cur = db.execute(
            """
            SELECT 
                COUNT(DISTINCT w.workout_date) AS total_days,
                COUNT(s.id) AS total_sessions,
                COALESCE(SUM(s.distance_km), 0) AS total_distance,
                COALESCE(SUM(s.total_kcal), 0) AS total_kcal,
                MIN(w.workout_date) AS start_date,
                MAX(w.workout_date) AS end_date
            FROM workouts w
            JOIN workout_sessions s ON w.id = s.workout_id
            """
        )
        total_stats = cur.fetchone()

        # 4. 다음 분기 피검사 D-Day (11월 중순 예정: 2026-11-17 기준)
        target_exam_date = date(2026, 11, 17)
        latest_date_str = str(total_stats[5]) if total_stats and total_stats[5] else datetime.now().strftime("%Y-%m-%d")
        try:
            curr_d = datetime.strptime(str(latest_date_str)[:10], "%Y-%m-%d").date()
        except Exception:
            curr_d = date.today()
        d_day = (target_exam_date - curr_d).days

        # 최신 혈액검사 KPI
        cur = db.execute(
            """
            SELECT exam_date, hba1c_pct, triglyceride_mgdl, uric_acid_mgdl, ldl_mgdl, fasting_glucose
            FROM clinical_lab_results
            ORDER BY exam_date DESC
            LIMIT 1
            """
        )
        latest_clinical = cur.fetchone()

        # 5. 최신 기상 공복혈당 (일상 자가 측정치)
        cur = db.execute(
            """
            SELECT workout_date, morning_fasting_blood_sugar
            FROM workouts
            WHERE morning_fasting_blood_sugar IS NOT NULL
            ORDER BY workout_date DESC
            LIMIT 1
            """
        )
        latest_fbs_row = cur.fetchone()
        latest_fbs = {
            "date": str(latest_fbs_row[0]),
            "glucose": int(latest_fbs_row[1])
        } if latest_fbs_row else None

        muscle_delta = (
            round(float(latest_body[2]) - float(prev_body[1]), 2)
            if (latest_body and prev_body and latest_body[2] and prev_body[1])
            else 0.0
        )
        weight_delta = (
            round(float(latest_body[1]) - float(prev_body[0]), 2)
            if (latest_body and prev_body and latest_body[1] and prev_body[0])
            else 0.0
        )

        return jsonify({
            "status": "success",
            "db_engine": DB_TYPE,
            "fasting_blood_sugar": latest_fbs,
            "body": {
                "date": str(latest_body[0]) if latest_body else None,
                "weight_kg": float(latest_body[1]) if latest_body else 0,
                "skeletal_muscle_kg": float(latest_body[2]) if latest_body else 0,
                "body_fat_pct": float(latest_body[3]) if latest_body else 0,
                "body_fat_kg": round(float(latest_body[1]) * (float(latest_body[3]) / 100.0), 2) if latest_body and latest_body[1] and latest_body[3] else 0.0,
                "bmi": float(latest_body[4]) if latest_body else 0,
                "muscle_line_status": "사수 완료 (+0.1kg 여유)" if latest_body and float(latest_body[2]) >= 35.0 else "관리 요망",
                "muscle_delta": muscle_delta,
                "weight_delta": weight_delta,
                "notes": latest_body[6] if latest_body else "",
            },
            "week": {
                "active_days": int(week_stats[0]) if week_stats else 0,
                "session_count": int(week_stats[1]) if week_stats else 0,
                "distance_km": round(float(week_stats[2]), 2) if week_stats else 0,
                "total_kcal": int(week_stats[3]) if week_stats else 0,
                "active_kcal": int(week_stats[4]) if week_stats else 0,
                "duration_minutes": round(float(week_stats[5] or 0) / 60, 1) if week_stats else 0,
            },
            "total": {
                "days": int(total_stats[0]) if total_stats else 0,
                "sessions": int(total_stats[1]) if total_stats else 0,
                "distance_km": round(float(total_stats[2]), 2) if total_stats else 0,
                "total_kcal": int(total_stats[3]) if total_stats else 0,
                "period": f"{str(total_stats[4])[:10]} ~ {str(total_stats[5])[:10]}" if total_stats else "",
            },
            "clinical": {
                "exam_date": str(latest_clinical[0]) if latest_clinical else "",
                "hba1c": float(latest_clinical[1]) if latest_clinical and latest_clinical[1] is not None else 0,
                "tg": int(latest_clinical[2]) if latest_clinical and latest_clinical[2] is not None else 0,
                "uric_acid": float(latest_clinical[3]) if latest_clinical and latest_clinical[3] is not None else 0,
                "ldl": int(latest_clinical[4]) if latest_clinical and latest_clinical[4] is not None else 0,
                "glucose": int(latest_clinical[5]) if latest_clinical and latest_clinical[5] is not None else 0,
                "d_day": d_day,
                "target_date": target_exam_date.strftime("%Y-%m-%d"),
            },
        })


@app.route("/api/chart/body-comp")
def api_chart_body_comp():
    """체성분 시계열 차트 데이터 (체중 vs 골격근량 듀얼 축)"""
    with get_db() as db:
        cur = db.execute(
            """
            SELECT measure_date, weight_kg, skeletal_muscle_kg, body_fat_pct, bmi, is_dehydrated, notes
            FROM body_composition
            ORDER BY measure_date ASC
            """
        )
        rows = cur.fetchall()

        labels = [str(r[0]) for r in rows]
        weights = [float(r[1]) for r in rows]
        muscles = [float(r[2]) for r in rows]
        fat_pcts = [float(r[3]) for r in rows]
        fat_masses = [round(w * (f / 100.0), 2) for w, f in zip(weights, fat_pcts)]
        bmis = [float(r[4]) for r in rows]
        target_muscle_line = [35.0 for _ in rows]

        return jsonify({
            "status": "success",
            "labels": labels,
            "weights": weights,
            "muscles": muscles,
            "fat_pcts": fat_pcts,
            "fat_masses": fat_masses,
            "bmis": bmis,
            "target_muscle_line": target_muscle_line,
        })


@app.route("/api/chart/workouts")
def api_chart_workouts():
    """
    운동 시계열 차트 및 필터링 데이터
    - days: 7, 30, all
    - sport: all, cycling, walking
    """
    days = request.args.get("days", "all")
    sport = request.args.get("sport", "all").lower()

    with get_db() as db:
        max_d = _get_max_workout_date(db)
        params = []

        date_filter = ""
        if days == "7":
            cutoff = (max_d - timedelta(days=6)).strftime("%Y-%m-%d")
            date_filter = "AND w.workout_date >= ?"
            params.append(cutoff)
        elif days == "30":
            cutoff = (max_d - timedelta(days=29)).strftime("%Y-%m-%d")
            date_filter = "AND w.workout_date >= ?"
            params.append(cutoff)

        sport_filter = ""
        if sport in ("cycling", "자전거"):
            sport_filter = "AND (s.sport_type LIKE '%자전거%' OR s.sport_type LIKE '%Cycling%')"
        elif sport in ("walking", "걷기"):
            sport_filter = "AND (s.sport_type LIKE '%걷기%' OR s.sport_type LIKE '%Walking%')"

        query = f"""
            SELECT 
                w.workout_date,
                w.day_of_week,
                w.evaluation,
                w.morning_fasting_blood_sugar,
                COALESCE(SUM(s.distance_km), 0) AS total_distance,
                COALESCE(SUM(s.total_kcal), 0) AS total_kcal,
                COALESCE(SUM(s.active_kcal), 0) AS active_kcal,
                COALESCE(SUM(s.duration_seconds), 0) AS total_duration,
                COALESCE(AVG(s.avg_heart_rate_bpm), 0) AS avg_hr,
                COALESCE(MAX(s.max_heart_rate_bpm), 0) AS max_hr,
                COUNT(s.id) AS session_count
            FROM workouts w
            JOIN workout_sessions s ON w.id = s.workout_id
            WHERE 1=1 {date_filter} {sport_filter}
            GROUP BY w.workout_date, w.day_of_week, w.evaluation, w.morning_fasting_blood_sugar
            ORDER BY w.workout_date ASC
        """
        cur = db.execute(query, tuple(params) if params else None)
        rows = cur.fetchall()

        labels = [f"{str(r[0])} ({r[1]})" for r in rows]
        dates = [str(r[0]) for r in rows]
        distances = [round(float(r[4]), 2) for r in rows]
        total_kcals = [int(r[5]) for r in rows]
        active_kcals = [int(r[6]) for r in rows]
        durations_min = [round(int(r[7]) / 60, 1) for r in rows]
        avg_hrs = [int(round(float(r[8]))) for r in rows]
        evaluations = [r[2] for r in rows]
        fbs_list = [r[3] for r in rows]

        return jsonify({
            "status": "success",
            "labels": labels,
            "dates": dates,
            "distances": distances,
            "total_kcals": total_kcals,
            "active_kcals": active_kcals,
            "durations_min": durations_min,
            "avg_hrs": avg_hrs,
            "evaluations": evaluations,
            "fasting_blood_sugars": fbs_list,
        })


@app.route("/api/chart/clinical")
def api_chart_clinical():
    """정기 피검사 목표 대비 시계열 데이터"""
    with get_db() as db:
        cur = db.execute(
            """
            SELECT 
                exam_date, hba1c_pct, fasting_glucose, triglyceride_mgdl,
                ldl_mgdl, uric_acid_mgdl, ast_u_l, alt_u_l, creatinine_mgdl, notes
            FROM clinical_lab_results
            ORDER BY exam_date ASC
            """
        )
        rows = cur.fetchall()

        labels = [str(r[0]) for r in rows]
        hba1c = [float(r[1]) if r[1] is not None else None for r in rows]
        glucose = [int(r[2]) if r[2] is not None else None for r in rows]
        tg = [int(r[3]) if r[3] is not None else None for r in rows]
        ldl = [int(r[4]) if r[4] is not None else None for r in rows]
        uric_acid = [float(r[5]) if r[5] is not None else None for r in rows]
        ast = [int(r[6]) if r[6] is not None else None for r in rows]
        alt = [int(r[7]) if r[7] is not None else None for r in rows]
        creatinine = [float(r[8]) if r[8] is not None else None for r in rows]
        notes = [r[9] for r in rows]

        return jsonify({
            "status": "success",
            "labels": labels,
            "hba1c": hba1c,
            "glucose": glucose,
            "tg": tg,
            "ldl": ldl,
            "uric_acid": uric_acid,
            "ast": ast,
            "alt": alt,
            "creatinine": creatinine,
            "notes": notes,
            # 목표선
            "targets": {
                "hba1c": 5.5,
                "glucose": 95,
                "tg": 120,
                "ldl_low": 70,
                "ldl_high": 80,
                "uric_acid": 6.50,
                "creatinine_max": 1.10,
            },
        })


@app.route("/api/workouts")
def api_workouts():
    """일자별 운동 일지 전체 목록 (세션 및 스플릿 포함)"""
    days = request.args.get("days", "all")
    sport = request.args.get("sport", "all").lower()

    with get_db() as db:
        max_d = _get_max_workout_date(db)
        params = []

        date_filter = ""
        if days == "7":
            cutoff = (max_d - timedelta(days=6)).strftime("%Y-%m-%d")
            date_filter = "AND w.workout_date >= ?"
            params.append(cutoff)
        elif days == "30":
            cutoff = (max_d - timedelta(days=29)).strftime("%Y-%m-%d")
            date_filter = "AND w.workout_date >= ?"
            params.append(cutoff)

        sport_filter = ""
        if sport in ("cycling", "자전거"):
            sport_filter = "AND (s.sport_type LIKE '%자전거%' OR s.sport_type LIKE '%Cycling%')"
        elif sport in ("walking", "걷기"):
            sport_filter = "AND (s.sport_type LIKE '%걷기%' OR s.sport_type LIKE '%Walking%')"

        # 1. 일자별 운동 마스터
        w_cur = db.execute(
            f"""
            SELECT DISTINCT
                w.id, w.workout_date, w.day_of_week, w.time_of_day,
                w.workout_type, w.routine_name, w.morning_fasting_blood_sugar,
                w.evaluation, w.notes
            FROM workouts w
            JOIN workout_sessions s ON w.id = s.workout_id
            WHERE 1=1 {date_filter} {sport_filter}
            ORDER BY w.workout_date DESC
            """,
            tuple(params) if params else None,
        )
        workouts = []
        for w_row in w_cur.fetchall():
            w_id = w_row[0]
            w_date_str = str(w_row[1])

            # 해당 일자 체성분 확인
            b_cur = db.execute(
                "SELECT weight_kg, skeletal_muscle_kg, body_fat_pct, bmi, notes FROM body_composition WHERE measure_date = ?",
                (w_date_str,),
            )
            b_row = b_cur.fetchone()

            # 해당 일자 세션 목록
            s_cur = db.execute(
                f"""
                SELECT 
                    id, session_no, sport_type, session_name,
                    duration_seconds, duration_str, distance_km, estimated_distance_km,
                    active_kcal, total_kcal, elevation_gain_m,
                    avg_heart_rate_bpm, max_heart_rate_bpm, avg_speed_kmh,
                    avg_pace, effort, weather_info, notes
                FROM workout_sessions
                WHERE workout_id = ? {sport_filter.replace('s.', '')}
                ORDER BY session_no ASC
                """,
                (w_id,),
            )
            sessions = []
            for s_row in s_cur.fetchall():
                sess_id = s_row[0]
                sp_cur = db.execute(
                    """
                    SELECT split_no, distance_km, time_str, speed_kmh, heart_rate_bpm
                    FROM session_splits
                    WHERE session_id = ?
                    ORDER BY split_no ASC
                    """,
                    (sess_id,),
                )
                splits = [
                    {
                        "split_no": sp[0],
                        "distance_km": float(sp[1]) if sp[1] is not None else None,
                        "time_str": sp[2],
                        "speed_kmh": float(sp[3]) if sp[3] is not None else None,
                        "heart_rate_bpm": sp[4],
                    }
                    for sp in sp_cur.fetchall()
                ]

                weather_parsed = None
                if s_row[16]:
                    try:
                        weather_parsed = json.loads(s_row[16])
                    except Exception:
                        pass

                sessions.append({
                    "id": s_row[0],
                    "session_no": s_row[1],
                    "sport_type": s_row[2],
                    "name": s_row[3],
                    "duration_seconds": int(s_row[4] or 0),
                    "duration_str": s_row[5],
                    "distance_km": float(s_row[6] or 0),
                    "estimated_distance_km": float(s_row[7]) if s_row[7] else None,
                    "active_kcal": int(s_row[8] or 0),
                    "total_kcal": int(s_row[9] or 0),
                    "elevation_gain_m": int(s_row[10] or 0),
                    "avg_heart_rate_bpm": s_row[11],
                    "max_heart_rate_bpm": s_row[12],
                    "avg_speed_kmh": float(s_row[13]) if s_row[13] is not None else None,
                    "avg_pace": s_row[14],
                    "effort": s_row[15],
                    "weather": weather_parsed,
                    "notes": s_row[17],
                    "splits": splits,
                })

            total_dist = sum(s["distance_km"] for s in sessions)
            total_kcal = sum(s["total_kcal"] for s in sessions)
            total_active_kcal = sum(s["active_kcal"] for s in sessions)
            total_duration_sec = sum(s["duration_seconds"] for s in sessions)

            workouts.append({
                "id": w_row[0],
                "date": w_date_str,
                "day_of_week": w_row[2],
                "time_of_day": w_row[3],
                "workout_type": w_row[4],
                "routine_name": w_row[5],
                "fasting_blood_sugar": w_row[6],
                "evaluation": w_row[7],
                "notes": w_row[8],
                "body_comp": {
                    "weight_kg": float(b_row[0]),
                    "skeletal_muscle_kg": float(b_row[1]),
                    "body_fat_pct": float(b_row[2]),
                    "bmi": float(b_row[3]),
                    "notes": b_row[4],
                } if b_row else None,
                "summary": {
                    "total_distance_km": round(total_dist, 2),
                    "total_kcal": total_kcal,
                    "total_active_kcal": total_active_kcal,
                    "total_duration_str": f"{total_duration_sec // 3600}:{(total_duration_sec % 3600) // 60:02d}:{total_duration_sec % 60:02d}",
                    "session_count": len(sessions),
                },
                "sessions": sessions,
            })

        return jsonify({"status": "success", "count": len(workouts), "workouts": workouts})


@app.route("/api/clinical/items")
def api_clinical_items():
    """피검사 33개 전 항목 비교 원천 데이터"""
    with get_db() as db:
        cur = db.execute(
            """
            SELECT exam_date, category, item_name, result_value, numeric_value, reference_range, unit, evaluation
            FROM clinical_lab_items
            ORDER BY id ASC
            """
        )
        rows = cur.fetchall()

        dates = ["2026-02-23", "2026-04-02", "2026-05-19", "2026-08-18"]
        items_map = {}

        for r in rows:
            ed = str(r[0])
            cat, name, r_val, n_val, ref, unit, eval_text = (
                r[1], r[2], r[3], r[4], r[5], r[6], r[7]
            )
            key = (cat, name)
            if key not in items_map:
                items_map[key] = {
                    "category": cat,
                    "name": name,
                    "reference": ref,
                    "unit": unit,
                    "evaluation": eval_text,
                    "values": {},
                }
            items_map[key]["values"][ed] = r_val

        return jsonify({
            "status": "success",
            "dates": dates,
            "items": list(items_map.values()),
        })


def main():
    port = int(os.getenv("HEALTHY_PORT", 5005))
    print(f"[*] Starting Baramgil Health Dashboard on http://0.0.0.0:{port} (Active DB: {DB_TYPE})")
    app.run(host="0.0.0.0", port=port, debug=True)


if __name__ == "__main__":
    main()
