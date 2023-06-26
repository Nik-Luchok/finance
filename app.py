import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import login_required, lookup, usd

# Configure application
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
    # select stocks that user owns from db
    rows = db.execute("SELECT * FROM stocks WHERE user_id = ?", session["user_id"])

    # select cash that user owns from db
    cash = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])[0]["cash"]

    # declare total = cash + sum of all value of actions
    total = 0
    # iterate the list of dictionaries with index number
    for i in range(len(rows)):
        # save quote dict for a searched quote
        quote_dict = lookup(rows[i]["stock_symbol"])

        # append price to the corresponding action
        rows[i]["price"] = usd(quote_dict["price"])

        # calculate sum and use it to calculate total
        sum = quote_dict["price"] * rows[i]["stock_amount"]
        total = total + sum

        # change sum int to str and save
        rows[i]["sum"] = usd(sum)

    # add cash to total value of actions
    total = total + cash

    # render template while converting total and cahs to str
    return render_template("index.html", rows=rows, cash=usd(cash), total=usd(total))


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":
        symbol = request.form.get("symbol")
        # validate user data
        if not symbol:
            flash("Type something in Symbol field to buy",
                  category='warning')
            return redirect('/')

        # try to search for symbol
        quote_dict = lookup(symbol)
        if quote_dict is None:
            # if not found
            flash(f"No company found with: {symbol}",
                  category='warning')
            return redirect('/')

        # validate number
        number = request.form.get("number")
        if not number.isdigit():
            flash("Shares must be a positive integer",
                  category='warning')
            return redirect('/')
        number = int(number)
        # check not 0
        if number == 0:
            flash("Shares must be a positive integer, starting from 1",
                  category='warning')
            return redirect('/')

        # can user buy such amount? check database. If not, say that to user and do nothing
        # select cash from DB for the current user
        cash = db.execute("SELECT cash FROM users WHERE (id = ?)", session["user_id"])[0]["cash"]

        # how much costs transaction
        transcation_cost = quote_dict["price"] * number

        # can user buy?
        if cash < transcation_cost:
            flash("Transaction declined: Not enough amount in the wallet",
                  category='warning')
            return redirect('/')

        # save new numbers to the database
        # record transaction
        transaction_type = "BUY"
        db.execute("INSERT INTO transactions VALUES (?, ?, ?, ?, ?, datetime('now'))",
                   session["user_id"], quote_dict["symbol"], number, quote_dict["price"], transaction_type)

        # deduct the amount he spend from what he have right now
        db.execute("UPDATE users SET cash = ? WHERE (id = ?)", (cash - transcation_cost), session["user_id"])

        # save symbol
        symbol = quote_dict["symbol"]

        # try to find a row with user id and stock name
        row = db.execute("SELECT * FROM stocks WHERE user_id = ? AND stock_symbol = ?",
                         session["user_id"], symbol)

        # record new stocks that user owns
        if len(row) == 0:
            db.execute("INSERT INTO stocks VALUES (?, ?, ?)", session["user_id"], symbol, number)
        else:
            db.execute("UPDATE stocks SET stock_amount = ? WHERE user_id = ? AND stock_symbol = ?",
                       (row[0]["stock_amount"] + number), session["user_id"], symbol)

        # redirect to portfolio
        flash(f"Bought successfully: {number}")
        return redirect("/")
    else:
        return render_template("buy.html", username=session["username"])


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    rows = db.execute("SELECT * FROM transactions WHERE (user_id = ?) ORDER BY timestamp DESC", session["user_id"])

    return render_template("history.html", username=session["username"], rows=rows)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            print(1)
            flash('Please provide username',
                  category='warning')
            return redirect('/login')

        # Ensure password was submitted
        elif not request.form.get("password"):
            print(2)
            flash('Please provide password',
                  category='warning')
            return redirect('/login')

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            flash("Invalid username or password",
                  category='warning')
            return redirect('/login')
        
        # Forget previous user session with id
        session.clear()

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # store username to display in the template
        session["username"] = rows[0]["username"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


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
            return redirect('/')

        # try to search for symbol
        quote_dict = lookup(symbol)
        if quote_dict is None:
            # if not found
            flash(f"No company found with: {symbol}",
                  category='warning')
            return redirect('/')

        # if found
        flash("Found")

        return render_template("quoted.html", quote=quote_dict, username=session["username"])
    else:
        return render_template("quote.html", username=session["username"])


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    # if we get here by form request
    if request.method == "POST":
        # save submitted data in variables
        username = request.form.get("username")
        # TODO validate data

        if not username:
            flash("Please enter the username",
                  category='warning')
            return redirect('/register')

        # get a list of dict from database
        rows = db.execute("SELECT username FROM users WHERE (username = ?);", username)

        # found a data in a database
        if len(rows) >= 1:
            flash("Sorry, this username is already taken, choose another one",
                  category='warning')
            return redirect('/')

        password = request.form.get("password")
        # TODO validate data
        if not password:
            flash("Please enter the password",
                  category='warning')
            return redirect('/')

        confirmation = request.form.get("confirmation")
        # TODO validate data
        if not confirmation:
            flash("Please confirm your password",
                  category='warning')
            return redirect('/')

        # compare passwords, alert user if don't match
        if password != confirmation:
            flash("passwords don't match",
                  category='warning')
            return redirect('/')

        # hash the password
        hashed_password = generate_password_hash(password)

        db.execute("INSERT INTO users (username, hash) VALUES (?, ?)", username, hashed_password)

        # redirect to login
        return redirect("/login")
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    # check request method
    if request.method == "POST":
        # validate data
        number = request.form.get("number")
        if not number.isdigit():
            flash("Number must be a positive integer",
                  category='warning')
            return redirect('/')
        number = int(number)
        # check not 0
        if number == 0:
            flash("Please provide valid number of shares",
                  category='warning')
            return redirect('/')

        symbol = request.form.get("symbol")
        if (not symbol) or symbol == "None":
            flash("Select stock symbol",
                  category='warning')
            return redirect('/')

        # select all stocks that user owns globally in this function
        rows = db.execute("SELECT * FROM stocks WHERE user_id = ?", session["user_id"])

        if not any(row["stock_symbol"] == symbol for row in rows):
            flash(f"You don't have {symbol} shares",
                  category='warning')
            return redirect(request.url)

        # check the amount of owned stock
        for row in rows:
            if row["stock_symbol"] == symbol:
                if row["stock_amount"] < number:
                    flash(f"You don't have such amount of {symbol}",
                          category='warning')
                    return redirect('/')
                else:
                    break

        # deduct the amount of stocks and add cash coresponding to the current price
        # find current price
        quote_dict = lookup(symbol)

        # how much cash a user would get if he sells stocks
        plus_cash = quote_dict["price"] * number

        # select current amount of cash
        old_users_cash = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])[0]["cash"]

        # calculate new amount of user's cash
        new_users_cash = old_users_cash + plus_cash

        # select current amount of stocks
        old_stock_amount = db.execute("SELECT stock_amount FROM stocks WHERE user_id = ? AND stock_symbol = ?",
                                      session["user_id"], symbol)[0]["stock_amount"]

        # calculate new amount of stocks
        new_stock_amount = old_stock_amount - number

        # insert new data in the database
        # record transaction
        transaction_type = "SELL"
        db.execute("INSERT INTO transactions VALUES (?, ?, ?, ?, ?, datetime('now'))",
                   session["user_id"], quote_dict["symbol"], number, quote_dict["price"], transaction_type)

        # cash
        db.execute("UPDATE users SET cash = ? WHERE id = ?", new_users_cash, session["user_id"])

        # amount of stocks
        # if after being sold, the amount of stocks = 0, delete row in sql
        if new_stock_amount == 0:
            db.execute("DELETE FROM stocks WHERE user_id = ? AND stock_symbol = ?", session["user_id"], symbol)

        else:
            db.execute("UPDATE stocks SET stock_amount = ? WHERE user_id = ? AND stock_symbol = ?",
                       new_stock_amount, session["user_id"], symbol)

        flash(f"You sold {number} of {symbol} stocks")
        return redirect("/")

    else:
        # select all stocks that user owns globally in this function
        rows = db.execute("SELECT * FROM stocks WHERE user_id = ?", session["user_id"])

        return render_template("sell.html", rows=rows, username=session["username"])
