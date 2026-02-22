def password_entered():
    """Checks whether a password entered by the user is correct."""
    # This looks for 'access_password' in your Streamlit Cloud settings
    if st.session_state["password"] == st.secrets["access_password"]:
        st.session_state["password_correct"] = True
        del st.session_state["password"] 
    else:
        st.session_state["password_correct"] = False
# --- Page Configuration ---
st.set_page_config(page_title="Account Reconciler", page_icon="📊", layout="wide")

# --- Logic Functions (Your Original Rules) ---
def extract_numeric_key(description):
    if pd.isna(description) or description is None:
        return None
    match = re.search(r'\d{8,}', str(description))
    return match.group(0) if match else None

def extract_text_key(description):
    if pd.isna(description) or description is None:
        return ''
    words = re.findall(r'[A-Z0-9]+', str(description).upper())
    stopwords = {'THE', 'AND', 'OR', 'A', 'AN', 'BUT', 'OF', 'TO', 'FOR', 'WITH', 'ON', 'FROM', 'REVERSAL', 'REF', 'TRF', 'PAYMENT', 'PAID'}
    keywords = [word for word in words if word not in stopwords and len(word) > 2]
    unique_keywords = sorted(list(set(keywords)))
    return ''.join(unique_keywords[:3]) if unique_keywords else ''

def extract_match_key(row):
    if row['Match_Key_Ref'] is not None:
        return row['Match_Key_Ref']
    text_key = row['Match_Key_Text']
    if text_key:
        return text_key + '_' + str(round(abs(row['Net_Value']), 2))
    return 'NO_KEY_VALUE_' + str(round(row['Net_Value'], 2))

# --- Streamlit UI Header ---
st.title("📊 Account Statement Reconciler")
st.markdown("""
Upload your **GL/Account Statement** file. This tool will automatically:
1. Identify matching reversals based on IDs and text patterns.
2. Group entries that net to zero.
3. Provide a downloadable reconciled Excel file.
""")

# --- File Upload ---
uploaded_file = st.file_uploader("Upload Excel File", type="xlsx")

if uploaded_file:
    try:
        # 1. Load Data
        df = pd.read_excel(uploaded_file, sheet_name=0, parse_dates=['Date'], dtype={'Description': str})
        required_cols = ['Date', 'Reference', 'Description', 'Value', 'Deposit', 'Withdrawal', 'Balance']
        
        if not all(col in df.columns for col in required_cols):
            st.error(f"❌ Missing columns! The file must contain: {', '.join(required_cols)}")
        else:
            # 2. Reconcile Logic
            balance_rows = df[df['Deposit'].isna() & df['Withdrawal'].isna()]
            if balance_rows.empty:
                df_transactions, df_ob, df_cb = df.copy(), pd.DataFrame(), pd.DataFrame()
            else:
                idx_ob, idx_cb = balance_rows.index[0], balance_rows.index[-1]
                df_ob, df_cb = df.loc[[idx_ob]].copy(), df.loc[[idx_cb]].copy()
                df_transactions = df.iloc[idx_ob + 1 : idx_cb].copy()

            # 3. Processing & Key Generation
            df_transactions['Match_Key_Ref'] = df_transactions['Description'].apply(extract_numeric_key)
            df_transactions['Match_Key_Text'] = df_transactions['Description'].apply(extract_text_key)
            df_transactions['Deposit'] = df_transactions['Deposit'].fillna(0)
            df_transactions['Withdrawal'] = df_transactions['Withdrawal'].fillna(0)
            df_transactions['Net_Value'] = df_transactions['Deposit'] - df_transactions['Withdrawal']
            df_transactions['Amount'] = df_transactions['Net_Value']
            df_transactions['Match_Key'] = df_transactions.apply(extract_match_key, axis=1)

            # 4. Separate Matched/Unmatched
            grouped_net = df_transactions.groupby('Match_Key')['Net_Value'].sum()
            matched_keys = grouped_net[grouped_net.round(4) == 0].index.tolist()

            df_matched = df_transactions[df_transactions['Match_Key'].isin(matched_keys)].copy()
            df_unmatched = df_transactions[~df_transactions['Match_Key'].isin(matched_keys)].copy()

            # 5. Dashboard Summary
            st.success("✅ Analysis Complete!")
            
            m1, m2, m3 = st.columns(3)
            m1.metric("Total Transactions", len(df_transactions))
            m2.metric("Matched (Netted)", len(df_matched))
            m3.metric("Unmatched", len(df_unmatched))

            # --- Visualizations ---
            col_chart1, col_chart2 = st.columns(2)
            
            with col_chart1:
                fig_pie = go.Figure(data=[go.Pie(
                    labels=['Matched', 'Unmatched'],
                    values=[len(df_matched), len(df_unmatched)],
                    hole=.4,
                    marker_colors=['#2ecc71', '#e74c3c']
                )])
                fig_pie.update_layout(title_text="Transaction Volume Split")
                st.plotly_chart(fig_pie, use_container_width=True)

            with col_chart2:
                unmatched_sum = df_unmatched['Amount'].sum()
                fig_gauge = go.Figure(go.Indicator(
                    mode = "number+delta",
                    value = unmatched_sum,
                    number = {'prefix': "$", 'valueformat': ",.2f"},
                    title = {"text": "Net Unmatched Value"},
                    delta = {'reference': 0, 'relative': False}
                ))
                st.plotly_chart(fig_gauge, use_container_width=True)

            # --- Data Preview ---
            with st.expander("🔍 Preview Unmatched Transactions"):
                st.dataframe(df_unmatched.drop(columns=['Match_Key', 'Net_Value', 'Match_Key_Ref', 'Match_Key_Text']), use_container_width=True)

            # 6. Final Assembly & Excel Export
            final_cols = ['Date', 'Reference', 'Description', 'Value', 'Deposit', 'Withdrawal', 'Amount', 'Balance']
            df_unmatched_out = pd.concat([df_ob, df_unmatched.drop(columns=['Match_Key', 'Net_Value', 'Match_Key_Ref', 'Match_Key_Text']), df_cb])[final_cols]
            df_matched_out = df_matched.sort_values(by='Match_Key').drop(columns=['Match_Key', 'Net_Value', 'Match_Key_Ref', 'Match_Key_Text'])[final_cols]

            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df_unmatched_out.to_excel(writer, sheet_name='Unmatched Statement', index=False)
                df_matched_out.to_excel(writer, sheet_name='Matched Entries', index=False)
                
                # Excel Formatting
                workbook = writer.book
                cur_fmt = workbook.add_format({'num_format': '#,##0.00'})
                date_fmt = workbook.add_format({'num_format': 'dd/mm/yyyy'})
                
                for sheet in writer.sheets.values():
                    sheet.set_column('A:A', 12, date_fmt)
                    sheet.set_column('D:H', 15, cur_fmt)

            st.markdown("---")
            st.download_button(
                label="📥 Download Reconciled Excel File",
                data=output.getvalue(),
                file_name="Reconciled_Account_Report.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary"
            )

    except Exception as e:
        st.error(f"⚠️ Error: {e}")

