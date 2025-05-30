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

import streamlit as st
import requests
import json
import time
from datetime import datetime
import pandas as pd
from typing import Optional, Dict, Any

# Configure Streamlit page
st.set_page_config(
    page_title="Local Legal AI",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Configuration
API_BASE_URL = "http://localhost:8000"
ADMIN_CREDENTIALS = {"username": "admin", "password": "admin123"}

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
            return None
        except Exception as e:
            st.error(f"Login error: {e}")
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
    st.markdown('<div class="main-header"><h1>⚖️ Local Legal AI</h1><p>AI-Powered Legal Document Analysis</p></div>', 
                unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        st.markdown("### 🔐 Authentication")
        
        with st.form("login_form"):
            username = st.text_input("Username", value="admin")
            password = st.text_input("Password", type="password", value="admin123")
            submit_button = st.form_submit_button("Login", type="primary")
            
            if submit_button:
                if username and password:
                    with st.spinner("Authenticating..."):
                        result = api_client.login(username, password)
                        
                    if result:
                        st.session_state.authenticated = True
                        st.session_state.access_token = result["access_token"]
                        st.session_state.user_info = result["user"]
                        st.success("✅ Login successful!")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("❌ Invalid credentials")
                else:
                    st.error("Please enter both username and password")
        
        # Quick login help
        st.markdown("""
        ---
        **Demo Credentials:**
        - Username: `admin`
        - Password: `admin123`
        
        **System Features:**
        - 📄 Upload legal documents
        - 🤖 AI-powered document analysis
        - 💬 Interactive chat interface
        - 📊 Document management
        """)

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

def show_dashboard():
    """Display dashboard with system overview."""
    st.markdown("## 🏠 Dashboard")
    
    # System health check
    health = api_client.check_health()
    if health:
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.markdown(f"""
            <div class="metric-card">
                <h3>🟢 API Status</h3>
                <p>{health['services']['api'].title()}</p>
            </div>
            """, unsafe_allow_html=True)
        
        with col2:
            st.markdown(f"""
            <div class="metric-card">
                <h3>🗄️ ChromaDB</h3>
                <p>{health['services']['chromadb'].title()}</p>
            </div>
            """, unsafe_allow_html=True)
        
        with col3:
            st.markdown(f"""
            <div class="metric-card">
                <h3>🤖 Model</h3>
                <p>{health['services']['model'].title()}</p>
            </div>
            """, unsafe_allow_html=True)
        
        with col4:
            # Get document stats
            doc_stats = api_client.list_documents()
            doc_count = doc_stats.get('total_documents', 0) if doc_stats else 0
            st.markdown(f"""
            <div class="metric-card">
                <h3>📚 Documents</h3>
                <p>{doc_count} Total</p>
            </div>
            """, unsafe_allow_html=True)
    
    st.markdown("---")
    
    # Quick actions
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("### 🚀 Quick Actions")
        if st.button("📄 Upload New Document", type="primary"):
            st.session_state.page_selector = "📄 Document Upload"
            st.rerun()
        
        if st.button("💬 Start Chat Session"):
            st.session_state.page_selector = "💬 Chat Interface"
            st.rerun()
    
    with col2:
        st.markdown("### 📈 Recent Activity")
        if len(st.session_state.chat_history) > 0:
            st.write("Recent queries:")
            for i, msg in enumerate(st.session_state.chat_history[-3:]):
                if msg['role'] == 'user':
                    st.write(f"• {msg['content'][:50]}...")
        else:
            st.write("No recent activity")
    
    # System information
    st.markdown("---")
    st.markdown("### ℹ️ System Information")
    
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("""
        **Backend Features:**
        - TF-IDF embedder for document analysis
        - ChromaDB vector storage
        - JWT authentication
        - FastAPI REST endpoints
        """)
    
    with col2:
        st.markdown("""
        **Supported Operations:**
        - Legal document upload and processing
        - Intelligent document chunking
        - Semantic similarity search
        - Context-aware Q&A
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
        **Supported Formats:**
        - ✅ Text files (.txt)
        - ⚠️ PDF files (basic support)
        - ⚠️ Word documents (basic support)
        
        **Best Practices:**
        - Use descriptive titles
        - Select appropriate categories
        - Ensure documents are text-readable
        - Legal documents work best
        
        **Processing Info:**
        - Documents are chunked intelligently
        - Legal sections are detected
        - TF-IDF embeddings are generated
        - Stored in ChromaDB for search
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
                    {message['content']}
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown(f"""
                <div class="chat-message assistant-message">
                    <strong>🤖 Legal AI:</strong><br>
                    {message['content']}
                </div>
                """, unsafe_allow_html=True)
                
                # Show sources if available
                if 'sources' in message and message['sources']:
                    with st.expander(f"📚 Sources ({len(message['sources'])} documents)"):
                        for i, source in enumerate(message['sources'][:3]):
                            st.markdown(f"""
                            **Source {i+1}:** {source.get('document_id', 'Unknown')[:8]}...
                            - **Similarity:** {source.get('similarity_score', 0):.3f}
                            - **Content:** {source.get('content', '')[:200]}...
                            """)
    
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
        recent_queries = [msg for msg in st.session_state.chat_history if msg['role'] == 'user'][-5:]
        
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

def main():
    """Main application entry point."""
    # Check if user is authenticated
    if not st.session_state.authenticated:
        show_login_page()
    else:
        show_main_interface()

if __name__ == "__main__":
    main()
