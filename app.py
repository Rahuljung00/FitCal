import os
from decimal import Decimal
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_migrate import Migrate
from models import db, User, FoodItem, MealLog, Meal
from utils import smart_search
from datetime import datetime


# ----------------- HELPER FUNCTIONS -----------------
def safe_decimal(value, default=0):
    """Safely convert any value to Decimal, with fallback."""
    if value is None or value == '' or (isinstance(value, str) and value.strip() == ''):
        return Decimal(str(default))
    try:
        return Decimal(str(value))
    except (ValueError, TypeError):
        return Decimal(str(default))


# ----------------- APP CONFIG -----------------
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "fallback_secret")

# Database configuration
app.config["SQLALCHEMY_DATABASE_URI"] = "postgresql://postgres:CLFA5ACD5C@localhost:5432/FitCal"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)
migrate = Migrate(app, db)


# ----------------- AUTH ROUTES -----------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]

        user = User.query.filter_by(username=username).first()
        if user and user.verify_password(password):
            session["user_id"] = user.id
            session["username"] = user.username
            flash("Login successful!", "success")
            return redirect(url_for("index"))
        else:
            flash("Invalid username or password.", "error")
            return redirect(url_for("login"))

    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username").strip()
        password = request.form.get("password")

        if not username or not password:
            flash("Username and password are required.", "error")
            return redirect(url_for("register"))

        if User.query.filter_by(username=username).first():
            flash("Username already taken", "error")
            return redirect(url_for("register"))

        try:
            new_user = User(username=username)
            new_user.password = password  # Uses password.setter (with validation)
            db.session.add(new_user)
            db.session.commit()
            flash("Registration successful! Please log in.", "success")
            return redirect(url_for("login"))
        except ValueError as ve:
            db.session.rollback()
            flash(str(ve), "error")
            return redirect(url_for("register"))
        except Exception as e:
            db.session.rollback()
            flash("An error occurred during registration.", "error")
            return redirect(url_for("register"))

    return render_template("register.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))


# ----------------- PAGE ROUTES -----------------
@app.route("/")
def home():
    return render_template("home.html")


@app.route("/index")
def index():
    return render_template("index.html")



# ----------------- MEAL LOG MANAGEMENT ROUTES -----------------

@app.route("/delete_log/<int:log_id>", methods=["POST"])
def delete_log(log_id):
    if "user_id" not in session:
        flash("You must be logged in to delete a log.", "warning")
        return redirect(url_for("login"))
    
    log = MealLog.query.filter_by(id=log_id, user_id=session["user_id"]).first()
    if log:
        db.session.delete(log)
        db.session.commit()
        flash("Meal log deleted.", "success")
    else:
        flash("Log not found or access denied.", "error")
    
    return redirect(url_for("meal_details"))


@app.route("/delete_all_logs", methods=["POST"])
def delete_all_logs():
    if "user_id" not in session:
        flash("You must be logged in to delete logs.", "warning")
        return redirect(url_for("login"))
    
    deleted_count = MealLog.query.filter_by(user_id=session["user_id"]).delete()
    db.session.commit()
    flash(f"All {deleted_count} meal logs deleted successfully.", "success")
    return redirect(url_for("meal_details"))
    

@app.route("/logmeals", methods=["GET", "POST"])
def log_meals():
    item = None
    quantity = None
    searched = False

    if request.method == "POST":
        foodname = request.form["foodname"].strip()
        try:
            quantity = Decimal(request.form["quantity"])
            if quantity <= 0:
                flash("Quantity must be greater than zero.", "error")
                return redirect(url_for("log_meals"))
        except:
            flash("Invalid quantity entered.", "error")
            return redirect(url_for("log_meals"))

        searched = True
        item = FoodItem.query.filter(FoodItem.name.ilike(foodname)).first()

        if not item:
            data = smart_search(foodname)
            if data:
                existing = FoodItem.query.filter_by(name=data["name"]).first()
                if not existing:
                    item = FoodItem(
                        name=data["name"],
                        calories_per_100g=data["calories_per_100g"],
                        protein=data["protein"],
                        carbs=data["carbs"],
                        fats=data["fats"],
                        source=data.get("source", "Unknown")
                    )
                    db.session.add(item)
                    db.session.commit()
                else:
                    item = existing

        if item and "user_id" in session:
            new_log = MealLog(
                food_id=item.id,
                quantity=quantity,
                user_id=session["user_id"]
            )
            db.session.add(new_log)
            db.session.commit()

        return render_template("logmeals.html", item=item, quantity=quantity, searched=searched)

    return render_template("logmeals.html", item=None, quantity=None, searched=searched)


@app.route("/meal_details")
def meal_details():
    if "user_id" not in session:
        flash("Please log in to view your meal details.", "warning")
        return redirect(url_for("login"))

    logs = MealLog.query.filter_by(user_id=session["user_id"]).order_by(MealLog.timestamp.desc()).all()

    enriched_logs = []
    totals = {"calories": 0, "protein": 0, "carbs": 0, "fats": 0}

    for entry in logs:
        food = entry.food
        q = float(entry.quantity)

        cal = float(food.calories_per_100g) * q / 100
        protein = float(food.protein) * q / 100
        carbs = float(food.carbs) * q / 100
        fats = float(food.fats) * q / 100

        # 👇 This is where you add "id": entry.id
        enriched_logs.append({
            "id": entry.id,              # ←←← ADDED HERE
            "name": food.name,
            "quantity": q,
            "calories": round(cal, 2),
            "protein": round(protein, 2),
            "carbs": round(carbs, 2),
            "fats": round(fats, 2),
            "source": food.source,
            "timestamp": entry.timestamp
        })

        totals["calories"] += cal
        totals["protein"] += protein
        totals["carbs"] += carbs
        totals["fats"] += fats

    return render_template(
        "meal_details.html",
        logs=enriched_logs,
        total_calories=round(totals["calories"], 2),
        total_protein=round(totals["protein"], 2),
        total_carbs=round(totals["carbs"], 2),
        total_fats=round(totals["fats"], 2)
    )

# ----------------- API ROUTES -----------------
@app.route("/api/users", methods=["GET"])
def api_get_users():
    users = User.query.all()
    return jsonify({"users": [{"id": u.id, "username": u.username} for u in users]})


@app.route("/api/users/<int:user_id>", methods=["GET"])
def api_get_user(user_id):
    user = User.query.get_or_404(user_id)
    return jsonify({"id": user.id, "username": user.username})


@app.route("/api/fooditems", methods=["GET"])
def api_get_food_items():
    items = FoodItem.query.all()
    return jsonify({
        "food_items": [{
            "id": f.id,
            "name": f.name,
            "calories_per_100g": float(f.calories_per_100g),
            "protein": float(f.protein),
            "carbs": float(f.carbs),
            "fats": float(f.fats),
            "source": f.source
        } for f in items]
    })


@app.route("/api/fooditems/<int:food_id>", methods=["GET"])
def api_get_food_item(food_id):
    f = FoodItem.query.get_or_404(food_id)
    return jsonify({
        "id": f.id,
        "name": f.name,
        "calories_per_100g": float(f.calories_per_100g),
        "protein": float(f.protein),
        "carbs": float(f.carbs),
        "fats": float(f.fats),
        "source": f.source
    })


@app.route("/api/fooditems", methods=["POST"])
def api_add_food_item():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Missing JSON data"}), 400

    required = ["name", "calories_per_100g", "protein", "carbs", "fats"]
    if not all(field in data for field in required):
        return jsonify({"error": "Missing required fields"}), 400

    if FoodItem.query.filter_by(name=data["name"]).first():
        return jsonify({"error": "Food item already exists"}), 400

    try:
        new_food = FoodItem(
            name=data["name"],
            calories_per_100g=safe_decimal(data["calories_per_100g"]),
            protein=safe_decimal(data["protein"]),
            carbs=safe_decimal(data["carbs"]),
            fats=safe_decimal(data["fats"]),
            source=data.get("source", "Unknown")
        )
        db.session.add(new_food)
        db.session.commit()
        return jsonify({"message": "Food item added", "id": new_food.id}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Invalid data: {str(e)}"}), 400


@app.route("/api/meallogs", methods=["GET"])
def api_get_meal_logs():
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    logs = MealLog.query.filter_by(user_id=session["user_id"]).all()
    data = []
    for entry in logs:
        f = entry.food
        q = float(entry.quantity)
        data.append({
            "id": entry.id,
            "food_name": f.name,
            "quantity": q,
            "calories": float(f.calories_per_100g) * q / 100,
            "protein": float(f.protein) * q / 100,
            "carbs": float(f.carbs) * q / 100,
            "fats": float(f.fats) * q / 100,
            "timestamp": entry.timestamp.isoformat()
        })
    return jsonify({"meal_logs": data})


@app.route("/api/meallogs", methods=["POST"])
def api_add_meal_log():
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json()
    if not data or "food_id" not in data or "quantity" not in data:
        return jsonify({"error": "Missing required fields"}), 400

    food_item = FoodItem.query.get(data["food_id"])
    if not food_item:
        return jsonify({"error": "Food item not found"}), 404

    try:
        quantity = float(data["quantity"])
        if quantity <= 0:
            return jsonify({"error": "Quantity must be > 0"}), 400
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid quantity"}), 400

    new_log = MealLog(
        user_id=session["user_id"],
        food_id=food_item.id,
        quantity=Decimal(str(quantity))
    )
    db.session.add(new_log)
    db.session.commit()
    return jsonify({"message": "Meal logged successfully", "id": new_log.id}), 201


@app.route("/api/meallogs/<int:log_id>", methods=["DELETE"])
def api_delete_meal_log(log_id):
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    log = MealLog.query.get_or_404(log_id)
    if log.user_id != session["user_id"]:
        return jsonify({"error": "Forbidden"}), 403

    db.session.delete(log)
    db.session.commit()
    return jsonify({"message": "Meal log deleted"}), 200


@app.route("/api/meallogs/<int:log_id>", methods=["PUT"])
def api_update_meal_log(log_id):
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    log = MealLog.query.get_or_404(log_id)
    if log.user_id != session["user_id"]:
        return jsonify({"error": "Forbidden"}), 403

    data = request.get_json()
    if not data or "quantity" not in data:
        return jsonify({"error": "Missing quantity"}), 400

    try:
        quantity = float(data["quantity"])
        if quantity <= 0:
            return jsonify({"error": "Quantity must be > 0"}), 400
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid quantity"}), 400

    log.quantity = Decimal(str(quantity))
    db.session.commit()
    return jsonify({"message": "Meal log updated", "id": log.id})


# ----------------- MAIN ENTRY -----------------
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)