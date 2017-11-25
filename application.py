```
from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session, url_for
from flask_session import Session
from passlib.apps import custom_app_context as pwd_context
from tempfile import mkdtemp

from helpers import *

# configure application
app = Flask(__name__)

# ensure responses aren't cached
if app.config["DEBUG"]:
    @app.after_request
    def after_request(response):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Expires"] = 0
        response.headers["Pragma"] = "no-cache"
        return response

# custom filter
app.jinja_env.filters["usd"] = usd

# configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

@app.route("/")
@login_required
def index():
    
    # query the database for the symbol of the user's stock
    current_holdings = db.execute("SELECT share, symbol FROM holding WHERE id = :id", id=session["user_id"])
    
    # a temporary variable to be used to calculate the total asset including available cash and stock value
    asset = 0
    
    # iterate through the stocks, and update the stock price and value in the databse
    for current_holding in current_holdings:
        symbol = current_holding["symbol"]
        shares = current_holding["share"]
        stock = lookup(symbol)
        value = shares * stock["price"]
        asset += value
        db.execute("UPDATE holding SET price=:price, value=:value WHERE id= :id AND symbol = :symbol",\
                    price=usd(stock["price"]),\
                    value=usd(value),\
                    id=session["user_id"],\
                    symbol=symbol)
    
    # query the databse for the user's available cash
    current_cash = db.execute("SELECT cash FROM users WHERE id=:id", id=session["user_id"])
    
    # a temporary variable to record the user's available cash
    total_cash = current_cash[0]["cash"]
    
    # query the database for the updated holding information
    updated_holdings = db.execute("SELECT * FROM holding WHERE id = :id", id=session["user_id"])
    
    # render the index.html
    return render_template("index.html", stocks=updated_holdings, cash=usd(total_cash),\
                            total_asset=usd(round(asset + total_cash, 2)))



@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock."""
    
    # if user reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        
        # ensure stock symbol was submitted
        stock = lookup(request.form.get("stock_symbol"))
        if not stock:
            return apology("Invalid Symbol")
        
        # ensure the number of shares to buy was submitted and is a positive integer
        try:
            shares = int(request.form.get("shares"))
            if shares <= 0:
                return apology("shares must be a positive integer")
        except:
            return apology("shares must be a positive integer")
        
        # query the database for the user's available cash
        saving = db.execute("SELECT cash FROM users WHERE id = :id",\
                            id=session["user_id"])
        
        # ensure the user has more cash than the total value of the stock to be purchased
        if not saving or float(saving[0]["cash"]) < stock["price"] * shares:
            return apology("not enough cash")
        
        # write into the database the trade info
        db.execute("INSERT INTO trade (id, stock, symbol, buy_in_price, buy_in_share, buy_in_value) \
                    VALUES (:id, :stock, :symbol, :buy_in_price, :buy_in_share, :buy_in_value)", \
                    id=session["user_id"],\
                    stock=stock["name"],\
                    symbol=stock["symbol"],\
                    buy_in_price=usd(stock["price"]),\
                    buy_in_share=shares,\
                    buy_in_value=usd(shares * stock["price"]))
        
        # update the user's available cash in the database after the purchase
        db.execute("UPDATE users SET cash = cash - :trade WHERE id = :id",\
                    id=session["user_id"],\
                    trade = float(shares) * stock["price"])
        
        # query the database for the stock purchased by the user
        current_share = db.execute("SELECT share FROM holding WHERE id = :id AND symbol = :symbol",\
                                    id=session["user_id"],\
                                    symbol=stock["symbol"])
        
        # if the stock does not exist, write into the database the purchased stock
        if not current_share:
            db.execute("INSERT INTO holding (id, stock, symbol, share, price, value)\
                        VALUES (:id, :stock, :symbol, :share, :price, :value)",\
                        id=session["user_id"],\
                        stock=stock["name"],\
                        symbol=stock["symbol"],\
                        share=shares,\
                        price=usd(stock["price"]),\
                        value=usd(shares * stock["price"]))
        
        # otherwise, update the share of the purchased stock
        else:
            db.execute("UPDATE holding SET share = share + :shares WHERE id = :id AND symbol = :symbol",\
                        id=session["user_id"],\
                        symbol=stock["symbol"],\
                        shares=shares)
        
        # redirect the user to index.html
        return redirect(url_for("index"))
                    
    
    # else if user reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("buy.html")
    

@app.route("/history")
@login_required
def history():
    """Show history of transactions."""
    
    histories = db.execute("SELECT * FROM trade WHERE id = :id", id=session["user_id"])
    
    return render_template("history.html", histories = histories)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in."""

    # forget any user_id
    session.clear()

    # if user reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username")

        # ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password")

        # query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username", username=request.form.get("username"))

        # ensure username exists and password is correct
        if len(rows) != 1 or not pwd_context.verify(request.form.get("password"), rows[0]["hash"]):
            return apology("invalid username and/or password")

        # remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # redirect user to home page
        return redirect(url_for("index"))

    # else if user reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")

@app.route("/logout")
def logout():
    """Log user out."""

    # forget any user_id
    session.clear()

    # redirect user to login form
    return redirect(url_for("login"))

@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    
    # if user reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        
        # lookup the user's target stock
        rows = lookup(request.form.get("symbol"))
        
        # ensure the stock exists
        if not rows:
            return apology("Invalid Symbol")
        
        # show the stock's price to user    
        return render_template("quoted.html", stock=rows)
    
    # else if user reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user."""
    
    # forget any user_id
    session.clear()
    
    # if user reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        
        # ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username")
        
        # ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password")
        
        # ensure the passwords match
        elif request.form.get("password") != request.form.get("password_confirnation"):
            return apology("passwords do not match")
        
        row = db.execute("INSERT INTO users (username, hash) VALUES (:username, :hash)",\
                         username=request.form.get("username"),\
                         hash=pwd_context.hash(request.form.get("password")))
        
        # prompt the user if the username has already existed
        if not row:
            return apology("username already exists")
        
        # query database for the registered username
        auto_login = db.execute("SELECT * FROM users WHERE username = :username",\
                                username=request.form.get("username"))
        # remember the user, who has just registered, as logged in
        session["user_id"] = auto_login[0]["id"]
        
        # redirect user to home page
        return redirect(url_for("index"))
    
    # else if user reached route via GET (as by clicking a link or via redirect)    
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock."""
    
    # if user reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        
        # lookup the stock that the user intends to sell
        stock = lookup(request.form.get("stock_symbol"))
        # if the stock cannot be found, prompt the user to provide a valid stock symbol
        if not stock:
            return apology("must provide a valid stock symbol")
        
        # convert the share into integer and store in the variable share
        try:
            share = int(request.form.get("share"))
            # ensure the share that the user key in is a positive integer
            if share <= 0:
                return apology("Shares may be positive integer")
        # ensure the value that the user key in is a valid positive integer
        except:
            return apology("Shares should be positive integer")
        
        # query the database for the share possessed by the user
        possessed_share = db.execute("SELECT share FROM holding WHERE id = :id AND symbol = :symbol",\
                                     id=session["user_id"], symbol=stock["symbol"])
        
        # ensure that the user has enough share to sell
        if not possessed_share or possessed_share[0]["share"] < share:
            return apology("not enough share in possession")

        # write the trade info into the databse
        db.execute("INSERT INTO trade (id, stock, symbol, sell_out_price, sell_out_share, sell_out_value)\
                    VALUES (:id, :stock, :symbol, :sell_out_price, :sell_out_share, :sell_out_value)", \
                    id=session["user_id"],\
                    stock=stock["name"],\
                    symbol=stock["symbol"],\
                    sell_out_price=usd(stock["price"]),\
                    sell_out_share=share,\
                    sell_out_value=usd(share * stock["price"]))
        
        # add the value of the sold stock to the user's cash
        db.execute("UPDATE users SET cash = cash + :trade WHERE id = :id",
                    id = session["user_id"],\
                    trade = float(share) * stock["price"])
        
        # temporarily store the updated possessed share of the user
        updated_share = possessed_share[0]["share"] - share
        
        # delete the stock from the holding if the updated possessed share is 0
        if updated_share == 0:
            db.execute("DELETE FROM holding WHERE id = :id AND symbol = :symbol",\
                        id = session["user_id"],\
                        symbol = stock["symbol"])
        
        # otherwise, update the holding database the possessed share of the user
        else:
            db.execute("UPDATE holding SET share = :share WHERE id = :id AND symbol = :symbol",\
                        share = updated_share,\
                        id = session["user_id"],\
                        symbol = stock["symbol"])
    
    # else if user reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("sell.html")
    
    # redirect the user to index
    return redirect(url_for("index"))
```
