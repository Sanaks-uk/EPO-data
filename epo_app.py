import streamlit as st
import requests
from requests.auth import HTTPBasicAuth
from lxml import etree
import pandas as pd
import time
import math

# ================= Streamlit page setup =================
st.set_page_config(page_title="EPO Patent Extractor", layout="wide")

# ================= CSS for centering input fields =================
st.markdown(
    """
    <style>
        .centered {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
        }
        .stButton>button {
            background-color: #FFB6C1;
            color: black;
        }
        .main {
            background-color: #FFD1DC;
            padding: 2rem;
        }
    </style>
    """, unsafe_allow_html=True
)

st.markdown('<div class="main centered">', unsafe_allow_html=True)
st.title("EPO Patent Extractor")
st.write("Enter your OPS credentials and fetch patent data.")

# ================= Inputs =================
client_id = st.text_input("Client ID")
client_secret = st.text_input("Client Secret", type="password")
year = st.number_input("Year to fetch", value=2024, step=1, min_value=1978, max_value=2100)
max_records = st.number_input("Max records", value=10, step=1, min_value=1)
batch_size = st.number_input("Batch size", value=10, step=1, min_value=1)

run_button = st.button("Run")

st.markdown('</div>', unsafe_allow_html=True)

# ================= Initialize session_state =================
if "run_trigger" not in st.session_state:
    st.session_state.run_trigger = False
if "all_records" not in st.session_state:
    st.session_state.all_records = []

if run_button:
    st.session_state.run_trigger = True

# ================= Functions =================
def get_access_token(client_id, client_secret):
    auth_url = "https://ops.epo.org/3.2/auth/accesstoken"
    resp = requests.post(auth_url, auth=HTTPBasicAuth(client_id, client_secret),
                         data={"grant_type": "client_credentials"})
    resp.raise_for_status()
    return resp.json()["access_token"]

ns = {
    "ops": "http://ops.epo.org",
    "ex": "http://www.epo.org/exchange",
    "epo": "http://www.epo.org/exchange",
    "xlink": "http://www.w3.org/1999/xlink"
}

def safe_xpath(root, xpath_str, namespaces, return_all=False):
    try:
        res = root.xpath(xpath_str, namespaces=namespaces)
        if return_all:
            return res
        return res[0].strip() if res and hasattr(res[0], 'strip') else (res[0] if res else "")
    except Exception:
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
            time.sleep(1.5)
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
            time.sleep(1)
    return data

def extract_biblio_data(doc_num, headers):
    biblio_urls = [
        f"https://ops.epo.org/3.2/rest-services/published-data/publication/epodoc/{doc_num}/biblio",
        f"https://ops.epo.org/3.2/rest-services/published-data/publication/docdb/{doc_num}/biblio"
    ]
    for biblio_url in biblio_urls:
        try:
            time.sleep(1)
            b_resp = requests.get(biblio_url, headers=headers, timeout=15)
            if b_resp.status_code != 200 or not b_resp.content:
                continue
            b_root = etree.fromstring(b_resp.content)
            # Publication date
            pub_date = safe_xpath(b_root, ".//ex:date/text()", ns)
            # Applicant name
            applicant_name = safe_xpath(b_root, ".//ex:applicant-name/ex:name/text()", ns)
            # Applicant country
            applicant_country = safe_xpath(b_root, ".//ex:residence/ex:country/text()", ns)
            return pub_date, applicant_name, applicant_country
        except:
            continue
    return "", "", ""

def extract_cpc_data(doc_num, headers):
    cpc_urls = [
        f"https://ops.epo.org/3.2/rest-services/published-data/publication/epodoc/{doc_num}/classifications",
        f"https://ops.epo.org/3.2/rest-services/published-data/publication/docdb/{doc_num}/classifications"
    ]
    for cpc_url in cpc_urls:
        try:
            time.sleep(1)
            cpc_resp = requests.get(cpc_url, headers=headers, timeout=15)
            if cpc_resp.status_code != 200 or not cpc_resp.content:
                continue
            cpc_root = etree.fromstring(cpc_resp.content)
            cpcs = cpc_root.xpath("//ex:classification-cpc", namespaces=ns)
            cpc_main = ""
            cpc_full = []
            for c in cpcs:
                code = safe_xpath(c, ".//ex:symbol/text()", ns)
                if code:
                    code_clean = code.replace(" ", "").replace("/", "")
                    cpc_full.append(code_clean)
                    if not cpc_main and len(code_clean) >= 4:
                        cpc_main = code_clean[:4]
            return cpc_main, cpc_full
        except:
            continue
    return "", []

# ================= Main execution =================
if st.session_state.run_trigger:
    if not client_id or not client_secret:
        st.warning("Please enter your Client ID and Secret")
    else:
        status_text = st.empty()
        status_text.info("You got it, now sit back and relax while I cook your CSV...")

        try:
            access_token = get_access_token(client_id, client_secret)
            headers = {"Authorization": f"Bearer {access_token}"}
        except Exception as e:
            st.error(f"Failed to get access token: {e}")
            st.stop()

        search_url = "https://ops.epo.org/3.2/rest-services/published-data/search/biblio"
        query = f'pd within "{year}0101 {year}1231"'
        params = {"q": query, "Range": f"1-{batch_size}"}
        search_resp = requests.get(search_url, headers=headers, params=params)
        search_root = etree.fromstring(search_resp.content)
        total_results = int(search_root.xpath("string(//ops:biblio-search/@total-result-count)", namespaces=ns))

        all_records = []
        total_to_fetch = min(total_results, max_records)
        total_batches = math.ceil(total_to_fetch / batch_size)

        for batch_num in range(total_batches):
            start = batch_num * batch_size + 1
            end = min(start + batch_size - 1, total_to_fetch)
            if batch_num == 0:
                batch_root = search_root
            else:
                params = {"q": query, "Range": f"{start}-{end}"}
                batch_resp = requests.get(search_url, headers=headers, params=params)
                batch_root = etree.fromstring(batch_resp.content)

            documents = batch_root.xpath("//ex:exchange-document", namespaces=ns)
            for doc in documents:
                if len(all_records) >= max_records:
                    break
                doc_num = doc.attrib.get("doc-number") or ""
                if not doc_num:
                    continue
                oid = doc.attrib.get("doc-id", "")
                pub_date, applicant_name, applicant_country = extract_biblio_data(doc_num, headers)
                cpc_main, cpc_full = extract_cpc_data(doc_num, headers)
                reg_data = fetch_register_data(doc_num, headers)
                record = {
                    "OID": oid,
                    "DocNumber": doc_num,
                    "Publn_date": pub_date,
                    "ApplicantFiledName": applicant_name,
                    "ApplicantCountry": applicant_country,
                    "CPCMain": cpc_main,
                    "CPCFull": ";".join(cpc_full),
                    **reg_data
                }
                all_records.append(record)
            time.sleep(1)

        if all_records:
            df = pd.DataFrame(all_records)
            filename = f"epo_patents_register_{year}.csv"
            df.to_csv(filename, index=False)
            st.success(f"Saved {len(df)} records to {filename}")
            st.dataframe(df)
        else:
            st.warning("No records collected")
