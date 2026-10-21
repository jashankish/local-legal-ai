#!/usr/bin/env python3
"""
Phase 2 Test - Verify RAG Pipeline with TF-IDF Embedder
Tests the working RAG system with TF-IDF embeddings.
"""

import sys
import os
import requests
import json
import time
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Server configuration
BASE_URL = "http://localhost:8000"
ADMIN_CREDENTIALS = {"username": "admin", "password": "admin123"}

def get_auth_token():
    """Get authentication token."""
    try:
        response = requests.post(f"{BASE_URL}/auth/login", json=ADMIN_CREDENTIALS)
        if response.status_code == 200:
            return response.json()["access_token"]
        else:
            logger.error(f"Failed to authenticate: {response.status_code}")
            return None
    except Exception as e:
        logger.error(f"Authentication error: {e}")
        return None

def test_document_upload():
    """Test document upload with TF-IDF embedder."""
    logger.info("Testing Document Upload...")
    
    token = get_auth_token()
    if not token:
        return False
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # Create a test legal document
    test_document = """
    EMPLOYMENT AGREEMENT
    
    WHEREAS, Company wishes to employ Employee in the capacity of Software Engineer; and
    WHEREAS, Employee desires to accept such employment;
    
    NOW THEREFORE, the parties agree as follows:
    
    1. EMPLOYMENT TERMS
    Employee shall be employed as a full-time Software Engineer.
    
    2. COMPENSATION
    Company shall pay Employee a salary of $80,000 per year, payable bi-weekly.
    
    3. BENEFITS
    Employee shall be entitled to standard company benefits including:
    - Health insurance coverage
    - 401(k) retirement plan
    - Paid time off (PTO)
    
    4. TERMINATION
    Either party may terminate this agreement with two weeks written notice.
    
    5. CONFIDENTIALITY
    Employee agrees to maintain confidentiality of all proprietary information.
    
    IN WITNESS WHEREOF, the parties have executed this agreement.
    """
    
    try:
        # Upload document
        files = {"file": ("employment_agreement.txt", test_document, "text/plain")}
        data = {
            "title": "Sample Employment Agreement",
            "category": "employment"
        }
        
        response = requests.post(
            f"{BASE_URL}/documents/upload",
            files=files,
            data=data,
            headers=headers
        )
        
        if response.status_code == 200:
            result = response.json()
            logger.info(f"✅ Document uploaded: {result['chunks_processed']} chunks processed")
            logger.info(f"   Processing time: {result['processing_time']:.2f}s")
            return result["document_id"]
        else:
            logger.error(f"❌ Upload failed: {response.status_code} - {response.text}")
            return None
            
    except Exception as e:
        logger.error(f"❌ Upload error: {e}")
        return None

def test_document_query(document_id):
    """Test RAG query functionality."""
    logger.info("Testing RAG Query...")
    
    token = get_auth_token()
    if not token:
        return False
    
    headers = {"Authorization": f"Bearer {token}"}
    
    test_queries = [
        "What is the salary mentioned in the employment agreement?",
        "What benefits are provided to the employee?",
        "How can the employment be terminated?",
        "What are the confidentiality requirements?"
    ]
    
    for query in test_queries:
        try:
            query_data = {
                "question": query,
                "num_documents": 3
            }
            
            response = requests.post(
                f"{BASE_URL}/query",
                json=query_data,
                headers=headers
            )
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"✅ Query: {query}")
                logger.info(f"   Answer: {result['answer'][:100]}...")
                logger.info(f"   Sources: {len(result['sources'])} documents")
                if result.get('confidence_score'):
                    logger.info(f"   Confidence: {result['confidence_score']:.3f}")
            else:
                logger.error(f"❌ Query failed: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Query error: {e}")
            return False
    
    return True

def test_document_stats():
    """Test document statistics."""
    logger.info("Testing Document Statistics...")
    
    token = get_auth_token()
    if not token:
        return False
    
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        response = requests.get(f"{BASE_URL}/documents/stats", headers=headers)
        
        if response.status_code == 200:
            stats = response.json()
            logger.info(f"✅ Document stats: {stats['document_count']} documents")
            logger.info(f"   Collection: {stats['name']}")
            logger.info(f"   Status: {stats['status']}")
            return True
        else:
            logger.error(f"❌ Stats failed: {response.status_code}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Stats error: {e}")
        return False

def test_documents_list():
    """Test document listing."""
    logger.info("Testing Document Listing...")
    
    token = get_auth_token()
    if not token:
        return False
    
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        response = requests.get(f"{BASE_URL}/documents", headers=headers)
        
        if response.status_code == 200:
            docs_info = response.json()
            total_docs = docs_info.get("total_documents", 0)
            logger.info(f"✅ Listed documents info: {total_docs} documents total")
            logger.info(f"   Collection: {docs_info.get('collection_name', 'unknown')}")
            logger.info(f"   Status: {docs_info.get('status', 'unknown')}")
            return True
        else:
            logger.error(f"❌ List failed: {response.status_code}")
            return False
            
    except Exception as e:
        logger.error(f"❌ List error: {e}")
        return False

def test_server_health():
    """Test server health."""
    logger.info("Testing Server Health...")
    
    try:
        response = requests.get(f"{BASE_URL}/health")
        
        if response.status_code == 200:
            health = response.json()
            logger.info(f"✅ Server status: {health['status']}")
            logger.info(f"   API: {health['services']['api']}")
            logger.info(f"   ChromaDB: {health['services']['chromadb']}")
            logger.info(f"   Model: {health['services']['model']}")
            return True
        else:
            logger.error(f"❌ Health check failed: {response.status_code}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Health check error: {e}")
        return False

def main():
    """Run comprehensive Phase 2 tests."""
    logger.info("=" * 60)
    logger.info("LOCAL LEGAL AI - PHASE 2 RAG PIPELINE TEST")
    logger.info("Testing with TF-IDF Embedder Fallback")
    logger.info("=" * 60)
    
    # Wait for server to be ready
    logger.info("Waiting for server to be ready...")
    time.sleep(2)
    
    tests = [
        ("Server Health", test_server_health),
        ("Document Upload", test_document_upload),
        ("Document Statistics", test_document_stats),
        ("Document Listing", test_documents_list),
    ]
    
    results = []
    document_id = None
    
    # Run tests
    for test_name, test_func in tests:
        logger.info(f"\n{test_name} Test:")
        logger.info("-" * 40)
        
        if test_name == "Document Upload":
            result = test_func()
            if result:
                document_id = result
                results.append((test_name, True))
            else:
                results.append((test_name, False))
        else:
            result = test_func()
            results.append((test_name, result))
    
    # Test queries if document was uploaded
    if document_id:
        logger.info(f"\nRAG Query Test:")
        logger.info("-" * 40)
        query_result = test_document_query(document_id)
        results.append(("RAG Query", query_result))
    
    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("PHASE 2 TEST SUMMARY")
    logger.info("=" * 60)
    
    passed = 0
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        logger.info(f"{test_name}: {status}")
        if result:
            passed += 1
    
    logger.info(f"\nOverall: {passed}/{len(results)} tests passed")
    
    if passed == len(results):
        logger.info("\n🎉 Phase 2 RAG Pipeline is FULLY OPERATIONAL!")
        logger.info("\n✅ Achievements:")
        logger.info("   - TF-IDF embedder working as fallback")
        logger.info("   - Document upload and processing")
        logger.info("   - RAG query system functional")
        logger.info("   - ChromaDB integration working")
        logger.info("   - All API endpoints operational")
        
        logger.info("\n🚀 Ready for Phase 3: Frontend Development")
        logger.info("   Next steps:")
        logger.info("   1. Create Streamlit interface")
        logger.info("   2. Build document upload UI")
        logger.info("   3. Implement chat interface")
        logger.info("   4. Add user authentication frontend")
    else:
        logger.info(f"\n⚠️  {len(results) - passed} tests failed.")
        logger.info("   Review errors above before proceeding.")
    
    return passed == len(results)

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 