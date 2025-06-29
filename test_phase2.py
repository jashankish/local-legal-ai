#!/usr/bin/env python3
"""
Phase 2 Test Script: RAG Pipeline Development
Tests the embedding system, RAG pipeline, document upload, and query functionality.
"""

import os
import sys
import requests
import json
import time
from datetime import datetime

# Configuration
API_BASE_URL = "http://localhost:8000"
TEST_USERNAME = "admin"
TEST_PASSWORD = "admin123"

# Test document content
SAMPLE_LEGAL_DOCUMENT = """
EMPLOYMENT AGREEMENT

This Employment Agreement ("Agreement") is entered into on January 1, 2024, 
between TechCorp Inc., a Delaware corporation ("Company"), and John Smith ("Employee").

SECTION 1. POSITION AND DUTIES
Employee shall serve as Senior Software Engineer and shall have the duties, 
authority, and responsibilities normally associated with such position.

SECTION 2. COMPENSATION
Company shall pay Employee a base salary of $120,000 per annum, payable in 
accordance with Company's normal payroll practices.

SECTION 3. BENEFITS
Employee shall be entitled to participate in all employee benefit plans 
maintained by Company for its employees, subject to the terms and conditions 
of such plans.

SECTION 4. TERMINATION
This Agreement may be terminated by either party upon thirty (30) days 
written notice to the other party.

SECTION 5. CONFIDENTIALITY
Employee agrees to maintain in confidence all proprietary information 
of Company and shall not disclose such information to any third party.

SECTION 6. GOVERNING LAW
This Agreement shall be governed by and construed in accordance with 
the laws of the State of Delaware.
"""

SAMPLE_CONTRACT_DOCUMENT = """
SOFTWARE LICENSE AGREEMENT

This Software License Agreement ("License") is entered into between 
SoftwareCorp LLC ("Licensor") and Client Corporation ("Licensee").

SECTION 1. GRANT OF LICENSE
Licensor hereby grants to Licensee a non-exclusive, non-transferable license 
to use the Software for internal business purposes only.

SECTION 2. LICENSE FEES
Licensee shall pay Licensor an annual license fee of $50,000, payable in advance.

SECTION 3. RESTRICTIONS
Licensee shall not: (a) modify, adapt, or create derivative works of the Software; 
(b) reverse engineer, decompile, or disassemble the Software; or (c) sublicense, 
distribute, or transfer the Software to any third party.

SECTION 4. SUPPORT AND MAINTENANCE
Licensor shall provide reasonable support and maintenance for the Software 
during the term of this License.

SECTION 5. WARRANTY DISCLAIMER
THE SOFTWARE IS PROVIDED "AS IS" WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED.

SECTION 6. TERM AND TERMINATION
This License shall commence on the effective date and continue for one (1) year, 
unless terminated earlier in accordance with the terms hereof.
"""

def print_test_header(test_name):
    """Print a formatted test header."""
    print(f"\n{'='*60}")
    print(f"Testing: {test_name}")
    print(f"{'='*60}")

def print_test_result(test_name, success, details=""):
    """Print test result with formatting."""
    status = "✅ PASSED" if success else "❌ FAILED"
    print(f"{status}: {test_name}")
    if details:
        print(f"  Details: {details}")

def get_auth_token():
    """Get authentication token."""
    try:
        response = requests.post(
            f"{API_BASE_URL}/auth/login",
            json={"username": TEST_USERNAME, "password": TEST_PASSWORD}
        )
        
        if response.status_code == 200:
            data = response.json()
            return data.get("access_token")
        else:
            print(f"❌ Authentication failed: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print(f"❌ Authentication error: {e}")
        return None

def test_embedder_initialization():
    """Test 1: Embedder Initialization"""
    print_test_header("Embedder Initialization")
    
    try:
        # Import embedder to test initialization
        sys.path.append(os.path.join(os.path.dirname(__file__), 'rag'))
        from embedder import get_embedder
        
        embedder = get_embedder()
        
        # Test basic properties
        success = True
        details = []
        
        if hasattr(embedder, 'model'):
            details.append(f"Model loaded: {embedder.model_name}")
        else:
            success = False
            details.append("Model not loaded")
        
        if hasattr(embedder, 'preprocess_legal_text'):
            details.append("Legal text preprocessing available")
        else:
            success = False
            details.append("Legal text preprocessing not available")
        
        print_test_result("Embedder Initialization", success, "; ".join(details))
        return success
        
    except Exception as e:
        print_test_result("Embedder Initialization", False, str(e))
        return False

def test_document_processing():
    """Test 2: Document Processing"""
    print_test_header("Document Processing")
    
    try:
        sys.path.append(os.path.join(os.path.dirname(__file__), 'rag'))
        from embedder import get_embedder
        
        embedder = get_embedder()
        
        # Test document processing
        result = embedder.process_document(
            text=SAMPLE_LEGAL_DOCUMENT,
            source="test_employment_agreement.txt",
            metadata={"category": "employment", "test": True}
        )
        
        success = True
        details = []
        
        if result.get("document_id"):
            details.append(f"Document ID: {result['document_id']}")
        else:
            success = False
            details.append("No document ID returned")
        
        if result.get("chunks_processed", 0) > 0:
            details.append(f"Chunks processed: {result['chunks_processed']}")
        else:
            success = False
            details.append("No chunks processed")
        
        print_test_result("Document Processing", success, "; ".join(details))
        return success
        
    except Exception as e:
        print_test_result("Document Processing", False, str(e))
        return False

def test_document_upload_api(token):
    """Test 3: Document Upload API"""
    print_test_header("Document Upload API")
    
    try:
        headers = {"Authorization": f"Bearer {token}"}
        
        # Create a test file
        files = {
            "file": ("employment_agreement.txt", SAMPLE_LEGAL_DOCUMENT, "text/plain")
        }
        data = {
            "title": "Test Employment Agreement",
            "category": "employment"
        }
        
        response = requests.post(
            f"{API_BASE_URL}/documents/upload",
            headers=headers,
            files=files,
            data=data
        )
        
        success = response.status_code == 200
        details = []
        
        if success:
            result = response.json()
            details.append(f"Upload successful: {result.get('message', 'No message')}")
            details.append(f"Chunks processed: {result.get('chunks_processed', 0)}")
            details.append(f"Processing time: {result.get('processing_time', 0):.2f}s")
        else:
            details.append(f"HTTP {response.status_code}: {response.text}")
        
        print_test_result("Document Upload API", success, "; ".join(details))
        
        # Upload second document for better testing
        if success:
            files2 = {
                "file": ("software_license.txt", SAMPLE_CONTRACT_DOCUMENT, "text/plain")
            }
            data2 = {
                "title": "Test Software License Agreement", 
                "category": "license"
            }
            
            response2 = requests.post(
                f"{API_BASE_URL}/documents/upload",
                headers=headers,
                files=files2,
                data=data2
            )
            
            if response2.status_code == 200:
                print("  ✅ Second document also uploaded successfully")
            else:
                print(f"  ⚠️ Second document upload failed: {response2.status_code}")
        
        return success
        
    except Exception as e:
        print_test_result("Document Upload API", False, str(e))
        return False

def test_document_stats_api(token):
    """Test 4: Document Statistics API"""
    print_test_header("Document Statistics API")
    
    try:
        headers = {"Authorization": f"Bearer {token}"}
        
        response = requests.get(
            f"{API_BASE_URL}/documents/stats",
            headers=headers
        )
        
        success = response.status_code == 200
        details = []
        
        if success:
            stats = response.json()
            details.append(f"Document count: {stats.get('count', 0)}")
            details.append(f"Collection name: {stats.get('collection_name', 'Unknown')}")
        else:
            details.append(f"HTTP {response.status_code}: {response.text}")
        
        print_test_result("Document Statistics API", success, "; ".join(details))
        return success
        
    except Exception as e:
        print_test_result("Document Statistics API", False, str(e))
        return False

def test_rag_pipeline_initialization():
    """Test 5: RAG Pipeline Initialization"""
    print_test_header("RAG Pipeline Initialization")
    
    try:
        sys.path.append(os.path.join(os.path.dirname(__file__), 'rag'))
        from rag_pipeline import get_rag_pipeline
        
        rag_pipeline = get_rag_pipeline()
        
        success = True
        details = []
        
        if hasattr(rag_pipeline, 'embedder'):
            details.append("Embedder integrated")
        else:
            success = False
            details.append("Embedder not integrated")
        
        if hasattr(rag_pipeline, 'chroma_manager'):
            details.append("ChromaDB manager integrated")
        else:
            success = False
            details.append("ChromaDB manager not integrated")
        
        if hasattr(rag_pipeline, 'query'):
            details.append("Query method available")
        else:
            success = False
            details.append("Query method not available")
        
        print_test_result("RAG Pipeline Initialization", success, "; ".join(details))
        return success
        
    except Exception as e:
        print_test_result("RAG Pipeline Initialization", False, str(e))
        return False

def test_query_api(token):
    """Test 6: Query API"""
    print_test_header("Query API")
    
    try:
        headers = {"Authorization": f"Bearer {token}"}
        
        # Test employment-related query
        query_data = {
            "question": "What is the base salary mentioned in the employment agreement?",
            "num_documents": 3
        }
        
        response = requests.post(
            f"{API_BASE_URL}/query",
            headers=headers,
            json=query_data
        )
        
        success = response.status_code == 200
        details = []
        
        if success:
            result = response.json()
            details.append(f"Query processed successfully")
            details.append(f"Answer length: {len(result.get('answer', ''))}")
            details.append(f"Sources found: {len(result.get('sources', []))}")
            details.append(f"Confidence: {result.get('confidence_score', 0):.2f}")
            details.append(f"Processing time: {result.get('processing_time', 0):.2f}s")
            
            # Show the answer for verification
            answer = result.get('answer', '')
            if len(answer) > 200:
                answer = answer[:200] + "..."
            print(f"  📝 Answer: {answer}")
            
        else:
            details.append(f"HTTP {response.status_code}: {response.text}")
        
        print_test_result("Query API - Employment Question", success, "; ".join(details))
        
        # Test license-related query
        if success:
            query_data2 = {
                "question": "What are the restrictions mentioned in the software license?",
                "num_documents": 3
            }
            
            response2 = requests.post(
                f"{API_BASE_URL}/query",
                headers=headers,
                json=query_data2
            )
            
            if response2.status_code == 200:
                result2 = response2.json()
                print(f"  ✅ License query also processed successfully")
                print(f"    Sources: {len(result2.get('sources', []))}")
                
                # Show the answer for verification
                answer2 = result2.get('answer', '')
                if len(answer2) > 200:
                    answer2 = answer2[:200] + "..."
                print(f"    📝 Answer: {answer2}")
            else:
                print(f"  ⚠️ License query failed: {response2.status_code}")
        
        return success
        
    except Exception as e:
        print_test_result("Query API", False, str(e))
        return False

def test_retrieval_accuracy(token):
    """Test 7: Retrieval Accuracy"""
    print_test_header("Retrieval Accuracy")
    
    try:
        headers = {"Authorization": f"Bearer {token}"}
        
        # Test specific queries and check if relevant sources are retrieved
        test_cases = [
            {
                "question": "What is the annual license fee?",
                "expected_keywords": ["50,000", "annual", "license fee", "advance"],
                "category": "license"
            },
            {
                "question": "What are the termination conditions?",
                "expected_keywords": ["thirty", "30", "days", "written notice"],
                "category": "employment"
            },
            {
                "question": "What confidentiality obligations exist?",
                "expected_keywords": ["confidentiality", "proprietary", "third party"],
                "category": "employment"
            }
        ]
        
        total_tests = len(test_cases)
        passed_tests = 0
        
        for i, test_case in enumerate(test_cases, 1):
            query_data = {
                "question": test_case["question"],
                "num_documents": 5
            }
            
            response = requests.post(
                f"{API_BASE_URL}/query",
                headers=headers,
                json=query_data
            )
            
            if response.status_code == 200:
                result = response.json()
                sources = result.get('sources', [])
                
                # Check if relevant keywords are found in sources
                all_source_text = " ".join([src.get('content', '') for src in sources]).lower()
                
                keywords_found = []
                for keyword in test_case["expected_keywords"]:
                    if keyword.lower() in all_source_text:
                        keywords_found.append(keyword)
                
                accuracy = len(keywords_found) / len(test_case["expected_keywords"])
                
                if accuracy >= 0.5:  # At least 50% of keywords found
                    passed_tests += 1
                    print(f"  ✅ Test {i}: {test_case['question'][:50]}... (Accuracy: {accuracy:.1%})")
                else:
                    print(f"  ❌ Test {i}: {test_case['question'][:50]}... (Accuracy: {accuracy:.1%})")
                
                print(f"    Keywords found: {keywords_found}")
            else:
                print(f"  ❌ Test {i}: API request failed ({response.status_code})")
        
        overall_success = passed_tests >= (total_tests * 0.6)  # 60% pass rate
        details = f"{passed_tests}/{total_tests} tests passed ({passed_tests/total_tests:.1%})"
        
        print_test_result("Retrieval Accuracy", overall_success, details)
        return overall_success
        
    except Exception as e:
        print_test_result("Retrieval Accuracy", False, str(e))
        return False

def main():
    """Main test execution."""
    print("🚀 Starting Phase 2: RAG Pipeline Development Tests")
    print(f"📅 Test Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Track test results
    tests_passed = 0
    total_tests = 7
    
    # Test 1: Embedder Initialization
    if test_embedder_initialization():
        tests_passed += 1
    
    # Test 2: Document Processing
    if test_document_processing():
        tests_passed += 1
    
    # Get authentication token
    token = get_auth_token()
    if not token:
        print("\n❌ Cannot proceed with API tests - authentication failed")
        return
    
    print("\n✅ Authentication successful - proceeding with API tests")
    
    # Test 3: Document Upload API
    if test_document_upload_api(token):
        tests_passed += 1
    
    # Test 4: Document Statistics API
    if test_document_stats_api(token):
        tests_passed += 1
    
    # Test 5: RAG Pipeline Initialization
    if test_rag_pipeline_initialization():
        tests_passed += 1
    
    # Test 6: Query API
    if test_query_api(token):
        tests_passed += 1
    
    # Test 7: Retrieval Accuracy
    if test_retrieval_accuracy(token):
        tests_passed += 1
    
    # Final summary
    print(f"\n{'='*60}")
    print(f"PHASE 2 TEST SUMMARY")
    print(f"{'='*60}")
    print(f"Tests Passed: {tests_passed}/{total_tests}")
    print(f"Success Rate: {tests_passed/total_tests:.1%}")
    
    if tests_passed == total_tests:
        print("🎉 All Phase 2 tests PASSED! RAG Pipeline is fully functional.")
        print("\nNext Steps:")
        print("1. 🌐 Start Phase 3: Frontend Development")
        print("2. 📊 Set up Streamlit interface")
        print("3. 🔗 Integrate frontend with RAG API")
        print("4. 🧪 Conduct end-to-end testing")
    elif tests_passed >= total_tests * 0.8:
        print("⚠️ Most Phase 2 tests passed - minor issues to address")
        print("\nNext Steps:")
        print("1. 🔧 Fix remaining issues")
        print("2. 🔄 Re-run failed tests")
        print("3. 🌐 Proceed to Phase 3 when ready")
    else:
        print("❌ Significant issues found - requires attention")
        print("\nNext Steps:")
        print("1. 🔧 Review and fix failed tests")
        print("2. 📋 Check logs for detailed error information")
        print("3. 🔄 Re-run Phase 2 tests")
    
    print(f"\n📊 Phase 2 Development Status: {'COMPLETE' if tests_passed == total_tests else 'IN PROGRESS'}")

if __name__ == "__main__":
    main() 