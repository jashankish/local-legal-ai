#!/usr/bin/env python3
"""
Frontend startup script for Local Legal AI
"""

import subprocess
import sys
import os

def main():
    """Run the Streamlit frontend application."""
    
    # Change to frontend directory
    frontend_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(frontend_dir)
    
    print("🚀 Starting Local Legal AI Frontend...")
    print("📍 Backend should be running on http://localhost:8000")
    print("🌐 Frontend will be available on http://localhost:8501")
    print("=" * 60)
    
    try:
        # Run Streamlit app
        subprocess.run([
            sys.executable, "-m", "streamlit", "run", 
            "streamlit_app.py",
            "--server.port", "8501",
            "--server.address", "0.0.0.0",
            "--browser.gatherUsageStats", "false"
        ])
    except KeyboardInterrupt:
        print("\n👋 Frontend stopped")
    except Exception as e:
        print(f"❌ Error running frontend: {e}")

if __name__ == "__main__":
    main() 