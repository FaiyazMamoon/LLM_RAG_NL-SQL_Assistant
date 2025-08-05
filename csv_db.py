import streamlit as st
import pandas as pd
import sqlite3
import requests
from sqlalchemy import create_engine

# Initialize session state for persistence
if "query_result" not in st.session_state:
    st.session_state.query_result = None
if "generated_sql" not in st.session_state:
    st.session_state.generated_sql = None
if "show_summarization" not in st.session_state:
    st.session_state.show_summarization = False  # Controls summarization button visibility
if "summary" not in st.session_state:
    st.session_state.summary = None  # Stores the generated summary

def create_database(csv_file):
    try:
        df = pd.read_csv(csv_file, dtype=str, low_memory=False)

        if df.empty:
            raise ValueError("Uploaded CSV file is empty. Please upload a valid file.")

        engine = create_engine("sqlite:///data.db", echo=False)
        df.to_sql("incidents", con=engine, if_exists="append", index=False)
        
        return engine
    except Exception as e:
        print(f"Error loading CSV: {e}")
        return None

def query_database(query):
    conn = sqlite3.connect("data.db")
    result = pd.read_sql_query(query, conn)
    conn.close()
    return result

SYSTEM_PROMPT = """
You are an AI assistant that converts natural language questions into SQL queries for an SQLite database.
Analyze the database schema and generate a valid SQL query.
Ensure that the query is correctly structured and retrieves the desired information.
Return ONLY the SQL query.DO NOT RETURN ANYTHING ELSE! Do not include any explanation or formatting, just the raw SQL. DO NOT RETURN YOUR THINKING PROCESS.
Database schema: 
[incident_id, incident_title, ticket_id, ticket_title, fault_id, client_name, link_name_nttn, link_name_gateway, link_id, LH, capacity_nttn, capacity_gateway, uni_nni, issue_type, client_priority, link_type, problem_category, problem_source, reason, event_time, escalation_time, clear_time, client_side_impact, provider_side_impact, remarks, responsible_concern, responsible_field_team, fault_status, created_time, task_comments, client_comments, provider, task_resolutions, subcenter, region, district, vendor, duration, last_om_comment_id, last_om_end_time, last_om_end_time_db, ticket_initiator_id, ticket_closer_id, fault_closer_id, sms_time, force_majeure, vlan_id, assigned_dept_names, number_of_occurance]
## STRICT OUTPUT RULES ##
- **DO NOT** include explanations, formatting, or prefixes.
- **DO NOT** wrap the query inside ```sql``` or '''sql''' blocks.
- **DO NOT** prepend text like "Generated query:", "Here is your query:", or any other commentary.  
- The output must start **directly** with `SELECT`
## IMPORTANT INSTRUCTIONS ##
- If the user asks about a specific problem type (e.g., fire, theft, power outage), **do not rely only on the `problem_category` column**.
- Also check the `reason` column for relevant terms using **`LOWER(reason) LIKE '%keyword%'`**.
- Automatically infer relevant keywords. Example:
  - For "fire incidents," search for **'fire', 'burn', 'smoke', 'flames'** in the `reason` column.
  - For "cable cut issues," search for **'cable cut', 'fiber cut', 'line break'**.
  - For "power failure," search for **'power outage', 'voltage drop', 'electric failure'**.
- Ensure the query retrieves all relevant data, even if the user does not explicitly mention technical terms.

Context: {context}
Question: {question}
"""

SYSTEM_PROMPT_2 = """You are an AI assistant that generates analysis reports based on the provided tabular data.
The report should be structured consistently every time. 

Report Structure:
1. **Summary:** Provide a brief summary of the data.
2. **Key Insights:** Highlight any important findings or trends in the data.
3. **Main Causes or Reasons:** If applicable, identify key causes or reasons related to the events described in the data.
4. **Recommendations:** Provide any actionable insights or recommendations based on the data.
5. **Conclusion:** Wrap up the report with a brief conclusion.

Please ensure the following:
- Include the **user's original query** (prompt) for context, but do not consider it as instruction for generating the report itself.
- Do not use the **user's original query** (prompt) for instruction for summary. Only use it as context about the data you are summarizing.
- Focus on the data provided and generate the report based on it.
- Avoid adding unnecessary details or explanations. Stick to the structure.
Context: {context}
Prompt: {prompt}
Data: {data}

Please generate the analysis report in the format outlined above."""

OLLAMA_URL = "http://192.168.5.201:11434/api/generate"

def call_llm(context, prompt):
    payload = {
        "model": "qwen2.5-coder:7b",
        "prompt": SYSTEM_PROMPT.format(context=context, question=prompt),
        "stream": False,
    }
    response = requests.post(OLLAMA_URL, json=payload)
    if response.status_code == 200:
        return response.json().get("response", "Error: No response from LLM")
    else:
        return f"Error: {response.status_code} - {response.text}"

def sum_llm(context, data, prompt):
    payload = {
        "model": "llama3.2",
        "prompt": SYSTEM_PROMPT_2.format(context=context, prompt=prompt, data=data),
        "stream": False,
    }
    response = requests.post(OLLAMA_URL, json=payload)
    if response.status_code == 200:
        return response.json().get("response", "Error: No response from LLM")
    else:
        return f"Error: {response.status_code} - {response.text}"
    
def prepare_data_for_summarization(df):

    original_columns = list(df.columns)
    original_shape = df.shape

    key_columns = [
        'client_name', 'link_name_nttn', 
        'reason', 'escalation_time', 'subcenter', 
        'district', 'event_time', 'clear_time', 'duration'
    ]
    
    if len(df.columns) <= 5:
        return df.to_csv(index=False)
    
    # If the query result includes many columns, filter to key columns
    filtered_df = df.copy()
    
    # Keep only the key columns that exist in the result
    columns_to_keep = [col for col in key_columns if col in df.columns]
    
    # If no key columns are present, take the first 5-10 columns
    if not columns_to_keep:
        columns_to_keep = df.columns[:min(10, len(df.columns))]
        
    # Get filtered dataframe
    filtered_df = df[columns_to_keep]

    final_columns = list(filtered_df.columns)
    final_shape = filtered_df.shape
    
    # Log the transformation
    st.sidebar.write(f"Original data: {original_shape[0]} rows × {original_shape[1]} columns")
    st.sidebar.write(f"Original columns: {', '.join(original_columns)}")
    st.sidebar.write(f"Filtered data: {final_shape[0]} rows × {final_shape[1]} columns")
    st.sidebar.write(f"Filtered columns: {', '.join(final_columns)}")

    
    return filtered_df.to_csv(index=False)

# Streamlit UI
st.set_page_config(page_title="CSV Data Query LLM", layout="wide")

with st.sidebar:
    st.sidebar.header("📑 Upload CSV File")
    uploaded_file = st.sidebar.file_uploader("Upload CSV", type=["csv"], accept_multiple_files=False)
    process = st.button("⚡ Process CSV")    

    if uploaded_file and process:
        engine = create_database(uploaded_file)
        st.sidebar.success("CSV file loaded successfully!")

st.header("🔎 Query Your Data Using Natural Language")
prompt = st.text_input("Enter your question:")
ask = st.button("Generate SQL & Query Data")

if ask and prompt:
    generated_sql = call_llm("Table: incidents", prompt)
    st.session_state.generated_sql = generated_sql  # Store SQL query in session state
    st.subheader("Generated SQL Query")
    st.code(generated_sql, language="sql")
    
    try:
        result_df = query_database(generated_sql)
        st.session_state.query_result = result_df  # Store results in session state
        st.session_state.show_summarization = True  # Make summarization button visible
        st.session_state.summary = None  # Reset summary when new query is made
    except Exception as e:
        st.error(f"Error executing query: {e}")

# Always show query results if available
if st.session_state.query_result is not None:
    st.subheader("Query Result")
    st.dataframe(st.session_state.query_result)

    # Show summarization button only if data is retrieved and summary is not yet generated
    if st.session_state.show_summarization:
        summarize = st.button("Summarize Data Insights")

        # if summarize:
        #     st.session_state.show_summarization = False  # Hide button after clicking
        #     data_text = st.session_state.query_result.head(100).to_csv(index=False)  # Limit to first 10 rows
        #     summary = sum_llm("Table: incidents", prompt, data_text)
        #     st.session_state.summary = summary  # Store summary in session state

        if summarize:
            st.session_state.show_summarization = False  # Hide button after clicking            
            data_text = prepare_data_for_summarization(st.session_state.query_result)            
            summary = sum_llm("Table: incidents", prompt, data_text)
            st.session_state.summary = summary  # Store summary in session state

# Show summary below the table after it's generated
if st.session_state.summary:
    st.subheader("Summarry Insights")
    st.text_area("Generated Summary:", st.session_state.summary, height=700)
