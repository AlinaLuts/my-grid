#!/usr/bin/env python3
"""
CLI & Benchmark Runner for IEEE-118 Power Grid Cascade Simulation.
Course: Cloud and Grid Systems
Stage 1: MIMD PC Benchmark (speedup, throughput, P(blackout), Amdahl analysis).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from multiprocessing import cpu_count
from pathlib import Path
from typing import List

# Додаємо поточну директорію для імпорту engine
sys.path.insert(0, str(Path(__file__).resolve().parent))
from engine import GridSimulationEngine, GridTopology


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="MIMD PC Benchmark for Power Grid IEEE-118 Monte Carlo Simulation"
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        default=True,
        help="Запуск у консольному бенчмарк-режимі без UI (за замовчуванням True)"
    )
    parser.add_argument(
        "--trials",
        type=int,
        default=10000,
        help="Загальна кількість Monte Carlo випробувань (за замовчуванням 10 000, для тесту 1 000)"
    )
    parser.add_argument(
        "--workers",
        type=str,
        default=None,
        help="Список воркерів через кому, наприклад: '1,2,4' або '1,2,4,8'. За замовчуванням: 1, 2, 4, ... cpu_count()"
    )
    parser.add_argument(
        "--k",
        type=int,
        default=1,
        help="Кількість початкових аварійних ліній N-k (за замовчуванням 1, обмеження: 1 <= k <= 5)"
    )
    parser.add_argument(
        "--sample",
        type=int,
        default=87554,
        help="Індекс робочого режиму (сценарію) з датасету PowerGraph (за замовчуванням: 87554)"
    )
    parser.add_argument(
        "--data",
        type=Path,
        default=Path("Datasets"),
        help="Шлях до каталогу датасету PowerGraph (якщо відсутній — використовується автономна топологія)"
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("benchmark_results_mimd_grid.json"),
        help="Шлях для збереження підсумкового JSON-звіту"
    )
    parser.add_argument(
        "--plot",
        type=Path,
        default=Path("speedup.png"),
        help="Шлях для збереження графіка прискорення (speedup.png)"
    )
    return parser.parse_args()


def get_default_workers_list() -> List[int]:
    """Формує стандартний геометричний ряд ядер: 1, 2, 4, ..., cpu_count()."""
    n_cpus = cpu_count()
    workers = []
    w = 1
    while w <= n_cpus:
        workers.append(w)
        w *= 2
    if n_cpus not in workers:
        workers.append(n_cpus)
    return sorted(list(set(workers)))


def run_headless_benchmark(
    n_trials: int,
    workers_list: List[int],
    k_fault: int,
    sample_idx: int,
    data_path: Path,
    out_json: Path,
    plot_path: Path | None = None
) -> dict:
    """
    Основний бенчмарк: виконує прогони для різної кількості ядер,
    вимірює Speedup, Throughput, формує JSON та графік.
    """
    print("=" * 70)
    print("  MIMD PC BENCHMARK: СИМУЛЯЦІЯ ЕНЕРГОСИСТЕМИ IEEE-118 (MONTE CARLO)")
    print("=" * 70)
    print(f"Кількість випробувань (trials) : {n_trials:,}")
    print(f"Номер зрізу сценарію (s)       : {sample_idx}")
    print(f"Параметр первинного шоку (k)   : {k_fault}")
    print(f"Доступно фізичних/логічних CPU : {cpu_count()}")
    print(f"Серія тестів за воркерами      : {workers_list}")
    print("-" * 70)

    # Ініціалізація двигуна з конкретним зрізом сценарію s
    engine = GridSimulationEngine(data_dir=data_path, sample_idx=sample_idx)
    print(f"Топологія успішно ініціалізована: 118 вузлів, 186 гілок.")
    print("-" * 70)

    runs_data = []
    t1_time = None

    print(f"{'Воркери':<10} | {'Час (с)':<10} | {'Throughput (tr/s)':<18} | {'Speedup':<10} | {'P(blackout)':<12}")
    print("-" * 70)

    for w in workers_list:
        start_t = time.perf_counter()
        sim_result = engine.run_simulation(
            n_trials=n_trials,
            n_workers=w,
            k_fault=k_fault,
            base_seed=100_000 + w * 777
        )
        elapsed = time.perf_counter() - start_t

        if w == 1 or t1_time is None:
            t1_time = elapsed
            speedup = 1.0
        else:
            speedup = t1_time / elapsed if elapsed > 0 else 1.0

        throughput = n_trials / elapsed if elapsed > 0 else 0.0
        p_blackout = sim_result["p_blackout"]

        print(f"{w:<10} | {elapsed:<10.3f} | {throughput:<18.1f} | {speedup:<10.2f}x | {p_blackout:<12.4f}")

        runs_data.append({
            "workers": w,
            "elapsed_sec": round(elapsed, 4),
            "throughput_trials_per_sec": round(throughput, 2),
            "speedup": round(speedup, 3),
            "efficiency": round(speedup / w, 3),
            "p_blackout": p_blackout,
            "avg_cascade_trips": sim_result["avg_cascade_trips"],
            "avg_dns": sim_result["avg_dns"],
            "top_vulnerable_lines": sim_result["top_vulnerable_lines"]
        })

    print("-" * 70)
    print("Бенчмарк завершено успішно.")

    # Підсумковий звіт
    summary_report = {
        "metadata": {
            "model": "IEEE-118 Power Grid",
            "nodes": 118,
            "branches": 186,
            "sample_index": sample_idx,
            "k_fault": k_fault,
            "n_trials": n_trials,
            "cpu_count": cpu_count(),
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        },
        "runs": runs_data,
        "baseline_top_vulnerable_lines": runs_data[-1]["top_vulnerable_lines"]
    }

    # Збереження JSON
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(summary_report, f, indent=2, ensure_ascii=False)
    print(f"Звіт збережено у: {out_json}")

    # Побудова графіка Speedup
    if plot_path:
        generate_speedup_plot(runs_data, plot_path)

    # Вивід підсумкового аналізу для звіту
    print_summary_analysis(summary_report)

    return summary_report


def generate_speedup_plot(runs_data: list, out_file: Path) -> None:
    """Генерує графік реального прискорення у порівнянні з ідеальним лінійним."""
    try:
        import matplotlib.pyplot as plt

        workers = [r["workers"] for r in runs_data]
        speedup = [r["speedup"] for r in runs_data]
        ideal = [float(w) for w in workers]

        fig, ax = plt.subplots(figsize=(8, 6), dpi=150)
        ax.plot(workers, ideal, "r--", label="Ідеальне лінійне прискорення (S = W)")
        ax.plot(workers, speedup, "b-o", linewidth=2.2, markersize=7, label="Реальне виміряне (MIMD Pool.map)")

        ax.set_title("Прискорення симуляції IEEE-118 (Speedup vs Workers)", fontsize=13, pad=12)
        ax.set_xlabel("Кількість процесорних ядер (Workers)", fontsize=11)
        ax.set_ylabel("Прискорення (Speedup = T1 / Tw)", fontsize=11)
        ax.set_xticks(workers)
        ax.grid(True, linestyle=":", alpha=0.6)
        ax.legend(fontsize=10)

        plt.tight_layout()
        plt.savefig(out_file)
        plt.close()
        print(f"Графік прискорення збережено у: {out_file}")
    except ImportError:
        print("[УВАГА] Бібліотеку matplotlib не встановлено. Графік speedup.png пропущено.")
    except Exception as e:
        print(f"[УВАГА] Не вдалося згенерувати графік: {e}")


def print_summary_analysis(report: dict) -> None:
    """Виводить короткий аналітичний звіт для аудиторної здачі."""
    runs = report["runs"]
    first = runs[0]
    last = runs[-1]
    top_lines = report["baseline_top_vulnerable_lines"]

    print("\n" + "=" * 70)
    print("  ГОТОВІ ВІДПОВІДІ ТА АНАЛІТИКА ДЛЯ ЗВІТУ (CLASSROOM)")
    print("=" * 70)
    print(f"1. Ймовірність колапсу P(blackout) при k={report['metadata']['k_fault']}: {last['p_blackout']:.4f}")
    print(f"2. Продуктивність (Throughput):")
    print(f"   - При 1 воркері: {first['throughput_trials_per_sec']:.1f} випробувань/с")
    print(f"   - При {last['workers']} воркерах: {last['throughput_trials_per_sec']:.1f} випробувань/с")
    print(f"3. Підсумкове прискорення (Speedup): {last['speedup']:.2f}x (ефективність: {last['efficiency'] * 100:.1f}%)")
    print(f"4. Топ-3 найбільш уразливі лінії мережі:")
    for rank, line in enumerate(top_lines[:3], 1):
        print(f"   #{rank}: Гілка ID {line['branch_id']} (вузли {line['from_bus']} <-> {line['to_bus']}) "
              f"— брала участь у {line['failures_in_blackouts']} аваріях ({line['failure_rate']*100:.1f}%)")
    print("5. Коментар щодо закону Амдала:")
    print("   Прискорення сублінійне через накладні витрати IPC (міжпроцесна серіалізація через pickle),")
    print("   створення процесів операційною системою та фінальну редукцію агрегованих результатів.")
    print("=" * 70 + "\n")


def main() -> None:
    args = parse_args()

    # Валідація параметра k
    if not (1 <= args.k <= 5):
        print(f"Помилка: параметр k повинен бути в межах від 1 до 5 (передано: {args.k}).", file=sys.stderr)
        sys.exit(1)

    # Список воркерів
    if args.workers:
        try:
            workers_list = sorted(list(set(int(x.strip()) for x in args.workers.split(","))))
        except ValueError:
            print("Помилка формату --workers. Приклад: --workers 1,2,4", file=sys.stderr)
            sys.exit(1)
    else:
        workers_list = get_default_workers_list()

    run_headless_benchmark(
        n_trials=args.trials,
        workers_list=workers_list,
        k_fault=args.k,
        sample_idx=args.sample,
        data_path=args.data,
        out_json=args.out,
        plot_path=args.plot
    )


if __name__ == "__main__":
    main()
