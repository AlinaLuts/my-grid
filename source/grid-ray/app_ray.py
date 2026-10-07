#!/usr/bin/env python3
"""
Етап 2: Ray Grid — розподілена симуляція на кількох ноутбуках.

CLI:
    python app_ray.py status
    python app_ray.py load --trials 10000 --k 1 --sample 69411
    python app_ray.py report --in benchmark_results_ray_grid.json
"""
import sys
import time
import json
import argparse
from pathlib import Path

import ray

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "grid-mimd"))
from engine import GridTopology, run_trial


@ray.remote
def simulate_trials_chunk_ray(chunk_size, k_fault, base_seed, topology_dict):
    blackouts = 0
    total_trips = 0
    total_dns = 0.0
    line_failure_counts = {}

    for i in range(chunk_size):
        seed = base_seed + i
        res = run_trial(topology_dict, k_fault=k_fault, seed=seed)
        if res["blackout"]:
            blackouts += 1
            for l_id in res["failed_lines"]:
                line_failure_counts[l_id] = line_failure_counts.get(l_id, 0) + 1
        total_trips += res["cascade_trips"]
        total_dns += res["dns_proxy"]

    return {
        "total_trials": chunk_size,
        "blackouts": blackouts,
        "total_trips": total_trips,
        "total_dns": total_dns,
        "line_failure_counts": line_failure_counts,
    }


# ──────────────────────────────────────────────────────────────
# Підкоманда: status
# ──────────────────────────────────────────────────────────────
def cmd_status(args):
    """Показати стан Ray-кластера."""
    ray.init(address="auto", ignore_reinit_error=True)
    resources = ray.cluster_resources()
    nodes = ray.nodes()

    print("=" * 60)
    print("RAY CLUSTER STATUS")
    print("=" * 60)
    print(f"CPU:  {resources.get('CPU', 0)}")
    print(f"GPU:  {resources.get('GPU', 0)}")
    print(f"RAM:  {resources.get('memory', 0) / 1e9:.2f} GB")
    print()
    print(f"Active nodes: {len([n for n in nodes if n['Alive']])}")
    for i, n in enumerate(nodes, 1):
        if n["Alive"]:
            ip = n["NodeManagerAddress"]
            cpus = n["Resources"].get("CPU", 0)
            print(f"  Node {i}: {ip}  ({cpus} CPU)")

    ray.shutdown()


# ──────────────────────────────────────────────────────────────
# Підкоманда: load
# ──────────────────────────────────────────────────────────────
def cmd_load(args):
    """Запустити розподілену симуляцію."""
    ray.init(address="auto", ignore_reinit_error=True)

    resources = ray.cluster_resources()
    num_cpus = int(resources.get("CPU", 1))

    print("=" * 60)
    print("RAY GRID BENCHMARK")
    print("=" * 60)
    print(f"Trials:   {args.trials}")
    print(f"k_fault:  {args.k}")
    print(f"Sample:   {args.sample}")
    print(f"CPU:      {num_cpus}")
    print("-" * 60)

    # Завантаження топології (тільки на Head)
    topo = GridTopology.from_dataset(args.data, sample_idx=args.sample)
    topology_dict = topo.to_dict()

    # Розбиття на чанки
    num_workers = num_cpus
    chunk_size = args.trials // num_workers
    remainder = args.trials % num_workers

    tasks = []
    current_seed = 100_000
    for w in range(num_workers):
        c_size = chunk_size + (1 if w < remainder else 0)
        if c_size > 0:
            tasks.append(simulate_trials_chunk_ray.remote(
                c_size, args.k, current_seed, topology_dict
            ))
            current_seed += c_size

    # Запуск
    start = time.perf_counter()
    results = ray.get(tasks)
    elapsed = time.perf_counter() - start

    # Агрегація
    total_trials = sum(r["total_trials"] for r in results)
    total_blackouts = sum(r["blackouts"] for r in results)
    total_trips = sum(r["total_trips"] for r in results)
    total_dns = sum(r["total_dns"] for r in results)

    p_blackout = total_blackouts / max(1, total_trials)
    avg_trips = total_trips / max(1, total_trials)
    avg_dns = total_dns / max(1, total_trials)
    throughput = total_trials / elapsed

    print(f"Час:        {elapsed:.3f} сек")
    print(f"Throughput: {throughput:.1f} trials/sec")
    print(f"P(blackout): {p_blackout:.4f}")
    print(f"avg_trips:  {avg_trips:.2f}")
    print(f"avg_dns:    {avg_dns:.6f}")
    print("=" * 60)

    # Збереження JSON
    report = {
        "metadata": {
            "backend": "ray",
            "trials": total_trials,
            "k_fault": args.k,
            "sample": args.sample,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        },
        "cluster": {
            "nodes": len([n for n in ray.nodes() if n["Alive"]]),
            "cpus": num_cpus,
        },
        "results": {
            "total_execution_time_sec": round(elapsed, 4),
            "throughput_trials_per_sec": round(throughput, 2),
            "p_blackout": round(p_blackout, 6),
            "avg_cascade_trips": round(avg_trips, 2),
            "avg_dns": round(avg_dns, 6),
        },
    }

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"Звіт збережено: {args.out}")

    ray.shutdown()


def cmd_report(args):
    """Порівняти результати Етапу 1 (MIMD) та Етапу 2 (Ray)."""
    # Файл Етапу 1
    etap1_file = Path("source/grid-mimd/benchmark_results_mimd_grid.json")
    if not etap1_file.exists():
        etap1_file = Path("benchmark_results_mimd_grid.json")
    
    # Файл Етапу 2
    etap2_file = args.in_file
    if not etap2_file.exists():
        print(f"Файл Етапу 2 не знайдено: {etap2_file}")
        print("Спочатку запустіть: python app_ray.py load --trials 10000")
        return

    print("=" * 70)
    print("  ПОРІВНЯННЯ: ЕТАП 1 (MIMD) vs ЕТАП 2 (RAY GRID)")
    print("=" * 70)

    # ─── Етап 1 ───
    if etap1_file.exists():
        with open(etap1_file, "r", encoding="utf-8") as f:
            data1 = json.load(f)
        
        print("\n📊 ЕТАП 1 (MIMD PC, multiprocessing.Pool)")
        print("-" * 70)
        print(f"  Модель:     {data1['metadata']['model']}")
        print(f"  Trials:     {data1['metadata']['n_trials']}")
        print(f"  Sample:     {data1['metadata']['sample_index']}")
        print(f"  k_fault:    {data1['metadata']['k_fault']}")
        print(f"  CPU count:  {data1['metadata']['cpu_count']}")
        print()
        
        # Показуємо всі прогони
        print(f"  {'Workers':<10} {'Час (с)':<12} {'Throughput':<18} {'Speedup':<10} {'P(blackout)':<12}")
        print("  " + "-" * 66)
        for run in data1["runs"]:
            print(f"  {run['workers']:<10} {run['elapsed_sec']:<12.3f} "
                  f"{run['throughput_trials_per_sec']:<18.1f} "
                  f"{run['speedup']:<10.2f} {run['p_blackout']:<12.4f}")
        
        # Найкращий результат
        best1 = max(data1["runs"], key=lambda r: r["throughput_trials_per_sec"])
        print()
        print(f"  🏆 Найкращий: {best1['workers']} workers, "
              f"{best1['throughput_trials_per_sec']:.1f} trials/sec "
              f"(speedup {best1['speedup']:.2f}x)")
    else:
        print(f"\n⚠️  Файл Етапу 1 не знайдено ({etap1_file})")
        print("   Запустіть спочатку Етап 1:")
        print("   python source/grid-mimd/app.py --headless --trials 10000 --workers 1,2,4,8,12")

    # ─── Етап 2 ───
    with open(etap2_file, "r", encoding="utf-8") as f:
        data2 = json.load(f)

    print("\n📊 ЕТАП 2 (RAY GRID)")
    print("-" * 70)
    print(f"  Backend:    {data2['metadata']['backend']}")
    print(f"  Trials:     {data2['metadata']['trials']}")
    print(f"  Sample:     {data2['metadata']['sample']}")
    print(f"  k_fault:    {data2['metadata']['k_fault']}")
    print(f"  Nodes:      {data2['cluster']['nodes']}")
    print(f"  CPUs:       {data2['cluster']['cpus']}")
    print()
    print(f"  Час:        {data2['results']['total_execution_time_sec']} сек")
    print(f"  Throughput: {data2['results']['throughput_trials_per_sec']} trials/sec")
    print(f"  P(blackout): {data2['results']['p_blackout']}")
    print(f"  avg_trips:  {data2['results']['avg_cascade_trips']}")
    print(f"  avg_dns:    {data2['results']['avg_dns']}")

    # ─── Порівняння ───
    if etap1_file.exists():
        print("\n" + "=" * 70)
        print("  ПОРІВНЯЛЬНА ТАБЛИЦЯ")
        print("=" * 70)
        
        best1 = max(data1["runs"], key=lambda r: r["throughput_trials_per_sec"])
        tp1 = best1["throughput_trials_per_sec"]
        tp2 = data2["results"]["throughput_trials_per_sec"]
        
        print(f"\n  {'Бекенд':<25} {'Throughput (trials/sec)':<25} {'Прискорення':<12}")
        print("  " + "-" * 62)
        print(f"  {'pool (Етап 1, ' + str(best1['workers']) + ' workers)':<25} "
              f"{tp1:<25.1f} {'1.00x':<12}")
        print(f"  {'ray (Етап 2, ' + str(data2['cluster']['nodes']) + ' nodes)':<25} "
              f"{tp2:<25.1f} {tp2/tp1:.2f}x")
        
        print(f"\n  P(blackout) однаковий: {data1['runs'][0]['p_blackout']:.4f} "
              f"(Етап 1) vs {data2['results']['p_blackout']:.4f} (Етап 2)")
        
        print("\n  💡 Висновок:")
        if tp2 > tp1:
            print(f"     Ray швидший у {tp2/tp1:.2f}x за рахунок 2 вузлів")
        else:
            print(f"     Ray повільніший — накладні витрати мережі перевищують виграш")
        print("=" * 70)

# ──────────────────────────────────────────────────────────────
# Головний парсер
# ──────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Ray Grid — розподілена симуляція IEEE-118"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # status
    p_status = subparsers.add_parser("status", help="Стан Ray-кластера")
    p_status.set_defaults(func=cmd_status)

    # load
    p_load = subparsers.add_parser("load", help="Запуск симуляції")
    p_load.add_argument("--trials", type=int, default=10000)
    p_load.add_argument("--k", type=int, default=1)
    p_load.add_argument("--sample", type=int, default=69411)
    p_load.add_argument("--data", type=Path, default=Path("Datasets"))
    p_load.add_argument("--out", type=Path, default=Path("benchmark_results_ray_grid.json"))
    p_load.set_defaults(func=cmd_load)

    # report
    p_report = subparsers.add_parser("report", help="Показати звіт")
    p_report.add_argument("--in", dest="in_file", type=Path, default=Path("benchmark_results_ray_grid.json"))
    p_report.set_defaults(func=cmd_report)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()