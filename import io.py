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

if uploaded_ahri:
    xls_ahri = pd.ExcelFile(uploaded_ahri)

    col_t1, _ = st.columns([1, 2])
    with col_t1:
        selected_tonnage = st.selectbox(
            "🎯 Select Tonnage / Capacity Tab:", options=xls_ahri.sheet_names
        )

    # Read without assuming row 1 is a header
    raw_ahri_df = pd.read_excel(uploaded_ahri, sheet_name=selected_tonnage, header=None)

    # Automatically set Column A as AHRI_Reference_Number
    raw_ahri_df = raw_ahri_df.rename(columns={0: "AHRI_Reference_Number"})

    # Standardize AHRI reference keys
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

        # 3. PDF Files
        elif filename.endswith(".pdf"):
            seen_lines = set()
            parsed_pdf_rows = []

            with pdfplumber.open(uploaded_file) as pdf:
                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        for line in text.split("\n"):
                            clean_line = line.strip()
                            if clean_line and clean_line not in seen_lines:
                                seen_lines.add(clean_line)

                                # Extract all price values ($X,XXX.XX) from line
                                prices = re.findall(r"\$\s*([0-9,]+\.\d{2})", clean_line)
                                system_price = prices[-1] if prices else None

                                parsed_pdf_rows.append({
                                    "Extracted_Line_Content": clean_line,
                                    "System_Price": system_price,
                                    "Distributor_Source": filename,
                                })

            if parsed_pdf_rows:
                pdf_df = pd.DataFrame(parsed_pdf_rows)
                distributor_records.append(pdf_df)

    if distributor_records:
        distributor_df = pd.concat(distributor_records, ignore_index=True)
        st.success(
            f"✅ Processed **{len(uploaded_dist_files)}** file(s) with **{len(distributor_df)}** unique catalog rows."
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

        for _, ahri_row in raw_ahri_df.iterrows():
            ahri_num = str(ahri_row["_clean_ahri_key"])

            # Word boundary search to prevent partial matching
            pattern = r"\b" + re.escape(ahri_num) + r"\b"
            matched_lines = distributor_df[
                distributor_df["Extracted_Line_Content"].str.contains(
                    pattern, regex=True, na=False
                )
            ]

            res_row = ahri_row.to_dict()

            if not matched_lines.empty:
                first_match = matched_lines.iloc[0]
                res_row["Matched_Catalog_Line"] = first_match["Extracted_Line_Content"]
                res_row["System_Price"] = first_match["System_Price"]
                res_row["Catalog_Source"] = first_match["Distributor_Source"]
            else:
                res_row["Matched_Catalog_Line"] = "No direct match found in PDF"
                res_row["System_Price"] = None
                res_row["Catalog_Source"] = None

            results.append(res_row)

        matched_results = pd.DataFrame(results)

        # Drop temporary cleaning keys
        matched_results = matched_results.drop(
            columns=["_clean_ahri_key"], errors="ignore"
        )
        matched_results.insert(0, "Selected_Tonnage", selected_tonnage)

        priced_count = matched_results["System_Price"].notna().sum()

        st.success(
            f"✨ Matching Complete! Found prices for **{priced_count}** out of **{len(raw_ahri_df)}** AHRI records."
        )

        # Metrics Summary
        m1, m2, m3 = st.columns(3)
        m1.metric("Selected Tonnage", selected_tonnage)
        m2.metric("Total AHRI Models", len(raw_ahri_df))
        m3.metric("Priced Matches Found", priced_count)

        # Pricing Output Table
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
    st.info(
        "💡 Please upload at least one **Distributor Price List** in Step 2 to view cross-referenced pricing."
    )