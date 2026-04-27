import streamlit as st
import google.generativeai as genai
import sqlite3
import os
import uuid
from datetime import datetime, date
from PIL import Image  

# --- Configuration & Initialization ---
st.set_page_config(page_title="TruthScan PMO Dashboard", page_icon="🔍", layout="wide")

DB_FILE = "truthscan.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS audit_logs (
            id TEXT PRIMARY KEY,
            filename TEXT,
            timestamp DATETIME,
            risk_status TEXT,
            raw_log TEXT
        )
    ''')
    conn.commit()
    conn.close()

# Initialize DB on load
init_db()

@st.cache_resource
def get_gemini_model():
    return genai.GenerativeModel('gemini-2.5-flash')

# --- Helper Functions ---
def save_audit(filename, risk_status, raw_log):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    audit_id = str(uuid.uuid4())
    timestamp = datetime.now()
    c.execute('''
        INSERT INTO audit_logs (id, filename, timestamp, risk_status, raw_log)
        VALUES (?, ?, ?, ?, ?)
    ''', (audit_id, filename, timestamp, risk_status, raw_log))
    conn.commit()
    conn.close()

def get_today_scans_count():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    today_str = date.today().isoformat() + "%"
    c.execute("SELECT COUNT(*) FROM audit_logs WHERE timestamp LIKE ?", (today_str,))
    count = c.fetchone()[0]
    conn.close()
    return count

def get_audit_history():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT timestamp, filename, risk_status FROM audit_logs ORDER BY timestamp DESC")
    history = c.fetchall()
    conn.close()
    return history

# --- Main UI ---
st.title("🔍 TruthScan PMO Dashboard")
st.subheader("AI Compliance Auditor")

# --- About Section ---
if "show_about" not in st.session_state:
    st.session_state.show_about = False

def toggle_about():
    st.session_state.show_about = not st.session_state.show_about

st.button("ℹ️ About TruthScan", on_click=toggle_about)

if st.session_state.show_about:
    st.info("""
    **What this app does:**
    TruthScan is an automated Regulatory Compliance tool for Project Management Offices (PMOs). It analyzes product packaging for essential verifiable compliance marks.
    
    **How it scans:**
    1. **Upload**: Accepts packaging design images (.jpg, .png).
    2. **Vision Analysis**: Passes the image to a powerful multimodal AI (Gemini 2.5 Flash).
    3. **Evaluation**: The AI acts as a strict EU Compliance Officer. It intentionally ignores superficial aesthetics (like green coloring) and scans specifically for verifiable data such as QR codes, barcodes, or ISO certifications.
    4. **Risk Status**: 
       - 🟢 **LOW RISK**: Necessary compliance data is present.
       - 🔴 **HIGH RISK**: Critical compliance marks are missing.
    5. **Audit Trail**: Saves the raw AI decision log to a secure local database for PMO tracking.
    """)


# Security Requirement: Never hardcode API key.
api_key = os.environ.get("GEMINI_API_KEY")

if not api_key:
    st.error("⚠️ GEMINI_API_KEY environment variable is not set. Please set it to use the application.")
    st.info("How to set on Windows: \n\n`set GEMINI_API_KEY=your_api_key_here` (for current session)\n\nor use `setx GEMINI_API_KEY your_api_key_here` (permanent)")
    st.stop()

# Configure GenAI
genai.configure(api_key=api_key)
model = get_gemini_model()

SYSTEM_PROMPT = """You are an EU compliance officer. Ignore visual aesthetics like green colors or leaves. Search only for verifiable data like QR codes or ISO certifications. 
You must output your response in exactly the following format:
STATUS: [HIGH RISK or LOW RISK]
REASON: [A clear, concise 1-2 sentence explanation of exactly why this picture was classified as high or low risk, specifying which marks were found or missing.]"""

# Sidebar Operations
st.sidebar.title("📊 PMO Audit History")
today_count = get_today_scans_count()
st.sidebar.metric(label="Total Scanned Today", value=today_count)

st.sidebar.markdown("### Past Audits")
history = get_audit_history()

if not history:
    st.sidebar.info("No past audits found.")
else:
    for record in history:
        tstamp_str = str(record[0])
        # Handle string slicing gracefully for cleaner display
        if '.' in tstamp_str:
            tstamp_str = tstamp_str.split('.')[0]
        fname = record[1]
        status = record[2]
        
        icon = "🔴" if status == "HIGH RISK" else "🟢" if status == "LOW RISK" else "⚪"
        st.sidebar.text(f"{icon} {tstamp_str}\n{fname}")


# File Uploader
uploaded_file = st.file_uploader("Upload Product Packaging Image", type=["jpg", "jpeg", "png"])

if uploaded_file is not None:
    # Use container width is newer version config for st.image
    st.image(uploaded_file, caption="Uploaded Packaging", use_container_width=True)
    
    if st.button("Run Compliance Audit"):
        with st.spinner("Analyzing packaging for EU compliance..."):
            try:
                # Load image fully in memory
                image = Image.open(uploaded_file)
                
                # Ensure the model reads image data natively
                response = model.generate_content([SYSTEM_PROMPT, image])
                
                raw_text = response.text
                
                # Display output depending on Risk Status
                risk_status = "UNKNOWN"
                reasoning = "Detailed explanation missing from AI output. See raw log for details."
                
                # Safely extract reasoning
                if "REASON:" in raw_text.upper():
                    reason_index = raw_text.upper().find("REASON:") + len("REASON:")
                    reasoning = raw_text[reason_index:].strip()

                if "HIGH RISK" in raw_text.upper():
                    risk_status = "HIGH RISK"
                    st.error(f"🚨 **{risk_status}**: Potential compliance violation detected.")
                    st.warning(f"**Explanation:**\n{reasoning}")
                elif "LOW RISK" in raw_text.upper():
                    risk_status = "LOW RISK"
                    st.success(f"✅ **{risk_status}**: Verifiable compliance data detected.")
                    st.info(f"**Explanation:**\n{reasoning}")
                else:
                    st.warning("⚠️ Could not definitively determine RISK STATUS from model output.")
                
                # Save details to Local DB
                save_audit(uploaded_file.name, risk_status, raw_text)
                
                # Expandable log widget
                with st.expander("Show Raw Audit Log"):
                    st.markdown(raw_text)
                    
            except Exception as e:
                st.error(f"An error occurred during analysis: {str(e)}")
                try:
                    models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
                    st.info(f"Your API key supports the following models:\n" + "\n".join(f"- {m}" for m in models))
                except Exception as m_e:
                    st.error(f"Could not fetch models list: {str(m_e)}")
