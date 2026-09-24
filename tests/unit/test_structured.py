import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from app.llm.structured import StructuredOutputError, extract_json, invoke_structured


class Item(BaseModel):
    name: str
    score: int


@pytest.mark.parametrize(
    ("text", "expected_name"),
    [
        ('{"name": "a", "score": 1}', "a"),
        ('Sure! Here it is:\n```json\n{"name": "a", "score": 1}\n```', "a"),
        ('<think>maybe {"name": "wrong"}</think>{"name": "a", "score": 1}', "a"),
        ('prefix {"name": "a", "score": 1} suffix', "a"),
        ('{"name": "a {with braces}", "score": 1}', "a {with braces}"),
    ],
)
def test_extract_json_variants(text, expected_name):
    assert extract_json(text) == {"name": expected_name, "score": 1}


def test_extract_json_no_object():
    with pytest.raises(ValueError):
        extract_json("no json here")


def test_invoke_structured_json_mode():
    llm = FakeListChatModel(responses=['```json\n{"name": "x", "score": 3}\n```'])
    result = invoke_structured(llm, Item, [HumanMessage(content="go")], mode="json")
    assert result == Item(name="x", score=3)


def test_invoke_structured_retries_after_invalid_reply():
    llm = FakeListChatModel(responses=["not json", '{"name": "x"}', '{"name": "x", "score": 5}'])
    result = invoke_structured(llm, Item, [HumanMessage(content="go")], mode="json", retries=2)
    assert result.score == 5


def test_invoke_structured_gives_up():
    llm = FakeListChatModel(responses=["nope", "still nope"])
    with pytest.raises(StructuredOutputError):
        invoke_structured(llm, Item, [HumanMessage(content="go")], mode="json", retries=1)


def test_auto_mode_falls_back_when_native_unsupported():
    # FakeListChatModel has no tool binding, so native mode raises and we fall back to JSON.
    llm = FakeListChatModel(responses=['{"name": "y", "score": 2}'])
    result = invoke_structured(llm, Item, [HumanMessage(content="go")], mode="auto")
    assert result.name == "y"
