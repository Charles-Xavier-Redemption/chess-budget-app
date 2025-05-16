from flask import Flask, render_template, request, redirect, session
import os
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

# ===== GOOGLE SHEETS SETUP =====
SHEET_ID = "1V0IWGxy_NyTHZwZv0i2xf6bSi-25bSkH5bdKlbzaMYU"

def get_gsheet_client():
    creds_path = '/etc/secrets/creds.json' if os.path.exists('/etc/secrets/creds.json') else 'creds.json'
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_name(creds_path, scope)
    client = gspread.authorize(creds)
    return client

def get_gsheet_tab(tab_name):
    client = get_gsheet_client()
    sheet = client.open_by_key(SHEET_ID)
    return sheet.worksheet(tab_name)

def load_data():
    # BALANCES
    balances_ws = get_gsheet_tab('Balances')
    balances_data = balances_ws.get_all_records()
    balances = {}
    for row in balances_data:
        try:
            name = row['Name']
            amount = float(row['Amount'])
            balances[name] = amount
        except (KeyError, ValueError, TypeError):
            continue

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
        for row in recurring_data if row["Amount"] != "" and row["Day"] != ""
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
        for row in onetime_data if row["Amount"] != "" and row["Date"] != ""
    ]

    # PAYCHECKS
    paychecks_ws = get_gsheet_tab('Paychecks')
    paychecks_data = paychecks_ws.get_all_records()
    paychecks = [
        {
            "amount": float(row["Amount"]),
            "date": row["Date"]
        }
        for row in paychecks_data if row["Amount"] != "" and row["Date"] != ""
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
        for row in forecasts_data if row["Date"] != "" and row["Projected"] != ""
    ]
    return {
        "balances": balances,
        "recurring": recurring,
        "one_time": one_time,
        "paychecks": paychecks,
        "forecasts": forecasts
    }

def save_data(data):
    # BALANCES
    balances_ws = get_gsheet_tab('Balances')
    balances_ws.clear()
    balances_ws.append_row(['Name', 'Amount'])
    for k, v in data["balances"].items():
        balances_ws.append_row([k, v])

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

# ===== FLASK & PIN SETUP =====
app = Flask(__name__)
app.secret_key = "super-secret-key"  # CHANGE THIS TO SOMETHING RANDOM/SECRET
PIN_CODE = "1877"  # CHANGE THIS TO YOUR 4-DIGIT PIN

def require_pin(view):
    def wrapped_view(*args, **kwargs):
        if session.get('authenticated'):
            return view(*args, **kwargs)
        if request.method == 'POST' and request.form.get('pin') == PIN_CODE:
            session['authenticated'] = True
            return redirect(request.url)
        return '''
            <form method="post">
                <p>Enter 4-digit PIN: <input type="password" name="pin" maxlength="4" pattern="\\d{4}" autofocus /></p>
                <input type="submit" value="Login" />
            </form>
        '''
    wrapped_view.__name__ = view.__name__
    return wrapped_view

@app.route("/", methods=["GET", "POST"])
@require_pin
def index():
    data = load_data()
    combined_balance = sum(data["balances"].values())
    # Get the latest forecast (by date)
    latest_forecast = None
    if data["forecasts"]:
        latest_forecast = max(data["forecasts"], key=lambda f: f["date"])

    if request.method == "POST":
        form_type = request.form.get("form_type")

        # Update Balances
        if form_type == "update_balances":
            data["balances"]["Chris"] = float(request.form.get("chris_balance", 0))
            data["balances"]["Angela"] = float(request.form.get("angela_balance", 0))
            save_data(data)
            return redirect("/")

        # Add Recurring Expense
        elif form_type == "add_expense":
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

        # Deactivate Recurring
        elif form_type == "deactivate_recurring":
            idx = int(request.form["idx"])
            if 0 <= idx < len(data["recurring"]):
                data["recurring"][idx]["active"] = False
                save_data(data)
            return redirect("/")

        # Delete Recurring
        elif form_type == "delete_recurring":
            idx = int(request.form["idx"])
            if 0 <= idx < len(data["recurring"]):
                del data["recurring"][idx]
                save_data(data)
            return redirect("/")

        # Add One-Time Expense
        elif form_type == "add_onetime":
            new_exp = {
                "name": request.form["name"],
                "amount": float(request.form["amount"]),
                "account": request.form["account"],
                "date": request.form["date"]
            }
            data["one_time"].append(new_exp)
            save_data(data)
            return redirect("/")

        # Add Paycheck
        elif form_type == "add_paycheck":
            new_pay = {
                "amount": float(request.form["amount"]),
                "date": request.form["date"]
            }
            data["paychecks"].append(new_pay)
            save_data(data)
            return redirect("/")

        # Forecast
        elif form_type == "forecast":
            forecast_date = request.form["forecast_date"]
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

        # Clear Forecasts
        elif form_type == "clear_forecast":
            data["forecasts"] = []
            save_data(data)
            return redirect("/")

    return render_template(
        "index.html",
        chris_balance=data["balances"].get("Chris", 0.0),
        angela_balance=data["balances"].get("Angela", 0.0),
        combined_balance=combined_balance,
        recurring=data["recurring"],
        one_time=data["one_time"],
        paychecks=data["paychecks"],
        forecasts=data["forecasts"],
        latest_forecast=latest_forecast
    )

@app.route("/logout")
def logout():
    session.pop('authenticated', None)
    return redirect("/")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
