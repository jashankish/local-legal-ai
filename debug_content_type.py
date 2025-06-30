#!/usr/bin/env python3
"""
Debug script to check content type detection
"""

import os
import tempfile
import mimetypes

# Test content type detection
legal_doc = '''SERVICE AGREEMENT
This Service Agreement is entered into as of March 15, 2024.
CLIENT: Digital Solutions Corp
SERVICE PROVIDER: TechConsult LLC
Base fee: $150 per hour'''

# Create temporary file with different methods
with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
    f.write(legal_doc)
    temp_file = f.name

print(f"Temp file: {temp_file}")
print(f"MIME type from filename: {mimetypes.guess_type(temp_file)}")

# Test what FastAPI would detect
try:
    import magic
    file_type = magic.from_file(temp_file, mime=True)
    print(f"Magic library detection: {file_type}")
except ImportError as e:
    print(f"Magic library not available: {e}")
    print("Install with: brew install libmagic && pip install python-magic")
except Exception as e:
    print(f"Magic library error: {e}")

# Cleanup
os.unlink(temp_file) 