
import sys
import os
sys.path.append(r'c:\Python\trade')
from drive_sync import download_from_drive

file_id = '1Isc7NK9dVSZM4bPNeSUYOdoA09GUgXBiGk1QxizMTGQ'
output_path = r'c:\Python\cowork\Report\20260505_latest.xlsx'

try:
    print(f"Downloading {file_id}...")
    content = download_from_drive(file_id)
    if content:
        with open(output_path, 'wb') as f:
            f.write(content)
        print(f"✅ Successfully downloaded to {output_path}")
    else:
        print("❌ Download failed.")
except Exception as e:
    print(f"Error: {e}")
