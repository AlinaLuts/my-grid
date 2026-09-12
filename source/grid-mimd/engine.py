#!/usr/bin/env python3
"""
GridSimulationEngine: Monte Carlo Power Grid Cascade Simulator (IEEE-118).
Course: Cloud and Grid Systems
Stage 1: MIMD PC (multiprocessing.Pool, chunking, speedup analysis).
"""

from email import base64mime

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

            # 1. Читання blist.mat (186 ліній)
            blist_file = found_dir / "blist.mat"
            with h5py.File(blist_file, "r") as hf:
                key = "bList" if "bList" in hf else [k for k in hf.keys() if not k.startswith("#")][0]
                blist = np.array(hf[key], dtype=np.float64)

            if blist.shape == (2, 186):
                blist = blist.T

            n_branches = int(blist.shape[0])

            # 2. Читання sample_idx з Ef.mat
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

            # 3. Читання sample_idx з Bf.mat
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
                    flow = abs(float(ef_sample[i, 0]))          # P_ij
                    raw_cap = abs(float(ef_sample[i, 3]))       # lr_ij

                    # Захист від артефактів датасету
                    if raw_cap < 1e-6:
                        # Немає даних — синтетичний ліміт
                        capacity = max(1.0, flow * 1.5)
                    elif raw_cap < flow * 1.05:
                        # Ліміт менший за потік (z-score артефакт) — трохи піднімаємо
                        capacity = flow * 1.15
                    else:
                        capacity = raw_cap
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

            # 4. Вузли
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

            # 5. Діагностика — скільки ліній реально навантажено
            utils = [abs(b["flow"]) / max(0.01, b["capacity"]) * 100 for b in branches]
            loaded = sum(1 for u in utils if u > 60)
            overloaded = sum(1 for u in utils if u > 100)
            print(f"[OK] s={sample_idx}: {loaded} ліній >60%, {overloaded} ліній >100% (перевантажені)")

            return cls(buses=buses, branches=branches)

        except Exception as exc:
            print(f"[УВАГА] Не вдалося зчитати s={sample_idx}: {exc}")
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

    @classmethod
    def build_stressed_ieee118(cls) -> "GridTopology":
        """
        Перевантажена модель IEEE-118: лінії вже на 85-95% ємності.
        При N-1 аварії майже гарантований каскадний збій — для демонстрації блекауту.
        """
        branches = []
        for i, (u, v) in enumerate(IEEE118_BRANCHES):
            base_flow = 55.0 + ((i * 17) % 60)
            # Малий запас 5-15%: мережа вже близька до межі
            margin = 1.05 + ((i * 3) % 10) / 100.0
            capacity = round(base_flow * margin, 2)
            branches.append({
                "id": i,
                "from_bus": u,
                "to_bus": v,
                "flow": float(base_flow),
                "capacity": float(capacity),
                "active": True
            })

        buses = []
        for j in range(1, 119):
            load_mw = 25.0 + ((j * 13) % 75)
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
    bus_loads = {b["id"]: b["load"] for b in topology_dict["buses"]}
    isolated_nodes = set()

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
            neighbor_branches = []
            for b_id in node_to_branches.get(u, []):
                if active[b_id]:
                    neighbor_branches.append(b_id)
            for b_id in node_to_branches.get(v, []):
                if active[b_id]:
                    neighbor_branches.append(b_id)

            # Перевірка на ізоляцію вузлів u та v (радіальні відводи)
            if u not in isolated_nodes:
                if not any(active[b_id] for b_id in node_to_branches.get(u, [])):
                    isolated_nodes.add(u)
                    lost_load += bus_loads.get(u, 0.0)

            if v not in isolated_nodes:
                if not any(active[b_id] for b_id in node_to_branches.get(v, [])):
                    isolated_nodes.add(v)
                    lost_load += bus_loads.get(v, 0.0)

            if not neighbor_branches:
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
    dns_proxy = min(1.0, lost_load / total_load)
    
    # Критерій блек-ауту: відчутна втрата навантаження (> 5%) або масовий обвал ліній (> 10% мережі = 18 ліній)
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


def compute_node_coordinates(branches: List[Dict[str, Any]], n_buses: int = 118) -> Dict[int, Tuple[float, float]]:
    """
    Завантажує координати IEEE-118 з ieee118_coords.json (kamada_kawai_layout).
    Якщо файл відсутній — fallback на кругове розміщення.
    """
    import json
    from pathlib import Path
    
    coords_file = Path(__file__).resolve().parent / "ieee118_coords.json"
    
    if coords_file.exists():
        with open(coords_file, "r", encoding="utf-8") as f:
            raw = json.load(f)
        # JSON зберігає ключі як рядки — конвертуємо в int
        return {int(k): tuple(v) for k, v in raw.items()}
    
    # Fallback: кругове розміщення
    print("[WARN] ieee118_coords.json не знайдено, використовується кругове розміщення")
    coords = {}
    for b_id in range(1, n_buses + 1):
        angle = (b_id / n_buses) * 2 * math.pi
        coords[b_id] = (
            round(500.0 + 300.0 * math.cos(angle), 1),
            round(360.0 + 300.0 * math.sin(angle), 1)
        )
    return coords


class InteractiveGridSession:
    """
    Сесія для інтерактивної покрокової веб-візуалізації каскаду в реальному часі.
    Дозволяє спостерігати кожен крок перерозподілу струмів у браузері.
    """

    def __init__(self, topology: GridTopology, sample_idx: int = 87554, source_label: str = "default"):
        self.topology = topology
        self.sample_idx = sample_idx
        self.source_label = source_label  # "dataset", "stressed", "default"
        self.node_coords = compute_node_coordinates(topology.branches, topology.n_buses)
        self.reset()

    def reset(self):
        """Скидає мережу до початкового здорового робочого стану."""
        self.active = [True] * self.topology.n_branches
        self.flows = [float(br["flow"]) for br in self.topology.branches]
        self.capacities = [float(br["capacity"]) for br in self.topology.branches]
        self.status = "NORMAL"  # NORMAL, SHOCK, CASCADING, STABLE, BLACKOUT
        self.step_num = 0
        self.newly_tripped: List[int] = []
        self.failed_history: List[int] = []
        self.isolated_nodes: set[int] = set()
        self.lost_load = 0.0
        src = {"dataset": f"датасет s={self.sample_idx}", "stressed": "перевантажена модель", "default": "синтетична IEEE-118"}.get(self.source_label, self.source_label)
        self.logs: List[str] = [f"Мережа ініціалізована в нормальному стані (118 вузлів, 186 ліній). Джерело: {src}."]

    def trigger_shock(self, k_fault: int = 1, line_id: int | None = None) -> List[int]:
        """Спричиняє первинну аварію N-k (або вимикає конкретну вказану лінію)."""
        self.reset()
        if line_id is not None and 0 <= line_id < self.topology.n_branches:
            shock_lines = [line_id]
        else:
            # Зважений ВИПАДКОВИЙ вибір за навантаженням (Monte Carlo: більш навантажені лінії
            # мають вищу ймовірність, але кожен натиск дає різний результат)
            import time as _time
            rng = random.Random(int(_time.time() * 1000) % (2**31))
            weights = []
            for i in range(self.topology.n_branches):
                util = abs(self.flows[i]) / max(1.0, self.capacities[i])
                weights.append(max(0.01, util ** 2))

            shock_lines = []
            remaining = list(range(self.topology.n_branches))
            rem_weights = list(weights)
            for _ in range(min(k_fault, len(remaining))):
                total_w = sum(rem_weights)
                probs = [w / total_w for w in rem_weights]
                r = rng.random()
                cum = 0.0
                chosen_pos = 0
                for pos, p in enumerate(probs):
                    cum += p
                    if r <= cum:
                        chosen_pos = pos
                        break
                shock_lines.append(remaining.pop(chosen_pos))
                rem_weights.pop(chosen_pos)

        for l_id in shock_lines:
            self.active[l_id] = False
            self.failed_history.append(l_id)
            self.newly_tripped.append(l_id)
            u = self.topology.branches[l_id]["from_bus"]
            v = self.topology.branches[l_id]["to_bus"]
            self.logs.append(f"⚡ [N-k Шок] Вибито лінію #{l_id} (вузол {u} <-> {v}, потік {self.flows[l_id]:.1f} МВт).")

        self.status = "SHOCK"
        return shock_lines

    def step_cascade(self) -> Dict[str, Any]:
        """Виконує РІВНО ОДИН крок хвилі каскадного перерозподілу."""
        if not self.newly_tripped:
            if self.status in ("SHOCK", "CASCADING"):
                self.status = "STABLE"
                self.logs.append("✅ [Стабілізація] Каскад завершився. Усі активні лінії витримують навантаження.")
            return self.get_state()

        self.step_num += 1
        lines_to_process = list(self.newly_tripped)
        self.newly_tripped = []
        node_to_branches = self.topology.node_to_branches
        bus_loads = {b["id"]: b["load"] for b in self.topology.buses}

        for l_id in lines_to_process:
            spilled = abs(self.flows[l_id])
            self.flows[l_id] = 0.0
            u = self.topology.branches[l_id]["from_bus"]
            v = self.topology.branches[l_id]["to_bus"]

            neighbor_branches = []
            for b_id in node_to_branches.get(u, []):
                if self.active[b_id]:
                    neighbor_branches.append(b_id)
            for b_id in node_to_branches.get(v, []):
                if self.active[b_id]:
                    neighbor_branches.append(b_id)

            # Перевірка на ізоляцію вузлів
            for node in (u, v):
                if node not in self.isolated_nodes:
                    if not any(self.active[b_id] for b_id in node_to_branches.get(node, [])):
                        self.isolated_nodes.add(node)
                        loss = bus_loads.get(node, 0.0)
                        self.lost_load += loss
                        self.logs.append(f"⚠️ [Ізоляція] Вузол {node} повністю відрізано від мережі! Втрачено {loss:.1f} МВт.")

            if not neighbor_branches:
                continue

            reserves = [max(0.5, self.capacities[nbr] - abs(self.flows[nbr])) for nbr in neighbor_branches]
            sum_res = sum(reserves)
            for nbr, res in zip(neighbor_branches, reserves):
                delta = (res / sum_res) * spilled
                self.flows[nbr] += delta

        # Перевірка на перевантаження
        overloaded = []
        for i in range(self.topology.n_branches):
            if self.active[i] and abs(self.flows[i]) > self.capacities[i]:
                overloaded.append(i)

        if overloaded:
            self.status = "CASCADING"
            for ov_id in overloaded:
                self.active[ov_id] = False
                self.failed_history.append(ov_id)
                self.newly_tripped.append(ov_id)
                u = self.topology.branches[ov_id]["from_bus"]
                v = self.topology.branches[ov_id]["to_bus"]
                self.logs.append(
                    f"🔥 [Крок {self.step_num}] Перевантаження лінії #{ov_id} ({u}<->{v}): "
                    f"потік {self.flows[ov_id]:.1f} > ліміту {self.capacities[ov_id]:.1f} МВт! Лінію вимкнено релейним захистом."
                )
        else:
            self.status = "STABLE"
            self.logs.append(f"✅ [Крок {self.step_num}] Нових перевантажень немає. Енергосистема стабілізувалася.")

        # Перевірка на блек-аут
        total_load = self.topology.to_dict()["total_load"]
        dns_ratio = self.lost_load / total_load
        if dns_ratio >= 0.05 or len(self.failed_history) >= 18:
            self.status = "BLACKOUT"
            self.logs.append(f"💀 [КАТАСТРОФА] СИСТЕМНИЙ БЛЕКАУТ! Відключено {len(self.failed_history)} ліній.")

        return self.get_state()

    def get_state(self) -> Dict[str, Any]:
        """Повертає повний знімок для інтерфейсу візуалізації."""
        total_load = self.topology.to_dict()["total_load"]
        dns_percent = round((self.lost_load / total_load) * 100, 2)

        branches_view = []
        for i, br in enumerate(self.topology.branches):
            flow = round(self.flows[i], 1)
            cap = round(self.capacities[i], 1)
            util = round((abs(flow) / max(0.1, cap)) * 100, 1) if self.active[i] else 0.0
            branches_view.append({
                "id": i,
                "u": br["from_bus"],
                "v": br["to_bus"],
                "flow": flow,
                "capacity": cap,
                "utilization": util,
                "active": self.active[i],
                "failed": not self.active[i]
            })

        buses_view = []
        for b in self.topology.buses:
            b_id = b["id"]
            coords = self.node_coords.get(b_id, (500.0, 350.0))
            buses_view.append({
                "id": b_id,
                "x": coords[0],
                "y": coords[1],
                "load": round(b["load"], 3),
                "isolated": b_id in self.isolated_nodes
            })

        return {
            "status": self.status,
            "step": self.step_num,
            "sample_idx": self.sample_idx,
            "source_label": self.source_label,
            "active_lines": sum(1 for a in self.active if a),
            "tripped_count": len(self.failed_history),
            "lost_load_mw": round(self.lost_load, 1),
            "dns_percent": dns_percent,
            "buses": buses_view,
            "branches": branches_view,
            "logs": self.logs[-12:]  # Останні 12 повідомлень
        }
