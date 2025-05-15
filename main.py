from flask import Flask, render_template, request, redirect
import json, os
from datetime import datetime
from uuid import uuid4

app = Flask(__name__)
app.secret_key = "your-secret-key"

DATA_FILE = "data.json"

def load_data():
    default_data = {
        "balances": {"Chris": 0.0, "Angela": 0.0},
        "recurring": [],
        "one_time": [],
        "paychecks": [],
        "forecasts": []
    }
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            existing = json.load(f)
            for key in default_data:
                if key not in existing:
                    existing[key] = default_data[key]
            for expense in existing["recurring"]:
                if "active" not in expense:
                    expense["active"] = True
            return existing
    else:
        return default_data

data = load_data()

@app.route("/", methods=["GET", "POST"])
def index():
    global data
    if request.method == "POST":
        form_type = request.form.get("form_type")

        if form_type == "update_balances":
            data["balances"]["Chris"] = float(request.form["chris_balance"])
            data["balances"]["Angela"] = float(request.form["angela_balance"])

        elif form_type == "add_expense":
            expense = {
                "id": str(uuid4()),
                "name": request.form["name"],
                "amount": float(request.form["amount"]),
                "account": request.form["account"],
                "day": int(request.form["day"]),
                "active": "active" in request.form
            }
            data["recurring"].append(expense)

        elif form_type == "delete_expense":
            expense_id = request.form["expense_id"]
            data["recurring"] = [e for e in data["recurring"] if e["id"] != expense_id]

        elif form_type == "toggle_expense":
            expense_id = request.form["expense_id"]
            for e in data["recurring"]:
                if e["id"] == expense_id:
                    e["active"] = not e.get("active", True)

        elif form_type == "add_one_time":
            one_time = {
                "id": str(uuid4()),
                "name": request.form["name"],
                "amount": float(request.form["amount"]),
                "date": request.form["date"],
                "account": request.form["account"]
            }
            data["one_time"].append(one_time)

        elif form_type == "delete_one_time":
            one_time_id = request.form["one_time_id"]
            data["one_time"] = [e for e in data["one_time"] if e["id"] != one_time_id]

        elif form_type == "add_paycheck":
            paycheck = {
                "id": str(uuid4()),
                "amount": float(request.form["pay_amount"]),
                "date": request.form["pay_date"]
            }
            data["paychecks"].append(paycheck)

        elif form_type == "delete_paycheck":
            paycheck_id = request.form["paycheck_id"]
            data["paychecks"] = [p for p in data["paychecks"] if p["id"] != paycheck_id]

        elif form_type == "clear_forecasts":
            data["forecasts"].clear()

        save_data()
        return redirect("/")

    combined_balance = sum(data["balances"].values())
    return render_template("index.html",
                           data=data,
                           combined_balance=combined_balance)

@app.route("/forecast", methods=["POST"])
def forecast():
    global data
    target_date_str = request.form["forecast_date"]
    target_date = datetime.strptime(target_date_str, "%Y-%m-%d").date()
    today = datetime.today().date()

    upcoming_expenses = 0
    for e in data["recurring"]:
        if not e.get("active", True):
            continue
        expense_day = e["day"]
        expense_date = datetime(today.year, today.month, expense_day).date()
        while expense_date <= target_date:
            if expense_date >= today:
                upcoming_expenses += e["amount"]
            if expense_date.month == 12:
                expense_date = datetime(expense_date.year + 1, 1, expense_day).date()
            else:
                expense_date = datetime(expense_date.year, expense_date.month + 1, expense_day).date()

    upcoming_one_time = sum(
        e["amount"] for e in data["one_time"]
        if datetime.strptime(e["date"], "%Y-%m-%d").date() <= target_date
    )

    incoming = sum(p["amount"] for p in data["paychecks"]
                   if datetime.strptime(p["date"], "%Y-%m-%d").date() <= target_date)

    combined_balance = sum(data["balances"].values())
    projected_balance = combined_balance + incoming - (upcoming_expenses + upcoming_one_time)

    forecast_result = {
        "date": target_date_str,
        "incoming": incoming,
        "expenses": upcoming_expenses + upcoming_one_time,
        "projected": projected_balance
    }
    data["forecasts"].append(forecast_result)
    save_data()

    return redirect("/")

def save_data():
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

if __name__ == "__main__":
import os
port = int(os.environ.get("PORT", 10000))
app.run(host="0.0.0.0", port=port)