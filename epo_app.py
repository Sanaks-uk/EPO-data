import streamlit as st
import pandas as pd
import requests
from requests.auth import HTTPBasicAuth
from lxml import etree
import time
import math

# ===== 1️⃣ Page config and CSS styling =====
st.set_page_config(page_title="EPO Patent Data", layout="centered")
st.markdown(
    """
    <style>
    /* Page background */
    .stApp {
        background-color: #FFE3EB;
    }
    /* Center container */
    .centered-container {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
    }
    /* Custom Run button color */
    div.stButton > button:first-child {
        background-color: #FF69B4;
        color: white;
        height: 3em;
        width: 150px;
        font-size: 16px;
        border-radius: 10px;
    }
    </style>
    """,
    unsafe_allow_html=True
)

st.title("📄 EPO Patent & Register Data")
st.markdown("Fill in your credentials and parameters below:")

# ===== 2️⃣ Centered input fields using columns =====
col1, col2, col3 = st.columns([1,2,1])
with col2:
    client_id = st.text_input("Client ID", key="client_id")
    client_secret = st.text_input("Client Secret", type="password", key="client_secret")
    year = st.number_input("Year", min_value=1900, max_value=2100, value=2024, key="year")
    max_rows = st.number_input("Max Rows", min_value=1, value=50, key="max_rows")

# ===== 3️⃣ Run button =====
with col2:
    run_button = st.button("Run")

if run_button:
    st.success("You got it, now sit back and relax while I cook your CSV")

    # ===== 4️⃣ Example placeholder for processing logic =====
    # Here you would add your EPO fetching logic
    # For demonstration, we'll just create a dummy dataframe
    dummy_data = {
        "DocNumber": [f"EP{1000+i}" for i in range(max_rows)],
        "Applicant": ["Sample Applicant"]*max_rows,
        "PubDate": [f"{year}-01-01"]*max_rows
    }
    df = pd.DataFrame(dummy_data)

    st.markdown("### Sample Results")
    st.dataframe(df)

    # ===== 5️⃣ Option to download CSV =====
    csv = df.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="Download CSV",
        data=csv,
        file_name=f"epo_patents_{year}.csv",
        mime='text/csv'
    )
