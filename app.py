import os
import datetime

from flask_cors import CORS
from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

CORS(app)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")


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
    id = session["user_id"]
    name = db.execute("SELECT username FROM users WHERE id = ?", id)[0]["username"]
    db.execute("CREATE TABLE IF NOT EXISTS current_positions (transaction_id INTEGER PRIMARY KEY, symbol TEXT, number NUMBER, price NUMBER, total NUMBER, time TEXT, name TEXT, id NUMBER)")
    db.execute("CREATE TABLE IF NOT EXISTS transactions (transaction_id INTEGER PRIMARY KEY, symbol TEXT, name TEXT, number NUMBER, price NUMBER, type TEXT, time TEXT, id NUMBER)")
    symbolsHeld = db.execute("SELECT DISTINCT symbol FROM current_positions WHERE id = ? AND number > 0 ORDER BY name ASC", id)

    # loop through each symbol held and create a dict of calculations/info for each symbol. Add each dict to an array.
    holding = []
    total = 0
    for symbol in symbolsHeld:
        sum = db.execute("SELECT name, SUM(number), SUM(total) FROM current_positions WHERE symbol = ? AND id = ?", symbol["symbol"], id)
        currentPrice = lookup(symbol["symbol"])['price']
        currentValue = (currentPrice * sum[0]['SUM(number)'])
        profit = usd((currentValue - sum[0]['SUM(total)']))
        v = {'symbol': symbol['symbol'], 'company': sum[0]['name']  ,'shares': sum[0]['SUM(number)'], 'total': usd(sum[0]['SUM(total)']), 'currentPrice': usd(currentPrice), 'currentValue': usd(currentValue), 'profit': profit }
        holding.append(v)
        total = total + currentValue

    # calculate any other information  needed for home screen
    unformattedBalance = db.execute("SELECT cash FROM users WHERE id = ?", id)[0]["cash"]
    balance = usd(unformattedBalance)
    grandTotal = usd(unformattedBalance + total)

    # display all of the above details in a table on the home screen
    return render_template("index.html", name = name.capitalize(), holding = holding, balance = balance, grandTotal = grandTotal)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # get selected symbol
        symbol = request.form.get("symbol")
        if not (symbol):
            return apology("No stock symbol entered", 403)

        # fetch current info for selected symbol
        buySymbol = lookup(symbol)

        # check response from lookup() to see if stock symbol is valid
        if buySymbol == None:
            return apology("This stock does not exist")

        # get number of shares user wishes to buy
        inputNumber = request.form.get("shares")

        # validate that user has input a whole number
        if inputNumber.isdigit() != True:
            return apology("Number must be a positive number", 400)

        symbol = buySymbol["symbol"]
        number = int(inputNumber)
        price = buySymbol["price"]
        time = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        name = buySymbol["name"]
        id = session["user_id"]
        transactionTotal = price * number



        # now that input has been cast to an int check to that input is a positive number
        if number < 0:
            return apology("Number must be a positive number", 400)

        # get user's balance
        balance = db.execute("SELECT cash FROM users WHERE id = ?", id)[0]["cash"]

        # check if user has sufficient funds to purchase the amount of stock requested
        if transactionTotal > balance:
            return apology("insufficient Funds", 400)

        # create new balance ready for updating user's db info
        newBalance = balance - transactionTotal

        # create current_positions/transactions tables if don't exist already
        db.execute("CREATE TABLE IF NOT EXISTS current_positions (transaction_id INTEGER PRIMARY KEY, symbol TEXT, number NUMBER, price NUMBER, total NUMBER, time TEXT, name TEXT, id NUMBER)")
        db.execute("CREATE TABLE IF NOT EXISTS transactions (transaction_id INTEGER PRIMARY KEY, symbol TEXT, name TEXT, number NUMBER, price NUMBER, type TEXT, time TEXT, id NUMBER)")
        # update current positions table
        db.execute("INSERT INTO current_positions (symbol, number, price, total, time, name, id) VALUES (?, ?, ?, ?, ?, ?, ?)", symbol, number, price, transactionTotal, time, name, id)
        # update transactions table
        db.execute("INSERT INTO transactions (symbol, number, name, price, type, time, id) VALUES (?, ?, ?, ?, ?, ?, ?)", symbol, number, name, price, "BUY", time, id)
        # update user table
        db.execute("UPDATE users SET cash = ? WHERE id = ?", newBalance, id)

        return redirect("/")
    else:
        return render_template("buy.html")

@app.route("/history")
@login_required
def history():
    id = session["user_id"]
    name = db.execute("SELECT username FROM users WHERE id = ?", id)[0]["username"]
    userHistory = db.execute("SELECT * FROM transactions WHERE id = ? ORDER BY transaction_id DESC", id)

    return render_template("history.html", name = name, userHistory = userHistory)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

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
        symbolInfo = lookup(request.form.get("symbol"))

        if symbolInfo == None:
            return apology("invalid stock symbol", 400)

        price = usd(symbolInfo["price"])

        return render_template("quoted.html", symbolInfo = symbolInfo, price = price)

    #return render_template("quote.html")
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    # Forget any user_id
    session.clear()

    # # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 400)

        # Ensure password was submitted
        if not request.form.get("password"):
            return apology("must provide password", 400)

        if request.form.get("password") != request.form.get("confirmation"):
            return apology("passwords do not match", 400)

        # check attempted username against usernames stored in db
        newName = request.form.get("username")
        userNames = db.execute("SELECT username FROM users")
        for username in userNames:
            if username["username"] == newName:
                return apology("username in use", 400)

        # else:
        # hash the password
        hash = generate_password_hash(request.form.get("password"), method='pbkdf2:sha256', salt_length=8)
        username = request.form.get("username")
        # Insert data in to database and check that return is not null
        db.execute("INSERT INTO users (username, hash) VALUES(?, ?)", username, hash)
        #search database for newly created user
        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", username)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("register.html")

@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    if request.method == "GET":

        id = session["user_id"]

        symbolsHeld = db.execute("SELECT DISTINCT symbol FROM current_positions WHERE id = ? AND number > 0", id)
        return render_template("sell.html", symbolsHeld = symbolsHeld)

    else:
        id = session["user_id"]

        symbolsHeld = db.execute("SELECT DISTINCT symbol FROM current_positions WHERE id = ? AND number > 0", id)
        # symbolsHeld = db.execute("SELECT symbol, SUM(number) FROM current_positions  WHERE id = ? AND number > 0 GROUP BY symbol", id)

        selectedSymbol = request.form.get("symbol")
        numberSelected = int(request.form.get("shares"))
        # maxAvailable = db.execute("SELECT SUM(number) FROM current_positions WHERE symbol = ? AND id = ?", selectedSymbol, id)[0]['SUM(number)']


        # count number of shares held for symbol selected
        currentNumber = 0
        for symbol in symbolsHeld:
            if symbol["symbol"] == selectedSymbol:
                currentNumber = db.execute("SELECT SUM(number) FROM current_positions WHERE id = ? And symbol = ?", id, selectedSymbol)[0]["SUM(number)"]

        if numberSelected > currentNumber:
            return apology("not enough shares")

        # TODO while loop  - while numberSelected > 0 loop through database and update to reduce number of shares
        toSell = numberSelected

        while toSell > 0:
            transInfo = db.execute("SELECT transaction_id, name, number, price FROM current_positions WHERE number > 0 AND id = ? AND symbol = ?", id, selectedSymbol)
            name = transInfo[0]["name"]
            number = transInfo[0]["number"]
            transId = transInfo[0]["transaction_id"]
            pricePaid = transInfo[0]["price"]
            shareValue = lookup(selectedSymbol)["price"]
            if toSell >= number:
                # remove sold shares from number of shares in transaction table
                db.execute("UPDATE current_positions SET number = 0, total = 0 WHERE transaction_id = ?", transId)
                # workout profit from shares sold
                profit = shareValue - pricePaid
                # get user's balance
                cash = db.execute("SELECT cash FROM users WHERE id = ?", id)[0]['cash']
                # create user's new balance
                newBalance = cash + (( pricePaid + profit) * number)
                db.execute("UPDATE users SET cash = ? WHERE id = ?", newBalance, id)
                # update transactions table
                time = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                db.execute("INSERT INTO transactions (symbol, number, name, price, type, time, id) VALUES (?, ?, ?, ?, ?, ?, ?)", selectedSymbol, number, name, shareValue, "SELL", time, id)
                toSell = toSell - number

                # go back to start of loop to get new number of shares from db
                continue
            if toSell < number:
                newNumber = number - toSell
                newTotal = pricePaid * newNumber
                db.execute("UPDATE current_positions SET number = ?, total = ? WHERE transaction_id = ?", newNumber, newTotal, transId)
                profit = shareValue - pricePaid
                cash = db.execute("SELECT cash FROM users WHERE id = ?", id)[0]['cash']
                newBalance = cash + ((pricePaid + profit) * toSell)
                db.execute("UPDATE users SET cash = ? WHERE id = ?", newBalance, id)
                time = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                db.execute("INSERT INTO transactions (symbol, number, name, price, type, time, id) VALUES (?, ?, ?, ?, ?, ?, ?)", selectedSymbol, toSell, name, shareValue, "SELL", time, id)
                toSell = 0

        return redirect("/")
