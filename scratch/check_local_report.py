
import pandas as pd
file_path = r'c:\Python\cowork\Report\20260412.xlsx'
try:
    df = pd.read_excel(file_path, nrows=5)
    print("Columns:", df.columns.tolist())
    print("First row:", df.iloc[0].to_dict())
except Exception as e:
    print(f"Error: {e}")
