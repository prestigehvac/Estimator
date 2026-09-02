import io
import re
import pandas as pd
import pdfplumber
import streamlit as st

# Page Configuration
st.set_page_config(
    page_title="Spreadsheet Pricing Cross-Referencer", layout="wide"
)

st.title("📊 Spreadsheet Pricing Cross-Referencer")
st.write(
    "Cross-reference product/part numbers against a master database or PDF price list."
)

# --- SIDEBAR: DATABASE / SOURCE DATA UPLOAD ---
st.sidebar.header("1. Master Source Data")
source_type = st.sidebar.radio(
    "Select Source Data Format:", ("Database / Excel / CSV", "PDF Price List")
)

master_df = None

if source_type == "Database / Excel / CSV":
    uploaded_master = st.sidebar.file_uploader(
        "Upload Master Price List (CSV or XLSX)", type=["csv", "xlsx"]
    )
    if uploaded_master:
        if uploaded_master.name.endswith(".csv"):
            master_df = pd.read_csv(uploaded_master)
        else:
            # Allows selecting tab in master excel if needed
            xls = pd.ExcelFile(uploaded_master)
            master_sheet = st.sidebar.selectbox(
                "Select Master Sheet:", xls.sheet_names
            )
            master_df = pd.read_excel(uploaded_master, sheet_name=master_sheet)

elif source_type == "PDF Price List":
    uploaded_pdf = st.sidebar.file_uploader(
        "Upload PDF Price List", type=["pdf"]
    )
    if uploaded_pdf:
        # Extract text/tables from PDF
        pdf_rows = []
        with pdfplumber.open(uploaded_pdf) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables()
                for table in tables:
                    for row in table:
                        if any(
                            row
                        ):  # filter empty rows                    pdf_rows.append(row)

        if pdf_rows:
            # Assume first row as header if non-numeric
            master_df = pd.DataFrame(pdf_rows[1:], columns=pdf_rows[0])
            st.sidebar.success(f"Extracted {len(master_df)} rows from PDF.")
        else:
            st.sidebar.error("Could not automatically extract tables from PDF.")

# --- MAIN SECTION: WORKING SPREADSHEET UPLOAD ---
st.header("2. Target Spreadsheet")
uploaded_target = st.file_uploader(
    "Upload the spreadsheet containing numbers to look up", type=["xlsx"]
)

if uploaded_target:
    xls_target = pd.ExcelFile(uploaded_target)

    # Use bottom tabs as parameter (e.g., "2-Ton", "2.5-Ton", "3-Ton")
    st.subheader("Select Search Parameter (Tab)")
    selected_tab = st.radio(
        "Choose Sheet / Capacity Tab:",
        options=xls_target.sheet_names,
        horizontal=True,
    )

    # Read selected sheet
    target_df = pd.read_excel(uploaded_target, sheet_name=selected_tab)

    st.write(
        f"**Preview of selected tab (`{selected_tab}`):**",
        target_df.head(),
    )

    # Select Key Column
    target_key_col = st.selectbox(
        "Select Column containing Part/Model Numbers to match:",
        options=target_df.columns,
    )

    # --- LOOKUP & QUERY SECTION ---
    if master_df is not None:
        st.markdown("---")
        st.header("3. Run Cross-Reference & Pricing Query")

        col1, col2 = st.columns(2)
        with col1:
            master_key_col = st.selectbox(
                "Master Source Key Column (Part/Model #):",
                options=master_df.columns,
            )
        with col2:
            master_price_col = st.selectbox(
                "Master Source Price Column:", options=master_df.columns
            )

        # Quick Search / Query Box
        query_input = st.text_input(
            "🔍 Quick Query Box (Type a number to test direct lookup):"
        )
        if query_input:
            match = master_df[
                master_df[master_key_col].astype(str).str.contains(query_input)
            ]
            st.write("Query Result:", match)

        # Execute Batch Merge
        if st.button("🚀 Cross-Reference & Merge Pricing Data"):
            # Ensure string matching format
            target_df[target_key_col] = (
                target_df[target_key_col].astype(str).str.strip()
            )
            master_df[master_key_col] = (
                master_df[master_key_col].astype(str).str.strip()
            )

            # Perform merge
            result_df = pd.merge(
                target_df,
                master_df[[master_key_col, master_price_col]],
                left_on=target_key_col,
                right_on=master_key_col,
                how="left",
            )

            # Tag with parameter tab
            result_df["Capacity_Parameter"] = selected_tab

            st.success("Matching Complete!")
            st.dataframe(result_df)

            # Export to Excel Download
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
                result_df.to_excel(writer, sheet_name=selected_tab, index=False)

            st.download_button(
                label="📥 Download Updated Spreadsheet",
                data=output.getvalue(),
                file_name=f"priced_{selected_tab}_output.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
    else:
        st.info(
            "Please upload a Master Price List on the sidebar to enable cross-referencing."
        )