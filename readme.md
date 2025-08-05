# Enhanced Log Assistant Documentation
## LLM-INCIDENT-ASSISTANT

## Table of Contents
1. [Project Overview](#project-overview)
2. [Architecture](#architecture)
3. [Installation & Setup](#installation--setup)
4. [Configuration](#configuration)
5. [User Management](#user-management)
6. [Database Schema](#database-schema)
7. [Features & Functionality](#features--functionality)
8. [API Integration](#api-integration)
9. [Security Implementation](#security-implementation)
10. [Usage Guide](#usage-guide)
11. [Troubleshooting](#troubleshooting)
12. [Development & Customization](#development--customization)

## Project Overview

The Enhanced Assistant is a secure, multi-tenant web application designed for Operations teams to query and analyze incident data using natural language. The system combines authentication, database management, and AI-powered query processing to provide an intuitive interface for incident management.

### Key Capabilities
- **Natural Language Querying**: Convert plain English questions to SQL queries
- **Multi-Client Data Isolation**: Secure separation of data between different clients
- **Conversational Memory**: Context-aware responses for better user experience
- **Admin Data Management**: Centralized data upload and database administration
- **Dual LLM Architecture**: Specialized models for query generation and conversation


## Architecture

### System Components

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Streamlit     │    │   SQLite         │    │   Ollama        │
│   Frontend      │◄──►│   Database       │    │   LLM Service   │
│                 │    │                  │    │                 │
│ - Authentication│    │ - Incident Data  │    │ - SQL Generator │
│ - Chat Interface│    │ - ClientIsolation│    │ - Chat Response │
│ - Admin Panel   │    │ - Query Execution│    │                 │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

### Technology Stack
- **Frontend**: Streamlit (Python web framework)
- **Database**: SQLite with SQLAlchemy ORM
- **AI/ML**: Ollama (Local LLM hosting)
  - qwen2.5-coder:7b (SQL generation)
  - llama3.2 (Conversational responses)
- **Data Processing**: Pandas, OpenPyXL
- **Security**: Session-based authentication, parameterized queries

## Installation & Setup

### Prerequisites
```
# Python 3.11.9
python --version

# Required system packages
pip install streamlit pandas sqlalchemy sqlite3 requests python-dotenv openpyxl
```

### Ollama Setup
```
# Install Ollama

# Pull required models
ollama pull qwen2.5-coder:7b
ollama pull llama3.2

# Start Ollama service
ollama serve
```

### Project Structure
```
noc-assistant/
├── app.py                 # Demo RAG file
├── csv_db.py              # Demo NL-SQL Query
├── demo.py                # Demo Chatbot (keyword search, No SQL or DB integration)
├── main.py                # Main NOC Chatbot
├── .env                   # Environment configuration (optional)
├── incidents.db           # SQLite database (created automatically)
├── requirements.txt       # Python dependencies
├── README.md              # Project documentation
└── data/                  # data directory
```

### Environment Configuration
Create `.env` file (optional):
```env
OLLAMA_URL=http://localhost:11434/api/generate
SQL_MODEL=qwen2.5-coder:7b
CHAT_MODEL=llama3.2
```

### Running the Application
```bash
streamlit run app.py
```

## Configuration

### User Credentials
Located in `USER_DB` dictionary:
```python
USER_DB = {
    "user1": {"password": "u1123", "client": "User1", "role": "user"},
    "user1": {"password": "u2123", "client": "User2", "role": "user"},
    "admin": {"password": "admin123", "client": "ALL", "role": "admin"},
}
```

### Database Configuration
- **Database File**: `incidents.db`
- **Table Name**: `incidents`
- **Storage**: Local SQLite file
- **Backup**: Manual file copy recommended

### LLM Configuration
- **SQL Generator**: qwen2.5-coder:7b
- **Chat Assistant**: llama3.2
- **Endpoint**: Configurable via environment variables
- **Timeout**: 30 seconds default

## User Management

### User Roles

#### Regular Users (GP/Banglalink)
- **Access**: Client-specific incident data only
- **Permissions**: Query, view, chat about incidents
- **Restrictions**: Cannot upload data, cannot see other clients' data

#### Admin User
- **Access**: All client data (when needed)
- **Permissions**: Upload data, manage database, full system access
- **Responsibilities**: Data maintenance, user support

### Authentication Flow
1. User enters credentials on login page
2. System validates against `USER_DB`
3. Session state established with user context
4. Role-based interface access granted
5. Client filtering applied to all queries

## Database Schema

### Incidents Table Structure
```sql
CREATE TABLE incidents (
    incident_id TEXT,
    incident_title TEXT,
    ticket_id TEXT,
    ticket_title TEXT,
    fault_id TEXT,
    client_name TEXT,          -- CRITICAL: Used for data isolation
    .........
    reason TEXT,               -- Used for comprehensive search
    event_time TEXT,
    ..........
    -- Additional metadata fields...
);
```

### Data Requirements
- **Mandatory Fields**: `client_name` (for isolation)
- **Key Search Fields**: `incident_id`, `ticket_id`
- **Analysis Fields**: `reason`, `problem_category`
- **Temporal Fields**: `event_time`, `clear_time`, `duration`

## Features & Functionality

### 1. Natural Language Query Processing

#### Query Types Supported
- **Specific Incident**: "Show me details about incident 2288441"
- **Ticket Lookup**: "Information about ticket 2025062665"
- **Link Status**: "Status of AFEA5345_XHF345 link"
- **List Queries**: "Show me last 10 incidents"

#### Query Processing Flow
```
User Question → SQL Generator (qwen2.5-coder) → Database Query → Results Analysis (llama3.2) → Response
```

### 2. Conversational Memory System (***work in progress***)

#### Single Incident Context
- **Trigger**: Query returns exactly 1 incident
- **Storage**: Full incident data in session memory
- **Usage**: Subsequent questions use this context
- **Duration**: Until chat cleared or logout

#### Multiple Incidents Summary
- **Trigger**: Query returns multiple incidents
- **Storage**: Summary with key identifiers
- **Display**: Interactive data table
- **Memory**: Limited context for follow-up questions

### 3. Admin Data Management

#### File Upload Process
1. Admin logs in with admin credentials
2. Navigates to Admin Panel in chat interface
3. Selects CSV/Excel file with incident data
4. System validates file format and required columns
5. Data appended to existing database
6. Success confirmation with statistics

#### Supported File Formats
- **CSV**
- **Excel**: .xlsx, .xls formats


### 4. Data Security & Isolation

#### Client Filtering
- All SQL queries automatically include `WHERE client_name = 'CLIENT'`
- Cross-client data access prevented
- Admin can access all clients when needed***

#### Security Measures
- Parameterized SQL queries prevent injection
- Session-based authentication
- Role-based access control
- Input validation and sanitization

## API Integration

### Ollama LLM Service

#### SQL Generation Endpoint
```python
POST http://localhost:11434/api/generate
{
    "model": "qwen2.5-coder:7b",
    "prompt": "SQL_GENERATION_PROMPT",
    "stream": false
}
```

#### Conversation Endpoint
```python
POST http://localhost/api/generate
{
    "model": "llama3.2",
    "prompt": "CONVERSATION_PROMPT", 
    "stream": false
}
```

#### Error Handling (***work in progress***)
- Connection timeout handling
- Graceful degradation on LLM service unavailability
- User-friendly error messages
- Retry logic for transient failures

## Security Implementation

### Authentication Security
- **Password Storage**: Plain text (consider hashing for production)
- **Session Management**: Streamlit session state
- **Timeout**: Automatic on browser close
- **Brute Force Protection**: Not implemented (consider rate limiting)

### Data Security
- **Access Control**: Role and client-based filtering
- **SQL Injection Prevention**: Parameterized queries with SQLAlchemy
- **Data Isolation**: Automatic client filtering in all queries
- **Audit Trail**: Basic logging of database operations

### Recommendations for Production
```python
# Add proper authentication 

# Add rate limiting
from streamlit_extras.add_vertical_space import add_vertical_space
import time

# Add audit logging
import logging
logging.basicConfig(level=logging.INFO)
```

## Usage Guide

### For Regular Users (NOC Engineers)

#### 1. Login Process
1. Open application URL
2. Enter username and password
3. Click Login button
4. Access granted to client-specific interface

#### 2. Querying Incidents
```
Example Queries:
- "Show me incident 2288441"
- "What happened with ticket 2025062665?"
- "List all incidents from yesterday"
- "Find incidents for DSGSDF5464 link"
```

#### 3. Understanding Responses
- **Single Incident**: Detailed conversational response with full context
- **Multiple Incidents**: Data table with optimized columns
- **No Results**: Clear message indicating no matches found
- **Errors**: User-friendly error messages with suggestions

#### 4. Using Conversation Memory
```
Initial Query: "Show me incident 2288441"
Follow-up: "When was it resolved?"
Follow-up: "What was the root cause?"
Follow-up: "Who was responsible for fixing it?"
```

### For Administrators

#### 1. Data Upload Process
1. Login with admin credentials
2. Access Admin Panel section
3. Review current database statistics
4. Upload CSV/Excel file with incident data
5. Verify successful upload and record count

## Troubleshooting

### Common Issues

#### 1. "No incidents found" for specific queries
**Cause**: SQL query too restrictive or data type mismatch
```python
# Debug: Check actual data
def debug_query(search_term):
    query = f"SELECT ticket_id FROM incidents WHERE ticket_id LIKE '%{search_term}%'"
    result = execute_sql_query(query) 
    print(result)
```

#### 2. LLM Service Connection Errors
**Symptoms**: "Error calling LLM" or timeout messages
**Solutions**:
- Verify Ollama service is running: `ollama serve`
- Check network connectivity to LLM endpoint
- Confirm models are downloaded: `ollama list`

#### 3. Database Errors
**Symptoms**: "Database initialization error" or "Query execution error"
**Solutions**:
- Check file permissions for database directory
- Verify SQLite installation
- Ensure database file is not corrupted

#### 4. File Upload Issues
**Symptoms**: "Error processing file" during data upload
**Solutions**:
- Verify file format (CSV/Excel)
- Check for `client_name` column in data
- Ensure file is not empty or corrupted
- Check file encoding (UTF-8 recommended)

### Performance Optimization

#### Database Performance
```python
# Add indexes for frequently queried columns
CREATE INDEX idx_client_name ON incidents(client_name);
CREATE INDEX idx_incident_id ON incidents(incident_id);
CREATE INDEX idx_ticket_id ON incidents(ticket_id);
CREATE INDEX idx_event_time ON incidents(event_time);
```

#### Memory Management
- Clear conversation memory regularly
- Limit query result sizes for large datasets
- Implement pagination for large result sets

### Logging and Monitoring

#### Enable Debug Logging
```python
import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename='noc_assistant.log'
)
```

#### Monitor Key Metrics
- Query response times
- Database size growth
- User session duration
- Error frequencies

## Development & Customization

### Adding New Features


*Last Updated: [27.05.25]*
*Version: 1.0*