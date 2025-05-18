from flask import Flask, render_template, request, redirect, session
import os
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
import calendar

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
            "active": str(row["Active"]).upper() == "TRUE",
            "chasecard": str(row.get("ChaseCard", "No")).strip().lower() == "yes",
            "chargeday": int(str(row.get("ChargeDay", "")).strip()) if str(row.get("ChargeDay", "")).strip() != "" else None,
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
            "date": row["Date"],
            "active": str(row.get("Active", "TRUE")).upper() == "TRUE"
        }
        for row in paychecks_data if row["Amount"] != "" and row["Date"] != ""
    ]

    # CHASE BALANCE (grab both amount and balance date)
    chase_ws = get_gsheet_tab('ChaseBalance')
    chase_data = chase_ws.get_all_records()
    chase_balance = 0.0
    chase_balance_date = None
    for row in chase_data:
        if row['Name'].strip().lower() == 'chase':
            chase_balance = float(row['Amount'])
            if row.get('BalanceAsOf'):
                chase_balance_date = datetime.strptime(row['BalanceAsOf'], "%Y-%m-%d")
            break

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
        "forecasts": forecasts,
        "chase_balance": chase_balance,
        "chase_balance_date": chase_balance_date
    }

def save_data(data):
    balances_ws = get_gsheet_tab('Balances')
    balances_ws.clear()
    balances_ws.append_row(['Name', 'Amount'])
    for k, v in data["balances"].items():
        balances_ws.append_row([k, v])

    recurring_ws = get_gsheet_tab('Recurring')
    recurring_ws.clear()
    recurring_ws.append_row(['Name', 'Amount', 'Account', 'Day', 'Active', 'ChaseCard', 'ChargeDay'])
    for item in data["recurring"]:
        recurring_ws.append_row([
            item["name"], item["amount"], item["account"], item["day"],
            str(item["active"]), "Yes" if item.get("chasecard") else "No", item.get("chargeday") or ""
        ])

    onetime_ws = get_gsheet_tab('Onetime')
    onetime_ws.clear()
    onetime_ws.append_row(['Name', 'Amount', 'Account', 'Date'])
    for item in data["one_time"]:
        onetime_ws.append_row([
            item["name"], item["amount"], item["account"], item["date"]
        ])

    paychecks_ws = get_gsheet_tab('Paychecks')
    paychecks_ws.clear()
    paychecks_ws.append_row(['Amount', 'Date', 'Active'])
    for item in data["paychecks"]:
        paychecks_ws.append_row([
            item["amount"], item["date"], str(item.get("active", True))
        ])

    forecasts_ws = get_gsheet_tab('Forecasts')
    forecasts_ws.clear()
    forecasts_ws.append_row(['Date', 'Incoming', 'Expenses', 'Projected'])
    for item in data["forecasts"]:
        forecasts_ws.append_row([
            item["date"], item["incoming"], item["expenses"], item["projected"]
        ])

app = Flask(__name__)
app.secret_key = "super-secret-key"
PIN_CODE = "1877"

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

def get_next_occurrence(recurring_day, base_date):
    year, month = base_date.year, base_date.month
    if base_date.day < recurring_day:
        return datetime(year, month, recurring_day)
    else:
        if month == 12:
            year += 1
            month = 1
        else:
            month += 1
        try:
            return datetime(year, month, recurring_day)
        except ValueError:
            last_day = calendar.monthrange(year, month)[1]
            return datetime(year, month, last_day)

@app.route("/", methods=["GET", "POST"])
@require_pin
def index():
    data = load_data()
    combined_balance = sum(data["balances"].values())
    chase_balance = data["chase_balance"]
    chase_balance_date = data["chase_balance_date"]

    # Calculate summary totals for current month
    today = datetime.today()
    current_month = today.strftime('%Y-%m')
    month_recurring_total = sum(
        float(item["amount"])
        for item in data["recurring"]
        if item["active"] and int(item["day"]) >= 1 and int(item["day"]) <= calendar.monthrange(today.year, today.month)[1]
    )
    month_paycheck_total = sum(
        float(p["amount"])
        for p in data["paychecks"]
        if p["active"] and p["date"].startswith(current_month)
    )

    if request.method == "POST":
        form_type = request.form.get("form_type")

        # --- [Copy your CRUD for balances, recurring, onetime, paychecks here] ---

        # Forecast with Chase logic (advanced, no double-count)
        if form_type == "forecast":
            forecast_date = request.form["forecast_date"]
            forecast_end = datetime.strptime(forecast_date, "%Y-%m-%d")

            # Only active paychecks up to forecast date
            incoming = sum(
                p["amount"] for p in data["paychecks"]
                if p["active"] and p["date"] <= forecast_date
            )

            # One-time expenses (before or on forecast date)
            onetime_exp = sum(e["amount"] for e in data["one_time"] if e["date"] <= forecast_date)

            # Recurring expenses: 
            #  - ChaseCard: only count charges that hit Chase *after* ChaseBalance BalanceAsOf date
            #  - Non-ChaseCard: count as usual
            recurring_exp = 0.0
            chase_recurring_exp = 0.0
            for exp in data["recurring"]:
                if not exp["active"]:
                    continue
                day = int(exp["day"])
                amount = float(exp["amount"])
                is_chase = exp.get("chasecard", False)
                charge_day = int(exp.get("chargeday") or day)
                # Start date for recurring charges:
                next_date = get_next_occurrence(charge_day, today)
                # For ChaseCard, start at the later of chase_balance_date or today
                if is_chase and chase_balance_date:
                    base_start = chase_balance_date
                    # Move to the first charge *after* the chase_balance_date
                    while next_date <= chase_balance_date:
                        year, month = next_date.year, next_date.month
                        if month == 12:
                            year += 1
                            month = 1
                        else:
                            month += 1
                        try:
                            next_date = datetime(year, month, charge_day)
                        except ValueError:
                            last_day = calendar.monthrange(year, month)[1]
                            next_date = datetime(year, month, last_day)
                while next_date <= forecast_end:
                    if is_chase:
                        chase_recurring_exp += amount
                    else:
                        recurring_exp += amount
                    year, month = next_date.year, next_date.month
                    if month == 12:
                        year += 1
                        month = 1
                    else:
                        month += 1
                    try:
                        next_date = datetime(year, month, charge_day)
                    except ValueError:
                        last_day = calendar.monthrange(year, month)[1]
                        next_date = datetime(year, month, last_day)

            # FINAL LOGIC:
            # - Subtract all Chase charges *after* balance date from forecast
            # - Subtract Chase balance itself
            # - Subtract regular recurring, onetime as usual
            projected = (combined_balance - recurring_exp - onetime_exp) + incoming - chase_recurring_exp - chase_balance
            data["forecasts"].append({
                "date": forecast_date,
                "incoming": incoming,
                "expenses": recurring_exp + onetime_exp + chase_recurring_exp + chase_balance,
                "projected": projected
            })
            save_data(data)
            return redirect("/")

    latest_forecast = data["forecasts"][-1] if data["forecasts"] else None

    return render_template(
        "index.html",
        chris_balance=data["balances"].get("Chris", 0.0),
        angela_balance=data["balances"].get("Angela", 0.0),
        combined_balance=combined_balance,
        chase_balance=chase_balance,
        recurring=data["recurring"],
        one_time=data["one_time"],
        paychecks=data["paychecks"],
        forecasts=data["forecasts"],
        latest_forecast=latest_forecast,
        month_recurring_total=month_recurring_total,
        month_paycheck_total=month_paycheck_total
    )

@app.route("/logout")
def logout():
    session.pop('authenticated', None)
    return redirect("/")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
