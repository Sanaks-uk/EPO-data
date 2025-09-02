import streamlit as st

import streamlit as st

st.markdown(
    """
    <style>
    /* Page background */
    .stApp {
        background-color: #FFEAF0;
    }

    /* Sidebar background (if you have one) */
    [data-testid="stSidebar"] {
        background-color: #ffeaf0;
    }
    </style>
    """,
    unsafe_allow_html=True
)




import pandas as pd
import requests
from requests.auth import HTTPBasicAuth
from lxml import etree
import time
import math

# ===== 1. PAGE CONFIG =====
st.set_page_config(
    page_title="EPO Patent Extractor",
    page_icon="📄",
    layout="wide",
)

# ===== 2. CUSTOM CSS FOR LIGHT PINK BACKGROUND =====
st.markdown(
    """
    <style>
    body {
        background-color: #ffe6f0;
    }
    .stButton>button {
        background-color: #ff99cc;
        color: white;
        font-weight: bold;
    }
    </style>
    """,
    unsafe_allow_html=True
)

st.title("📄 EPO Patent & Register Extractor")
st.markdown("Enter your OPS credentials, year, and max rows, then hit *Run* to get your CSV.")

# ===== 3. USER INPUTS =====
client_id = st.text_input("Client ID", type="password")
client_secret = st.text_input("Client Secret", type="password")
year = st.number_input("Year", min_value=1978, max_value=2100, value=2024)
max_rows = st.number_input("Max rows to fetch", min_value=1, max_value=10000, value=50)

# ===== 4. RUN BUTTON =====
if st.button("Run"):
    st.info("✓ You got it, now sit back and relax while I cook your CSV...")
    
    try:
        # ===== 5. GET ACCESS TOKEN =====
        auth_url = "https://ops.epo.org/3.2/auth/accesstoken"
        resp = requests.post(auth_url, auth=HTTPBasicAuth(client_id, client_secret),
                             data={"grant_type": "client_credentials"})
        resp.raise_for_status()
        access_token = resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {access_token}"}
        st.success("Access token obtained!")

        # ===== 6. SEARCH PATENTS =====
        ns = {
            "ops": "http://ops.epo.org",
            "ex": "http://www.epo.org/exchange",
            "epo": "http://www.epo.org/exchange",
            "xlink": "http://www.w3.org/1999/xlink"
        }
        search_url = "https://ops.epo.org/3.2/rest-services/published-data/search/biblio"
        query = f'pd within "{year}0101 {year}1231"'
        batch_size = 10

        params = {"q": query, "Range": f"1-{batch_size}"}
        search_resp = requests.get(search_url, headers=headers, params=params)
        search_resp.raise_for_status()
        search_root = etree.fromstring(search_resp.content)
        total_results = int(search_root.xpath("string(//ops:biblio-search/@total-result-count)", namespaces=ns))
        st.info(f"Total patents found: {total_results}")

        # ===== 7. FETCH DATA =====
        all_records = []
        total_to_fetch = min(total_results, max_rows)
        total_batches = math.ceil(total_to_fetch / batch_size)
        delay = 2

        for batch_num in range(total_batches):
            start = batch_num * batch_size + 1
            end = min(start + batch_size - 1, total_to_fetch)
            st.write(f"Fetching batch {batch_num+1}/{total_batches} ({start}-{end})...")
            
            if batch_num == 0:
                batch_root = search_root
            else:
                params = {"q": query, "Range": f"{start}-{end}"}
                batch_resp = requests.get(search_url, headers=headers, params=params)
                if batch_resp.status_code != 200:
                    st.warning(f"Batch failed: {batch_resp.status_code}")
                    continue
                batch_root = etree.fromstring(batch_resp.content)

            documents = batch_root.xpath("//ex:exchange-document", namespaces=ns)
            for doc in documents:
                if len(all_records) >= max_rows:
                    break
                doc_num = doc.attrib.get("doc-number", "")
                pub_date = doc.xpath(".//ex:publication-reference/ex:document-id/ex:date/text()", namespaces=ns)
                applicant = doc.xpath(".//ex:applicant-name/ex:name/text()", namespaces=ns)
                record = {
                    "DocNumber": doc_num,
                    "PubDate": pub_date[0] if pub_date else "",
                    "Applicant": applicant[0] if applicant else "",
                }
                all_records.append(record)
            time.sleep(delay)

        # ===== 8. SAVE TO CSV =====
        if all_records:
            df = pd.DataFrame(all_records)
            filename = f"epo_patents_{year}.csv"
            df.to_csv(filename, index=False)
            st.success(f"✓ CSV ready: {filename}")
            st.download_button(
                "Download CSV",
                data=df.to_csv(index=False),
                file_name=filename,
                mime="text/csv"
            )
        else:
            st.warning("No records collected.")

    except Exception as e:
        st.error(f"An error occurred: {e}")
