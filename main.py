from flask import Flask, render_template, request, redirect
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os

# Google Sheet ID (use your actual sheet ID)
SHEET_ID = "1V0IWGxy_NyTHZwZv0i2xf6bSi-25bSkH5bdKlbzaMYU"  # Change to your sheet ID

app = Flask(__name__)
app.secret_key = "your-secret-key"

# --- Helper to get each worksheet ---
def get_gsheet_tab(tab_name):
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_name('/etc/secrets/creds.json', scope)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(SHEET_ID)
    return sheet.worksheet(tab_name)

# --- Load ALL data from Google Sheets ---
def load_data():
    # BALANCES
    balances_ws = get_gsheet_tab('Balances')
    balances_data = balances_ws.get_all_records()
    balances = {row['Name']: float(row['Amount']) for row in balances_data}

    # RECURRING
    recurring_ws = get_gsheet_tab('Recurring')
    recurring_data = recurring_ws.get_all_records()
    recurring = [
        {
            "name": row["Name"],
            "amount": float(row["Amount"]),
            "account": row["Account"],
            "day": int(row["Day"]),
            "active": str(row["Active"]).upper() == "TRUE"
        }
        for row in recurring_data
    ]

    # ONETIME
    onetime_ws = get_gsheet_tab('Onetime')
    onetime_data = onetime_ws.get_all_records()
    one_time = [
        {
            "name": row["Name"],
            "amount": float(row["Amount"]),
            "account": row["Account"],
            "date": row["Date"]
        }
        for row in onetime_data
    ]

    # PAYCHECKS
    paychecks_ws = get_gsheet_tab('Paychecks')
    paychecks_data = paychecks_ws.get_all_records()
    paychecks = [
        {
            "amount": float(row["Amount"]),
            "date": row["Date"]
        }
        for row in paychecks_data
    ]

    # FORECASTS
    forecasts_ws = get_gsheet_tab('Forecasts')
    forecasts_data = forecasts_ws.get_all_records()
    forecasts = [
        {
            "date": row["Date"],
            "incoming": float(row["Incoming"]),
            "expenses": float(row["Expenses"]),
            "projected": float(row["Projected"])
        }
        for row in forecasts_data
    ]

    return {
        "balances": balances,
        "recurring": recurring,
        "one_time": one_time,
        "paychecks": paychecks,
        "forecasts": forecasts
    }

# --- Save ALL data to Google Sheets ---
def save_data(data):
    # BALANCES
    balances_ws = get_gsheet_tab('Balances')
    balances_list = [[k, v] for k, v in data["balances"].items()]
    balances_ws.clear()
    balances_ws.append_row(['Name', 'Amount'])
    for row in balances_list:
        balances_ws.append_row(row)

    # RECURRING
    recurring_ws = get_gsheet_tab('Recurring')
    recurring_ws.clear()
    recurring_ws.append_row(['Name', 'Amount', 'Account', 'Day', 'Active'])
    for item in data["recurring"]:
        recurring_ws.append_row([
            item["name"], item["amount"], item["account"], item["day"], str(item["active"])
        ])

    # ONETIME
    onetime_ws = get_gsheet_tab('Onetime')
    onetime_ws.clear()
    onetime_ws.append_row(['Name', 'Amount', 'Account', 'Date'])
    for item in data["one_time"]:
        onetime_ws.append_row([
            item["name"], item["amount"], item["account"], item["date"]
        ])

    # PAYCHECKS
    paychecks_ws = get_gsheet_tab('Paychecks')
    paychecks_ws.clear()
    paychecks_ws.append_row(['Amount', 'Date'])
    for item in data["paychecks"]:
        paychecks_ws.append_row([
            item["amount"], item["date"]
        ])

    # FORECASTS
    forecasts_ws = get_gsheet_tab('Forecasts')
    forecasts_ws.clear()
    forecasts_ws.append_row(['Date', 'Incoming', 'Expenses', 'Projected'])
    for item in data["forecasts"]:
        forecasts_ws.append_row([
            item["date"], item["incoming"], item["expenses"], item["projected"]
        ])

# --- Flask Routes (basic version, you can expand with more features) ---

@app.route("/", methods=["GET", "POST"])
def index():
    data = load_data()

    if request.method == "POST":
        # Checking balance update
        if request.form.get("form_type") == "update_balances":
            data["balances"]["Chris"] = float(request.form.get("chris_balance", 0))
            data["balances"]["Angela"] = float(request.form.get("angela_balance", 0))
            save_data(data)
            return redirect("/")

        # Add recurring expense
        elif request.form.get("form_type") == "add_expense":
            new_exp = {
                "name": request.form["name"],
                "amount": float(request.form["amount"]),
                "account": request.form["account"],
                "day": int(request.form["day"]),
                "active": "active" in request.form
            }
            data["recurring"].append(new_exp)
            save_data(data)
            return redirect("/")

        # Add one-time expense
        elif request.form.get("form_type") == "add_onetime":
            new_exp = {
                "name": request.form["name"],
                "amount": float(request.form["amount"]),
                "account": request.form["account"],
                "date": request.form["date"]
            }
            data["one_time"].append(new_exp)
            save_data(data)
            return redirect("/")

        # Add paycheck
        elif request.form.get("form_type") == "add_paycheck":
            new_pay = {
                "amount": float(request.form["amount"]),
                "date": request.form["date"]
            }
            data["paychecks"].append(new_pay)
            save_data(data)
            return redirect("/")

        # Forecast
        elif request.form.get("form_type") == "forecast":
            forecast_date = request.form["forecast_date"]
            # Add your forecast logic here, example placeholder:
            incoming = sum(p["amount"] for p in data["paychecks"] if p["date"] <= forecast_date)
            recurring_exp = sum(e["amount"] for e in data["recurring"] if e["active"])
            onetime_exp = sum(e["amount"] for e in data["one_time"] if e["date"] <= forecast_date)
            total_exp = recurring_exp + onetime_exp
            combined_balance = sum(data["balances"].values())
            projected = combined_balance + incoming - total_exp
            data["forecasts"].append({
                "date": forecast_date,
                "incoming": incoming,
                "expenses": total_exp,
                "projected": projected
            })
            save_data(data)
            return redirect("/")

        # Clear forecast history
        elif request.form.get("form_type") == "clear_forecast":
            data["forecasts"] = []
            save_data(data)
            return redirect("/")

    # Calculate combined balance for display
    combined_balance = sum(data["balances"].values())

    return render_template(
        "index.html",
        chris_balance=data["balances"].get("Chris", 0.0),
        angela_balance=data["balances"].get("Angela", 0.0),
        combined_balance=combined_balance,
        recurring=data["recurring"],
        one_time=data["one_time"],
        paychecks=data["paychecks"],
        forecasts=data["forecasts"]
    )

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
