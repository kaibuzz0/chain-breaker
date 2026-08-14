"""Regression tests for Phase 8M-C: Genesis & Network Initialization.



This phase enforces a clear separation between the frozen Protocol V2

alpha/dev/test identity and any production network identity derived from an

independent key ceremony.

"""



from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from chainbreaker.block import (
    GENESIS_GOVERNANCE_KEYS,
    GENESIS_HASH,
    GENESIS_REGISTRY_ROOT,
    NETWORK_ID,
    BlockHeaderV2,
    create_genesis_block,
    mine_header_v2,
)
from chainbreaker.chain import Ledger
from chainbreaker.cli import cli
from chainbreaker.crypto import encode_public_key, generate_keypair
from chainbreaker.network_identity import (
    NetworkIdentityError,
    alpha_network_identity,
    derive_network_identity,
    derive_test_network_identity,
    identity_matches_genesis,
)


def _gov_keys(n: int = 3):

    keys = []

    for _ in range(n):

        sk, pk = generate_keypair()

        keys.append(encode_public_key(pk))

    return keys





def _write_key(path, hex_key: str) -> None:

    path.write_text(hex_key + "\n", encoding="utf-8")





class TestAlphaIdentity:

    """The frozen alpha/dev/test identity must remain byte-for-byte stable."""



    def test_alpha_identity_matches_canonical_genesis(self):

        identity = alpha_network_identity()

        genesis = create_genesis_block()

        assert identity_matches_genesis(identity, genesis)

        assert identity.genesis_hash == GENESIS_HASH

        assert identity.genesis_registry_root == GENESIS_REGISTRY_ROOT

        assert identity.network_id == NETWORK_ID



    def test_alpha_ledger_roundtrip(self):

        led = Ledger()

        data = led.to_dict()

        reloaded = Ledger.from_dict(data)

        assert reloaded.genesis_hash() == led.genesis_hash()

        assert reloaded.network_id == NETWORK_ID

        assert reloaded.network_identity.kind == "alpha"



    def test_alpha_genesis_cannot_be_remined(self):

        genesis = create_genesis_block()

        assert mine_header_v2(genesis.header, max_iterations=1_000_000, start_nonce=0) is False

        assert genesis.hash == GENESIS_HASH



    def test_alpha_ledger_rejects_different_governance_keys(self):

        led = Ledger()

        data = led.to_dict()

        data["governance_keys"] = _gov_keys(3)

        with pytest.raises(NetworkIdentityError):

            Ledger.from_dict(data)



    def test_alpha_ledger_rejects_different_network_id(self):

        led = Ledger()

        data = led.to_dict()

        data["network_id"] = "wrong"

        with pytest.raises((NetworkIdentityError, ValueError)):

            Ledger.from_dict(data)



    def test_alpha_ledger_rejects_different_genesis_hash(self):

        led = Ledger()

        data = led.to_dict()

        # Corrupt a header field so the recomputed hash no longer matches.

        data["chain"][0]["header"]["nonce"] = 99999

        with pytest.raises(NetworkIdentityError):

            Ledger.from_dict(data)





class TestProductionIdentity:

    """Production identities are distinct networks with real governance keys."""



    def test_production_identity_is_distinct(self):

        keys = _gov_keys(3)

        identity = derive_network_identity("chainbreaker-prod", keys, 2)

        assert identity.network_id == "chainbreaker-prod"

        assert identity.kind == "production"

        assert identity.genesis_hash != GENESIS_HASH

        assert identity.genesis_registry_root != GENESIS_REGISTRY_ROOT



    def test_production_identity_deterministic(self):

        keys = _gov_keys(3)

        a = derive_network_identity("chainbreaker-prod", keys, 2)

        b = derive_network_identity("chainbreaker-prod", keys, 2)

        assert a.genesis_hash == b.genesis_hash

        assert a.genesis_registry_root == b.genesis_registry_root

        assert a.genesis_header_bytes == b.genesis_header_bytes



    def test_production_identity_rejects_placeholder_keys(self):

        with pytest.raises(NetworkIdentityError):

            derive_network_identity(

                "chainbreaker-prod",

                list(GENESIS_GOVERNANCE_KEYS),

                2,

                kind="production",

            )



    def test_production_ledger_validates(self):

        keys = _gov_keys(3)

        identity = derive_network_identity("chainbreaker-prod", keys, 2)

        led = Ledger(network_identity=identity)

        assert led.validate_chain()

        assert led.network_id == "chainbreaker-prod"

        assert led.network_identity.is_production()



    def test_production_ledger_roundtrip(self):

        keys = _gov_keys(3)

        identity = derive_network_identity("chainbreaker-prod", keys, 2)

        led = Ledger(network_identity=identity)

        data = led.to_dict()

        reloaded = Ledger.from_dict(data)

        assert reloaded.genesis_hash() == led.genesis_hash()

        assert reloaded.network_id == led.network_id



    def test_production_ledger_mines_and_validates(self):

        keys = _gov_keys(3)

        identity = derive_network_identity("chainbreaker-prod", keys, 2)

        led = Ledger(network_identity=identity)

        block = led.mine_block_v2([])

        assert led.add_block_v2(block)

        assert led.validate_chain()

        assert led.height() == 1





class TestTestIdentity:

    """Test/dev identities isolate experiments from the alpha chain."""



    def test_test_identity_from_real_keys(self):

        keys = _gov_keys(3)

        identity = derive_test_network_identity(keys, 2)

        assert identity.is_alpha() is False

        assert identity.kind == "test"

        assert identity.network_id != NETWORK_ID



    def test_ledger_auto_derives_test_identity(self):

        keys = _gov_keys(3)

        led = Ledger(governance_keys=keys, governance_threshold=2)

        assert led.network_identity.kind == "test"

        assert led.network_id != NETWORK_ID

        assert led.validate_chain()





class TestCLI:

    """CLI enforces explicit identity choice and rejects production without keys."""



    def test_cli_chain_init_default_is_alpha(self):

        runner = CliRunner()

        with runner.isolated_filesystem():

            result = runner.invoke(cli, ["v2", "chain", "init", "--output", "ledger.json"])

            assert result.exit_code == 0

            data = json.loads(result.output)

            assert data["network_id"] == NETWORK_ID

            assert data["kind"] == "alpha"

            assert data["genesis_hash"] == GENESIS_HASH



    def test_cli_chain_init_dev_explicit(self):

        runner = CliRunner()

        with runner.isolated_filesystem():

            result = runner.invoke(cli, ["v2", "chain", "init", "--output", "ledger.json", "--dev"])

            assert result.exit_code == 0

            data = json.loads(result.output)

            assert data["kind"] == "alpha"



    def test_cli_chain_init_production_requires_keys(self):

        runner = CliRunner()

        with runner.isolated_filesystem():

            result = runner.invoke(

                cli,

                ["v2", "chain", "init", "--output", "ledger.json", "--network-id", "prod-net"],

            )

            assert result.exit_code != 0

            assert "governance" in result.output.lower() or "key" in result.output.lower()



    def test_cli_chain_init_production_succeeds_with_keys(self):

        runner = CliRunner()

        with runner.isolated_filesystem():

            sks = []

            pks = []

            for i in range(3):

                sk, pk = generate_keypair()

                sks.append(sk)

                pks.append(pk)

                _write_key_key = f"gov_{i}.hex"

                _write_key_key_path = _write_key_key

                # Use decode_private_key to get raw hex

                raw = sk.private_bytes_raw().hex()

                from pathlib import Path

                Path(_write_key_key).write_text(raw + "\n", encoding="utf-8")

            result = runner.invoke(

                cli,

                [

                    "v2", "chain", "init",

                    "--output", "ledger.json",

                    "--network-id", "prod-net",

                    "--governance-key", "gov_0.hex",

                    "--governance-key", "gov_1.hex",

                    "--governance-key", "gov_2.hex",

                    "--governance-threshold", "2",

                ],

            )

            assert result.exit_code == 0, result.output

            data = json.loads(result.output)

            assert data["kind"] == "production"

            assert data["network_id"] == "prod-net"

            assert data["genesis_hash"] != GENESIS_HASH



    def test_cli_chain_init_rejects_placeholder_keys(self):

        runner = CliRunner()

        with runner.isolated_filesystem():

            for i, key in enumerate(GENESIS_GOVERNANCE_KEYS):

                from pathlib import Path

                Path(f"gov_{i}.hex").write_text(key + "\n", encoding="utf-8")

            result = runner.invoke(

                cli,

                [

                    "v2", "chain", "init",

                    "--output", "ledger.json",

                    "--network-id", "prod-net",

                    "--governance-key", "gov_0.hex",

                    "--governance-key", "gov_1.hex",

                    "--governance-key", "gov_2.hex",

                ],

            )

            assert result.exit_code != 0





class TestGenesisConstants:

    """Dead-code removal and genesis guard."""



    def test_compute_genesis_constants_removed(self):

        from chainbreaker.block import _compute_genesis_constants

        with pytest.raises(RuntimeError):

            _compute_genesis_constants()



    def test_new_header_with_alpha_bytes_rejected(self):

        """A fresh header whose canonical bytes equal GENESIS_HEADER_BYTES is rejected."""

        from chainbreaker.codec import BinaryCodec

        header_dict, _ = BinaryCodec.decode_header_v2(alpha_network_identity().genesis_header_bytes)

        header = BlockHeaderV2.from_dict(header_dict)

        assert mine_header_v2(header, max_iterations=1_000_000, start_nonce=0) is False
