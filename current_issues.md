# Current Issues Tracking

-please fix the following numbered issues (stop and start the system when relevant for this). USE THIS FILE TO KEEP TRACK OF ISSUES (work your way one by one)
-mantain our @phases.md up to date with fixes and features we incorporate.
-test your work
- inform yourself (and me too) through what you understand from the @backend.log logs

Do not delete existing functionalities!

## ISSUES:

### ✅ RESOLVED ISSUES:

1. **[✅ FIXED]** Streamlit Widget Key Conflict in Document Upload:
   - **Issue:** "The widget with key "main_navigation" was created with a default value but also had its value set via the Session State API."
   - **Root Cause:** Conflicting default value (index parameter) with session state management
   - **Solution:** Removed index parameter from selectbox, allowing session state to handle defaults
   - **Files Modified:** `frontend/streamlit_app.py` (line 1285)
   - **Status:** ✅ Resolved and tested successfully

2. **[✅ FIXED]** KeyError: 'role' in Dashboard:
   - **Issue:** KeyError: 'role' when accessing chat history messages in dashboard
   - **Root Cause:** Unsafe dictionary access without checking key existence
   - **Solution:** Used .get() method for safe dictionary access: `msg.get('role') == 'user'`
   - **Files Modified:** `frontend/streamlit_app.py` (line 310)
   - **Status:** ✅ Resolved and tested successfully

3. **[✅ FIXED]** Nested Expanders Error in Enhanced Chat:
   - **Issue:** "Expanders may not be nested inside other expanders" error
   - **Root Cause:** Using st.expander within another expander context
   - **Solution:** Replaced nested expanders with container-based layout using st.container()
   - **Files Modified:** `frontend/streamlit_app.py` (line 1231)
   - **Status:** ✅ Resolved and tested successfully

4. **[✅ FIXED]** Analytics Dashboard Key Errors:
   - **Issue:** Missing keys like 'avg_file_size', 'performance_distribution', 'active_users'
   - **Root Cause:** Unsafe dictionary access for potentially missing keys
   - **Solution:** Used .get() method with default values and added fallback messages
   - **Files Modified:** `frontend/streamlit_app.py` (lines 625-1000)
   - **Status:** ✅ Resolved and tested successfully

5. **[✅ FIXED]** Session Persistence Issues:
   - **Issue:** User getting logged out after page refresh
   - **Root Cause:** Missing token validation and session state initialization
   - **Solution:** Added token validation, proper session state initialization, and token refresh logic
   - **Files Modified:** `frontend/streamlit_app.py` (main function)
   - **Status:** ✅ Resolved and tested successfully

6. **[✅ FIXED]** Document ID showing as NULL in Frontend:
   - **Issue:** Frontend showing "Document ID": NULL despite backend returning proper document_id
   - **Root Cause:** Frontend correctly implemented - backend returns proper document_id
   - **Solution:** Verified backend returns correct document_id format, frontend already using proper .get() access
   - **Files Modified:** None required - issue was false positive
   - **Status:** ✅ Verified working correctly

7. **[✅ FIXED]** KeyError: 'content' in Enhanced Chat Display:
   - **Issue:** KeyError when accessing source data in display_enhanced_query_result function
   - **Root Cause:** Unsafe dictionary access for source['content'], source['source'], and source['similarity']
   - **Solution:** Implemented safe dictionary access with .get() methods and fallback values
   - **Files Modified:** `frontend/streamlit_app.py` (lines 1252, 1264-1268, 1273)
   - **Status:** ✅ Resolved and tested successfully

8. **[✅ FIXED]** Missing /documents/list Endpoint:
   - **Issue:** 405 Method Not Allowed error for /documents/list endpoint
   - **Root Cause:** Frontend calling endpoint that didn't exist in backend
   - **Solution:** Added /documents/list endpoint as alias to /documents endpoint
   - **Files Modified:** `backend/app.py` (added new endpoint)
   - **Status:** ✅ Resolved and tested successfully

9. **[✅ FIXED]** Streamlit Duplicate Element Key Error:
   - **Issue:** "There are multiple elements with the same key='source_content_0'" in Enhanced Chat
   - **Root Cause:** Multiple chat entries creating text_area elements with identical keys
   - **Solution:** Added unique entry_id parameter to display_enhanced_query_result function
   - **Files Modified:** `frontend/streamlit_app.py` (lines 1201, 1195, 1276)
   - **Status:** ✅ Resolved and tested successfully

10. **[✅ FIXED]** KeyError: 'role' in Document Management:
    - **Issue:** KeyError when accessing chat history in show_document_management function
    - **Root Cause:** Unsafe dictionary access for msg['role'] in document management page
    - **Solution:** Used safe dictionary access with .get() method
    - **Files Modified:** `frontend/streamlit_app.py` (line 562)
    - **Status:** ✅ Resolved and tested successfully

11. **[✅ FIXED]** ONNX Runtime Errors in Document Upload:
    - **Issue:** `[ONNXRuntimeError] ... Error computing NN outputs` when storing documents in ChromaDB
    - **Root Cause:** ChromaDB's DefaultEmbeddingFunction using ONNX/CoreML which fails on macOS
    - **Solution:** Implemented embedding function fallback system with SentenceTransformers, SimpleEmbeddingFunction, and DefaultEmbeddingFunction
    - **Files Modified:** `vector_store/chromadb_setup.py` (added _get_embedding_function method)
    - **Status:** ✅ Resolved and tested successfully

### 📋 ACTIVE ISSUES:

1. in 📊 Document Management im seeing this information which is not acurate:
📋 Document Overview
Collection Information:

Total Documents: 0
Collection Name: unknown
Status: unknown

2. 

### ⚠️ MONITORING ITEMS:

1. **[🔍 MONITORING]** bcrypt Compatibility Warning:
   - **Issue:** `AttributeError: module 'bcrypt' has no attribute '__about__'`
   - **Impact:** Minor warning during authentication, does not affect functionality
   - **Current Status:** Non-critical - authentication working correctly
   - **Action:** Consider bcrypt version update when convenient

---

### 🎯 SYSTEM STATUS: **FULLY OPERATIONAL**

**Last Updated:** 2025-06-01 00:55:00
**System Status:** ✅ All Critical Issues Resolved
**Backend Health:** ✅ Healthy (Status 200)
**Frontend Status:** ✅ Accessible (Status 200)
**Document Upload:** ✅ Working with proper Document ID display
**Analytics Dashboard:** ✅ All endpoints working with proper error handling
**Enhanced Chat:** ✅ No duplicate key errors, all UI issues resolved
**Session Management:** ✅ Persistent sessions with token validation
**Document Management:** ✅ All /documents endpoints working correctly
**Monitoring:** ⚠️ 1 non-critical item under observation