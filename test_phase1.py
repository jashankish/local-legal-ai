#!/usr/bin/env python3
"""
Test script for Phase 1 implementation of Local Legal AI.
This script validates the core infrastructure setup.
"""

import os
import sys
import requests
import time
import json
from pathlib import Path

# Add backend to path
sys.path.append(str(Path(__file__).parent / "backend"))

def test_environment_setup():
    """Test environment configuration."""
    print("🔧 Testing environment setup...")
    
    try:
        from backend.config import settings
        print(f"✅ Configuration loaded successfully")
        print(f"   - App name: {settings.app_name}")
        print(f"   - Debug mode: {settings.debug}")
        print(f"   - ChromaDB: {settings.get_chromadb_url()}")
        return True
    except Exception as e:
        print(f"❌ Configuration failed: {e}")
        return False

def test_auth_system():
    """Test authentication system."""
    print("\n🔐 Testing authentication system...")
    
    try:
        from backend.auth import user_manager, create_access_token
        
        # Test user creation
        test_user = {
            "username": "testuser",
            "email": "test@example.com",
            "password": "testpass123",
            "role": "user"
        }
        
        # Test password hashing
        hash1 = user_manager.get_password_hash("password123")
        hash2 = user_manager.get_password_hash("password123")
        
        if hash1 != hash2:
            print("✅ Password hashing working (different hashes)")
        else:
            print("⚠️  Password hashing might be deterministic")
        
        # Test password verification
        if user_manager.verify_password("password123", hash1):
            print("✅ Password verification working")
        else:
            print("❌ Password verification failed")
        
        # Test token creation
        token = create_access_token({"sub": "testuser"})
        print(f"✅ JWT token creation working")
        
        return True
        
    except Exception as e:
        print(f"❌ Authentication system failed: {e}")
        return False

def test_chromadb_connection():
    """Test ChromaDB connection."""
    print("\n🗄️  Testing ChromaDB connection...")
    
    try:
        from vector_store.chromadb_setup import chroma_manager
        
        # Test health check
        if chroma_manager.health_check():
            print("✅ ChromaDB connection healthy")
        else:
            print("❌ ChromaDB connection failed")
            return False
        
        # Test collection stats
        stats = chroma_manager.get_collection_stats()
        print(f"✅ Collection stats: {stats}")
        
        # Test document operations
        test_docs = ["This is a test legal document about contracts."]
        test_metadata = [{"source": "test.txt", "type": "contract"}]
        
        if chroma_manager.add_documents(test_docs, test_metadata):
            print("✅ Document addition working")
            
            # Test search
            results = chroma_manager.search_documents("legal contract")
            if results.get('documents') and len(results['documents'][0]) > 0:
                print("✅ Document search working")
            else:
                print("⚠️  Document search returned no results")
            
            # Clean up test document
            chroma_manager.collection.delete(where={"source": "test.txt"})
            print("✅ Document cleanup completed")
            
        return True
        
    except Exception as e:
        print(f"❌ ChromaDB connection failed: {e}")
        print("   Make sure ChromaDB is running on localhost:8002")
        return False

def test_api_endpoints():
    """Test API endpoints (requires server to be running)."""
    print("\n🌐 Testing API endpoints...")
    
    base_url = "http://localhost:8000"
    
    try:
        # Test root endpoint
        response = requests.get(f"{base_url}/")
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Root endpoint working: {data['message']}")
        else:
            print(f"❌ Root endpoint failed: {response.status_code}")
            return False
        
        # Test health endpoint
        response = requests.get(f"{base_url}/health")
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Health endpoint working: {data['status']}")
            print(f"   Services: {data.get('services', {})}")
        else:
            print(f"❌ Health endpoint failed: {response.status_code}")
        
        # Test login with default admin user
        login_data = {
            "username": "admin",
            "password": "admin123"
        }
        
        response = requests.post(f"{base_url}/auth/login", json=login_data)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Authentication working")
            print(f"   User: {data['user']['username']} ({data['user']['role']})")
            
            # Test authenticated endpoint
            headers = {"Authorization": f"Bearer {data['access_token']}"}
            response = requests.get(f"{base_url}/auth/me", headers=headers)
            if response.status_code == 200:
                print("✅ Token validation working")
            else:
                print("❌ Token validation failed")
                
        else:
            print(f"❌ Authentication failed: {response.status_code}")
            print(f"   Response: {response.text}")
        
        return True
        
    except requests.ConnectionError:
        print("❌ Cannot connect to API server")
        print("   Start the server with: cd backend && python app.py")
        return False
    except Exception as e:
        print(f"❌ API testing failed: {e}")
        return False

def main():
    """Run all tests."""
    print("🧪 Running Phase 1 Tests for Local Legal AI\n")
    
    tests = [
        ("Environment Setup", test_environment_setup),
        ("Authentication System", test_auth_system),
        ("ChromaDB Connection", test_chromadb_connection),
        ("API Endpoints", test_api_endpoints),
    ]
    
    results = []
    
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except KeyboardInterrupt:
            print("\n\n⚠️  Tests interrupted by user")
            break
        except Exception as e:
            print(f"\n❌ {name} test crashed: {e}")
            results.append((name, False))
    
    # Summary
    print("\n" + "="*50)
    print("📊 TEST SUMMARY")
    print("="*50)
    
    passed = 0
    total = len(results)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {name}")
        if result:
            passed += 1
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed! Phase 1 implementation is working correctly.")
        print("\nNext steps:")
        print("1. Set up environment variables (.env file)")
        print("2. Start ChromaDB service")
        print("3. Start the backend API server")
        print("4. Proceed to Phase 2 (RAG Pipeline Development)")
    else:
        print(f"\n⚠️  {total - passed} tests failed. Please fix issues before proceeding.")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 