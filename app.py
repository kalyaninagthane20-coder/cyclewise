from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date, timedelta
from fpdf import FPDF
from io import BytesIO
from flask import send_file
import hashlib
import json
import numpy as np
import os

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

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

# ── CYCLE LOGIC ───────────────────────────────────────────

def calc_stats(cycles):
    if len(cycles) < 2:
        return {"avg_cycle": 28, "avg_period": 5, "irregular": False, "next_period": None, "total": len(cycles)}
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
    return {"avg_cycle": avg_cycle, "avg_period": avg_period, "irregular": irregular,
            "next_period": str(next_p) if next_p else None, "total": len(sorted_c)}

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

    # severity detection
    severe_words   = ["severe", "unbearable", "cant move", "fainted", "very heavy", "weeks", "daily"]
    moderate_words = ["painful", "recurring", "every month", "affecting", "missing work", "bad"]

    is_severe   = any(w in history for w in severe_words)
    is_moderate = any(w in history for w in moderate_words)

    # run ML prediction on last message
    result     = predict(last_msg, pipeline)
    condition  = result["condition"]
    confidence = result["confidence"]
    tips       = result["condition_info"].get("tips", [])

    phase = user_context.get("phase", "unknown")
    irreg = user_context.get("irregular", False)

    # escalation ladder
    num_turns = len([m for m in messages if m["role"] == "user"])

    if num_turns == 1:
        # first message — just ask a follow-up
        replies = [
            "I hear you. How long have you been experiencing this?",
            "Thanks for sharing that. Is this something that happens regularly or just recently?",
            "I understand. Would you say this is affecting your daily life or is it manageable so far?",
            "Got it. Are these symptoms getting worse over time, or staying about the same?"
        ]
        import random
        return {"reply": random.choice(replies), "severity": "mild", "show_condition": False}

    elif num_turns == 2:
        if is_severe:
            return {
                "reply": f"That sounds quite difficult. Based on what you've described, it could be worth looking into {condition}. Are these symptoms affecting your daily activities?",
                "severity": "moderate", "show_condition": True, "condition": condition, "confidence": confidence
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
                "severity": "severe", "show_condition": True, "condition": condition,
                "confidence": confidence, "suggest_report": True
            }
        elif confidence > 60:
            return {
                "reply": f"Your symptoms sound like they could be related to {condition} — but they seem mild right now. Try: {tips[1] if len(tips)>1 else tips[0] if tips else 'tracking your symptoms for 2 more weeks'}. If things don't improve, consider seeing a doctor.",
                "severity": "moderate", "show_condition": True, "condition": condition, "confidence": confidence
            }
        else:
            tip1 = tips[0] if tips else "stay hydrated"
            tip2 = tips[1] if len(tips) > 1 else "get enough sleep"
            return {
                "reply": f"Your symptoms are worth monitoring but don't seem alarming right now. Some things that often help: {tip1}, and {tip2}. Keep tracking how you feel and reach out if it gets worse.",
                "severity": "mild", "show_condition": False
            }

    return {"reply": "I'm here to help. Can you tell me more about how you're feeling?", "severity": "mild", "show_condition": False}

# ── AUTH ROUTES ───────────────────────────────────────────

@app.route("/")
def landing():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        pw    = request.form.get("password")
        user  = User.query.filter_by(email=email).first()
        if user and user.password == hash_pw(pw):
            login_user(user)
            return redirect(url_for("dashboard"))
        flash("Invalid email or password")
    return render_template("index.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name  = request.form.get("name")
        email = request.form.get("email")
        pw    = request.form.get("password")
        if User.query.filter_by(email=email).first():
            flash("Email already registered")
            return render_template("register.html")
        user = User(name=name, email=email, password=hash_pw(pw))
        db.session.add(user)
        db.session.commit()
        login_user(user)
        return redirect(url_for("dashboard"))
    return render_template("register.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))

# ── DASHBOARD ─────────────────────────────────────────────

@app.route("/dashboard")
@login_required
def dashboard():
    cycles = Cycle.query.filter_by(user_id=current_user.id).order_by(Cycle.start_date.desc()).all()
    notes  = DailyNote.query.filter_by(user_id=current_user.id).order_by(DailyNote.date.desc()).limit(3).all()
    stats  = calc_stats(cycles)
    phase  = get_phase(cycles[0].start_date if cycles else None, stats["avg_cycle"])
    return render_template("dashboard.html", user=current_user, stats=stats,
                           phase=phase, phase_info=PHASE_INFO.get(phase, PHASE_INFO["unknown"]),
                           notes=notes)

# ── CALENDAR ──────────────────────────────────────────────

@app.route("/calendar", methods=["GET", "POST"])
@login_required
def calendar():
    if request.method == "POST":
        start = request.form.get("start_date")
        end   = request.form.get("end_date") or None
        c = Cycle(user_id=current_user.id,
                  start_date=datetime.strptime(start, "%Y-%m-%d").date(),
                  end_date=datetime.strptime(end, "%Y-%m-%d").date() if end else None)
        db.session.add(c)
        db.session.commit()
        return redirect(url_for("calendar"))

    cycles = Cycle.query.filter_by(user_id=current_user.id).order_by(Cycle.start_date.desc()).all()
    stats  = calc_stats(cycles)
    period_dates = []
    for c in cycles:
        d = c.start_date
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

# ── NOTES ─────────────────────────────────────────────────

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

# ── CHAT ──────────────────────────────────────────────────

@app.route("/chat")
@login_required
def chat():
    return render_template("chat.html")

@app.route("/chat/send", methods=["POST"])
@login_required
def chat_send():
    data     = request.get_json()
    messages = data.get("messages", [])
    cycles   = Cycle.query.filter_by(user_id=current_user.id).order_by(Cycle.start_date.desc()).all()
    stats    = calc_stats(cycles)
    phase    = get_phase(cycles[0].start_date if cycles else None, stats["avg_cycle"])
    ctx      = {"phase": phase, "irregular": stats["irregular"]}
    result   = get_bot_response(messages, ctx)

    # save symptom if moderate/severe
    if result["severity"] in ("moderate", "severe") and messages:
        last = next((m["content"] for m in reversed(messages) if m["role"] == "user"), None)
        if last:
            s = Symptom(user_id=current_user.id, text=last,
                        condition=result.get("condition"), severity=result["severity"])
            db.session.add(s)
            db.session.commit()

    return jsonify(result)

# ── REPORT ────────────────────────────────────────────────

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

        # helper: strip emojis / non-latin characters safe for PDF
        def safe(text):
            return text.encode("latin-1", errors="ignore").decode("latin-1") if text else ""

        # generate PDF — use DejaVu for full Unicode support
        pdf = FPDF()
        pdf.add_page()
        # fpdf2 bundles DejaVu fonts — locate them via the package path
        import fpdf as _fpdf_pkg
        _fonts_dir = os.path.join(os.path.dirname(_fpdf_pkg.__file__), "fonts")
        _dejavu     = os.path.join(_fonts_dir, "DejaVuSansCondensed.ttf")
        _dejavu_b   = os.path.join(_fonts_dir, "DejaVuSansCondensed-Bold.ttf")

        if os.path.exists(_dejavu):
            pdf.add_font("DejaVu",      fname=_dejavu)
            pdf.add_font("DejaVu", "B", fname=_dejavu_b)
            _font_name = "DejaVu"
        else:
            # fallback: Helvetica (emojis will be stripped by safe())
            _font_name = "Helvetica"

        def set_font(style="", size=11):
            pdf.set_font(_font_name, style, size)

        # header
        pdf.set_fill_color(153, 53, 86)
        pdf.rect(0, 0, 210, 28, "F")
        pdf.set_text_color(255, 255, 255)
        set_font("B", 18)
        pdf.set_xy(10, 8)
        pdf.cell(0, 12, "CycleWise Health Report", ln=True)

        pdf.set_text_color(80, 80, 80)
        set_font("", 10)
        pdf.set_xy(10, 32)
        date_range = f"{start} to {end}" if start else f"All time to {end}"
        pdf.cell(0, 6, f"Name: {current_user.name}  |  Period: {date_range}  |  Generated: {date.today()}", ln=True)

        # cycle stats
        pdf.set_xy(10, 44)
        set_font("B", 13)
        pdf.set_text_color(153, 53, 86)
        pdf.cell(0, 8, "Cycle Summary", ln=True)
        set_font("", 11)
        pdf.set_text_color(60, 60, 60)
        pdf.cell(0, 7, f"Average cycle length: {stats['avg_cycle']} days", ln=True)
        pdf.cell(0, 7, f"Average period length: {stats['avg_period']} days", ln=True)
        pdf.cell(0, 7, f"Total cycles tracked: {stats['total']}", ln=True)
        pdf.cell(0, 7, f"Cycle pattern: {'Irregular' if stats['irregular'] else 'Regular'}", ln=True)
        if stats["next_period"]:
            pdf.cell(0, 7, f"Next period predicted: {stats['next_period']}", ln=True)

        # notes
        if notes:
            pdf.ln(4)
            set_font("B", 13)
            pdf.set_text_color(153, 53, 86)
            pdf.cell(0, 8, "Journal Notes", ln=True)
            set_font("", 10)
            pdf.set_text_color(60, 60, 60)
            for n in notes[:10]:
                mood = f" [{safe(n.mood_tag)}]" if n.mood_tag else ""
                text = safe(n.content[:100]) + ("..." if len(n.content) > 100 else "")
                pdf.multi_cell(0, 6, f"{n.date}{mood}: {text}")
                pdf.ln(1)

        # symptoms
        if symptoms:
            pdf.ln(4)
            set_font("B", 13)
            pdf.set_text_color(153, 53, 86)
            pdf.cell(0, 8, "Symptoms Discussed", ln=True)
            set_font("", 10)
            pdf.set_text_color(60, 60, 60)
            for s in symptoms[:10]:
                sev = f" ({s.severity})" if s.severity else ""
                cond = f" → {s.condition}" if s.condition else ""
                pdf.multi_cell(0, 6, f"{s.date}{sev}: {safe(s.text[:80])}{cond}")
                pdf.ln(1)

        # disclaimer
        pdf.ln(6)
        pdf.set_fill_color(245, 240, 255)
        set_font("", 9)
        pdf.set_text_color(100, 80, 150)
        pdf.multi_cell(0, 6, "CycleWise is for awareness only and does not replace professional medical advice. Always consult a qualified doctor.", fill=True)

        buf = BytesIO()
        pdf.output(buf)
        buf.seek(0)
        return send_file(buf, as_attachment=True,
                         download_name=f"CycleWise_{current_user.name}_{date.today()}.pdf",
                         mimetype="application/pdf")

    return render_template("report.html", today=str(date.today()))

# ── INIT ──────────────────────────────────────────────────

with app.app_context():
    db.create_all()

if __name__ == "__main__":
    app.run(debug=True, port=5000, host="0.0.0.0")