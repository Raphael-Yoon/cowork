
import sys
import os
sys.path.append(r'c:\Python\trade')
from drive_sync import get_drive_service

def search_drive(query):
    try:
        service = get_drive_service()
        results = service.files().list(q=query, fields="files(id, name, createdTime)").execute()
        files = results.get('files', [])
        for f in files:
            print(f"{f['name']} | {f['id']} | {f['createdTime']}")
    except Exception as e:
        print(f"Error: {e}")

search_drive("name contains '20260505'")
