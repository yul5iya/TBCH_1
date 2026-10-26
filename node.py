import sys
import json
import requests
from flask import Flask, jsonify, request
from core import Blockchain, Transaction, Wallet, Block, compute_merkle_root

app = Flask(__name__)
blockchain = Blockchain()
peers = set()

def serialize_block(block: Block) -> dict:
    return {
        "index": block.index,
        "timestamp": block.timestamp,
        "previous_hash": block.previous_hash,
        "transactions": [
            {
                "sender": tx.sender,
                "recipient": tx.recipient,
                "amount": tx.amount,
                "fee": tx.fee,
                "nonce": tx.nonce,
                "signature": tx.signature
            } for tx in block.transactions
        ],
        "merkle_root": block.merkle_root,
        "difficulty": block.difficulty,
        "nonce": block.nonce,
        "hash": block.hash
    }

def deserialize_block(data: dict) -> Block:
    txs = []
    for t in data["transactions"]:
        tx = Transaction(t["sender"], t["recipient"], t["amount"], t["fee"], t["nonce"])
        tx.signature = t["signature"]
        txs.append(tx)
    
    block = Block(
        index=data["index"],
        previous_hash=data["previous_hash"],
        transactions=txs,
        difficulty=data["difficulty"],
        nonce=data["nonce"],
        timestamp=data["timestamp"]
    )
    block.hash = data["hash"]
    return block

@app.route('/wallet/new', methods=['GET'])
def new_wallet():
    wallet = Wallet()
    blockchain.public_keys[wallet.address] = wallet.public_key_hex
    return jsonify({
        "address": wallet.address,
        "public_key": wallet.public_key_hex,
        "private_key": wallet.private_key.to_string().hex()
    }), 200

@app.route('/transaction/send', methods=['POST'])
def send_transaction():
    values = request.get_json()
    required = ['sender', 'recipient', 'amount', 'fee', 'nonce', 'public_key', 'signature']
    if not all(k in values for k in required):
        return jsonify({"message": "Помилка: Відсутні обов'язкові поля."}), 400

    blockchain.public_keys[values['sender']] = values['public_key']

    tx = Transaction(
        values['sender'],
        values['recipient'],
        float(values['amount']),
        float(values['fee']),
        int(values['nonce'])
    )
    tx.signature = values['signature']

    confirmed_hashes = blockchain.get_confirmed_tx_hashes()
    success, msg = blockchain.mempool.add_transaction(
        tx,
        values['public_key'],
        blockchain.get_balance,
        blockchain.get_nonce,
        confirmed_hashes
    )

    if not success:
        return jsonify({"message": msg}), 400

    for peer in peers:
        try:
            requests.post(f"{peer}/transaction/receive", json=values, timeout=2)
        except Exception:
            pass

    return jsonify({"message": msg}), 201

@app.route('/transaction/receive', methods=['POST'])
def receive_transaction():
    values = request.get_json()
    blockchain.public_keys[values['sender']] = values['public_key']
    tx = Transaction(
        values['sender'],
        values['recipient'],
        float(values['amount']),
        float(values['fee']),
        int(values['nonce'])
    )
    tx.signature = values['signature']

    confirmed_hashes = blockchain.get_confirmed_tx_hashes()
    blockchain.mempool.add_transaction(
        tx,
        values['public_key'],
        blockchain.get_balance,
        blockchain.get_nonce,
        confirmed_hashes
    )
    return jsonify({"message": "Транзакцію отримано."}), 200

@app.route('/mine', methods=['GET'])
def mine():
    miner_address = request.args.get('address', 'MINER_1')
    new_block = blockchain.mine_block(miner_address)
    
    block_data = serialize_block(new_block)
    for peer in peers:
        try:
            requests.post(f"{peer}/block/receive", json=block_data, timeout=2)
        except Exception:
            pass

    return jsonify({
        "message": "Новий блок успішно смайнено.",
        "block": block_data
    }), 200

@app.route('/block/receive', methods=['POST'])
def receive_block():
    data = request.get_json()
    new_block = deserialize_block(data)

    if new_block.previous_hash == blockchain.get_last_block().hash:
        if new_block.calculate_hash() == new_block.hash and new_block.hash.startswith("0" * new_block.difficulty):
            blockchain.chain.append(new_block)
            
            mined_hashes = {blockchain.mempool.get_tx_hash(t) for t in new_block.transactions}
            blockchain.mempool.pending_transactions = [
                t for t in blockchain.mempool.pending_transactions 
                if blockchain.mempool.get_tx_hash(t) not in mined_hashes
            ]
            return jsonify({"message": "Блок прийнято."}), 200

    resolve_conflicts()
    return jsonify({"message": "Синхронізація розгалуження виконана."}), 200

@app.route('/chain', methods=['GET'])
def get_chain():
    chain_data = [serialize_block(b) for b in blockchain.chain]
    return jsonify({
        "length": len(chain_data),
        "chain": chain_data
    }), 200

@app.route('/balance/<address>', methods=['GET'])
def get_balance(address):
    balance = blockchain.get_balance(address)
    return jsonify({"address": address, "balance": balance}), 200

@app.route('/validate', methods=['GET'])
def validate_chain():
    valid, msg = blockchain.is_chain_valid()
    return jsonify({"is_valid": valid, "message": msg}), 200

@app.route('/nodes/register', methods=['POST'])
def register_nodes():
    values = request.get_json()
    nodes_list = values.get('nodes')
    if not nodes_list:
        return jsonify({"message": "Помилка: Надайте коректний список вузлів."}), 400

    for node in nodes_list:
        peers.add(node)

    return jsonify({"message": "Вузли успішно додано.", "total_nodes": list(peers)}), 201

def resolve_conflicts() -> bool:
    new_chain = None
    max_length = len(blockchain.chain)

    for node in peers:
        try:
            response = requests.get(f"{node}/chain", timeout=2)
            if response.status_code == 200:
                length = response.json()['length']
                chain_data = response.json()['chain']
                
                temp_chain = [deserialize_block(b) for b in chain_data]
                is_valid, _ = blockchain.is_chain_valid(temp_chain)

                if length > max_length and is_valid:
                    max_length = length
                    new_chain = temp_chain
        except Exception:
            continue

    if new_chain:
        fork_index = 0
        while fork_index < len(blockchain.chain) and fork_index < len(new_chain):
            if blockchain.chain[fork_index].hash != new_chain[fork_index].hash:
                break
            fork_index += 1

        orphan_txs = []
        for b in blockchain.chain[fork_index:]:
            for tx in b.transactions:
                if tx.sender != "COINBASE":
                    orphan_txs.append(tx)

        blockchain.chain = new_chain

        confirmed_hashes = blockchain.get_confirmed_tx_hashes()
        for tx in orphan_txs:
            tx_hash = blockchain.mempool.get_tx_hash(tx)
            if tx_hash not in confirmed_hashes and not any(blockchain.mempool.get_tx_hash(t) == tx_hash for t in blockchain.mempool.pending_transactions):
                blockchain.mempool.pending_transactions.append(tx)

        return True

    return False

@app.route('/nodes/resolve', methods=['GET'])
def consensus():
    replaced = resolve_conflicts()
    if replaced:
        return jsonify({"message": "Ланцюг було замінено на довший.", "new_length": len(blockchain.chain)}), 200
    return jsonify({"message": "Наш ланцюг є актуальним.", "length": len(blockchain.chain)}), 200

if __name__ == '__main__':
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5001
    app.run(host='0.0.0.0', port=port)