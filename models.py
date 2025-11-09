from datetime import datetime
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_migrate import Migrate




app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "postgresql://postgres:CLFA5ACD5C@localhost:5432/FitCal"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)
migrate = Migrate(app, db)

class FoodItem(db.Model):
    __tablename__ = "food_items"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    calories_per_100g = db.Column(db.Numeric(10, 2), nullable=False)
    protein = db.Column(db.Numeric(10, 2), nullable=False)
    carbs = db.Column(db.Numeric(10, 2), nullable=False)
    fats = db.Column(db.Numeric(10, 2), nullable=False)
    source = db.Column(db.String(50), default="Unknown")

    def __repr__(self):
        return f"<FoodItem {self.name}>"


class Goal(db.Model):
    __tablename__ = "goals"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    goal_type = db.Column(db.String(20), nullable=False, default="maintain")  # lose, maintain, gain
    calories = db.Column(db.Integer, nullable=False)
    duration = db.Column(db.Integer, nullable=False, default=4)  # in weeks
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User", backref="goal")

    def __repr__(self):
        return f"<Goal {self.goal_type} {self.calories} kcal for {self.user.username}>"
    

class MealLog(db.Model):
    __tablename__ = "meal_logs"
    id = db.Column(db.Integer, primary_key=True)
    food_id = db.Column(db.Integer, db.ForeignKey("food_items.id"))
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    quantity = db.Column(db.Float)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationship to FoodItem
    food = db.relationship("FoodItem", backref="meal_logs")

class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    _password = db.Column("password", db.String(500), nullable=False)

    @property
    def password(self):
        raise AttributeError("password is write‑only")

    @password.setter
    def password(self, plain_text):
        self._password = generate_password_hash(plain_text)

    def verify_password(self, plain_text):
        return check_password_hash(self._password, plain_text)

    def __repr__(self):
        return f"<User {self.username}>"

class Meal(db.Model):
    __tablename__ = "meals"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    food_id = db.Column(db.Integer, db.ForeignKey("food_items.id"), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    calories = db.Column(db.Numeric(10, 2), nullable=False)
    date = db.Column(db.DateTime(timezone=True), default=datetime.utcnow)

    user = db.relationship("User", backref="meals")
    food_item = db.relationship("FoodItem", backref="meals")

    def __repr__(self):
        return f"<Meal {self.id} for {self.user.username}>"

with app.app_context():
    db.create_all()
