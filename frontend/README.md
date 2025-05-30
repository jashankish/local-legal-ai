# Local Legal AI - Frontend (Phase 3)

A comprehensive Streamlit web interface for the Local Legal AI system, featuring user authentication, document management, and an interactive RAG-powered chat interface.

## ✨ Features

### 🔐 Authentication System
- JWT-based user authentication
- Admin/user role management
- Secure session handling
- Auto-login with demo credentials

### 📄 Document Upload & Management
- Drag-and-drop file upload interface
- Support for .txt, .pdf, .doc, .docx files
- Document categorization (employment, contract, litigation, etc.)
- Real-time processing feedback
- Document preview for text files

### 💬 Interactive Chat Interface
- RAG-powered Q&A system
- Real-time document analysis
- Source citations with similarity scores
- Conversation history
- Suggested legal questions
- Context-aware responses

### 📊 Dashboard & Analytics
- System health monitoring
- Document statistics
- Recent activity tracking
- Admin controls
- Collection status overview

## 🚀 Quick Start

### Prerequisites
- Python 3.8+
- FastAPI backend running on `http://localhost:8000`
- All Phase 1 & 2 components operational

### Installation

1. **Install frontend dependencies:**
```bash
cd frontend
pip install -r requirements.txt
```

2. **Start the frontend:**
```bash
python run_frontend.py
```

Or run directly:
```bash
streamlit run streamlit_app.py --server.port 8501
```

3. **Access the application:**
- Open your browser to `http://localhost:8501`
- Login with demo credentials: `admin` / `admin123`

## 🎯 User Guide

### Getting Started
1. **Login:** Use the demo credentials (admin/admin123)
2. **Dashboard:** View system status and quick actions
3. **Upload Documents:** Add legal documents for analysis
4. **Chat:** Ask questions about uploaded documents
5. **Manage:** View document statistics and history

### Using the Chat Interface

**Sample Questions:**
- "What is the salary mentioned in the employment agreement?"
- "What are the key terms and conditions?"
- "How can the agreement be terminated?"
- "What confidentiality requirements are specified?"

**Features:**
- Real-time responses from TF-IDF embedder
- Source document citations
- Similarity scores for transparency
- Conversation history retention

### Document Upload

**Supported Formats:**
- ✅ Text files (.txt) - Full support
- ⚠️ PDF files (.pdf) - Basic text extraction
- ⚠️ Word documents (.doc, .docx) - Basic text extraction

**Best Practices:**
- Use descriptive document titles
- Select appropriate categories
- Ensure documents contain readable text
- Legal documents work best with the system

## 🏗️ Architecture

### Component Structure
```
frontend/
├── streamlit_app.py      # Main Streamlit application
├── run_frontend.py       # Startup script
├── requirements.txt      # Python dependencies
└── README.md            # This file
```

### API Integration
The frontend communicates with the FastAPI backend via:
- **Authentication:** `/auth/login`, `/auth/me`
- **Documents:** `/documents/upload`, `/documents/stats`, `/documents`
- **Queries:** `/query` (RAG pipeline)
- **Health:** `/health` (system status)

### Session Management
- JWT tokens stored in Streamlit session state
- Automatic token refresh handling
- Secure logout functionality
- Persistent chat history within session

## 🎨 UI/UX Features

### Modern Design
- Clean, professional interface
- Responsive layout for different screen sizes
- Custom CSS styling with blue/green theme
- Intuitive navigation with sidebar menu

### Interactive Elements
- Real-time system status indicators
- Progress bars for document processing
- Expandable source citations
- Quick action buttons
- Suggested question buttons

### Error Handling
- Graceful API error handling
- User-friendly error messages
- Connection status indicators
- Automatic retry mechanisms

## 🔧 Configuration

### Environment Variables
Set these in your environment or `.env` file:
```bash
API_BASE_URL=http://localhost:8000  # FastAPI backend URL
```

### Customization
- Modify `API_BASE_URL` in `streamlit_app.py` for different backend locations
- Adjust styling in the custom CSS section
- Configure page layout in `st.set_page_config()`

## 🧪 Testing the Frontend

### Manual Testing Checklist
- [ ] Login with demo credentials
- [ ] Navigate between different pages
- [ ] Upload a test document
- [ ] Ask questions in chat interface
- [ ] View document statistics
- [ ] Check system health status
- [ ] Test logout functionality

### Sample Test Flow
1. **Login:** Use admin/admin123
2. **Upload:** Upload the provided test document
3. **Query:** Ask "What is the salary mentioned?"
4. **Verify:** Check that sources are displayed
5. **Navigate:** Test all menu options

## 🔍 Troubleshooting

### Common Issues

**"Connection Error"**
- Ensure FastAPI backend is running on port 8000
- Check that Phase 2 tests are passing
- Verify network connectivity

**"Authentication Failed"**
- Use correct demo credentials: admin/admin123
- Check backend `/auth/login` endpoint
- Clear browser cache if needed

**"Upload Failed"**
- Ensure file is in supported format
- Check file size (should be reasonable)
- Verify backend `/documents/upload` endpoint

**"No Documents Found"**
- Upload at least one document first
- Check document processing was successful
- Verify ChromaDB is operational

### Debug Mode
Run Streamlit in debug mode:
```bash
streamlit run streamlit_app.py --logger.level=debug
```

## 📈 Performance Notes

### Expected Response Times
- **Login:** < 1 second
- **Document Upload:** 2-5 seconds (depending on size)
- **Query Processing:** 2-4 seconds
- **Page Navigation:** < 0.5 seconds

### Resource Usage
- **Frontend:** Minimal (Streamlit is lightweight)
- **Memory:** ~50-100MB for typical usage
- **Network:** REST API calls to backend

## 🚀 Next Steps (Phase 4)

Planned enhancements:
- Real-time streaming responses
- Advanced document viewer with highlighting
- Batch document upload
- Export conversation history
- Advanced analytics dashboard
- Multi-user support with individual workspaces

## 🤝 Contributing

When extending the frontend:
1. Follow Streamlit best practices
2. Maintain consistent UI/UX patterns
3. Add proper error handling
4. Update this README with new features
5. Test thoroughly with the backend

## 📜 License

Part of the Local Legal AI project - see main project LICENSE file. 