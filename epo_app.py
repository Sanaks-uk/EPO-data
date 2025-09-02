import streamlit as st
import requests
from requests.auth import HTTPBasicAuth
from lxml import etree
import pandas as pd
import time
import math

# ===== Streamlit page setup =====
st.set_page_config(page_title="EPO Patents Data Extractor", layout="centered")
st.title("EPO Patents Data Extractor")
st.markdown("Enter your credentials and parameters to fetch patent data.")

# ===== Centered input fields =====
with st.container():
    col1, col2, col3, col4 = st.columns([1,2,2,1])
    with col2:
        client_id = st.text_input("Client ID")
        client_secret = st.text_input("Client Secret", type="password")
        year = st.number_input("Year", min_value=1978, max_value=2100, value=2024)
        max_records = st.number_input("Max records", min_value=1, max_value=10000, value=10)

run_button = st.button("Run")

# ===== Namespaces =====
ns = {
    "ops": "http://ops.epo.org",
    "ex": "http://www.epo.org/exchange",
    "epo": "http://www.epo.org/exchange",
    "xlink": "http://www.w3.org/1999/xlink"
}

# ===== Helper functions =====
def safe_xpath(root, xpath_str, namespaces, return_all=False):
    try:
        res = root.xpath(xpath_str, namespaces=namespaces)
        if return_all:
            return res
        return res[0].strip() if res and hasattr(res[0], 'strip') else (res[0] if res else "")
    except:
        return [] if return_all else ""

def fetch_register_data(doc_num, headers):
    data = {
        "RepName": "", "RepCountry": "",
        "OpponentName": "", "OppositionFilingDate": "",
        "AppealNr": "", "AppealResult": "", "AppealDate": ""
    }
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

def extract_biblio_data(doc_num, headers):
    urls = [
        f"https://ops.epo.org/3.2/rest-services/published-data/publication/epodoc/{doc_num}/biblio",
        f"https://ops.epo.org/3.2/rest-services/published-data/publication/docdb/{doc_num}/biblio"
    ]
    for url in urls:
        try:
            time.sleep(1)
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code == 200 and resp.content:
                root = etree.fromstring(resp.content)
                pub_date = safe_xpath(root, ".//ex:date/text()", ns)
                applicant_name = safe_xpath(root, ".//ex:applicant-name/ex:name/text()", ns)
                applicant_country = safe_xpath(root, ".//ex:residence/ex:country/text()", ns)
                return pub_date, applicant_name, applicant_country
        except:
            continue
    return "", "", ""

def extract_cpc_data(doc_num, headers):
    urls = [
        f"https://ops.epo.org/3.2/rest-services/published-data/publication/epodoc/{doc_num}/classifications",
        f"https://ops.epo.org/3.2/rest-services/published-data/publication/docdb/{doc_num}/classifications"
    ]
    for url in urls:
        try:
            time.sleep(1)
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code == 200 and resp.content:
                root = etree.fromstring(resp.content)
                cpcs = root.xpath("//ex:classification-cpc/ex:symbol/text()", namespaces=ns)
                cpcs_clean = [c.replace(" ","").replace("/","") for c in cpcs]
                cpc_main = cpcs_clean[0][:4] if cpcs_clean else ""
                return cpc_main, ";".join(cpcs_clean)
        except:
            continue
    return "", ""

# ===== Main processing =====
if run_button:
    st.info("You got it, now sit back and relax while I cook your CSV 🍳")
    
    # 1. Get OAuth token
    auth_url = "https://ops.epo.org/3.2/auth/accesstoken"
    resp = requests.post(auth_url, auth=HTTPBasicAuth(client_id, client_secret),
                         data={"grant_type": "client_credentials"})
    if resp.status_code != 200:
        st.error("Authentication failed. Check credentials.")
    else:
        access_token = resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {access_token}"}
        
        # 2. Search API
        search_url = "https://ops.epo.org/3.2/rest-services/published-data/search/biblio"
        query = f'pd within "{year}0101 {year}1231"'
        params = {"q": query, "Range": f"1-{max_records}"}
        search_resp = requests.get(search_url, headers=headers, params=params)
        
        if search_resp.status_code != 200:
            st.error("Search failed.")
        else:
            search_root = etree.fromstring(search_resp.content)
            documents = search_root.xpath("//ex:exchange-document", namespaces=ns)
            all_records = []
            
            for doc in documents:
                doc_num = doc.attrib.get("doc-number", "")
                if not doc_num:
                    continue
                pub_date, applicant_name, applicant_country = extract_biblio_data(doc_num, headers)
                cpc_main, cpc_full = extract_cpc_data(doc_num, headers)
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
                filename = f"epo_patents_{year}.csv"
                df.to_csv(filename, index=False)
                st.success(f"CSV saved: {filename}")
                st.dataframe(df.head(5))
            else:
                st.warning("No records fetched.")
