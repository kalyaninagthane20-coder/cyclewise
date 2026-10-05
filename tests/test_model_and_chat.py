import pytest

from chatbot import get_bot_response
from model import CONDITION_INFO, candidate_models, load, predict


@pytest.fixture(scope="module")
def pipeline():
    return load()


def test_pipeline_predicts_a_known_condition(pipeline):
    result = predict("extremely painful periods and pain during sex", pipeline)
    assert result["condition"] in CONDITION_INFO
    assert 0 <= result["confidence"] <= 100
    assert result["urgency"] in ("green", "yellow", "red")
    # probabilities are reported for every class, highest first
    values = list(result["all_probs"].values())
    assert values == sorted(values, reverse=True)
    assert len(values) == len(CONDITION_INFO)


def test_candidate_models_are_all_pipelines():
    # the evaluation compares the same TF-IDF front end with different classifiers
    names = set(candidate_models())
    assert names == {"majority_baseline", "naive_bayes", "logistic_regression"}


def _chat(turns, pipeline):
    messages = []
    response = None
    for text in turns:
        messages.append({"role": "user", "content": text})
        response = get_bot_response(messages, pipeline)
        messages.append({"role": "assistant", "content": response["reply"]})
    return response


def test_first_turn_asks_a_follow_up_question(pipeline):
    response = _chat(["my period is painful"], pipeline)
    assert response["severity"] == "mild"
    assert response["show_condition"] is False


def test_severe_wording_escalates_by_third_turn(pipeline):
    response = _chat(["periods are unbearable", "this is every month", "it is severe"], pipeline)
    assert response["severity"] == "severe"
    assert response["suggest_report"] is True
    assert response["condition"] in CONDITION_INFO


def test_mild_conversation_stays_mild(pipeline):
    response = _chat(["a little tired", "maybe a bit of bloating", "not really sure"], pipeline)
    assert response["severity"] in ("mild", "moderate")
    assert response["severity"] != "severe"
