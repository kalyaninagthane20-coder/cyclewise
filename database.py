from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime, date

db = SQLAlchemy()

class User(UserMixin, db.Model):
    id            = db.Column(db.Integer, primary_key=True)
    name          = db.Column(db.String(100), nullable=False)
    email         = db.Column(db.String(120), unique=True, nullable=False)
    mobile        = db.Column(db.String(15), nullable=False)
    gender        = db.Column(db.String(20), nullable=False)
    password      = db.Column(db.String(200), nullable=False)
    is_admin      = db.Column(db.Boolean, default=False)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)
    cycles        = db.relationship("Cycle",     back_populates="user", cascade="all, delete")
    notes         = db.relationship("DailyNote", back_populates="user", cascade="all, delete")
    symptoms      = db.relationship("Symptom",   back_populates="user", cascade="all, delete")

class Cycle(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date   = db.Column(db.Date, nullable=True)
    user       = db.relationship("User", back_populates="cycles")

class DailyNote(db.Model):
    id       = db.Column(db.Integer, primary_key=True)
    user_id  = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    date     = db.Column(db.Date, nullable=False, default=date.today)
    content  = db.Column(db.Text, nullable=False)
    mood_tag = db.Column(db.String(50), nullable=True)
    user     = db.relationship("User", back_populates="notes")

class Symptom(db.Model):
    id        = db.Column(db.Integer, primary_key=True)
    user_id   = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    date      = db.Column(db.Date, default=date.today)
    text      = db.Column(db.Text, nullable=False)
    condition = db.Column(db.String(100), nullable=True)
    severity  = db.Column(db.String(20), nullable=True)
    user      = db.relationship("User", back_populates="symptoms")