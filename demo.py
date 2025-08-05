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

# Set up error handling
try:
    # Load environment variables
    load_dotenv()
except Exception as e:
    pass  # Continue even if .env file doesn't exist

# Dummy user credentials and client mapping
USER_DB = {
    "gp_user": {"password": "gp123", "client": "GP"},
    "bl_user": {"password": "bl123", "client": "Banglalink"},
}

# System prompt template
SYSTEM_PROMPT = """You are a helpful NOC assistant answering network incident queries.
Current date: {current_date}

Client: {client}

Incident data:
{incident_data}

User question: {question}

Provide a clear, concise answer based on the incident data provided. 
If the user asks a question that cannot be answered with the provided data,
respond with "I don't have that information in my current dataset."
"""

# Define API endpoint and model
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://192.168.5.201:11434/api/generate")
MODEL = os.getenv("MODEL", "llama3.2")

# Sample data as a fallback
SAMPLE_DATA = """
"incident_id","incident_title","ticket_id","ticket_title","fault_id","client_name","link_name_nttn","link_name_gateway","link_id","LH","capacity_nttn","capacity_gateway","uni_nni","issue_type","client_priority","link_type","problem_category","problem_source","reason","event_time","escalation_time","clear_time","client_side_impact","provider_side_impact","remarks","responsible_concern","responsible_field_team","fault_status","created_time","task_comments","client_comments","provider","task_resolutions","subcenter","region","district","vendor","duration","last_om_comment_id","last_om_end_time","last_om_end_time_db","ticket_initiator_id","ticket_closer_id","fault_closer_id","sms_time","force_majeure","vlan_id","assigned_dept_names","number_of_occurance"
"2288441","Auto Ticket: MBKAM042HTR01_MBMKM1 to MBKAM049HTR01_MBADA3 is down","2288940","Auto Ticket:[NEW_UNMS]-: MBKAM042HTR01_MBMKM1 to MBKAM049HTR01_MBADA3 is down","2393955","GP","MBKAM049HTR01_MBADA3 to MBKAM042HTR01_MBMKM1","","NA","","10000","NA","NNI","NTTN","VVIP","OH","Link Down","NMS","Others : Client end Power Outage/Ckt Breaker Trip/Others","2024-07-01 00:01:00","2024-07-01 00:05:34","2024-07-01 00:18:23","TBD","MBKAM042HTR01_MBMKM1 to MBKAM049HTR01_MBADA3","oss_bot(NOC)[2024-07-01 00:05:34] : MBKAM042HTR01_MBMKM1 to MBKAM049HTR01_MBADA3 is down","NA","12","closed","2024-07-01 00:05:34","[oss_bot][NOC][2024-07-01 00:05:34][escalated] :MBKAM042HTR01_MBMKM1 to MBKAM049HTR01_MBADA3 is down||[munshi.sarfaraj][Regional Implementation & Operations 2][2024-07-01 00:18:12][RTI] : base site power issue at client end..link is up now.please check and close tt.||[zahid.iqbal][NOC][2024-07-01 01:30:52][Closed] :base site power issue at client end..link is up now.please check and close tt.","[oss_bot][10][2024-07-01 00:05:34]: MBKAM042HTR01_MBMKM1 to MBKAM049HTR01_MBADA3 is down","258","Others: Client end Power outage/Ckt Breaker trip/Others->Others: Data Provided || ","Sylhet","Regional Implementation & Operations 2","Sylhet","Green Surma","0.2897","munshi.sarfaraj","2024-07-01 00:18:23","2024-07-01 00:18:12","oss_bot","zahid.iqbal","zahid.iqbal","NO SMS","false","0","","Cannot Provide"
"""

# Function to load incident data - with dependency checking
def load_incident_data(file=None):
    try:
        if file is not None:
            if file.name.endswith(('.xlsx', '.xls')):
                try:
                    # Try to import openpyxl first
                    
                    df = pd.read_excel(file)
                except ImportError:
                    st.error("""
                    Error!
                    """)
                    # Fall back to sample data
                    df = pd.read_csv(io.StringIO(SAMPLE_DATA.strip()))
            else:
                df = pd.read_csv(file)
        else:
            # Use sample data
            df = pd.read_csv(io.StringIO(SAMPLE_DATA.strip()))
        
        return df
    except Exception as e:
        st.error(f"Error loading file: {str(e)}")
        st.info("Using sample data as fallback.")
        # Return sample data as fallback
        return pd.read_csv(io.StringIO(SAMPLE_DATA.strip()))

# Find data relevant to a query
def find_relevant_data(query, df, client=None):
    """Extract relevant data from dataframe based on query and enforce client isolation"""

    # Always filter by client
    if client:
        df_filtered = df[df['client_name'] == client]
    else:
        df_filtered = df

    # If no data after filtering, return message
    if len(df_filtered) == 0:
        return f"No incident data available for {client}."

    # Check if the query contains any incident/ticket ID from other clients
    all_incident_ids = set(df['incident_id'].astype(str).values)
    allowed_incident_ids = set(df_filtered['incident_id'].astype(str).values)
    for id_val in all_incident_ids - allowed_incident_ids:
        if id_val in query:
            return "You do not have access to this incident."

    all_ticket_ids = set(df['ticket_id'].astype(str).values)
    allowed_ticket_ids = set(df_filtered['ticket_id'].astype(str).values)
    for id_val in all_ticket_ids - allowed_ticket_ids:
        if id_val in query:
            return "You do not have access to this ticket."

    # # Check if the query contains any link name from other clients
    # all_link_nttn = set(str(val).lower() for val in df['link_name_nttn'].dropna().values if str(val).lower() != 'nan')
    # allowed_link_nttn = set(str(val).lower() for val in df_filtered['link_name_nttn'].dropna().values if str(val).lower() != 'nan')
    # for link in all_link_nttn - allowed_link_nttn:
    #     if link in query.lower():
    #         return "You do not have access to this link."

    # all_link_gateway = set(str(val).lower() for val in df['link_name_gateway'].dropna().values if str(val).lower() != 'nan')
    # allowed_link_gateway = set(str(val).lower() for val in df_filtered['link_name_gateway'].dropna().values if str(val).lower() != 'nan')
    # for link in all_link_gateway - allowed_link_gateway:
    #     if link in query.lower():
    #         return "You do not have access to this link."

    # Search for incident ID in query (within allowed client)
    if "incident" in query.lower() and any(str(id_val) in query for id_fval in allowed_incident_ids):
        for id_val in allowed_incident_ids:
            if id_val in query:
                incident_data = df_filtered[df_filtered['incident_id'].astype(str) == id_val]
                if not incident_data.empty:
                    return incident_data.to_dict('records')[0]

    # Search for ticket ID in query (within allowed client)
    if "ticket" in query.lower() and any(str(id_val) in query for id_val in allowed_ticket_ids):
        for id_val in allowed_ticket_ids:
            if id_val in query:
                ticket_data = df_filtered[df_filtered['ticket_id'].astype(str) == id_val]
                if not ticket_data.empty:
                    return ticket_data.to_dict('records')[0]

    # Search for link name in query (within allowed client)
    for idx, row in df_filtered.iterrows():
        link_nttn = str(row.get('link_name_nttn', ''))
        link_gateway = str(row.get('link_name_gateway', ''))

        if link_nttn and link_nttn != 'nan' and link_nttn.lower() in query.lower():
            return row.to_dict()

        if link_gateway and link_gateway != 'nan' and link_gateway.lower() in query.lower():
            return row.to_dict()

    # Return summary of available data if no specific match found
    return {
        "summary": f"Data available for {len(df_filtered)} incidents",
        "columns": list(df_filtered.columns),
        "sample": df_filtered.head(1).to_dict('records')
    }

# Function to call the LLM
def call_llm(client, question, incident_data):
    """Call the LLM with context and question"""
    
    # Format the incident data as a string
    if isinstance(incident_data, dict):
        data_str = json.dumps(incident_data, indent=2)
    else:
        data_str = str(incident_data)
    
    # Prepare the payload
    payload = {
        "model": MODEL,
        "prompt": SYSTEM_PROMPT.format(
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
            st.error(f"Error calling LLM: {response.status_code}")
            return "I'm having trouble accessing my knowledge base right now."
    except Exception as e:
        st.error(f"Exception when calling LLM: {str(e)}")
        return "I'm currently unable to process your request due to a connection issue."

# Login page
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
            st.session_state.messages = []
            st.rerun()
        else:
            st.error("Invalid username or password")

# Chat interface
def chat_interface():
    """Display chat interface"""
    st.title(f"NOC Assistant - {st.session_state.client}")
    st.write(f"Welcome, {st.session_state.username}!")
    
    # Display chat messages
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
    
    # Chat input
    if prompt := st.chat_input("Ask about incidents..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        
        with st.chat_message("user"):
            st.markdown(prompt)
        
        # Load data if not already in session state
        if "incident_df" not in st.session_state:
            st.session_state.incident_df = load_incident_data()
        
        try:
            # Find relevant data for the query
            relevant_data = find_relevant_data(
                prompt, 
                st.session_state.incident_df, 
                st.session_state.client
            )
            
            # Call LLM with the data
            with st.spinner("Thinking..."):
                response = call_llm(
                    st.session_state.client,
                    prompt,
                    relevant_data
                )
        except Exception as e:
            st.error(f"Error processing query: {str(e)}")
            response = "I encountered an error processing your request. Please try a different question or check the error message."
        
        with st.chat_message("assistant"):
            st.markdown(response)
        
        st.session_state.messages.append({"role": "assistant", "content": response})
    
    # Sidebar with controls
    with st.sidebar:
        st.title("Options")
        
        # Upload data option
        st.header("Data Source")
        uploaded_file = st.file_uploader("Upload incident data", type=["xlsx", "csv", "xls"])
        
        if uploaded_file:
            try:
                with st.spinner("Loading data..."):
                    df = load_incident_data(uploaded_file)
                    records_count = len(df)
                    st.session_state.incident_df = df
                    st.success(f"✅ Loaded {records_count} records")
            except Exception as e:
                st.error(f"Error: {str(e)}")
                st.info("Make sure you have installed openpyxl if using Excel files: `pip install openpyxl`")
        
        # Chat controls
        st.header("Chat Controls")
        if st.button("Clear Chat"):
            st.session_state.messages = []
            st.rerun()
        
        if st.button("Logout"):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.session_state.authenticated = False
            st.rerun()

# Main function
def main():
    """Main app"""
    st.set_page_config(page_title="NOC Assistant", page_icon="📡")
    
    # Check for required dependencies
    try:
        import requests
        import pandas as pd
    except ImportError as e:
        st.error(f"Missing required dependency: {e}")
        return
    
    # Initialize session state
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    
    if "messages" not in st.session_state:
        st.session_state.messages = []
    
    # Show installation instructions for first run
    if "first_run" not in st.session_state:
        st.session_state.first_run = True
        
    
    # Make sure we have incident data
    try:
        if "incident_df" not in st.session_state:
            st.session_state.incident_df = load_incident_data()
    except Exception as e:
        st.error(f"Error initializing data: {str(e)}")
        st.session_state.incident_df = pd.read_csv(io.StringIO(SAMPLE_DATA.strip()))
    

    if st.session_state.authenticated:
        chat_interface()
    else:
        login_page()

if __name__ == "__main__":
    main()