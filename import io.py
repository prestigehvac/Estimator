import io
import re
import pandas as pd
import pdfplumber
import streamlit as st

# Page Configuration
st.set_page_config(page_title="AHRI & Distributor Pricing Matcher", layout="wide")

st.title("🏷️ AHRI & Distributor Pricing Lookup Tool")
st.write(
    "Upload your **Master AHRI Sheet** and one or more **Distributor Price Lists** below to select a tonnage capacity and instantly view pricing options."
)
st.markdown("---")

# --- SECTION 1: MASTER AHRI UPLOAD ---
with st.container():
    st.subheader("1️⃣ Step 1: Upload Master AHRI File")
    uploaded_ahri = st.file_uploader(
        "📁 Click to Upload Master AHRI File (.xlsx or .xls)",
        type=["xlsx", "xls"],
        key="master_ahri_uploader",
    )

    raw_ahri_df = None
    ahri_df = None
    selected_tonnage = None

    if uploaded_ahri:
        xls_ahri = pd.ExcelFile(uploaded_ahri)
        col_t1, _ = st.columns([1, 2])
        with col_t1:
            selected_tonnage = st.selectbox(
                "🎯 Select Tonnage / Capacity Tab:", options=xls_ahri.sheet_names
            )

        raw_ahri_df = pd.read_excel(uploaded_ahri, sheet_name=selected_tonnage, header=None)
        raw_ahri_df = raw_ahri_df.rename(columns={0: "AHRI_Reference_Number"})

        raw_ahri_df["_clean_ahri_key"] = (
            raw_ahri_df["AHRI_Reference_Number"]
            .astype(str)
            .str.strip()
            .str.replace(".0", "", regex=False)
        )

        ahri_df = raw_ahri_df.dropna(subset=["AHRI_Reference_Number"])
        st.success(
            f"✅ Successfully loaded **{len(ahri_df)}** AHRI records from tab **'{selected_tonnage}'**."
        )

        with st.expander("👁️ Preview Extracted Master AHRI Records"):
            st.dataframe(raw_ahri_df.head(10), use_container_width=True)

st.markdown("---")

# --- SECTION 2: MULTI-DISTRIBUTOR PRICE LIST UPLOAD ---
with st.container():
    st.subheader("2️⃣ Step 2: Upload Distributor Price Lists")
    uploaded_dist_files = st.file_uploader(
        "📁 Upload Distributor Price Sheets (Select multiple CSV, XLSX, or PDF files)",
        type=["csv", "xlsx", "pdf"],
        accept_multiple_files=True,
        key="multi_distributor_uploader",
    )

    distributor_records = []

    if uploaded_dist_files:
        for uploaded_file in uploaded_dist_files:
            filename = uploaded_file.name

            # 1. CSV Files
            if filename.endswith(".csv"):
                df = pd.read_csv(uploaded_file)
                df["Distributor_Source"] = filename
                distributor_records.append(df)

            # 2. Excel Files
            elif filename.endswith((".xlsx", ".xls")):
                xls = pd.ExcelFile(uploaded_file)
                for sheet in xls.sheet_names:
                    df = pd.read_excel(uploaded_file, sheet_name=sheet)
                    df["Distributor_Source"] = f"{filename} ({sheet})"
                    distributor_records.append(df)

            # 3. PDF Files (Enhanced Multi-Line Block Parsing)
            elif filename.endswith(".pdf"):
                parsed_pdf_rows = []

                with pdfplumber.open(uploaded_file) as pdf:
                    for page_idx, page in enumerate(pdf.pages):
                        page_text = page.extract_text() or ""
                        
                        # Process both raw page text and table rows
                        lines = [l.strip() for l in page_text.split("\n") if l.strip()]
                        
                        tables = page.extract_tables() or []
                        for table in tables:
                            for row in table:
                                row_str = " ".join([str(c).strip() for c in row if c])
                                if row_str:
                                    lines.append(row_str)

                        # Parse entries line by line & block by block
                        for i, line in enumerate(lines):
                            # Find any 7 to 10 digit AHRI reference numbers in line
                            ahri_candidates = re.findall(r"\b\d{7,10}\b", line)
                            
                            # Search current line + next 2 lines for price matches
                            block_text = " ".join(lines[i:i+3])
                            # Pattern matches $3,336.58 or 3336.58 or 3,336.58
                            prices = re.findall(r"\$?\s*([0-9]{1,3}(?:,[0-9]{3})+\.\d{2}|[0-9]{3,6}\.\d{2})", block_text)
                            
                            price_val = prices[-1] if prices else None

                            if ahri_candidates:
                                for ahri_found in ahri_candidates:
                                    parsed_pdf_rows.append({
                                        "Extracted_AHRI": ahri_found,
                                        "Extracted_Line_Content": line,
                                        "System_Price": price_val,
                                        "Distributor_Source": filename,
                                    })
                            else:
                                # Fallback record for line-based matching
                                prices_line = re.findall(r"\$?\s*([0-9]{1,3}(?:,[0-9]{3})+\.\d{2}|[0-9]{3,6}\.\d{2})", line)
                                parsed_pdf_rows.append({
                                    "Extracted_AHRI": None,
                                    "Extracted_Line_Content": line,
                                    "System_Price": prices_line[-1] if prices_line else None,
                                    "Distributor_Source": filename,
                                })

                if parsed_pdf_rows:
                    pdf_df = pd.DataFrame(parsed_pdf_rows)
                    distributor_records.append(pdf_df)

        if distributor_records:
            distributor_df = pd.concat(distributor_records, ignore_index=True)
            st.success(
                f"✅ Processed **{len(uploaded_dist_files)}** price list file(s) with **{len(distributor_df)}** parsed records."
            )
            with st.expander("👁️ Preview Parsed Distributor Data"):
                st.dataframe(distributor_df.head(15), use_container_width=True)

st.markdown("---")

# --- SECTION 3: MATCHING & RESULTS ---
if ahri_df is not None and distributor_records:
    st.subheader("3️⃣ Step 3: Match & View Pricing Options")

    matched_results = []

    for _, ahri_row in ahri_df.iterrows():
        ahri_num = str(ahri_row["_clean_ahri_key"]).strip()
        original_ref = ahri_row["AHRI_Reference_Number"]

        if not ahri_num or ahri_num == "nan":
            continue

        # Match by extracted AHRI candidate key or string containment
        matched_rows = distributor_df[
            (distributor_df["Extracted_AHRI"] == ahri_num) |
            (distributor_df["Extracted_Line_Content"].str.contains(re.escape(ahri_num), case=False, na=False))
        ]

        # Prioritize matches that successfully captured a System_Price
        if not matched_rows.empty:
            valid_price_matches = matched_rows[matched_rows["System_Price"].notna()]
            target_df = valid_price_matches if not valid_price_matches.empty else matched_rows

            for _, match in target_df.iterrows():
                matched_results.append({
                    "Selected_Tonnage": selected_tonnage,
                    "AHRI_Reference_Number": original_ref,
                    "Matched_Catalog_Line": match.get("Extracted_Line_Content", "N/A"),
                    "System_Price": match.get("System_Price", "N/A"),
                    "Catalog_Source": match.get("Distributor_Source", "N/A"),
                })
        else:
            matched_results.append({
                "Selected_Tonnage": selected_tonnage,
                "AHRI_Reference_Number": original_ref,
                "Matched_Catalog_Line": "No direct match found in PDF",
                "System_Price": None,
                "Catalog_Source": None,
            })

    results_df = pd.DataFrame(matched_results).drop_duplicates(
        subset=["AHRI_Reference_Number", "System_Price", "Catalog_Source"]
    )

    total_ahri = len(ahri_df)
    priced_matches = results_df["System_Price"].notna().sum()

    st.success(f"⚡ Matching Complete! Found prices for {priced_matches} out of {total_ahri} AHRI records.")

    m1, m2, m3 = st.columns(3)
    m1.metric("Selected Tonnage", selected_tonnage)
    m2.metric("Total AHRI Models", total_ahri)
    m3.metric("Priced Matches Found", priced_matches)

    st.subheader(f"📊 {selected_tonnage} Multi-Distributor Pricing Table")
    st.dataframe(results_df, use_container_width=True)

    # Excel Download Button
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        results_df.to_excel(writer, index=False, sheet_name=f"{selected_tonnage}_Pricing")

    st.download_button(
        label=f"📥 Download {selected_tonnage} Priced Sheet (Excel)",
        data=buffer.getvalue(),
        file_name=f"AHRI_Priced_{selected_tonnage}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )