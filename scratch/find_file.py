
import sys
import os
sys.path.append(r'c:\Python\trade')
from drive_sync import get_drive_service

def find_specific_file(name):
    try:
        service = get_drive_service()
        query = f"name contains '{name}' and trashed = false"
        results = service.files().list(q=query, fields="files(id, name, createdTime, webViewLink)").execute()
        files = results.get('files', [])
        for f in files:
            print(f"{f['name']} | {f['createdTime']} | {f['webViewLink']} | {f['id']}")
        return len(files)
    except Exception as e:
        print(f"Error: {e}")
        return -1

find_specific_file('kospi_all_20260505')
