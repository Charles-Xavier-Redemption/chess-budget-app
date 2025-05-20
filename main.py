from flask import Flask, render_template, request, redirect, session
import os
import psycopg2
from datetime import datetime, date, time
import calendar

app = Flask(__name__)
app.secret_key = "super-secret-key"
PIN_CODE = "1877"

DATABASE_URL = os.environ.get("DATABASE_URL")

def get_db_conn():
    return psycopg2.connect(DATABASE_URL)

# ========== LOAD DATA FROM DATABASE ==========

def load_data():
    conn = get_db_conn()
    cur = conn.cursor()

    cur.execute("SELECT name, amount FROM balances")
    balances = {row[0]: float(row[1]) for row in cur.fetchall()}

    cur.execute("SELECT name, amount, account, day, active, chasecard, chargeday FROM recurring")
    recurring = []
    for row in cur.fetchall():
        recurring.append({
            "name": row[0],
            "amount": float(row[1]),
            "account": row[2],
            "day": int(row[3]),
            "active": row[4],
            "chasecard": row[5],
            "chargeday": row[6]
        })

    cur.execute("SELECT name, amount, account, date FROM onetime")
    one_time = [{"name": row[0], "amount": float(row[1]), "account": row[2], "date": str(row[3])} for row in cur.fetchall()]

    cur.execute("SELECT amount, date, active FROM paychecks")
    paychecks = [{"amount": float(row[0]), "date": str(row[1]), "active": row[2]} for row in cur.fetchall()]

    cur.execute("SELECT amount, balance_as_of FROM chase_balance ORDER BY balance_as_of DESC LIMIT 1")
    row = cur.fetchone()
    chase_balance = float(row[0]) if row else 0.0
    chase_balance_date = row[1] if row else None

    cur.execute("SELECT date, incoming, expenses, projected FROM forecasts ORDER BY date ASC")
    forecasts = [{"date": str(row[0]), "incoming": float(row[1]), "expenses": float(row[2]), "projected": float(row[3])} for row in cur.fetchall()]

    cur.close()
    conn.close()

    return {
        "balances": balances,
        "recurring": recurring,
        "one_time": one_time,
        "paychecks": paychecks,
        "forecasts": forecasts,
        "chase_balance": chase_balance,
        "chase_balance_date": chase_balance_date
    }

# ========== SAVE DATA TO DATABASE ==========

def save_balances(balances):
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM balances")
    for k, v in balances.items():
        cur.execute("INSERT INTO balances (name, amount) VALUES (%s, %s)", (k, v))
    conn.commit()
    cur.close()
    conn.close()

def save_recurring(recurring):
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM recurring")
    for r in recurring:
        cur.execute("INSERT INTO recurring (name, amount, account, day, active, chasecard, chargeday) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (r["name"], r["amount"], r["account"], r["day"], r["active"], r["chasecard"], r.get("chargeday")))
    conn.commit()
    cur.close()
    conn.close()

def save_onetime(one_time):
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM onetime")
    for o in one_time:
        cur.execute("INSERT INTO onetime (name, amount, account, date) VALUES (%s, %s, %s, %s)",
                    (o["name"], o["amount"], o["account"], o["date"]))
    conn.commit()
    cur.close()
    conn.close()

def save_paychecks(paychecks):
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM paychecks")
    for p in paychecks:
        cur.execute("INSERT INTO paychecks (amount, date, active) VALUES (%s, %s, %s)",
                    (p["amount"], p["date"], p["active"]))
    conn.commit()
    cur.close()
    conn.close()

def save_chase_balance(amount, balance_as_of):
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM chase_balance")
    cur.execute("INSERT INTO chase_balance (amount, balance_as_of) VALUES (%s, %s)",
                (amount, balance_as_of))
    conn.commit()
    cur.close()
    conn.close()

def save_forecasts(forecasts):
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM forecasts")
    for f in forecasts:
        cur.execute("INSERT INTO forecasts (date, incoming, expenses, projected) VALUES (%s, %s, %s, %s)",
                    (f["date"], f["incoming"], f["expenses"], f["projected"]))
    conn.commit()
    cur.close()
    conn.close()

def save_data(data):
    save_balances(data["balances"])
    save_recurring(data["recurring"])
    save_onetime(data["one_time"])
    save_paychecks(data["paychecks"])
    save_forecasts(data["forecasts"])
    if data["chase_balance"] is not None and data["chase_balance_date"] is not None:
        save_chase_balance(data["chase_balance"], data["chase_balance_date"])

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
    if "recurring_chase_shown" not in session:
        session["recurring_chase_shown"] = False
    if "recurring_other_shown" not in session:
        session["recurring_other_shown"] = False

    data = load_data()
    combined_balance = sum(data["balances"].values())
    chase_balance = data["chase_balance"]
    chase_balance_date = data["chase_balance_date"]

    if chase_balance_date and isinstance(chase_balance_date, date) and not isinstance(chase_balance_date, datetime):
        chase_balance_date = datetime.combine(chase_balance_date, time.min)

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
    chase_recurring_total = sum(item["amount"] for item in data["recurring"] if item["chasecard"] and item["active"])
    nonchase_recurring_total = sum(item["amount"] for item in data["recurring"] if not item["chasecard"] and item["active"])

    if request.method == "POST":
        form_type = request.form.get("form_type")

        if form_type == "toggle_recurring_chase":
            session["recurring_chase_shown"] = not session.get("recurring_chase_shown", False)
            return redirect("/")
        if form_type == "toggle_recurring_other":
            session["recurring_other_shown"] = not session.get("recurring_other_shown", False)
            return redirect("/")

        # === BALANCES ===
        if form_type == "update_balances":
            data["balances"]["Chris"] = float(request.form.get("chris_balance", 0))
            data["balances"]["Angela"] = float(request.form.get("angela_balance", 0))
            save_balances(data["balances"])
            return redirect("/")

        # === CHASE BALANCE ===
        elif form_type == "update_chase_balance":
            new_chase = float(request.form.get("chase_balance", 0))
            today_str = datetime.today().strftime("%Y-%m-%d")
            save_chase_balance(new_chase, today_str)
            return redirect("/")

        # === RECURRING ===
        elif form_type == "add_expense":
            account_or_chase = request.form["account"]
            is_chase = account_or_chase == "Chase"
            chargeday = request.form.get("chargeday") if is_chase else None
            # Fallback to "day" field if chargeday is empty or not provided
            if is_chase and (not chargeday or chargeday == ""):
                chargeday = request.form["day"]
            new_exp = {
                "name": request.form["name"],
                "amount": float(request.form["amount"]),
                "account": None if is_chase else account_or_chase,
                "day": int(request.form["day"]),
                "active": "active" in request.form,
                "chasecard": is_chase,
                "chargeday": int(chargeday) if is_chase and chargeday is not None else None,
            }
            data["recurring"].append(new_exp)
            save_recurring(data["recurring"])
            return redirect("/")

        elif form_type == "activate_recurring":
            idx = int(request.form["idx"])
            if 0 <= idx < len(data["recurring"]):
                data["recurring"][idx]["active"] = True
                save_recurring(data["recurring"])
            return redirect("/")

        elif form_type == "deactivate_recurring":
            idx = int(request.form["idx"])
            if 0 <= idx < len(data["recurring"]):
                data["recurring"][idx]["active"] = False
                save_recurring(data["recurring"])
            return redirect("/")

        elif form_type == "delete_recurring":
            idx = int(request.form["idx"])
            if 0 <= idx < len(data["recurring"]):
                del data["recurring"][idx]
                save_recurring(data["recurring"])
            return redirect("/")

        # === ONETIME ===
        elif form_type == "add_onetime":
            new_exp = {
                "name": request.form["name"],
                "amount": float(request.form["amount"]),
                "account": request.form["account"],
                "date": request.form["date"]
            }
            data["one_time"].append(new_exp)
            save_onetime(data["one_time"])
            return redirect("/")

        # === PAYCHECKS ===
        elif form_type == "add_paycheck":
            new_pay = {
                "amount": float(request.form["amount"]),
                "date": request.form["date"],
                "active": True
            }
            data["paychecks"].append(new_pay)
            save_paychecks(data["paychecks"])
            return redirect("/")

        elif form_type == "activate_paycheck":
            idx = int(request.form["idx"])
            if 0 <= idx < len(data["paychecks"]):
                data["paychecks"][idx]["active"] = True
                save_paychecks(data["paychecks"])
            return redirect("/")

        elif form_type == "deactivate_paycheck":
            idx = int(request.form["idx"])
            if 0 <= idx < len(data["paychecks"]):
                data["paychecks"][idx]["active"] = False
                save_paychecks(data["paychecks"])
            return redirect("/")

        elif form_type == "delete_paycheck":
            idx = int(request.form["idx"])
            if 0 <= idx < len(data["paychecks"]):
                del data["paychecks"][idx]
                save_paychecks(data["paychecks"])
            return redirect("/")

        # === CLEAR FORECASTS ===
        elif form_type == "clear_forecast":
            data["forecasts"] = []
            save_forecasts(data["forecasts"])
            return redirect("/")

        # === FORECAST LOGIC (same as before) ===
        elif form_type == "forecast":
            forecast_date = request.form["forecast_date"]
            forecast_end = datetime.strptime(forecast_date, "%Y-%m-%d")
            incoming = sum(
                p["amount"] for p in data["paychecks"]
                if p["active"] and p["date"] <= forecast_date
            )
            onetime_exp = sum(e["amount"] for e in data["one_time"] if e["date"] <= forecast_date)
            recurring_exp = 0.0
            chase_recurring_exp = 0.0
            for exp in data["recurring"]:
                if not exp["active"]:
                    continue
                day = int(exp["day"])
                amount = float(exp["amount"])
                is_chase = exp.get("chasecard", False)
                charge_day = int(exp.get("chargeday") or day)
                next_date = get_next_occurrence(charge_day, today)
                if is_chase and chase_balance_date:
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
            projected = (combined_balance - recurring_exp - onetime_exp) + incoming - chase_recurring_exp - chase_balance
            data["forecasts"].append({
                "date": forecast_date,
                "incoming": incoming,
                "expenses": recurring_exp + onetime_exp + chase_recurring_exp + chase_balance,
                "projected": projected
            })
            save_forecasts(data["forecasts"])
            return redirect("/")

    latest_forecast = data["forecasts"][-1] if data["forecasts"] else None

    return render_template(
        "index.html",
        chris_balance=data["balances"].get("Chris", 0.0),
        angela_balance=data["balances"].get("Angela", 0.0),
        combined_balance=combined_balance,
        chase_balance=chase_balance,
        chase_balance_date=chase_balance_date,
        recurring=data["recurring"],
        one_time=data["one_time"],
        paychecks=data["paychecks"],
        forecasts=data["forecasts"],
        latest_forecast=latest_forecast,
        month_recurring_total=month_recurring_total,
        month_paycheck_total=month_paycheck_total,
        chase_recurring_total=chase_recurring_total,
        nonchase_recurring_total=nonchase_recurring_total,
        recurring_chase_shown=session.get("recurring_chase_shown", False),
        recurring_other_shown=session.get("recurring_other_shown", False)
    )

@app.route("/logout")
def logout():
    session.pop('authenticated', None)
    return redirect("/")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
