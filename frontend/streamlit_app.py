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
from datetime import datetime, timedelta
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from typing import Optional, Dict, Any, List
import os

# Configure Streamlit page
st.set_page_config(
    page_title="Local Legal AI - Phase 4",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Global configuration
API_BASE_URL = "http://localhost:8000"
AUTH_TOKEN = st.session_state.get("access_token", "")
ADMIN_CREDENTIALS = {"username": "admin", "password": "admin123"}
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

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
        
        **Note:** Session expires on page refresh. Please avoid refreshing the page.
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
    """Display the main dashboard with quick actions and system info."""
    st.markdown("## 🏠 Dashboard")
    st.markdown("Welcome to the Local Legal AI System! Choose an action below to get started.")
    
    # Quick actions
    st.markdown("### ⚡ Quick Actions")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("### 📄 Document Operations")
        
        # Use different session state variables for button navigation
        if st.button("📄 Upload New Document", type="primary", key="nav_upload"):
            st.session_state.navigate_to = "📄 Upload Documents"
            st.rerun()
        
        if st.button("💬 Start Chat Session", key="nav_chat"):
            st.session_state.navigate_to = "💬 Enhanced Chat"
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
                df_trends['date'] = pd.to_datetime(df_trends['date'])
                
                fig = px.line(
                    df_trends, 
                    x='date', 
                    y='queries',
                    title="Daily Query Volume",
                    markers=True
                )
                fig.update_layout(
                    xaxis_title="Date",
                    yaxis_title="Number of Queries",
                    hovermode='x unified'
                )
                st.plotly_chart(fig, use_container_width=True)
            
            # Document analytics
            st.subheader("📄 Document Analytics")
            doc_metrics = analytics_data["document_analytics"]
            
            col1, col2 = st.columns(2)
            with col1:
                st.info(f"**Average File Size:** {doc_metrics['avg_file_size']:.0f} bytes")
                st.info(f"**Average Chunks per Document:** {doc_metrics['avg_chunks_per_doc']:.1f}")
            
            with col2:
                st.info(f"**Average Processing Time:** {doc_metrics['avg_processing_time']:.3f}s")
                st.info(f"**Average Legal Complexity:** {doc_metrics['avg_legal_complexity']:.3f}")
            
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
                st.plotly_chart(fig, use_container_width=True)
        
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
            if perf_data["performance_distribution"]:
                st.subheader("🚀 Query Performance Distribution")
                
                df_perf = pd.DataFrame(perf_data["performance_distribution"])
                
                fig = px.bar(
                    df_perf,
                    x='category',
                    y='count',
                    color='avg_time',
                    title="Query Performance Categories",
                    color_continuous_scale='RdYlGn_r'
                )
                fig.update_layout(
                    xaxis_title="Performance Category",
                    yaxis_title="Number of Queries"
                )
                st.plotly_chart(fig, use_container_width=True)
            
            # Quality distribution
            if perf_data["quality_distribution"]:
                st.subheader("🎯 Query Quality Distribution")
                
                df_quality = pd.DataFrame(perf_data["quality_distribution"])
                
                fig = px.pie(
                    df_quality,
                    values='count',
                    names='category',
                    title="Query Result Quality Distribution",
                    color_discrete_map={
                        'excellent': '#2E8B57',
                        'good': '#32CD32',
                        'fair': '#FFD700',
                        'poor': '#FF6347',
                        'very_poor': '#DC143C'
                    }
                )
                st.plotly_chart(fig, use_container_width=True)
            
            # Slowest queries
            if perf_data["slowest_queries"]:
                st.subheader("🐌 Slowest Queries")
                
                df_slow = pd.DataFrame(perf_data["slowest_queries"])
                
                for idx, row in df_slow.head(5).iterrows():
                    with st.expander(f"Query {idx + 1} - {row['processing_time']:.3f}s"):
                        st.text(row['query'])
                        st.caption(f"Similarity Score: {row['similarity_score']:.3f}")
            
            # Optimization suggestions
            if perf_data["optimization_suggestions"]:
                st.subheader("💡 Optimization Suggestions")
                
                for suggestion in perf_data["optimization_suggestions"]:
                    st.info(f"💡 {suggestion}")
        
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
                    doc_options = {f"{doc['source']} ({doc['document_id'][:8]}...)": doc['document_id'] 
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
                                    doc_id = similar_doc["document_id"]
                                    
                                    # Color code by similarity
                                    if similarity > 0.8:
                                        st.success(f"🔗 **{doc_id[:12]}...** - Similarity: {similarity:.3f}")
                                    elif similarity > 0.6:
                                        st.info(f"🔗 **{doc_id[:12]}...** - Similarity: {similarity:.3f}")
                                    else:
                                        st.warning(f"🔗 **{doc_id[:12]}...** - Similarity: {similarity:.3f}")
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
                    
                    for idx, row in pairs_df.head(10).iterrows():
                        similarity = row['similarity']
                        
                        # Color code by similarity level
                        if similarity > 0.9:
                            st.success(f"🔗 **{row['doc1'][:12]}...** ↔ **{row['doc2'][:12]}...** - Similarity: {similarity:.3f}")
                        elif similarity > 0.8:
                            st.info(f"🔗 **{row['doc1'][:12]}...** ↔ **{row['doc2'][:12]}...** - Similarity: {similarity:.3f}")
                        else:
                            st.warning(f"🔗 **{row['doc1'][:12]}...** ↔ **{row['doc2'][:12]}...** - Similarity: {similarity:.3f}")
        
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
                activity_data["active_users"],
                help=f"Number of active users in the last {days} days"
            )
            
            # Activity types distribution
            if activity_data["activity_types"]:
                st.subheader("📊 Activity Types Distribution")
                
                df_activities = pd.DataFrame(activity_data["activity_types"])
                
                fig = px.bar(
                    df_activities,
                    x='type',
                    y='count',
                    title="User Activity Types",
                    color='count',
                    color_continuous_scale='viridis'
                )
                fig.update_layout(
                    xaxis_title="Activity Type",
                    yaxis_title="Number of Activities"
                )
                st.plotly_chart(fig, use_container_width=True)
            
            # Hourly activity patterns
            if activity_data["hourly_patterns"]:
                st.subheader("🕐 Hourly Activity Patterns")
                
                df_hourly = pd.DataFrame(activity_data["hourly_patterns"])
                
                fig = px.line(
                    df_hourly,
                    x='hour',
                    y='activity_count',
                    title="Activity Pattern by Hour of Day",
                    markers=True
                )
                fig.update_layout(
                    xaxis_title="Hour of Day",
                    yaxis_title="Activity Count"
                )
                st.plotly_chart(fig, use_container_width=True)
            
            # Top users
            if activity_data["top_users"]:
                st.subheader("🏆 Most Active Users")
                
                df_users = pd.DataFrame(activity_data["top_users"])
                
                for idx, row in df_users.head(5).iterrows():
                    st.info(f"👤 **{row['user_id']}** - {row['activity_count']} activities")
        
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

# Enhanced chat interface with Phase 4 features
def show_enhanced_chat():
    """Enhanced chat interface with query suggestions and legal entity highlighting."""
    st.title("💬 Enhanced Legal Chat")
    st.markdown("*AI-powered legal document analysis with advanced features*")
    
    if not st.session_state.get("access_token"):
        st.error("Please log in to use the chat interface")
        return
    
    # Initialize chat history
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []
    
    # Query input with enhancements
    col1, col2 = st.columns([4, 1])
    
    with col1:
        user_query = st.text_area(
            "Enter your legal question:",
            placeholder="e.g., What are the termination conditions in employment agreements?",
            key="enhanced_chat_input",
            height=100
        )
    
    with col2:
        st.markdown("### Settings")
        max_results = st.slider("Max Results", 1, 10, 5, key="enhanced_max_results")
        similarity_threshold = st.slider("Similarity Threshold", 0.1, 0.9, 0.3, step=0.1, key="enhanced_similarity")
        include_suggestions = st.checkbox("Show Query Suggestions", value=True, key="include_suggestions")
        highlight_entities = st.checkbox("Highlight Legal Entities", value=True, key="highlight_entities")
    
    if st.button("🔍 Submit Query", key="enhanced_submit", type="primary"):
        if user_query.strip():
            with st.spinner("Processing your query..."):
                try:
                    headers = {"Authorization": f"Bearer {st.session_state.get('access_token', '')}"}
                    
                    query_data = {
                        "query": user_query,
                        "max_results": max_results,
                        "similarity_threshold": similarity_threshold,
                        "include_metadata": True
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
                        
                        # Display result
                        display_enhanced_query_result(result, include_suggestions, highlight_entities)
                    
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
        st.subheader("💬 Chat History")
        
        for i, entry in enumerate(reversed(st.session_state.chat_history[-5:])):  # Show last 5
            with st.expander(f"Query {len(st.session_state.chat_history) - i}: {entry['query'][:50]}...", expanded=(i == 0)):
                st.caption(f"Asked at: {entry['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}")
                display_enhanced_query_result(entry['result'], include_suggestions, highlight_entities)
        
        if st.button("🗑️ Clear Chat History", key="clear_enhanced_chat"):
            st.session_state.chat_history = []
            st.rerun()

def display_enhanced_query_result(result: Dict, include_suggestions: bool = True, highlight_entities: bool = True):
    """Display enhanced query result with Phase 4 features."""
    
    # Main answer
    st.markdown("### 🤖 AI Response")
    st.info(result["answer"])
    
    # Metadata
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Confidence", f"{result['confidence']:.3f}")
    with col2:
        st.metric("Sources Found", len(result["sources"]))
    with col3:
        st.metric("Processing Time", f"{result['processing_time']:.3f}s")
    
    # Legal entities (Phase 4 feature)
    if highlight_entities and result.get("legal_entities"):
        st.markdown("### 🏛️ Legal Entities Identified")
        
        entities = result["legal_entities"]
        
        for entity_type, entity_list in entities.items():
            if entity_list:
                st.markdown(f"**{entity_type.replace('_', ' ').title()}:**")
                
                # Display entities as tags
                entity_tags = "  ".join([f"`{entity}`" for entity in entity_list[:10]])  # Limit to first 10
                st.markdown(entity_tags)
    
    # Query suggestions (Phase 4 feature)
    if include_suggestions and result.get("query_suggestions"):
        st.markdown("### 💡 Related Query Suggestions")
        
        suggestions = result["query_suggestions"]
        
        # Display suggestions as clickable buttons
        cols = st.columns(2)
        for i, suggestion in enumerate(suggestions[:6]):  # Show up to 6 suggestions
            with cols[i % 2]:
                if st.button(f"💭 {suggestion}", key=f"suggestion_{i}_{len(st.session_state.get('chat_history', []))}"):
                    st.session_state.enhanced_chat_input = suggestion
                    st.rerun()
    
    # Sources with enhanced metadata
    if result["sources"]:
        st.markdown("### 📚 Source Documents")
        
        for i, source in enumerate(result["sources"]):
            with st.expander(f"📄 Source {i+1} - {source['source']} (Similarity: {source['similarity']:.3f})"):
                
                # Enhanced source metadata
                col1, col2 = st.columns(2)
                
                with col1:
                    st.markdown(f"**Category:** {source.get('category', 'N/A')}")
                    st.markdown(f"**Chunk Index:** {source.get('chunk_index', 'N/A')}")
                
                with col2:
                    if 'legal_score' in source:
                        st.markdown(f"**Legal Relevance:** {source['legal_score']:.3f}")
                    if 'complexity_score' in source:
                        st.markdown(f"**Complexity:** {source['complexity_score']:.3f}")
                    if 'section_type' in source:
                        st.markdown(f"**Section Type:** {source['section_type']}")
                
                # Source text
                st.markdown("**Content:**")
                st.text(source["text"])

# Update the main navigation to include analytics
def main():
    """Main application function with Phase 4 enhancements."""
    st.sidebar.title("⚖️ Local Legal AI")
    st.sidebar.markdown("*Phase 4 - Enhanced Analytics & RAG*")
    
    # Authentication check - using the correct session state variables
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    
    if not st.session_state.authenticated:
        show_login_page()
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
        "📊 Analytics Dashboard": show_analytics_dashboard,
        "📁 Document Management": show_document_management
    }
    
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
        for key in ["authenticated", "access_token", "user_info"]:
            if key in st.session_state:
                del st.session_state[key]
        st.rerun()
    
    # Show selected page
    pages[selected_page]()

if __name__ == "__main__":
    main()
