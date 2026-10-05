import os
import sys

# Make the project root importable (tests live one level below it).
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# Use an in-memory database before app.py is imported, so tests never touch cyclewise.db.
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret")
