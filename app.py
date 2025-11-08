from flask import Flask, render_template, request, redirect, url_for, session, flash
from models import db, User ,FoodItem
from werkzeug.security import generate_password_hash, check_password_hash
from flask_migrate import Migrate
from utils import search_food
from decimal import Decimal
from models import FoodItem , MealLog
from flask import request, render_template
from utils import search_food  # your external API search logic


app = Flask(__name__)
app.secret_key = "your_secret_key_here"

# DB config
app.config["SQLALCHEMY_DATABASE_URI"] = "postgresql://postgres:CLFA5ACD5C@localhost:5432/FitCal"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)
migrate = Migrate(app, db)

# ---------- ROUTES ----------

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        _user = User.query.filter_by(username=username).first()
        if _user and _user.verify_password(password):
            session["user_id"] = _user.id
            session["username"] = _user.username
            flash("Login successful!", "success")
            return redirect(url_for("index"))
        else:
            flash("Invalid username or password.", "error")
            return redirect(url_for("login"))

    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        if User.query.filter_by(username=username).first():
            flash("Username already taken")
            return redirect(url_for("register"))

        new_user = User(username=username)
        new_user.password = password  # setter handles hashing
        db.session.add(new_user)
        db.session.commit()

        flash("Registration successful! Please log in.")
        return redirect(url_for("login"))

    return render_template("signup.html")

@app.route("/")
def home():
    return render_template("home.html")

@app.route("/index")
def index():
    goal = None
    return render_template("index.html")  # Logged-in home/dashboard




@app.route("/maintenance")
def maintenance():
    return render_template("maintenance.html")


@app.route('/setgoal')
def set_goal():
    # Get calories from query parameter
    calories = request.args.get('calories', type=int)
    return render_template('setgoals.html', calories=calories)


@app.route("/logmeals", methods=["GET", "POST"])
def log_meals():
    if "user_id" not in session:
        flash("Please log in first.", "error")
        return redirect(url_for("login"))

    item = None
    quantity = None
    searched = False

    if request.method == "POST":
        foodname = request.form["foodname"].strip()
        quantity = Decimal(request.form["quantity"])
        searched = True

        item = FoodItem.query.filter(FoodItem.name.ilike(foodname)).first()

        if not item:
            data = search_food(foodname)
            if data:
                existing = FoodItem.query.filter(FoodItem.name == data["name"]).first()
                if not existing:
                    item = FoodItem(**data)
                    db.session.add(item)
                    db.session.commit()
                else:
                    item = existing

        # Save the meal log
        if item:
            new_log = MealLog(
                food_id=item.id,
                quantity=quantity,
                user_id=session["user_id"]  # link the meal to the logged-in user
            )
            db.session.add(new_log)
            db.session.commit()
            flash(f"{item.name} ({quantity}g) logged successfully!", "success")
        else:
            flash("Food not found. Please try another name.", "error")

        return render_template("logmeals.html", item=item, quantity=quantity, searched=searched)

    return render_template("logmeals.html", item=None, quantity=None, searched=False)


@app.route("/details")
def meal_details():
    meal_entries = MealLog.query.order_by(MealLog.timestamp.desc()).all()

    total_calories = 0
    total_protein = 0
    total_carbs = 0
    total_fats = 0

    enriched_logs = []

    for entry in meal_entries:
        food = entry.food
        q = entry.quantity or 0

        cal = float(food.calories_per_100g or 0) * q / 100
        protein = float(food.protein or 0) * q / 100
        carbs = float(food.carbs or 0) * q / 100
        fats = float(food.fats or 0) * q / 100

        total_calories += cal
        total_protein += protein
        total_carbs += carbs
        total_fats += fats

        enriched_logs.append({
            "id": entry.id,  # ✅ Needed for delete buttons
            "date": entry.timestamp.date() if entry.timestamp else None,
            "name": food.name,
            "quantity": q,
            "calories": round(cal, 2),
            "protein": round(protein, 2),
            "carbs": round(carbs, 2),
            "fats": round(fats, 2)
        })

    return render_template(
        "meal_details.html",
        meals=enriched_logs,  # ✅ same variable name as HTML
        total_calories=round(total_calories, 2),
        total_protein=round(total_protein, 2),
        total_carbs=round(total_carbs, 2),
        total_fats=round(total_fats, 2)
    )


# ✅ Route for deleting one entry
@app.route("/delete_meal/<int:meal_id>", methods=["POST"])
def delete_meal(meal_id):
    entry = MealLog.query.get(meal_id)
    if entry:
        db.session.delete(entry)
        db.session.commit()
        flash("Meal deleted successfully!", "success")
    else:
        flash("Meal not found.", "error")
    return redirect(url_for("meal_details"))


# ✅ Route for deleting all entries
@app.route("/delete_all_meals", methods=["POST"])
def delete_all_meals():
    MealLog.query.delete()
    db.session.commit()
    flash("All meals deleted successfully!", "success")
    return redirect(url_for("meal_details"))



@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.")
    return redirect(url_for("login"))

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)