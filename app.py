from flask import Flask, render_template, request, redirect, url_for, session, flash
from models import db, User, FoodItem, MealLog, Goal
from werkzeug.security import generate_password_hash, check_password_hash
from flask_migrate import Migrate
from utils import search_food
from decimal import Decimal
from datetime import datetime
from sqlalchemy import func

app = Flask(__name__)
app.secret_key = "your_secret_key_here"

# ------------------ Database Configuration ------------------
app.config["SQLALCHEMY_DATABASE_URI"] = "postgresql://postgres:CLFA5ACD5C@localhost:5432/FitCal"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)
migrate = Migrate(app, db)

# ------------------ Helper Functions ------------------
def get_current_user_id():
    """Return the logged-in user's ID or None."""
    return session.get("user_id")


# ------------------ Routes ------------------

# ---------- Authentication ----------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        _user = User.query.filter_by(username=username).first()
        if _user and _user.verify_password(password):
            session["user_id"] = _user.id
            session["username"] = _user.username
            #Don't flash here to avoid message carrying forward
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
            flash("Username already taken.", "error")
            return redirect(url_for("register"))

        new_user = User(username=username)
        new_user.password = password  # setter hashes password
        db.session.add(new_user)
        db.session.commit()

        flash("Registration successful! Please log in.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")

@app.route("/")
def home():
     return render_template("home.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))


# ---------- Dashboard ----------


@app.route("/index")
def index():
    if "user_id" not in session:
        flash("Please log in first.", "error")
        return redirect(url_for("login"))

    user_id = session["user_id"]

    # Get current goal
    current_goal = Goal.query.filter_by(user_id=user_id).first()

    # Calculate total calories today using the relationship
    total_calories = (
        db.session.query(func.coalesce(func.sum(FoodItem.calories_per_100g * MealLog.quantity / 100), 0))
        .select_from(MealLog)
        .join(FoodItem, MealLog.food_id == FoodItem.id)
        .filter(MealLog.user_id == user_id)
        .filter(func.date(MealLog.timestamp) == datetime.utcnow().date())
        .scalar()
    )

    return render_template(
        "index.html",
        current_goal=current_goal,
        total_calories=round(total_calories, 2)
    )

# ---------- Maintenance ----------
@app.route("/maintenance", methods=["GET", "POST"])
def maintenance():
    user_id = get_current_user_id()
    if not user_id:
        flash("Please log in first.", "error")
        return redirect(url_for("login"))

    calories_from_maintenance = None
    if request.method == "POST":
        weight = float(request.form.get("weight", 0))
        height = float(request.form.get("height", 0))
        age = int(request.form.get("age", 0))
        gender = request.form.get("gender", "male")

        if gender == "male":
            calories_from_maintenance = int(10*weight + 6.25*height - 5*age + 5)
        else:
            calories_from_maintenance = int(10*weight + 6.25*height - 5*age - 161)

        flash(f"Your estimated maintenance calories: {calories_from_maintenance} kcal", "success")

    return render_template("maintenance.html", calories_from_maintenance=calories_from_maintenance)


# ---------- Set Goals ----------
@app.route("/setgoal", methods=["GET", "POST"])
def set_goal():
    user_id = get_current_user_id()
    if not user_id:
        flash("Please log in first.", "error")
        return redirect(url_for("login"))

    calories = request.args.get("calories", None)

    if request.method == "POST":
        calories_input = request.form.get("calories")
        if calories_input:
            calories_value = int(calories_input)
            goal = Goal.query.filter_by(user_id=user_id).first()
            if not goal:
                goal = Goal(user_id=user_id, calories=calories_value)
                db.session.add(goal)
            else:
                goal.calories = calories_value

            db.session.commit()
            flash("Daily calorie goal set successfully!", "success")
            return redirect(url_for("index"))

    goal = Goal.query.filter_by(user_id=user_id).first()
    current_calories = calories or (goal.calories if goal else "")
    return render_template("setgoals.html", current_goal={"calories": current_calories})


# ---------- Log Meals ----------
@app.route("/logmeals", methods=["GET", "POST"])
def log_meals():
    user_id = get_current_user_id()
    if not user_id:
        flash("Please log in first.", "error")
        return redirect(url_for("login"))

    last_entry = None
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

        if item:
            new_log = MealLog(
                food_id=item.id,
                quantity=quantity,
                user_id=user_id
            )
            db.session.add(new_log)
            db.session.commit()

            # Prepare dictionary for template
            last_entry = {
                "name": item.name,
                "quantity": float(quantity),
                "calories": float(item.calories_per_100g) * float(quantity) / 100,
                "protein": float(item.protein) * float(quantity) / 100,
                "carbs": float(item.carbs) * float(quantity) / 100,
                "fats": float(item.fats) * float(quantity) / 100
            }

            flash(f"{item.name} ({quantity}g) logged successfully!", "success")
        else:
            flash("Food not found. Please try another name.", "error")

    return render_template("logmeals.html", item=last_entry, searched=searched)



# ---------- Meal Details ----------
@app.route("/details")
def meal_details():
    user_id = get_current_user_id()
    if not user_id:
        flash("Please log in first.", "error")
        return redirect(url_for("login"))

    meal_entries = MealLog.query.filter_by(user_id=user_id).order_by(MealLog.timestamp.desc()).all()

    total_calories = total_protein = total_carbs = total_fats = 0
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
            "id": entry.id,
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
        meals=enriched_logs,
        total_calories=round(total_calories, 2),
        total_protein=round(total_protein, 2),
        total_carbs=round(total_carbs, 2),
        total_fats=round(total_fats, 2)
    )


# ---------- Delete Meal ----------
@app.route("/delete_meal/<int:meal_id>", methods=["POST"])
def delete_meal(meal_id):
    user_id = get_current_user_id()
    if not user_id:
        flash("Please log in first.", "error")
        return redirect(url_for("login"))

    entry = MealLog.query.get(meal_id)
    if entry and entry.user_id == user_id:
        db.session.delete(entry)
        db.session.commit()
        flash("Meal deleted successfully!", "success")
    else:
        flash("Meal not found.", "error")
    return redirect(url_for("meal_details"))


@app.route("/delete_all_meals", methods=["POST"])
def delete_all_meals():
    user_id = get_current_user_id()
    if not user_id:
        flash("Please log in first.", "error")
        return redirect(url_for("login"))

    MealLog.query.filter_by(user_id=user_id).delete()
    db.session.commit()
    flash("All meals deleted successfully!", "success")
    return redirect(url_for("meal_details"))


# ---------- Run App ----------
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)
