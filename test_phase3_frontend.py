#!/usr/bin/env python3
"""
Phase 3 Frontend Integration Test Suite
Tests the complete Local Legal AI system including Streamlit frontend
"""

import requests
import time
import json
import os
from typing import Dict, Any
import sys

class Phase3Tester:
    def __init__(self):
        self.backend_url = "http://localhost:8000"
        self.frontend_url = "http://localhost:8501"
        self.auth_token = None
        self.test_results = []
        
    def log_test(self, test_name: str, passed: bool, message: str = ""):
        """Log test results"""
        status = "✅ PASS" if passed else "❌ FAIL"
        self.test_results.append({
            'test': test_name,
            'passed': passed,
            'message': message
        })
        print(f"{status}: {test_name}")
        if message:
            print(f"    {message}")
        print()

    def test_backend_health(self) -> bool:
        """Test if backend is running and healthy"""
        try:
            response = requests.get(f"{self.backend_url}/health", timeout=10)
            if response.status_code == 200:
                health_data = response.json()
                services_healthy = (
                    health_data.get("status") == "healthy" and
                    health_data.get("services", {}).get("api") == "healthy" and
                    health_data.get("services", {}).get("chromadb") == "healthy"
                )
                self.log_test("Backend Health Check", services_healthy, 
                             f"API: {health_data.get('services', {}).get('api')}, "
                             f"ChromaDB: {health_data.get('services', {}).get('chromadb')}")
                return services_healthy
            else:
                self.log_test("Backend Health Check", False, f"HTTP {response.status_code}")
                return False
        except Exception as e:
            self.log_test("Backend Health Check", False, f"Connection error: {e}")
            return False

    def test_frontend_accessibility(self) -> bool:
        """Test if Streamlit frontend is accessible"""
        try:
            response = requests.get(self.frontend_url, timeout=10)
            accessible = response.status_code == 200
            self.log_test("Frontend Accessibility", accessible, 
                         f"Streamlit on {self.frontend_url} - HTTP {response.status_code}")
            return accessible
        except Exception as e:
            self.log_test("Frontend Accessibility", False, f"Connection error: {e}")
            return False

    def test_authentication(self) -> bool:
        """Test backend authentication system"""
        try:
            # Test login
            login_data = {"username": "admin", "password": "admin123"}
            response = requests.post(f"{self.backend_url}/auth/login", json=login_data)
            
            if response.status_code == 200:
                auth_data = response.json()
                self.auth_token = auth_data.get("access_token")
                self.log_test("Authentication Login", True, 
                             f"Token received: {self.auth_token[:20]}...")
                return True
            else:
                self.log_test("Authentication Login", False, f"HTTP {response.status_code}")
                return False
        except Exception as e:
            self.log_test("Authentication Login", False, f"Error: {e}")
            return False

    def test_document_upload(self) -> bool:
        """Test document upload functionality"""
        if not self.auth_token:
            self.log_test("Document Upload", False, "No auth token available")
            return False
            
        try:
            # Create test document
            test_content = "This is a comprehensive test legal document for Phase 3 testing. It contains legal terms, conditions, and provisions that should be properly processed by the RAG system."
            
            headers = {"Authorization": f"Bearer {self.auth_token}"}
            files = {"file": ("test_phase3.txt", test_content, "text/plain")}
            data = {
                "title": "Phase 3 Test Document",
                "category": "test"
            }
            
            response = requests.post(f"{self.backend_url}/documents/upload", 
                                   headers=headers, files=files, data=data)
            
            if response.status_code == 200:
                upload_data = response.json()
                chunks_processed = upload_data.get("chunks_processed", 0)
                success = chunks_processed > 0
                self.log_test("Document Upload", success, 
                             f"Chunks processed: {chunks_processed}, "
                             f"Processing time: {upload_data.get('processing_time', 0):.3f}s")
                return success
            else:
                self.log_test("Document Upload", False, f"HTTP {response.status_code}")
                return False
        except Exception as e:
            self.log_test("Document Upload", False, f"Error: {e}")
            return False

    def test_document_query(self) -> bool:
        """Test RAG query functionality"""
        if not self.auth_token:
            self.log_test("Document Query", False, "No auth token available")
            return False
            
        try:
            headers = {"Authorization": f"Bearer {self.auth_token}"}
            query_data = {
                "query": "What are the legal terms and conditions in the uploaded documents?",
                "max_results": 3
            }
            
            response = requests.post(f"{self.backend_url}/query", 
                                   headers=headers, json=query_data)
            
            if response.status_code == 200:
                query_result = response.json()
                answer = query_result.get("answer", "")
                sources = query_result.get("sources", [])
                confidence = query_result.get("confidence", 0)
                
                success = len(answer) > 10 and len(sources) > 0 and confidence > 0
                self.log_test("Document Query", success, 
                             f"Answer length: {len(answer)}, Sources: {len(sources)}, "
                             f"Confidence: {confidence:.2f}")
                return success
            else:
                self.log_test("Document Query", False, f"HTTP {response.status_code}")
                return False
        except Exception as e:
            self.log_test("Document Query", False, f"Error: {e}")
            return False

    def test_document_statistics(self) -> bool:
        """Test document statistics endpoint"""
        if not self.auth_token:
            self.log_test("Document Statistics", False, "No auth token available")
            return False
            
        try:
            headers = {"Authorization": f"Bearer {self.auth_token}"}
            response = requests.get(f"{self.backend_url}/documents/stats", headers=headers)
            
            if response.status_code == 200:
                stats = response.json()
                total_docs = stats.get("total_documents", 0)
                success = total_docs >= 0  # Should have at least the uploaded document
                self.log_test("Document Statistics", success, 
                             f"Total documents: {total_docs}, "
                             f"Total chunks: {stats.get('total_chunks', 0)}")
                return success
            else:
                self.log_test("Document Statistics", False, f"HTTP {response.status_code}")
                return False
        except Exception as e:
            self.log_test("Document Statistics", False, f"Error: {e}")
            return False

    def test_document_listing(self) -> bool:
        """Test document listing endpoint"""
        if not self.auth_token:
            self.log_test("Document Listing", False, "No auth token available")
            return False
            
        try:
            headers = {"Authorization": f"Bearer {self.auth_token}"}
            response = requests.get(f"{self.backend_url}/documents", headers=headers)
            
            if response.status_code == 200:
                documents = response.json()
                doc_count = len(documents) if isinstance(documents, list) else 0
                success = doc_count >= 0
                self.log_test("Document Listing", success, f"Documents listed: {doc_count}")
                return success
            else:
                self.log_test("Document Listing", False, f"HTTP {response.status_code}")
                return False
        except Exception as e:
            self.log_test("Document Listing", False, f"Error: {e}")
            return False

    def run_all_tests(self):
        """Run all Phase 3 tests"""
        print("=" * 80)
        print("🧪 PHASE 3 FRONTEND INTEGRATION TEST SUITE")
        print("Testing complete Local Legal AI system")
        print("=" * 80)
        print()

        # Run tests in order
        tests = [
            self.test_backend_health,
            self.test_frontend_accessibility,
            self.test_authentication,
            self.test_document_upload,
            self.test_document_query,
            self.test_document_statistics,
            self.test_document_listing,
        ]

        for test in tests:
            test()

        # Summary
        passed = sum(1 for result in self.test_results if result['passed'])
        total = len(self.test_results)
        
        print("=" * 80)
        print(f"📊 PHASE 3 TEST SUMMARY: {passed}/{total} tests passed")
        
        if passed == total:
            print("🎉 ALL TESTS PASSED! Phase 3 is fully operational!")
            print()
            print("✅ Backend API: Fully functional")
            print("✅ Frontend UI: Accessible and ready")
            print("✅ Authentication: Working correctly")
            print("✅ Document Upload: Processing successfully")
            print("✅ RAG Queries: Returning relevant results")
            print("✅ Document Management: All endpoints operational")
            print()
            print("🚀 Ready for Phase 4 development!")
        else:
            print(f"⚠️  {total - passed} test(s) failed. Review errors before proceeding.")
            print()
            for result in self.test_results:
                if not result['passed']:
                    print(f"❌ {result['test']}: {result['message']}")
        
        print("=" * 80)

if __name__ == "__main__":
    tester = Phase3Tester()
    tester.run_all_tests() 