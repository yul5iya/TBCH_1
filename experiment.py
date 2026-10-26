import time
import numpy as np
import matplotlib.pyplot as plt
from core import Blockchain

difficulties = [1, 2, 3, 4]
runs_per_difficulty = 10
results = {d: [] for d in difficulties}

print("Запуск експерименту вимірювання часу майнінгу...")

for d in difficulties:
    bc = Blockchain(initial_difficulty=d)
    for i in range(runs_per_difficulty):
        start_time = time.time()
        bc.mine_block("TEST_MINER")
        elapsed = time.time() - start_time
        results[d].append(elapsed)
    print(f"Складність {d}: Середній час = {np.mean(results[d]):.4f} сек")

means = [np.mean(results[d]) for d in difficulties]
stds = [np.std(results[d]) for d in difficulties]

plt.figure(figsize=(8, 5))
plt.errorbar(difficulties, means, yerr=stds, fmt='-o', capsize=5, ecolor='r', color='b')
plt.yscale('log')
plt.xlabel('Складність (кількість нулів)')
plt.ylabel('Час майнінгу (секунди, лог. шкала)')
plt.title('Залежність часу майнінгу від складності Proof of Work')
plt.xticks(difficulties)
plt.grid(True, which="both", ls="--")

plt.savefig('mining_experiment.png')
print("Графік збережено у файл mining_experiment.png")
plt.show()