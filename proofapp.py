import streamlit as st
import pandas as pd
import re
import io

st.set_page_config(page_title="Account Reconciler", page_icon="📊")

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

# --- Streamlit UI ---
st.title("📊 Account Statement Reconciler")
st.write("Upload your `GL/Account Statement` file to identify matching reversals and unmatched entries.")

uploaded_file = st.file_uploader("Choose an Excel file", type="xlsx")

if uploaded_file:
    try:
        # Load Data
        df = pd.read_excel(uploaded_file, sheet_name=0, parse_dates=['Date'], dtype={'Description': str})
        required_cols = ['Date', 'Reference', 'Description', 'Value', 'Deposit', 'Withdrawal', 'Balance']
        
        if not all(col in df.columns for col in required_cols):
            st.error(f"Missing columns! Required: {', '.join(required_cols)}")
        else:
            # Reconcile Logic
            balance_rows = df[df['Deposit'].isna() & df['Withdrawal'].isna()]
            if balance_rows.empty:
                df_transactions, df_ob, df_cb = df.copy(), pd.DataFrame(), pd.DataFrame()
            else:
                idx_ob, idx_cb = balance_rows.index[0], balance_rows.index[-1]
                df_ob, df_cb = df.loc[[idx_ob]].copy(), df.loc[[idx_cb]].copy()
                df_transactions = df.iloc[idx_ob + 1 : idx_cb].copy()

            # Processing
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

            # Final Assembly
            final_cols = ['Date', 'Reference', 'Description', 'Value', 'Deposit', 'Withdrawal', 'Amount', 'Balance']
            df_unmatched_out = pd.concat([df_ob, df_unmatched.drop(columns=['Match_Key', 'Net_Value']), df_cb])[final_cols]
            df_matched_out = df_matched.sort_values(by='Match_Key').drop(columns=['Match_Key', 'Net_Value'])[final_cols]

            # Output to Excel
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df_unmatched_out.to_excel(writer, sheet_name='Unmatched Statement', index=False)
                df_matched_out.to_excel(writer, sheet_name='Matched Entries', index=False)
                
                # Apply basic formatting
                workbook = writer.book
                cur_fmt = workbook.add_format({'num_format': '#,##0.00'})
                for sheet in writer.sheets.values():
                    sheet.set_column('D:H', 15, cur_fmt)

            st.success("Reconciliation Complete!")
            st.metric("Matched Entries", len(df_matched))
            st.metric("Unmatched Entries", len(df_unmatched))

            st.download_button(
                label="📥 Download Reconciled Excel",
                data=output.getvalue(),
                file_name="Reconciled_Account.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

    except Exception as e:

        st.error(f"An error occurred: {e}")

