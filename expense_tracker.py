import os, csv, json, datetime, time, sqlite3, smtplib, threading
import pandas as pd, matplotlib.pyplot as plt, numpy as np
from flask import Flask, render_template, request, redirect, url_for
from sklearn.linear_model import LinearRegression
from dotenv import load_dotenv
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage


load_dotenv()
DATA_FILE, BUDGET_FILE, DB_FILE = "expenses.csv", "budgets.json", "expenses.db"
SMTP_SERVER, SMTP_PORT = os.getenv("SMTP_SERVER", "smtp.gmail.com"), int(os.getenv("SMTP_PORT", 587))
EMAIL_USER, EMAIL_PASS = os.getenv("EMAIL_USER"), os.getenv("EMAIL_PASS")


def init_setup():
    if not os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'w', newline='') as f: csv.writer(f).writerow(["Date", "Category", "Amount", "Description"])
    if not os.path.exists(BUDGET_FILE):
        json.dump({"Groceries": 300, "Entertainment": 100, "Utilities": 200}, open(BUDGET_FILE, 'w'))
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS expenses
                        (id INTEGER PRIMARY KEY, date TEXT, category TEXT, amount REAL, description TEXT)''')

def db_query(query, params=(), fetch=False):
    with sqlite3.connect(DB_FILE) as conn:
        cur = conn.execute(query, params)
        return pd.DataFrame(cur.fetchall(), columns=[d[0] for d in cur.description]) if fetch else None


def add_expense(date, category, amount, desc):
    db_query("INSERT INTO expenses (date, category, amount, description) VALUES (?, ?, ?, ?)",
             (date, category, amount, desc))
    check_budget(category, amount)

def get_expenses():
    return db_query("SELECT * FROM expenses", fetch=True)


def check_budget(category, amount):
    budgets = json.load(open(BUDGET_FILE))
    if category not in budgets: return
    df = get_expenses()
    if df.empty: return
    df['Date'] = pd.to_datetime(df['date'])
    monthly_spent = df[(df['Date'].dt.to_period('M') == datetime.date.today().strftime('%Y-%m')) &
                       (df['category'] == category)]['amount'].sum()
    if monthly_spent + amount > budgets[category]:
        print(f"⚠️ Over budget for {category}! Spent: ${monthly_spent}, New: ${amount}")


def view_summary():
    df = get_expenses()
    if df.empty: return print("No expenses.")
    df['Date'] = pd.to_datetime(df['date'])
    print("\nMonthly:\n", df.groupby(df['Date'].dt.to_period('M'))['amount'].sum())
    print("\nBy Category:\n", df.groupby('category')['amount'].sum())

def generate_chart(month):
    df = get_expenses()
    if df.empty: return
    df['Date'] = pd.to_datetime(df['date'])
    month_df = df[df['Date'].dt.strftime('%Y-%m') == month]
    if month_df.empty: return print("No data for month.")
    plt.subplot(1, 2, 1)
    month_df.groupby('category')['amount'].sum().plot.pie(autopct='%1.1f%%')
    plt.subplot(1, 2, 2)
    plt.plot(month_df.groupby('Date')['amount'].sum(), marker='o')
    plt.tight_layout()
    path = f"expense_report_{month}.png"
    plt.savefig(path); plt.show()
    return path

def send_email_report(month, receiver, img_path=None):
    df = get_expenses()
    if df.empty: return
    month_df = df[df['date'].str.startswith(month)]
    total = month_df['amount'].sum()
    categories = month_df.groupby('category')['amount'].sum().to_dict()
    msg = MIMEMultipart()
    msg['Subject'], msg['From'], msg['To'] = f"Expense Report {month}", EMAIL_USER, receiver
    html = f"<h1>Total: ${total:.2f}</h1><ul>" + "".join([f"<li>{k}: ${v:.2f}</li>" for k,v in categories.items()]) + "</ul>"
    if img_path: html += '<img src="cid:chart">'
    msg.attach(MIMEText(html, 'html'))
    if img_path:
        with open(img_path, 'rb') as img:
            img_mime = MIMEImage(img.read()); img_mime.add_header('Content-ID', '<chart>'); msg.attach(img_mime)
    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls(); server.login(EMAIL_USER, EMAIL_PASS); server.send_message(msg)


def predict_expenses():
    df = get_expenses()
    if len(df) < 3: return print("Not enough data.")
    df['Date'] = pd.to_datetime(df['date'])
    monthly = df.resample('M', on='Date')['amount'].sum().reset_index()
    monthly['i'] = range(len(monthly))
    X, y = monthly[['i']], monthly['amount']
    model = LinearRegression().fit(X, y)
    pred = model.predict([[monthly['i'].max() + 1]])[0]
    print(f"Next month: ${pred:.2f}")

app = Flask(__name__)
@app.route('/') 
def index(): 
    df = get_expenses()
    return render_template('index.html', expenses=df.to_dict('records'), total=df['amount'].sum() if not df.empty else 0)
@app.route('/add', methods=['POST'])
def add_web():
    add_expense(request.form['date'], request.form['category'], float(request.form['amount']), request.form['description'])
    return redirect(url_for('index'))


def main():
    init_setup()
    while True:
        print("\n1.Add 2.Summary 3.Chart 4.Web 5.Predict 6.Exit")
        choice = input("> ")
        if choice == '1':
            add_expense(input("Date: ") or datetime.date.today().isoformat(),
                        input("Category: "), float(input("Amount: ")), input("Desc: "))
        elif choice == '2': view_summary()
        elif choice == '3': generate_chart(input("Month YYYY-MM: "))
        elif choice == '4': app.run()
        elif choice == '5': predict_expenses()
        elif choice == '6': break

if __name__ == "__main__":
    main()
