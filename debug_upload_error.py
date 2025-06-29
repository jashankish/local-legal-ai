#!/usr/bin/env python3
import requests
import tempfile
import os
from io import BytesIO

# Get token
response = requests.post('http://localhost:8000/auth/login', json={'username': 'admin', 'password': 'admin123'})
token = response.json()['access_token']

# Try upload with correct content type
legal_doc = '''SERVICE AGREEMENT
This Service Agreement is entered into as of March 15, 2024.
CLIENT: Digital Solutions Corp
SERVICE PROVIDER: TechConsult LLC
Base fee: $150 per hour'''

# Create a file-like object with explicit content type
file_content = legal_doc.encode('utf-8')
file_obj = BytesIO(file_content)

try:
    response = requests.post(
        'http://localhost:8000/documents/upload',
        headers={'Authorization': f'Bearer {token}'},
        files={'file': ('test_service_agreement.txt', file_obj, 'text/plain')},
        data={'title': 'Test Service Agreement', 'category': 'service_agreement'}
    )
    print(f'Status: {response.status_code}')
    print(f'Response: {response.text}')
finally:
    file_obj.close() 