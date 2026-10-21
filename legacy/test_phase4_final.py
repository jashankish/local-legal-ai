#!/usr/bin/env python3
"""
Final Phase 4 Comprehensive Test - Demonstrating Enhanced Document Processing
Tests all working features of the Phase 4 enhanced system
"""

import requests
import json
import time
from io import BytesIO
import os

class Phase4FinalTest:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.token = None
        
    def authenticate(self):
        """Get authentication token"""
        response = requests.post(
            f"{self.base_url}/auth/login",
            json={"username": "admin", "password": "admin123"}
        )
        if response.status_code == 200:
            self.token = response.json()["access_token"]
            print("✅ Authentication successful")
            return True
        return False
    
    def test_enhanced_processor_capabilities(self):
        """Test Phase 4 enhanced document processor capabilities"""
        print("\n🚀 PHASE 4 ENHANCED PROCESSOR CAPABILITIES")
        print("=" * 60)
        
        # Test 1: Upload a comprehensive legal document
        print("\n1. Testing Enhanced Document Upload...")
        
        legal_document = """SERVICE AGREEMENT

This Service Agreement ("Agreement") is entered into as of March 15, 2024, between:

CLIENT: Digital Solutions Corp, a California corporation
SERVICE PROVIDER: TechConsult LLC, a Delaware limited liability company

RECITALS
WHEREAS, Client desires to engage Service Provider for professional consulting services;
WHEREAS, Service Provider has the expertise and capabilities to provide such services;

NOW THEREFORE, the parties agree as follows:

ARTICLE 1: SERVICES
1.1 Scope of Work: Service Provider shall provide software development consulting services including:
    a) System architecture design
    b) Code review and optimization
    c) Technical documentation
    d) Performance analysis

1.2 Deliverables: Service Provider shall deliver:
    - Detailed technical specifications
    - Source code with documentation
    - Performance optimization reports
    - Monthly progress reports

ARTICLE 2: COMPENSATION
2.1 Fee Structure: Client shall pay Service Provider:
    - Base fee: $150 per hour
    - Minimum commitment: 20 hours per week
    - Maximum total: $50,000 for initial phase

2.2 Payment Terms: Invoices shall be paid within thirty (30) days of receipt.

ARTICLE 3: CONFIDENTIALITY
3.1 Confidential Information: Both parties acknowledge that they may receive confidential information.
3.2 Non-Disclosure: Each party agrees to maintain confidentiality of all proprietary information.

ARTICLE 4: INTELLECTUAL PROPERTY
4.1 Work Product: All work product created shall be owned by Client.
4.2 Pre-existing IP: Service Provider retains rights to pre-existing intellectual property.

ARTICLE 5: TERM AND TERMINATION
5.1 Term: This Agreement shall commence on April 1, 2024 and continue for six (6) months.
5.2 Termination: Either party may terminate with thirty (30) days written notice.

ARTICLE 6: LIABILITY AND INDEMNIFICATION
6.1 Limitation of Liability: Service Provider's liability shall not exceed the total fees paid.
6.2 Indemnification: Each party shall indemnify the other for certain claims.

ARTICLE 7: GENERAL PROVISIONS
7.1 Governing Law: This Agreement shall be governed by California law.
7.2 Entire Agreement: This Agreement constitutes the entire agreement between the parties.
7.3 Amendments: Modifications must be in writing and signed by both parties.

IN WITNESS WHEREOF, the parties have executed this Agreement.

CLIENT: Digital Solutions Corp
By: Michael Chen, CEO
Date: March 15, 2024

SERVICE PROVIDER: TechConsult LLC  
By: Sarah Rodriguez, Managing Partner
Date: March 15, 2024"""

        headers = {"Authorization": f"Bearer {self.token}"}
        
        # Create file-like object with explicit content type
        file_content = legal_document.encode('utf-8')
        file_obj = BytesIO(file_content)
        
        try:
            files = {"file": ("phase4_service_agreement.txt", file_obj, "text/plain")}
            data = {
                "title": "Phase 4 Service Agreement Demo",
                "category": "service_agreement"
            }
            
            response = requests.post(
                f"{self.base_url}/documents/upload",
                headers=headers,
                files=files,
                data=data
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get("success") and "Enhanced Processor (Phase 4)" in result.get("message", ""):
                    print(f"   ✅ Enhanced document uploaded successfully")
                    print(f"   📄 Chunks processed: {result.get('chunks_processed')}")
                    print(f"   ⏱️  Processing time: {result.get('processing_time'):.3f}s")
                    return True
                else:
                    print(f"   ❌ Upload failed: {result.get('message')}")
            else:
                print(f"   ❌ Upload request failed: {response.status_code}")
                print(f"   📝 Response: {response.text}")
                
        finally:
            file_obj.close()
        
        return False
    
    def test_legal_document_analysis(self):
        """Test enhanced legal document analysis capabilities"""
        print("\n2. Testing Legal Document Analysis...")
        
        headers = {"Authorization": f"Bearer {self.token}"}
        
        # Test queries that demonstrate legal understanding
        test_queries = [
            {
                "question": "What is the hourly rate in the service agreement?",
                "expected_keywords": ["150", "hour", "fee"]
            },
            {
                "question": "What are the termination provisions?",
                "expected_keywords": ["thirty", "30", "days", "notice"]
            },
            {
                "question": "Who owns the intellectual property created under this agreement?",
                "expected_keywords": ["client", "work product", "owned"]
            },
            {
                "question": "What is the governing law for this contract?",
                "expected_keywords": ["california", "law", "governed"]
            }
        ]
        
        successful_queries = 0
        
        for i, query in enumerate(test_queries, 1):
            query_data = {
                "question": query["question"],
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
                
                # Check if answer contains expected keywords
                found_keywords = [kw for kw in query["expected_keywords"] if kw.lower() in answer]
                keyword_score = len(found_keywords) / len(query["expected_keywords"])
                
                if keyword_score >= 0.5 and sources:
                    print(f"   ✅ Query {i}: Found relevant information (confidence: {confidence:.3f})")
                    successful_queries += 1
                else:
                    print(f"   ⚠️  Query {i}: Limited relevance (confidence: {confidence:.3f})")
            else:
                print(f"   ❌ Query {i}: Request failed")
        
        success_rate = successful_queries / len(test_queries)
        print(f"   📊 Analysis success rate: {success_rate:.1%} ({successful_queries}/{len(test_queries)})")
        
        return success_rate >= 0.5
    
    def test_document_management(self):
        """Test document management capabilities"""
        print("\n3. Testing Document Management...")
        
        headers = {"Authorization": f"Bearer {self.token}"}
        
        # Get document statistics
        response = requests.get(f"{self.base_url}/documents/stats", headers=headers)
        if response.status_code == 200:
            stats = response.json()
            doc_count = stats.get("document_count", 0)
            print(f"   📚 Total documents in system: {doc_count}")
            return doc_count > 0
        
        return False
    
    def test_enhanced_metadata(self):
        """Test enhanced metadata capabilities"""
        print("\n4. Testing Enhanced Metadata Processing...")
        
        headers = {"Authorization": f"Bearer {self.token}"}
        
        # Query to get document with metadata
        query_data = {
            "question": "service agreement details",
            "num_documents": 1
        }
        
        response = requests.post(
            f"{self.base_url}/query",
            headers=headers,
            json=query_data
        )
        
        if response.status_code == 200:
            result = response.json()
            sources = result.get("sources", [])
            
            if sources:
                metadata = sources[0].get("metadata", {})
                
                # Check for Phase 4 enhanced metadata fields
                enhanced_fields = [
                    "legal_document_type",
                    "legal_terms", 
                    "processing_version",
                    "document_hash",
                    "char_count",
                    "word_count"
                ]
                
                found_fields = [field for field in enhanced_fields if field in metadata]
                enhancement_score = len(found_fields) / len(enhanced_fields)
                
                print(f"   🔍 Enhanced metadata fields found: {len(found_fields)}/{len(enhanced_fields)}")
                print(f"   📋 Document type: {metadata.get('legal_document_type', 'unknown')}")
                print(f"   🏷️  Processing version: {metadata.get('processing_version', 'unknown')}")
                
                return enhancement_score >= 0.7
        
        return False
    
    def run_comprehensive_test(self):
        """Run comprehensive Phase 4 test suite"""
        print("🎯 PHASE 4 COMPREHENSIVE FEATURE DEMONSTRATION")
        print("=" * 70)
        print("Testing enhanced document processing and legal analysis capabilities")
        
        if not self.authenticate():
            print("❌ Authentication failed")
            return
        
        tests = [
            ("Enhanced Document Processing", self.test_enhanced_processor_capabilities),
            ("Legal Document Analysis", self.test_legal_document_analysis),
            ("Document Management", self.test_document_management),
            ("Enhanced Metadata", self.test_enhanced_metadata)
        ]
        
        results = []
        
        for test_name, test_func in tests:
            print(f"\n{'='*20} {test_name} {'='*20}")
            success = test_func()
            results.append((test_name, success))
            time.sleep(1)  # Brief pause between tests
        
        # Final summary
        print("\n" + "="*70)
        print("🏆 PHASE 4 COMPREHENSIVE TEST RESULTS")
        print("="*70)
        
        passed = sum(1 for _, success in results if success)
        total = len(results)
        
        for test_name, success in results:
            status = "✅ PASS" if success else "❌ FAIL"
            print(f"{status} {test_name}")
        
        print(f"\n📊 Overall Results: {passed}/{total} tests passed ({passed/total:.1%})")
        
        if passed == total:
            print("\n🎉 ALL PHASE 4 FEATURES WORKING PERFECTLY!")
            print("✅ Enhanced document processor operational")
            print("✅ Legal document analysis capabilities confirmed")
            print("✅ Metadata enhancement working")
            print("✅ Document management functional")
            print("\n🚀 Phase 4 is ready for production deployment!")
        elif passed >= total * 0.75:
            print("\n🎊 PHASE 4 SUBSTANTIALLY COMPLETE!")
            print(f"✅ {passed}/{total} core features working")
            print("🔧 Minor issues may need attention")
        else:
            print("\n⚠️  PHASE 4 NEEDS ADDITIONAL WORK")
            print("🔧 Several features require fixes")

if __name__ == "__main__":
    tester = Phase4FinalTest()
    tester.run_comprehensive_test() 