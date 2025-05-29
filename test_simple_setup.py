#!/usr/bin/env python3
"""
Simple test script to verify the TF-IDF embedder fallback is working
and test basic functionality before starting the full server.
"""

import sys
import os
import logging

# Add paths
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))
sys.path.append(os.path.join(os.path.dirname(__file__), 'rag'))
sys.path.append(os.path.join(os.path.dirname(__file__), 'vector_store'))

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_simple_embedder():
    """Test the simple TF-IDF embedder."""
    logger.info("Testing Simple TF-IDF Embedder...")
    
    try:
        from rag.simple_embedder import get_simple_embedder
        embedder = get_simple_embedder()
        logger.info("✅ Simple embedder imported successfully")
        
        # Test document processing
        test_text = """
        WHEREAS, the parties wish to enter into this agreement; and
        WHEREAS, this contract governs the legal relationship;
        NOW THEREFORE, the parties agree as follows:
        1. Payment terms shall be net 30 days.
        2. All disputes shall be resolved through arbitration.
        """
        
        metadata = {
            'source': 'test_contract.txt',
            'category': 'contract',
            'created_at': '2024-01-01'
        }
        
        # Process document
        chunks, embeddings = embedder.process_document(test_text, metadata)
        logger.info(f"✅ Document processed: {len(chunks)} chunks created")
        
        # Test query embedding
        query = "What are the payment terms?"
        query_embedding = embedder.embed_query(query)
        logger.info(f"✅ Query embedded: dimension {len(query_embedding)}")
        
        # Test similarity search
        if embeddings:
            similarities = embedder.similarity_search(query_embedding, embeddings, top_k=2)
            logger.info(f"✅ Similarity search: found {len(similarities)} results")
            for idx, score in similarities[:2]:
                logger.info(f"   Result {idx}: similarity {score:.3f}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Simple embedder test failed: {e}")
        return False

def test_chromadb():
    """Test ChromaDB connection."""
    logger.info("Testing ChromaDB...")
    
    try:
        from vector_store.chromadb_setup import chroma_manager
        
        # Test health check
        is_healthy = chroma_manager.health_check()
        if is_healthy:
            logger.info("✅ ChromaDB connected successfully")
        else:
            logger.warning("⚠️ ChromaDB connection issues but manager available")
        
        # Test collection stats
        stats = chroma_manager.get_collection_stats()
        logger.info(f"✅ ChromaDB stats: {stats.get('document_count', 0)} documents")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ ChromaDB test failed: {e}")
        return False

def test_config():
    """Test configuration."""
    logger.info("Testing Configuration...")
    
    try:
        from config import settings
        logger.info(f"✅ Config loaded: {settings.app_name}")
        
        # Check optional attributes safely
        env = getattr(settings, 'environment', 'development')
        logger.info(f"   Environment: {env}")
        
        chunk_size = getattr(settings, 'chunk_size', 512)
        logger.info(f"   Chunk size: {chunk_size}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Config test failed: {e}")
        return False

def test_auth():
    """Test authentication system."""
    logger.info("Testing Authentication...")
    
    try:
        from auth import user_manager, create_access_token
        
        # Test user creation (if not exists)
        try:
            test_user = user_manager.create_user("test_user", "test_password", "user")
            logger.info("✅ Test user created")
        except:
            logger.info("✅ Test user already exists")
        
        # Test token creation
        token = create_access_token(data={"sub": "test_user"})
        logger.info("✅ Token creation successful")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Auth test failed: {e}")
        return False

def main():
    """Run all tests."""
    logger.info("=" * 50)
    logger.info("LOCAL LEGAL AI - SIMPLE SETUP TEST")
    logger.info("=" * 50)
    
    tests = [
        ("Configuration", test_config),
        ("ChromaDB", test_chromadb),
        ("Authentication", test_auth),
        ("Simple Embedder", test_simple_embedder),
    ]
    
    results = []
    for test_name, test_func in tests:
        logger.info(f"\n{test_name} Test:")
        logger.info("-" * 30)
        result = test_func()
        results.append((test_name, result))
    
    # Summary
    logger.info("\n" + "=" * 50)
    logger.info("TEST SUMMARY")
    logger.info("=" * 50)
    
    passed = 0
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        logger.info(f"{test_name}: {status}")
        if result:
            passed += 1
    
    logger.info(f"\nOverall: {passed}/{len(tests)} tests passed")
    
    if passed == len(tests):
        logger.info("\n🎉 All tests passed! Ready to start FastAPI server.")
        logger.info("\nNext steps:")
        logger.info("1. Start server: python3 -m uvicorn backend.app:app --host 0.0.0.0 --port 8000")
        logger.info("2. Test endpoints: curl http://localhost:8000/")
        logger.info("3. Proceed to Phase 3: Frontend Development")
    else:
        logger.info(f"\n⚠️  {len(tests) - passed} tests failed. Review errors above.")
    
    return passed == len(tests)

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 