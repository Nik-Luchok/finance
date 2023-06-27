import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import login_required, lookup, usd

app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    # load user cash and stocks from db
    stocks = db.execute("""SELECT *
                           FROM stocks
                           WHERE user_id = ?""",
                        session["user_id"]
                        )
    cash = db.execute("""SELECT cash
                         FROM users
                         WHERE id = ?""",
                      session["user_id"]
                      )[0]["cash"]

    all_stocks_value = 0
    # iterate user stocks information, update stocks 
    for i, stock in enumerate(stocks):
        quote_info = lookup(stock["stock_symbol"])

        stock_total_value = quote_info["price"] * stock["stock_amount"]
        all_stocks_value += stock_total_value

        # convert values to str, add to stocks
        stocks[i]["stock_total_value"] = usd(stock_total_value)
        stocks[i]["price"] = usd(quote_info["price"])

    portfolio_value = all_stocks_value + cash
    cash = usd(cash)
    portfolio_value = usd(portfolio_value)

    return render_template(
            "index.html",
            rows=stocks,
            cash=cash,
            total=portfolio_value
        )


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":
        number = request.form.get("number")
        symbol = request.form.get("symbol")

        if not symbol:
            flash("Type something in Symbol field to buy",
                  category='warning')
            return redirect(request.url)

        number = _validate_shares_num(number)
        if not number:
            flash("Please provide valid number of shares",
                  category='warning')
            return redirect(request.url)
        
        # quote a stock
        quote_info = lookup(symbol)
        if quote_info is None:
            # if not found
            flash(f"No company found with: {symbol}",
                  category='warning')
            return redirect(request.url)

        cash = db.execute("""SELECT cash 
                             FROM users
                             WHERE (id = ?)""",
                          session["user_id"]
                          )[0]["cash"]

        # check if user has enough cash to have a transaction
        transcation_cost = quote_info["price"] * number
        if cash < transcation_cost:
            flash("Transaction declined: Not enough amount in the wallet",
                  category='warning'
                  )
            return redirect(request.url)

        # record transaction to history
        transaction_type = "BUY"
        db.execute("""INSERT INTO transactions
                      VALUES (?, ?, ?, ?, ?, datetime('now'))""",
                   session["user_id"],
                   quote_info["symbol"], 
                   number, quote_info["price"], 
                   transaction_type
                   )

        # record new account balance
        db.execute("""UPDATE users 
                      SET cash = ? 
                      WHERE (id = ?)""",
                   (cash - transcation_cost),
                   session["user_id"]
                   )

        # record the new stocks amount user owns
        symbol = quote_info["symbol"]
        row = db.execute("""SELECT * 
                            FROM stocks 
                            WHERE user_id = ? 
                            AND stock_symbol = ?""",
                         session["user_id"],
                         symbol
                         )

        if len(row) == 0:
            db.execute("""INSERT INTO stocks 
                          VALUES (?, ?, ?)""",
                       session["user_id"],
                       symbol, 
                       number
                       )
        else:
            db.execute("""UPDATE stocks 
                          SET stock_amount = ? 
                          WHERE user_id = ? 
                          AND stock_symbol = ?""",
                       (row[0]["stock_amount"] + number), 
                       session["user_id"], 
                       symbol
                       )

        # redirect to portfolio
        flash(f"Bought successfully: {number} {symbol} shares")
        return redirect("/")
    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    rows = db.execute("""SELECT * 
                         FROM transactions 
                         WHERE (user_id = ?) 
                         ORDER BY timestamp DESC""",
                      session["user_id"]
                      )

    return render_template("history.html", rows=rows)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""
    if request.method == "POST":
        username = request.form.get('username')
        password = request.form.get('password')

        # Ensure username was submitted
        if not username:
            flash('Please provide username',
                  category='warning')
            return redirect(request.url)

        # Ensure password was submitted
        elif not password:
            flash('Please provide password',
                  category='warning')
            return redirect(request.url)
        
        # Ensure username exists and password is correct
        user_db_query = db.execute("""SELECT * 
                                      FROM users 
                                      WHERE username = ?""",
                                   username
                                   )
        if (    len(user_db_query) != 1 or not
                check_password_hash(user_db_query[0]["hash"], password)):
            # if any of the conditions is true
            flash("Invalid username or password",
                  category='warning')
            return redirect(request.url)
        
        # Forget previous user session with id
        session.clear()

        # record new session
        session["user_id"] = user_db_query[0]["id"]
        session["username"] = username

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""
    session.clear()

    # Redirect user to login form
    return redirect("/login")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":
        symbol = request.form.get("symbol")
        # validate user data
        if not symbol:
            flash("Type in Symbol field to search",
                  category='warning')
            return redirect(request.url)

        # try to search for symbol
        quote_info = lookup(symbol)
        if quote_info is None:
            # if not found
            flash(f"No company found with: {symbol}",
                  category='warning')
            return redirect(request.url)

        # if found
        flash("Found")

        return render_template("quoted.html", quote=quote_info,)
    else:
        return render_template("quote.html",)


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":
        username = request.form.get("username")
        password_1 = request.form.get("password")
        password_2 = request.form.get("confirmation")

        if not username or not password_1 or not password_2:
            flash("Please enter the username and password with confirmation",
                  category='warning')
            return redirect(request.url)

        # check if user already exists
        users = db.execute("""SELECT username 
                              FROM users 
                              WHERE (username = ?);""",
                           username
                           )
        if users:
            flash("Username is already taken, choose another one",
                  category='warning')
            return redirect(request.url)

        # compare passwords
        if password_1 != password_2:
            flash("Passwords don't match",
                  category='warning')
            return redirect(request.url)

        # hash the password, record new user
        hashed_password = generate_password_hash(password_1)
        db.execute("""INSERT INTO users (username, hash) 
                      VALUES (?, ?)""", 
                   username, hashed_password
                   )

        # redirect to login
        return redirect("/login")
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "POST":
        number = request.form.get("number")
        symbol = request.form.get("symbol")

        number = _validate_shares_num(number)
        if not number:
            flash("Please provide valid number of shares",
                  category='warning')
            return redirect('/')

        if not symbol:
            flash("Type something in Symbol field to buy",
                  category='warning')
            return redirect('/')

        # select all stocks that user owns
        stocks = db.execute("""SELECT * 
                               FROM stocks 
                               WHERE user_id = ?""",
                            session["user_id"]
                            )
        # check if user owns them
        if not any(row["stock_symbol"] == symbol for row in stocks):
            flash(f"You don't have {symbol} shares",
                  category='warning')
            return redirect(request.url)

        # validate if ser owns that ammount
        for row in stocks:
            if row["stock_symbol"] == symbol:
                if row["stock_amount"] < number:
                    flash(f"You don't have such amount of {symbol}",
                          category='warning')
                    return redirect('/')
                else:
                    break
        
        # quote current stock info
        quote_info = lookup(symbol)

        # calculate new cash ballance
        old_users_cash = db.execute("""SELECT cash 
                                       FROM users 
                                       WHERE id = ?""",
                                    session["user_id"]
                                    )[0]["cash"]

        plus_cash = quote_info["price"] * number
        new_users_cash = old_users_cash + plus_cash

        # calculate new stocks ballance
        old_stock_amount = db.execute("""SELECT stock_amount 
                                         FROM stocks 
                                         WHERE user_id = ? 
                                         AND stock_symbol = ?""",
                                      session["user_id"],
                                      symbol
                                      )[0]["stock_amount"]

        new_stock_amount = old_stock_amount - number
        if new_stock_amount < 0:
            flash("Error has occured, operation declined",
                  category='warning')
            raise ValueError(
                f"new_stock_ammount < 0: {new_stock_amount}\n"
                f"user id: {session['user_id']}\n"
                "Check if validation works"
            )

        # record transaction
        transaction_type = "SELL"
        db.execute("""INSERT INTO transactions 
                      VALUES (?, ?, ?, ?, ?, datetime('now'))""",
                   session["user_id"], 
                   quote_info["symbol"], 
                   number, 
                   quote_info["price"], 
                   transaction_type
                   )

        # update user's cash ballance
        db.execute("""UPDATE users 
                      SET cash = ? 
                      WHERE id = ?""",
                   new_users_cash,
                   session["user_id"]
                   )

        # amount of stocks
        # if after being sold, the amount of stocks = 0, delete row in sql
        if new_stock_amount == 0:
            db.execute("""DELETE FROM stocks 
                          WHERE user_id = ? 
                          AND stock_symbol = ?""", 
                       session["user_id"], 
                       symbol
                       )

        else:
            db.execute("""UPDATE stocks 
                          SET stock_amount = ? 
                          WHERE user_id = ? 
                          AND stock_symbol = ?""",
                       new_stock_amount, 
                       session["user_id"], 
                       symbol
                       )

        flash(f"You sold {number} of {symbol} stocks")
        return redirect("/")

    else:
        # select all stocks that user owns globally in this function
        stocks = db.execute("""SELECT * 
                               FROM stocks 
                               WHERE user_id = ?""",
                            session["user_id"]
                            )

        return render_template("sell.html", rows=stocks)
    

def _validate_shares_num(num: str) -> int:
    """Validates string of digits (shares number)

    if num is digits string AND num != 0:
        return: int(num) 
    else: return 0
    """
    if not num.isdigit():
        return 0
       
    num = int(num)

    if num == 0:
        return 0   
    return num
