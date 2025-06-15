import csv
import datetime
import os
import pandas as pd
import matplotlib.pyplot as plt
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from flask import Flask, render_template, request, redirect, url_for
from sklearn.linear_model import LinearRegression
import numpy as np
import sqlite3
from dotenv import load_dotenv
import threading
import time

# Load environment variables
load_dotenv()

# Configuration
DATA_FILE = "expenses.csv"
BUDGET_FILE = "budgets.json"
DB_FILE = "expenses.db"
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASS = os.getenv("EMAIL_PASS")

# Initialize files
def init_files():
    # Create CSV if not exists
    if not os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(["Date", "Category", "Amount", "Description"])
    
    # Create budget file
    if not os.path.exists(BUDGET_FILE):
        with open(BUDGET_FILE, 'w') as f:
            f.write('{"Groceries": 300, "Entertainment": 100, "Utilities": 200}')
    
    # Initialize SQLite database
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS expenses
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                 date TEXT, category TEXT, amount REAL, description TEXT)''')
    conn.commit()
    conn.close()

# Database functions
def add_expense_to_db(date, category, amount, description):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT INTO expenses (date, category, amount, description) VALUES (?, ?, ?, ?)",
              (date, category, amount, description))
    conn.commit()
    conn.close()

def get_expenses_from_db():
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query("SELECT * FROM expenses", conn)
    conn.close()
    return df

# Core functionality
def add_expense():
    """Add new expense with budget check"""
    date = input("Enter date (YYYY-MM-DD) [Today]: ") or datetime.date.today().isoformat()
    category = input("Category: ").title()
    amount = float(input("Amount: $"))
    description = input("Description: ")
    
    # Add to database
    add_expense_to_db(date, category, amount, description)
    
    # Check budget
    check_budget(category, amount)
    
    print("✓ Expense added successfully")

def view_summary():
    """Show monthly summary and category breakdown"""
    df = get_expenses_from_db()
    
    if df.empty:
        print("No expenses found")
        return df
    
    # Monthly summary
    df['Date'] = pd.to_datetime(df['date'])
    df['Month'] = df['Date'].dt.to_period('M')
    monthly = df.groupby('Month')['amount'].sum().reset_index()
    print("\nMonthly Expenses:")
    print(monthly.to_string(index=False))
    
    # Category breakdown
    category_totals = df.groupby('category')['amount'].sum().reset_index()
    print("\nCategory Breakdown:")
    print(category_totals.to_string(index=False))
    
    return df

def generate_chart():
    """Create expense visualization charts"""
    df = get_expenses_from_db()
    
    if df.empty:
        print("No expenses found")
        return
    
    month = input("Enter month to visualize (YYYY-MM): ")
    
    # Filter by month
    df['Date'] = pd.to_datetime(df['date'])
    monthly_expenses = df[df['Date'].dt.strftime('%Y-%m') == month]
    
    if monthly_expenses.empty:
        print("No expenses found for this month")
        return
    
    # Category pie chart
    plt.figure(figsize=(12, 5))
    plt.subplot(1, 2, 1)
    monthly_expenses.groupby('category')['amount'].sum().plot.pie(
        autopct='%1.1f%%', startangle=90
    )
    plt.title(f"Expense Distribution ({month})")
    
    # Daily spending trend
    plt.subplot(1, 2, 2)
    daily_totals = monthly_expenses.groupby('Date')['amount'].sum().reset_index()
    plt.plot(daily_totals['Date'], daily_totals['amount'], marker='o')
    plt.title(f"Daily Spending Trend ({month})")
    plt.xticks(rotation=45)
    plt.tight_layout()
    
    # Save and show
    image_path = f"expense_report_{month}.png"
    plt.savefig(image_path)
    print(f"✓ Chart saved as {image_path}")
    plt.show()
    
    return image_path

# Budget alerts
def get_budgets():
    with open(BUDGET_FILE, 'r') as f:
        return json.load(f)

def check_budget(category, amount):
    budgets = get_budgets()
    if category not in budgets:
        return
    
    # Get current month's expenses for this category
    current_month = pd.Period(datetime.date.today(), freq='M')
    df = get_expenses_from_db()
    
    if not df.empty:
        df['Date'] = pd.to_datetime(df['date'])
        df['Month'] = df['Date'].dt.to_period('M')
        current_month_expenses = df[(df['Month'] == current_month) & (df['category'] == category)]
        total_spent = current_month_expenses['amount'].sum()
    else:
        total_spent = 0
    
    budget = budgets[category]
    
    if total_spent + amount > budget:
        print(f"⚠️ Warning: Adding this expense will exceed your {category} budget (${budget})!")
        print(f"Already spent: ${total_spent}, this expense: ${amount}, total: ${total_spent+amount}")

# Automated email reports
def send_email_report(month, receiver_email, image_path=None):
    """Send expense report via email"""
    df = get_expenses_from_db()
    
    if df.empty:
        print("No expenses to report")
        return
    
    # Generate report text
    monthly_expenses = df[df['date'].str.startswith(month)]
    total = monthly_expenses['amount'].sum()
    category_summary = monthly_expenses.groupby('category')['amount'].sum().to_dict()
    
    # Create email
    msg = MIMEMultipart()
    msg['Subject'] = f"Expense Report for {month}"
    msg['From'] = EMAIL_USER
    msg['To'] = receiver_email
    
    # Create HTML body
    html = f"""<html>
    <body>
        <h1>Expense Report for {month}</h1>
        <p>Total spent: <b>${total:.2f}</b></p>
        <h3>Category Breakdown:</h3>
        <ul>"""
    
    for category, amount in category_summary.items():
        html += f"<li>{category}: ${amount:.2f}</li>"
    
    html += "</ul>"
    
    if image_path:
        html += f'<img src="cid:chart">'
    
    html += "</body></html>"
    
    msg.attach(MIMEText(html, 'html'))
    
    # Attach chart image
    if image_path and os.path.exists(image_path):
        with open(image_path, 'rb') as img:
            mime_img = MIMEImage(img.read())
            mime_img.add_header('Content-ID', '<chart>')
            msg.attach(mime_img)
    
    # Send email
    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(EMAIL_USER, EMAIL_PASS)
            server.send_message(msg)
        print(f"✓ Email sent to {receiver_email}")
    except Exception as e:
        print(f"✗ Failed to send email: {str(e)}")

def automated_reports():
    """Schedule monthly email reports"""
    while True:
        now = datetime.datetime.now()
        # Send on last day of month at 6 PM
        next_month = now.replace(day=28) + datetime.timedelta(days=4)
        last_day = next_month - datetime.timedelta(days=next_month.day)
        report_time = last_day.replace(hour=18, minute=0, second=0, microsecond=0)
        
        if now > report_time:
            # Move to next month
            report_time = report_time.replace(month=report_time.month+1)
        
        wait_seconds = (report_time - now).total_seconds()
        print(f"Next report scheduled for {report_time}")
        time.sleep(wait_seconds)
        
        # Generate and send report
        month = (datetime.date.today() - datetime.timedelta(days=1)).strftime("%Y-%m")
        image_path = generate_chart()
        send_email_report(month, EMAIL_USER, image_path)

# Flask web interface
app = Flask(__name__)

@app.route('/')
def index():
    df = get_expenses_from_db()
    if df.empty:
        return render_template('index.html', expenses=[], total=0)
    
    total = df['amount'].sum()
    return render_template('index.html', expenses=df.to_dict('records'), total=total)

@app.route('/add', methods=['POST'])
def add_expense_web():
    date = request.form['date'] or datetime.date.today().isoformat()
    category = request.form['category']
    amount = float(request.form['amount'])
    description = request.form['description']
    
    add_expense_to_db(date, category, amount, description)
    check_budget(category, amount)
    
    return redirect(url_for('index'))

@app.route('/reports')
def reports():
    df = get_expenses_from_db()
    if df.empty:
        return render_template('reports.html', months=[])
    
    df['Date'] = pd.to_datetime(df['date'])
    df['Month'] = df['Date'].dt.strftime('%Y-%m')
    months = sorted(df['Month'].unique(), reverse=True)
    
    return render_template('reports.html', months=months)

# Expense prediction
def predict_expenses():
    """Predict next month's expenses using linear regression"""
    df = get_expenses_from_db()
    if df.empty or len(df) < 3:
        print("Not enough data for prediction")
        return None
    
    # Prepare data
    df['Date'] = pd.to_datetime(df['date'])
    monthly = df.resample('M', on='Date')['amount'].sum().reset_index()
    monthly['MonthIndex'] = range(len(monthly))
    
    # Train model
    X = monthly[['MonthIndex']]
    y = monthly['amount']
    model = LinearRegression()
    model.fit(X, y)
    
    # Predict next month
    next_month = monthly['MonthIndex'].max() + 1
    prediction = model.predict([[next_month]])[0]
    
    # Plot results
    plt.figure(figsize=(10, 6))
    plt.scatter(monthly['MonthIndex'], monthly['amount'], color='blue', label='Actual')
    plt.plot(monthly['MonthIndex'], model.predict(X), color='red', label='Regression')
    plt.scatter([next_month], [prediction], color='green', s=100, label='Prediction')
    plt.title('Expense Prediction')
    plt.xlabel('Month Index')
    plt.ylabel('Amount ($)')
    plt.legend()
    plt.grid(True)
    
    # Save plot
    image_path = "prediction.png"
    plt.savefig(image_path)
    plt.show()
    
    print(f"Predicted expenses for next month: ${prediction:.2f}")
    return prediction

# Main CLI
def main():
    init_files()
    
    # Start automated reports in background thread
    if EMAIL_USER and EMAIL_PASS:
        report_thread = threading.Thread(target=automated_reports, daemon=True)
        report_thread.start()
    
    while True:
        print("\nEXPENSE TRACKER")
        print("1. Add Expense")
        print("2. View Summary")
        print("3. Generate Charts")
        print("4. Run Web Interface")
        print("5. Predict Next Month")
        print("6. Exit")
        
        choice = input("Select option: ")
        
        if choice == '1':
            add_expense()
        elif choice == '2':
            view_summary()
        elif choice == '3':
            generate_chart()
        elif choice == '4':
            print("Starting web interface at http://localhost:5000")
            app.run(debug=False)
        elif choice == '5':
            predict_expenses()
        elif choice == '6':
            print("Goodbye!")
            break
        else:
            print("Invalid choice")

if __name__ == "__main__":
    main()