# MIMD-моделювання каскадних аварій IEEE-118

Проєкт моделює стійкість енергосистеми IEEE-118 методом Монте-Карло. Модель містить **118 вузлів і 186 ліній**. Один trial є незалежним сценарієм аварії, тому trials розподіляються між процесами через `multiprocessing.Pool`, Ray та Kubernetes.

## Структура репозиторію

```text
my-grid/
├── README.md
├── Datasets/
│   └── dataset_cascades/ieee118/ieee118/raw/
│       ├── blist.mat       # топологія ліній
│       ├── Bf.mat          # навантаження вузлів
│       └── Ef.mat          # потоки та пропускні здатності ліній
├── source/
│   ├── grid-mimd/          # Етап 1: Локальний MIMD (multiprocessing)
│   ├── grid-ray/           # Етап 2: Розподілений Ray Grid
│   ├── grid-docker/        # Етап 3: Docker + Web UI
│   └── grid-k8s/           # Етап 4: Kubernetes Job & Deployment
├── benchmark_results_mimd_grid.json
├── benchmark_k8s.json
├── speedup.png
└── docs/work/PLAN.md
```

## Як запустити

### Етап 1: Локальний MIMD (Bare-Metal)
З кореня репозиторію:
```powershell
python source/grid-mimd/app.py --headless --trials 100000 --workers 1,2,4,8,12 --k 1 --sample 69411 --out benchmark_results_mimd_grid.json
```

### Етап 2: Ray Grid
```bash
# Термінал 1 (Head)
ray start --head --port=6379
# Термінал 2 (Worker)
ray start --address=127.0.0.1:6379 --num-cpus=4
# Запуск
python source/grid-ray/app_ray.py load --trials 100000 --k 1 --sample 69411
```

### Етап 3: Docker
```bash
cd source/grid-docker
docker compose up --build
# Відкрити http://localhost:8080
```

### Етап 4: Kubernetes (Minikube)
```bash
minikube start --driver=docker --cpus=2 --memory=3072
minikube image load grid-web:latest
cd source/grid-k8s
kubectl apply -f deployment.yaml
kubectl apply -f service.yaml
kubectl apply -f grid-job.yaml
# Експорт результатів
kubectl logs -l workload=grid-contingency-calc --tail=200 > benchmark_k8s.json
```

## Реалізований алгоритм

1. `load_powergraph_cascades()` читає `.mat` файли, `build_topology()` формує граф.
2. `run_trial()` виконує зважений N-k шок (ймовірність пропорційна `(flow / capacity)^2`).
3. Потік вимкненої лінії розподіляється між сусідніми лініями пропорційно вільному резерву.
4. Лінії з `flow > capacity` вимикаються захистом (каскад).
5. `Pool.map` / `ray.remote` / K8s Job розподіляють незалежні trials.

Blackout фіксується, якщо DNS ≥ 5% або вимкнено ≥ 18 ліній.

---

## Фінальний бенчмарк: Bare-Metal vs Ray vs Docker vs Kubernetes

| Критерій | Bare-Metal (MIMD) | Ray Grid | Docker | Kubernetes Job |
| :--- | :--- | :--- | :--- | :--- |
| **Ізоляція** | Спільна пам'ять | Процеси (емуляція на 1 ПК) | cgroups v2 | Поди (cgroups v2 + netns) |
| **Паралелізм** | Pool(8) | 16 CPU (12 + 4) | 4 workers | parallelism: 4, completions: 8 |
| **Холодний старт** | ~0.1 с | ~3–5 с | ~1–2 с | ~5–8 с |
| **Відмовостійкість** | Відсутня | Ретрай окремих задач | restart: always | Kubelet + Probes + Backoff |
| **Час (100k trials)** | **10.64 с** | 17.93 с | 20.25 с | ~20.0 с |
| **Throughput** | **9 401 tr/s** | 5 577 tr/s | 4 938 tr/s | 5 000 tr/s |

### Висновки
1. **Bare-Metal (MIMD)** — найшвидший (9 401 tr/s), оскільки відсутні накладні витрати на віртуалізацію та мережу.
2. **Ray Grid** — 5 577 tr/s. Добре масштабується, але має overhead на міжпроцесний обмін (IPC).
3. **Docker** — 4 938 tr/s. ~13% overhead порівняно з bare-metal через обмеження CPU (`cpus: 2.0`).
4. **Kubernetes Job** — ~5 000 tr/s. Забезпечує найкращу **відмовостійкість** (Kubelet, Probes, Backoff), але має найдовший холодний старт (~5–8 с).