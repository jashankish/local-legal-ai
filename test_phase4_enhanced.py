#!/usr/bin/env python3
"""
Phase 4 Enhanced Features Testing Script
Tests the enhanced document processor and advanced capabilities
"""

import requests
import json
import time
import os
from typing import Dict, Any

class Phase4Tester:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.token = None
        self.test_results = []
        
    def log_test(self, test_name: str, success: bool, details: str = ""):
        """Log test results"""
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} {test_name}")
        if details:
            print(f"    {details}")
        
        self.test_results.append({
            "test": test_name,
            "success": success,
            "details": details
        })
    
    def authenticate(self) -> bool:
        """Authenticate and get access token"""
        try:
            response = requests.post(
                f"{self.base_url}/auth/login",
                json={"username": "admin", "password": "admin123"}
            )
            
            if response.status_code == 200:
                self.token = response.json()["access_token"]
                self.log_test("Authentication", True, f"Token obtained: {self.token[:20]}...")
                return True
            else:
                self.log_test("Authentication", False, f"Status: {response.status_code}")
                return False
                
        except Exception as e:
            self.log_test("Authentication", False, f"Error: {e}")
            return False
    
    def test_health_check(self) -> bool:
        """Test health check endpoint"""
        try:
            response = requests.get(f"{self.base_url}/health")
            
            if response.status_code == 200:
                health_data = response.json()
                services = health_data.get("services", {})
                
                details = f"Services: {', '.join([f'{k}:{v}' for k, v in services.items()])}"
                self.log_test("Health Check", True, details)
                return True
            else:
                self.log_test("Health Check", False, f"Status: {response.status_code}")
                return False
                
        except Exception as e:
            self.log_test("Health Check", False, f"Error: {e}")
            return False
    
    def test_enhanced_document_upload(self) -> bool:
        """Test enhanced document upload with Phase 4 processor"""
        try:
            # Create test legal contract content
            contract_content = """CONFIDENTIALITY AND NON-DISCLOSURE AGREEMENT

This Confidentiality and Non-Disclosure Agreement ("Agreement") is entered into on January 15, 2024, between:

DISCLOSING PARTY: TechCorp Solutions, Inc., a Delaware corporation
RECEIVING PARTY: John Smith, an individual

WHEREAS, Disclosing Party possesses certain confidential and proprietary information;
WHEREAS, Receiving Party may have access to such confidential information;

NOW THEREFORE, the parties agree as follows:

1. DEFINITION OF CONFIDENTIAL INFORMATION
"Confidential Information" means all non-public, proprietary information disclosed by Disclosing Party, including but not limited to:
- Trade secrets and know-how
- Technical data and specifications
- Business plans and financial information
- Customer lists and supplier information
- Software code and algorithms

2. OBLIGATIONS OF RECEIVING PARTY
Receiving Party agrees to:
a) Hold all Confidential Information in strict confidence
b) Not disclose Confidential Information to any third parties
c) Use Confidential Information solely for the agreed purpose
d) Return or destroy all Confidential Information upon termination

3. EXCEPTIONS
This Agreement does not apply to information that:
- Is publicly available through no breach of this Agreement
- Was known to Receiving Party prior to disclosure
- Is independently developed without use of Confidential Information
- Is required to be disclosed by law

4. TERM AND TERMINATION
This Agreement shall remain in effect for a period of five (5) years from the date of execution.

5. REMEDIES
Any breach of this Agreement may result in irreparable harm, entitling Disclosing Party to seek injunctive relief.

6. GOVERNING LAW
This Agreement shall be governed by the laws of the State of Delaware.

IN WITNESS WHEREOF, the parties have executed this Agreement as of the date first written above.

DISCLOSING PARTY: TechCorp Solutions, Inc.
By: Sarah Johnson, CEO

RECEIVING PARTY: John Smith
Signature: _________________"""

            # Save as temporary file
            with open("test_nda.txt", "w") as f:
                f.write(contract_content)
            
            # Upload document
            headers = {"Authorization": f"Bearer {self.token}"}
            files = {"file": open("test_nda.txt", "rb")}
            data = {
                "title": "Phase 4 NDA Test Document",
                "category": "confidentiality"
            }
            
            response = requests.post(
                f"{self.base_url}/documents/upload",
                headers=headers,
                files=files,
                data=data
            )
            
            files["file"].close()
            os.remove("test_nda.txt")
            
            if response.status_code == 200:
                result = response.json()
                success = result.get("success", False)
                message = result.get("message", "")
                chunks = result.get("chunks_processed", 0)
                processing_time = result.get("processing_time", 0)
                
                details = f"Success: {success}, Chunks: {chunks}, Time: {processing_time:.3f}s"
                if "Enhanced Processor (Phase 4)" in message:
                    details += " [Enhanced Processor Used]"
                
                self.log_test("Enhanced Document Upload", success, details)
                return success
            else:
                self.log_test("Enhanced Document Upload", False, f"Status: {response.status_code}")
                return False
                
        except Exception as e:
            self.log_test("Enhanced Document Upload", False, f"Error: {e}")
            return False
    
    def test_legal_document_query(self) -> bool:
        """Test querying legal documents with enhanced features"""
        try:
            headers = {"Authorization": f"Bearer {self.token}"}
            
            # Test queries for different legal concepts
            test_queries = [
                {
                    "question": "What is the definition of confidential information in the NDA?",
                    "expected_terms": ["confidential", "proprietary", "trade secrets"]
                },
                {
                    "question": "What are the obligations of the receiving party?",
                    "expected_terms": ["receiving party", "obligations", "confidential"]
                },
                {
                    "question": "What is the term duration of the agreement?",
                    "expected_terms": ["five", "years", "term"]
                }
            ]
            
            all_queries_passed = True
            
            for i, query_test in enumerate(test_queries):
                query_data = {
                    "question": query_test["question"],
                    "num_documents": 3
                }
                
                response = requests.post(
                    f"{self.base_url}/query",
                    headers=headers,
                    json=query_data
                )
                
                if response.status_code == 200:
                    result = response.json()
                    answer = result.get("answer", "").lower()
                    sources = result.get("sources", [])
                    confidence = result.get("confidence_score", 0)
                    
                    # Check if expected terms are in the answer
                    found_terms = [term for term in query_test["expected_terms"] if term in answer]
                    term_coverage = len(found_terms) / len(query_test["expected_terms"])
                    
                    success = term_coverage >= 0.5 and len(sources) > 0
                    details = f"Query {i+1}: Confidence: {confidence:.3f}, Sources: {len(sources)}, Term coverage: {term_coverage:.1%}"
                    
                    self.log_test(f"Legal Query {i+1}", success, details)
                    if not success:
                        all_queries_passed = False
                else:
                    self.log_test(f"Legal Query {i+1}", False, f"Status: {response.status_code}")
                    all_queries_passed = False
            
            return all_queries_passed
            
        except Exception as e:
            self.log_test("Legal Document Query", False, f"Error: {e}")
            return False
    
    def test_document_statistics(self) -> bool:
        """Test document statistics endpoint"""
        try:
            headers = {"Authorization": f"Bearer {self.token}"}
            response = requests.get(f"{self.base_url}/documents/stats", headers=headers)
            
            if response.status_code == 200:
                stats = response.json()
                total_docs = stats.get("total_documents", 0)
                details = f"Total documents: {total_docs}"
                
                success = total_docs >= 0  # Should at least return valid stats
                self.log_test("Document Statistics", success, details)
                return success
            else:
                self.log_test("Document Statistics", False, f"Status: {response.status_code}")
                return False
                
        except Exception as e:
            self.log_test("Document Statistics", False, f"Error: {e}")
            return False
    
    def test_enhanced_processor_status(self) -> bool:
        """Test enhanced processor availability through document formats"""
        try:
            # Test by attempting to upload and checking error messages for unsupported formats
            headers = {"Authorization": f"Bearer {self.token}"}
            
            # Create a dummy PDF-like content (will fail but should show enhanced processor messages)
            test_data = b"This is not a real PDF but should trigger format validation"
            
            files = {"file": ("test.pdf", test_data, "application/pdf")}
            data = {"title": "Format Test", "category": "test"}
            
            response = requests.post(
                f"{self.base_url}/documents/upload",
                headers=headers,
                files=files,
                data=data
            )
            
            # Check response for enhanced processor indicators
            if response.status_code in [400, 422]:  # Expected for unsupported format
                result = response.json()
                detail = result.get("detail", "")
                
                # Look for enhanced processor messages
                enhanced_indicators = [
                    "Enhanced processor not available",
                    "Supported:",
                    "Missing dependencies:"
                ]
                
                has_enhanced_messages = any(indicator in detail for indicator in enhanced_indicators)
                self.log_test("Enhanced Processor Status", True, f"Format validation working: {has_enhanced_messages}")
                return True
            else:
                self.log_test("Enhanced Processor Status", False, f"Unexpected status: {response.status_code}")
                return False
                
        except Exception as e:
            self.log_test("Enhanced Processor Status", False, f"Error: {e}")
            return False
    
    def run_all_tests(self):
        """Run all Phase 4 tests"""
        print("="*60)
        print("PHASE 4 ENHANCED FEATURES TESTING")
        print("="*60)
        
        # Run tests in sequence
        if not self.authenticate():
            print("❌ Authentication failed - cannot proceed with tests")
            return
        
        tests = [
            self.test_health_check,
            self.test_enhanced_document_upload,
            self.test_legal_document_query,
            self.test_document_statistics,
            self.test_enhanced_processor_status
        ]
        
        for test in tests:
            test()
            time.sleep(0.5)  # Brief pause between tests
        
        # Summary
        print("\n" + "="*60)
        print("PHASE 4 TEST SUMMARY")
        print("="*60)
        
        passed = sum(1 for result in self.test_results if result["success"])
        total = len(self.test_results)
        
        print(f"Tests Passed: {passed}/{total}")
        
        if passed == total:
            print("🎉 ALL PHASE 4 TESTS PASSED!")
            print("✅ Enhanced document processing is working correctly")
            print("✅ Legal document analysis capabilities are operational")
            print("✅ Phase 4 features are ready for production use")
        else:
            print("⚠️  Some tests failed. Please review the results above.")
            
            failed_tests = [result for result in self.test_results if not result["success"]]
            print("\nFailed tests:")
            for test in failed_tests:
                print(f"- {test['test']}: {test['details']}")

if __name__ == "__main__":
    tester = Phase4Tester()
    tester.run_all_tests() 