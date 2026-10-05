"""CycleWise web app: Flask routes and the app factory.

The business logic is in small modules so it can be tested without HTTP:
  cycle_logic.py  cycle averages, irregularity, phase
  chatbot.py      symptom-checker conversation rules (uses the ML model)
  model.py        TF-IDF + logistic regression training and prediction
  passwords.py    salted password hashing with legacy-hash upgrade
  hospitals.py    hospital directory
  reports.py      PDF health report
"""
import hmac
import json
import os
import random
from datetime import date, datetime, timedelta
from functools import wraps
from io import BytesIO

from flask import (Flask, current_app, flash, jsonify, redirect, render_template, request,
                   send_file, session, url_for)
from flask_login import LoginManager, current_user, login_required, login_user, logout_user

from chatbot import get_bot_response
from cycle_logic import PHASE_INFO, calc_stats, get_phase
from database import Cycle, DailyNote, Symptom, User, db
from hospitals import HOSPITALS, find_hospitals
from model import load
from passwords import hash_password, needs_upgrade, verify_password
from reports import build_health_report

CAPTCHA_WORDS = ["health", "cycle", "women", "care", "track", "bloom", "lunar", "peace", "aware", "trust"]


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.update(
        # Secrets come from the environment. The fallback is for local development only.
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev-only-change-me"),
        SQLALCHEMY_DATABASE_URI=os.environ.get("DATABASE_URL", "sqlite:///cyclewise.db"),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        # Admin login is disabled unless both variables are set.
        ADMIN_EMAIL=os.environ.get("ADMIN_EMAIL"),
        ADMIN_PASSWORD=os.environ.get("ADMIN_PASSWORD"),
    )
    if test_config:
        app.config.update(test_config)

    db.init_app(app)
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = "login"

    app.config["PIPELINE"] = load()

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    register_routes(app)

    with app.app_context():
        db.create_all()
    return app


# ── helpers ───────────────────────────────────────────────

def generate_captcha():
    word = random.choice(CAPTCHA_WORDS)
    session["captcha_word"] = word
    return " - ".join(word.upper())


def admin_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not session.get("is_admin"):
            flash("Admin access required.")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapper


def parse_date(value):
    """Parse a YYYY-MM-DD string, returning None for empty input."""
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


def user_cycles(user_id):
    return Cycle.query.filter_by(user_id=user_id).order_by(Cycle.start_date.desc()).all()


def check_admin_credentials(login_input, password):
    admin_email = current_app.config.get("ADMIN_EMAIL")
    admin_password = current_app.config.get("ADMIN_PASSWORD")
    if not admin_email or not admin_password:
        return False  # admin login is switched off when not configured
    return hmac.compare_digest(login_input, admin_email) and hmac.compare_digest(password, admin_password)


# ── routes ────────────────────────────────────────────────

def register_routes(app):

    @app.route("/")
    def landing():
        if session.get("is_admin"):
            return redirect(url_for("admin_dashboard"))
        if current_user.is_authenticated:
            return redirect(url_for("dashboard"))
        return redirect(url_for("login"))

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            login_input = request.form.get("login_input", "").strip()
            password = request.form.get("password", "")

            if check_admin_credentials(login_input, password):
                session["is_admin"] = True
                return redirect(url_for("admin_dashboard"))

            user = User.query.filter_by(email=login_input).first() or \
                   User.query.filter_by(mobile=login_input).first()

            if user and verify_password(user.password, password):
                if needs_upgrade(user.password):
                    user.password = hash_password(password)
                    db.session.commit()
                session.pop("is_admin", None)
                login_user(user)
                return redirect(url_for("dashboard"))

            flash("Invalid email/mobile or password.")
        return render_template("index.html")

    @app.route("/register", methods=["GET", "POST"])
    def register():
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            email = request.form.get("email", "").strip()
            mobile = request.form.get("mobile", "").strip()
            gender = request.form.get("gender", "").strip()
            password = request.form.get("password", "")
            confirm_pw = request.form.get("confirm_password", "")
            captcha = request.form.get("captcha", "").strip().lower()
            agreed = request.form.get("agree")

            def fail(message):
                # issue a fresh captcha after every failed attempt
                flash(message)
                return render_template("register.html", captcha_display=generate_captcha())

            # Check the answer against the word shown on the page, before issuing a new one.
            if captcha != session.get("captcha_word", ""):
                return fail("Incorrect captcha. Please try again.")
            if not agreed:
                return fail("You must agree to the terms before registering.")
            if password != confirm_pw:
                return fail("Passwords do not match.")
            if len(password) < 6:
                return fail("Password must be at least 6 characters.")
            if not mobile.isdigit() or len(mobile) != 10:
                return fail("Please enter a valid 10-digit mobile number.")
            if User.query.filter_by(email=email).first():
                return fail("Email already registered.")

            user = User(name=name, email=email, mobile=mobile, gender=gender,
                        password=hash_password(password))
            db.session.add(user)
            db.session.commit()
            session.pop("captcha_word", None)
            login_user(user)
            return redirect(url_for("dashboard"))

        return render_template("register.html", captcha_display=generate_captcha())

    @app.route("/logout")
    @login_required
    def logout():
        logout_user()
        session.pop("is_admin", None)
        return redirect(url_for("login"))

    # ── admin ─────────────────────────────────────────────

    @app.route("/admin")
    @admin_required
    def admin_dashboard():
        users = User.query.order_by(User.created_at.desc()).all()
        return render_template(
            "admin.html", users=users,
            total_cycles=sum(len(u.cycles) for u in users),
            total_notes=sum(len(u.notes) for u in users),
            total_symptoms=sum(len(u.symptoms) for u in users),
        )

    @app.route("/admin/delete_user/<int:uid>")
    @admin_required
    def admin_delete_user(uid):
        user = db.session.get(User, uid)
        if user:
            db.session.delete(user)
            db.session.commit()
            flash(f"User {user.name} deleted successfully.")
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/logout")
    def admin_logout():
        session.pop("is_admin", None)
        return redirect(url_for("login"))

    # ── dashboard, calendar, notes ────────────────────────

    @app.route("/dashboard")
    @login_required
    def dashboard():
        cycles = user_cycles(current_user.id)
        notes = DailyNote.query.filter_by(user_id=current_user.id) \
                               .order_by(DailyNote.date.desc()).limit(3).all()
        stats = calc_stats(cycles)
        phase = get_phase(cycles[0].start_date if cycles else None, stats["avg_cycle"])
        return render_template("dashboard.html", user=current_user, stats=stats, phase=phase,
                               phase_info=PHASE_INFO.get(phase, PHASE_INFO["unknown"]), notes=notes)

    @app.route("/calendar", methods=["GET", "POST"])
    @login_required
    def calendar():
        if request.method == "POST":
            try:
                start = parse_date(request.form.get("start_date"))
                end = parse_date(request.form.get("end_date"))
            except ValueError:
                flash("Please enter valid dates.")
                return redirect(url_for("calendar"))
            if start is None:
                flash("A start date is required.")
            elif end and end < start:
                flash("End date cannot be before the start date.")
            else:
                db.session.add(Cycle(user_id=current_user.id, start_date=start, end_date=end))
                db.session.commit()
            return redirect(url_for("calendar"))

        cycles = user_cycles(current_user.id)
        stats = calc_stats(cycles)

        period_dates = []
        for c in cycles:
            day, last = c.start_date, c.end_date or c.start_date
            while day <= last:
                period_dates.append(str(day))
                day += timedelta(days=1)

        return render_template("calendar.html", cycles=cycles, stats=stats,
                               period_dates=json.dumps(period_dates))

    @app.route("/delete_cycle/<int:cid>")
    @login_required
    def delete_cycle(cid):
        cycle = Cycle.query.filter_by(id=cid, user_id=current_user.id).first()
        if cycle:
            db.session.delete(cycle)
            db.session.commit()
        return redirect(url_for("calendar"))

    @app.route("/notes", methods=["GET", "POST"])
    @login_required
    def notes():
        if request.method == "POST":
            try:
                note_date = parse_date(request.form.get("date"))
            except ValueError:
                flash("Please enter a valid date.")
                return redirect(url_for("notes"))
            content = request.form.get("content", "")
            mood = request.form.get("mood_tag") or None

            existing = DailyNote.query.filter_by(user_id=current_user.id, date=note_date).first()
            if existing:
                existing.content, existing.mood_tag = content, mood
            else:
                db.session.add(DailyNote(user_id=current_user.id, date=note_date,
                                         content=content, mood_tag=mood))
            db.session.commit()
            return redirect(url_for("notes"))

        all_notes = DailyNote.query.filter_by(user_id=current_user.id) \
                                   .order_by(DailyNote.date.desc()).all()
        return render_template("notes.html", notes=all_notes, today=str(date.today()))

    @app.route("/delete_note/<int:nid>")
    @login_required
    def delete_note(nid):
        note = DailyNote.query.filter_by(id=nid, user_id=current_user.id).first()
        if note:
            db.session.delete(note)
            db.session.commit()
        return redirect(url_for("notes"))

    # ── chat and hospitals ────────────────────────────────

    @app.route("/chat")
    @login_required
    def chat():
        return render_template("chat.html")

    @app.route("/chat/send", methods=["POST"])
    @login_required
    def chat_send():
        data = request.get_json(silent=True) or {}
        messages = data.get("messages", [])

        result = get_bot_response(messages, app.config["PIPELINE"])

        # Keep a record of moderate and severe conversations for the user's report.
        if result["severity"] in ("moderate", "severe"):
            last_user_text = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), None)
            if last_user_text:
                db.session.add(Symptom(user_id=current_user.id, text=last_user_text,
                                       condition=result.get("condition"),
                                       severity=result["severity"]))
                db.session.commit()

        return jsonify(result)

    @app.route("/hospitals")
    @login_required
    def hospitals():
        city = request.args.get("city", "").strip()
        hospital_type = request.args.get("type", "").strip()
        return render_template("hospitals.html",
                               hospitals=find_hospitals(city, hospital_type),
                               cities=sorted(HOSPITALS.keys()),
                               selected_city=city if city in HOSPITALS else "",
                               selected_type=hospital_type)

    # ── report ────────────────────────────────────────────

    @app.route("/report", methods=["GET", "POST"])
    @login_required
    def report():
        if request.method == "POST":
            try:
                start = parse_date(request.form.get("start_date"))
                end = parse_date(request.form.get("end_date")) or date.today()
            except ValueError:
                flash("Please enter valid dates.")
                return redirect(url_for("report"))

            def in_range(query, column):
                if start:
                    query = query.filter(column >= start)
                return query.filter(column <= end)

            cycles = in_range(Cycle.query.filter_by(user_id=current_user.id), Cycle.start_date) \
                        .order_by(Cycle.start_date).all()
            notes = in_range(DailyNote.query.filter_by(user_id=current_user.id), DailyNote.date) \
                        .order_by(DailyNote.date).all()
            symptoms = in_range(Symptom.query.filter_by(user_id=current_user.id), Symptom.date) \
                          .order_by(Symptom.date).all()

            pdf_bytes = build_health_report(current_user.name, start, end,
                                            calc_stats(cycles), notes, symptoms)
            return send_file(BytesIO(pdf_bytes), as_attachment=True,
                             download_name=f"CycleWise_{current_user.name}_{date.today()}.pdf",
                             mimetype="application/pdf")

        return render_template("report.html", today=str(date.today()))


app = create_app()

if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1", port=5000, host="127.0.0.1")
