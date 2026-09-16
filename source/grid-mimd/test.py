#!/usr/bin/env python3
"""
Пошук samples у датасеті PowerGraph, де мережа найбільш навантажена
і де run_trial дає блекаут.

Запуск:
    python find_stressed_sample.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "source" / "grid-mimd"))
from engine import GridTopology, run_trial

# Скільки samples перевірити (рівномірно по всьому діапазону 0..122499)
N_SAMPLES = 30
STEP = 122500 // N_SAMPLES

# Скільки trials на кожен sample (для оцінки P(blackout))
TRIALS_PER_SAMPLE = 100
K_FAULT = 1

print("=" * 90)
print(f"ПОШУК НАВАНТАЖЕНИХ SAMPLES (перевіряємо {N_SAMPLES} samples, по {TRIALS_PER_SAMPLE} trials)")
print("=" * 90)
print(f"{'sample':>8} | {'avg_util':>10} | {'max_util':>10} | {'trips (1 trial)':>16} | {'P(blackout)':>12} | {'top line':>10}")
print("-" * 90)

results = []

for s in range(0, 122500, STEP):
    try:
        topo = GridTopology.from_dataset("Datasets", sample_idx=s)
        topo_dict = topo.to_dict()
        
        # Utilization
        utils = [abs(b["flow"]) / max(0.01, b["capacity"]) for b in topo.branches]
        avg_util = sum(utils) / len(utils) * 100
        max_util = max(utils) * 100
        
        # Один trial для швидкої оцінки
        res1 = run_trial(topo_dict, k_fault=K_FAULT, seed=42)
        
        # Багато trials для P(blackout)
        blackouts = 0
        line_counts = {}
        for i in range(TRIALS_PER_SAMPLE):
            r = run_trial(topo_dict, k_fault=K_FAULT, seed=1000 + i)
            if r["blackout"]:
                blackouts += 1
                for l in r["failed_lines"]:
                    line_counts[l] = line_counts.get(l, 0) + 1
        
        p_blackout = blackouts / TRIALS_PER_SAMPLE
        
        # Топ-лінія
        top_line = "-"
        if line_counts:
            top_id = max(line_counts, key=line_counts.get)
            top_line = f"#{top_id} ({line_counts[top_id]})"
        
        print(f"{s:>8} | {avg_util:>9.1f}% | {max_util:>9.1f}% | {res1['cascade_trips']:>16} | {p_blackout:>11.3f} | {top_line:>10}")
        
        results.append({
            "sample": s,
            "avg_util": avg_util,
            "max_util": max_util,
            "p_blackout": p_blackout,
        })
    
    except Exception as e:
        print(f"{s:>8} | ПОМИЛКА: {e}")

print("=" * 90)

# Топ-3 найкращих samples
print("\n🏆 ТОП-3 SAMPLES ДЛЯ БЕНЧМАРКУ (найвищий P(blackout)):")
sorted_by_p = sorted(results, key=lambda x: x["p_blackout"], reverse=True)
for i, r in enumerate(sorted_by_p[:3], 1):
    print(f"  #{i}: sample={r['sample']}, P(blackout)={r['p_blackout']:.3f}, avg_util={r['avg_util']:.1f}%")

print("\n🏆 ТОП-3 SAMPLES ЗА НАВАНТАЖЕННЯМ (найвищий avg_util):")
sorted_by_util = sorted(results, key=lambda x: x["avg_util"], reverse=True)
for i, r in enumerate(sorted_by_util[:3], 1):
    print(f"  #{i}: sample={r['sample']}, avg_util={r['avg_util']:.1f}%, P(blackout)={r['p_blackout']:.3f}")

print("\n💡 Використайте найкращий sample у бенчмарку:")
if sorted_by_p[0]["p_blackout"] > 0:
    best = sorted_by_p[0]["sample"]
    print(f"   python source/grid-mimd/app.py --headless --trials 10000 --workers 1,2,4,8,12 --k 1 --sample {best} --out benchmark_results_mimd_grid.json")
else:
    print("   ⚠️ Жоден sample не дав блекауту при k=1. Спробуйте k=2 або --stressed.")