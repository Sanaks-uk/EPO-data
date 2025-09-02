import streamlit as st
import requests
from requests.auth import HTTPBasicAuth
from lxml import etree
import pandas as pd
import time
import math
from io import StringIO

# =========================
# Streamlit UI
# =========================
st.title("EPO Patent Data Extractor")
st.write("Enter your EPO OPS API credentials and parameters below:")

client_id = st.text_input("Client ID", type="password")
client_secret = st.text_input("Client Secret", type="password")
year = st.number_input("Publication Year", min_value=1970, max_value=2050, value=2024)
max_records = st.number_input("Max Records", min_value=1, max_value=500, value=50)
batch_size = 10
delay = 6

run_button = st.button("Fetch Patent Data")

if run_button:
    if not client_id or not client_secret:
        st.error("Please enter both Client ID and Client Secret.")
    else:
        try:
            # ===== 1. Get OAuth2 Token =====
            st.write("🔑 Getting access token...")
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

            # ===== 2. Namespaces =====
            ns = {
                "ops": "http://ops.epo.org",
                "ex": "http://www.epo.org/exchange",
                "epo": "http://www.epo.org/exchange",
                "xlink": "http://www.w3.org/1999/xlink"
            }

            # ===== 3. Search parameters =====
            search_url = "https://ops.epo.org/3.2/rest-services/published-data/search/biblio"
            query = f'pd within "{year}0101 {year}1231"'
            params = {"q": query, "Range": f"1-{batch_size}"}
            search_resp = requests.get(search_url, headers=headers, params=params)
            search_resp.raise_for_status()
            search_root = etree.fromstring(search_resp.content)
            total_results = int(search_root.xpath("string(//ops:biblio-search/@total-result-count)", namespaces=ns))
            st.write(f"📄 Total patents found: {total_results}")

            # ===== 4. Processing Loop =====
            all_records = []
            total_to_fetch = min(total_results, max_records)
            total_batches = math.ceil(total_to_fetch / batch_size)

            progress_bar = st.progress(0)
            status_text = st.empty()

            for batch_num in range(total_batches):
                start = batch_num * batch_size + 1
                end = min(start + batch_size - 1, total_to_fetch)

                status_text.text(f"Batch {batch_num+1}/{total_batches} (records {start}-{end})")

                if batch_num == 0:
                    batch_root = search_root
                else:
                    params = {"q": query, "Range": f"{start}-{end}"}
                    batch_resp = requests.get(search_url, headers=headers, params=params)
                    if batch_resp.status_code != 200:
                        continue
                    batch_root = etree.fromstring(batch_resp.content)

                documents = batch_root.xpath("//ex:exchange-document", namespaces=ns)

                for doc in documents:
                    if len(all_records) >= max_records:
                        break

                    doc_num = doc.attrib.get("doc-number", "")
                    oid = doc.attrib.get("doc-id", "")

                    pub_date = doc.xpath("string(.//ex:date)", namespaces=ns)
                    applicant = doc.xpath("string(.//ex:applicant-name/ex:name)", namespaces=ns)

                    record = {
                        "OID": oid,
                        "DocNumber": doc_num,
                        "Publn_date": pub_date,
                        "ApplicantFiledName": applicant
                    }
                    all_records.append(record)

                progress_bar.progress((batch_num + 1) / total_batches)
                time.sleep(delay)

            # ===== 5. Save Results =====
            if all_records:
                df = pd.DataFrame(all_records)
                csv = df.to_csv(index=False)
                st.success(f"✓ Done! Collected {len(df)} records.")

                st.dataframe(df.head(10))

                st.download_button(
                    label="Download CSV",
                    data=csv,
                    file_name=f"epo_patents_register_{year}.csv",
                    mime="text/csv"
                )
            else:
                st.warning("No records collected.")

        except Exception as e:
            st.error(f"Error: {e}")
