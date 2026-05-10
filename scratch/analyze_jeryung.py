import pandas as pd

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from audit_loader import get_latest_audit_report

try:
    df = get_latest_audit_report()
    # 제룡전기 검색
    target = df[df['종목명'].str.contains('제룡전기', na=False)]
    
    if not target.empty:
        print("--- Jeryung Electric Analysis ---")
        for col in target.columns:
            print(f"{col}: {target.iloc[0][col]}")
    else:
        print("제룡전기 종목을 찾을 수 없습니다.")

except Exception as e:
    print(f"Error: {e}")
