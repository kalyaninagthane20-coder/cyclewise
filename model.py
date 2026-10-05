import json
import os
import pickle

import numpy as np
import pandas as pd
from sklearn.dummy import DummyClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold, cross_validate
from sklearn.naive_bayes import MultinomialNB
from sklearn.pipeline import Pipeline

BASE_DIR     = os.path.dirname(__file__)
DATA_PATH    = os.path.join(BASE_DIR, "data", "symptoms.csv")
MODEL_PATH   = os.path.join(BASE_DIR, "model.pkl")
METRICS_PATH = os.path.join(BASE_DIR, "metrics.json")

CONDITION_INFO = {
    "PCOS": {
        "full_name":   "Polycystic Ovary Syndrome (PCOS)",
        "description": "A hormonal disorder causing irregular periods, excess androgen, and cysts on ovaries.",
        "tips": [
            "Maintain a low-carb, balanced diet",
            "Exercise at least 30 minutes daily",
            "Track your periods regularly",
            "Get hormone blood tests (LH, FSH, testosterone)"
        ]
    },
    "Endometriosis": {
        "full_name":   "Endometriosis",
        "description": "Tissue similar to uterine lining grows outside the uterus, causing severe pain during periods.",
        "tips": [
            "Use a heating pad to manage pain",
            "Keep a pain diary to show your doctor",
            "Try an anti-inflammatory diet",
            "Request a gynaecologist referral"
        ]
    },
    "Anaemia": {
        "full_name":   "Iron Deficiency Anaemia",
        "description": "Low iron levels in blood, commonly caused by heavy periods, leading to fatigue and weakness.",
        "tips": [
            "Eat iron-rich foods: spinach, lentils, jaggery",
            "Take Vitamin C with meals to boost iron absorption",
            "Get a CBC blood test done",
            "Avoid tea/coffee immediately after meals"
        ]
    },
    "Hypothyroidism": {
        "full_name":   "Hypothyroidism (Underactive Thyroid)",
        "description": "The thyroid gland produces insufficient hormones, causing fatigue, weight gain, and cold sensitivity.",
        "tips": [
            "Get a TSH blood test — simple and affordable",
            "Highly treatable with daily medication once diagnosed",
            "Avoid excess raw cruciferous vegetables",
            "Tell your doctor about all symptoms"
        ]
    },
    "Fibroids": {
        "full_name":   "Uterine Fibroids",
        "description": "Non-cancerous growths in the uterus causing heavy bleeding, pelvic pressure, and pain.",
        "tips": [
            "Check iron/haemoglobin levels — anaemia is common alongside fibroids",
            "An ultrasound scan can confirm fibroids",
            "Many fibroids only need monitoring, not treatment",
            "See a gynaecologist if bleeding affects daily life"
        ]
    },
    "Perimenopause": {
        "full_name":   "Perimenopause",
        "description": "Natural transition before menopause, usually in the 40s, causing irregular periods and hormonal changes.",
        "tips": [
            "This is a natural transition, not a disease",
            "Regular exercise and good sleep help significantly",
            "Track symptoms to discuss with your doctor",
            "Ask your doctor about Hormone Replacement Therapy (HRT)"
        ]
    }
}

URGENCY_INFO = {
    "green":  {"label": "Monitor at home",    "message": "Your symptoms are mild. Monitor for a few weeks and mention at your next routine visit."},
    "yellow": {"label": "See a doctor soon",  "message": "Your symptoms need attention. Try to see a gynaecologist within 1–2 weeks."},
    "red":    {"label": "Seek care urgently", "message": "Your symptoms suggest a condition needing prompt evaluation. Please see a doctor soon."}
}

CONDITION_URGENCY = {
    "PCOS": "yellow", "Endometriosis": "red",
    "Anaemia": "yellow", "Hypothyroidism": "yellow",
    "Fibroids": "yellow", "Perimenopause": "green"
}

def build_pipeline(classifier):
    """TF-IDF text features (unigrams + bigrams) followed by any sklearn classifier."""
    return Pipeline([
        ("tfidf", TfidfVectorizer(ngram_range=(1, 2), max_features=3000, stop_words="english")),
        ("clf", classifier),
    ])


def candidate_models():
    return {
        "majority_baseline": build_pipeline(DummyClassifier(strategy="most_frequent")),
        "naive_bayes": build_pipeline(MultinomialNB()),
        "logistic_regression": build_pipeline(LogisticRegression(max_iter=1000, C=1.0)),
    }


def evaluate(X, y, n_splits=4):
    """Stratified k-fold cross-validation, so every row is tested exactly once.

    With only 28 rows, a single train/test split would be too noisy to trust.
    Reporting mean and standard deviation across folds gives a fairer picture.
    """
    cv = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)
    results = {}
    for name, model in candidate_models().items():
        scores = cross_validate(model, X, y, cv=cv, scoring=["accuracy", "f1_macro"])
        results[name] = {
            "accuracy_mean": float(np.mean(scores["test_accuracy"])),
            "accuracy_std": float(np.std(scores["test_accuracy"])),
            "f1_macro_mean": float(np.mean(scores["test_f1_macro"])),
            "f1_macro_std": float(np.std(scores["test_f1_macro"])),
        }
    return results


def train():
    df = pd.read_csv(DATA_PATH)
    X, y = df["symptom_text"], df["condition"]

    print(f"Dataset shape: {df.shape}")
    print(f"Conditions: {y.value_counts().to_dict()}")

    results = evaluate(X, y)
    for name, r in results.items():
        print(f"{name:>20}: accuracy {r['accuracy_mean']:.2f} +/- {r['accuracy_std']:.2f}, "
              f"macro-F1 {r['f1_macro_mean']:.2f} +/- {r['f1_macro_std']:.2f}")

    # The production model is fitted on all rows. Its metrics come from the CV above.
    pipeline = build_pipeline(LogisticRegression(max_iter=1000, C=1.0))
    pipeline.fit(X, y)

    with open(MODEL_PATH, "wb") as f:
        pickle.dump(pipeline, f)
    with open(METRICS_PATH, "w") as f:
        json.dump({"rows": int(len(df)), "classes": sorted(y.unique().tolist()),
                   "cv_folds": 4, "models": results}, f, indent=2)
    print("Model and metrics saved.")
    return pipeline

def load():
    if not os.path.exists(MODEL_PATH):
        print("No saved model — training now...")
        return train()
    with open(MODEL_PATH, "rb") as f:
        return pickle.load(f)

def predict(text: str, pipeline) -> dict:
    text_clean = text.lower().strip()
    condition  = pipeline.predict([text_clean])[0]
    proba      = pipeline.predict_proba([text_clean])[0]
    classes    = pipeline.classes_
    confidence = round(float(np.max(proba)) * 100)

    # all condition probabilities for display
    prob_dict = {
        cls: round(float(p) * 100)
        for cls, p in zip(classes, proba)
    }
    prob_dict = dict(sorted(prob_dict.items(), key=lambda x: x[1], reverse=True))

    urgency = CONDITION_URGENCY.get(condition, "yellow")

    return {
        "condition":      condition,
        "condition_info": CONDITION_INFO.get(condition, {}),
        "confidence":     confidence,
        "all_probs":      prob_dict,
        "urgency":        urgency,
        "urgency_info":   URGENCY_INFO.get(urgency, {})
    }

if __name__ == "__main__":
    train()