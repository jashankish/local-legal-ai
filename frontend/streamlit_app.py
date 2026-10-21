#!/usr/bin/env python3
"""
Local Legal AI - Streamlit Frontend
Phase 3: Frontend Development

A comprehensive web interface for the Local Legal AI system featuring:
- User authentication
- Document upload and management
- RAG-powered chat interface
- Admin panel
"""

import html
import streamlit as st
import requests
import json
import time
from datetime import datetime, timedelta
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from typing import Optional, Dict, Any, List
import os

# Configure Streamlit page
st.set_page_config(
    page_title="Local Legal AI",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Global configuration
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
API_BASE_URL = BACKEND_URL
AUTH_TOKEN = st.session_state.get("access_token", "")

# Custom CSS for better styling
st.markdown("""
<style>
    .main-header {
        background: linear-gradient(90deg, #1e3a8a 0%, #3b82f6 100%);
        padding: 1rem;
        border-radius: 10px;
        color: white;
        text-align: center;
        margin-bottom: 2rem;
    }
    .chat-message {
        padding: 1rem;
        border-radius: 10px;
        margin: 0.5rem 0;
        border-left: 4px solid #3b82f6;
        background-color: #f8fafc;
    }
    .user-message {
        background-color: #dbeafe;
        border-left-color: #1e40af;
    }
    .assistant-message {
        background-color: #f0fdf4;
        border-left-color: #16a34a;
    }
    .document-card {
        border: 1px solid #e5e7eb;
        border-radius: 8px;
        padding: 1rem;
        margin: 0.5rem 0;
        background-color: #fefefe;
    }
    .metric-card {
        background: white;
        padding: 1rem;
        border-radius: 8px;
        border: 1px solid #e5e7eb;
        text-align: center;
    }
    .sidebar .block-container {
        padding-top: 1rem;
    }
    .feature-grid {
        display: grid;
        grid-template-columns: repeat(3, 1fr);
        gap: 0.75rem;
        margin-top: 1.5rem;
        font-size: 0.9rem;
    }
    .feature-grid > div {
        border: 1px solid rgba(128, 128, 128, 0.25);
        border-radius: 8px;
        padding: 0.75rem;
    }
    .feature-grid span {
        opacity: 0.75;
    }
</style>
""", unsafe_allow_html=True)

# Session state initialization
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'user_info' not in st.session_state:
    st.session_state.user_info = None
if 'access_token' not in st.session_state:
    st.session_state.access_token = None
if 'chat_history' not in st.session_state:
    st.session_state.chat_history = []
if 'documents' not in st.session_state:
    st.session_state.documents = []

class APIClient:
    """API client for communicating with FastAPI backend."""
    
    def __init__(self, base_url: str):
        self.base_url = base_url
    
    def _get_headers(self) -> Dict[str, str]:
        """Get headers with authentication token."""
        headers = {"Content-Type": "application/json"}
        if st.session_state.access_token:
            headers["Authorization"] = f"Bearer {st.session_state.access_token}"
        return headers
    
    def login(self, username: str, password: str) -> Optional[Dict]:
        """Authenticate user and get access token."""
        try:
            response = requests.post(
                f"{self.base_url}/auth/login",
                json={"username": username, "password": password}
            )
            if response.status_code == 200:
                return response.json()
            self.last_error = (response.json().get("detail") if response.headers.get(
                "content-type", "").startswith("application/json") else None) or "Sign-in failed"
            return None
        except Exception as e:
            self.last_error = f"Cannot reach the API at {self.base_url} ({type(e).__name__})"
            return None
    
    def check_health(self) -> Optional[Dict]:
        """Check API health status."""
        try:
            response = requests.get(f"{self.base_url}/health")
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            st.error(f"Health check error: {e}")
            return None
    
    def upload_document(self, file_content: bytes, filename: str, title: str, category: str) -> Optional[Dict]:
        """Upload a document to the system."""
        try:
            files = {"file": (filename, file_content, "text/plain")}
            data = {"title": title, "category": category}
            headers = {"Authorization": f"Bearer {st.session_state.access_token}"}
            
            response = requests.post(
                f"{self.base_url}/documents/upload",
                files=files,
                data=data,
                headers=headers
            )
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            st.error(f"Upload error: {e}")
            return None
    
    def query_documents(self, question: str, num_documents: int = 5) -> Optional[Dict]:
        """Query documents using RAG pipeline."""
        try:
            headers = self._get_headers()
            data = {"question": question, "num_documents": num_documents}
            
            response = requests.post(
                f"{self.base_url}/query",
                json=data,
                headers=headers
            )
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            st.error(f"Query error: {e}")
            return None
    
    def get_document_stats(self) -> Optional[Dict]:
        """Get document statistics."""
        try:
            headers = self._get_headers()
            response = requests.get(f"{self.base_url}/documents/stats", headers=headers)
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            st.error(f"Stats error: {e}")
            return None
    
    def list_documents(self) -> Optional[Dict]:
        """List all documents."""
        try:
            headers = self._get_headers()
            response = requests.get(f"{self.base_url}/documents", headers=headers)
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            st.error(f"List documents error: {e}")
            return None

# Initialize API client
api_client = APIClient(API_BASE_URL)

def show_login_page():
    """Display login page."""
    st.markdown('<div class="main-header"><h1>⚖️ Local Legal AI</h1>'
                '<p>Private, on-premise document intelligence for legal teams</p></div>',
                unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 1.4, 1])

    with col2:
        if st.session_state.get("session_notice"):
            st.warning(st.session_state.session_notice)
        with st.form("login_form"):
            st.markdown("#### 🔐 Sign in")
            username = st.text_input("Username", placeholder="e.g. admin")
            password = st.text_input("Password", type="password")
            submit_button = st.form_submit_button("Sign in", type="primary", width="stretch")
            
            if submit_button:
                if username and password:
                    with st.spinner("Authenticating..."):
                        result = api_client.login(username, password)
                        
                    if result:
                        st.session_state.authenticated = True
                        st.session_state.access_token = result["access_token"]
                        st.session_state.user_info = result["user"]
                        st.session_state.pop("session_notice", None)
                        st.rerun()
                    else:
                        st.error(f"❌ {getattr(api_client, 'last_error', 'Sign-in failed')}")
                else:
                    st.error("Please enter both username and password")
        
        st.caption("First run? Sign in with the default administrator account "
                   "`admin` / `admin123`, then change its password.")

    _, features_col, _ = st.columns([1, 3, 1])
    with features_col:
        st.markdown("""
        <div class="feature-grid">
          <div>🔒 <b>Stays on this machine</b><br><span>Documents, vectors and the model never leave your network.</span></div>
          <div>🧾 <b>Cited answers</b><br><span>Every answer points to the exact passages it came from.</span></div>
          <div>🛡️ <b>Audit trail</b><br><span>Tamper-evident log of every sign-in, upload and question.</span></div>
        </div>
        """, unsafe_allow_html=True)

def show_main_interface():
    """Display main application interface."""
    # Header
    st.markdown('<div class="main-header"><h1>⚖️ Local Legal AI</h1><p>AI-Powered Legal Document Analysis System</p></div>', 
                unsafe_allow_html=True)
    
    # Sidebar
    with st.sidebar:
        st.markdown(f"### Welcome, {st.session_state.user_info['username']}!")
        st.markdown(f"**Role:** {st.session_state.user_info['role']}")
        
        if st.button("🚪 Logout", type="secondary"):
            st.session_state.authenticated = False
            st.session_state.access_token = None
            st.session_state.user_info = None
            st.session_state.chat_history = []
            st.rerun()
        
        st.markdown("---")
        
        # Navigation
        page = st.selectbox(
            "Navigate to:",
            ["🏠 Dashboard", "📄 Document Upload", "💬 Chat Interface", "📊 Document Management"],
            key="page_selector"
        )
    
    # Main content based on selected page
    if page == "🏠 Dashboard":
        show_dashboard()
    elif page == "📄 Document Upload":
        show_document_upload()
    elif page == "💬 Chat Interface":
        show_chat_interface()
    elif page == "📊 Document Management":
        show_document_management()

ACRONYMS = {"nda": "NDA", "msa": "MSA", "sow": "SOW", "llc": "LLC"}
ACTIVITY_LABELS = {
    "query.ask": "Questions asked", "auth.login": "Sign-ins", "document.upload": "Uploads",
    "document.delete": "Deletions", "user.create": "Users created", "analytics.export": "Report exports",
    "audit.verify": "Audit checks", "audit.export": "Audit exports",
}


def pretty_label(value: Any) -> str:
    """Turn stored keys like 'real_estate' or 'nda' into display labels."""
    words = str(value or "").replace("_", " ").split()
    return " ".join(ACRONYMS.get(w.lower(), w.capitalize()) for w in words)


def show_dashboard():
    """Display the main dashboard with quick actions and system info."""
    st.markdown("## 🏠 Dashboard")
    username = st.session_state.get("user_info", {}).get("username", "")
    st.markdown(f"Welcome back{', **' + username + '**' if username else ''}. "
                "Here's the state of your private document library.")

    headers = {"Authorization": f"Bearer {st.session_state.get('access_token', '')}"}
    try:
        library = requests.get(f"{BACKEND_URL}/documents", headers=headers, timeout=10).json()
    except Exception:
        library = {"documents": [], "total": 0, "total_chunks": 0}
    try:
        health = requests.get(f"{BACKEND_URL}/health", timeout=5).json().get("services", {})
    except Exception:
        health = {}

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("📚 Documents", library.get("total", 0))
    col2.metric("🧩 Indexed passages", library.get("total_chunks", 0))
    model_state = health.get("model", "unknown")
    col3.metric("🤖 Answer engine", "Local LLM" if model_state == "healthy" else "Extractive",
                help="Generated answers need a local model server; otherwise answers are cited excerpts.")
    col4.metric("🗄️ Vector store", "Online" if health.get("chromadb") == "healthy" else "Offline")

    documents = library.get("documents", [])
    if documents:
        st.markdown("### 🗂️ Recently added")
        st.dataframe(pd.DataFrame([{
            "Document": d.get("filename"),
            "Category": pretty_label(d.get("category")),
            "Type": pretty_label(d.get("document_type")),
            "Passages": d.get("chunk_count"),
            "Uploaded by": d.get("uploaded_by"),
            "Uploaded": str(d.get("upload_date", ""))[:10],
        } for d in documents[:6]]), width="stretch", hide_index=True)

    # Quick actions
    st.markdown("### ⚡ Quick Actions")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("##### 📄 Documents")
        
        # Use different session state variables for button navigation
        if st.button("📄 Upload New Document", type="primary", key="nav_upload"):
            st.session_state.navigate_to = "📄 Upload Documents"
            st.rerun()
        
        if st.button("💬 Start Chat Session", key="nav_chat"):
            st.session_state.navigate_to = "💬 Enhanced Chat"
            st.rerun()
    
    with col2:
        st.markdown("##### 📈 Your recent questions")
        if len(st.session_state.chat_history) > 0:
            st.write("Recent queries:")
            for i, msg in enumerate(st.session_state.chat_history[-3:]):
                if msg.get('role') == 'user':
                    st.write(f"• {msg['content'][:50]}...")
        else:
            st.caption("No questions yet this session.")
    
    # System information
    st.markdown("---")
    st.markdown("### ℹ️ How it works")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("""
        **Under the hood**
        - PDF, DOCX and TXT parsing with legal document-type detection
        - Clause-aware chunking, MiniLM embeddings in an embedded ChromaDB
        - Answers from a local OpenAI-compatible model (vLLM / Ollama)
        - JWT sign-in, hash-chained audit log, IP allow-listing
        """)

    with col2:
        st.markdown("""
        **Try asking**
        - *What notice period is required to terminate the agreement?*
        - *What is the monthly retainer and when is it invoiced?*
        - *How long do confidentiality obligations last?*
        - *Which state's law governs the lease?*
        """)

def show_document_upload():
    """Display document upload interface."""
    st.markdown("## 📄 Document Upload")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        uploaded_file = st.file_uploader(
            "Choose a legal document",
            type=['txt', 'pdf', 'doc', 'docx'],
            help="Upload legal documents for AI analysis. Currently optimized for text files."
        )
        
        if uploaded_file is not None:
            # File details
            st.markdown("### 📋 Document Details")
            
            title = st.text_input("Document Title", value=uploaded_file.name)
            category = st.selectbox(
                "Category",
                ["employment", "contract", "litigation", "corporate", "general"],
                index=4
            )
            
            # Preview file content (for text files)
            if uploaded_file.type == "text/plain":
                content = str(uploaded_file.read(), "utf-8")
                st.markdown("### 👀 Document Preview")
                st.text_area("Content Preview", content[:500] + "..." if len(content) > 500 else content, height=150)
                uploaded_file.seek(0)  # Reset file pointer
            
            # Upload button
            if st.button("🚀 Upload and Process", type="primary"):
                with st.spinner("Processing document..."):
                    file_content = uploaded_file.read()
                    result = api_client.upload_document(
                        file_content=file_content,
                        filename=uploaded_file.name,
                        title=title,
                        category=category
                    )
                
                if result and result.get('success'):
                    st.success(f"✅ Document uploaded successfully!")
                    st.json({
                        "Document ID": result.get('document_id'),
                        "Chunks Processed": result.get('chunks_processed'),
                        "Processing Time": f"{result.get('processing_time', 0):.2f}s"
                    })
                else:
                    st.error("❌ Upload failed. Please try again.")
    
    with col2:
        st.markdown("### ℹ️ Upload Guidelines")
        st.markdown("""
        **Supported formats**
        - ✅ PDF (text-based; scanned images need OCR first)
        - ✅ Word (.docx)
        - ✅ Plain text (.txt)

        **Best practices**
        - Use a descriptive title — it is shown in every citation
        - Pick a category so the library stays organised
        - Upload final, executed versions where possible

        **What happens on upload**
        - Text is extracted and the document type is detected
        - The document is split clause by clause ("Section 1", "Section 2", …)
        - Each passage is embedded locally and indexed in ChromaDB
        - The upload is recorded in the audit log

        **Bulk import**
        - Drop files into `data/inbox/` (or `data/inbox/<category>/`) on the server — they are indexed automatically
        """)

def show_chat_interface():
    """Display chat interface for querying documents."""
    st.markdown("## 💬 Legal AI Chat Interface")
    
    # Chat history display
    st.markdown("### 📜 Conversation History")
    
    chat_container = st.container()
    with chat_container:
        if len(st.session_state.chat_history) == 0:
            st.markdown("""
            <div class="chat-message assistant-message">
                <strong>🤖 Legal AI Assistant:</strong><br>
                Hello! I'm here to help you analyze legal documents. Ask me questions about uploaded documents, 
                and I'll provide detailed answers based on the content.
            </div>
            """, unsafe_allow_html=True)
        
        for message in st.session_state.chat_history:
            if message['role'] == 'user':
                st.markdown(f"""
                <div class="chat-message user-message">
                    <strong>👤 You:</strong><br>
                    {html.escape(message['content'])}
                </div>
                """, unsafe_allow_html=True)
            else:
                with st.chat_message("assistant", avatar="⚖️"):
                    st.markdown(message['content'])
                    if message.get('mode'):
                        st.caption(answer_mode_caption(message))
                
                # Show sources if available
                if 'sources' in message and message['sources']:
                    with st.expander(f"📚 Sources ({len(message['sources'])} passages)"):
                        for i, source in enumerate(message['sources']):
                            metadata = source.get('metadata') or {}
                            st.markdown(
                                f"**[{i+1}] {metadata.get('source', 'Unknown document')}** "
                                f"· relevance {source.get('similarity_score', 0):.2f}"
                            )
                            st.caption(source.get('content', '')[:400] + "…")
    
    # Chat input
    st.markdown("---")
    
    # Suggested questions
    st.markdown("### 💡 Suggested Questions")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("💰 Ask about compensation"):
            query = "What compensation or salary information is mentioned in the documents?"
            st.session_state.pending_query = query
    
    with col2:
        if st.button("📋 Ask about terms"):
            query = "What are the key terms and conditions mentioned?"
            st.session_state.pending_query = query
    
    with col3:
        if st.button("⚠️ Ask about termination"):
            query = "How can the agreement be terminated?"
            st.session_state.pending_query = query
    
    # Text input for custom questions
    user_input = st.text_input(
        "Ask a question about your legal documents:",
        value=getattr(st.session_state, 'pending_query', ''),
        placeholder="e.g., What are the confidentiality requirements in the employment agreement?",
        key="chat_input"
    )
    
    if hasattr(st.session_state, 'pending_query'):
        del st.session_state.pending_query
    
    col1, col2 = st.columns([1, 4])
    with col1:
        send_button = st.button("🚀 Send", type="primary")
    
    if send_button and user_input:
        # Add user message to history
        st.session_state.chat_history.append({
            'role': 'user',
            'content': user_input,
            'timestamp': datetime.now()
        })
        
        # Query the API
        with st.spinner("🤖 Analyzing documents..."):
            result = api_client.query_documents(user_input)
        
        if result:
            # Add assistant response to history
            assistant_message = {
                'role': 'assistant',
                'content': result.get('answer', 'Sorry, I could not process your question.'),
                'sources': result.get('sources', []),
                'confidence': result.get('confidence_score', 0),
                'mode': result.get('mode'),
                'model': result.get('model'),
                'timestamp': datetime.now()
            }
            st.session_state.chat_history.append(assistant_message)
        else:
            st.session_state.chat_history.append({
                'role': 'assistant',
                'content': 'Sorry, I encountered an error while processing your question. Please try again.',
                'timestamp': datetime.now()
            })
        
        # Clear input and refresh
        st.rerun()

def show_document_management():
    """Display document management interface."""
    st.markdown("## 📊 Document Management")
    
    # Document statistics
    stats = api_client.get_document_stats()
    doc_list = api_client.list_documents()
    
    if stats:
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("📚 Total Documents", stats.get('document_count', 0))
        
        with col2:
            st.metric("🗄️ Collection", stats.get('name', 'Unknown'))
        
        with col3:
            st.metric("✅ Status", stats.get('status', 'Unknown'))
    
    if doc_list:
        st.markdown(f"### 📋 Document Overview")
        total_docs = doc_list.get('total_documents', 0)
        collection_name = doc_list.get('collection_name', 'unknown')
        status = doc_list.get('status', 'unknown')
        
        st.markdown(f"""
        **Collection Information:**
        - **Total Documents:** {total_docs}
        - **Collection Name:** {collection_name}
        - **Status:** {status}
        """)
    
    # Recent uploads (simulated)
    st.markdown("### 📈 System Activity")
    
    if len(st.session_state.chat_history) > 0:
        st.markdown("**Recent Queries:**")
        recent_queries = [msg for msg in st.session_state.chat_history if msg.get('role') == 'user']
        
        for query in recent_queries:
            st.markdown(f"• {query['content'][:80]}...")
    else:
        st.markdown("No recent activity to display.")
    
    # Clear data option (admin only)
    if st.session_state.user_info.get('role') == 'admin':
        st.markdown("---")
        st.markdown("### ⚠️ Admin Actions")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🗑️ Clear Chat History", type="secondary"):
                st.session_state.chat_history = []
                st.success("Chat history cleared!")
        
        with col2:
            if st.button("🔄 Refresh Stats", type="secondary"):
                st.rerun()

def show_files_management():
    """Display Google Drive-style file management interface."""
    st.header("📁 Files Management")
    
    if 'access_token' not in st.session_state:
        st.error("Please login first")
        return
    
    # Top action bar with upload and search
    col1, col2, col3 = st.columns([2, 3, 1])
    
    with col1:
        st.subheader("📂 Document Library")
    
    with col2:
        search_query = st.text_input("🔍 Search files...", placeholder="Search by filename, content, or category")
    
    with col3:
        if st.button("🔄 Refresh", width="stretch"):
            st.rerun()
    
    # Upload section
    with st.expander("📤 Upload New Document", expanded=False):
        uploaded_file = st.file_uploader(
            "Choose a file", 
            type=['txt', 'pdf', 'docx'],
            help="Supported formats: PDF, DOCX, TXT"
        )
        
        col1, col2 = st.columns(2)
        with col1:
            upload_title = st.text_input("Document Title (optional)")
        with col2:
            upload_category = st.selectbox(
                "Category", 
                ["general", "contract", "employment", "legal", "policy", "agreement"]
            )
        
        if uploaded_file and st.button("📤 Upload Document", type="primary"):
            try:
                with st.spinner("Uploading and processing document..."):
                    # Prepare the upload
                    files = {"file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)}
                    data = {
                        "title": upload_title or uploaded_file.name,
                        "category": upload_category
                    }
                    headers = {"Authorization": f"Bearer {st.session_state.access_token}"}
                    
                    # Upload the file
                    response = requests.post(
                        f"{api_client.base_url}/documents/upload",
                        files=files,
                        data=data,
                        headers=headers
                    )
                    
                    if response.status_code == 200:
                        result = response.json()
                        if result.get('success'):
                            st.success(f"✅ Document uploaded successfully!")
                            st.info(f"Document ID: {result.get('document_id')}")
                            st.info(f"Chunks processed: {result.get('chunks_processed')}")
                            st.info(f"Processing time: {result.get('processing_time'):.2f}s")
                            st.rerun()
                        else:
                            st.error(f"Upload failed: {result.get('message')}")
                    else:
                        st.error(f"Upload failed: {response.status_code}")
            except Exception as e:
                st.error(f"Upload error: {e}")
    
    # Get document stats
    try:
        stats_response = api_client.get_document_stats()
        if stats_response:
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("📄 Documents", stats_response.get('document_count', 0))
            with col2:
                st.metric("🧩 Indexed passages", stats_response.get('chunk_count', 0))
            with col3:
                st.metric("💾 Vector store", "ChromaDB")
            with col4:
                st.metric("⚡ Status", stats_response.get('status', 'Unknown').title())
    except Exception as e:
        st.warning(f"Could not load stats: {e}")
    
    st.markdown("---")
    
    # File listing section
    try:
        docs_response = api_client.list_documents()
        if docs_response and docs_response.get('documents'):
            documents = docs_response['documents']
            
            # Filter documents based on search
            if search_query:
                filtered_docs = []
                for doc in documents:
                    filename = doc.get('filename', '').lower()
                    category = doc.get('category', '').lower()
                    source = doc.get('source', '').lower()
                    
                    if (search_query.lower() in filename or 
                        search_query.lower() in category or 
                        search_query.lower() in source):
                        filtered_docs.append(doc)
                documents = filtered_docs
            
            if documents:
                # Sort documents by upload date (newest first)
                documents.sort(key=lambda x: x.get('upload_date', ''), reverse=True)
                
                # Group by category
                categories = {}
                for doc in documents:
                    category = doc.get('category', 'general')
                    if category not in categories:
                        categories[category] = []
                    categories[category].append(doc)
                
                # Display documents by category
                for category, category_docs in categories.items():
                    file_word = "file" if len(category_docs) == 1 else "files"
                    with st.expander(f"📁 {pretty_label(category)} ({len(category_docs)} {file_word})", expanded=True):
                        
                        # Create grid layout for files
                        cols_per_row = 3
                        for i in range(0, len(category_docs), cols_per_row):
                            cols = st.columns(cols_per_row)
                            
                            for j, col in enumerate(cols):
                                if i + j < len(category_docs):
                                    doc = category_docs[i + j]
                                    
                                    with col:
                                        # File icon based on type
                                        filename = doc.get('filename', 'Unknown')
                                        if filename.lower().endswith('.pdf'):
                                            icon = "📄"
                                        elif filename.lower().endswith('.docx'):
                                            icon = "📝"
                                        elif filename.lower().endswith('.txt'):
                                            icon = "📃"
                                        else:
                                            icon = "📄"
                                        
                                        # File card
                                        with st.container():
                                            st.markdown(f"""
                                            <div style="border: 1px solid #ddd; border-radius: 8px; padding: 12px; margin: 8px 0; background: #f9f9f9;">
                                                <div style="font-size: 24px; text-align: center; margin-bottom: 8px;">{icon}</div>
                                                <div style="font-weight: bold; font-size: 14px; margin-bottom: 4px; word-wrap: break-word;" title="{html.escape(filename)}">{html.escape(filename if len(filename) <= 34 else filename[:32] + "…")}</div>
                                                <div style="font-size: 12px; color: #666; margin-bottom: 8px;">
                                                    {doc.get('upload_date', 'Unknown')[:10]}<br>
                                                    ID: {doc.get('id', 'Unknown')[:8]}...
                                                </div>
                                            </div>
                                            """, unsafe_allow_html=True)
                                            
                                            # Action buttons
                                            col_btn1, col_btn2 = st.columns(2)
                                            with col_btn1:
                                                if st.button("ℹ️", key=f"info_{doc.get('id')}", help="View Info"):
                                                    st.info(f"""
                                                    **File:** {doc.get('filename', 'Unknown')}
                                                    **Category:** {doc.get('category', 'Unknown')}
                                                    **Uploaded:** {doc.get('upload_date', 'Unknown')}
                                                    **Source:** {doc.get('source', 'Unknown')}
                                                    **ID:** {doc.get('id', 'Unknown')}
                                                    """)
                                            
                                            with col_btn2:
                                                if st.button("🗑️", key=f"delete_{doc.get('id')}", help="Delete File"):
                                                    if st.session_state.get(f"confirm_delete_{doc.get('id')}", False):
                                                        try:
                                                            headers = {"Authorization": f"Bearer {st.session_state.access_token}"}
                                                            response = requests.delete(
                                                                f"{api_client.base_url}/documents/{doc.get('id')}",
                                                                headers=headers
                                                            )
                                                            if response.status_code == 200:
                                                                st.success("File deleted!")
                                                                st.rerun()
                                                            else:
                                                                st.error("Delete failed")
                                                        except Exception as e:
                                                            st.error(f"Error: {e}")
                                                    else:
                                                        st.session_state[f"confirm_delete_{doc.get('id')}"] = True
                                                        st.warning("Click again to confirm deletion")
                
            else:
                if search_query:
                    st.info(f"No files found matching '{search_query}'")
                else:
                    st.info("No documents found. Upload some documents to get started!")
        
        else:
            st.info("No documents found. Upload some documents to get started!")
    
    except Exception as e:
        st.error(f"Failed to load documents: {e}")
    
    # Bulk operations section
    st.markdown("---")
    with st.expander("🔧 Advanced Operations", expanded=False):
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("🗑️ Bulk Delete")
            if st.button("Clear All Documents", type="secondary"):
                st.warning("⚠️ This will delete ALL documents!")
                
        with col2:
            st.subheader("📊 Export Data")
            if st.button("📥 Export Document List", type="secondary"):
                try:
                    docs_response = api_client.list_documents()
                    if docs_response:
                        import json
                        data = json.dumps(docs_response, indent=2)
                        st.download_button(
                            "💾 Download JSON",
                            data,
                            "documents_export.json",
                            "application/json"
                        )
                except Exception as e:
                    st.error(f"Export error: {e}")

def show_analytics_dashboard():
    """Show the analytics dashboard (Phase 4 feature)."""
    st.title("📊 Analytics Dashboard")
    st.markdown("*Comprehensive system analytics and insights*")
    
    if not st.session_state.get("access_token"):
        st.error("Please log in to access analytics")
        return
    
    # Check admin access
    user_info = st.session_state.get("user_info", {})
    user_role = user_info.get("role", "user")
    if user_role != "admin":
        st.error("Admin access required for analytics dashboard")
        return
    
    # Analytics navigation
    analytics_tabs = st.tabs([
        "📈 Usage Analytics", 
        "⚡ Performance", 
        "🔗 Similarity Analysis", 
        "👥 User Activity",
        "📋 Reports"
    ])
    
    with analytics_tabs[0]:
        show_usage_analytics()
    
    with analytics_tabs[1]:
        show_performance_analytics()
    
    with analytics_tabs[2]:
        show_similarity_analytics()
    
    with analytics_tabs[3]:
        show_user_activity_analytics()
    
    with analytics_tabs[4]:
        show_analytics_reports()

def show_usage_analytics():
    """Display usage analytics."""
    st.subheader("📈 Usage Analytics")
    
    # Date range selector
    col1, col2 = st.columns(2)
    with col1:
        days = st.selectbox(
            "Analysis Period",
            [7, 14, 30, 60, 90],
            index=2,
            help="Select the number of days to analyze"
        )
    
    with col2:
        if st.button("🔄 Refresh Analytics", key="refresh_usage"):
            st.cache_data.clear()
    
    try:
        # Fetch usage analytics
        headers = {"Authorization": f"Bearer {st.session_state.get('access_token', '')}"}
        response = requests.get(
            f"{BACKEND_URL}/analytics/usage?days={days}",
            headers=headers
        )
        
        if response.status_code == 200:
            analytics_data = response.json()["data"]
            
            # Display metrics cards
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric(
                    "Total Queries",
                    analytics_data["query_analytics"]["total_queries"],
                    help="Total number of queries in the selected period"
                )
            
            with col2:
                st.metric(
                    "Unique Users",
                    analytics_data["query_analytics"]["unique_users"],
                    help="Number of unique users who made queries"
                )
            
            with col3:
                st.metric(
                    "Documents Uploaded",
                    analytics_data["document_analytics"]["total_documents"],
                    help="Total documents uploaded in the period"
                )
            
            with col4:
                avg_similarity = analytics_data["query_analytics"]["avg_similarity_score"]
                st.metric(
                    "Avg Query Quality",
                    f"{avg_similarity:.3f}",
                    help="Average similarity score of query results"
                )
            
            # Daily trends chart
            if analytics_data["daily_trends"]:
                st.subheader("📅 Daily Query Trends")
                
                df_trends = pd.DataFrame(analytics_data["daily_trends"])
                # Category axis keeps a sensible layout even with a single day of data.
                df_trends['date'] = pd.to_datetime(df_trends['date']).dt.strftime('%b %d')

                fig = px.bar(
                    df_trends,
                    x='date',
                    y='queries',
                    title="Daily Query Volume",
                    text='queries'
                )
                fig.update_traces(marker_color="#1e3a8a", textposition="outside")
                fig.update_layout(
                    xaxis_title="Date",
                    yaxis_title="Number of Queries",
                    xaxis_type="category",
                    bargap=0.6 if len(df_trends) < 4 else 0.2,
                )
                st.plotly_chart(fig, width="stretch")
            
            # Document analytics
            st.subheader("📄 Document Analytics")
            doc_metrics = analytics_data["document_analytics"]
            
            col1, col2 = st.columns(2)
            with col1:
                # Use safe access for potentially missing keys
                avg_file_size = doc_metrics.get('avg_file_size', 'N/A')
                if isinstance(avg_file_size, (int, float)):
                    st.info(f"**Average File Size:** {avg_file_size / 1024:.1f} KB")
                else:
                    st.info(f"**Average File Size:** {avg_file_size}")
                st.info(f"**Average Passages per Document:** {doc_metrics.get('avg_chunks_per_doc', 0):.1f}")

            with col2:
                st.info(f"**Average Ingestion Time:** {doc_metrics.get('avg_processing_time', 0):.2f}s")
                st.info(f"**Documents in Library:** {doc_metrics.get('library_documents', 0)} "
                        f"({doc_metrics.get('library_chunks', 0)} passages)")
            
            # Query types distribution
            if analytics_data["top_query_types"]:
                st.subheader("🔍 Query Types Distribution")
                df_types = pd.DataFrame(analytics_data["top_query_types"])
                
                fig = px.pie(
                    df_types,
                    values='count',
                    names='type',
                    title="Distribution of Query Types"
                )
                st.plotly_chart(fig, width="stretch")
        
        else:
            st.error(f"Failed to fetch usage analytics: {response.status_code}")
    
    except Exception as e:
        st.error(f"Error loading usage analytics: {e}")

def show_performance_analytics():
    """Display performance analytics."""
    st.subheader("⚡ Performance Analytics")
    
    try:
        headers = {"Authorization": f"Bearer {st.session_state.get('access_token', '')}"}
        response = requests.get(
            f"{BACKEND_URL}/analytics/performance",
            headers=headers
        )
        
        if response.status_code == 200:
            perf_data = response.json()["data"]
            
            # Performance distribution
            if perf_data.get("performance_distribution"):
                st.subheader("🚀 Query Performance Distribution")
                
                # Show every latency band, including empty ones, in a fixed order.
                bands = {"very_fast": "< 0.1 s", "fast": "0.1–0.5 s", "moderate": "0.5–1 s",
                         "slow": "1–2 s", "very_slow": "> 2 s"}
                counts = {row["category"]: row["count"] for row in perf_data["performance_distribution"]}
                df_perf = pd.DataFrame({"band": list(bands.values()),
                                        "count": [counts.get(key, 0) for key in bands]})

                fig = px.bar(df_perf, x='band', y='count', title="Response Time Distribution", text='count')
                fig.update_traces(marker_color="#1e3a8a", textposition="outside")
                fig.update_layout(
                    xaxis_title="Response time",
                    yaxis_title="Number of Queries"
                )
                st.plotly_chart(fig, width="stretch")
            else:
                st.info("Performance distribution data not available")
            
            # Quality distribution
            if perf_data.get("quality_distribution"):
                st.subheader("🎯 Query Quality Distribution")
                
                quality_order = ["excellent", "good", "fair", "poor", "very_poor"]
                quality_colors = ["#15803d", "#4ade80", "#facc15", "#f97316", "#dc2626"]
                counts = {row["category"]: row["count"] for row in perf_data["quality_distribution"]}
                df_quality = pd.DataFrame({"quality": [pretty_label(q) for q in quality_order],
                                           "count": [counts.get(q, 0) for q in quality_order]})

                fig = px.bar(df_quality, x='quality', y='count', text='count',
                             title="Retrieval Quality (average similarity of retrieved passages)",
                             color='quality', color_discrete_sequence=quality_colors)
                fig.update_traces(textposition="outside")
                fig.update_layout(showlegend=False, xaxis_title="Quality band", yaxis_title="Number of Queries")
                st.plotly_chart(fig, width="stretch")
            else:
                st.info("Quality distribution data not available")
            
            # Slowest queries
            if perf_data.get("slowest_queries"):
                st.subheader("🐌 Slowest Queries")
                
                df_slow = pd.DataFrame(perf_data["slowest_queries"])
                
                for idx, row in df_slow.head(5).iterrows():
                    with st.expander(f"Query {idx + 1} - {row['processing_time']:.3f}s"):
                        st.text(row['query'])
                        st.caption(f"Similarity Score: {row['similarity_score']:.3f}")
            else:
                st.info("Slowest queries data not available")
            
            # Optimization suggestions
            if perf_data.get("optimization_suggestions"):
                st.subheader("💡 Optimization Suggestions")
                
                for suggestion in perf_data["optimization_suggestions"]:
                    st.info(f"💡 {suggestion}")
            else:
                st.info("No optimization suggestions available")
        
        else:
            st.error(f"Failed to fetch performance analytics: {response.status_code}")
    
    except Exception as e:
        st.error(f"Error loading performance analytics: {e}")

def show_similarity_analytics():
    """Display document similarity analytics."""
    st.subheader("🔗 Document Similarity Analysis")
    
    col1, col2 = st.columns([2, 1])
    
    with col2:
        analysis_type = st.radio(
            "Analysis Type",
            ["Overall Statistics", "Specific Document"],
            key="similarity_type"
        )
    
    try:
        headers = {"Authorization": f"Bearer {st.session_state.get('access_token', '')}"}
        
        if analysis_type == "Specific Document":
            # Get document list for selection
            doc_response = requests.get(f"{BACKEND_URL}/documents/list", headers=headers)
            if doc_response.status_code == 200:
                documents = doc_response.json()["documents"]
                if documents:
                    doc_options = {f"{doc.get('filename') or doc.get('source')} ({doc['id'][:8]})": doc['id']
                                 for doc in documents}
                    
                    selected_doc = st.selectbox(
                        "Select Document",
                        options=list(doc_options.keys()),
                        key="selected_doc_similarity"
                    )
                    
                    if selected_doc:
                        document_id = doc_options[selected_doc]
                        
                        response = requests.get(
                            f"{BACKEND_URL}/analytics/similarity?document_id={document_id}",
                            headers=headers
                        )
                        
                        if response.status_code == 200:
                            sim_data = response.json()["data"]
                            
                            st.subheader(f"📄 Similar Documents to: {selected_doc}")
                            
                            if sim_data["similar_documents"]:
                                for similar_doc in sim_data["similar_documents"]:
                                    similarity = similar_doc["similarity"]
                                    doc_name = similar_doc.get("filename") or similar_doc["document_id"]

                                    # Color code by similarity
                                    if similarity > 0.8:
                                        st.success(f"🔗 **{doc_name}** - Similarity: {similarity:.3f}")
                                    elif similarity > 0.6:
                                        st.info(f"🔗 **{doc_name}** - Similarity: {similarity:.3f}")
                                    else:
                                        st.warning(f"🔗 **{doc_name}** - Similarity: {similarity:.3f}")
                            else:
                                st.info("No similar documents found")
                else:
                    st.warning("No documents available for similarity analysis")
        else:
            # Overall statistics
            response = requests.get(
                f"{BACKEND_URL}/analytics/similarity",
                headers=headers
            )
            
            if response.status_code == 200:
                sim_data = response.json()["data"]
                
                # Overall stats
                if "overall_stats" in sim_data:
                    stats = sim_data["overall_stats"]
                    
                    col1, col2, col3 = st.columns(3)
                    
                    with col1:
                        st.metric(
                            "Average Similarity",
                            f"{stats['avg_similarity']:.3f}",
                            help="Average similarity across all document pairs"
                        )
                    
                    with col2:
                        st.metric(
                            "Maximum Similarity",
                            f"{stats['max_similarity']:.3f}",
                            help="Highest similarity score found"
                        )
                    
                    with col3:
                        st.metric(
                            "Total Comparisons",
                            stats['total_comparisons'],
                            help="Total number of document pair comparisons"
                        )
                
                # Similar document pairs
                if sim_data.get("similar_document_pairs"):
                    st.subheader("🔗 Most Similar Document Pairs")
                    
                    pairs_df = pd.DataFrame(sim_data["similar_document_pairs"])
                    
                    pairs_df = pairs_df.head(10).copy()
                    pairs_df["pair"] = pairs_df["doc1"] + "  ↔  " + pairs_df["doc2"]
                    fig = px.bar(
                        pairs_df.iloc[::-1], x="similarity", y="pair", orientation="h",
                        text=pairs_df.iloc[::-1]["similarity"].map(lambda v: f"{v:.2f}"),
                        range_x=[0, 1],
                    )
                    fig.update_traces(marker_color="#1e3a8a", textposition="outside")
                    fig.update_layout(xaxis_title="Cosine similarity of document embeddings",
                                      yaxis_title=None, height=120 + 45 * len(pairs_df))
                    st.plotly_chart(fig, width="stretch")
                    st.caption("Highly similar documents may be duplicates, amendments or templates of each other.")
        
    except Exception as e:
        st.error(f"Error loading similarity analytics: {e}")

def show_user_activity_analytics():
    """Display user activity analytics."""
    st.subheader("👥 User Activity Analytics")
    
    # Date range selector
    col1, col2 = st.columns(2)
    with col1:
        days = st.selectbox(
            "Analysis Period",
            [7, 14, 30, 60, 90],
            index=2,
            key="activity_days"
        )
    
    try:
        headers = {"Authorization": f"Bearer {st.session_state.get('access_token', '')}"}
        response = requests.get(
            f"{BACKEND_URL}/analytics/activity?days={days}",
            headers=headers
        )
        
        if response.status_code == 200:
            activity_data = response.json()["data"]
            
            # Active users metric
            st.metric(
                "Active Users",
                activity_data.get("active_users", 0),
                help=f"Number of active users in the last {days} days"
            )
            
            # Activity types distribution
            if activity_data.get("activity_types"):
                st.subheader("📊 Activity Types Distribution")
                
                df_activities = pd.DataFrame(activity_data["activity_types"])
                df_activities["type"] = df_activities["type"].map(lambda t: ACTIVITY_LABELS.get(t, t))

                fig = px.bar(df_activities, x='type', y='count', title="What people are doing", text='count')
                fig.update_traces(marker_color="#1e3a8a", textposition="outside")
                fig.update_layout(
                    xaxis_title="Activity",
                    yaxis_title="Number of Activities"
                )
                st.plotly_chart(fig, width="stretch")
            else:
                st.info("Activity types data not available")
            
            # Hourly activity patterns
            if activity_data.get("hourly_patterns"):
                st.subheader("🕐 Hourly Activity Patterns")
                
                # Fill all 24 hours so the shape of the working day is visible.
                counts = {row["hour"]: row["activity_count"] for row in activity_data["hourly_patterns"]}
                hours = [f"{h:02d}:00" for h in range(24)]
                df_hourly = pd.DataFrame({"hour": hours, "activity_count": [counts.get(h, 0) for h in hours]})

                fig = px.bar(df_hourly, x='hour', y='activity_count', title="Activity by Hour of Day (server time)")
                fig.update_traces(marker_color="#3b82f6")
                fig.update_layout(
                    xaxis_title="Hour of Day",
                    yaxis_title="Activity Count",
                    xaxis_type="category",
                )
                st.plotly_chart(fig, width="stretch")
            else:
                st.info("Hourly patterns data not available")
            
            # Top users
            if activity_data.get("top_users"):
                st.subheader("🏆 Most Active Users")
                
                df_users = pd.DataFrame(activity_data["top_users"])
                
                for idx, row in df_users.head(5).iterrows():
                    st.info(f"👤 **{row['user_id']}** - {row['activity_count']} activities")
            else:
                st.info("Top users data not available")
        
        else:
            st.error(f"Failed to fetch activity analytics: {response.status_code}")
    
    except Exception as e:
        st.error(f"Error loading activity analytics: {e}")

def show_analytics_reports():
    """Display analytics reports section."""
    st.subheader("📋 Analytics Reports")
    
    st.markdown("Generate and export comprehensive analytics reports.")
    
    col1, col2 = st.columns(2)
    
    with col1:
        report_format = st.selectbox(
            "Report Format",
            ["json"],  # Could add CSV, PDF later
            key="report_format"
        )
    
    with col2:
        if st.button("📥 Generate Report", key="generate_report"):
            try:
                headers = {"Authorization": f"Bearer {st.session_state.get('access_token', '')}"}
                response = requests.get(
                    f"{BACKEND_URL}/analytics/report?format={report_format}",
                    headers=headers
                )
                
                if response.status_code == 200:
                    report_data = response.json()
                    
                    # Display report summary
                    st.success("✅ Report generated successfully!")
                    
                    with st.expander("📄 Report Summary"):
                        st.json({
                            "generated_at": report_data.get("generated_at"),
                            "report_type": report_data.get("report_type"),
                            "sections": list(report_data.keys())
                        })
                    
                    # Download button
                    report_json = json.dumps(report_data, indent=2)
                    st.download_button(
                        label="💾 Download Full Report",
                        data=report_json,
                        file_name=f"analytics_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                        mime="application/json"
                    )
                    
                    # Display key insights
                    st.subheader("🔍 Key Insights")
                    
                    usage_data = report_data.get("usage_analytics", {})
                    if usage_data:
                        query_analytics = usage_data.get("query_analytics", {})
                        doc_analytics = usage_data.get("document_analytics", {})
                        
                        insights = []
                        
                        if query_analytics.get("total_queries", 0) > 0:
                            insights.append(f"📊 Total queries: {query_analytics['total_queries']}")
                            insights.append(f"⚡ Average processing time: {query_analytics['avg_processing_time']:.3f}s")
                            insights.append(f"🎯 Average similarity score: {query_analytics['avg_similarity_score']:.3f}")
                        
                        if doc_analytics.get("total_documents", 0) > 0:
                            insights.append(f"📄 Total documents: {doc_analytics['total_documents']}")
                            insights.append(f"🧩 Average chunks per document: {doc_analytics['avg_chunks_per_doc']:.1f}")
                        
                        for insight in insights:
                            st.info(insight)
                
                else:
                    st.error(f"Failed to generate report: {response.status_code}")
            
            except Exception as e:
                st.error(f"Error generating report: {e}")

def show_audit_log():
    """Admin view of the tamper-evident audit trail."""
    st.title("🛡️ Audit Log")
    st.markdown("*Every sign-in, upload, question and deletion, hash-chained so edits are detectable.*")

    if st.session_state.get("user_info", {}).get("role") != "admin":
        st.error("Admin access required")
        return
    headers = {"Authorization": f"Bearer {st.session_state.get('access_token', '')}"}

    try:
        summary = requests.get(f"{BACKEND_URL}/audit/summary?days=30", headers=headers, timeout=10).json()
        by_status = summary.get("by_status", {})
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Events (30 days)", sum(by_status.values()))
        col2.metric("Sign-ins", summary.get("by_action", {}).get("auth.login", 0))
        col3.metric("Queries", summary.get("by_action", {}).get("query.ask", 0))
        col4.metric("Failed / denied", by_status.get("failure", 0) + by_status.get("denied", 0))
    except Exception as e:
        st.warning(f"Could not load audit summary: {e}")

    with st.container(border=True):
        col1, col2 = st.columns([3, 1])
        with col1:
            st.markdown("**Integrity check** — recomputes the SHA-256 chain over every stored event.")
        with col2:
            if st.button("🔍 Verify chain", key="verify_audit_chain", width="stretch"):
                result = requests.get(f"{BACKEND_URL}/audit/verify", headers=headers, timeout=30).json()
                if result.get("valid"):
                    st.success(f"Intact — {result['checked']} events verified")
                else:
                    st.error(f"Tampering detected at event #{result.get('first_invalid_id')}")

    st.markdown("### Filter")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        username = st.text_input("User", key="audit_user").strip() or None
    with col2:
        action = st.selectbox("Action", ["All", "auth.login", "document.upload", "document.delete",
                                         "query.ask", "user.create", "analytics.export", "audit.",
                                         "access.ip_denied"], key="audit_action")
    with col3:
        outcome = st.selectbox("Outcome", ["All", "success", "failure", "denied"], key="audit_status")
    with col4:
        days = st.selectbox("Period", [1, 7, 30, 90, 365], index=2, key="audit_days",
                            format_func=lambda d: f"Last {d} day{'s' if d > 1 else ''}")

    params = {"limit": 500, "days": days}
    if username:
        params["username"] = username
    if action != "All":
        params["action"] = action
    if outcome != "All":
        params["status_filter"] = outcome

    try:
        response = requests.get(f"{BACKEND_URL}/audit/logs", headers=headers, params=params, timeout=15)
        response.raise_for_status()
        result = response.json()
    except Exception as e:
        st.error(f"Failed to load audit events: {e}")
        return

    events = result.get("events", [])
    st.caption(f"Showing {len(events)} of {result.get('total', 0)} matching events")
    if events:
        rows = [{
            "Time (UTC)": e["timestamp"][:19].replace("T", " "),
            "User": e.get("username") or "—",
            "Action": e["action"],
            "Outcome": e["status"],
            "Resource": e.get("resource") or "",
            "IP": e.get("ip_address") or "",
            "Details": json.dumps(e["details"]) if e.get("details") else "",
        } for e in events]
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

        export = requests.get(f"{BACKEND_URL}/audit/export", headers=headers,
                              params={k: v for k, v in params.items() if k != "limit"}, timeout=30)
        if export.status_code == 200:
            st.download_button("💾 Export CSV", export.content,
                               f"audit_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv", "text/csv")
    else:
        st.info("No audit events match these filters.")


# Enhanced chat interface with Phase 4 features
def show_enhanced_chat():
    """Enhanced chat interface with query suggestions and legal entity highlighting."""
    st.title("💬 Ask Your Documents")
    st.markdown("*Answers cite the exact passages they come from, with the parties, amounts and deadlines pulled out.*")

    if not st.session_state.get("access_token"):
        st.error("Please log in to use the chat interface")
        return

    # Initialize chat history
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []
    # A clicked suggestion is applied before the text area is created.
    if "pending_enhanced_query" in st.session_state:
        st.session_state.enhanced_chat_input = st.session_state.pop("pending_enhanced_query")
    
    # Query input with enhancements
    col1, col2 = st.columns([4, 1])
    
    with col1:
        user_query = st.text_area(
            "Your question",
            placeholder="e.g., What notice period is required to terminate the services agreement?",
            key="enhanced_chat_input",
            height=110
        )

    with col2:
        max_results = st.slider("Passages to retrieve", 1, 10, 5, key="enhanced_max_results")
        include_suggestions = st.checkbox("Suggest follow-ups", value=True, key="include_suggestions")
        highlight_entities = st.checkbox("Extract key terms", value=True, key="highlight_entities")
    
    if st.button("🔍 Submit Query", key="enhanced_submit", type="primary"):
        if user_query.strip():
            with st.spinner("Processing your query..."):
                try:
                    headers = {"Authorization": f"Bearer {st.session_state.get('access_token', '')}"}
                    
                    query_data = {
                        "query": user_query,
                        "max_results": max_results,
                    }
                    
                    response = requests.post(
                        f"{BACKEND_URL}/documents/query",
                        headers=headers,
                        json=query_data
                    )
                    
                    if response.status_code == 200:
                        result = response.json()
                        
                        # Add to chat history
                        chat_entry = {
                            "timestamp": datetime.now(),
                            "query": user_query,
                            "result": result
                        }
                        st.session_state.chat_history.append(chat_entry)
                        # The newest entry renders expanded in the history below.
                        st.rerun()
                    
                    else:
                        st.error(f"Query failed: {response.status_code}")
                        if response.text:
                            st.error(response.text)
                
                except Exception as e:
                    st.error(f"Error processing query: {e}")
        else:
            st.warning("Please enter a query")
    
    # Display chat history
    if st.session_state.chat_history:
        st.markdown("---")

        for i, entry in enumerate(reversed(st.session_state.chat_history[-5:])):  # Show last 5
            title = entry['query'] if len(entry['query']) <= 90 else entry['query'][:90] + "…"
            with st.expander(f"Q{len(st.session_state.chat_history) - i}: {title}", expanded=(i == 0)):
                st.caption(f"Asked at: {entry['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}")
                display_enhanced_query_result(entry['result'], include_suggestions, highlight_entities, entry_id=f"entry_{entry.get('timestamp', datetime.now()).strftime('%Y%m%d_%H%M%S_%f')}")
        
        if st.button("🗑️ Clear Chat History", key="clear_enhanced_chat"):
            st.session_state.chat_history = []
            st.rerun()

def answer_mode_caption(result: Dict) -> str:
    """One-line note on how an answer was produced."""
    if result.get("mode") == "generative":
        return f"Generated by local model `{result.get('model') or 'LLM'}` from the cited passages."
    return "Extractive mode: verbatim passages ranked by relevance (no local model connected)."


def display_enhanced_query_result(result: Dict, include_suggestions: bool = True, highlight_entities: bool = True, entry_id: str = None):
    """Display enhanced query result with Phase 4 features."""
    
    # Generate unique identifier for this entry if not provided
    if entry_id is None:
        entry_id = str(int(time.time() * 1000))  # Use timestamp as unique ID
    
    # Main answer
    st.markdown("### 🤖 AI Response")
    with st.container(border=True):
        st.markdown(result["answer"])
    if result.get("mode"):
        st.caption(answer_mode_caption(result))
    
    # Metadata
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Confidence", f"{result.get('confidence_score', result.get('confidence', 0)):.0%}")
    with col2:
        st.metric("Passages consulted", len(result["sources"]))
    with col3:
        st.metric("Response time", f"{result.get('processing_time', 0):.2f}s")
    
    # Key terms extracted from the cited passages
    if highlight_entities and result.get("legal_entities"):
        st.markdown("### 🏛️ Key Terms in the Cited Passages")
        labels = {
            "organizations": "🏢 Parties", "defined_terms": "📖 Defined terms",
            "monetary_amounts": "💵 Amounts", "durations": "⏱️ Periods",
            "percentages": "📈 Rates", "dates": "📅 Dates",
            "governing_law": "⚖️ Governing law", "citations": "📚 Citations",
        }
        for entity_type, entity_list in result["legal_entities"].items():
            if entity_list:
                tags = "  ".join(f"`{entity}`" for entity in entity_list[:10])
                st.markdown(f"**{labels.get(entity_type, entity_type.replace('_', ' ').title())}:** {tags}")

    # Follow-up suggestions
    if include_suggestions and result.get("query_suggestions"):
        st.markdown("### 💡 Suggested Follow-ups")
        
        suggestions = result["query_suggestions"]
        
        # Display suggestions as clickable buttons
        cols = st.columns(2)
        for i, suggestion in enumerate(suggestions[:6]):  # Show up to 6 suggestions
            with cols[i % 2]:
                if st.button(f"💭 {suggestion}", key=f"suggestion_{i}_{entry_id}"):
                    st.session_state.pending_enhanced_query = suggestion
                    st.rerun()
    
    # Sources with enhanced metadata
    if result["sources"]:
        st.markdown("### 📚 Sources")
        cited = set(result.get("citations") or [])

        for i, source in enumerate(result["sources"], 1):
            source_name = source.get('source', source.get('document_id', 'Unknown'))
            similarity = source.get('similarity', source.get('similarity_score', 0))
            category = pretty_label(source.get('category'))
            marker = "✅ cited" if i in cited else "retrieved"
            content = source.get("content") or source.get("text") or "Content not available"
            with st.container(border=True):
                st.markdown(f"**[{i}] {source_name}** · {category} · relevance {similarity:.2f} · _{marker}_")
                st.caption(content if len(content) <= 600 else content[:600].rsplit(" ", 1)[0] + "…")

def sign_out(notice: Optional[str] = None):
    """Clear the session and return to the sign-in page."""
    for key in ["authenticated", "access_token", "user_info", "chat_history"]:
        st.session_state.pop(key, None)
    if notice:
        st.session_state.session_notice = notice
    st.rerun()


def auth_headers() -> Dict[str, str]:
    return {"Authorization": f"Bearer {st.session_state.get('access_token', '')}"}


def api_error(response: requests.Response) -> str:
    try:
        return response.json().get("detail", response.text)
    except ValueError:
        return response.text or f"HTTP {response.status_code}"


def password_change_form(form_key: str, intro: Optional[str] = None) -> bool:
    """Render a change-password form; on success store the fresh token and return True."""
    with st.form(form_key, clear_on_submit=True):
        if intro:
            st.markdown(intro)
        current = st.text_input("Current password", type="password")
        new = st.text_input("New password", type="password",
                            help="At least 8 characters, not your username or the default password.")
        confirm = st.text_input("Confirm new password", type="password")
        submitted = st.form_submit_button("Update password", type="primary")
    if not submitted:
        return False
    if new != confirm:
        st.error("The new passwords don't match.")
        return False
    response = requests.post(f"{BACKEND_URL}/auth/change-password", headers=auth_headers(),
                             json={"current_password": current, "new_password": new}, timeout=15)
    if response.status_code != 200:
        st.error(api_error(response))
        return False
    st.session_state.access_token = response.json()["access_token"]
    st.session_state.user_info["must_change_password"] = False
    return True


def show_forced_password_change():
    """Blocking screen shown until a default or temporary password is replaced."""
    st.markdown('<div class="main-header"><h1>⚖️ Local Legal AI</h1>'
                '<p>Private, on-premise document intelligence for legal teams</p></div>',
                unsafe_allow_html=True)
    _, col, _ = st.columns([1, 1.4, 1])
    with col:
        username = st.session_state.user_info.get("username", "")
        st.markdown(f"#### 🔑 Choose a new password, {username}")
        st.info("You're signed in with a default or temporary password. "
                "Set your own password to continue — other sessions will be signed out.")
        if password_change_form("forced_password_change"):
            st.success("Password updated.")
            time.sleep(0.8)
            st.rerun()
        if st.button("Sign out", key="forced_change_sign_out"):
            sign_out()


def show_my_account():
    """Profile details and self-service password change for every user."""
    st.title("👤 My Account")
    info = st.session_state.get("user_info", {})
    col1, col2, col3 = st.columns(3)
    col1.metric("Username", info.get("username", "—"))
    col2.metric("Role", pretty_label(info.get("role")))
    previous = info.get("previous_login") or info.get("last_login")
    col3.metric("Previous sign-in", str(previous)[:16].replace("T", " ") if previous else "First sign-in")
    if info.get("email"):
        st.caption(f"Email: {info['email']}")

    st.markdown("### 🔑 Change password")
    st.caption("Changing your password signs out every other session for your account.")
    if password_change_form("account_password_change"):
        st.success("Password updated. Other sessions have been signed out.")


def show_integrations():
    """Admin view of the watched inbox folder and outbound n8n / Slack notifications."""
    st.title("🔌 Integrations")
    st.markdown("*Automatic ingestion from a watched folder, and event notifications to n8n and Slack.*")
    if st.session_state.get("user_info", {}).get("role") != "admin":
        st.error("Admin access required")
        return

    response = requests.get(f"{BACKEND_URL}/integrations/status", headers=auth_headers(), timeout=10)
    if response.status_code != 200:
        st.error(f"Failed to load integration status: {api_error(response)}")
        return
    status_data = response.json()
    inbox = status_data.get("inbox", {})
    notifications = status_data.get("notifications", {})

    # --- Watched folder -------------------------------------------------------------
    with st.container(border=True):
        head, action = st.columns([4, 1])
        with head:
            st.markdown("#### 📥 Watched inbox folder")
            if inbox.get("running"):
                st.caption(f"Checking `{inbox.get('inbox_dir')}` every {inbox.get('interval_seconds', 0):.0f}s. "
                           "Drop PDF, DOCX or TXT files in it — or in a sub-folder named after a category, "
                           "e.g. `contracts/` — and they are indexed automatically.")
            else:
                st.caption("The inbox watcher is disabled (`INBOX_ENABLED=false`).")
        with action:
            if inbox.get("running") and st.button("🔄 Scan now", key="scan_inbox", width="stretch"):
                scan = requests.post(f"{BACKEND_URL}/integrations/inbox/scan", headers=auth_headers(), timeout=600)
                if scan.status_code == 200:
                    counts = scan.json()["counts"]
                    st.toast(f"Indexed {counts['processed']}, failed {counts['failed']}")
                    st.rerun()
                else:
                    st.error(api_error(scan))
        if inbox.get("running"):
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Indexed", inbox.get("processed", 0))
            col2.metric("Failed", inbox.get("failed", 0))
            col3.metric("Waiting", inbox.get("waiting", 0))
            col4.metric("Last check", str(inbox.get("last_scan") or "—")[11:19] or "—")
            recent = inbox.get("recent", [])
            if recent:
                st.dataframe(pd.DataFrame([{
                    "Time": r["timestamp"].replace("T", " "),
                    "File": r["file"],
                    "Category": pretty_label(r.get("category")),
                    "Result": f"✅ {r.get('passages')} passages" if r.get("ok") else f"❌ {r.get('error')}",
                    "Moved to": r.get("moved_to", ""),
                } for r in recent]), width="stretch", hide_index=True)
            else:
                st.caption("No files processed since the server started.")

    # --- Notifications --------------------------------------------------------------
    with st.container(border=True):
        head, action = st.columns([4, 1])
        with head:
            st.markdown("#### 📣 Event notifications")
            st.caption("Uploads, deletions, user changes and security events are sent as JSON to n8n and/or as "
                       "messages to Slack. Only metadata is sent — never document text or questions.")
        with action:
            if notifications.get("enabled") and st.button("📨 Send test event", key="send_test_event", width="stretch"):
                test = requests.post(f"{BACKEND_URL}/integrations/test", headers=auth_headers(), timeout=60)
                if test.status_code == 200:
                    for delivery in test.json()["deliveries"]:
                        if delivery["ok"]:
                            st.success(f"{delivery['target']}: delivered (HTTP {delivery['status_code']})")
                        else:
                            st.error(f"{delivery['target']}: failed — {delivery['error']}")
                else:
                    st.error(api_error(test))

        n8n = notifications.get("n8n", {})
        slack = notifications.get("slack", {})
        col1, col2 = st.columns(2)
        with col1:
            if n8n.get("configured"):
                st.success(f"**n8n webhook:** {n8n.get('target')}"
                           + (" · signed (HMAC-SHA256)" if n8n.get("signed") else " · ⚠️ unsigned — set WEBHOOK_SECRET"))
            else:
                st.info("**n8n webhook:** not configured — set `N8N_WEBHOOK_URL` in `.env`")
        with col2:
            if slack.get("configured"):
                st.success(f"**Slack:** {slack.get('target')}")
            else:
                st.info("**Slack:** not configured — set `SLACK_WEBHOOK_URL` in `.env`")

        events = notifications.get("events", [])
        if events:
            st.markdown("**Events sent:** " + "  ".join(f"`{e}`" for e in events))
        deliveries = notifications.get("recent_deliveries", [])
        if deliveries:
            st.dataframe(pd.DataFrame([{
                "Time (UTC)": d["timestamp"].replace("T", " ")[:19],
                "Event": d["event"],
                "Target": d["target"],
                "Result": "✅ delivered" if d["ok"] else f"❌ {d['error']}",
                "Attempts": d["attempts"],
            } for d in deliveries]), width="stretch", hide_index=True)
        st.caption("Ready-made n8n workflows (Slack alerts, drop-zone ingestion, daily digest) are in "
                   "`workflows/n8n/` — see its README for setup.")


def show_user_admin():
    """Admin view: list, create, update, disable and reset users."""
    st.title("👥 Users")
    st.markdown("*Manage who can sign in, what they can do, and reset forgotten passwords.*")
    if st.session_state.get("user_info", {}).get("role") != "admin":
        st.error("Admin access required")
        return

    response = requests.get(f"{BACKEND_URL}/users", headers=auth_headers(), timeout=10)
    if response.status_code != 200:
        st.error(f"Failed to load users: {api_error(response)}")
        return
    users = response.json()["users"]

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Accounts", len(users))
    col2.metric("Active", sum(1 for u in users if u.get("is_active", True)))
    col3.metric("Administrators", sum(1 for u in users if u.get("role") == "admin"))
    col4.metric("Pending password change", sum(1 for u in users if u.get("must_change_password")))

    def fmt_time(value):
        return str(value)[:16].replace("T", " ") if value else "Never"

    st.dataframe(pd.DataFrame([{
        "Username": u["username"],
        "Email": u.get("email") or "",
        "Role": pretty_label(u.get("role")),
        "Status": ("Active" if u.get("is_active", True) else "Disabled")
                  + (" · must change password" if u.get("must_change_password") else ""),
        "Last sign-in": fmt_time(u.get("last_login")),
        "Created": fmt_time(u.get("created_at"))[:10],
    } for u in users]), width="stretch", hide_index=True)

    create_col, manage_col = st.columns(2)
    with create_col:
        with st.container(border=True):
            st.markdown("#### ➕ Add a user")
            with st.form("create_user_form", clear_on_submit=True):
                new_username = st.text_input("Username", placeholder="e.g. j.ellis")
                new_email = st.text_input("Email (optional)")
                new_role = st.selectbox("Role", ["lawyer", "user", "admin"], format_func=pretty_label,
                                        help="Admins manage users and see analytics and the audit log.")
                temp_password = st.text_input("Temporary password", type="password",
                                              help="Share it securely; the user must replace it at first sign-in.")
                must_change = st.checkbox("Require a new password at first sign-in", value=True)
                if st.form_submit_button("Create user", type="primary"):
                    created = requests.post(f"{BACKEND_URL}/auth/register", headers=auth_headers(), timeout=15, json={
                        "username": new_username.strip(), "email": new_email.strip() or None,
                        "role": new_role, "password": temp_password, "must_change_password": must_change,
                    })
                    if created.status_code == 200:
                        st.success(f"Created {new_username}.")
                        st.rerun()
                    else:
                        st.error(api_error(created))

    with manage_col:
        with st.container(border=True):
            st.markdown("#### ✏️ Manage a user")
            usernames = [u["username"] for u in users]
            selected = st.selectbox("User", usernames, key="manage_user_select")
            target = next(u for u in users if u["username"] == selected)
            roles = ["admin", "lawyer", "user"]
            with st.form("update_user_form"):
                role = st.selectbox("Role", roles, index=roles.index(target.get("role", "user"))
                                    if target.get("role") in roles else 2, format_func=pretty_label)
                active = st.toggle("Account active", value=target.get("is_active", True))
                email = st.text_input("Email", value=target.get("email") or "")
                if st.form_submit_button("Save changes", type="primary"):
                    saved = requests.patch(f"{BACKEND_URL}/users/{selected}", headers=auth_headers(), timeout=15,
                                           json={"role": role, "is_active": active, "email": email.strip() or None})
                    if saved.status_code == 200:
                        st.success(saved.json().get("message", "Saved"))
                        st.rerun()
                    else:
                        st.error(api_error(saved))
            with st.form("reset_password_form", clear_on_submit=True):
                temp = st.text_input(f"Temporary password for {selected}", type="password")
                if st.form_submit_button("Reset password"):
                    reset = requests.post(f"{BACKEND_URL}/users/{selected}/reset-password",
                                          headers=auth_headers(), json={"new_password": temp}, timeout=15)
                    if reset.status_code == 200:
                        st.success(reset.json()["message"])
                    else:
                        st.error(api_error(reset))
            st.caption("Disabling an account, changing its role or resetting its password "
                       "signs that user out everywhere.")


def main():
    """Main application function with Phase 4 enhancements."""
    st.sidebar.title("⚖️ Local Legal AI")
    st.sidebar.caption("Private document intelligence for legal teams")
    
    # Initialize session state variables
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if "access_token" not in st.session_state:
        st.session_state.access_token = None
    if "user_info" not in st.session_state:
        st.session_state.user_info = {}
    
    # Validate existing token if present
    if st.session_state.authenticated and st.session_state.access_token:
        try:
            headers = {"Authorization": f"Bearer {st.session_state.access_token}"}
            response = requests.get(f"{BACKEND_URL}/auth/me", headers=headers, timeout=10)
            if response.status_code == 200:
                # Keep role / pending-password state current (an admin may have changed them).
                st.session_state.user_info = {**(st.session_state.user_info or {}), **response.json()}
            else:
                # Token expired, revoked (password change, account disabled) or invalid
                st.session_state.authenticated = False
                st.session_state.access_token = None
                st.session_state.user_info = {}
                st.session_state.session_notice = response.json().get("detail", "Please sign in again.")
        except requests.RequestException:
            # Network error, assume token is still valid
            pass

    # Authentication check
    if not st.session_state.authenticated:
        show_login_page()
        return

    if st.session_state.user_info.get("must_change_password"):
        show_forced_password_change()
        return
    
    # Handle navigation from button clicks BEFORE creating the widget
    if "navigate_to" in st.session_state:
        st.session_state.main_navigation = st.session_state.navigate_to
        del st.session_state.navigate_to
    
    # Enhanced navigation with Phase 4 features
    pages = {
        "🏠 Dashboard": show_dashboard,
        "📄 Upload Documents": show_document_upload,
        "💬 Enhanced Chat": show_enhanced_chat,
        "📁 Document Management": show_document_management,
        "📁 Files Management": show_files_management,
    }
    if st.session_state.get("user_info", {}).get("role") == "admin":
        pages["📊 Analytics Dashboard"] = show_analytics_dashboard
        pages["🛡️ Audit Log"] = show_audit_log
        pages["👥 Users"] = show_user_admin
        pages["🔌 Integrations"] = show_integrations
    pages["👤 My Account"] = show_my_account
    if st.session_state.get("main_navigation") not in pages:
        st.session_state.main_navigation = "🏠 Dashboard"
    
    # Navigation
    # Initialize navigation if not set
    if "main_navigation" not in st.session_state:
        st.session_state.main_navigation = "🏠 Dashboard"
    
    selected_page = st.sidebar.selectbox(
        "Navigate to:",
        list(pages.keys()),
        key="main_navigation"
    )
    
    # User info in sidebar
    st.sidebar.markdown("---")
    user_info = st.session_state.get("user_info", {})
    user_id = user_info.get("username", "Unknown")
    user_role = user_info.get("role", "user")
    
    st.sidebar.markdown(f"**User:** {user_id}")
    st.sidebar.markdown(f"**Role:** {user_role.title()}")
    
    if st.sidebar.button("🚪 Logout", key="logout_main"):
        sign_out()
    
    # Show selected page
    pages[selected_page]()

if __name__ == "__main__":
    main()
