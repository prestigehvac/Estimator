import io
import re
import pandas as pd
import pdfplumber
import streamlit as st

# Page Configuration
st.set_page_config(
    page_title="AHRI & Distributor Pricing Matcher", layout="wide"
)

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
ahri_col_name = None

if uploaded_ahri:
    xls_ahri = pd.ExcelFile(uploaded_ahri)

    col_t1, col_t2 = st.columns([1, 2])
    with col_t1:
        selected_tonnage = st.selectbox(
            "🎯 Select Tonnage / Capacity Tab:", options=xls_ahri.sheet_names
        )

    raw_ahri_df = pd.read_excel(uploaded_ahri, sheet_name=selected_tonnage)

    with col_t2:
        ahri_col_name = st.selectbox(
            "📌 Select AHRI Reference Column (Defaults to Column A):",
            options=raw_ahri_df.columns,
            index=0,
        )

    # Standardize AHRI reference keys
    raw_ahri_df["_clean_ahri_key"] = (
        raw_ahri_df[ahri_col_name]
        .astype(str)
        .str.strip()
        .str.replace(".0", "", regex=False)
    )
    ahri_df = raw_ahri_df.dropna(subset=[ahri_col_name])

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

        # 3. PDF Files (Full Line-by-Line Parsing)
        elif filename.endswith(".pdf"):
            pdf_lines = []
            with pdfplumber.open(uploaded_file) as pdf:
                for page in pdf.pages:
                    # A. Table Extraction
                    tables = page.extract_tables()
                    for table in tables:
                        for row in table:
                            if row:
                                clean_row = [str(c).strip() for c in row if c is not None]
                                if clean_row:
                                    pdf_lines.append(" | ".join(clean_row))

                    # B. Full Page Text Extraction
                    text = page.extract_text()
                    if text:
                        for line in text.split("\n"):
                            if line.strip():
                                pdf_lines.append(line.strip())

            # Convert PDF extracted lines into a structured DataFrame
            parsed_pdf_rows = []
            for line in pdf_lines:
                # Find price pattern ($X,XXX.XX or XXX.XX)
                price_match = re.search(r"\$?\s*([0-9,]+\.\d{2})", line)
                price_val = price_match.group(1) if price_match else None
                
                parsed_pdf_rows.append({
                    "Extracted_Line_Content": line,
                    "Detected_Price": price_val,
                    "Distributor_Source": filename
                })

            if parsed_pdf_rows:
                pdf_df = pd.DataFrame(parsed_pdf_rows)
                distributor_records.append(pdf_df)

    if distributor_records:
        distributor_df = pd.concat(distributor_records, ignore_index=True)
        st.success(
            f"✅ Processed **{len(uploaded_dist_files)}** file(s) with **{len(distributor_df)}** extracted distributor lines."
        )
    else:
        distributor_df = None
else:
    distributor_df = None

st.markdown("---")

# --- SECTION 3: MATCHING & DISPLAY RESULTS ---
st.subheader("3️⃣ Step 3: View Pricing Results")

if ahri_df is not None and distributor_df is not None:

    if st.button(
        "🚀 Match & Fetch Pricing Options",
        type="primary",
        use_container_width=True,
    ):
        results = []

        # Perform substring searching across all extracted PDF catalog lines
        for _, ahri_row in raw_ahri_df.iterrows():
            ahri_num = str(ahri_row["_clean_ahri_key"])
            
            # Find matching lines containing the AHRI or Model number
            matched_lines = distributor_df[
                distributor_df["Extracted_Line_Content"].str.contains(ahri_num, case=False, na=False)
            ]

            if not matched_lines.empty:
                for _, dist_row in matched_lines.iterrows():
                    res_row = ahri_row.to_dict()
                    res_row["Matched_Catalog_Line"] = dist_row["Extracted_Line_Content"]
                    res_row["Distributor_Price"] = dist_row["Detected_Price"]
                    res_row["Catalog_Source"] = dist_row["Distributor_Source"]
                    results.append(res_row)
            else:
                res_row = ahri_row.to_dict()
                res_row["Matched_Catalog_Line"] = "No direct match found in PDF"
                res_row["Distributor_Price"] = None
                res_row["Catalog_Source"] = None
                results.append(res_row)

        matched_results = pd.DataFrame(results)

        # Drop temporary keys
        matched_results = matched_results.drop(columns=["_clean_ahri_key"], errors="ignore")
        matched_results.insert(0, "Selected_Tonnage", selected_tonnage)

        priced_count = matched_results["Distributor_Price"].notna().sum()

        st.success(
            f"✨ Matching Complete! Found matches for **{priced_count}** out of **{len(raw_ahri_df)}** AHRI records."
        )

        # Metrics
        m1, m2, m3 = st.columns(3)
        m1.metric("Selected Tonnage", selected_tonnage)
        m2.metric("Total AHRI Models", len(raw_ahri_df))
        m3.metric("Priced Matches Found", priced_count)

        # Output Table
        st.subheader(f"📊 {selected_tonnage} Multi-Distributor Pricing Table")
        st.dataframe(matched_results, use_container_width=True)

        # Excel Download
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
            matched_results.to_excel(
                writer, sheet_name=f"{selected_tonnage}_Priced", index=False
            )

        st.download_button(
            label=f"📥 Download {selected_tonnage} Priced Sheet (Excel)",
            data=output.getvalue(),
            file_name=f"AHRI_{selected_tonnage}_Pricing.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

elif ahri_df is None:
    st.info("💡 Please upload the **Master AHRI Spreadsheet** in Step 1 to begin.")
elif distributor_df is None:
    st.info("💡 Please upload at least one **Distributor Price List** in Step 2 to view cross-referenced pricing.")