import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from sklearn.linear_model import LinearRegression
import datetime
import os
import streamlit as st

DATA_FILE = "expenses.csv"

# --- Setup CSV file if not exists ---
def init_setup():
    if not os.path.exists(DATA_FILE):
        df = pd.DataFrame(columns=["Date", "Category", "Amount", "Description"])
        df.to_csv(DATA_FILE, index=False)

# --- Load data ---
def get_expenses():
    return pd.read_csv(DATA_FILE)

# --- Add expense ---
def add_expense(date, category, amount, desc=""):
    df = get_expenses()
    new_row = {"Date": date, "Category": category, "Amount": amount, "Description": desc}
    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    df.to_csv(DATA_FILE, index=False)

# --- View summary ---
def summary_text():
    df = get_expenses()
    if df.empty:
        return "No expenses yet."
    df['Date'] = pd.to_datetime(df['Date'])
    monthly = df.groupby(df['Date'].dt.to_period('M'))['Amount'].sum()
    by_cat = df.groupby('Category')['Amount'].sum()
    return f"Monthly:\n{monthly}\n\nBy Category:\n{by_cat}"

# --- Prediction ---
def predict_expenses():
    df = get_expenses()
    if len(df) < 3:
        return "Not enough data for prediction."
    df['Date'] = pd.to_datetime(df['Date'])
    monthly = df.resample('M', on='Date')['Amount'].sum().reset_index()
    monthly['i'] = range(len(monthly))
    X, y = monthly[['i']], monthly['Amount']
    model = LinearRegression().fit(X, y)
    pred = model.predict([[monthly['i'].max() + 1]])[0]
    return f"Predicted next month expense: ${pred:.2f}"

# --- CLI Mode ---
def cli_mode():
    while True:
        print("\n1.Add 2.Summary 3.Predict 4.Exit")
        choice = input("> ")
        if choice == '1':
            add_expense(input("Date (YYYY-MM-DD): ") or datetime.date.today().isoformat(),
                        input("Category: "), float(input("Amount: ")), input("Desc: "))
        elif choice == '2': print(summary_text())
        elif choice == '3': print(predict_expenses())
        elif choice == '4': break

# --- Web Mode (Streamlit) ---
def web_mode():
    st.title("Expense Tracker")

    menu = st.sidebar.radio("Menu", ["Add Expense", "View Summary", "Predict Expenses"])

    if menu == "Add Expense":
        date = st.date_input("Date", datetime.date.today())
        category = st.text_input("Category")
        amount = st.number_input("Amount", min_value=0.0, step=0.1)
        desc = st.text_area("Description")
        if st.button("Save"):
            add_expense(str(date), category, amount, desc)
            st.success("Expense added!")

    elif menu == "View Summary":
        df = get_expenses()
        if df.empty:
            st.warning("No expenses yet.")
        else:
            st.write(df)
            df['Date'] = pd.to_datetime(df['Date'])
            st.subheader("Monthly Total")
            st.bar_chart(df.groupby(df['Date'].dt.to_period('M'))['Amount'].sum())
            st.subheader("By Category")
            st.bar_chart(df.groupby('Category')['Amount'].sum())

    elif menu == "Predict Expenses":
        st.info(predict_expenses())

# --- Entry Point ---
if __name__ == "__main__":
    init_setup()
    mode = input("Run in (c)ommand line or (w)eb? ").strip().lower()
    if mode == "c":
        cli_mode()
    else:
        # Run with: streamlit run expenses.py
        web_mode()
