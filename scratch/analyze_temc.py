import pandas as pd

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from audit_loader import get_latest_audit_report

try:
    df = get_latest_audit_report()
    # 티이엠씨 검색 (정확한 매칭 혹은 포함 매칭)
    target = df[df['종목명'].str.contains('티이엠씨', na=False)]
    
    if not target.empty:
        # 여러 개가 나올 수 있으므로 (예: 티이엠씨씨 등) 가장 짧은 것 선택
        target = target.sort_values(by='종목명', key=lambda x: x.str.len()).iloc[0]
        print("--- TEMC Analysis ---")
        for col in df.columns:
            print(f"{col}: {target[col]}")
    else:
        print("티이엠씨 종목을 찾을 수 없습니다.")

except Exception as e:
    print(f"Error: {e}")
