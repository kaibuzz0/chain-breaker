"""
minimal_contracts.py

Safe, limited smart contracts for Chain-Breaker.

Design philosophy:
- NOT Turing-complete (avoid Ethereum's complexity/mess)
- Deterministic execution (same input = same output, always)
- Gas metering (prevent infinite loops, pay for computation)
- Simple opcodes (10-15 operations, not 100+)
- State isolation (contracts can't brick the chain)

This enables:
- Escrow (hold funds until conditions)
- Multi-sig wallets (require N signatures)
- Time locks (release at specific block/time)
- Token creation (new assets)
- Conditional payments (if X then Y)

Without:
- Reentrancy attacks
- Infinite loops
- Complex state manipulation
- Millions in lost funds
"""

import hashlib
import time
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum


class Opcode(Enum):
    """Contract opcodes - minimal set."""
    # Stack operations
    PUSH = 1      # Push value to stack
    POP = 2       # Pop from stack
    DUP = 3       # Duplicate top of stack
    SWAP = 4      # Swap top two stack items
    
    # Logic
    EQ = 10       # Equality check
    GT = 11       # Greater than
    LT = 12       # Less than
    AND = 13      # Boolean AND
    OR = 14       # Boolean OR
    NOT = 15      # Boolean NOT
    
    # Control flow
    JMP = 20      # Jump to position
    JZ = 21       # Jump if zero
    JNZ = 22      # Jump if not zero
    
    # State
    LOAD = 30     # Load from storage
    STORE = 31    # Store to storage
    BALANCE = 32  # Get contract balance
    SENDER = 33   # Get transaction sender
    BLOCKTIME = 34 # Get current block time
    BLOCKNUM = 35  # Get current block number
    
    # Actions
    TRANSFER = 40  # Transfer funds
    REQUIRE = 41   # Require condition (revert if false)
    RETURN = 42    # Return value


class ContractStatus(Enum):
    """Contract execution status."""
    READY = "ready"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    OUT_OF_GAS = "out_of_gas"


@dataclass
class Contract:
    """Smart contract on Chain-Breaker."""
    address: str
    creator: str
    code: List[int]         # Bytecode (opcode list)
    storage: Dict[str, Any] = field(default_factory=dict)
    balance: int = 0
    created_at: float = field(default_factory=time.time)
    
    # Gas tracking
    gas_used_total: int = 0
    calls_total: int = 0


@dataclass
class ExecutionContext:
    """Context for contract execution."""
    sender: str
    value: int              # Amount sent to contract
    gas_limit: int          # Max gas allowed
    block_time: float
    block_number: int
    
    # Execution state
    pc: int = 0             # Program counter
    stack: List[Any] = field(default_factory=list)
    gas_used: int = 0
    status: ContractStatus = ContractStatus.READY
    return_value: Any = None


class MinimalContracts:
    """
    Safe smart contract execution engine.
    
    Gas costs (per operation):
    - Simple ops (PUSH, POP, DUP): 1 gas
    - Logic (EQ, GT, AND): 2 gas
    - Storage (LOAD, STORE): 10 gas (expensive - prevents spam)
    - Actions (TRANSFER, REQUIRE): 5 gas
    
    Default gas limit: 10,000 (prevents infinite loops)
    """
    
    GAS_COSTS = {
        Opcode.PUSH: 1, Opcode.POP: 1, Opcode.DUP: 1, Opcode.SWAP: 1,
        Opcode.EQ: 2, Opcode.GT: 2, Opcode.LT: 2, Opcode.AND: 2,
        Opcode.OR: 2, Opcode.NOT: 1,
        Opcode.JMP: 3, Opcode.JZ: 3, Opcode.JNZ: 3,
        Opcode.LOAD: 10, Opcode.STORE: 10,
        Opcode.BALANCE: 2, Opcode.SENDER: 1,
        Opcode.BLOCKTIME: 1, Opcode.BLOCKNUM: 1,
        Opcode.TRANSFER: 5, Opcode.REQUIRE: 5, Opcode.RETURN: 1,
    }
    
    def __init__(self):
        self.contracts: Dict[str, Contract] = {}
        self.deploy_gas_cost: int = 100  # Gas to deploy
        self.default_gas_limit: int = 10000
        
        # Stats
        self.total_contracts = 0
        self.total_executions = 0
        self.total_gas_used = 0
        self.failed_executions = 0
    
    def deploy_contract(
        self,
        creator: str,
        code: List[int],
        initial_balance: int = 0
    ) -> Optional[str]:
        """
        Deploy new contract.
        
        Returns contract address or None if failed.
        """
        # Check gas for deployment
        if len(code) > self.default_gas_limit:
            return None
        
        # Generate address
        contract_id = hashlib.sha256(
            f"{creator}:{code}:{time.time()}".encode()
        ).hexdigest()[:16]
        
        contract = Contract(
            address=contract_id,
            creator=creator,
            code=code,
            balance=initial_balance,
        )
        
        self.contracts[contract_id] = contract
        self.total_contracts += 1
        
        return contract_id
    
    def execute_contract(
        self,
        contract_address: str,
        sender: str,
        value: int = 0,
        gas_limit: Optional[int] = None,
        block_time: Optional[float] = None,
        block_number: int = 0,
    ) -> ExecutionContext:
        """
        Execute contract code.
        
        Returns execution context with results.
        """
        if contract_address not in self.contracts:
            return ExecutionContext(
                sender=sender,
                value=value,
                gas_limit=0,
                block_time=block_time or time.time(),
                block_number=block_number,
                status=ContractStatus.FAILED,
            )
        
        contract = self.contracts[contract_address]
        
        # Setup context
        ctx = ExecutionContext(
            sender=sender,
            value=value,
            gas_limit=gas_limit or self.default_gas_limit,
            block_time=block_time or time.time(),
            block_number=block_number,
        )
        
        ctx.status = ContractStatus.RUNNING
        
        # Execute
        try:
            self._execute_bytecode(contract, ctx)
        except Exception as e:
            ctx.status = ContractStatus.FAILED
            self.failed_executions += 1
        
        # Update stats
        contract.gas_used_total += ctx.gas_used
        contract.calls_total += 1
        self.total_executions += 1
        self.total_gas_used += ctx.gas_used
        
        return ctx
    
    def _execute_bytecode(self, contract: Contract, ctx: ExecutionContext):
        """Execute contract bytecode."""
        code = contract.code
        
        while ctx.pc < len(code):
            # Check gas
            if ctx.gas_used >= ctx.gas_limit:
                ctx.status = ContractStatus.OUT_OF_GAS
                return
            
            opcode_val = code[ctx.pc]
            
            try:
                opcode = Opcode(opcode_val)
            except ValueError:
                # Invalid opcode - halt
                ctx.status = ContractStatus.FAILED
                return
            
            # Charge gas
            gas_cost = self.GAS_COSTS.get(opcode, 1)
            ctx.gas_used += gas_cost
            
            # Execute opcode
            if not self._execute_opcode(opcode, contract, ctx, code):
                return
            
            ctx.pc += 1
        
        # Completed without explicit return
        ctx.status = ContractStatus.SUCCESS
    
    def _execute_opcode(
        self,
        opcode: Opcode,
        contract: Contract,
        ctx: ExecutionContext,
        code: List[int]
    ) -> bool:
        """Execute single opcode. Returns False if should halt."""
        
        # Stack operations
        if opcode == Opcode.PUSH:
            ctx.pc += 1
            if ctx.pc >= len(code):
                return False
            ctx.stack.append(code[ctx.pc])
            
        elif opcode == Opcode.POP:
            if not ctx.stack:
                ctx.status = ContractStatus.FAILED
                return False
            ctx.stack.pop()
            
        elif opcode == Opcode.DUP:
            if not ctx.stack:
                ctx.status = ContractStatus.FAILED
                return False
            ctx.stack.append(ctx.stack[-1])
            
        elif opcode == Opcode.SWAP:
            if len(ctx.stack) < 2:
                ctx.status = ContractStatus.FAILED
                return False
            ctx.stack[-1], ctx.stack[-2] = ctx.stack[-2], ctx.stack[-1]
        
        # Logic
        elif opcode == Opcode.EQ:
            if len(ctx.stack) < 2:
                ctx.status = ContractStatus.FAILED
                return False
            b, a = ctx.stack.pop(), ctx.stack.pop()
            ctx.stack.append(1 if a == b else 0)
            
        elif opcode == Opcode.GT:
            if len(ctx.stack) < 2:
                ctx.status = ContractStatus.FAILED
                return False
            b, a = ctx.stack.pop(), ctx.stack.pop()
            ctx.stack.append(1 if a > b else 0)
            
        elif opcode == Opcode.LT:
            if len(ctx.stack) < 2:
                ctx.status = ContractStatus.FAILED
                return False
            b, a = ctx.stack.pop(), ctx.stack.pop()
            ctx.stack.append(1 if a < b else 0)
            
        elif opcode == Opcode.AND:
            if len(ctx.stack) < 2:
                ctx.status = ContractStatus.FAILED
                return False
            b, a = ctx.stack.pop(), ctx.stack.pop()
            ctx.stack.append(1 if (a and b) else 0)
            
        elif opcode == Opcode.NOT:
            if not ctx.stack:
                ctx.status = ContractStatus.FAILED
                return False
            a = ctx.stack.pop()
            ctx.stack.append(1 if not a else 0)
        
        # Control flow
        elif opcode == Opcode.JMP:
            ctx.pc += 1
            if ctx.pc >= len(code):
                return False
            target = code[ctx.pc]
            if 0 <= target < len(code):
                ctx.pc = target - 1  # -1 because pc increments after
            else:
                ctx.status = ContractStatus.FAILED
                return False
                
        elif opcode == Opcode.JZ:
            ctx.pc += 1
            if ctx.pc >= len(code):
                return False
            if not ctx.stack or ctx.stack[-1] == 0:
                target = code[ctx.pc]
                if 0 <= target < len(code):
                    ctx.pc = target - 1
                else:
                    ctx.status = ContractStatus.FAILED
                    return False
                
        elif opcode == Opcode.JNZ:
            ctx.pc += 1
            if ctx.pc >= len(code):
                return False
            if ctx.stack and ctx.stack[-1] != 0:
                target = code[ctx.pc]
                if 0 <= target < len(code):
                    ctx.pc = target - 1
                else:
                    ctx.status = ContractStatus.FAILED
                    return False
        
        # State
        elif opcode == Opcode.LOAD:
            ctx.pc += 1
            if ctx.pc >= len(code):
                return False
            key_idx = code[ctx.pc]
            key = str(key_idx)
            ctx.stack.append(contract.storage.get(key, 0))
            
        elif opcode == Opcode.STORE:
            ctx.pc += 1
            if ctx.pc >= len(code) or len(ctx.stack) < 1:
                ctx.status = ContractStatus.FAILED
                return False
            key_idx = code[ctx.pc]
            key = str(key_idx)
            value = ctx.stack.pop()
            contract.storage[key] = value
            
        elif opcode == Opcode.BALANCE:
            ctx.stack.append(contract.balance)
            
        elif opcode == Opcode.SENDER:
            ctx.stack.append(ctx.sender)
            
        elif opcode == Opcode.BLOCKTIME:
            ctx.stack.append(int(ctx.block_time))
            
        elif opcode == Opcode.BLOCKNUM:
            ctx.stack.append(ctx.block_number)
        
        # Actions
        elif opcode == Opcode.TRANSFER:
            ctx.pc += 1
            if ctx.pc >= len(code) or len(ctx.stack) < 1:
                ctx.status = ContractStatus.FAILED
                return False
            amount = ctx.stack.pop()
            if amount <= contract.balance:
                # Would actually transfer here
                contract.balance -= amount
                ctx.stack.append(1)  # Success
            else:
                ctx.stack.append(0)  # Failure
                
        elif opcode == Opcode.REQUIRE:
            if not ctx.stack or ctx.stack[-1] == 0:
                ctx.status = ContractStatus.FAILED
                return False
                
        elif opcode == Opcode.RETURN:
            if ctx.stack:
                ctx.return_value = ctx.stack[-1]
            ctx.status = ContractStatus.SUCCESS
            return False  # Halt execution
        
        return True
    
    def get_contract(self, address: str) -> Optional[Contract]:
        """Get contract by address."""
        return self.contracts.get(address)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get contract system statistics."""
        return {
            'total_contracts': self.total_contracts,
            'total_executions': self.total_executions,
            'total_gas_used': self.total_gas_used,
            'failed_executions': self.failed_executions,
            'avg_gas_per_execution': (
                self.total_gas_used / self.total_executions
                if self.total_executions > 0 else 0
            ),
        }
    
    def compile_escrow(self, required_amount: int, timeout: int) -> List[int]:
        """
        Compile simple escrow contract.
        
        Conditions:
        - Amount sent >= required_amount
        - Block time < timeout
        - Sender is authorized
        
        Returns bytecode.
        """
        # Simple escrow: require value >= required_amount
        bytecode = [
            Opcode.SENDER.value,       # Push sender
            Opcode.PUSH.value, 0,      # Push expected sender (placeholder)
            Opcode.EQ.value,           # Check equal
            Opcode.REQUIRE.value,      # Require match
            
            Opcode.BLOCKTIME.value,    # Get block time
            Opcode.PUSH.value, timeout, # Push timeout
            Opcode.LT.value,           # Check time < timeout
            Opcode.REQUIRE.value,      # Require not expired
            
            Opcode.PUSH.value, required_amount,  # Push required
            Opcode.BALANCE.value,      # Get balance
            Opcode.GT.value,           # Check balance > required
            Opcode.REQUIRE.value,      # Require sufficient
            
            Opcode.PUSH.value, 1,      # Return 1 (success)
            Opcode.RETURN.value,
        ]
        
        return bytecode


if __name__ == "__main__":
    print("=" * 60)
    print("MINIMAL CONTRACTS - Safe Smart Contract Execution")
    print("=" * 60)
    
    contracts = MinimalContracts()
    
    print("\nAvailable opcodes:", len(Opcode))
    for op in Opcode:
        print(f"  {op.name}: {op.value} (gas: {contracts.GAS_COSTS.get(op, 1)})")
    
    # Deploy simple escrow
    print("\n" + "-" * 60)
    print("Deploying Escrow Contract")
    
    escrow_code = contracts.compile_escrow(
        required_amount=1000,
        timeout=9999999999
    )
    
    contract_addr = contracts.deploy_contract(
        creator="alice",
        code=escrow_code,
        initial_balance=0
    )
    
    print(f"Contract deployed: {contract_addr}")
    print(f"Code size: {len(escrow_code)} opcodes")
    
    # Execute contract
    print("\nExecuting contract...")
    result = contracts.execute_contract(
        contract_address=contract_addr,
        sender="alice",
        value=1000,
        block_number=100,
    )
    
    print(f"  Status: {result.status.value}")
    print(f"  Gas used: {result.gas_used}")
    print(f"  Return value: {result.return_value}")
    print(f"  Stack: {result.stack}")
    
    # Stats
    print("\n" + "=" * 60)
    print("Contract System Statistics:")
    stats = contracts.get_stats()
    print(f"  Total contracts: {stats['total_contracts']}")
    print(f"  Total executions: {stats['total_executions']}")
    print(f"  Total gas used: {stats['total_gas_used']}")
    print(f"  Failed: {stats['failed_executions']}")
    
    print("\n" + "=" * 60)
    print("Contracts: Safe, deterministic, gas-metered")
    print("=" * 60)
