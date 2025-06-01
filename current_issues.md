# Current Issues Tracking

-please fix the following numbered issues (stop and start the system when relevant for this). USE THIS FILE TO KEEP TRACK OF ISSUES 
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

### 📋 ACTIVE ISSUES:

1. for some reasion i'm seeing a success message, yet the json that is showed in the frontend after uploading is showing the Document ID as "NULL": (i thout this was already working, it might be we just arent reading it properly?)

✅ Document uploaded successfully!

{
"Document ID":NULL
"Chunks Processed":0
"Processing Time":"3.11s"
}

2. when i tried asking this question in "💬 Enhanced Legal Chat" "what documents do we have?" i got:

Query failed: 405

{"detail":"Method Not Allowed"}

3. in "📊 Analytics Dashboard"

a. under Usage Analytics im getting :
"Failed to fetch usage analytics: 404"

b. under Performance iim getting:
"Failed to fetch performance analytics: 404"
c. under user activity analytics :
"Failed to fetch activity analytics: 404"
d. under reports when i click Generate report i get :
Failed to generate report: 404

4. when i refresh the page seems i get bumped out of the session, it asks me to log in again


---

I. **[🔍 MONITORING]** Backend Logs Analysis:
   - **Current Status:** Backend healthy (Status 200), but some warnings present
   - **Observed Warnings:** 
     - PyTorch version 2.1+ required (current: 2.0.1)
     - SentenceTransformers not available (handled with fallback)
   - **Mitigation:** Fallback mechanisms implemented and working
   - **Action Required:** None - system operational with graceful degradation

### 🎯 NEXT AREAS TO MONITOR:

II. **Performance Optimization:** Monitor TF-IDF fallback performance vs SentenceTransformers
III. **Dependency Updates:** Consider PyTorch upgrade when compatible versions available
IV. **User Experience:** Continue monitoring for any new UI/UX issues

---

**Last Updated:** 2025-05-31 22:18:41  
**System Status:** ✅ Fully Operational  
**Active Issues:** 0 Critical, 1 Monitoring