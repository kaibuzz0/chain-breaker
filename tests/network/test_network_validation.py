"""Tests for typed network message payload validation."""

from __future__ import annotations

import pytest

from chainbreaker.network import (
    MAX_BLOCKS_RESPONSE,
    MAX_HEADERS_RESPONSE,
    MAX_INVENTORY_ENTRIES,
    MAX_LOCATOR_SIZE,
    NetworkValidationError,
)
from chainbreaker.network.messages import (
    BlockMessage,
    GetArchiveMessage,
    GetBlockMessage,
    GetDataMessage,
    GetHeadersMessage,
    HeadersMessage,
    HelloAckMessage,
    HelloMessage,
    InventoryMessage,
    PingMessage,
)


def test_hello_requires_fields() -> None:
    with pytest.raises(NetworkValidationError):
        HelloMessage.from_payload(b"{}")


def test_hello_rejects_bad_genesis_hash() -> None:
    import json
    payload = json.dumps({
        "protocol_version": 1,
        "network_id": "chainbreaker-scripture-v2",
        "genesis_hash": "short",
        "best_height": 0,
        "best_chain_work": "0" * 64,
    }).encode("utf-8")
    with pytest.raises(NetworkValidationError):
        HelloMessage.from_payload(payload)


def test_hello_rejects_negative_height() -> None:
    import json
    payload = json.dumps({
        "protocol_version": 1,
        "network_id": "chainbreaker-scripture-v2",
        "genesis_hash": "0" * 64,
        "best_height": -1,
        "best_chain_work": "0" * 64,
    }).encode("utf-8")
    with pytest.raises(NetworkValidationError):
        HelloMessage.from_payload(payload)


def test_hello_round_trip() -> None:
    msg = HelloMessage(
        protocol_version=1,
        network_id="chainbreaker-scripture-v2",
        genesis_hash="0" * 64,
        best_height=100,
        best_chain_work="0" * 64,
        feature_bits=["foo"],
        node_limits={"max_payload_bytes": 1000},
    )
    decoded = HelloMessage.from_payload(msg.to_payload())
    assert decoded.best_height == 100
    assert decoded.feature_bits == ["foo"]


def test_hello_ack_requires_fields() -> None:
    with pytest.raises(NetworkValidationError):
        HelloAckMessage.from_payload(b"{}")


def test_ping_requires_nonce() -> None:
    with pytest.raises(NetworkValidationError):
        PingMessage.from_payload(b"{}")


def test_ping_rejects_negative_nonce() -> None:
    with pytest.raises(NetworkValidationError):
        PingMessage.from_payload(b'{"nonce":-1}')


def test_get_headers_enforces_locator_limit() -> None:
    hashes = ["0" * 64] * (MAX_LOCATOR_SIZE + 1)
    payload = f'{{"start_hashes":{hashes},"stop_hash":null,"max_count":1}}'.replace("'", "\"")
    with pytest.raises(NetworkValidationError):
        GetHeadersMessage.from_payload(payload.encode("utf-8"))


def test_get_headers_enforces_max_count() -> None:
    import json
    payload = json.dumps({
        "start_hashes": ["0" * 64],
        "stop_hash": None,
        "max_count": MAX_HEADERS_RESPONSE + 1,
    }).encode("utf-8")
    with pytest.raises(NetworkValidationError):
        GetHeadersMessage.from_payload(payload)


def test_headers_enforces_count_limit() -> None:
    headers = [{"height": i, "hash": "0" * 64, "header_bytes": "00"} for i in range(MAX_HEADERS_RESPONSE + 1)]
    import json
    payload = json.dumps({"headers": headers}).encode("utf-8")
    with pytest.raises(NetworkValidationError):
        HeadersMessage.from_payload(payload)


def test_get_block_enforces_count_limit() -> None:
    hashes = ["0" * 64] * (MAX_BLOCKS_RESPONSE + 1)
    import json
    payload = json.dumps({"hashes": hashes, "max_total_bytes": 1}).encode("utf-8")
    with pytest.raises(NetworkValidationError):
        GetBlockMessage.from_payload(payload)


def test_block_enforces_count_limit() -> None:
    blocks = [{"hash": "0" * 64, "block_bytes": "00"} for _ in range(MAX_BLOCKS_RESPONSE + 1)]
    import json
    payload = json.dumps({"blocks": blocks}).encode("utf-8")
    with pytest.raises(NetworkValidationError):
        BlockMessage.from_payload(payload)


def test_inventory_enforces_count_limit() -> None:
    hashes = ["0" * 64] * (MAX_INVENTORY_ENTRIES + 1)
    import json
    payload = json.dumps({"type": "blocks", "hashes": hashes}).encode("utf-8")
    with pytest.raises(NetworkValidationError):
        InventoryMessage.from_payload(payload)


def test_inventory_rejects_invalid_type() -> None:
    with pytest.raises(NetworkValidationError):
        InventoryMessage.from_payload(b'{"type":"bad","hashes":[]}')


def test_get_archive_requires_hash() -> None:
    with pytest.raises(NetworkValidationError):
        GetArchiveMessage.from_payload(b"{}")


def test_get_data_rejects_invalid_type() -> None:
    with pytest.raises(NetworkValidationError):
        GetDataMessage.from_payload(b'{"type":"bad","hashes":[]}')
