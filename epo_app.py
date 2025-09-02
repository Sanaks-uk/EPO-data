import streamlit as st
import requests
from requests.auth import HTTPBasicAuth
from lxml import etree
import pandas as pd
import time
import math
from io import BytesIO

st.title("EPO Patent Extractor")

# ===== 1. User Inputs =====
client_id = st.text_input("Client ID")
client_secret = st.text_input("Client Secret", type="password")
year = st.number_input("Year", min_value=1978, max_value=2100, value=2024)
max_rows = st.number_input("Max number of patents to fetch (0 = all)", min_value=0, value=0)
batch_size = st.number_input("Batch Size (recommended 50)", min_value=10, max_value=100, value=50)
fetch_button = st.button("Fetch Patents")

# ===== 2. Helper functions =====
def safe_xpath(root, xpath_str, ns):
    res = root.xpath(xpath_str, namespaces=ns)
    return res[0] if res else ""

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
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code == 200 and resp.content:
                try:
                    j = resp.json()
                except ValueError:
                    continue
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

# ===== 3. Main process =====
if fetch_button:
    if not client_id or not client_secret:
        st.error("Please enter Client ID and Client Secret")
    else:
        st.info("Fetching access token...")
        try:
            auth_url = "https://ops.epo.org/3.2/auth/accesstoken"
            resp = requests.post(auth_url, auth=HTTPBasicAuth(client_id, client_secret),
                                 data={"grant_type": "client_credentials"})
            resp.raise_for_status()
            access_token = resp.json()["access_token"]
            headers = {"Authorization": f"Bearer {access_token}"}
            st.success("✓ Access token obtained")
        except Exception as e:
            st.error(f"Access token error: {e}")
            st.stop()

        ns = {"ops": "http://ops.epo.org", "ex": "http://www.epo.org/exchange"}
        search_url = "https://ops.epo.org/3.2/rest-services/published-data/search/biblio"
        query = f'pd within "{year}0101 {year}1231"'
        delay = 2

        # ===== Get total results =====
        params = {"q": query, "Range": f"1-{batch_size}"}
        search_resp = requests.get(search_url, headers=headers, params=params)
        search_resp.raise_for_status()
        search_root = etree.fromstring(search_resp.content)
        total_results = int(search_root.xpath("string(//ops:biblio-search/@total-result-count)", namespaces=ns))
        st.write(f"Total patents found: {total_results}")

        if max_rows > 0:
            total_to_fetch = min(total_results, max_rows)
        else:
            total_to_fetch = total_results

        total_batches = math.ceil(total_to_fetch / batch_size)
        all_records = []

        progress_bar = st.progress(0)
        for batch_num in range(total_batches):
            start = batch_num*batch_size + 1
            end = min(start+batch_size-1, total_to_fetch)
            st.info(f"Fetching batch {batch_num+1} ({start}-{end})")

            params = {"q": query, "Range": f"{start}-{end}"}
            batch_resp = requests.get(search_url, headers=headers, params=params)
            batch_root = etree.fromstring(batch_resp.content)
            documents = batch_root.xpath("//ex:exchange-document", namespaces=ns)

            for doc in documents:
                doc_num = doc.attrib.get("doc-number")
                oid = doc.attrib.get("doc-id")
                if not doc_num:
                    continue

                # Biblio
                biblio_url = f"https://ops.epo.org/3.2/rest-services/published-data/publication/epodoc/{doc_num}/biblio"
                try:
                    time.sleep(0.1)
                    b_resp = requests.get(biblio_url, headers=headers, timeout=10)
                    if b_resp.status_code == 200 and b_resp.content:
                        b_root = etree.fromstring(b_resp.content)
                        pub_date = safe_xpath(b_root, ".//ex:publication-reference/ex:document-id[@document-id-type='docdb']/ex:date", ns)
                        applicant_name = safe_xpath(b_root, ".//ex:applicants/ex:applicant/ex:name", ns)
                        applicant_country = safe_xpath(b_root, ".//ex:applicants/ex:applicant/ex:addressbook/ex:address/ex:country", ns)
                    else:
                        pub_date, applicant_name, applicant_country = "", "", ""
                except:
                    pub_date, applicant_name, applicant_country = "", "", ""

                # CPC
                cpc_url = f"https://ops.epo.org/3.2/rest-services/published-data/publication/epodoc/{doc_num}/classifications"
                try:
                    time.sleep(0.05)
                    cpc_resp = requests.get(cpc_url, headers=headers, timeout=10)
                    cpc_main = ""
                    cpc_full = []
                    if cpc_resp.status_code == 200 and cpc_resp.content:
                        cpc_root = etree.fromstring(cpc_resp.content)
                        cpcs = cpc_root.xpath("//ex:classification-cpc", namespaces=ns)
                        for c in cpcs:
                            code = c.xpath("string(.//ex:cpc-symbol)", namespaces=ns)
                            if code:
                                code_clean = code.replace(" ", "").replace("/", "")
                                cpc_full.append(code_clean)
                                if not cpc_main:
                                    cpc_main = code_clean[:4]
                    else:
                        cpc_main, cpc_full = "", []
                except:
                    cpc_main, cpc_full = "", []

                # Register
                reg_data = fetch_register_data(doc_num, headers)

                all_records.append({
                    "OID": oid,
                    "DocNumber": doc_num,
                    "Publn_date": pub_date,
                    "ApplicantFiledName": applicant_name,
                    "ApplicantCountry": applicant_country,
                    "CPCMain": cpc_main,
                    "CPCFull": ";".join(cpc_full),
                    **reg_data
                })

            progress_bar.progress(min((batch_num+1)/total_batches, 1.0))
            time.sleep(delay)

        # ===== Download CSV =====
        if all_records:
            df = pd.DataFrame(all_records)
            csv = df.to_csv(index=False).encode('utf-8')
            st.success(f"✓ Fetched {len(df)} records")
            st.download_button(
                label="Download CSV",
                data=csv,
                file_name=f"epo_patents_{year}.csv",
                mime='text/csv'
            )
        else:
            st.warning("No records collected")
