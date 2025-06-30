#!/usr/bin/env python3
"""
Analytics Module - Phase 4 Local Legal AI
Provides usage analytics, query performance metrics, and user activity tracking
"""

import json
import logging
import sqlite3
import time
from collections import defaultdict, Counter
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
import numpy as np
from dataclasses import dataclass
import os

@dataclass
class QueryMetrics:
    """Data class for query performance metrics."""
    query_id: str
    query_text: str
    timestamp: datetime
    processing_time: float
    similarity_scores: List[float]
    documents_retrieved: int
    user_feedback: Optional[float] = None
    user_id: Optional[str] = None

@dataclass
class DocumentMetrics:
    """Data class for document analytics."""
    document_id: str
    upload_timestamp: datetime
    file_size: int
    chunks_created: int
    processing_time: float
    query_count: int = 0
    avg_similarity_score: float = 0.0
    document_type: str = "unknown"
    legal_complexity: float = 0.0

class AnalyticsManager:
    """
    Comprehensive analytics manager for Local Legal AI system.
    
    Features:
    - Usage analytics and trends
    - Query performance monitoring
    - Document similarity analysis
    - User activity tracking
    - Performance optimization insights
    - System health monitoring
    """
    
    def __init__(self, db_path: str = "analytics.db"):
        self.db_path = db_path
        self.logger = logging.getLogger(__name__)
        self.init_database()
        
        # In-memory caches for performance
        self.query_cache = {}
        self.document_cache = {}
        self.performance_cache = {}
        
        # Analytics configuration
        self.retention_days = 365  # Keep analytics for 1 year
        self.similarity_threshold = 0.7
        
        self.logger.info("Analytics Manager initialized")
    
    def init_database(self):
        """Initialize the analytics database with required tables."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Query analytics table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS query_analytics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    query_id TEXT UNIQUE NOT NULL,
                    query_text TEXT NOT NULL,
                    timestamp DATETIME NOT NULL,
                    processing_time REAL NOT NULL,
                    documents_retrieved INTEGER NOT NULL,
                    avg_similarity_score REAL,
                    max_similarity_score REAL,
                    user_id TEXT,
                    user_feedback REAL,
                    session_id TEXT,
                    query_type TEXT DEFAULT 'general',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Document analytics table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS document_analytics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    document_id TEXT UNIQUE NOT NULL,
                    filename TEXT NOT NULL,
                    upload_timestamp DATETIME NOT NULL,
                    file_size INTEGER NOT NULL,
                    chunks_created INTEGER NOT NULL,
                    processing_time REAL NOT NULL,
                    document_type TEXT DEFAULT 'unknown',
                    legal_complexity REAL DEFAULT 0.0,
                    query_count INTEGER DEFAULT 0,
                    last_queried DATETIME,
                    avg_similarity_score REAL DEFAULT 0.0,
                    total_similarity_score REAL DEFAULT 0.0,
                    uploader_id TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # User activity table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_activity (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    activity_type TEXT NOT NULL,
                    activity_data TEXT,
                    timestamp DATETIME NOT NULL,
                    session_id TEXT,
                    ip_address TEXT,
                    user_agent TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # System performance table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS system_performance (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME NOT NULL,
                    cpu_usage REAL,
                    memory_usage REAL,
                    active_connections INTEGER,
                    query_throughput REAL,
                    avg_response_time REAL,
                    error_rate REAL DEFAULT 0.0,
                    storage_usage REAL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Document similarity table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS document_similarity (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    doc1_id TEXT NOT NULL,
                    doc2_id TEXT NOT NULL,
                    similarity_score REAL NOT NULL,
                    calculated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(doc1_id, doc2_id)
                )
            """)
            
            # Create indexes for better performance
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_query_timestamp ON query_analytics(timestamp)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_doc_upload_time ON document_analytics(upload_timestamp)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_activity_time ON user_activity(timestamp)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_system_perf_time ON system_performance(timestamp)")
            
            conn.commit()
            self.logger.info("Analytics database initialized successfully")
    
    def log_query(self, query_metrics: QueryMetrics) -> bool:
        """Log query analytics data."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                avg_similarity = np.mean(query_metrics.similarity_scores) if query_metrics.similarity_scores else 0.0
                max_similarity = max(query_metrics.similarity_scores) if query_metrics.similarity_scores else 0.0
                
                cursor.execute("""
                    INSERT OR REPLACE INTO query_analytics 
                    (query_id, query_text, timestamp, processing_time, documents_retrieved,
                     avg_similarity_score, max_similarity_score, user_id, user_feedback)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    query_metrics.query_id,
                    query_metrics.query_text,
                    query_metrics.timestamp,
                    query_metrics.processing_time,
                    query_metrics.documents_retrieved,
                    avg_similarity,
                    max_similarity,
                    query_metrics.user_id,
                    query_metrics.user_feedback
                ))
                
                conn.commit()
                
                # Update document query counts
                self._update_document_query_stats(query_metrics.similarity_scores, cursor)
                conn.commit()
                
                return True
                
        except Exception as e:
            self.logger.error(f"Failed to log query analytics: {e}")
            return False
    
    def log_document_upload(self, document_metrics: DocumentMetrics) -> bool:
        """Log document upload analytics."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    INSERT OR REPLACE INTO document_analytics 
                    (document_id, filename, upload_timestamp, file_size, chunks_created,
                     processing_time, document_type, legal_complexity)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    document_metrics.document_id,
                    document_metrics.document_id,  # Using document_id as filename for now
                    document_metrics.upload_timestamp,
                    document_metrics.file_size,
                    document_metrics.chunks_created,
                    document_metrics.processing_time,
                    document_metrics.document_type,
                    document_metrics.legal_complexity
                ))
                
                conn.commit()
                return True
                
        except Exception as e:
            self.logger.error(f"Failed to log document analytics: {e}")
            return False
    
    def log_user_activity(self, user_id: str, activity_type: str, 
                         activity_data: Dict = None, session_id: str = None) -> bool:
        """Log user activity."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    INSERT INTO user_activity 
                    (user_id, activity_type, activity_data, timestamp, session_id)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    user_id,
                    activity_type,
                    json.dumps(activity_data) if activity_data else None,
                    datetime.now(),
                    session_id
                ))
                
                conn.commit()
                return True
                
        except Exception as e:
            self.logger.error(f"Failed to log user activity: {e}")
            return False
    
    def log_system_performance(self, performance_data: Dict[str, float]) -> bool:
        """Log system performance metrics."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    INSERT INTO system_performance 
                    (timestamp, cpu_usage, memory_usage, active_connections,
                     query_throughput, avg_response_time, error_rate, storage_usage)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    datetime.now(),
                    performance_data.get('cpu_usage', 0.0),
                    performance_data.get('memory_usage', 0.0),
                    performance_data.get('active_connections', 0),
                    performance_data.get('query_throughput', 0.0),
                    performance_data.get('avg_response_time', 0.0),
                    performance_data.get('error_rate', 0.0),
                    performance_data.get('storage_usage', 0.0)
                ))
                
                conn.commit()
                return True
                
        except Exception as e:
            self.logger.error(f"Failed to log system performance: {e}")
            return False
    
    def get_usage_analytics(self, days: int = 30) -> Dict[str, Any]:
        """Get comprehensive usage analytics for the specified period."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                start_date = datetime.now() - timedelta(days=days)
                
                # Query statistics
                cursor.execute("""
                    SELECT COUNT(*) as total_queries,
                           AVG(processing_time) as avg_processing_time,
                           AVG(avg_similarity_score) as avg_similarity,
                           COUNT(DISTINCT user_id) as unique_users
                    FROM query_analytics 
                    WHERE timestamp >= ?
                """, (start_date,))
                
                query_stats = cursor.fetchone()
                
                # Document statistics
                cursor.execute("""
                    SELECT COUNT(*) as total_documents,
                           AVG(file_size) as avg_file_size,
                           AVG(chunks_created) as avg_chunks,
                           AVG(processing_time) as avg_processing_time,
                           AVG(legal_complexity) as avg_complexity
                    FROM document_analytics 
                    WHERE upload_timestamp >= ?
                """, (start_date,))
                
                doc_stats = cursor.fetchone()
                
                # Daily activity trends
                cursor.execute("""
                    SELECT DATE(timestamp) as date, COUNT(*) as query_count
                    FROM query_analytics 
                    WHERE timestamp >= ?
                    GROUP BY DATE(timestamp)
                    ORDER BY date
                """, (start_date,))
                
                daily_trends = cursor.fetchall()
                
                # Top query types
                cursor.execute("""
                    SELECT query_type, COUNT(*) as count
                    FROM query_analytics 
                    WHERE timestamp >= ?
                    GROUP BY query_type
                    ORDER BY count DESC
                    LIMIT 10
                """, (start_date,))
                
                query_types = cursor.fetchall()
                
                # Performance trends
                cursor.execute("""
                    SELECT AVG(avg_response_time) as avg_response,
                           AVG(error_rate) as avg_error_rate,
                           AVG(query_throughput) as avg_throughput
                    FROM system_performance 
                    WHERE timestamp >= ?
                """, (start_date,))
                
                perf_stats = cursor.fetchone()
                
                return {
                    "period_days": days,
                    "query_analytics": {
                        "total_queries": query_stats[0] or 0,
                        "avg_processing_time": round(query_stats[1] or 0, 3),
                        "avg_similarity_score": round(query_stats[2] or 0, 3),
                        "unique_users": query_stats[3] or 0
                    },
                    "document_analytics": {
                        "total_documents": doc_stats[0] or 0,
                        "avg_file_size": round(doc_stats[1] or 0, 0),
                        "avg_chunks_per_doc": round(doc_stats[2] or 0, 1),
                        "avg_processing_time": round(doc_stats[3] or 0, 3),
                        "avg_legal_complexity": round(doc_stats[4] or 0, 3)
                    },
                    "daily_trends": [{"date": row[0], "queries": row[1]} for row in daily_trends],
                    "top_query_types": [{"type": row[0], "count": row[1]} for row in query_types],
                    "performance_metrics": {
                        "avg_response_time": round(perf_stats[0] or 0, 3),
                        "avg_error_rate": round(perf_stats[1] or 0, 3),
                        "avg_throughput": round(perf_stats[2] or 0, 2)
                    }
                }
                
        except Exception as e:
            self.logger.error(f"Failed to get usage analytics: {e}")
            return {}
    
    def get_document_similarity_analysis(self, document_id: str = None) -> Dict[str, Any]:
        """Get document similarity analysis."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                if document_id:
                    # Get similarities for specific document
                    cursor.execute("""
                        SELECT doc2_id, similarity_score 
                        FROM document_similarity 
                        WHERE doc1_id = ?
                        ORDER BY similarity_score DESC
                        LIMIT 10
                    """, (document_id,))
                    
                    similarities = cursor.fetchall()
                    
                    return {
                        "document_id": document_id,
                        "similar_documents": [
                            {"document_id": row[0], "similarity": round(row[1], 3)}
                            for row in similarities
                        ]
                    }
                else:
                    # Get overall similarity statistics
                    cursor.execute("""
                        SELECT AVG(similarity_score) as avg_similarity,
                               MAX(similarity_score) as max_similarity,
                               COUNT(*) as total_comparisons
                        FROM document_similarity
                    """)
                    
                    stats = cursor.fetchone()
                    
                    # Get document clusters (high similarity groups)
                    cursor.execute("""
                        SELECT doc1_id, doc2_id, similarity_score 
                        FROM document_similarity 
                        WHERE similarity_score > ?
                        ORDER BY similarity_score DESC
                    """, (self.similarity_threshold,))
                    
                    clusters = cursor.fetchall()
                    
                    return {
                        "overall_stats": {
                            "avg_similarity": round(stats[0] or 0, 3),
                            "max_similarity": round(stats[1] or 0, 3),
                            "total_comparisons": stats[2] or 0
                        },
                        "similar_document_pairs": [
                            {
                                "doc1": row[0],
                                "doc2": row[1],
                                "similarity": round(row[2], 3)
                            }
                            for row in clusters[:20]  # Top 20 similar pairs
                        ]
                    }
                    
        except Exception as e:
            self.logger.error(f"Failed to get similarity analysis: {e}")
            return {}
    
    def get_query_performance_insights(self) -> Dict[str, Any]:
        """Get query performance insights and optimization suggestions."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Query performance distribution
                cursor.execute("""
                    SELECT 
                        CASE 
                            WHEN processing_time < 0.1 THEN 'very_fast'
                            WHEN processing_time < 0.5 THEN 'fast'
                            WHEN processing_time < 1.0 THEN 'moderate'
                            WHEN processing_time < 2.0 THEN 'slow'
                            ELSE 'very_slow'
                        END as performance_category,
                        COUNT(*) as count,
                        AVG(processing_time) as avg_time
                    FROM query_analytics
                    GROUP BY performance_category
                """)
                
                performance_dist = cursor.fetchall()
                
                # Slowest queries for optimization
                cursor.execute("""
                    SELECT query_text, processing_time, avg_similarity_score
                    FROM query_analytics
                    ORDER BY processing_time DESC
                    LIMIT 10
                """)
                
                slow_queries = cursor.fetchall()
                
                # Similarity score distribution
                cursor.execute("""
                    SELECT 
                        CASE 
                            WHEN avg_similarity_score >= 0.8 THEN 'excellent'
                            WHEN avg_similarity_score >= 0.6 THEN 'good'
                            WHEN avg_similarity_score >= 0.4 THEN 'fair'
                            WHEN avg_similarity_score >= 0.2 THEN 'poor'
                            ELSE 'very_poor'
                        END as quality_category,
                        COUNT(*) as count
                    FROM query_analytics
                    WHERE avg_similarity_score IS NOT NULL
                    GROUP BY quality_category
                """)
                
                quality_dist = cursor.fetchall()
                
                # Generate optimization suggestions
                suggestions = self._generate_optimization_suggestions(
                    performance_dist, slow_queries, quality_dist
                )
                
                return {
                    "performance_distribution": [
                        {
                            "category": row[0],
                            "count": row[1],
                            "avg_time": round(row[2], 3)
                        }
                        for row in performance_dist
                    ],
                    "slowest_queries": [
                        {
                            "query": row[0][:100] + "..." if len(row[0]) > 100 else row[0],
                            "processing_time": round(row[1], 3),
                            "similarity_score": round(row[2] or 0, 3)
                        }
                        for row in slow_queries
                    ],
                    "quality_distribution": [
                        {"category": row[0], "count": row[1]}
                        for row in quality_dist
                    ],
                    "optimization_suggestions": suggestions
                }
                
        except Exception as e:
            self.logger.error(f"Failed to get performance insights: {e}")
            return {}
    
    def get_user_activity_summary(self, days: int = 30) -> Dict[str, Any]:
        """Get user activity summary and patterns."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                start_date = datetime.now() - timedelta(days=days)
                
                # Active users
                cursor.execute("""
                    SELECT COUNT(DISTINCT user_id) as active_users
                    FROM user_activity
                    WHERE timestamp >= ?
                """, (start_date,))
                
                active_users = cursor.fetchone()[0] or 0
                
                # Activity types distribution
                cursor.execute("""
                    SELECT activity_type, COUNT(*) as count
                    FROM user_activity
                    WHERE timestamp >= ?
                    GROUP BY activity_type
                    ORDER BY count DESC
                """, (start_date,))
                
                activity_types = cursor.fetchall()
                
                # Daily activity patterns
                cursor.execute("""
                    SELECT 
                        strftime('%H', timestamp) as hour,
                        COUNT(*) as activity_count
                    FROM user_activity
                    WHERE timestamp >= ?
                    GROUP BY strftime('%H', timestamp)
                    ORDER BY hour
                """, (start_date,))
                
                hourly_patterns = cursor.fetchall()
                
                # Most active users
                cursor.execute("""
                    SELECT user_id, COUNT(*) as activity_count
                    FROM user_activity
                    WHERE timestamp >= ?
                    GROUP BY user_id
                    ORDER BY activity_count DESC
                    LIMIT 10
                """, (start_date,))
                
                top_users = cursor.fetchall()
                
                return {
                    "period_days": days,
                    "active_users": active_users,
                    "activity_types": [
                        {"type": row[0], "count": row[1]}
                        for row in activity_types
                    ],
                    "hourly_patterns": [
                        {"hour": f"{int(row[0]):02d}:00", "activity_count": row[1]}
                        for row in hourly_patterns
                    ],
                    "top_users": [
                        {"user_id": row[0], "activity_count": row[1]}
                        for row in top_users
                    ]
                }
                
        except Exception as e:
            self.logger.error(f"Failed to get user activity summary: {e}")
            return {}
    
    def _update_document_query_stats(self, similarity_scores: List[float], cursor):
        """Update document query statistics based on similarity scores."""
        # This is a simplified implementation
        # In a real system, you'd track which documents were actually retrieved
        if similarity_scores:
            avg_score = np.mean(similarity_scores)
            # Update the most recently uploaded documents (simplified approach)
            cursor.execute("""
                UPDATE document_analytics 
                SET query_count = query_count + 1,
                    total_similarity_score = total_similarity_score + ?,
                    avg_similarity_score = total_similarity_score / query_count,
                    last_queried = ?
                WHERE id IN (
                    SELECT id FROM document_analytics 
                    ORDER BY upload_timestamp DESC 
                    LIMIT 3
                )
            """, (avg_score, datetime.now()))
    
    def _generate_optimization_suggestions(self, performance_dist, slow_queries, quality_dist) -> List[str]:
        """Generate optimization suggestions based on performance data."""
        suggestions = []
        
        # Analyze performance distribution
        total_queries = sum(row[1] for row in performance_dist)
        slow_queries_count = sum(row[1] for row in performance_dist if row[0] in ['slow', 'very_slow'])
        
        if total_queries > 0:
            slow_percentage = (slow_queries_count / total_queries) * 100
            
            if slow_percentage > 20:
                suggestions.append("Consider optimizing query processing - over 20% of queries are slow")
            
            if slow_percentage > 10:
                suggestions.append("Review document chunking strategy to improve retrieval speed")
        
        # Analyze quality distribution
        total_quality_queries = sum(row[1] for row in quality_dist)
        poor_quality_count = sum(row[1] for row in quality_dist if row[0] in ['poor', 'very_poor'])
        
        if total_quality_queries > 0:
            poor_percentage = (poor_quality_count / total_quality_queries) * 100
            
            if poor_percentage > 30:
                suggestions.append("Improve document preprocessing to enhance similarity matching")
            
            if poor_percentage > 15:
                suggestions.append("Consider expanding legal vocabulary for better semantic understanding")
        
        # Analyze slow queries
        if len(slow_queries) > 5:
            suggestions.append("Implement query caching for frequently asked questions")
            suggestions.append("Consider pre-computing embeddings for common query patterns")
        
        # Default suggestions
        if not suggestions:
            suggestions.append("System performance is good - consider adding more documents for better coverage")
            suggestions.append("Monitor user feedback to identify areas for improvement")
        
        return suggestions
    
    def export_analytics_report(self, format: str = "json") -> Dict[str, Any]:
        """Export comprehensive analytics report."""
        try:
            report = {
                "generated_at": datetime.now().isoformat(),
                "report_type": "comprehensive_analytics",
                "usage_analytics": self.get_usage_analytics(30),
                "performance_insights": self.get_query_performance_insights(),
                "similarity_analysis": self.get_document_similarity_analysis(),
                "user_activity": self.get_user_activity_summary(30),
                "system_health": self._get_system_health_summary()
            }
            
            if format == "json":
                return report
            else:
                # Could implement other formats (CSV, PDF) in the future
                return report
                
        except Exception as e:
            self.logger.error(f"Failed to export analytics report: {e}")
            return {}
    
    def _get_system_health_summary(self) -> Dict[str, Any]:
        """Get current system health summary."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Recent system performance
                cursor.execute("""
                    SELECT AVG(cpu_usage), AVG(memory_usage), AVG(error_rate)
                    FROM system_performance
                    WHERE timestamp >= ?
                """, (datetime.now() - timedelta(hours=24),))
                
                perf_data = cursor.fetchone()
                
                # Database size
                cursor.execute("SELECT page_count * page_size as size FROM pragma_page_count(), pragma_page_size()")
                db_size = cursor.fetchone()[0] if cursor.fetchone() else 0
                
                return {
                    "avg_cpu_usage": round(perf_data[0] or 0, 2),
                    "avg_memory_usage": round(perf_data[1] or 0, 2),
                    "avg_error_rate": round(perf_data[2] or 0, 4),
                    "database_size_mb": round(db_size / (1024 * 1024), 2),
                    "status": "healthy" if (perf_data[0] or 0) < 80 and (perf_data[2] or 0) < 0.05 else "warning"
                }
                
        except Exception as e:
            self.logger.error(f"Failed to get system health: {e}")
            return {"status": "unknown", "error": str(e)}
    
    def cleanup_old_data(self, days: int = None):
        """Clean up old analytics data beyond retention period."""
        if days is None:
            days = self.retention_days
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cutoff_date = datetime.now() - timedelta(days=days)
                
                # Clean up old records
                tables = ['query_analytics', 'user_activity', 'system_performance']
                deleted_counts = {}
                
                for table in tables:
                    cursor.execute(f"DELETE FROM {table} WHERE timestamp < ?", (cutoff_date,))
                    deleted_counts[table] = cursor.rowcount
                
                conn.commit()
                
                self.logger.info(f"Cleaned up old analytics data: {deleted_counts}")
                return deleted_counts
                
        except Exception as e:
            self.logger.error(f"Failed to cleanup old data: {e}")
            return {}

# Global analytics manager instance
analytics_manager = AnalyticsManager() 