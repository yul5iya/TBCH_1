import unittest
from core import Wallet, Transaction, Mempool, Block, Blockchain, compute_merkle_root

class TestBlockchain(unittest.TestCase):

    def setUp(self):
        self.blockchain = Blockchain(initial_difficulty=2)
        self.wallet1 = Wallet()
        self.wallet2 = Wallet()
        self.blockchain.public_keys[self.wallet1.address] = self.wallet1.public_key_hex
        self.blockchain.public_keys[self.wallet2.address] = self.wallet2.public_key_hex

    def test_01_wallet_creation(self):
        self.assertIsNotNone(self.wallet1.address)
        self.assertEqual(len(self.wallet1.address), 64)

    def test_02_transaction_signature(self):
        tx = Transaction(self.wallet1.address, self.wallet2.address, 10.0, 1.0, 0)
        tx.sign(self.wallet1.private_key)
        self.assertTrue(tx.verify_signature(self.wallet1.public_key_hex))

    def test_03_merkle_root_even_and_odd(self):
        tx1 = Transaction("A", "B", 10, 1, 0)
        tx2 = Transaction("B", "C", 5, 1, 0)
        root_even = compute_merkle_root([tx1, tx2])
        self.assertIsNotNone(root_even)

        tx3 = Transaction("C", "A", 2, 1, 0)
        root_odd = compute_merkle_root([tx1, tx2, tx3])
        self.assertIsNotNone(root_odd)

    def test_04_mempool_valid_addition(self):
        self.blockchain.mine_block(self.wallet1.address)
        tx = Transaction(self.wallet1.address, self.wallet2.address, 10.0, 1.0, 0)
        tx.sign(self.wallet1.private_key)
        success, msg = self.blockchain.mempool.add_transaction(
            tx, self.wallet1.public_key_hex, self.blockchain.get_balance, self.blockchain.get_nonce, set()
        )
        self.assertTrue(success)

    def test_05_mempool_insufficient_balance(self):
        tx = Transaction(self.wallet2.address, self.wallet1.address, 1000.0, 1.0, 0)
        tx.sign(self.wallet2.private_key)
        success, msg = self.blockchain.mempool.add_transaction(
            tx, self.wallet2.public_key_hex, self.blockchain.get_balance, self.blockchain.get_nonce, set()
        )
        self.assertFalse(success)

    def test_06_mempool_invalid_nonce(self):
        self.blockchain.mine_block(self.wallet1.address)
        tx = Transaction(self.wallet1.address, self.wallet2.address, 5.0, 1.0, 10)
        tx.sign(self.wallet1.private_key)
        success, msg = self.blockchain.mempool.add_transaction(
            tx, self.wallet1.public_key_hex, self.blockchain.get_balance, self.blockchain.get_nonce, set()
        )
        self.assertFalse(success)

    def test_07_valid_chain(self):
        self.blockchain.mine_block(self.wallet1.address)
        valid, _ = self.blockchain.is_chain_valid()
        self.assertTrue(valid)

    def test_08_attack_tamper_old_transaction(self):
        self.blockchain.mine_block(self.wallet1.address)
        tx = Transaction(self.wallet1.address, self.wallet2.address, 10.0, 1.0, 0)
        tx.sign(self.wallet1.private_key)
        self.blockchain.mempool.add_transaction(
            tx, self.wallet1.public_key_hex, self.blockchain.get_balance, self.blockchain.get_nonce, set()
        )
        self.blockchain.mine_block(self.wallet2.address)
        
        self.blockchain.chain[2].transactions[1].amount = 1000.0
        valid, msg = self.blockchain.is_chain_valid()
        self.assertFalse(valid)

    def test_09_attack_recalculate_hash(self):
        self.blockchain.mine_block(self.wallet1.address)
        self.blockchain.mine_block(self.wallet2.address)
        
        self.blockchain.chain[1].transactions[0].amount = 999.0
        self.blockchain.chain[1].merkle_root = compute_merkle_root(self.blockchain.chain[1].transactions)
        self.blockchain.chain[1].hash = self.blockchain.chain[1].calculate_hash()
        
        valid, msg = self.blockchain.is_chain_valid()
        self.assertFalse(valid)

    def test_10_attack_fake_signature(self):
        tx = Transaction(self.wallet1.address, self.wallet2.address, 10.0, 1.0, 0)
        tx.sign(self.wallet2.private_key)
        success, msg = self.blockchain.mempool.add_transaction(
            tx, self.wallet1.public_key_hex, self.blockchain.get_balance, self.blockchain.get_nonce, set()
        )
        self.assertFalse(success)

    def test_11_attack_double_spending(self):
        self.blockchain.mine_block(self.wallet1.address)
        tx1 = Transaction(self.wallet1.address, self.wallet2.address, 40.0, 1.0, 0)
        tx1.sign(self.wallet1.private_key)
        self.blockchain.mempool.add_transaction(
            tx1, self.wallet1.public_key_hex, self.blockchain.get_balance, self.blockchain.get_nonce, set()
        )
        
        tx2 = Transaction(self.wallet1.address, self.wallet2.address, 40.0, 1.0, 0)
        tx2.sign(self.wallet1.private_key)
        success, msg = self.blockchain.mempool.add_transaction(
            tx2, self.wallet1.public_key_hex, self.blockchain.get_balance, self.blockchain.get_nonce, set()
        )
        self.assertFalse(success)

    def test_12_attack_replay(self):
        self.blockchain.mine_block(self.wallet1.address)
        tx = Transaction(self.wallet1.address, self.wallet2.address, 10.0, 1.0, 0)
        tx.sign(self.wallet1.private_key)
        self.blockchain.mempool.add_transaction(
            tx, self.wallet1.public_key_hex, self.blockchain.get_balance, self.blockchain.get_nonce, set()
        )
        self.blockchain.mine_block(self.wallet2.address)
        
        confirmed_hashes = self.blockchain.get_confirmed_tx_hashes()
        success, msg = self.blockchain.mempool.add_transaction(
            tx, self.wallet1.public_key_hex, self.blockchain.get_balance, self.blockchain.get_nonce, confirmed_hashes
        )
        self.assertFalse(success)

if __name__ == '__main__':
    unittest.main()