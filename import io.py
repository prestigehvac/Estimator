import io
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
        # Tonnage Dropdown Selection
        selected_tonnage = st.selectbox(
            "🎯 Select Tonnage / Capacity Tab:", options=xls_ahri.sheet_names
        )

    # Read selected tonnage tab
    raw_ahri_df = pd.read_excel(uploaded_ahri, sheet_name=selected_tonnage)

    with col_t2:
        # Select Column A / AHRI column
        ahri_col_name = st.selectbox(
            "📌 Select AHRI Reference Column (Defaults to Column A):",
            options=raw_ahri_df.columns,
            index=0,
        )

    # Clean AHRI key column for matching
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

distributor_frames = []

if uploaded_dist_files:
    for uploaded_file in uploaded_dist_files:
        filename = uploaded_file.name
        # 1. Process CSV Files
        if filename.endswith(".csv"):
            df = pd.read_csv(uploaded_file)
            df["Distributor_Source"] = filename
            distributor_frames.append(df)

        # 2. Process Excel Files
        elif filename.endswith((".xlsx", ".xls")):
            xls = pd.ExcelFile(uploaded_file)
            for sheet in xls.sheet_names:
                df = pd.read_excel(uploaded_file, sheet_name=sheet)
                df["Distributor_Source"] = f"{filename} ({sheet})"
                distributor_frames.append(df)

        # 3. Process PDF Files
        elif filename.endswith(".pdf"):
            pdf_rows = []
            with pdfplumber.open(uploaded_file) as pdf:
                for page in pdf.pages:
                    tables = page.extract_tables()
                    for table in tables:
                        for row in table:
                            if any(row):
                                pdf_rows.append(row)
            if pdf_rows:
                pdf_df = pd.DataFrame(pdf_rows[1:], columns=pdf_rows[0])
                pdf_df["Distributor_Source"] = filename
                distributor_frames.append(pdf_df)

    if distributor_frames:
        distributor_df = pd.concat(distributor_frames, ignore_index=True)
        st.success(
            f"✅ Processed **{len(uploaded_dist_files)}** file(s) with **{len(distributor_df)}** total price list rows."
        )
    else:
        distributor_df = None
else:
    distributor_df = None

st.markdown("---")

# --- SECTION 3: MATCHING & DISPLAY RESULTS ---
st.subheader("3️⃣ Step 3: View Pricing Results")

if ahri_df is not None and distributor_df is not None:
    col_m1, col_m2 = st.columns(2)
    with col_m1:
        dist_key_col = st.selectbox(
            "Select Distributor Model / AHRI # Column:",
            options=distributor_df.columns,
        )
    with col_m2:
        dist_price_col = st.selectbox(
            "Select Distributor Price Column:",
            options=distributor_df.columns,
        )

    st.markdown("<br>", unsafe_allow_html=True)

    if st.button(
        "🚀 Match & Fetch Pricing Options",
        type="primary",
        use_container_width=True,
    ):
        # Format distributor key column
        distributor_df["_clean_dist_key"] = (
            distributor_df[dist_key_col]
            .astype(str)
            .str.strip()
            .str.replace(".0", "", regex=False)
        )

        # Merge AHRI records with compiled distributor catalog
        matched_results = pd.merge(
            raw_ahri_df,
            distributor_df,
            left_on="_clean_ahri_key",
            right_on="_clean_dist_key",
            how="left",
        )

        # Drop temporary helper key columns
        matched_results = matched_results.drop(
            columns=["_clean_ahri_key", "_clean_dist_key"], errors="ignore"
        )

        # Tag results with selected tonnage
        matched_results.insert(0, "Selected_Tonnage", selected_tonnage)

        priced_items = matched_results[matched_results[dist_price_col].notna()]

        st.success(
            f"✨ Matching Complete! Found pricing for **{len(priced_items)}** out of **{len(raw_ahri_df)}** AHRI records across uploaded distributors."
        )

        # Summary Metrics Cards
        m1, m2, m3 = st.columns(3)
        m1.metric("Selected Tonnage", selected_tonnage)
        m2.metric("Total AHRI Models", len(raw_ahri_df))
        m3.metric("Priced Matches Found", len(priced_items))

        # Direct Pricing Table
        st.subheader(f"📊 {selected_tonnage} Multi-Distributor Pricing Table")
        st.dataframe(
            matched_results,
            use_container_width=True,
            column_config={
                dist_price_col: st.column_config.NumberColumn(
                    "Price", format="$%.2f"
                )
            },
        )

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
    st.info(
        "💡 Please upload the **Master AHRI Spreadsheet** in Step 1 to begin."
    )
elif distributor_df is None:
    st.info(
        "💡 Please upload at least one **Distributor Price List** in Step 2 to view cross-referenced pricing."
    )