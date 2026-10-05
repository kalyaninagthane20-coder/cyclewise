# CycleWise: ML-Powered Women's Health and Cycle Tracking

A Flask web app for period tracking, cycle prediction, a symptom checker that uses a
trained text classifier, journal notes, a hospital directory and PDF health reports.

> Awareness tool only. It does not replace medical advice.

## Features

| Area | What it does |
|---|---|
| Cycle analytics | Average cycle and period length, next-period prediction, irregular-cycle detection, current phase |
| Symptom checker | Chatbot that asks follow-up questions and predicts one of six conditions, with confidence and urgency |
| Journal | One note per day with an optional mood tag |
| Health report | Downloadable PDF summary of cycles, notes and symptoms for a chosen date range |
| Hospitals | Directory of government and private hospitals, filterable by city and type |
| Admin | Users list, totals, and user deletion (admin login is configured with environment variables) |

## Architecture

```
          Browser (Jinja2 templates, vanilla JS)
                     │  HTTP
┌────────────────────▼─────────────────────────────────────────┐
│ app.py  Flask routes, sessions (Flask-Login), CAPTCHA        │
│   │                                                          │
│   ├── chatbot.py ─────► model.py  (TF-IDF + Logistic Reg.)   │
│   ├── cycle_logic.py     pure functions: stats, phase        │
│   ├── reports.py         fpdf2 PDF generation                │
│   ├── hospitals.py       static directory                    │
│   └── passwords.py       salted hashing + legacy upgrade     │
│                                                              │
│ database.py  SQLAlchemy models: User, Cycle, DailyNote,      │
│              Symptom        (SQLite locally, DATABASE_URL)   │
└──────────────────────────────────────────────────────────────┘
```

Each module has one job and no hidden global state. The pure modules
(`cycle_logic`, `model`, `passwords`) do not import Flask, so they are tested directly.

## The machine-learning part

**Task.** Given a free-text description of symptoms, predict one of six conditions:
PCOS, Endometriosis, Anaemia, Hypothyroidism, Fibroids, Perimenopause. The
predicted condition then maps to tips and an urgency level (green, yellow or red).

**Pipeline.**

```
symptom text ─► lower-case ─► TF-IDF (1–2-grams, 3000 features, English stop words)
             ─► LogisticRegression (multinomial, lbfgs, C = 1.0) ─► class + probabilities
```

**Evaluation.** Stratified 4-fold cross-validation on the 28-row dataset in
`data/symptoms.csv`. Every row is tested exactly once, and the results are saved to
`metrics.json` each time the model is trained.

| Model | Accuracy (mean ± std) | Macro-F1 (mean ± std) |
|---|---|---|
| Majority-class baseline | 0.14 ± 0.00 | 0.04 ± 0.00 |
| Multinomial Naive Bayes | 0.50 ± 0.16 | 0.38 ± 0.13 |
| **Logistic Regression (deployed)** | **0.54 ± 0.16** | **0.42 ± 0.14** |

**Honest limitations.**

* The dataset is small (28 hand-written examples, 4–6 per class). The scores are indicative,
  not clinical validity, and the spread between folds is wide.
* The model was never tested on real patient data.
* Confidence scores are the model's softmax probabilities. They are not calibrated probabilities of a diagnosis.

**Next steps.** Collect more labelled and consented data, try calibrated probabilities,
compare character n-grams and sentence embeddings, and report results on a held-out set
written by clinicians.

## Running locally

Requires Python 3.10+.

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows (macOS/Linux: source .venv/bin/activate)
pip install -r requirements-dev.txt
python model.py                 # trains model.pkl and writes metrics.json
python app.py                   # http://127.0.0.1:5000
```

Run the tests:

```bash
pytest
```

## Configuration

| Variable | Purpose | Default |
|---|---|---|
| `SECRET_KEY` | Session signing key. **Always set this in production.** | `dev-only-change-me` |
| `DATABASE_URL` | SQLAlchemy URL | `sqlite:///cyclewise.db` |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | Enable the admin login. Both must be set. | disabled |
| `FLASK_DEBUG` | Set to `1` for the debug server locally. Never in production. | off |

Deployment on Render uses `render.yaml` (`gunicorn app:app`). Set the variables above in
the Render dashboard.

## Security

* Passwords use salted scrypt hashes (Werkzeug). The first version stored unsalted SHA-256 hashes.
  Those still log in, and are re-hashed on the next successful login.
* The admin credentials are no longer in source code. They come from environment variables, and
  the comparison is constant-time.
* Users only see and change their own cycles, notes and symptoms (every query is filtered by `user_id`).
* The CAPTCHA is checked against the word on the page the user loaded, and a new one is issued after a failed attempt.
* Report downloads and chat requests require login.

**Known limitation.** Deleting a user from the admin page is a `GET` request, so it is open to
CSRF. Changing it to `POST` with a form token is the next fix.

## Project layout

```
app.py            routes and app factory
model.py          training, evaluation, prediction
chatbot.py        symptom-checker conversation rules
cycle_logic.py    cycle statistics and phases
passwords.py      password hashing
reports.py        PDF report
hospitals.py      hospital directory
database.py       SQLAlchemy models
data/symptoms.csv labelled training data
metrics.json      cross-validation results from the last training run
tests/            pytest suite (cycle logic, passwords, model and chat, Flask routes)
templates/        Jinja2 pages
static/           CSS
```
