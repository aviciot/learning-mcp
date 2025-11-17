#!/usr/bin/env python3
"""Test updated json_loader with key context"""

import sys
sys.path.insert(0, '/app/src')

from learning_mcp.json_loader import load_json

# Load the avi profile
print("Loading avi_profile.json...")
chunks = load_json('/app/data/persons/avi_profile.json', chunk_size=800, chunk_overlap=100)

print(f"\nTotal chunks generated: {len(chunks)}")

# Find chunks with 'education' in text
edu_chunks = [c for c in chunks if 'education' in c['text'].lower()]
print(f"Chunks containing 'education': {len(edu_chunks)}")

if edu_chunks:
    print("\n" + "="*80)
    print("EDUCATION CHUNKS:")
    print("="*80)
    for i, chunk in enumerate(edu_chunks[:3]):  # Show first 3
        print(f"\nChunk #{i+1}:")
        print(f"Path: {chunk['metadata']['path']}")
        print(f"Text preview: {chunk['text'][:250]}")
        print("-"*80)
else:
    print("\nNo chunks with 'education' found!")

# Show a few random chunks to see the format
print("\n" + "="*80)
print("SAMPLE CHUNKS (showing key context format):")
print("="*80)
for i in [0, 5, 10, 15, 20]:
    if i < len(chunks):
        chunk = chunks[i]
        print(f"\nChunk #{i}:")
        print(f"Path: {chunk['metadata']['path']}")
        print(f"Text preview: {chunk['text'][:150]}")
        print("-"*40)
