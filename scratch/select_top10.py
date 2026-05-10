
import pandas as pd

file_path = r'c:\Python\cowork\Report\20260505_latest.xlsx'
df = pd.read_excel(file_path)

# Filter for stability (Audit Team's focus)
mask = (
    (df['회계감사의견'] == '적정') & 
    (df['내부통제의견'] == '적정') &
    (df['ROE'] > 15) &
    (df['부채비율'] < 100) &
    (df['목표주가'] > 0)
)
top_stocks = df[mask].sort_values(by='외국인순매수', ascending=False).head(10)

for idx, row in top_stocks.iterrows():
    print(f"Code: {row['종목코드']} | Name: {row['종목명']} | ROE: {row['ROE']} | Debt: {row['부채비율']} | Target: {row['목표주가']} | Foreign: {row['외국인순매수']}")
