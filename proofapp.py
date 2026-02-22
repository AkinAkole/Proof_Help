import streamlit as st
import pandas as pd
import re
import io
import plotly.graph_objects as go

# --- Page Configuration ---
st.set_page_config(page_title="Financial Reconciler | Secure Portal", page_icon="🔐", layout="wide")

# --- Authentication Logic ---
def password_entered():
    """Checks whether a password entered by the user is correct."""
    if st.session_state["password"] == st.secrets["access_password"]:
        st.session_state["password_correct"] = True
        del st.session_state["password"] 
    else:
        st.session_state["password_correct"] = False

def check_password():
    """Displays a styled login screen."""
    if "password_correct" not in st.session_state:
        # LANDING PAGE UI
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.markdown("<br><br>", unsafe_allow_view_ Wood=True)
            st.image("https://cdn-icons-png.flaticon.com/512/6165/6165577.png", width=100)
            st.title("Financial Operations Portal")
            st.markdown("""
                ### Welcome back! 
                Please enter your credentials to access the **Account Statement Reconciler**. 
                This tool is restricted to authorized personnel only.
                
                ---
                **Need Help?** Contact the Finance IT department if you've forgotten your access key.
            """)
            st.text_input("Access Key", type="password", on_change=password_entered, key="password", help="Enter the secret key provided by your manager.")
        return False
    elif not st.session_state["password_correct"]:
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.error("🔒 Access Denied. The key you entered is incorrect.")
            st.text_input("Try Again", type="password", on_change=password_entered, key="password")
        return False
    return True

# --- Logic Functions ---
def extract_numeric_key(description):
    if pd.isna(description): return None
    match = re.search(r'\d{8,}', str(description))
    return match.group(0) if match else None

def extract_text_key(description):
    if pd.isna(description): return ''
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
        return f"{text_key}_{round(abs(row['Net_Value']), 2)}"
    return f"NO_KEY_VALUE_{round(row['Net_Value'], 2)}"

# --- Authenticated App Content ---
if check_password():
    # Sidebar Info
    with st.sidebar:
        st.header("Help & Instructions")
        st.markdown("""
        **File Requirements:**
        * Must be an `.xlsx` file.
        * Columns needed: `Date`, `Reference`, `Description`, `Value`, `Deposit`, `Withdrawal`, `Balance`.
        
        **Common Errors:**
        * Date format issues.
        * Missing column headers.
        """)
        if st.button("Logout"):
            st.session_state["password_correct"] = False
            st.rerun()

    st.title("📊 Account Statement Reconciler")
    st.markdown("Automate your matching process with smart reversal detection.")

    uploaded_file = st.file_uploader("Drop your GL/Account Statement file here", type="xlsx")

    if uploaded_file:
        try:
            df = pd.read_excel(uploaded_file, sheet_name=0, parse_dates=['Date'], dtype={'Description': str})
            required_cols = ['Date', 'Reference', 'Description', 'Value', 'Deposit', 'Withdrawal', 'Balance']
            
            if not all(col in df.columns for col in required_cols):
                st.error(f"⚠️ Column Mismatch! The file must have: {', '.join(required_cols)}")
            else:
                # 2. Reconcile Process
                balance_rows = df[df['Deposit'].isna() & df['Withdrawal'].isna()]
                if balance_rows.empty:
                    df_transactions, df_ob, df_cb = df.copy(), pd.DataFrame(), pd.DataFrame()
                else:
                    idx_ob, idx_cb = balance_rows.index[0], balance_rows.index[-1]
                    df_ob, df_cb = df.loc[[idx_ob]].copy(), df.loc[[idx_cb]].copy()
                    df_transactions = df.iloc[idx_ob + 1 : idx_cb].copy()

                df_transactions['Match_Key_Ref'] = df_transactions['Description'].apply(extract_numeric_key)
                df_transactions['Match_Key_Text'] = df_transactions['Description'].apply(extract_text_key)
                df_transactions['Deposit'] = df_transactions['Deposit'].fillna(0)
                df_transactions['Withdrawal'] = df_transactions['Withdrawal'].fillna(0)
                df_transactions['Net_Value'] = df_transactions['Deposit'] - df_transactions['Withdrawal']
                df_transactions['Amount'] = df_transactions['Net_Value']
                df_transactions['Match_Key'] = df_transactions.apply(extract_match_key, axis=1)

                grouped_net = df_transactions.groupby('Match_Key')['Net_Value'].sum()
                matched_keys = grouped_net[grouped_net.round(4) == 0].index.tolist()

                df_matched = df_transactions[df_transactions['Match_Key'].isin(matched_keys)].copy()
                df_unmatched = df_transactions[~df_transactions['Match_Key'].isin(matched_keys)].copy()

                # Dashboard
                st.subheader("Process Summary")
                m1, m2, m3 = st.columns(3)
                m1.metric("Rows Processed", len(df_transactions))
                m2.metric("Matches Found", len(df_matched))
                m3.metric("Unmatched items", len(df_unmatched))

                c1, c2 = st.columns(2)
                with c1:
                    fig_pie = go.Figure(data=[go.Pie(labels=['Matched', 'Unmatched'], 
                                                     values=[len(df_matched), len(df_unmatched)], 
                                                     hole=.4, marker_colors=['#00D1B2', '#FF3860'])])
                    st.plotly_chart(fig_pie, use_container_width=True)
                with c2:
                    unmatched_sum = df_unmatched['Amount'].sum()
                    fig_ind = go.Figure(go.Indicator(mode="number+delta", value=unmatched_sum,
                                                     number={'prefix': "$", 'valueformat': ",.2f"},
                                                     title={"text": "Net Exposure"},
                                                     delta={'reference': 0}))
                    st.plotly_chart(fig_ind, use_container_width=True)

                # Export
                final_cols = ['Date', 'Reference', 'Description', 'Value', 'Deposit', 'Withdrawal', 'Amount', 'Balance']
                df_unmatched_out = pd.concat([df_ob, df_unmatched.drop(columns=['Match_Key', 'Net_Value', 'Match_Key_Ref', 'Match_Key_Text']), df_cb])[final_cols]
                df_matched_out = df_matched.sort_values(by='Match_Key').drop(columns=['Match_Key', 'Net_Value', 'Match_Key_Ref', 'Match_Key_Text'])[final_cols]

                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    df_unmatched_out.to_excel(writer, sheet_name='Unmatched Statement', index=False)
                    df_matched_out.to_excel(writer, sheet_name='Matched Entries', index=False)
                    
                st.download_button(label="📥 Download Reconciled Excel", data=output.getvalue(), 
                                   file_name="Reconciled_Report.xlsx", 
                                   mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                   type="primary")

        except Exception as e:
            st.error(f"An error occurred: {e}")
