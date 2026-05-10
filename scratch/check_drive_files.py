
import sys
import os
sys.path.append(r'c:\Python\trade')
from drive_sync import list_files_in_folder

try:
    files = list_files_in_folder('Stock_Analysis_Results')
    if not files:
        print("No files found.")
    else:
        # Sort by createdTime desc (though list_files_in_folder already does this)
        for f in files[:10]:
            print(f"{f.get('name')} | {f.get('createdTime')} | {f.get('id')}")
except Exception as e:
    print(f"Error: {e}")
