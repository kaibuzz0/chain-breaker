# Smart Contracts: Minimal vs Complex

## Our Philosophy: Minimal Contracts

Chain-Breaker uses **minimal contracts** — enough power for real use cases, safe enough to prevent disasters.

### Why NOT Turing-Complete?

**Ethereum's approach:**
- 140+ opcodes
- Turing-complete (can compute anything)
- Result: $2.2 billion in hacks, reentrancy attacks, bridge exploits

**Our approach:**
- 18 opcodes
- Deterministic (same input = same output, always)
- No reentrancy, no infinite loops, no surprises

### What Minimal Contracts CAN Do

| Use Case | How |
|----------|-----|
| **Escrow** | Hold funds until conditions met |
| **Multi-sig** | Require N signatures to spend |
| **Time locks** | Release funds at specific time/block |
| **Token creation** | New assets with simple rules |
| **Conditional payments** | If X then pay Y |
| **Subscriptions** | Auto-pay monthly (time-triggered) |
| **Auctions** | Highest bidder wins (simple comparison) |

### What Minimal Contracts CANNOT Do

| Use Case | Why We Avoid |
|----------|--------------|
| Flash loans | Too complex, flash crashes |
| Recursive lending | Risk of infinite loops |
| Complex DeFi | Composability = fragility |
| AI integration | Nondeterministic |
| Self-modifying code | Unpredictable behavior |

### Safety Features

1. **Gas Metering**
   - Every operation costs gas
   - Prevents infinite loops
   - Pays for network resources used

2. **Deterministic Execution**
   - Same input = same output, always
   - No randomness in contracts
   - Reproducible results

3. **State Isolation**
   - Contract can't corrupt others
   - Storage limits per contract
   - Failed contract doesn't crash chain

4. **No External Calls**
   - Can't call other contracts recursively
   - Prevents reentrancy attacks
   - Simple state machine

### Opcode Reference

```
Stack:
  PUSH - Push value
  POP - Remove value  
  DUP - Copy top
  SWAP - Swap top two

Logic:
  EQ - Equal
  GT - Greater than
  LT - Less than
  AND - Boolean AND
  OR - Boolean OR
  NOT - Boolean NOT

Control:
  JMP - Jump
  JZ - Jump if zero
  JNZ - Jump if not zero

State:
  LOAD - Read storage
  STORE - Write storage
  BALANCE - Contract balance
  SENDER - Call sender
  BLOCKTIME - Current time
  BLOCKNUM - Current height

Actions:
  TRANSFER - Send funds
  REQUIRE - Assert condition
  RETURN - End with value
```

### Example: Simple Escrow

```python
# Hold 1000 coins until authorized address claims
# Requires: sender == authorized AND block_time < timeout

bytecode = [
    SENDER,         # Who is calling?
    PUSH, 0,        # Expected sender (set at deploy)
    EQ,             # Are they equal?
    REQUIRE,        # Revert if not
    
    BLOCKTIME,      # What time is it?
    PUSH, timeout,  # Deadline
    LT,             # Before deadline?
    REQUIRE,        # Revert if expired
    
    BALANCE,        # How much stored?
    PUSH, 1000,     # Required amount
    GT,             # Enough?
    REQUIRE,        # Revert if insufficient
    
    PUSH, 1,        # Success
    RETURN,
]
```

### Gas Costs

| Operation | Cost |
|-----------|------|
| Stack ops | 1 gas |
| Logic | 2 gas |
| Storage | 10 gas |
| Actions | 5 gas |

**Default limit:** 10,000 gas (prevents runaway execution)

### Comparison

| Feature | Ethereum | Chain-Breaker |
|---------|----------|---------------|
| Opcodes | 140+ | 18 |
| Turing-complete | Yes | No |
| Gas per operation | Variable | Fixed |
| Reentrancy possible | Yes | No |
| Infinite loops | Possible | Impossible |
| Major hacks | $2.2B+ | None (by design) |
| Learning curve | Steep | Gentle |
| Audit required | Yes | Optional for simple |

### When to Use Contracts

**Use contracts for:**
- Escrow (hold funds safely)
- Multi-sig (shared control)
- Time delays (cooldown periods)
- Simple tokens (new assets)
- Conditional logic (if/then)

**Don't use for:**
- Complex financial instruments
- Recursive algorithms
- External API calls
- Random number generation
- Machine learning

### Bottom Line

**Minimal contracts = Real utility + Real safety**

We didn't sacrifice functionality. We eliminated footguns.

- Can build useful things: ✅
- Can't shoot yourself: ✅
- Predictable costs: ✅
- Auditable code: ✅

This is how contracts should have been from day one.
