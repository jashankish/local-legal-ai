#!/usr/bin/env python3
"""
Enhanced Document Processor for Phase 4
Supports multiple file formats with advanced processing capabilities
"""

import os
import logging
import mimetypes
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
import hashlib
import re
import unicodedata

# Document processing libraries
try:
    import PyPDF2
    import fitz  # PyMuPDF
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False

try:
    from docx import Document as DocxDocument
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False

try:
    import docx2txt
    DOCX2TXT_AVAILABLE = True
except ImportError:
    DOCX2TXT_AVAILABLE = False

class EnhancedDocumentProcessor:
    """Enhanced document processor with multi-format support"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.supported_formats = {
            'text/plain': self._process_text,
            'application/pdf': self._process_pdf,
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document': self._process_docx,
            'application/msword': self._process_doc
        }
        
        # Legal document patterns for better chunking
        self.legal_section_patterns = [
            r'^\s*(?:SECTION|Section|SEC\.|Sec\.)\s+\d+',
            r'^\s*(?:ARTICLE|Article|ART\.|Art\.)\s+\d+',
            r'^\s*(?:CLAUSE|Clause)\s+\d+',
            r'^\s*\d+\.\s+[A-Z]',  # Numbered sections
            r'^\s*\([a-z]\)\s+',   # Lettered subsections
            r'^\s*WHEREAS\b',      # Contract clauses
            r'^\s*NOW THEREFORE\b',
            r'^\s*IN WITNESS WHEREOF\b'
        ]
    
    def process_document(self, file_content: bytes, filename: str, 
                        content_type: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process document with enhanced capabilities
        
        Args:
            file_content: Raw file bytes
            filename: Original filename
            content_type: MIME type
            metadata: Additional metadata
            
        Returns:
            Dictionary with processed content and enhanced metadata
        """
        try:
            # Determine processing method
            if content_type not in self.supported_formats:
                raise ValueError(f"Unsupported file type: {content_type}")
            
            processor = self.supported_formats[content_type]
            
            # Process document
            result = processor(file_content, filename, metadata)
            
            # Add common enhancements
            result = self._enhance_processing_result(result, filename, content_type)
            
            return result
            
        except Exception as e:
            self.logger.error(f"Error processing document {filename}: {e}")
            raise
    
    def _process_text(self, file_content: bytes, filename: str, 
                     metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Process plain text files"""
        try:
            # Try different encodings
            encodings = ['utf-8', 'latin-1', 'cp1252']
            text_content = None
            
            for encoding in encodings:
                try:
                    text_content = file_content.decode(encoding)
                    break
                except UnicodeDecodeError:
                    continue
            
            if text_content is None:
                raise ValueError("Could not decode text file")
            
            # Clean and normalize text
            text_content = self._clean_text(text_content)
            
            # Extract legal document structure
            sections = self._extract_legal_sections(text_content)
            
            return {
                'text': text_content,
                'sections': sections,
                'page_count': 1,
                'word_count': len(text_content.split()),
                'char_count': len(text_content),
                'encoding_used': encoding
            }
            
        except Exception as e:
            raise ValueError(f"Error processing text file: {e}")
    
    def _process_pdf(self, file_content: bytes, filename: str, 
                    metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Process PDF files with enhanced extraction and encoding handling"""
        if not PDF_AVAILABLE:
            raise ValueError("PDF processing libraries not available")
        
        try:
            text_content = ""
            doc_metadata = {}
            page_count = 0
            extraction_method = "unknown"
            
            try:
                # Use PyMuPDF for better text extraction
                doc = fitz.open(stream=file_content, filetype="pdf")
                page_count = len(doc)
                extraction_method = "pymupdf"
                
                # Extract metadata
                doc_metadata = doc.metadata or {}
                
                # Extract text from all pages with encoding handling
                full_text = []
                for page_num in range(page_count):
                    page = doc[page_num]
                    page_text = page.get_text()
                    
                    # Clean the page text immediately
                    if page_text and page_text.strip():
                        cleaned_page_text = self._clean_text(page_text)
                        if cleaned_page_text.strip():
                            full_text.append(f"[Page {page_num + 1}]\n{cleaned_page_text}")
                
                text_content = "\n\n".join(full_text)
                doc.close()
                
                # If PyMuPDF extraction resulted in mostly garbage, try alternative
                if self._is_text_garbled(text_content):
                    self.logger.warning("PyMuPDF extraction appears garbled, trying alternative method")
                    raise Exception("Text appears garbled, trying fallback")
                
            except Exception as e:
                self.logger.warning(f"PyMuPDF failed or produced garbled text, trying PyPDF2: {e}")
                
                # Fallback to PyPDF2
                import io
                pdf_reader = PyPDF2.PdfReader(io.BytesIO(file_content))
                page_count = len(pdf_reader.pages)
                extraction_method = "pypdf2"
                
                full_text = []
                for page_num, page in enumerate(pdf_reader.pages):
                    page_text = page.extract_text()
                    
                    # Clean the page text immediately
                    if page_text and page_text.strip():
                        cleaned_page_text = self._clean_text(page_text)
                        if cleaned_page_text.strip():
                            full_text.append(f"[Page {page_num + 1}]\n{cleaned_page_text}")
                
                text_content = "\n\n".join(full_text)
                
                # Extract metadata
                if pdf_reader.metadata:
                    doc_metadata = {
                        'pdf_title': str(pdf_reader.metadata.get('/Title', '')),
                        'pdf_author': str(pdf_reader.metadata.get('/Author', '')),
                        'pdf_subject': str(pdf_reader.metadata.get('/Subject', '')),
                        'pdf_creator': str(pdf_reader.metadata.get('/Creator', '')),
                        'pdf_producer': str(pdf_reader.metadata.get('/Producer', '')),
                        'pdf_creation_date': str(pdf_reader.metadata.get('/CreationDate', '')),
                        'pdf_modification_date': str(pdf_reader.metadata.get('/ModDate', ''))
                    }
            
            # Final cleaning and validation
            text_content = self._clean_text(text_content)
            
            # Check if extraction was successful
            if not text_content or len(text_content.strip()) < 10:
                self.logger.warning(f"PDF extraction resulted in minimal text for {filename}")
                # Try one more time with different settings if possible
                if extraction_method == "pypdf2":
                    raise ValueError("PDF text extraction failed - document may be image-based or corrupted")
            
            # Check for still garbled text after cleaning
            if self._is_text_garbled(text_content):
                self.logger.warning(f"Text still appears garbled after cleaning for {filename}")
                # Could implement OCR here as a last resort
                # For now, we'll proceed with a warning
                text_content = f"[WARNING: Text extraction may be incomplete or corrupted]\n\n{text_content}"
            
            # Extract legal sections
            sections = self._extract_legal_sections(text_content)
            
            return {
                'text': text_content,
                'sections': sections,
                'page_count': page_count,
                'word_count': len(text_content.split()),
                'char_count': len(text_content),
                'pdf_metadata': doc_metadata,
                'extraction_method': extraction_method,
                'extraction_quality': 'good' if not self._is_text_garbled(text_content) else 'poor'
            }
            
        except Exception as e:
            raise ValueError(f"Error processing PDF file '{filename}': {e}")
    
    def _is_text_garbled(self, text: str) -> bool:
        """Check if extracted text appears to be garbled or corrupted"""
        if not text or len(text.strip()) < 10:
            return True
        
        # Calculate ratios to detect garbled text
        total_chars = len(text)
        if total_chars == 0:
            return True
        
        # Count different character types
        ascii_chars = sum(1 for c in text if ord(c) < 128)
        letter_chars = sum(1 for c in text if c.isalpha())
        space_chars = sum(1 for c in text if c.isspace())
        
        ascii_ratio = ascii_chars / total_chars
        letter_ratio = letter_chars / total_chars
        space_ratio = space_chars / total_chars
        
        # Text is likely garbled if:
        # - Very low ASCII ratio (< 0.3)
        # - Very low letter ratio (< 0.2) 
        # - Very high space ratio (> 0.8) indicating mostly spaces
        # - Very low space ratio (< 0.05) indicating no word boundaries
        
        if (ascii_ratio < 0.3 or 
            letter_ratio < 0.2 or 
            space_ratio > 0.8 or 
            space_ratio < 0.05):
            return True
        
        # Check for excessive repeated characters (common in garbled text)
        if len(set(text)) < max(5, len(text) * 0.1):
            return True
        
        return False
    
    def _process_docx(self, file_content: bytes, filename: str, 
                     metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Process Word DOCX files"""
        if not DOCX_AVAILABLE and not DOCX2TXT_AVAILABLE:
            raise ValueError("Word document processing libraries not available")
        
        try:
            import io
            text_content = ""
            doc_metadata = {}
            
            try:
                # Try python-docx first for better formatting
                if DOCX_AVAILABLE:
                    doc = DocxDocument(io.BytesIO(file_content))
                    
                    # Extract text from paragraphs
                    paragraphs = []
                    for paragraph in doc.paragraphs:
                        if paragraph.text.strip():
                            paragraphs.append(paragraph.text)
                    
                    text_content = "\n\n".join(paragraphs)
                    
                    # Extract metadata
                    core_props = doc.core_properties
                    doc_metadata = {
                        'title': core_props.title or '',
                        'author': core_props.author or '',
                        'subject': core_props.subject or '',
                        'keywords': core_props.keywords or '',
                        'created': str(core_props.created) if core_props.created else '',
                        'modified': str(core_props.modified) if core_props.modified else '',
                        'last_modified_by': core_props.last_modified_by or ''
                    }
                    
                else:
                    # Fallback to docx2txt
                    text_content = docx2txt.process(io.BytesIO(file_content))
                
            except Exception as e:
                self.logger.warning(f"Advanced DOCX processing failed, using basic extraction: {e}")
                if DOCX2TXT_AVAILABLE:
                    text_content = docx2txt.process(io.BytesIO(file_content))
                else:
                    raise ValueError("No DOCX processing method available")
            
            # Clean and process text
            text_content = self._clean_text(text_content)
            
            # Extract legal sections
            sections = self._extract_legal_sections(text_content)
            
            return {
                'text': text_content,
                'sections': sections,
                'page_count': 1,  # Approximate for DOCX
                'word_count': len(text_content.split()),
                'char_count': len(text_content),
                'docx_metadata': doc_metadata
            }
            
        except Exception as e:
            raise ValueError(f"Error processing DOCX file: {e}")
    
    def _process_doc(self, file_content: bytes, filename: str, 
                    metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Process legacy Word DOC files"""
        # For now, return an error as DOC processing is complex
        # In a full implementation, you'd use libraries like python-docx2txt or antiword
        raise ValueError("Legacy DOC format not yet supported. Please convert to DOCX or PDF.")
    
    def _clean_text(self, text: str) -> str:
        """Clean and normalize text content with robust encoding handling"""
        # Handle None or empty text
        if not text:
            return ""
        
        # Ensure we have a string
        if isinstance(text, bytes):
            # Try different encodings
            for encoding in ['utf-8', 'latin-1', 'cp1252', 'ascii']:
                try:
                    text = text.decode(encoding)
                    break
                except (UnicodeDecodeError, AttributeError):
                    continue
            else:
                # If all encodings fail, use utf-8 with error handling
                text = text.decode('utf-8', errors='replace')
        
        # Normalize Unicode characters (fix encoding issues)
        text = unicodedata.normalize('NFKD', text)
        
        # Remove or replace problematic characters
        # Remove control characters except newlines and tabs
        text = ''.join(char for char in text if ord(char) >= 32 or char in '\n\t')
        
        # Fix common PDF extraction issues
        # Replace non-breaking spaces with regular spaces
        text = text.replace('\u00a0', ' ')
        text = text.replace('\xa0', ' ')
        
        # Fix ligatures and special characters
        ligature_map = {
            'ﬁ': 'fi', 'ﬂ': 'fl', 'ﬀ': 'ff', 'ﬃ': 'ffi', 'ﬄ': 'ffl',
            'ﬆ': 'st', ''': "'", ''': "'", '"': '"', '"': '"',
            '–': '-', '—': '-', '…': '...', '€': 'EUR', '£': 'GBP',
            '°': ' degrees ', '§': 'section', '¶': 'paragraph'
        }
        
        for ligature, replacement in ligature_map.items():
            text = text.replace(ligature, replacement)
        
        # Remove excessive whitespace
        text = re.sub(r'\s+', ' ', text)
        
        # Remove page breaks and form feeds
        text = re.sub(r'[\f\r]', '', text)
        
        # Fix hyphenated words at line breaks
        text = re.sub(r'-\s*\n\s*', '', text)
        
        # Normalize line breaks
        text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)
        
        # Strip leading/trailing whitespace
        text = text.strip()
        
        # Final check for readability
        if text and len(text.split()) > 0:
            # Calculate ratio of ASCII characters to total characters
            ascii_chars = sum(1 for c in text if ord(c) < 128)
            ascii_ratio = ascii_chars / len(text) if text else 0
            
            # If less than 50% ASCII, try additional cleaning
            if ascii_ratio < 0.5:
                # Remove characters that are likely encoding artifacts
                cleaned_chars = []
                for char in text:
                    if (char.isalnum() or 
                        char.isspace() or 
                        char in '.,!?;:()[]{}"\'-/\\@#$%^&*+=<>|`~'):
                        cleaned_chars.append(char)
                    elif ord(char) > 127:
                        # Try to transliterate non-ASCII characters
                        try:
                            ascii_char = unicodedata.normalize('NFKD', char).encode('ascii', 'ignore').decode('ascii')
                            if ascii_char:
                                cleaned_chars.append(ascii_char)
                        except:
                            cleaned_chars.append(' ')  # Replace with space if all else fails
                
                text = ''.join(cleaned_chars)
                # Clean up extra spaces again
                text = re.sub(r'\s+', ' ', text).strip()
        
        return text
    
    def _extract_legal_sections(self, text: str) -> List[Dict[str, Any]]:
        """Extract legal document sections for better chunking"""
        sections = []
        lines = text.split('\n')
        current_section = None
        current_content = []
        
        for line_num, line in enumerate(lines):
            # Check if line matches a legal section pattern
            is_section_header = False
            for pattern in self.legal_section_patterns:
                if re.match(pattern, line, re.IGNORECASE):
                    is_section_header = True
                    break
            
            if is_section_header:
                # Save previous section
                if current_section and current_content:
                    sections.append({
                        'title': current_section,
                        'content': '\n'.join(current_content).strip(),
                        'start_line': sections[-1]['end_line'] if sections else 0,
                        'end_line': line_num
                    })
                
                # Start new section
                current_section = line.strip()
                current_content = []
            else:
                if line.strip():
                    current_content.append(line)
        
        # Add final section
        if current_section and current_content:
            sections.append({
                'title': current_section,
                'content': '\n'.join(current_content).strip(),
                'start_line': sections[-1]['end_line'] if sections else 0,
                'end_line': len(lines)
            })
        
        return sections
    
    def _enhance_processing_result(self, result: Dict[str, Any], 
                                 filename: str, content_type: str) -> Dict[str, Any]:
        """Add common enhancements to processing results"""
        
        # Generate document hash for deduplication
        text_hash = hashlib.md5(result['text'].encode()).hexdigest()
        
        # Detect legal document type
        doc_type = self._detect_legal_document_type(result['text'])
        
        # Extract key legal terms
        legal_terms = self._extract_legal_terms(result['text'])
        
        # Start with enhanced metadata - all simple types for ChromaDB compatibility
        enhanced_metadata = {
            'document_hash': text_hash,
            'filename': filename,
            'content_type': content_type,
            'processed_at': datetime.utcnow().isoformat(),
            'legal_document_type': doc_type,
            'legal_terms': ', '.join(legal_terms) if legal_terms else '',  # Convert list to string
            'processing_version': '4.0',
            # Convert sections to string representation
            'sections_count': len(result.get('sections', [])),
            'sections_titles': ', '.join([s.get('title', '') for s in result.get('sections', [])]) if result.get('sections') else ''
        }
        
        # Handle PDF metadata specifically - flatten nested dictionaries
        if 'pdf_metadata' in result and isinstance(result['pdf_metadata'], dict):
            pdf_meta = result['pdf_metadata']
            for key, value in pdf_meta.items():
                # Ensure all values are simple types
                enhanced_metadata[f'pdf_{key}'] = str(value) if value else ''
            # Remove the nested pdf_metadata
            result.pop('pdf_metadata', None)
        
        # Handle DOCX metadata specifically - flatten nested dictionaries  
        if 'docx_metadata' in result and isinstance(result['docx_metadata'], dict):
            docx_meta = result['docx_metadata']
            for key, value in docx_meta.items():
                # Ensure all values are simple types
                enhanced_metadata[f'docx_{key}'] = str(value) if value else ''
            # Remove the nested docx_metadata
            result.pop('docx_metadata', None)
        
        # Add other simple metadata fields from result
        simple_fields = ['extraction_method', 'extraction_quality', 'page_count', 'word_count', 'char_count', 'encoding_used']
        for field in simple_fields:
            if field in result:
                enhanced_metadata[field] = result[field]
        
        # Update result with flattened metadata
        result.update(enhanced_metadata)
        
        # Remove the original sections list to avoid ChromaDB issues
        result.pop('sections', None)
        
        return result
    
    def _detect_legal_document_type(self, text: str) -> str:
        """Detect the type of legal document"""
        text_lower = text.lower()
        
        # Define document type patterns
        doc_types = {
            'contract': ['agreement', 'contract', 'whereas', 'party', 'consideration'],
            'employment': ['employment', 'employee', 'employer', 'compensation', 'benefits'],
            'lease': ['lease', 'tenant', 'landlord', 'rent', 'premises'],
            'nda': ['non-disclosure', 'confidential', 'proprietary', 'trade secret'],
            'terms_of_service': ['terms of service', 'terms and conditions', 'user agreement'],
            'privacy_policy': ['privacy policy', 'personal information', 'data collection'],
            'license': ['license', 'licensed', 'licensor', 'licensee'],
            'will': ['last will', 'testament', 'executor', 'beneficiary'],
            'power_of_attorney': ['power of attorney', 'attorney-in-fact', 'principal']
        }
        
        # Score each document type
        scores = {}
        for doc_type, keywords in doc_types.items():
            score = sum(1 for keyword in keywords if keyword in text_lower)
            if score > 0:
                scores[doc_type] = score
        
        # Return the highest scoring type or 'general' if no clear match
        if scores:
            return max(scores, key=scores.get)
        return 'general'
    
    def _extract_legal_terms(self, text: str) -> List[str]:
        """Extract important legal terms from the document"""
        # Common legal terms to identify
        legal_terms_patterns = [
            r'\b(?:whereas|therefore|heretofore|hereinafter|notwithstanding)\b',
            r'\b(?:party|parties|agreement|contract|consideration)\b',
            r'\b(?:liability|indemnify|damages|breach|default)\b',
            r'\b(?:termination|expiration|renewal|amendment)\b',
            r'\b(?:confidential|proprietary|intellectual property)\b',
            r'\b(?:jurisdiction|governing law|dispute resolution)\b'
        ]
        
        found_terms = set()
        text_lower = text.lower()
        
        for pattern in legal_terms_patterns:
            matches = re.findall(pattern, text_lower)
            found_terms.update(matches)
        
        return list(found_terms)

    def get_supported_formats(self) -> List[str]:
        """Return list of supported file formats"""
        formats = ['text/plain']
        
        if PDF_AVAILABLE:
            formats.append('application/pdf')
        
        if DOCX_AVAILABLE or DOCX2TXT_AVAILABLE:
            formats.append('application/vnd.openxmlformats-officedocument.wordprocessingml.document')
        
        return formats
    
    def check_dependencies(self) -> Dict[str, bool]:
        """Check which document processing libraries are available"""
        return {
            'pdf_processing': PDF_AVAILABLE,
            'docx_processing': DOCX_AVAILABLE or DOCX2TXT_AVAILABLE,
            'pymupdf': 'fitz' in globals(),
            'pypdf2': 'PyPDF2' in globals(),
            'python_docx': DOCX_AVAILABLE,
            'docx2txt': DOCX2TXT_AVAILABLE
        } 