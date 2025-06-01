#!/usr/bin/env python3
import requests

response = requests.post('http://localhost:8000/auth/login', json={'username': 'admin', 'password': 'admin123'})
token = response.json()['access_token']

response = requests.get('http://localhost:8000/documents/stats', headers={'Authorization': f'Bearer {token}'})
print('Document stats:', response.json())

# Also test a simple query
response = requests.post('http://localhost:8000/query', 
    headers={'Authorization': f'Bearer {token}'},
    json={'question': 'What documents are in the system?', 'num_documents': 5})
print('Query response:')
print('- Sources found:', len(response.json().get('sources', [])))
print('- Confidence:', response.json().get('confidence_score'))
print('- Answer preview:', response.json().get('answer', '')[:200] + '...') 