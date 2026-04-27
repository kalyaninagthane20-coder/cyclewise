from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash, send_file
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from datetime import datetime, date, timedelta
from fpdf import FPDF
from io import BytesIO
import hashlib, random, string, json, os

from database import db, User, Cycle, DailyNote, Symptom
from model import load, predict, CONDITION_INFO, URGENCY_INFO

app = Flask(__name__)
app.secret_key = "cyclewise-mini-secret"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///cyclewise.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

pipeline = load()

# ── HARDCODED ADMIN ───────────────────────────────────────
ADMIN_EMAIL    = "admin@cyclewise.com"
ADMIN_PASSWORD = "Admin@2025"

# ── FIXED HOSPITAL LIST ───────────────────────────────────
HOSPITALS = {
    "Mumbai": [
        {"name": "KEM Hospital",              "address": "Acharya Donde Marg, Parel",          "phone": "022-24136051", "type": "Government"},
        {"name": "Cama & Albless Hospital",   "address": "Mahapalika Marg, Fort",              "phone": "022-22620684", "type": "Government"},
        {"name": "Wadia Hospital for Women",  "address": "Acharya Donde Marg, Parel",          "phone": "022-24129929", "type": "Government"},
        {"name": "Hinduja Hospital",          "address": "Veer Savarkar Marg, Mahim",          "phone": "022-24452222", "type": "Private"},
        {"name": "Lilavati Hospital",         "address": "A-791 Bandra Reclamation, Bandra",   "phone": "022-26751000", "type": "Private"},
    ],
    "Pune": [
        {"name": "Sassoon General Hospital",  "address": "Jai Prakash Narayan Road, Pune",     "phone": "020-26128000", "type": "Government"},
        {"name": "Jehangir Hospital",         "address": "32 Sassoon Road, Sangamvadi",        "phone": "020-66810000", "type": "Private"},
        {"name": "Ruby Hall Clinic",          "address": "40 Sassoon Road, Pune",              "phone": "020-66455100", "type": "Private"},
        {"name": "Deenanath Mangeshkar",      "address": "Erandwane, Pune",                    "phone": "020-49150300", "type": "Private"},
        {"name": "Aundh District Hospital",   "address": "Aundh, Pune",                        "phone": "020-25880151", "type": "Government"},
    ],
    "Kolhapur": [
        {"name": "Kolhapur Civil Hospital",   "address": "Tarabai Park, Kolhapur",             "phone": "0231-2521137", "type": "Government"},
        {"name": "Sahyadri Hospital",         "address": "Near Bus Stand, Kolhapur",           "phone": "0231-2522222", "type": "Private"},
        {"name": "Chhatrapati Pramila Raje",  "address": "CPR Road, Kolhapur",                 "phone": "0231-2543022", "type": "Government"},
    ],
    "Nagpur": [
        {"name": "AIIMS Nagpur",              "address": "Plot No 2, Sector 20, MIHAN",        "phone": "0712-2807700", "type": "Government"},
        {"name": "Wockhardt Hospital",        "address": "Trimurti Nagar, Nagpur",             "phone": "0712-6116116", "type": "Private"},
        {"name": "Orange City Hospital",      "address": "Wathoda Road, Nagpur",               "phone": "0712-6604999", "type": "Private"},
        {"name": "Government Medical College","address": "Hanuman Nagar, Nagpur",              "phone": "0712-2748888", "type": "Government"},
    ],
    "Nashik": [
        {"name": "Dr Zakir Hussain Hospital", "address": "Nashik Road, Nashik",                "phone": "0253-2465001", "type": "Government"},
        {"name": "Wockhardt Hospital Nashik", "address": "Bombay Naka, Nashik",                "phone": "0253-6633333", "type": "Private"},
        {"name": "Bharat Agro Hospital",      "address": "College Road, Nashik",               "phone": "0253-2317777", "type": "Private"},
    ],
    "Aurangabad": [
        {"name": "Government Medical College","address": "Aurangabad, Maharashtra",            "phone": "0240-2402412", "type": "Government"},
        {"name": "Kamalnayan Bajaj Hospital", "address": "Satara Parisar, Aurangabad",         "phone": "0240-2352222", "type": "Private"},
    ],
    "Delhi": [
        {"name": "AIIMS Delhi (OBG dept)",    "address": "Ansari Nagar East, New Delhi",       "phone": "011-26588500", "type": "Government"},
        {"name": "Safdarjung Hospital",       "address": "Ansari Nagar West, New Delhi",       "phone": "011-26165060", "type": "Government"},
        {"name": "Fortis La Femme",           "address": "Greater Kailash, New Delhi",         "phone": "011-42007777", "type": "Private"},
    ],
    "Bangalore": [
        {"name": "Bangalore Medical College", "address": "Fort Road, Bangalore",               "phone": "080-22867400", "type": "Government"},
        {"name": "Manipal Hospital",          "address": "98 HAL Airport Road, Bangalore",     "phone": "080-25024444", "type": "Private"},
        {"name": "Cloudnine Hospital",        "address": "Bellandur, Bangalore",               "phone": "080-40182929", "type": "Private"},
    ],
    "Hyderabad": [
        {"name": "Niloufer Hospital",         "address": "Red Hills, Hyderabad",               "phone": "040-23320401", "type": "Government"},
        {"name": "KIMS Hospital",             "address": "Minister Road, Secunderabad",        "phone": "040-44885000", "type": "Private"},
        {"name": "Rainbow Hospital",          "address": "Banjara Hills, Hyderabad",           "phone": "040-44555333", "type": "Private"},
    ],
}

# ── CAPTCHA ───────────────────────────────────────────────
CAPTCHA_WORDS = [
    "health", "cycle", "women", "care", "track",
    "bloom", "lunar", "peace", "aware", "trust"
]

def generate_captcha():
    word = random.choice(CAPTCHA_WORDS)
    session["captcha_word"] = word
    return " - ".join(word.upper())

# ── HELPERS ───────────────────────────────────────────────
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

# ── CYCLE LOGIC ───────────────────────────────────────────
def calc_stats(cycles):
    if len(cycles) < 2:
        return {"avg_cycle": 28, "avg_period": 5, "irregular": False,
                "next_period": None, "total": len(cycles)}
    sorted_c = sorted(cycles, key=lambda c: c.start_date)
    gaps, lengths = [], []
    for i in range(1, len(sorted_c)):
        gap = (sorted_c[i].start_date - sorted_c[i-1].start_date).days
        if 15 <= gap <= 50:
            gaps.append(gap)
    for c in sorted_c:
        if c.end_date:
            l = (c.end_date - c.start_date).days + 1
            if 1 <= l <= 10:
                lengths.append(l)
    avg_cycle  = round(sum(gaps) / len(gaps)) if gaps else 28
    avg_period = round(sum(lengths) / len(lengths)) if lengths else 5
    irregular  = bool(gaps and (max(gaps) - min(gaps) > 7))
    next_p     = sorted_c[-1].start_date + timedelta(days=avg_cycle) if sorted_c else None
    return {"avg_cycle": avg_cycle, "avg_period": avg_period,
            "irregular": irregular, "next_period": str(next_p) if next_p else None,
            "total": len(sorted_c)}

def get_phase(last_start, avg_cycle):
    if not last_start:
        return "unknown"
    day = (date.today() - last_start).days + 1
    if day <= 5:           return "menstrual"
    elif day <= 13:        return "follicular"
    elif day <= 16:        return "ovulation"
    elif day <= avg_cycle: return "luteal"
    else:                  return "late"

PHASE_INFO = {
    "menstrual":  {"label": "Menstrual Phase",  "color": "#D4537E", "tip": "Rest and stay warm. Iron-rich foods recommended."},
    "follicular": {"label": "Follicular Phase", "color": "#378ADD", "tip": "Energy is rising — good time for new activities."},
    "ovulation":  {"label": "Ovulation Phase",  "color": "#1D9E75", "tip": "Peak energy day. Great time for exercise."},
    "luteal":     {"label": "Luteal Phase",      "color": "#BA7517", "tip": "You may feel bloated. Magnesium-rich foods help."},
    "late":       {"label": "Late Cycle",        "color": "#7F77DD", "tip": "Period may be approaching soon."},
    "unknown":    {"label": "Log Your Cycle",    "color": "#888",    "tip": "Add your period dates to see cycle insights."},
}

# ── CHAT LOGIC ────────────────────────────────────────────
def get_bot_response(messages, user_context):
    last_msg = messages[-1]["content"].lower() if messages else ""
    history  = " ".join([m["content"].lower() for m in messages])

    severe_words   = ["severe", "unbearable", "cant move", "fainted", "very heavy", "weeks", "daily"]
    moderate_words = ["painful", "recurring", "every month", "affecting", "missing work", "bad"]

    is_severe   = any(w in history for w in severe_words)
    is_moderate = any(w in history for w in moderate_words)

    result     = predict(last_msg, pipeline)
    condition  = result["condition"]
    confidence = result["confidence"]
    tips       = result["condition_info"].get("tips", [])

    num_turns = len([m for m in messages if m["role"] == "user"])

    if num_turns == 1:
        replies = [
            "I hear you. How long have you been experiencing this?",
            "Thanks for sharing. Is this something that happens regularly or just recently?",
            "I understand. Would you say this is affecting your daily life or is it manageable?",
            "Got it. Are these symptoms getting worse over time, or staying about the same?"
        ]
        return {"reply": random.choice(replies), "severity": "mild", "show_condition": False}

    elif num_turns == 2:
        if is_severe:
            return {
                "reply": f"That sounds quite difficult. Based on what you've described, it could be worth looking into {condition}. Are these symptoms affecting your daily activities?",
                "severity": "moderate", "show_condition": True,
                "condition": condition, "confidence": confidence
            }
        else:
            tip = tips[0] if tips else "drink plenty of water and rest well"
            return {
                "reply": f"That sounds manageable for now. A simple tip: {tip}. Have you noticed if your symptoms are worse at any particular time of the month?",
                "severity": "mild", "show_condition": False
            }

    elif num_turns >= 3:
        if is_severe or (confidence > 60 and is_moderate):
            return {
                "reply": f"Based on everything you've described, the symptoms are consistent with {condition}. Given that they seem to be affecting your daily life, I'd recommend seeing a gynaecologist. Would you like me to generate a health summary for your doctor?",
                "severity": "severe", "show_condition": True,
                "condition": condition, "confidence": confidence, "suggest_report": True
            }
        elif confidence > 60:
            return {
                "reply": f"Your symptoms sound like they could be related to {condition} — but they seem mild right now. Try: {tips[1] if len(tips)>1 else tips[0] if tips else 'tracking your symptoms for 2 more weeks'}. If things don't improve, consider seeing a doctor.",
                "severity": "moderate", "show_condition": True,
                "condition": condition, "confidence": confidence
            }
        else:
            tip1 = tips[0] if tips else "stay hydrated"
            tip2 = tips[1] if len(tips) > 1 else "get enough sleep"
            return {
                "reply": f"Your symptoms are worth monitoring but don't seem alarming right now. Some things that often help: {tip1}, and {tip2}. Keep tracking how you feel.",
                "severity": "mild", "show_condition": False
            }

    return {"reply": "I'm here to help. Can you tell me more about how you're feeling?",
            "severity": "mild", "show_condition": False}

# ── ADMIN DECORATOR ───────────────────────────────────────
def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("is_admin"):
            flash("Admin access required.")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

# ══════════════════════════════════════════════════════════
# AUTH ROUTES
# ══════════════════════════════════════════════════════════

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
        pw          = request.form.get("password", "")

        # hardcoded admin check
        if login_input == ADMIN_EMAIL and pw == ADMIN_PASSWORD:
            session["is_admin"] = True
            return redirect(url_for("admin_dashboard"))

        # normal user — email or mobile
        user = User.query.filter_by(email=login_input).first()
        if not user:
            user = User.query.filter_by(mobile=login_input).first()

        if user and user.password == hash_pw(pw):
            session.pop("is_admin", None)
            login_user(user)
            return redirect(url_for("dashboard"))

        flash("Invalid email/mobile or password.")
    return render_template("index.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    captcha_display = generate_captcha()

    if request.method == "POST":
        name       = request.form.get("name", "").strip()
        email      = request.form.get("email", "").strip()
        mobile     = request.form.get("mobile", "").strip()
        gender     = request.form.get("gender", "").strip()
        password   = request.form.get("password", "")
        confirm_pw = request.form.get("confirm_password", "")
        captcha    = request.form.get("captcha", "").strip().lower()
        agree      = request.form.get("agree")

        captcha_display = generate_captcha()

        if not agree:
            flash("You must agree to the terms before registering.")
            return render_template("register.html", captcha_display=captcha_display)

        if password != confirm_pw:
            flash("Passwords do not match.")
            return render_template("register.html", captcha_display=captcha_display)

        if len(password) < 6:
            flash("Password must be at least 6 characters.")
            return render_template("register.html", captcha_display=captcha_display)

        if captcha != session.get("captcha_word", ""):
            flash("Incorrect captcha. Please try again.")
            return render_template("register.html", captcha_display=captcha_display)

        if not mobile.isdigit() or len(mobile) != 10:
            flash("Please enter a valid 10-digit mobile number.")
            return render_template("register.html", captcha_display=captcha_display)

        if User.query.filter_by(email=email).first():
            flash("Email already registered.")
            return render_template("register.html", captcha_display=captcha_display)

        user = User(name=name, email=email, mobile=mobile,
                    gender=gender, password=hash_pw(password))
        db.session.add(user)
        db.session.commit()
        login_user(user)
        return redirect(url_for("dashboard"))

    return render_template("register.html", captcha_display=captcha_display)

@app.route("/logout")
@login_required
def logout():
    logout_user()
    session.pop("is_admin", None)
    return redirect(url_for("login"))

# ══════════════════════════════════════════════════════════
# ADMIN ROUTES
# ══════════════════════════════════════════════════════════

@app.route("/admin")
@admin_required
def admin_dashboard():
    users          = User.query.order_by(User.created_at.desc()).all()
    total_cycles   = sum(len(u.cycles)   for u in users)
    total_notes    = sum(len(u.notes)    for u in users)
    total_symptoms = sum(len(u.symptoms) for u in users)
    return render_template("admin.html", users=users,
                           total_cycles=total_cycles,
                           total_notes=total_notes,
                           total_symptoms=total_symptoms)

@app.route("/admin/delete_user/<int:uid>")
@admin_required
def admin_delete_user(uid):
    user = User.query.get(uid)
    if user:
        db.session.delete(user)
        db.session.commit()
        flash(f"User {user.name} deleted successfully.")
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/logout")
def admin_logout():
    session.pop("is_admin", None)
    return redirect(url_for("login"))

# ══════════════════════════════════════════════════════════
# DASHBOARD
# ══════════════════════════════════════════════════════════

@app.route("/dashboard")
@login_required
def dashboard():
    cycles = Cycle.query.filter_by(user_id=current_user.id).order_by(Cycle.start_date.desc()).all()
    notes  = DailyNote.query.filter_by(user_id=current_user.id).order_by(DailyNote.date.desc()).limit(3).all()
    stats  = calc_stats(cycles)
    phase  = get_phase(cycles[0].start_date if cycles else None, stats["avg_cycle"])
    return render_template("dashboard.html", user=current_user, stats=stats,
                           phase=phase,
                           phase_info=PHASE_INFO.get(phase, PHASE_INFO["unknown"]),
                           notes=notes)

# ══════════════════════════════════════════════════════════
# CALENDAR
# ══════════════════════════════════════════════════════════

@app.route("/calendar", methods=["GET", "POST"])
@login_required
def calendar():
    if request.method == "POST":
        start = request.form.get("start_date")
        end   = request.form.get("end_date") or None
        c = Cycle(
            user_id    = current_user.id,
            start_date = datetime.strptime(start, "%Y-%m-%d").date(),
            end_date   = datetime.strptime(end, "%Y-%m-%d").date() if end else None
        )
        db.session.add(c)
        db.session.commit()
        return redirect(url_for("calendar"))

    cycles = Cycle.query.filter_by(user_id=current_user.id).order_by(Cycle.start_date.desc()).all()
    stats  = calc_stats(cycles)

    period_dates = []
    for c in cycles:
        d   = c.start_date
        end = c.end_date or c.start_date
        while d <= end:
            period_dates.append(str(d))
            d += timedelta(days=1)

    return render_template("calendar.html", cycles=cycles, stats=stats,
                           period_dates=json.dumps(period_dates))

@app.route("/delete_cycle/<int:cid>")
@login_required
def delete_cycle(cid):
    c = Cycle.query.filter_by(id=cid, user_id=current_user.id).first()
    if c:
        db.session.delete(c)
        db.session.commit()
    return redirect(url_for("calendar"))

# ══════════════════════════════════════════════════════════
# NOTES / JOURNAL
# ══════════════════════════════════════════════════════════

@app.route("/notes", methods=["GET", "POST"])
@login_required
def notes():
    if request.method == "POST":
        d       = request.form.get("date")
        content = request.form.get("content")
        mood    = request.form.get("mood_tag") or None
        existing = DailyNote.query.filter_by(
            user_id=current_user.id,
            date=datetime.strptime(d, "%Y-%m-%d").date()
        ).first()
        if existing:
            existing.content  = content
            existing.mood_tag = mood
        else:
            note = DailyNote(user_id=current_user.id,
                             date=datetime.strptime(d, "%Y-%m-%d").date(),
                             content=content, mood_tag=mood)
            db.session.add(note)
        db.session.commit()
        return redirect(url_for("notes"))

    all_notes = DailyNote.query.filter_by(user_id=current_user.id).order_by(DailyNote.date.desc()).all()
    return render_template("notes.html", notes=all_notes, today=str(date.today()))

@app.route("/delete_note/<int:nid>")
@login_required
def delete_note(nid):
    n = DailyNote.query.filter_by(id=nid, user_id=current_user.id).first()
    if n:
        db.session.delete(n)
        db.session.commit()
    return redirect(url_for("notes"))

# ══════════════════════════════════════════════════════════
# CHAT
# ══════════════════════════════════════════════════════════

@app.route("/chat")
@login_required
def chat():
    return render_template("chat.html")

@app.route("/chat/send", methods=["POST"])
@login_required
def chat_send():
    data     = request.get_json()
    messages = data.get("messages", [])

    cycles = Cycle.query.filter_by(user_id=current_user.id).order_by(Cycle.start_date.desc()).all()
    stats  = calc_stats(cycles)
    phase  = get_phase(cycles[0].start_date if cycles else None, stats["avg_cycle"])
    ctx    = {"phase": phase, "irregular": stats["irregular"]}

    result = get_bot_response(messages, ctx)

    # save symptom if moderate or severe
    if result["severity"] in ("moderate", "severe") and messages:
        last = next((m["content"] for m in reversed(messages) if m["role"] == "user"), None)
        if last:
            s = Symptom(user_id=current_user.id, text=last,
                        condition=result.get("condition"),
                        severity=result["severity"])
            db.session.add(s)
            db.session.commit()

    return jsonify(result)

# ══════════════════════════════════════════════════════════
# HOSPITALS
# ══════════════════════════════════════════════════════════

@app.route("/hospitals")
@login_required
def hospitals():
    selected_city = request.args.get("city", "").strip()
    selected_type = request.args.get("type", "").strip()
    cities        = sorted(HOSPITALS.keys())

    if selected_city and selected_city in HOSPITALS:
        results = HOSPITALS[selected_city]
    else:
        results       = [h for city_list in HOSPITALS.values() for h in city_list]
        selected_city = ""

    if selected_type:
        results = [h for h in results if h["type"] == selected_type]

    return render_template("hospitals.html",
                           hospitals=results,
                           cities=cities,
                           selected_city=selected_city,
                           selected_type=selected_type)

# ══════════════════════════════════════════════════════════
# REPORT
# ══════════════════════════════════════════════════════════

@app.route("/report", methods=["GET", "POST"])
@login_required
def report():
    if request.method == "POST":
        start_str = request.form.get("start_date")
        end_str   = request.form.get("end_date")
        start     = datetime.strptime(start_str, "%Y-%m-%d").date() if start_str else None
        end       = datetime.strptime(end_str,   "%Y-%m-%d").date() if end_str   else date.today()

        cycles_q   = Cycle.query.filter_by(user_id=current_user.id)
        notes_q    = DailyNote.query.filter_by(user_id=current_user.id)
        symptoms_q = Symptom.query.filter_by(user_id=current_user.id)

        if start:
            cycles_q   = cycles_q.filter(Cycle.start_date >= start)
            notes_q    = notes_q.filter(DailyNote.date >= start)
            symptoms_q = symptoms_q.filter(Symptom.date >= start)
        if end:
            cycles_q   = cycles_q.filter(Cycle.start_date <= end)
            notes_q    = notes_q.filter(DailyNote.date <= end)
            symptoms_q = symptoms_q.filter(Symptom.date <= end)

        cycles   = cycles_q.order_by(Cycle.start_date).all()
        notes    = notes_q.order_by(DailyNote.date).all()
        symptoms = symptoms_q.order_by(Symptom.date).all()
        stats    = calc_stats(cycles)

        # generate PDF
        pdf = FPDF()
        pdf.add_page()

        # header bar
        pdf.set_fill_color(153, 53, 86)
        pdf.rect(0, 0, 210, 28, "F")
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("Helvetica", "B", 18)
        pdf.set_xy(10, 8)
        pdf.cell(0, 12, "CycleWise Health Report", ln=True)

        # meta info
        pdf.set_text_color(80, 80, 80)
        pdf.set_font("Helvetica", "", 10)
        pdf.set_xy(10, 32)
        date_range = f"{start} to {end}" if start else f"All time to {end}"
        pdf.cell(0, 6, f"Name: {current_user.name}  |  Period: {date_range}  |  Generated: {date.today()}", ln=True)

        # cycle stats
        pdf.set_xy(10, 44)
        pdf.set_font("Helvetica", "B", 13)
        pdf.set_text_color(153, 53, 86)
        pdf.cell(0, 8, "Cycle Summary", ln=True)
        pdf.set_font("Helvetica", "", 11)
        pdf.set_text_color(60, 60, 60)
        pdf.cell(0, 7, f"Average cycle length : {stats['avg_cycle']} days", ln=True)
        pdf.cell(0, 7, f"Average period length: {stats['avg_period']} days", ln=True)
        pdf.cell(0, 7, f"Total cycles tracked : {stats['total']}", ln=True)
        pdf.cell(0, 7, f"Cycle pattern        : {'Irregular' if stats['irregular'] else 'Regular'}", ln=True)
        if stats["next_period"]:
            pdf.cell(0, 7, f"Next period predicted: {stats['next_period']}", ln=True)

        # notes
        if notes:
            pdf.ln(4)
            pdf.set_font("Helvetica", "B", 13)
            pdf.set_text_color(153, 53, 86)
            pdf.cell(0, 8, "Journal Notes", ln=True)
            pdf.set_font("Helvetica", "", 10)
            pdf.set_text_color(60, 60, 60)
            for n in notes[:10]:
                mood = f" [{n.mood_tag}]" if n.mood_tag else ""
                text = n.content[:100] + ("..." if len(n.content) > 100 else "")
                pdf.multi_cell(0, 6, f"{n.date}{mood}: {text}")
                pdf.ln(1)

        # symptoms
        if symptoms:
            pdf.ln(4)
            pdf.set_font("Helvetica", "B", 13)
            pdf.set_text_color(153, 53, 86)
            pdf.cell(0, 8, "Symptoms Discussed", ln=True)
            pdf.set_font("Helvetica", "", 10)
            pdf.set_text_color(60, 60, 60)
            for s in symptoms[:10]:
                sev  = f" ({s.severity})" if s.severity else ""
                cond = f" -> {s.condition}" if s.condition else ""
                pdf.multi_cell(0, 6, f"{s.date}{sev}: {s.text[:80]}{cond}")
                pdf.ln(1)

        # disclaimer
        pdf.ln(6)
        pdf.set_fill_color(245, 240, 255)
        pdf.set_font("Helvetica", "I", 9)
        pdf.set_text_color(100, 80, 150)
        pdf.multi_cell(0, 6,
            "CycleWise is for awareness only and does not replace professional medical advice. "
            "Always consult a qualified doctor.", fill=True)

        buf = BytesIO()
        pdf.output(buf)
        buf.seek(0)
        return send_file(buf, as_attachment=True,
                         download_name=f"CycleWise_{current_user.name}_{date.today()}.pdf",
                         mimetype="application/pdf")

    return render_template("report.html", today=str(date.today()))

# ══════════════════════════════════════════════════════════
# INIT DB
# ══════════════════════════════════════════════════════════

with app.app_context():
    db.create_all()

if __name__ == "__main__":
    app.run(debug=True, port=5000, host="0.0.0.0")