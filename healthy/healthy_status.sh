#!/bin/bash
# -----------------------------------------------------------------------------
# [개발4팀] 바람길 (Baramgil) 실시간 관제 상태 브리핑 스크립트 (healthy_status.sh)
# -----------------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

PID_FILE="$SCRIPT_DIR/healthy.pid"
PID="N/A"
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
fi

RUNNING=false
if [ "$PID" != "N/A" ] && ps -p $PID > /dev/null 2>&1; then
    RUNNING=true
fi

echo "=========================================="
echo "🍃 바람길 (Baramgil) 관제 상태 리포트"
echo "=========================================="

if [ "$RUNNING" = true ]; then
    echo "🟢 프로세스 상태 : 정상 가동 중 (PID: $PID, 포트: 5005)"
else
    echo "🔴 프로세스 상태 : 중지됨"
fi

# 실시간 KPI API 조회
"$WORKSPACE_DIR/.venv/bin/python" -c "
import urllib.request, json
try:
    with urllib.request.urlopen('http://127.0.0.1:5005/api/summary', timeout=3) as resp:
        d = json.loads(resp.read())
        b = d['body']
        w = d['week']
        c = d['clinical']
        print(f'• 활성 DB 엔진  : {d.get(\"db_engine\", \"N/A\").upper()}')
        print(f'• 골격근량 사수선: {b[\"skeletal_muscle_kg\"]}kg (★ {b[\"muscle_line_status\"]}) | 체중 {b[\"weight_kg\"]}kg')
        print(f'• 최근 7일 부하  : {w[\"active_days\"]}일 {w[\"session_count\"]}세션 / {w[\"distance_km\"]}km ({w[\"total_kcal\"]:,} kcal)')
        print(f'• 피검사 D-Day  : D-{c[\"d_day\"]} (최근 HbA1c {c[\"hba1c\"]}%, TG {c[\"tg\"]}, 요산 {c[\"uric_acid\"]})')
except Exception as e:
    print(f'• API 요약 조회 실패: {e}')
"

echo "• 외부 접속 주소 : https://health.snowball1566.com"
echo "=========================================="
