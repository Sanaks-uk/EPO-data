import streamlit as st
import requests
from requests.auth import HTTPBasicAuth
from lxml import etree
import pandas as pd
import time
import math
import io
from datetime import datetime

# Page configuration
st.set_page_config(
    page_title="EPO Patent Data Extractor",
    page_icon="📄",
    layout="wide"
)

st.title("🔍 EPO Patent Data Extractor")
st.markdown("Extract patent data from the European Patent Office (EPO) database")

# Sidebar for inputs
st.sidebar.header("Configuration")

# User inputs
client_id = st.sidebar.text_input(
    "Client ID", 
    type="password",
    help="Your EPO OPS API client ID"
)

client_secret = st.sidebar.text_input(
    "Client Secret", 
    type="password",
    help="Your EPO OPS API client secret"
)

year = st.sidebar.number_input(
    "Year", 
    min_value=1900, 
    max_value=2024, 
    value=2024,
    help="Publication year to search for"
)

max_records = st.sidebar.number_input(
    "Number of Records", 
    min_value=1, 
    max_value=1000, 
    value=10,
    help="Maximum number of records to extract"
)

# Advanced settings
with st.sidebar.expander("Advanced Settings"):
    batch_size = st.number_input("Batch Size", min_value=1, max_value=100, value=10)
    delay = st.number_input("Delay (seconds)", min_value=1, max_value=30, value=6)

# Initialize session state
if 'extraction_complete' not in st.session_state:
    st.session_state.extraction_complete = False
if 'df_result' not in st.session_state:
    st.session_state.df_result = None

# Helper functions (copied from original script)
def safe_xpath(root, xpath_str, namespaces, return_all=False):
    try:
        res = root.xpath(xpath_str, namespaces=namespaces)
        if return_all:
            return res
        return res[0].strip() if res and hasattr(res[0], 'strip') else (res[0] if res else "")
    except Exception as e:
        st.error(f"XPath error: {e}")
        return [] if return_all else ""

def extract_from_text_node(element, xpath_str, namespaces):
    """Extract text from nodes, handling both text content and attributes"""
    try:
        if element is None:
            return ""
        result = element.xpath(xpath_str, namespaces=namespaces)
        if isinstance(result, list) and result:
            if hasattr(result[0], 'text'):
                return result[0].text.strip() if result[0].text else ""
            else:
                return str(result[0]).strip()
        elif isinstance(result, str):
            return result.strip()
        return ""
    except Exception as e:
        st.error(f"Text extraction error: {e}")
        return ""

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
            time.sleep(2)
            resp = requests.get(url, headers=headers, timeout=15)
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
        except Exception as e:
            st.warning(f"Register API failed for {doc_num} ({key}): {e}")
            time.sleep(2)
    return data

def extract_biblio_data(doc_num, headers, ns):
    """Extract bibliographic data with better error handling"""
    biblio_urls = [
        f"https://ops.epo.org/3.2/rest-services/published-data/publication/epodoc/{doc_num}/biblio",
        f"https://ops.epo.org/3.2/rest-services/published-data/publication/docdb/{doc_num}/biblio"
    ]
    
    for url_type, biblio_url in enumerate(biblio_urls):
        try:
            time.sleep(2)
            b_resp = requests.get(biblio_url, headers=headers, timeout=15)
            
            if b_resp.status_code == 404:
                continue
                
            if b_resp.status_code != 200:
                continue
                
            if not b_resp.content:
                continue
                
            b_root = etree.fromstring(b_resp.content)
            
            # Try multiple XPath patterns for publication date
            pub_date_paths = [
                ".//ex:publication-reference/ex:document-id[@document-id-type='epodoc']/ex:date/text()",
                ".//ex:publication-reference/ex:document-id[@document-id-type='docdb']/ex:date/text()", 
                ".//ex:publication-reference/ex:document-id/ex:date/text()",
                ".//ex:document-id[@document-id-type='epodoc']/ex:date/text()",
                ".//ex:document-id[@document-id-type='docdb']/ex:date/text()",
                ".//ex:date/text()",
                "//ex:date/text()"
            ]
            
            pub_date = ""
            for path in pub_date_paths:
                pub_date = safe_xpath(b_root, path, ns)
                if pub_date:
                    break
            
            # Try multiple XPath patterns for applicant name
            applicant_name_paths = [
                ".//ex:applicants/ex:applicant/ex:applicant-name/ex:name/text()",
                ".//ex:applicants/ex:applicant/ex:name/text()", 
                ".//ex:applicant/ex:applicant-name/ex:name/text()",
                ".//ex:applicant/ex:name/text()",
                ".//ex:applicant-name/ex:name/text()",
                "//ex:applicant-name/ex:name/text()",
                "//ex:applicant//ex:name/text()"
            ]
            
            applicant_name = ""
            for path in applicant_name_paths:
                applicant_name = safe_xpath(b_root, path, ns)
                if applicant_name:
                    break
            
            # Try multiple XPath patterns for applicant country
            applicant_country_paths = [
                ".//ex:applicants/ex:applicant/ex:addressbook/ex:address/ex:country/text()",
                ".//ex:applicants/ex:applicant/ex:residence/ex:country/text()",
                ".//ex:applicant/ex:addressbook/ex:address/ex:country/text()",
                ".//ex:applicant/ex:residence/ex:country/text()", 
                ".//ex:address/ex:country/text()",
                "//ex:residence/ex:country/text()",
                "//ex:country/text()"
            ]
            
            applicant_country = ""
            for path in applicant_country_paths:
                applicant_country = safe_xpath(b_root, path, ns)
                if applicant_country:
                    break
            
            return pub_date, applicant_name, applicant_country
            
        except Exception as e:
            continue
    
    return "", "", ""

def extract_cpc_data(doc_num, headers, ns):
    """Extract CPC classification data with better error handling"""
    cpc_urls = [
        f"https://ops.epo.org/3.2/rest-services/published-data/publication/epodoc/{doc_num}/classifications",
        f"https://ops.epo.org/3.2/rest-services/published-data/publication/docdb/{doc_num}/classifications"
    ]
    
    for url_type, cpc_url in enumerate(cpc_urls):
        try:
            time.sleep(1.5)
            cpc_resp = requests.get(cpc_url, headers=headers, timeout=15)
            
            if cpc_resp.status_code == 404:
                continue
                
            if cpc_resp.status_code != 200:
                continue
                
            if not cpc_resp.content:
                continue
                
            cpc_root = etree.fromstring(cpc_resp.content)
            
            # Try multiple CPC paths
            cpc_paths = [
                "//ex:classification-cpc",
                "//ex:cpc", 
                ".//ex:classification-cpc",
                "//ex:classification"
            ]
            
            cpc_main = ""
            cpc_full = []
            
            for cpc_path in cpc_paths:
                cpcs = cpc_root.xpath(cpc_path, namespaces=ns)
                if cpcs:
                    for c in cpcs:
                        symbol_paths = [
                            ".//ex:symbol/text()", 
                            ".//ex:cpc-symbol/text()",
                            ".//text()[normalize-space()]",
                            "./text()"
                        ]
                        
                        code = ""
                        for symbol_path in symbol_paths:
                            results = c.xpath(symbol_path, namespaces=ns)
                            if results:
                                code = results[0].strip() if hasattr(results[0], 'strip') else str(results[0]).strip()
                                if code:
                                    break
                        
                        if code:
                            code_clean = str(code).replace(" ", "").replace("/", "")
                            cpc_full.append(code_clean)
                            if not cpc_main and len(code_clean) >= 4:
                                cpc_main = code_clean[:4]
                    break
            
            return cpc_main, cpc_full
            
        except Exception as e:
            continue
    
    return "", []

def main_extraction(client_id, client_secret, year, max_records, batch_size, delay):
    """Main extraction function"""
    
    # Progress tracking
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    try:
        # Get OAuth2 Token
        status_text.text("🔑 Getting access token...")
        auth_url = "https://ops.epo.org/3.2/auth/accesstoken"
        resp = requests.post(auth_url, auth=HTTPBasicAuth(client_id, client_secret),
                           data={"grant_type": "client_credentials"})
        resp.raise_for_status()
        access_token = resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {access_token}"}
        st.success("✅ Access token obtained")
        
        # Namespaces
        ns = {
            "ops": "http://ops.epo.org",
            "ex": "http://www.epo.org/exchange",
            "epo": "http://www.epo.org/exchange",
            "xlink": "http://www.w3.org/1999/xlink"
        }
        
        # Search parameters
        search_url = "https://ops.epo.org/3.2/rest-services/published-data/search/biblio"
        query = f'pd within "{year}0101 {year}1231"'
        
        # Get total results
        status_text.text("🔍 Searching for patents...")
        params = {"q": query, "Range": f"1-{batch_size}"}
        search_resp = requests.get(search_url, headers=headers, params=params)
        search_resp.raise_for_status()
        search_root = etree.fromstring(search_resp.content)
        total_results = int(search_root.xpath("string(//ops:biblio-search/@total-result-count)", namespaces=ns))
        
        st.info(f"📊 Found {total_results} patents for year {year}")
        
        # Process records
        all_records = []
        total_to_fetch = min(total_results, max_records)
        total_batches = math.ceil(total_to_fetch / batch_size)
        
        for batch_num in range(total_batches):
            start = batch_num * batch_size + 1
            end = min(start + batch_size - 1, total_to_fetch)
            
            status_text.text(f"📦 Processing batch {batch_num+1}/{total_batches} (records {start}-{end})")
            progress_bar.progress((batch_num) / total_batches)
            
            if batch_num == 0:
                batch_root = search_root
            else:
                params = {"q": query, "Range": f"{start}-{end}"}
                batch_resp = requests.get(search_url, headers=headers, params=params)
                if batch_resp.status_code != 200:
                    st.error(f"Batch {batch_num+1} failed: {batch_resp.status_code}")
                    continue
                batch_root = etree.fromstring(batch_resp.content)
            
            # Find documents in the batch
            documents = batch_root.xpath("//ex:exchange-document", namespaces=ns)
            
            for i, doc in enumerate(documents):
                if len(all_records) >= max_records:
                    break
                
                # Get document number
                doc_num = doc.attrib.get("doc-number")
                if not doc_num:
                    doc_id_elem = doc.xpath(".//ex:document-id[@document-id-type='epodoc']", namespaces=ns)
                    if doc_id_elem:
                        doc_num = safe_xpath(doc_id_elem[0], "./ex:doc-number", ns)
                
                oid = doc.attrib.get("doc-id", "")
                
                if not doc_num:
                    continue
                
                # Extract basic info from search results
                try:
                    pub_ref = doc.xpath(".//ex:publication-reference/ex:document-id[@document-id-type='epodoc']", namespaces=ns)
                    search_pub_date = ""
                    search_applicant = ""
                    full_doc_number = ""
                    
                    if pub_ref:
                        country = safe_xpath(pub_ref[0], "./ex:country/text()", ns)
                        number = safe_xpath(pub_ref[0], "./ex:doc-number/text()", ns) 
                        kind = safe_xpath(pub_ref[0], "./ex:kind/text()", ns)
                        date_elem = pub_ref[0].xpath("./ex:date/text()", namespaces=ns)
                        
                        if country and number:
                            full_doc_number = f"{country}{number}{kind}" if kind else f"{country}{number}"
                            
                        if date_elem:
                            search_pub_date = date_elem[0] if date_elem[0] else ""
                    
                    applicant_elem = doc.xpath(".//ex:applicant-name/ex:name", namespaces=ns)
                    if applicant_elem and hasattr(applicant_elem[0], 'text') and applicant_elem[0].text:
                        search_applicant = applicant_elem[0].text.strip()
                        
                    search_applicant_country = ""
                    country_elem = doc.xpath(".//ex:applicant/ex:addressbook/ex:address/ex:country", namespaces=ns)
                    if country_elem and hasattr(country_elem[0], 'text') and country_elem[0].text:
                        search_applicant_country = country_elem[0].text.strip()
                    
                    if full_doc_number:
                        doc_num = full_doc_number
                        
                except Exception as e:
                    search_pub_date, search_applicant, search_applicant_country = "", "", ""
                
                # Fetch detailed data
                pub_date, applicant_name, applicant_country = extract_biblio_data(doc_num, headers, ns)
                
                # Use search results as fallback
                if not pub_date:
                    pub_date = search_pub_date
                if not applicant_name:
                    applicant_name = search_applicant
                if not applicant_country:
                    applicant_country = search_applicant_country
                
                # Fetch CPC classifications
                cpc_main, cpc_full = extract_cpc_data(doc_num, headers, ns)
                
                # Fetch Register data
                reg_data = fetch_register_data(doc_num, headers)
                
                # Save record
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
                
                # Update progress
                current_progress = len(all_records) / max_records
                progress_bar.progress(min(current_progress, 1.0))
                status_text.text(f"✅ Processed {len(all_records)}/{max_records} records")
            
            if len(all_records) >= max_records:
                break
            
            # Delay between batches
            if batch_num < total_batches - 1:
                time.sleep(delay)
        
        progress_bar.progress(1.0)
        status_text.text("🎉 Extraction completed!")
        
        return pd.DataFrame(all_records)
        
    except Exception as e:
        st.error(f"❌ An error occurred: {str(e)}")
        return None

# Main interface
col1, col2 = st.columns([2, 1])

with col1:
    st.header("📋 Extraction Settings")
    
    if st.button("🚀 Start Extraction", type="primary", disabled=not (client_id and client_secret)):
        if not client_id or not client_secret:
            st.error("⚠️ Please provide both Client ID and Client Secret")
        else:
            with st.spinner("Extracting patent data..."):
                df_result = main_extraction(client_id, client_secret, year, max_records, batch_size, delay)
                if df_result is not None:
                    st.session_state.df_result = df_result
                    st.session_state.extraction_complete = True

with col2:
    st.header("ℹ️ Information")
    st.info("""
    **Required:**
    - EPO OPS API credentials
    - Publication year
    - Number of records to extract
    
    **Features:**
    - Extracts bibliographic data
    - Gets CPC classifications
    - Fetches register information
    - Exports to CSV
    """)

# Display results
if st.session_state.extraction_complete and st.session_state.df_result is not None:
    df = st.session_state.df_result
    
    st.header("📊 Extraction Results")
    
    # Summary statistics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total Records", len(df))
    
    with col2:
        st.metric("With Publication Dates", (df['Publn_date'] != '').sum())
    
    with col3:
        st.metric("With Applicant Names", (df['ApplicantFiledName'] != '').sum())
    
    with col4:
        st.metric("With CPC Classifications", (df['CPCMain'] != '').sum())
    
    # Additional statistics
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("With Representatives", (df['RepName'] != '').sum())
    
    with col2:
        st.metric("With Oppositions", (df['OpponentName'] != '').sum())
    
    with col3:
        st.metric("With Appeals", (df['AppealNr'] != '').sum())
    
    # Data preview
    st.subheader("📄 Data Preview")
    st.dataframe(df.head(10), use_container_width=True)
    
    # Download options
    st.subheader("💾 Download Data")
    
    # CSV download
    csv_buffer = io.StringIO()
    df.to_csv(csv_buffer, index=False)
    csv_data = csv_buffer.getvalue()
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"epo_patents_register_{year}_{timestamp}.csv"
    
    st.download_button(
        label="📥 Download as CSV",
        data=csv_data,
        file_name=filename,
        mime="text/csv",
        type="primary"
    )
    
    # Excel download
    excel_buffer = io.BytesIO()
    with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='EPO Patents', index=False)
    excel_data = excel_buffer.getvalue()
    
    st.download_button(
        label="📥 Download as Excel",
        data=excel_data,
        file_name=filename.replace('.csv', '.xlsx'),
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    
    # Show full dataset option
    if st.checkbox("Show full dataset"):
        st.dataframe(df, use_container_width=True)

# Footer
st.markdown("---")
st.markdown("*EPO Patent Data Extractor - Built with Streamlit*")
