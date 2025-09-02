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
        background-color: #FFE6EE;
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

# Input fields
st.markdown('<div class="centered">', unsafe_allow_html=True)
client_id = st.text_input("Client ID")
client_secret = st.text_input("Client Secret", type="password")
year = st.number_input("Year", min_value=1978, max_value=2100, value=2024)
max_rows = st.number_input("Max rows to fetch", min_value=10, max_value=1000, value=50)
st.markdown('</div>', unsafe_allow_html=True)

run = st.button("Run")

# ----------------- Helper Functions -----------------
def safe_xpath(root, xpath_str, namespaces, return_all=False):
    try:
        res = root.xpath(xpath_str, namespaces=namespaces)
        if return_all:
            return res
        return res[0].strip() if res and hasattr(res[0], 'strip') else (res[0] if res else "")
    except:
        return [] if return_all else ""

def fetch_register_data(doc_num, headers):
    data = {"RepName": "", "RepCountry": "", "OpponentName": "", "OppositionFilingDate": "",
            "AppealNr": "", "AppealResult": "", "AppealDate": ""}
    endpoints = {
        "rep": f"https://register.epo.org/api/publication/epodoc/{doc_num}/representatives",
        "opp": f"https://register.epo.org/api/publication/epodoc/{doc_num}/oppositions",
        "appeal": f"https://register.epo.org/api/publication/epodoc/{doc_num}/appeals"
    }
    for key, url in endpoints.items():
        try:
            time.sleep(1)
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code == 200 and resp.content:
                j = resp.json()
                if key == "rep" and j.get("representatives"):
                    r = j["representatives"][0]
                    data["RepName"] = r.get("name", "")
                    data["RepCountry"] = r.get("countryCode", "")
                elif key == "opp" and j.get("oppositions"):
                    o = j["oppositions"][0]
                    data["OpponentName"] = o.get("name", "")
                    data["OppositionFilingDate"] = o.get("dateFiled", "")
                elif key == "appeal" and j.get("appeals"):
                    a = j["appeals"][0]
                    data["AppealNr"] = a.get("number", "")
                    data["AppealResult"] = a.get("result", "")
                    data["AppealDate"] = a.get("resultDate", "")
        except:
            continue
    return data

def extract_biblio_data(doc_num, headers, ns):
    urls = [
        f"https://ops.epo.org/3.2/rest-services/published-data/publication/epodoc/{doc_num}/biblio",
        f"https://ops.epo.org/3.2/rest-services/published-data/publication/docdb/{doc_num}/biblio"
    ]
    for url in urls:
        try:
            time.sleep(1)
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code != 200 or not resp.content:
                continue
            root = etree.fromstring(resp.content)
            pub_date = safe_xpath(root, ".//ex:publication-reference/ex:document-id/ex:date/text()", ns)
            applicant_name = safe_xpath(root, ".//ex:applicant-name/ex:name/text()", ns)
            applicant_country = safe_xpath(root, ".//ex:applicant/ex:addressbook/ex:address/ex:country/text()", ns)
            return pub_date, applicant_name, applicant_country
        except:
            continue
    return "", "", ""

def extract_cpc_data(doc_num, headers, ns):
    urls = [
        f"https://ops.epo.org/3.2/rest-services/published-data/publication/epodoc/{doc_num}/classifications",
        f"https://ops.epo.org/3.2/rest-services/published-data/publication/docdb/{doc_num}/classifications"
    ]
    for url in urls:
        try:
            time.sleep(1)
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code != 200 or not resp.content:
                continue
            root = etree.fromstring(resp.content)
            cpcs = root.xpath("//ex:classification-cpc", namespaces=ns)
            cpc_main = ""
            cpc_full = []
            for c in cpcs:
                code = safe_xpath(c, ".//ex:symbol/text()", ns)
                if code:
                    code_clean = str(code).replace(" ", "").replace("/", "")
                    cpc_full.append(code_clean)
                    if not cpc_main and len(code_clean) >= 4:
                        cpc_main = code_clean[:4]
            return cpc_main, ";".join(cpc_full)
        except:
            continue
    return "", ""

# ----------------- Main Logic -----------------
if run:
    st.success("You got it, now sit back and relax while I cook your CSV!")
    ns = {"ex": "http://www.epo.org/exchange"}
    auth_url = "https://ops.epo.org/3.2/auth/accesstoken"

    # Get OAuth token
    resp = requests.post(auth_url, auth=HTTPBasicAuth(client_id, client_secret),
                         data={"grant_type": "client_credentials"})
    resp.raise_for_status()
    access_token = resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {access_token}"}

    # Search query
    query = f'pd within "{year}0101 {year}1231"'
    search_url = "https://ops.epo.org/3.2/rest-services/published-data/search/biblio"
    batch_size = 10

    # Get first batch to determine total results
    params = {"q": query, "Range": f"1-{batch_size}"}
    search_resp = requests.get(search_url, headers=headers, params=params)
    search_resp.raise_for_status()
    search_root = etree.fromstring(search_resp.content)
    total_results = int(search_root.xpath("string(//ops:biblio-search/@total-result-count)",
                                         namespaces={"ops": "http://ops.epo.org"}))
    total_to_fetch = min(total_results, max_rows)
    total_batches = math.ceil(total_to_fetch / batch_size)

    all_records = []

    for batch_num in range(total_batches):
        start = batch_num * batch_size + 1
        end = min(start + batch_size - 1, total_to_fetch)
        params = {"q": query, "Range": f"{start}-{end}"}
        batch_resp = requests.get(search_url, headers=headers, params=params)
        if batch_resp.status_code != 200:
            continue
        batch_root = etree.fromstring(batch_resp.content)
        documents = batch_root.xpath("//ex:exchange-document", namespaces=ns)

        for doc in documents:
            doc_num = doc.attrib.get("doc-number") or ""
            if not doc_num:
                continue

            pub_date, applicant_name, applicant_country = extract_biblio_data(doc_num, headers, ns)
            cpc_main, cpc_full = extract_cpc_data(doc_num, headers, ns)
            reg_data = fetch_register_data(doc_num, headers)

            record = {
                "DocNumber": doc_num,
                "Publn_date": pub_date,
                "ApplicantFiledName": applicant_name,
                "ApplicantCountry": applicant_country,
                "CPCMain": cpc_main,
                "CPCFull": cpc_full,
                **reg_data
            }
            all_records.append(record)

    if all_records:
        df = pd.DataFrame(all_records)
        st.dataframe(df)
        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button("Download CSV", csv, "epo_patents.csv", "text/csv")
    else:
        st.warning("No records found for this year or credentials.")

