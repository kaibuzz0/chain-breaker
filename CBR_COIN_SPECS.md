# CHAIN-BREAKER (CBR) - Complete Cryptocurrency

## Coin Name: **CBR** (Chain-Breaker)

### Tokenomics

**Symbol:** CBR  
**Type:** Deflationary Proof-of-Stake  
**Supply:** Dynamic (deflationary over time)  
**Consensus:** Stake-based (not mined)

---

## Staking System

### How to Stake

```python
from chain_breaker.efficient_consensus import EfficientConsensus

# Create consensus
consensus = EfficientConsensus(
    min_stake=1000,      # Minimum 1000 CBR to be validator
    block_time=12,       # 12 second blocks
)

# Stake CBR to become validator
consensus.register_validator(
    address="your_address",
    stake_amount=5000    # Stake 5000 CBR
)
```

### Validator Requirements

| Requirement | Amount |
|------------|--------|
| **Minimum Stake** | 1,000 CBR |
| **Recommended Stake** | 10,000+ CBR |
| **Block Time** | 12 seconds |
| **Block Reward** | 0 CBR (deflationary - no new minting) |
| **Income Source** | Transaction fees (burned + redistributed) |

### Staking Rewards

**No inflation** - CBR is deflationary:
- No block rewards (no new CBR created)
- Validators earn from **transaction fees**
- Fees are burned (deflationary pressure)

**Effective yield comes from:**
1. Transaction fee share
2. Deflation (remaining CBR worth more)
3. MEV protection (fair ordering)

### Validator Responsibilities

1. **Stay online** - Produce blocks when selected
2. **Validate transactions** - Check validity
3. **Maintain network** - Run full node
4. **Slash risk** - Lose stake if malicious

### Slashing Conditions

| Offense | Penalty |
|---------|---------|
| Double signing | 10% of stake |
| Long downtime | Jail (temporary exclusion) |
| Invalid blocks | 10% of stake |

---

## Coin Properties

### Deflationary Mechanics

```
Total Supply Formula:
- Genesis: 1,000,000 CBR
- Ongoing: Burn > Mint
- Result: Supply decreases over time
```

**Burn Sources:**
1. Transaction fees (100% burned)
2. Dormant coin penalties (1% per year)
3. Reclamation penalties (10% to reclaim)
4. Contract execution gas

**Mint Sources:**
1. Genesis distribution (1M CBR)
2. Block rewards (minimal, decaying)
3. Recycled lost coins (after 20 years)

### Distribution

| Allocation | Amount | Percentage |
|------------|--------|------------|
| **Genesis** | 1,000,000 CBR | 100% (initial) |
| **Miners/Validators** | From fees | N/A (no inflation) |
| **Development** | From reclamation | ~1% over time |

---

## Transaction Fees

### Fee Structure

```python
from chain_breaker.deflationary_mint import DeflationaryMint

mint = DeflationaryMint(
    base_burn_rate=0.01,  # 1% burn per transaction
    min_burn_amount=1,     # Minimum 1 CBR burn
)

# Send 1000 CBR
result = mint.process_transaction(
    from_address="alice",
    to_address="bob",
    amount=1000
)

# Result:
# - Burned: 10 CBR (1%)
# - Transferred: 990 CBR
# - Net deflation: 10 CBR
```

### Fee Distribution

- **100% burned** - No validator reward from fees
- Validators earn from **MEV protection** and **state rent**
- Economic alignment: validators want CBR to appreciate (deflation)

---

## Staking vs Mining

| Aspect | Bitcoin (Mining) | CBR (Staking) |
|--------|------------------|---------------|
| **Hardware** | ASICs ($$$) | Any computer |
| **Energy** | 150 TWh/year | ~0 |
| **Entry cost** | $10,000+ | 1,000 CBR |
| **Rewards** | New BTC + fees | Fees only |
| **Inflation** | Yes (infinite) | No (deflation) |
| **Centralization** | Pools | Distributed |
| **Security** | Energy cost | Economic stake |

---

## Wallet Support

### CLI Wallet

```bash
# Generate wallet
python wallet_cli.py generate --save

# Check balance
python wallet_cli.py balance YOUR_ADDRESS

# Send CBR
python wallet_cli.py send your_wallet.json RECEIVER_ADDRESS AMOUNT

# Stake (become validator)
python wallet_cli.py stake your_wallet.json AMOUNT
```

### Integration

CBR uses standard cryptography:
- E8 lattice signatures (quantum-safe)
- Binary encoding (efficient)
- Compatible with existing wallet frameworks

---

## Economic Model

### Why Deflationary?

**Bitcoin's problem:** Infinite inflation via fees  
**CBR's solution:** Deflation via burns

**Benefits:**
- CBR becomes more scarce over time
- Early holders rewarded
- No "fee sniping" attacks
- Sustainable long-term

### Price Dynamics

```
Scarcity Increases:
- Users burn CBR for transactions
- Lost coins eventually recycled
- Supply shrinks
- Remaining CBR more valuable

Natural Demand:
- Required for fees
- Required for staking
- Required for storage rent
- Required for contracts
```

---

## Summary

**CBR is:**
- ✅ **Stakable** - 1,000 minimum to validate
- ✅ **Deflationary** - Supply decreases over time
- ✅ **Energy-free** - No mining
- ✅ **Quantum-safe** - E8 signatures
- ✅ **Fair** - MEV protection
- ✅ **Sustainable** - State rent

**Ticker:** CBR  
**Type:** Utility + Governance + Store of Value  
**Consensus:** Proof-of-Stake (stake-weighted)  
**Max Supply:** Decreasing (deflationary)

---

*CBR: The coin for the corrected blockchain.*
