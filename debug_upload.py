#!/usr/bin/env python3
"""
Debug script to trace the upload process and identify the chunk processing issue
"""

import sys
import os
sys.path.append('.')

from rag.enhanced_document_processor import EnhancedDocumentProcessor
from rag.simple_embedder import get_simple_embedder
from vector_store.chromadb_setup import chroma_manager

def debug_upload_process():
    print("=== DEBUGGING UPLOAD PROCESS ===")
    
    # Step 1: Test Enhanced Processor
    print("\n1. Testing Enhanced Document Processor...")
    processor = EnhancedDocumentProcessor()
    
    with open('test_contract.txt', 'rb') as f:
        content = f.read()
    
    print(f"   File size: {len(content)} bytes")
    
    document_metadata = {
        "source": "test_contract.txt",
        "category": "employment",
        "uploaded_by": "admin",
        "content_type": "text/plain",
        "file_size": len(content)
    }
    
    try:
        processed_result = processor.process_document(
            file_content=content,
            filename="test_contract.txt",
            content_type="text/plain",
            metadata=document_metadata
        )
        
        print(f"   ✅ Enhanced processor successful")
        print(f"   Text length: {len(processed_result['text'])}")
        print(f"   Sections: {len(processed_result.get('sections', []))}")
        print(f"   Document type: {processed_result.get('legal_document_type', 'unknown')}")
        
        text_content = processed_result['text']
        enhanced_metadata = {**document_metadata, **processed_result}
        enhanced_metadata.pop('text', None)
        
    except Exception as e:
        print(f"   ❌ Enhanced processor failed: {e}")
        return
    
    # Step 2: Test Embedder
    print("\n2. Testing Simple Embedder...")
    try:
        embedder = get_simple_embedder()
        print(f"   ✅ Embedder initialized")
        
        chunks, embeddings = embedder.process_document(
            text=text_content,
            metadata=enhanced_metadata
        )
        
        print(f"   Chunks generated: {len(chunks)}")
        print(f"   Embeddings type: {type(embeddings)}")
        
        if chunks:
            print(f"   First chunk preview: {chunks[0]['text'][:100]}...")
            print(f"   First chunk metadata keys: {list(chunks[0]['metadata'].keys())}")
        
    except Exception as e:
        print(f"   ❌ Embedder failed: {e}")
        return
    
    # Step 3: Test ChromaDB Storage
    print("\n3. Testing ChromaDB Storage...")
    if chunks:
        try:
            texts = [chunk['text'] for chunk in chunks]
            metadatas = [chunk['metadata'] for chunk in chunks]
            ids = [chunk['id'] for chunk in chunks]
            
            print(f"   Texts count: {len(texts)}")
            print(f"   Metadatas count: {len(metadatas)}")
            print(f"   IDs count: {len(ids)}")
            
            success = chroma_manager.add_documents(
                texts=texts,
                metadatas=metadatas,
                ids=ids
            )
            
            if success:
                print(f"   ✅ ChromaDB storage successful")
                print(f"   Document ID: {ids[0] if ids else 'None'}")
            else:
                print(f"   ❌ ChromaDB storage failed")
            
        except Exception as e:
            print(f"   ❌ ChromaDB storage error: {e}")
    else:
        print(f"   ❌ No chunks to store!")
    
    # Step 4: Test Retrieval
    print("\n4. Testing Document Retrieval...")
    try:
        stats = chroma_manager.get_collection_stats()
        print(f"   Collection stats: {stats}")
        
        search_results = chroma_manager.search_documents(
            query="employment agreement",
            n_results=3
        )
        
        if search_results and 'documents' in search_results:
            docs = search_results['documents']
            if docs and isinstance(docs[0], list):
                docs = docs[0]
            print(f"   Search results: {len(docs)} documents found")
        else:
            print(f"   No search results found")
            
    except Exception as e:
        print(f"   ❌ Retrieval error: {e}")
    
    print("\n=== DEBUG COMPLETE ===")

if __name__ == "__main__":
    debug_upload_process() 