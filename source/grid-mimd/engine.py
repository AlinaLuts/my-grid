#!/usr/bin/env python3
"""
GridSimulationEngine: Monte Carlo Power Grid Cascade Simulator (IEEE-118).
Course: Cloud and Grid Systems
Stage 1: MIMD PC (multiprocessing.Pool, chunking, speedup analysis).
"""

from __future__ import annotations

import math
import os
import random
from dataclasses import dataclass
from multiprocessing import Pool, cpu_count
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Стандартні 186 ліній тестової енергосистеми IEEE-118: пари (from_bus, to_bus), 1-індексація
IEEE118_BRANCHES: List[Tuple[int, int]] = [
    (1, 2), (1, 3), (2, 12), (3, 5), (4, 5), (4, 11), (5, 6), (5, 11),
    (6, 7), (7, 12), (8, 9), (8, 5), (8, 30), (9, 10), (11, 12), (11, 13),
    (12, 14), (12, 16), (12, 117), (13, 15), (14, 15), (15, 17), (15, 33), (15, 19),
    (16, 17), (17, 18), (17, 30), (17, 113), (18, 19), (19, 20), (19, 34), (20, 21),
    (21, 22), (22, 23), (23, 24), (23, 25), (23, 32), (24, 70), (24, 72), (25, 26),
    (25, 27), (26, 30), (27, 28), (27, 32), (27, 115), (28, 29), (29, 31), (30, 38),
    (31, 32), (32, 113), (32, 114), (33, 37), (34, 36), (34, 37), (35, 36), (35, 37),
    (37, 39), (37, 40), (38, 65), (39, 40), (40, 41), (40, 42), (41, 42), (42, 49),
    (43, 44), (44, 45), (45, 46), (45, 49), (46, 47), (46, 48), (47, 49), (47, 69),
    (48, 49), (49, 50), (49, 51), (49, 54), (49, 66), (49, 69), (50, 57), (51, 52),
    (51, 58), (52, 53), (53, 54), (54, 55), (54, 56), (54, 59), (55, 56), (55, 59),
    (56, 57), (56, 58), (56, 59), (59, 60), (59, 61), (59, 63), (60, 61), (60, 62),
    (61, 62), (62, 63), (62, 64), (63, 64), (64, 65), (65, 66), (65, 68), (66, 67),
    (67, 68), (68, 69), (68, 81), (68, 116), (69, 70), (69, 75), (69, 77), (70, 71),
    (70, 74), (70, 75), (71, 72), (71, 73), (72, 73), (73, 74), (74, 75), (75, 77),
    (75, 118), (76, 77), (76, 118), (77, 78), (77, 80), (77, 82), (78, 79), (79, 80),
    (80, 81), (80, 96), (80, 97), (80, 98), (80, 99), (81, 82), (82, 83), (82, 96),
    (83, 84), (83, 85), (84, 85), (85, 86), (85, 88), (85, 89), (86, 87), (88, 89),
    (89, 90), (89, 92), (90, 91), (91, 92), (92, 93), (92, 94), (92, 100), (92, 102),
    (93, 94), (94, 95), (94, 96), (94, 100), (95, 96), (96, 97), (98, 100), (99, 100),
    (100, 101), (100, 103), (100, 104), (100, 106), (101, 102), (103, 104), (103, 105),
    (103, 110), (104, 105), (105, 106), (105, 107), (105, 108), (106, 107), (107, 108),
    (108, 109), (109, 110), (110, 111), (110, 112), (111, 112), (112, 113), (114, 115)
]


class GridTopology:
    """
    Зберігає топологію енергосистеми IEEE-118 (118 вузлів, 186 ліній).
    Підтримує завантаження з датасету PowerGraph (.mat) або автономну генерацію.
    """

    def __init__(
        self,
        buses: List[Dict[str, Any]],
        branches: List[Dict[str, Any]]
    ):
        self.buses = buses
        self.branches = branches
        self.n_buses = len(buses)
        self.n_branches = len(branches)
        
        # Словник суміжності: bus_id -> список індексів ліній (branch_id)
        self.node_to_branches: Dict[int, List[int]] = {b["id"]: [] for b in buses}
        for br in branches:
            u, v, b_id = br["from_bus"], br["to_bus"], br["id"]
            if u in self.node_to_branches:
                self.node_to_branches[u].append(b_id)
            if v in self.node_to_branches:
                self.node_to_branches[v].append(b_id)

    def to_dict(self) -> Dict[str, Any]:
        """Серіалізація топології для безпечної передачі через IPC воркерам multiprocessing."""
        return {
            "buses": self.buses,
            "branches": self.branches,
            "node_to_branches": self.node_to_branches,
            "total_load": sum(max(0.0, b["load"]) for b in self.buses) or 1.0,
        }

    @classmethod
    def from_dataset(cls, data_dir: Path | str, sample_idx: int = 87554) -> "GridTopology":
        """
        Завантаження конкретного зрізу (сценарію) sample_idx з файлів PowerGraph .mat.
        Витягує реальні навантаження 118 вузлів з Bf.mat та потоки/ліміти 186 ліній з Ef.mat.
        Якщо датасет відсутній — прозоро перемикається на автономну еталонну модель.
        """
        data_path = Path(data_dir)
        raw_candidates = [
            data_path / "dataset_cascades" / "ieee118" / "ieee118" / "raw",
            data_path / "ieee118" / "ieee118" / "raw",
            data_path / "ieee118" / "raw",
            data_path / "raw",
            data_path,
        ]
        
        found_dir = None
        for cand in raw_candidates:
            if (cand / "blist.mat").exists():
                found_dir = cand
                break

        if not found_dir:
            print(f"[INFO] Файли датасету не знайдено за шляхом {data_path}. Використовується автономна топологія IEEE-118.")
            return cls.build_default_ieee118()

        try:
            import numpy as np
            import h5py
            import scipy.io as sio

            # 1. Читання blist.mat (186 ліній)
            blist_file = found_dir / "blist.mat"
            try:
                blist_mat = sio.loadmat(str(blist_file))
                key = "bList" if "bList" in blist_mat else "blist"
                blist = np.asarray(blist_mat[key], dtype=np.float64)
            except Exception:
                with h5py.File(blist_file, "r") as hf:
                    key = "bList" if "bList" in hf else [k for k in hf.keys() if not k.startswith("#")][0]
                    blist = np.array(hf[key], dtype=np.float64)

            if blist.shape == (2, 186):
                blist = blist.T

            n_branches = int(blist.shape[0])

            # 2. Читання зрізу sample_idx з Ef.mat (потоки та ємності 186 ліній)
            ef_file = found_dir / "Ef.mat"
            ef_sample = None
            if ef_file.exists():
                with h5py.File(ef_file, "r") as hf:
                    var_name = "E_f_post" if "E_f_post" in hf else [k for k in hf.keys() if not k.startswith("#")][0]
                    ds = hf[var_name]
                    idx = np.unravel_index(sample_idx % ds.size, ds.shape)
                    ref = ds[idx]
                    arr = np.array(hf[ref], dtype=np.float64)
                    if arr.ndim == 2 and arr.shape == (4, 186):
                        arr = arr.T
                    ef_sample = arr

            # 3. Читання зрізу sample_idx з Bf.mat (навантаження 118 вузлів)
            bf_file = found_dir / "Bf.mat"
            bf_sample = None
            if bf_file.exists():
                with h5py.File(bf_file, "r") as hf:
                    var_name = "B_f_tot" if "B_f_tot" in hf else [k for k in hf.keys() if not k.startswith("#")][0]
                    ds = hf[var_name]
                    idx = np.unravel_index(sample_idx % ds.size, ds.shape)
                    ref = ds[idx]
                    arr = np.array(hf[ref], dtype=np.float64)
                    if arr.ndim == 2 and arr.shape == (3, 118):
                        arr = arr.T
                    bf_sample = arr

            branches = []
            for i in range(n_branches):
                u, v = int(blist[i, 0]), int(blist[i, 1])
                if ef_sample is not None and i < ef_sample.shape[0]:
                    flow = abs(float(ef_sample[i, 0]))
                    raw_cap = float(ef_sample[i, 3])
                    # Нормалізація ємності для безлімітних ліній або z-score артефактів
                    capacity = raw_cap if raw_cap > flow * 1.05 else max(1.0, flow * 1.5)
                else:
                    flow = 40.0 + ((i * 17) % 80)
                    capacity = flow * 1.4

                branches.append({
                    "id": i,
                    "from_bus": u,
                    "to_bus": v,
                    "flow": float(flow),
                    "capacity": float(capacity),
                    "active": True
                })

            n_buses = 118
            buses = []
            for j in range(n_buses):
                bus_id = j + 1
                if bf_sample is not None and j < bf_sample.shape[0]:
                    load = abs(float(bf_sample[j, 0]))
                    voltage = float(bf_sample[j, 2]) if bf_sample.shape[1] > 2 else 1.0
                else:
                    load = 15.0 + ((j * 13) % 65)
                    voltage = 1.0

                buses.append({"id": bus_id, "load": float(load), "voltage": float(voltage)})

            print(f"[OK] Успішно завантажено зріз сценарію s={sample_idx} з датасету PowerGraph ({found_dir.name}).")
            return cls(buses=buses, branches=branches)

        except Exception as exc:
            print(f"[УВАГА] Не вдалося зчитати зріз s={sample_idx} з HDF5 ({exc}). Увімкнено автономну модель IEEE-118.")
            return cls.build_default_ieee118()

    @classmethod
    def build_default_ieee118(cls) -> "GridTopology":
        """
        Автономна генерація еталонної моделі IEEE-118 (118 вузлів, 186 гілок).
        Забезпечує негайну працездатність навіть без 2 ГБ бінарних файлів датасету.
        """
        branches = []
        for i, (u, v) in enumerate(IEEE118_BRANCHES):
            # Фізично узгоджений початковий потік і ліміт пропускної здатності
            base_flow = 40.0 + ((i * 17) % 80)
            # Коефіцієнт навантаження 60-80% у нормальному стані (запас 25-40%)
            margin = 1.35 + ((i * 7) % 30) / 100.0
            capacity = round(base_flow * margin, 2)
            branches.append({
                "id": i,
                "from_bus": u,
                "to_bus": v,
                "flow": float(base_flow),
                "capacity": float(capacity),
                "active": True
            })

        # 118 вузлів з реалістичними навантаженнями (МВт)
        buses = []
        for j in range(1, 119):
            load_mw = 15.0 + ((j * 13) % 65)
            buses.append({
                "id": j,
                "load": float(load_mw),
                "voltage": 1.0
            })

        return cls(buses=buses, branches=branches)


def run_trial(topology_dict: Dict[str, Any], k_fault: int = 1, seed: int | None = None) -> Dict[str, Any]:
    """
    Моделювання одного незалежного сценарію каскадної аварії (Monte Carlo Trial).
    
    1. Зважений вибір k_fault аварійних ліній за показником завантаження flow / capacity.
    2. Перерозподіл потоків з аварійних ліній на активні суміжні гілки за вільною ємністю.
    3. Релейне спрацювання захисту при flow > capacity (каскадний крок).
    4. Зупинка при стабілізації або блек-ауті.
    """
    rng = random.Random(seed)
    
    branches = topology_dict["branches"]
    node_to_branches = topology_dict["node_to_branches"]
    n_branches = len(branches)
    total_load = topology_dict["total_load"]

    # Локальні масиви стану для високої швидкодії
    active = [True] * n_branches
    flows = [br["flow"] for br in branches]
    capacities = [br["capacity"] for br in branches]
    from_buses = [br["from_bus"] for br in branches]
    to_buses = [br["to_bus"] for br in branches]

    # --- 1. Первинний шок N-k (зважений вибір за завантаженістю ліній) ---
    weights = []
    for i in range(n_branches):
        utilization = abs(flows[i]) / max(1.0, capacities[i])
        weights.append(max(0.01, utilization ** 2))
    
    # Вибираємо k_fault унікальних ліній
    initial_shock: List[int] = []
    remaining_indices = list(range(n_branches))
    rem_weights = list(weights)

    for _ in range(min(k_fault, n_branches)):
        total_w = sum(rem_weights)
        probs = [w / total_w for w in rem_weights]
        r = rng.random()
        cum = 0.0
        chosen_idx = 0
        for idx, p in enumerate(probs):
            cum += p
            if r <= cum:
                chosen_idx = idx
                break
        
        line_id = remaining_indices.pop(chosen_idx)
        rem_weights.pop(chosen_idx)
        initial_shock.append(line_id)

    # Вимикаємо початкові аварійні лінії
    failed_lines = list(initial_shock)
    for l_id in initial_shock:
        active[l_id] = False

    newly_tripped = list(initial_shock)
    cascade_trips = 0
    max_steps = 30
    step = 0
    lost_load = 0.0

    # --- 2. Цикл розвитку каскаду (Ланцюгова реакція) ---
    while newly_tripped and step < max_steps:
        step += 1
        lines_to_redistribute = newly_tripped
        newly_tripped = []

        for line_id in lines_to_redistribute:
            spilled_flow = abs(flows[line_id])
            flows[line_id] = 0.0
            u = from_buses[line_id]
            v = to_buses[line_id]

            # Суміжні активні гілки біля вузлів u та v
            neighbor_branches = set()
            for b_id in node_to_branches.get(u, []):
                if active[b_id]:
                    neighbor_branches.add(b_id)
            for b_id in node_to_branches.get(v, []):
                if active[b_id]:
                    neighbor_branches.add(b_id)

            if not neighbor_branches:
                # Вузол відсічено від мережі — втрата навантаження
                lost_load += spilled_flow * 0.5
                continue

            # Розподіл пропорційно вільному резерву (capacity - flow)
            reserves = [max(0.5, capacities[nbr] - abs(flows[nbr])) for nbr in neighbor_branches]
            sum_reserves = sum(reserves)

            for nbr, res in zip(neighbor_branches, reserves):
                share = (res / sum_reserves) * spilled_flow
                flows[nbr] += share

        # Перевірка на перевантаження серед усіх активних ліній
        overloaded = []
        for i in range(n_branches):
            if active[i] and abs(flows[i]) > capacities[i]:
                overloaded.append(i)

        if not overloaded:
            # Стабілізація: всі активні лінії тримають струм
            break

        # Захист вибиває перевантажені лінії
        for ov_id in overloaded:
            active[ov_id] = False
            failed_lines.append(ov_id)
            newly_tripped.append(ov_id)
            cascade_trips += 1

    # --- 3. Фінальні метрики випробування ---
    dns_proxy = min(1.0, (lost_load + cascade_trips * 12.0) / total_load)
    
    # Критерій блек-ауту: суттєва втрата потужності (> 5%) або масовий обвал ліній (> 10% мережі)
    is_blackout = bool(dns_proxy >= 0.05 or len(failed_lines) >= 18)

    return {
        "blackout": is_blackout,
        "cascade_trips": cascade_trips,
        "failed_lines": failed_lines,
        "initial_shock": initial_shock,
        "dns_proxy": round(dns_proxy, 4),
    }


def simulate_trials_chunk(args: Tuple[int, int, int, Dict[str, Any]]) -> Dict[str, Any]:
    """
    Обробник пакета випробувань (chunk) у воркері пулу multiprocessing.
    
    args: (chunk_size, k_fault, base_seed, topology_dict)
    """
    chunk_size, k_fault, base_seed, topology_dict = args
    
    blackouts = 0
    total_trips = 0
    total_dns = 0.0
    line_failure_counts: Dict[int, int] = {}

    for i in range(chunk_size):
        seed = base_seed + i
        res = run_trial(topology_dict, k_fault=k_fault, seed=seed)

        if res["blackout"]:
            blackouts += 1
            # Фіксуємо лінії, які спричинили або потрапили під удар під час блек-ауту
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


class GridSimulationEngine:
    """
    Координатор паралельної симуляції Монте-Карло для енергомережі IEEE-118.
    Реалізує MIMD-патерн: чанкування задач, Pool.map, агрегація метрик.
    """

    def __init__(
        self,
        topology: GridTopology | None = None,
        data_dir: Path | str | None = None,
        sample_idx: int = 87554
    ):
        self.sample_idx = sample_idx
        if topology:
            self.topology = topology
        elif data_dir:
            self.topology = GridTopology.from_dataset(data_dir, sample_idx=sample_idx)
        else:
            self.topology = GridTopology.build_default_ieee118()

    def run_simulation(
        self,
        n_trials: int = 10000,
        n_workers: int = 1,
        k_fault: int = 1,
        base_seed: int = 42
    ) -> Dict[str, Any]:
        """
        Запуск симуляції на пулі з n_workers процесів.
        """
        if n_workers <= 0:
            n_workers = cpu_count()

        topology_dict = self.topology.to_dict()

        # Розбиття n_trials на чанки для кожного воркера
        chunk_size = n_trials // n_workers
        remainder = n_trials % n_workers

        tasks = []
        current_seed = base_seed
        for w in range(n_workers):
            # Додаємо залишок до перших воркерів
            c_size = chunk_size + (1 if w < remainder else 0)
            if c_size > 0:
                tasks.append((c_size, k_fault, current_seed, topology_dict))
                current_seed += c_size + 100

        # Виконання розрахунків (однопотоково без пулу або через multiprocessing.Pool)
        if n_workers == 1:
            results = [simulate_trials_chunk(tasks[0])]
        else:
            with Pool(processes=n_workers) as pool:
                results = pool.map(simulate_trials_chunk, tasks)

        # Агрегація результатів
        total_trials_computed = sum(r["total_trials"] for r in results)
        total_blackouts = sum(r["blackouts"] for r in results)
        total_trips = sum(r["total_trips"] for r in results)
        total_dns = sum(r["total_dns"] for r in results)

        combined_line_counts: Dict[int, int] = {}
        for r in results:
            for l_id, cnt in r["line_failure_counts"].items():
                combined_line_counts[l_id] = combined_line_counts.get(l_id, 0) + cnt

        # Рейтинг найбільш уразливих ліній (топ-5)
        top_lines = sorted(combined_line_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        top_vulnerable = [
            {
                "branch_id": l_id,
                "from_bus": self.topology.branches[l_id]["from_bus"],
                "to_bus": self.topology.branches[l_id]["to_bus"],
                "failures_in_blackouts": cnt,
                "failure_rate": round(cnt / max(1, total_blackouts), 4)
            }
            for l_id, cnt in top_lines
        ]

        p_blackout = total_blackouts / max(1, total_trials_computed)
        avg_trips = total_trips / max(1, total_trials_computed)
        avg_dns = total_dns / max(1, total_trials_computed)

        return {
            "trials": total_trials_computed,
            "workers": n_workers,
            "k_fault": k_fault,
            "blackouts": total_blackouts,
            "p_blackout": round(p_blackout, 6),
            "avg_cascade_trips": round(avg_trips, 2),
            "avg_dns": round(avg_dns, 6),
            "top_vulnerable_lines": top_vulnerable
        }
