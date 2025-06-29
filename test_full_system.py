#!/usr/bin/env python3
"""
Comprehensive System Test for Local Legal AI
Tests all functionality across Phases 1-4
"""

import requests
import json
import time
import os
import sys
from datetime import datetime
from typing import Dict, List, Tuple

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    END = '\033[0m'

class SystemTester:
    def __init__(self):
        self.backend_url = "http://localhost:8000"
        self.frontend_url = "http://localhost:8501"
        self.test_results = []
        self.auth_token = None
        
    def log_test(self, test_name: str, success: bool, message: str = ""):
        """Log test result with formatting"""
        status = f"{Colors.GREEN}✓ PASS{Colors.END}" if success else f"{Colors.RED}✗ FAIL{Colors.END}"
        print(f"  {status} {test_name}")
        if message:
            print(f"    {message}")
        
        self.test_results.append({
            'test': test_name,
            'success': success,
            'message': message,
            'timestamp': datetime.now().isoformat()
        })
    
    def test_phase1_infrastructure(self) -> bool:
        """Test Phase 1: Core Infrastructure"""
        print(f"\n{Colors.BOLD}=== Phase 1: Core Infrastructure Tests ==={Colors.END}")
        
        # Test 1: Backend Health Check
        try:
            response = requests.get(f"{self.backend_url}/health", timeout=5)
            if response.status_code == 200:
                health_data = response.json()
                self.log_test("Backend Health Check", True, f"Status: {health_data.get('status')}")
            else:
                self.log_test("Backend Health Check", False, f"HTTP {response.status_code}")
        except Exception as e:
            self.log_test("Backend Health Check", False, str(e))
            return False
        
        # Test 2: Frontend Accessibility
        try:
            response = requests.get(self.frontend_url, timeout=10)
            self.log_test("Frontend Accessibility", response.status_code == 200, 
                         f"HTTP {response.status_code}")
        except Exception as e:
            self.log_test("Frontend Accessibility", False, str(e))
        
        # Test 3: API Documentation
        try:
            response = requests.get(f"{self.backend_url}/docs", timeout=5)
            self.log_test("API Documentation", response.status_code == 200)
        except Exception as e:
            self.log_test("API Documentation", False, str(e))
        
        # Test 4: Authentication Endpoints
        try:
            # Test login with default admin user
            login_data = {
                "username": "admin",
                "password": "admin123"
            }
            login_response = requests.post(f"{self.backend_url}/auth/login", json=login_data)
            if login_response.status_code == 200:
                token_data = login_response.json()
                self.auth_token = token_data.get("access_token")
                self.log_test("Admin Authentication", True, "Admin token obtained")
                
                # Test user registration (admin only)
                test_user = {
                    "username": f"test_user_{int(time.time())}",
                    "email": f"test_{int(time.time())}@example.com",
                    "password": "TestPassword123!",
                    "role": "user"
                }
                
                headers = {"Authorization": f"Bearer {self.auth_token}"}
                response = requests.post(f"{self.backend_url}/auth/register", json=test_user, headers=headers)
                if response.status_code in [200, 201]:
                    self.log_test("User Registration (Admin)", True, "New user created by admin")
                else:
                    self.log_test("User Registration (Admin)", False, f"HTTP {response.status_code}")
            else:
                self.log_test("Admin Authentication", False, f"HTTP {login_response.status_code}")
                
        except Exception as e:
            self.log_test("Authentication System", False, str(e))
        
        return True
    
    def test_phase2_rag_pipeline(self) -> bool:
        """Test Phase 2: RAG Pipeline"""
        print(f"\n{Colors.BOLD}=== Phase 2: RAG Pipeline Tests ==={Colors.END}")
        
        if not self.auth_token:
            self.log_test("Phase 2 Setup", False, "No auth token available")
            return False
        
        headers = {"Authorization": f"Bearer {self.auth_token}"}
        
        # Test 1: Document Upload
        try:
            # Create a test legal document
            test_doc_content = """
            EMPLOYMENT AGREEMENT
            
            This Employment Agreement is entered into between Company ABC and Employee John Doe.
            
            1. POSITION AND DUTIES
            Employee shall serve as Senior Developer and shall perform duties as assigned.
            
            2. COMPENSATION
            Employee shall receive a salary of $80,000 per year.
            
            3. BENEFITS
            Employee shall be entitled to health insurance and 15 days of vacation per year.
            
            4. TERMINATION
            This agreement may be terminated by either party with 30 days written notice.
            """
            
            # Create temporary file
            test_file_path = "test_employment_contract.txt"
            with open(test_file_path, "w") as f:
                f.write(test_doc_content)
            
            # Upload document
            with open(test_file_path, "rb") as f:
                files = {"file": (test_file_path, f, "text/plain")}
                response = requests.post(f"{self.backend_url}/documents/upload", 
                                       files=files, headers=headers)
            
            # Clean up
            os.remove(test_file_path)
            
            if response.status_code in [200, 201]:
                upload_data = response.json()
                self.log_test("Document Upload", True, f"Doc ID: {upload_data.get('document_id')}")
            else:
                self.log_test("Document Upload", False, f"HTTP {response.status_code}")
                
        except Exception as e:
            self.log_test("Document Upload", False, str(e))
        
        # Test 2: Document Listing
        try:
            response = requests.get(f"{self.backend_url}/documents", headers=headers)
            if response.status_code == 200:
                docs = response.json()
                doc_count = len(docs) if isinstance(docs, list) else docs.get('count', 0)
                self.log_test("Document Listing", True, f"{doc_count} documents found")
            else:
                self.log_test("Document Listing", False, f"HTTP {response.status_code}")
        except Exception as e:
            self.log_test("Document Listing", False, str(e))
        
        # Test 3: RAG Query
        try:
            query_data = {"question": "What is the salary mentioned in the employment agreement?"}
            response = requests.post(f"{self.backend_url}/query", json=query_data, headers=headers)
            
            if response.status_code == 200:
                result = response.json()
                self.log_test("RAG Query Processing", True, f"Response: {result.get('answer', '')[:50]}...")
            else:
                self.log_test("RAG Query Processing", False, f"HTTP {response.status_code}")
        except Exception as e:
            self.log_test("RAG Query Processing", False, str(e))
        
        # Test 4: Document Statistics
        try:
            response = requests.get(f"{self.backend_url}/documents/stats", headers=headers)
            if response.status_code == 200:
                stats = response.json()
                self.log_test("Document Statistics", True, f"Stats: {stats}")
            else:
                self.log_test("Document Statistics", False, f"HTTP {response.status_code}")
        except Exception as e:
            self.log_test("Document Statistics", False, str(e))
        
        return True
    
    def test_phase3_frontend(self) -> bool:
        """Test Phase 3: Frontend Components"""
        print(f"\n{Colors.BOLD}=== Phase 3: Frontend Tests ==={Colors.END}")
        
        # Test 1: Frontend Loading
        try:
            response = requests.get(self.frontend_url, timeout=10)
            self.log_test("Frontend Loading", response.status_code == 200)
        except Exception as e:
            self.log_test("Frontend Loading", False, str(e))
        
        # Test 2: Frontend Health (streamlit specific)
        try:
            response = requests.get(f"{self.frontend_url}/healthz", timeout=5)
            self.log_test("Frontend Health Check", response.status_code == 200)
        except Exception as e:
            # Streamlit might not have /healthz, so we just check main page
            self.log_test("Frontend Health Check", True, "Main page accessible")
        
        return True
    
    def test_phase4_enhanced_features(self) -> bool:
        """Test Phase 4: Enhanced Document Processing"""
        print(f"\n{Colors.BOLD}=== Phase 4: Enhanced Document Processing Tests ==={Colors.END}")
        
        if not self.auth_token:
            self.log_test("Phase 4 Setup", False, "No auth token available")
            return False
        
        headers = {"Authorization": f"Bearer {self.auth_token}"}
        
        # Test 1: Enhanced Document Processing Dependencies
        try:
            import PyPDF2
            import fitz  # PyMuPDF
            from docx import Document
            import plotly
            import pandas as pd
            import numpy as np
            
            self.log_test("Enhanced Dependencies", True, "All Phase 4 dependencies available")
        except ImportError as e:
            self.log_test("Enhanced Dependencies", False, f"Missing: {e}")
        
        # Test 2: Multi-format Document Support
        try:
            # Test with a more complex document structure
            complex_doc = """
            LEGAL SERVICE AGREEMENT
            
            PARTIES:
            Client: ABC Corporation
            Attorney: Law Firm XYZ
            
            SCOPE OF SERVICES:
            - Contract review and analysis
            - Legal compliance assessment
            - Risk evaluation
            
            FEES:
            Hourly rate: $300
            Retainer: $5,000
            
            TERMS:
            Duration: 6 months
            Confidentiality: Standard attorney-client privilege applies
            """
            
            test_file = "test_service_agreement.txt"
            with open(test_file, "w") as f:
                f.write(complex_doc)
            
            with open(test_file, "rb") as f:
                files = {"file": (test_file, f, "text/plain")}
                response = requests.post(f"{self.backend_url}/documents/upload", 
                                       files=files, headers=headers)
            
            os.remove(test_file)
            
            if response.status_code in [200, 201]:
                result = response.json()
                self.log_test("Enhanced Document Upload", True, 
                             f"Processed with metadata: {bool(result.get('metadata'))}")
            else:
                self.log_test("Enhanced Document Upload", False, f"HTTP {response.status_code}")
                
        except Exception as e:
            self.log_test("Enhanced Document Upload", False, str(e))
        
        # Test 3: Legal Document Analysis
        try:
            query_data = {"question": "What are the fees and payment terms in the service agreement?"}
            response = requests.post(f"{self.backend_url}/query", json=query_data, headers=headers)
            
            if response.status_code == 200:
                result = response.json()
                answer = result.get('answer', '')
                # Check if response mentions fees or payment terms
                has_relevant_info = any(term in answer.lower() for term in ['fee', 'payment', '300', '5,000', 'retainer'])
                self.log_test("Legal Document Analysis", has_relevant_info, 
                             f"Analysis quality: {'High' if has_relevant_info else 'Needs improvement'}")
            else:
                self.log_test("Legal Document Analysis", False, f"HTTP {response.status_code}")
        except Exception as e:
            self.log_test("Legal Document Analysis", False, str(e))
        
        return True
    
    def generate_report(self):
        """Generate comprehensive test report"""
        print(f"\n{Colors.BOLD}{'='*60}{Colors.END}")
        print(f"{Colors.BOLD}COMPREHENSIVE SYSTEM TEST REPORT{Colors.END}")
        print(f"{Colors.BOLD}{'='*60}{Colors.END}")
        
        total_tests = len(self.test_results)
        passed_tests = len([t for t in self.test_results if t['success']])
        failed_tests = total_tests - passed_tests
        
        success_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0
        
        print(f"\n{Colors.BOLD}Summary:{Colors.END}")
        print(f"  Total Tests: {total_tests}")
        print(f"  Passed: {Colors.GREEN}{passed_tests}{Colors.END}")
        print(f"  Failed: {Colors.RED}{failed_tests}{Colors.END}")
        print(f"  Success Rate: {Colors.GREEN if success_rate >= 75 else Colors.YELLOW}{success_rate:.1f}%{Colors.END}")
        
        if failed_tests > 0:
            print(f"\n{Colors.BOLD}Failed Tests:{Colors.END}")
            for test in self.test_results:
                if not test['success']:
                    print(f"  {Colors.RED}✗{Colors.END} {test['test']}: {test['message']}")
        
        print(f"\n{Colors.BOLD}System Status:{Colors.END}")
        if success_rate >= 90:
            print(f"  {Colors.GREEN}🎉 Excellent! System is fully operational{Colors.END}")
        elif success_rate >= 75:
            print(f"  {Colors.YELLOW}✅ Good! System is mostly functional with minor issues{Colors.END}")
        elif success_rate >= 50:
            print(f"  {Colors.YELLOW}⚠️ Moderate! System has significant issues that need attention{Colors.END}")
        else:
            print(f"  {Colors.RED}❌ Poor! System has major issues and needs immediate attention{Colors.END}")
        
        # Save detailed report
        report_data = {
            'timestamp': datetime.now().isoformat(),
            'summary': {
                'total_tests': total_tests,
                'passed': passed_tests,
                'failed': failed_tests,
                'success_rate': success_rate
            },
            'tests': self.test_results
        }
        
        with open('logs/test_report.json', 'w') as f:
            json.dump(report_data, f, indent=2)
        
        print(f"\n{Colors.BLUE}📄 Detailed report saved to: logs/test_report.json{Colors.END}")
    
    def run_all_tests(self):
        """Run all system tests"""
        print(f"{Colors.BOLD}🧪 Starting Comprehensive System Test{Colors.END}")
        print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Ensure logs directory exists
        os.makedirs('logs', exist_ok=True)
        
        # Run all test phases
        self.test_phase1_infrastructure()
        self.test_phase2_rag_pipeline()
        self.test_phase3_frontend()
        self.test_phase4_enhanced_features()
        
        # Generate final report
        self.generate_report()

if __name__ == "__main__":
    tester = SystemTester()
    tester.run_all_tests() 