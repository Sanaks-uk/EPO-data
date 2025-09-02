import streamlit as st
import requests
from requests.auth import HTTPBasicAuth
from lxml import etree
import pandas as pd
import time

st.set_page_config(page_title="EPO OPS Patent Extractor", layout="wide")
st.title("📄 EPO OPS Patent Extractor")

# ===== Inputs =====
client_id = st.text_input("Client ID", "")
client_secret = st.text_input("Client Secret", "", type="password")
year = st.number_input("Year", min_value=1978, max_value=2100, value=2024)
max_records = st.number_input("Max records", min_value=1, max_value=500, value=50)

if st.button("Fetch Data"):

    if not client_id or not client_secret:
        st.error("Please enter both Client ID and Client Secret")
        st.stop()

    # ===== Auth =====
    try:
        st.info("Obtaining access token...")
        auth_url = "https://ops.epo.org/3.2/auth/accesstoken"
        resp = requests.post(
            auth_url,
            auth=HTTPBasicAuth(client_id, client_secret),
            data={"grant_type": "client_credentials"}
        )
        resp.raise_for_status()
        access_token = resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {access_token}"}
        st.success("✓ Access token obtained")
    except Exception as e:
        st.error(f"Error obtaining token: {e}")
        st.stop()

    # ===== Search patents =====
    search_url = "https://ops.epo.org/3.2/rest-services/published-data/search/biblio"
    query = f'pd within "{year}0101 {year}1231"'
    batch_size = 10
    delay = 2

    try:
        params = {"q": query, "Range": f"1-{batch_size}"}
        search_resp = requests.get(search_url, headers=headers, params=params)
        search_resp.raise_for_status()
        ns = {"ops": "http://ops.epo.org", "ex": "http://www.epo.org/exchange"}
        search_root = etree.fromstring(search_resp.content)
        total_results = int(search_root.xpath("string(//ops:biblio-search/@total-result-count)", namespaces=ns))
        st.write(f"Total patents found: {total_results}")
    except Exception as e:
        st.error(f"Error fetching search results: {e}")
        st.stop()

    # ===== Collect patents =====
    all_records = []
    docs_processed = 0
    start = 1

    while docs_processed < max_records:
        end = min(start + batch_size - 1, max_records)
        params = {"q": query, "Range": f"{start}-{end}"}
        search_resp = requests.get(search_url, headers=headers, params=params)
        if search_resp.status_code != 200:
            st.warning(f"Search batch {start}-{end} failed: {search_resp.status_code}")
            break

        search_root = etree.fromstring(search_resp.content)
        documents = search_root.xpath("//ex:exchange-document", namespaces=ns)

        for doc in documents:
            doc_num = doc.attrib.get("doc-number", "")
            country = doc.attrib.get("country", "")
            kind = doc.attrib.get("kind", "")
            pub_date = doc.xpath(".//ex:publication-reference/ex:document-id/ex:date/text()", namespaces=ns)
            title = doc.xpath(".//ex:invention-title/text()", namespaces=ns)
            applicant = doc.xpath(".//ex:applicant/ex:applicant-name/ex:name/text()", namespaces=ns)
            inventor = doc.xpath(".//ex:inventor/ex:inventor-name/ex:name/text()", namespaces=ns)

            # ===== Register data =====
            register_url = f"https://ops.epo.org/3.2/rest-services/register/publication/epodoc/{doc_num}"
            register_data = {}
            try:
                reg_resp = requests.get(register_url, headers=headers)
                if reg_resp.status_code == 200:
                    reg_root = etree.fromstring(reg_resp.content)
                    reg_event = reg_root.xpath("string(//reg:event-code)", namespaces={"reg": "http://www.epo.org/register"})
                    reg_status = reg_root.xpath("string(//reg:status)", namespaces={"reg": "http://www.epo.org/register"})
                    register_data = {"RegisterEvent": reg_event, "RegisterStatus": reg_status}
            except Exception:
                pass

            # ===== CPC classification =====
            cpc_url = f"https://ops.epo.org/3.2/rest-services/classification/cpc/publication/epodoc/{doc_num}"
            cpc_codes = []
            try:
                cpc_resp = requests.get(cpc_url, headers=headers)
                if cpc_resp.status_code == 200:
                    cpc_root = etree.fromstring(cpc_resp.content)
                    codes = cpc_root.xpath("//cpc:classification-symbol/text()", namespaces={"cpc": "http://www.epo.org/cpc"})
                    cpc_codes = codes
            except Exception:
                pass

            record = {
                "DocNumber": doc_num,
                "Country": country,
                "Kind": kind,
                "Publn_date": pub_date[0] if pub_date else "",
                "Title": title[0] if title else "",
                "Applicant": applicant[0] if applicant else "",
                "Inventor": inventor[0] if inventor else "",
                "CPC": "; ".join(cpc_codes),
                **register_data
            }
            all_records.append(record)
            docs_processed += 1

        start += batch_size
        time.sleep(delay)

    # ===== Show results =====
    if all_records:
        df = pd.DataFrame(all_records)
        st.success(f"✓ Extracted {len(df)} records")
        st.dataframe(df)
        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button("Download CSV", data=csv, file_name=f"epo_patents_{year}.csv")
    else:
        st.warning("No records found")
