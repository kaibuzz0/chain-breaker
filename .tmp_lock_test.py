
import sys
from pathlib import Path
sys.path.insert(0, r'E:\Hermes-USB-Portable-main\src\chain-breaker-checkout')
from chainbreaker.storage import FlatFileStorageBackend

root = Path(r'E:\Hermes-USB-Portable-main\src\chain-breaker-checkout\.test_lock')
import shutil
if root.exists():
    shutil.rmtree(root)
root.mkdir()

b1 = FlatFileStorageBackend(chain_root=root, network_id='test-net', genesis_hash='0'*64)
print('b1 acquired')
try:
    b2 = FlatFileStorageBackend(chain_root=root, network_id='test-net', genesis_hash='0'*64)
    print('b2 acquired - unexpected')
except Exception as e:
    print('b2 failed as expected:', type(e).__name__, e)
b1.close()
print('b1 closed')
b3 = FlatFileStorageBackend(chain_root=root, network_id='test-net', genesis_hash='0'*64)
print('b3 acquired after close')
b3.close()
print('done')
