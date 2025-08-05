import streamlit as st
import requests
from datetime import datetime
import uuid
import os
from dotenv import load_dotenv
import pandas as pd
import io
import json
import traceback
import openpyxl
import sqlite3
from sqlalchemy import create_engine, text
import hashlib

# Set up error handling
try:
    # Load environment variables
    load_dotenv()
except Exception as e:
    pass  # Continue even if .env file doesn't exist

# Enhanced user credentials with admin user
USER_DB = {
    "gp_user": {"password": "gp123", "client": "GP", "role": "user"},
    "bl_user": {"password": "bl123", "client": "Banglalink", "role": "user"},
    "admin": {"password": "admin123", "client": "ALL", "role": "admin"},
}

# Database configuration
DATABASE_PATH = "noc_incidents.db"

# System prompts
SQL_GENERATION_PROMPT = """
You are an AI assistant that converts natural language questions into SQL queries for an SQLite database.
Analyze the database schema and generate a valid SQL query with proper client filtering.
Return ONLY the SQL query. DO NOT RETURN ANYTHING ELSE! Do not include any explanation or formatting, just the raw SQL.

Database schema: 
[incident_id, incident_title, ticket_id, ticket_title, fault_id, client_name, link_name_nttn, link_name_gateway, link_id, LH, capacity_nttn, capacity_gateway, uni_nni, issue_type, client_priority, link_type, problem_category, problem_source, reason, event_time, escalation_time, clear_time, client_side_impact, provider_side_impact, remarks, responsible_concern, responsible_field_team, fault_status, created_time, task_comments, client_comments, provider, task_resolutions, subcenter, region, district, vendor, duration, last_om_comment_id, last_om_end_time, last_om_end_time_db, ticket_initiator_id, ticket_closer_id, fault_closer_id, sms_time, force_majeure, vlan_id, assigned_dept_names, number_of_occurance]

STRICT OUTPUT RULES:
- DO NOT include explanations, formatting, or prefixes
- DO NOT wrap the query inside ```sql``` blocks
- The output must start directly with SELECT
- ALWAYS include WHERE client_name = '{client}' for data isolation


Current client: {client}
Question: {question}
"""

CONVERSATION_PROMPT = """You are a helpful NOC assistant answering network incident queries.
Current date: {current_date}
Client: {client}

You have access to specific incident data in your conversation memory:
{incident_data}

User question: {question}

Provide a clear, concise answer based on the incident data in your memory. 
Focus on the specific incident details, timeline, resolution steps, and any relevant technical information.
If the user asks about information not available in the current incident data, 
respond with "I don't have that specific information for this incident."
"""

# Define API endpoint and models
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://192.168.5.201:11434/api/generate")
SQL_MODEL = os.getenv("SQL_MODEL", "qwen2.5-coder:7b")
CHAT_MODEL = os.getenv("CHAT_MODEL", "llama3.2")

def init_database():
    """Initialize the database with proper schema"""
    try:
        engine = create_engine(f"sqlite:///{DATABASE_PATH}", echo=False)
        
        # Check if incidents table exists
        with engine.connect() as conn:
            result = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='incidents'"))
            if not result.fetchone():
                st.info("Database initialized. Please upload incident data as admin.")
        
        return engine
    except Exception as e:
        st.error(f"Database initialization error: {str(e)}")
        return None

def create_or_append_data(file, engine):
    """Create or append data to database"""
    try:
        if file.name.endswith(('.xlsx', '.xls')):
            df = pd.read_excel(file, dtype=str)
        else:
            df = pd.read_csv(file, dtype=str)
        
        if df.empty:
            raise ValueError("Uploaded file is empty.")
        
        # Ensure client_name column exists for data isolation
        if 'client_name' not in df.columns:
            raise ValueError("File must contain 'client_name' column for data isolation.")
        
        # Append to database
        df.to_sql("incidents", con=engine, if_exists="append", index=False)
        
        return len(df), df['client_name'].unique().tolist()
    except Exception as e:
        raise Exception(f"Error processing file: {str(e)}")

def execute_sql_query(query, client):
    """Execute SQL query with client filtering and security measures"""
    try:
        # Additional security: ensure client filtering is present
        query_lower = query.lower()
        if "where" not in query_lower or client.lower() not in query_lower:
            if client != "ALL":  # Admin can see all data
                # Add client filtering if missing (security failsafe)
                if "where" in query_lower:
                    query += f" AND client_name = '{client}'"
                else:
                    query += f" WHERE client_name = '{client}'"
        
        engine = create_engine(f"sqlite:///{DATABASE_PATH}", echo=False)
        with engine.connect() as conn:
            result = pd.read_sql_query(text(query), conn)
        
        return result
    except Exception as e:
        raise Exception(f"Query execution error: {str(e)}")

def call_sql_llm(client, question):
    """Call LLM for SQL generation"""
    payload = {
        "model": SQL_MODEL,
        "prompt": SQL_GENERATION_PROMPT.format(
            client=client,
            question=question
        ),
        "stream": False
    }
    
    try:
        response = requests.post(OLLAMA_URL, json=payload)
        if response.status_code == 200:
            return response.json().get("response", "").strip()
        else:
            return None
    except Exception as e:
        st.error(f"SQL LLM error: {str(e)}")
        return None

def call_chat_llm(client, question, incident_data):
    """Call LLM for conversational responses"""
    if isinstance(incident_data, dict):
        data_str = json.dumps(incident_data, indent=2)
    else:
        data_str = str(incident_data)
    
    payload = {
        "model": CHAT_MODEL,
        "prompt": CONVERSATION_PROMPT.format(
            client=client,
            question=question,
            current_date=datetime.now().strftime("%Y-%m-%d"),
            incident_data=data_str
        ),
        "stream": False
    }
    
    try:
        response = requests.post(OLLAMA_URL, json=payload)
        if response.status_code == 200:
            return response.json().get("response", "I couldn't process your request.")
        else:
            return "I'm having trouble accessing my knowledge base right now."
    except Exception as e:
        st.error(f"Chat LLM error: {str(e)}")
        return "I'm currently unable to process your request due to a connection issue."

def is_single_incident_query(query_result):
    """Determine if query result is a single incident"""
    return len(query_result) == 1

def prepare_summary_for_memory(df):
    """Prepare a summary of multiple incidents for conversational memory"""
    if len(df) == 0:
        return "No incidents found."
    
    summary_data = {
        "total_incidents": len(df),
        "clients": df.get('client_name', pd.Series()).unique().tolist(),
        "incident_ids": df.get('incident_id', pd.Series()).head(10).tolist(),  # First 10 IDs
        "ticket_ids": df.get('ticket_id', pd.Series()).head(10).tolist(),
        "link_names": df.get('link_name_nttn', pd.Series()).dropna().head(10).tolist(),
        "recent_events": df.get('event_time', pd.Series()).head(5).tolist()
    }
    
    return summary_data

def prepare_data_for_display(df):
    """Optimize data for display in dataframe"""
    if len(df.columns) <= 10:
        return df
    
    # Key columns for display
    key_columns = [
        'incident_id', 'ticket_id', 'client_name', 'link_name_nttn', 
        'issue_type', 'problem_category', 'fault_status', 'event_time', 
        'clear_time', 'duration', 'region', 'district'
    ]
    
    # Keep only existing key columns
    columns_to_show = [col for col in key_columns if col in df.columns]
    
    # If no key columns exist, show first 10 columns
    if not columns_to_show:
        columns_to_show = df.columns[:10].tolist()
    
    return df[columns_to_show]

def login_page():
    """Display login form"""
    st.title("NOC Assistant Login")
    
    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submit_button = st.form_submit_button("Login")
    
    if submit_button:
        user = USER_DB.get(username)
        if user and user["password"] == password:
            st.session_state.authenticated = True
            st.session_state.username = username
            st.session_state.client = user["client"]
            st.session_state.role = user["role"]
            st.session_state.messages = []
            st.session_state.conversation_memory = None
            st.rerun()
        else:
            st.error("Invalid username or password")

def admin_interface():
    """Admin interface for data management"""
    st.header("Admin Panel - Data Management")
    
    # Database status
    try:
        engine = create_engine(f"sqlite:///{DATABASE_PATH}", echo=False)
        with engine.connect() as conn:
            result = conn.execute(text("SELECT COUNT(*) as count, COUNT(DISTINCT client_name) as clients FROM incidents"))
            stats = result.fetchone()
            st.info(f"Database contains {stats[0]} incidents from {stats[1]} clients")
    except:
        st.warning("Database not initialized or empty")
    
    # File upload
    st.subheader("Upload Incident Data")
    uploaded_file = st.file_uploader(
        "Upload CSV or Excel file", 
        type=["csv", "xlsx", "xls"],
        help="File must contain 'client_name' column for proper data isolation"
    )
    
    if uploaded_file and st.button("Process and Append Data"):
        try:
            engine = init_database()
            if engine:
                with st.spinner("Processing file..."):
                    record_count, clients = create_or_append_data(uploaded_file, engine)
                    st.success(f"✅ Successfully added {record_count} records for clients: {', '.join(clients)}")
        except Exception as e:
            st.error(f"Error: {str(e)}")

def chat_interface():
    """Main chat interface"""
    if st.session_state.role == "admin":
        admin_interface()
        st.divider()
    
    st.title(f"NOC Assistant - {st.session_state.client}")
    st.write(f"Welcome, {st.session_state.username}!")
    
    # Display chat messages
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            if message.get("type") == "dataframe":
                st.dataframe(message["content"], use_container_width=True)
            else:
                st.markdown(message["content"])
    
    # Chat input
    if prompt := st.chat_input("Ask about incidents..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        
        with st.chat_message("user"):
            st.markdown(prompt)
        
        try:
            with st.spinner("Processing your query..."):
                # Generate SQL query
                sql_query = call_sql_llm(st.session_state.client, prompt)
                # Show the generated SQL query in the sidebar for debugging
                st.sidebar.subheader("Generated SQL Query")
                st.sidebar.code(sql_query, language="sql")

                
                if sql_query:
                    # Execute query
                    query_result = execute_sql_query(sql_query, st.session_state.client)
                    
                    if len(query_result) == 0:
                        response = "No incidents found matching your query."
                        st.session_state.messages.append({"role": "assistant", "content": response})
                    
                    elif is_single_incident_query(query_result):
                        # Single incident - store in conversation memory and use chat LLM
                        incident_data = query_result.iloc[0].to_dict()
                        st.session_state.conversation_memory = incident_data
                        
                        response = call_chat_llm(st.session_state.client, prompt, incident_data)
                        st.session_state.messages.append({"role": "assistant", "content": response})
                    
                    else:
                        # Multiple incidents - show table and store summary in memory
                        display_df = prepare_data_for_display(query_result)
                        summary_data = prepare_summary_for_memory(query_result)
                        st.session_state.conversation_memory = summary_data
                        
                        response = f"Found {len(query_result)} incidents matching your query:"
                        st.session_state.messages.append({"role": "assistant", "content": response})
                        st.session_state.messages.append({
                            "role": "assistant", 
                            "content": display_df, 
                            "type": "dataframe"
                        })
                else:
                    response = "I couldn't understand your query. Please try rephrasing your question."
                    st.session_state.messages.append({"role": "assistant", "content": response})
        
        except Exception as e:
            st.error(f"Error processing query: {str(e)}")
            response = "I encountered an error processing your request. Please try a different question."
            st.session_state.messages.append({"role": "assistant", "content": response})
        
        # Display new messages
        for message in st.session_state.messages[-2:]:  # Show last 2 messages (user + assistant)
            if message["role"] == "assistant":
                with st.chat_message("assistant"):
                    if message.get("type") == "dataframe":
                        st.dataframe(message["content"], use_container_width=True)
                    else:
                        st.markdown(message["content"])
    
    # Sidebar controls
    with st.sidebar:
        st.title("Options")
        
        # Memory status
        if st.session_state.conversation_memory:
            st.header("Conversation Context")
            if isinstance(st.session_state.conversation_memory, dict):
                if "total_incidents" in st.session_state.conversation_memory:
                    st.info(f"📊 {st.session_state.conversation_memory['total_incidents']} incidents in memory")
                else:
                    st.info("🔍 Single incident in memory")
            else:
                st.info("💾 Context available")
        
        # Chat controls
        st.header("Chat Controls")
        if st.button("Clear Chat"):
            st.session_state.messages = []
            st.session_state.conversation_memory = None
            st.rerun()
        
        if st.button("Logout"):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.session_state.authenticated = False
            st.rerun()

def main():
    """Main application"""
    st.set_page_config(page_title="NOC Assistant", page_icon="📡", layout="wide")
    
    # Check dependencies
    try:
        import requests
        import pandas as pd
        import sqlite3
        from sqlalchemy import create_engine
    except ImportError as e:
        st.error(f"Missing required dependency: {e}")
        return
    
    # Initialize session state
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    
    if "messages" not in st.session_state:
        st.session_state.messages = []
    
    if "conversation_memory" not in st.session_state:
        st.session_state.conversation_memory = None
    
    # Initialize database
    if st.session_state.authenticated:
        init_database()
    
    # Route to appropriate interface
    if st.session_state.authenticated:
        chat_interface()
    else:
        login_page()

if __name__ == "__main__":
    main()