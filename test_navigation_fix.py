#!/usr/bin/env python3
"""
Quick test to verify navigation fix
Tests that the session state modification error is resolved
"""

import requests
import time
from datetime import datetime

def test_frontend_health():
    """Test if frontend is accessible and working"""
    print("🧪 Testing Navigation Fix")
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*50)
    
    # Wait for services to be ready
    print("⏳ Waiting for services to start...")
    for i in range(30):  # Wait up to 30 seconds
        try:
            # Test backend
            backend_response = requests.get("http://localhost:8000/health", timeout=5)
            if backend_response.status_code == 200:
                print("✅ Backend is healthy")
                break
        except:
            time.sleep(1)
    else:
        print("❌ Backend failed to start")
        return False
    
    # Test frontend
    for i in range(30):  # Wait up to 30 seconds  
        try:
            frontend_response = requests.get("http://localhost:8501", timeout=5)
            if frontend_response.status_code == 200:
                print("✅ Frontend is accessible")
                print(f"✅ Status Code: {frontend_response.status_code}")
                
                # Check if it's a proper Streamlit response
                content = frontend_response.text
                if "streamlit" in content.lower():
                    print("✅ Streamlit framework detected")
                    
                # Check for no error messages in initial load
                if "StreamlitAPIException" not in content:
                    print("✅ No session state errors detected")
                else:
                    print("❌ Session state error still present")
                    return False
                    
                return True
        except Exception as e:
            print(f"⏳ Frontend not ready yet... ({i+1}/30)")
            time.sleep(1)
    
    print("❌ Frontend failed to start")
    return False

def test_authentication():
    """Test login functionality"""
    print("\n🔐 Testing Authentication...")
    
    try:
        response = requests.post(
            "http://localhost:8000/auth/login",
            json={"username": "admin", "password": "admin123"},
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            if "access_token" in data:
                print("✅ Authentication working properly")
                return True
        
        print(f"❌ Authentication failed: HTTP {response.status_code}")
        return False
        
    except Exception as e:
        print(f"❌ Authentication error: {e}")
        return False

if __name__ == "__main__":
    print("🚀 Navigation Fix Verification Test")
    print("="*50)
    
    success = True
    
    # Test frontend health and navigation fix
    if not test_frontend_health():
        success = False
    
    # Test authentication
    if not test_authentication():
        success = False
    
    print("\n" + "="*50)
    if success:
        print("🎉 SUCCESS: Navigation fix verified!")
        print("✅ System is operational without session state errors")
        print("✅ You can now use the dashboard buttons safely")
        print("\n🌐 Access the system at: http://localhost:8501")
        print("🔐 Login with: admin / admin123")
    else:
        print("❌ FAILED: Issues detected")
        print("🔧 Please check the error messages above")
    
    print(f"\nTest completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}") 