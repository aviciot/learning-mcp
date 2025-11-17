#!/usr/bin/env python3
"""Simple test of search via HTTP"""

import requests
import json

url = "http://localhost:8013/search/docs"
payload = {
    "query": "education",
    "profile": "avi-cohen",
    "top_k": 3
}

print(f"Searching for: '{payload['query']}'")
print(f"Profile: {payload['profile']}\n")

try:
    response = requests.post(url, json=payload)
    response.raise_for_status()
    data = response.json()
    
    results = data.get('results', [])
    print(f"Found {len(results)} results\n")
    print("="*80)
    
    for i, r in enumerate(results, 1):
        score = r.get('score', 0)
        text = r.get('text', '')
        metadata = r.get('metadata', {})
        
        print(f"\nResult #{i} - Score: {score:.4f}")
        print(f"Path: {metadata.get('path', 'N/A')}")
        print(f"Text: {text[:250]}")
        print("-"*80)
        
except requests.exceptions.RequestException as e:
    print(f"Error: {e}")
