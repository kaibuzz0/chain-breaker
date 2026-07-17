"""
wallet_cli.py

Command-line wallet interface.
- Generate/import keys
- Check balances
- Sign transactions
- Send to network
"""

import argparse
import json
import os
from typing import Optional


def cmd_generate(args):
    """Generate new wallet."""
    from chain_breaker.wallet_key import Wallet
    
    wallet = Wallet.generate()
    
    print("=" * 50)
    print("NEW WALLET GENERATED")
    print("=" * 50)
    print(f"Address:    {wallet.address}")
    print(f"Public Key: {wallet.public_key}")
    print(f"Private Key: {wallet.private_key}")
    print("\n⚠️  SAVE YOUR PRIVATE KEY - IT CANNOT BE RECOVERED")
    
    if args.save:
        filename = f"{wallet.address}.json"
        wallet.save(filename)
        print(f"\nSaved to: {filename}")


def cmd_balance(args):
    """Check balance."""
    from chain_breaker.pruned_ledger import PrunedLedger
    
    ledger = PrunedLedger()
    
    # Load from file if exists
    if os.path.exists('ledger_state.json'):
        with open('ledger_state.json', 'r') as f:
            data = json.load(f)
            # Restore state
            for addr, bal in data.get('balances', {}).items():
                ledger.state[addr] = bal
    
    balance = ledger.get_balance(args.address)
    print(f"Balance for {args.address}: {balance}")


def cmd_send(args):
    """Send transaction."""
    from chain_breaker.wallet_key import Wallet
    from chain_breaker.e8_signatures import E8Signer
    
    # Load wallet
    if not os.path.exists(args.from_wallet):
        print(f"Wallet file not found: {args.from_wallet}")
        return
    
    wallet = Wallet.load(args.from_wallet)
    
    # Create transaction
    tx = {
        'from': wallet.address,
        'to': args.to,
        'amount': args.amount,
        'timestamp': time.time(),
    }
    
    # Sign with E8
    signer = E8Signer(private_seed=wallet.private_key.encode())
    sig = signer.sign(json.dumps(tx, sort_keys=True).encode())
    
    tx['signature'] = sig.to_bytes().hex()
    
    print("=" * 50)
    print("TRANSACTION SIGNED")
    print("=" * 50)
    print(f"From:   {tx['from']}")
    print(f"To:     {tx['to']}")
    print(f"Amount: {tx['amount']}")
    print(f"Sig:    {tx['signature'][:20]}...")
    
    if args.broadcast:
        print("\nBroadcasting to network...")
        # Would connect to micro_node here
        print("(Broadcast not implemented in demo)")
    else:
        print("\nTransaction ready to broadcast:")
        print(json.dumps(tx, indent=2))


def cmd_info(args):
    """Show wallet info."""
    if not os.path.exists(args.wallet_file):
        print(f"Wallet not found: {args.wallet_file}")
        return
    
    wallet = Wallet.load(args.wallet_file)
    
    print("=" * 50)
    print("WALLET INFO")
    print("=" * 50)
    print(f"Address:     {wallet.address}")
    print(f"Public Key:  {wallet.public_key}")
    print(f"Private Key: {'*' * 20} (hidden)")


def main():
    parser = argparse.ArgumentParser(
        description='Chain-Breaker Wallet CLI',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Command')
    
    # Generate
    gen_parser = subparsers.add_parser('generate', help='Generate new wallet')
    gen_parser.add_argument('--save', action='store_true', help='Save to file')
    
    # Balance
    bal_parser = subparsers.add_parser('balance', help='Check balance')
    bal_parser.add_argument('address', help='Wallet address')
    
    # Send
    send_parser = subparsers.add_parser('send', help='Send transaction')
    send_parser.add_argument('from_wallet', help='Wallet file')
    send_parser.add_argument('to', help='Recipient address')
    send_parser.add_argument('amount', type=int, help='Amount')
    send_parser.add_argument('--broadcast', action='store_true', help='Broadcast to network')
    
    # Info
    info_parser = subparsers.add_parser('info', help='Show wallet info')
    info_parser.add_argument('wallet_file', help='Wallet file')
    
    args = parser.parse_args()
    
    if args.command == 'generate':
        cmd_generate(args)
    elif args.command == 'balance':
        cmd_balance(args)
    elif args.command == 'send':
        cmd_send(args)
    elif args.command == 'info':
        cmd_info(args)
    else:
        parser.print_help()


if __name__ == '__main__':
    import time
    from chain_breaker.wallet_key import Wallet
    main()
