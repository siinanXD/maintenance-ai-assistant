"""The success envelope: a dict result is the body, ``success`` stays true."""

from app.responses import success_payload


def test_success_payload_spreads_the_body_and_keeps_success_true():
    """A body key named ``success`` must not flip the envelope."""
    payload = success_payload({"id": 7, "success": False})

    assert payload["success"] is True
    assert payload["id"] == 7
    assert payload["data"] == {"id": 7, "success": False}
    assert payload["message"] == "OK"


def test_success_payload_keeps_a_nested_data_key_as_the_data_field():
    """Agent results carry their own ``data``; the response keeps that shape."""
    payload = success_payload({"type": "agent_action", "data": {"task": {"id": 3}}})

    assert payload["type"] == "agent_action"
    assert payload["data"] == {"task": {"id": 3}}


def test_success_payload_message_comes_from_argument_then_body_then_default():
    """An explicit message wins, otherwise the body's own message, otherwise OK."""
    assert success_payload({"message": "gespeichert"})["message"] == "gespeichert"
    assert success_payload({"message": "x"}, message="explizit")["message"] == "explizit"
    assert success_payload({"message": ""})["message"] == "OK"
    assert success_payload([1, 2])["message"] == "OK"
    assert success_payload(None)["data"] is None
