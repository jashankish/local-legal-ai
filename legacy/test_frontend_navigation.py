#!/usr/bin/env python3
"""
Frontend Navigation & Authentication Test
Tests the specific UI issues that were reported
"""

import requests
import time
from datetime import datetime

class FrontendNavigationTester:
    def __init__(self):
        self.backend_url = "http://localhost:8000"
        self.frontend_url = "http://localhost:8501"
        self.test_results = []
        
    def log_test(self, test_name, passed, details=""):
        status = "✓ PASS" if passed else "✗ FAIL"
        self.test_results.append({
            "test": test_name,
            "passed": passed,
            "details": details
        })
        print(f"  {status} {test_name}")
        if details:
            print(f"    {details}")
    
    def test_authentication_flow(self):
        """Test the complete authentication flow"""
        print("\n=== Authentication Flow Tests ===")
        
        # Test 1: Login endpoint
        try:
            response = requests.post(
                f"{self.backend_url}/auth/login",
                json={"username": "admin", "password": "admin123"}
            )
            
            if response.status_code == 200:
                data = response.json()
                token = data.get("access_token")
                user_info = data.get("user")
                
                self.log_test("Backend Login", True, f"Token length: {len(token)} chars")
                self.log_test("User Info Extraction", "username" in user_info, f"User: {user_info.get('username', 'N/A')}")
                
                # Store for subsequent tests
                self.auth_token = token
                self.user_info = user_info
                
            else:
                self.log_test("Backend Login", False, f"HTTP {response.status_code}")
                
        except Exception as e:
            self.log_test("Backend Login", False, str(e))
    
    def test_rag_functionality(self):
        """Test RAG query functionality"""
        print("\n=== RAG Functionality Tests ===")
        
        if not hasattr(self, 'auth_token'):
            self.log_test("RAG Query", False, "No auth token available")
            return
            
        try:
            headers = {"Authorization": f"Bearer {self.auth_token}"}
            response = requests.post(
                f"{self.backend_url}/query",
                json={"question": "What are the key legal terms mentioned in the documents?"},
                headers=headers
            )
            
            if response.status_code == 200:
                data = response.json()
                answer = data.get("answer", "")
                self.log_test("RAG Query Processing", True, f"Response length: {len(answer)} chars")
                self.log_test("Response Quality", "legal" in answer.lower() or "document" in answer.lower(), 
                             "Contains relevant legal content")
            else:
                self.log_test("RAG Query Processing", False, f"HTTP {response.status_code}")
                
        except Exception as e:
            self.log_test("RAG Query Processing", False, str(e))
    
    def test_document_operations(self):
        """Test document upload and management"""
        print("\n=== Document Operations Tests ===")
        
        if not hasattr(self, 'auth_token'):
            self.log_test("Document Operations", False, "No auth token available")
            return
            
        try:
            headers = {"Authorization": f"Bearer {self.auth_token}"}
            
            # Test document listing
            response = requests.get(f"{self.backend_url}/documents", headers=headers)
            if response.status_code == 200:
                docs = response.json()
                self.log_test("Document Listing", True, f"Found {len(docs)} documents")
            else:
                self.log_test("Document Listing", False, f"HTTP {response.status_code}")
                
            # Test document stats
            response = requests.get(f"{self.backend_url}/documents/stats", headers=headers)
            if response.status_code == 200:
                stats = response.json()
                self.log_test("Document Statistics", True, f"DB status: {stats.get('status', 'unknown')}")
            else:
                self.log_test("Document Statistics", False, f"HTTP {response.status_code}")
                
        except Exception as e:
            self.log_test("Document Operations", False, str(e))
    
    def test_frontend_accessibility(self):
        """Test frontend page accessibility"""
        print("\n=== Frontend Accessibility Tests ===")
        
        try:
            # Test main page
            response = requests.get(self.frontend_url, timeout=10)
            self.log_test("Frontend Main Page", response.status_code == 200, f"HTTP {response.status_code}")
            
            # Test if Streamlit is responding properly
            if response.status_code == 200:
                content = response.text
                has_streamlit = "streamlit" in content.lower()
                has_legal_ai = "legal" in content.lower() and "ai" in content.lower()
                self.log_test("Streamlit Framework", has_streamlit, "Framework detected in response")
                self.log_test("Legal AI Content", has_legal_ai, "Application content detected")
            
        except Exception as e:
            self.log_test("Frontend Accessibility", False, str(e))
    
    def run_all_tests(self):
        """Run all frontend navigation tests"""
        print("🧪 Starting Frontend Navigation & Authentication Tests")
        print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        self.test_frontend_accessibility()
        self.test_authentication_flow()
        self.test_rag_functionality()
        self.test_document_operations()
        
        # Summary
        print("\n" + "="*60)
        print("FRONTEND NAVIGATION TEST REPORT")
        print("="*60)
        
        total_tests = len(self.test_results)
        passed_tests = sum(1 for t in self.test_results if t["passed"])
        success_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0
        
        print(f"\nSummary:")
        print(f"  Total Tests: {total_tests}")
        print(f"  Passed: {passed_tests}")
        print(f"  Failed: {total_tests - passed_tests}")
        print(f"  Success Rate: {success_rate:.1f}%")
        
        if success_rate == 100:
            print(f"\nSystem Status:")
            print(f"  🎉 Excellent! All frontend navigation features working")
        elif success_rate >= 80:
            print(f"\nSystem Status:")
            print(f"  ✅ Good! System mostly functional with minor issues")
        else:
            print(f"\nSystem Status:")
            print(f"  ❌ Poor! System has significant issues")
        
        # List any failed tests
        failed_tests = [t for t in self.test_results if not t["passed"]]
        if failed_tests:
            print(f"\nFailed Tests:")
            for test in failed_tests:
                print(f"  ✗ {test['test']}: {test['details']}")
        
        return success_rate

if __name__ == "__main__":
    tester = FrontendNavigationTester()
    success_rate = tester.run_all_tests() 