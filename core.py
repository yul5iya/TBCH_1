import hashlib
import json
import time
from ecdsa import SigningKey, SECP256k1, VerifyingKey, BadSignatureError

class Wallet:
    def __init__(self):
        self.private_key = SigningKey.generate(curve=SECP256k1)
        self.public_key = self.private_key.verifying_key
        self.public_key_hex = self.public_key.to_string().hex()
        self.address = hashlib.sha256(bytes.fromhex(self.public_key_hex)).hexdigest()

class Transaction:
    def __init__(self, sender_address, recipient_address, amount, fee, nonce):
        self.sender = sender_address
        self.recipient = recipient_address
        self.amount = amount
        self.fee = fee
        self.nonce = nonce
        self.signature = None

    def to_dict(self):
        return {
            "sender": self.sender,
            "recipient": self.recipient,
            "amount": self.amount,
            "fee": self.fee,
            "nonce": self.nonce
        }

    def serialize(self) -> bytes:
        return json.dumps(self.to_dict(), sort_keys=True).encode('utf-8')

    def sign(self, private_key: SigningKey):
        self.signature = private_key.sign(self.serialize()).hex()

    def verify_signature(self, public_key_hex: str) -> bool:
        if not self.signature:
            return False
        try:
            pub_key = VerifyingKey.from_string(bytes.fromhex(public_key_hex), curve=SECP256k1)
            return pub_key.verify(bytes.fromhex(self.signature), self.serialize())
        except (BadSignatureError, ValueError):
            return False

class Mempool:
    def __init__(self):
        self.pending_transactions: list[Transaction] = []

    def get_tx_hash(self, tx: Transaction) -> str:
        tx_data = tx.to_dict()
        tx_data['signature'] = tx.signature
        return hashlib.sha256(json.dumps(tx_data, sort_keys=True).encode()).hexdigest()

    def add_transaction(self, tx: Transaction, public_key_hex: str, get_balance_func, get_nonce_func, confirmed_tx_hashes: set) -> tuple[bool, str]:
        if not tx.verify_signature(public_key_hex):
            return False, "Помилка: Недійсний цифровий підпис."

        tx_hash = self.get_tx_hash(tx)
        if tx_hash in confirmed_tx_hashes:
            return False, "Помилка: Транзакція вже існує в блокчейні."
        if any(self.get_tx_hash(t) == tx_hash for t in self.pending_transactions):
            return False, "Помилка: Транзакція вже перебуває в мемпулі."

        mempool_sender_txs = [t for t in self.pending_transactions if t.sender == tx.sender]
        pending_amount_sum = sum(t.amount + t.fee for t in mempool_sender_txs)
        expected_nonce = get_nonce_func(tx.sender) + len(mempool_sender_txs)

        if tx.nonce != expected_nonce:
            return False, f"Помилка: Невірний nonce. Очікувався {expected_nonce}, отримано {tx.nonce}."

        current_balance = get_balance_func(tx.sender)
        total_required = pending_amount_sum + tx.amount + tx.fee
        if current_balance < total_required:
            return False, f"Помилка: Недостатньо коштів. Доступно: {current_balance}, потрібно: {total_required}."

        self.pending_transactions.append(tx)
        return True, "Транзакцію успішно додано до мемпулу."

def compute_merkle_root(transactions: list[Transaction]) -> str:
    if not transactions:
        return hashlib.sha256(b"").hexdigest()

    hashes = [
        hashlib.sha256(tx.serialize() + (tx.signature.encode() if tx.signature else b"")).hexdigest()
        for tx in transactions
    ]

    while len(hashes) > 1:
        if len(hashes) % 2 != 0:
            hashes.append(hashes[-1])

        next_level = []
        for i in range(0, len(hashes), 2):
            combined = hashes[i] + hashes[i+1]
            parent_hash = hashlib.sha256(combined.encode('utf-8')).hexdigest()
            next_level.append(parent_hash)
        hashes = next_level

    return hashes[0]

class Block:
    def __init__(self, index: int, previous_hash: str, transactions: list[Transaction], difficulty: int, nonce: int = 0, timestamp: float = None):
        self.index = index
        self.timestamp = timestamp if timestamp is not None else time.time()
        self.previous_hash = previous_hash
        self.transactions = transactions
        self.merkle_root = compute_merkle_root(transactions)
        self.difficulty = difficulty
        self.nonce = nonce
        self.hash = self.calculate_hash()

    def get_header_dict(self) -> dict:
        return {
            "index": self.index,
            "timestamp": self.timestamp,
            "previous_hash": self.previous_hash,
            "merkle_root": self.merkle_root,
            "difficulty": self.difficulty,
            "nonce": self.nonce
        }

    def calculate_hash(self) -> str:
        header_bytes = json.dumps(self.get_header_dict(), sort_keys=True).encode('utf-8')
        return hashlib.sha256(header_bytes).hexdigest()

class Blockchain:
    def __init__(self, initial_difficulty=4, target_block_time=10, adjust_interval=10):
        self.chain: list[Block] = []
        self.mempool = Mempool()
        self.difficulty = initial_difficulty
        self.target_block_time = target_block_time
        self.adjust_interval = adjust_interval
        self.public_keys = {}
        self.create_genesis_block()

    def create_genesis_block(self):
        genesis_tx = Transaction("0", "0", 0, 0, 0)
        genesis_tx.signature = "0"
        genesis_block = Block(0, "0" * 64, [genesis_tx], self.difficulty)
        self.chain.append(genesis_block)

    def get_last_block(self) -> Block:
        return self.chain[-1]

    def get_balance(self, address: str) -> float:
        balance = 0.0
        for block in self.chain:
            for tx in block.transactions:
                if tx.recipient == address:
                    balance += tx.amount
                if tx.sender == address:
                    balance -= (tx.amount + tx.fee)
        return balance

    def get_nonce(self, address: str) -> int:
        nonce = 0
        for block in self.chain:
            for tx in block.transactions:
                if tx.sender == address:
                    nonce += 1
        return nonce

    def adjust_difficulty(self):
        if len(self.chain) <= self.adjust_interval or (len(self.chain) - 1) % self.adjust_interval != 0:
            return
        latest_interval_blocks = self.chain[-self.adjust_interval:]
        actual_time = latest_interval_blocks[-1].timestamp - latest_interval_blocks[0].timestamp
        expected_time = self.target_block_time * self.adjust_interval

        if actual_time < expected_time / 2:
            self.difficulty += 1
        elif actual_time > expected_time * 2:
            self.difficulty = max(1, self.difficulty - 1)

    def mine_block(self, miner_address: str, miner_reward: float = 50.0) -> Block:
        total_fees = sum(tx.fee for tx in self.mempool.pending_transactions)
        reward_tx = Transaction("COINBASE", miner_address, miner_reward + total_fees, 0, 0)
        reward_tx.signature = "COINBASE_REWARD"

        block_txs = [reward_tx] + list(self.mempool.pending_transactions)
        new_block = Block(
            index=len(self.chain),
            previous_hash=self.get_last_block().hash,
            transactions=block_txs,
            difficulty=self.difficulty
        )

        target_prefix = "0" * self.difficulty
        while not new_block.hash.startswith(target_prefix):
            new_block.nonce += 1
            new_block.hash = new_block.calculate_hash()

        self.chain.append(new_block)
        self.mempool.pending_transactions.clear()
        self.adjust_difficulty()
        return new_block

    def get_confirmed_tx_hashes(self) -> set:
        hashes = set()
        for block in self.chain:
            for tx in block.transactions:
                hashes.add(self.mempool.get_tx_hash(tx))
        return hashes

    def is_chain_valid(self, chain_to_validate: list[Block] = None) -> tuple[bool, str]:
        chain = chain_to_validate if chain_to_validate is not None else self.chain
        if not chain:
            return False, "Помилка: Ланцюг порожній."

        for i in range(1, len(chain)):
            current = chain[i]
            previous = chain[i - 1]

            if current.previous_hash != previous.hash:
                return False, f"Помилка у блоці {current.index}: розрив хешу попереднього блоку."

            if current.calculate_hash() != current.hash:
                return False, f"Помилка у блоці {current.index}: недопустимий хеш блоку."

            if not current.hash.startswith("0" * current.difficulty):
                return False, f"Помилка у блоці {current.index}: складність хешу не відповідає вимогам."

            if current.merkle_root != compute_merkle_root(current.transactions):
                return False, f"Помилка у блоці {current.index}: корінь Меркла некоректний."

        return True, "Ланцюг повністю валідний."