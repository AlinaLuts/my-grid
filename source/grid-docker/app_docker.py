#!/usr/bin/env python3
"""Dockerized grid simulator with REST API."""
import json
import sys
from pathlib import Path
from http.server import BaseHTTPRequestHandler, HTTPServer

from engine import (
    GridTopology,
    InteractiveGridSession,
    run_trial,
)

from multiprocessing import Pool
import time

HTML_PAGE = """<!DOCTYPE html>
<html lang="uk">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>IEEE-118 Power Grid | Симулятор каскадних аварій</title>
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&family=Outfit:wght@400;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-base: #090d16;
            --bg-card: rgba(18, 24, 38, 0.85);
            --border: #1e293b;
            --accent: #38bdf8;
            --success: #10b981;
            --warning: #f59e0b;
            --danger: #ef4444;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            background-color: var(--bg-base);
            color: var(--text-main);
            font-family: 'Outfit', sans-serif;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            overflow-x: hidden;
        }
        header {
            background: rgba(15, 23, 42, 0.95);
            border-bottom: 1px solid var(--border);
            padding: 12px 24px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            backdrop-filter: blur(12px);
        }
        .logo {
            display: flex;
            align-items: center;
            gap: 12px;
            font-size: 1.25rem;
            font-weight: 700;
            color: var(--accent);
        }
        .logo span { color: var(--text-muted); font-size: 0.85rem; font-weight: 400; }
        .header-stats {
            display: flex;
            gap: 16px;
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.85rem;
        }
        .stat-badge {
            background: rgba(30, 41, 59, 0.6);
            padding: 6px 12px;
            border-radius: 8px;
            border: 1px solid var(--border);
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .stat-badge b { color: var(--accent); }
        .status-badge {
            padding: 6px 14px;
            border-radius: 8px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            font-size: 0.8rem;
        }
        .status-NORMAL { background: rgba(16, 185, 129, 0.15); color: var(--success); border: 1px solid var(--success); }
        .status-SHOCK { background: rgba(245, 158, 11, 0.15); color: var(--warning); border: 1px solid var(--warning); }
        .status-CASCADING { background: rgba(239, 68, 68, 0.2); color: var(--danger); border: 1px solid var(--danger); animation: pulse 1s infinite; }
        .status-STABLE { background: rgba(16, 185, 129, 0.2); color: var(--success); border: 1px solid var(--success); }
        .status-BLACKOUT { background: rgba(220, 38, 38, 0.35); color: #fca5a5; border: 1px solid var(--danger); animation: pulse 0.5s infinite; }

        @keyframes pulse {
            0%, 100% { opacity: 1; transform: scale(1); }
            50% { opacity: 0.75; transform: scale(0.98); }
        }

        .main-container {
            display: grid;
            grid-template-columns: 1fr 360px;
            gap: 16px;
            padding: 16px;
            flex: 1;
        }
        .viewport-card {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 12px;
            display: flex;
            flex-direction: column;
            position: relative;
            overflow: hidden;
        }
        .toolbar {
            background: rgba(15, 23, 42, 0.8);
            border-bottom: 1px solid var(--border);
            padding: 10px 16px;
            display: flex;
            align-items: center;
            gap: 10px;
            flex-wrap: wrap;
        }
        .btn {
            background: #0284c7;
            color: #fff;
            border: none;
            padding: 8px 14px;
            border-radius: 6px;
            font-size: 0.85rem;
            font-weight: 600;
            cursor: pointer;
            display: flex;
            align-items: center;
            gap: 6px;
            transition: all 0.2s;
        }
        .btn:hover { background: #0369a1; transform: translateY(-1px); }
        .btn-danger { background: #dc2626; }
        .btn-danger:hover { background: #b91c1c; }
        .btn-warning { background: #d97706; }
        .btn-warning:hover { background: #b45309; }
        .btn-reset { background: #475569; }
        .btn-reset:hover { background: #334155; }
        .input-group {
            display: flex;
            align-items: center;
            gap: 6px;
            font-size: 0.85rem;
            color: var(--text-muted);
        }
        .input-group input, .input-group select {
            background: #0f172a;
            border: 1px solid var(--border);
            color: #fff;
            padding: 6px 8px;
            border-radius: 6px;
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.85rem;
        }
        canvas {
            width: 100%;
            height: 100%;
            display: block;
            background: radial-gradient(circle at center, #0d1527 0%, #080c16 100%);
            cursor: crosshair;
        }

        .side-panel {
            display: flex;
            flex-direction: column;
            gap: 16px;
        }
        .panel-card {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 14px 16px;
            display: flex;
            flex-direction: column;
            gap: 10px;
        }
        .panel-card h3 {
            font-size: 0.95rem;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            color: var(--accent);
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .log-box {
            background: #090d16;
            border: 1px solid #1e293b;
            border-radius: 8px;
            padding: 10px;
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.78rem;
            height: 280px;
            overflow-y: auto;
            display: flex;
            flex-direction: column;
            gap: 6px;
        }
        .log-entry {
            line-height: 1.4;
            padding: 2px 4px;
            border-radius: 4px;
        }
        .log-entry.shock { color: #fbbf24; background: rgba(245, 158, 11, 0.1); }
        .log-entry.trip { color: #f87171; background: rgba(239, 68, 68, 0.1); }
        .log-entry.stable { color: #34d399; background: rgba(16, 185, 129, 0.1); }
        .log-entry.blackout { color: #fca5a5; background: rgba(220, 38, 38, 0.25); font-weight: 700; }

        .legend {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 8px;
            font-size: 0.75rem;
            font-family: 'JetBrains Mono', monospace;
        }
        .legend-item { display: flex; align-items: center; gap: 8px; }
        .legend-color { width: 14px; height: 14px; border-radius: 3px; }

        #tooltip {
            position: absolute;
            background: rgba(15, 23, 42, 0.95);
            border: 1px solid var(--accent);
            border-radius: 6px;
            padding: 8px 12px;
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.75rem;
            pointer-events: none;
            display: none;
            box-shadow: 0 4px 14px rgba(0,0,0,0.5);
            z-index: 100;
        }
    </style>
</head>
<body>
    <header>
        <div class="logo">
            ⚡ IEEE-118 СИМУЛЯТОР
            <span>MIMD PC • Етап 1 (118 вузлів, 186 ліній)</span>
        </div>
        <div class="header-stats">
            <div class="stat-badge">Сценарій: <b id="disp-sample">87554</b></div>
            <div class="stat-badge">Активні лінії: <b id="disp-active">186 / 186</b></div>
            <div class="stat-badge">Втрата DNS: <b id="disp-dns">0.0%</b></div>
            <div id="status-tag" class="status-badge status-NORMAL">НОРМА</div>
        </div>
    </header>

    <div class="main-container">
        <div class="viewport-card">
            <div class="toolbar">
                <div class="input-group">
                    <label>Сценарій s:</label>
                    <input type="number" id="inp-sample" value="87554" style="width: 85px;">
                    <button class="btn btn-reset" onclick="applySample()">Змінити</button>
                </div>
                <div class="input-group" style="margin-left: 12px;">
                    <label>Шок k:</label>
                    <select id="inp-k">
                        <option value="1">k = 1 (N-1 аварія)</option>
                        <option value="2">k = 2 (N-2 подвійна)</option>
                        <option value="3">k = 3 (стрес-тест)</option>
                    </select>
                </div>
                <button class="btn btn-danger" onclick="triggerShock()">⚡ Вибити N-k</button>
                <button class="btn" onclick="stepCascade()">➡️ Крок каскаду</button>
                <button class="btn btn-warning" id="btn-play" onclick="togglePlay()">▶ Авто-гра</button>
                <button class="btn btn-reset" onclick="resetGrid()">🔄 Скинути</button>
                <button class="btn" id="btn-stress" onclick="toggleStress()" style="background:#7c3aed;" title="Переключити між нормальною (запас 35-65%) та перевантаженою (запас 5-15%) мережею">перевантажена мережа</button>
            </div>
            <canvas id="grid-canvas" width="1000" height="720"></canvas>
            <div id="tooltip"></div>
        </div>

        <div class="side-panel">
            <div class="panel-card">
                <h3>📊 Стан каскаду</h3>
                <div style="display: flex; flex-direction: column; gap: 8px; font-size: 0.85rem;">
                    <div style="display: flex; justify-content: space-between;">
                        <span style="color: var(--text-muted)">Крок хвилі каскаду:</span>
                        <b id="disp-step" style="font-family: 'JetBrains Mono';">0</b>
                    </div>
                    <div style="display: flex; justify-content: space-between;">
                        <span style="color: var(--text-muted)">Відключено захистом:</span>
                        <b id="disp-trips" style="color: var(--danger); font-family: 'JetBrains Mono';">0 ліній</b>
                    </div>
                    <div style="display: flex; justify-content: space-between;">
                        <span style="color: var(--text-muted)">Знеструмлено навантаження:</span>
                        <b id="disp-lost" style="color: var(--warning); font-family: 'JetBrains Mono';">0.0 МВт</b>
                    </div>
                </div>
            </div>

            <div class="panel-card" style="flex: 1;">
                <h3>📜 Журнал подій релейного захисту</h3>
                <div class="log-box" id="log-box"></div>
            </div>

            <div class="panel-card">
                <h3>🎨 Легенда навантаження ліній</h3>
                <div class="legend">
    <div class="legend-item"><div class="legend-color" style="background: #ef4444;"></div>&gt;90% — критично</div>
    <div class="legend-item"><div class="legend-color" style="background: #f59e0b;"></div>50–90% — напружено</div>
    <div class="legend-item"><div class="legend-color" style="background: #10b981;"></div>25–50% — помірно</div>
    <div class="legend-item"><div class="legend-color" style="background: #38bdf8;"></div>10–25% — норма</div>
    <div class="legend-item"><div class="legend-color" style="background: #6366f1;"></div>2–10% — слабкий потік</div>
    <div class="legend-item"><div class="legend-color" style="background: #4975AD;"></div>&lt;2% — майже нуль</div>
    <div class="legend-item"><div class="legend-color" style="background: #475569; border: 1px dashed #ef4444;"></div>Відключена</div>
    <div class="legend-item"><div class="legend-color" style="background: #a855f7; border-radius: 50%;"></div>Вузол</div>
</div>
            </div>
        </div>
    </div>

    <script>
        let currentState = null;
        let playTimer = null;
        const canvas = document.getElementById('grid-canvas');
        const ctx = canvas.getContext('2d');
        const tooltip = document.getElementById('tooltip');

        async function fetchState() {
            const res = await fetch('/api/state');
            currentState = await res.json();
            updateUI();
            render();
        }

        async function triggerShock() {
            const k = document.getElementById('inp-k').value;
            const res = await fetch('/api/shock', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({k: parseInt(k)})
            });
            currentState = await res.json();
            updateUI();
            render();
        }

        async function stepCascade() {
            const res = await fetch('/api/step', {method: 'POST'});
            currentState = await res.json();
            updateUI();
            render();
            if (currentState.status === 'STABLE' || currentState.status === 'BLACKOUT') {
                stopPlay();
            }
        }

        function togglePlay() {
            if (playTimer) {
                stopPlay();
            } else {
                document.getElementById('btn-play').innerText = '⏸ Пауза';
                document.getElementById('btn-play').style.background = '#ea580c';
                playTimer = setInterval(stepCascade, 450);
            }
        }

        function stopPlay() {
            if (playTimer) {
                clearInterval(playTimer);
                playTimer = null;
                document.getElementById('btn-play').innerText = '▶ Авто-гра';
                document.getElementById('btn-play').style.background = '#d97706';
            }
        }

        async function resetGrid() {
            stopPlay();
            const res = await fetch('/api/reset', {method: 'POST'});
            currentState = await res.json();
            updateUI();
            render();
        }

        let isStressMode = false;

        async function applySample() {
            stopPlay();
            const sample = document.getElementById('inp-sample').value;
            const res = await fetch('/api/reset', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({sample: parseInt(sample), stress: isStressMode})
            });
            currentState = await res.json();
            document.getElementById('disp-sample').innerText = sample;
            updateUI();
            render();
        }

        async function toggleStress() {
            stopPlay();
            isStressMode = !isStressMode;
            const btn = document.getElementById('btn-stress');
            if (isStressMode) {
                btn.innerText = 'нормальна мережа';
                btn.style.background = '#3CB371';
                btn.title = 'Зараз: перевантажена мережа (запас 5-15%). Клікни щоб повернути норму.';
            } else {
                btn.innerText = 'навантажена мережа';
                btn.style.background = '#5c0c6e';
                btn.title = 'Зараз: нормальна мережа (запас 35-65%). Клікни для стрес-режиму.';
            }
            const res = await fetch('/api/stress', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({stress: isStressMode})
            });
            currentState = await res.json();
            updateUI();
            render();
        }

        function updateUI() {
            if (!currentState) return;
            document.getElementById('disp-active').innerText = `${currentState.active_lines} / 186`;
            document.getElementById('disp-dns').innerText = `${currentState.dns_percent}%`;
            document.getElementById('disp-step').innerText = currentState.step;
            document.getElementById('disp-trips').innerText = `${currentState.tripped_count} ліній`;
            document.getElementById('disp-lost').innerText = `${currentState.lost_load_mw} МВт`;
            // Синхронізація номера сценарію з API (виправляє hardcode 87554)
            if (currentState.sample_idx !== undefined) {
                document.getElementById('disp-sample').innerText = currentState.sample_idx;
                document.getElementById('inp-sample').value = currentState.sample_idx;
            }

            const tag = document.getElementById('status-tag');
            tag.className = `status-badge status-${currentState.status}`;
            const titles = {
                'NORMAL': 'НОРМА',
                'SHOCK': 'N-k ШОК',
                'CASCADING': 'КАСКАДНИЙ ОБВАЛ',
                'STABLE': 'СТАБІЛІЗОВАНО',
                'BLACKOUT': 'БЛЕКАУТ'
            };
            tag.innerText = titles[currentState.status] || currentState.status;

            // Logs
            const logBox = document.getElementById('log-box');
            logBox.innerHTML = '';
            currentState.logs.forEach(l => {
                const el = document.createElement('div');
                el.className = 'log-entry';
                if (l.includes('Шок')) el.className += ' shock';
                else if (l.includes('Перевантаження') || l.includes('Ізоляція')) el.className += ' trip';
                else if (l.includes('Стабілізація') || l.includes('стабілізувалася')) el.className += ' stable';
                else if (l.includes('БЛЕКАУТ')) el.className += ' blackout';
                el.innerText = l;
                logBox.appendChild(el);
            });
            logBox.scrollTop = logBox.scrollHeight;
        }

        function render() {
            if (!currentState) return;
            ctx.clearRect(0, 0, canvas.width, canvas.height);

            const buses = {};
            currentState.buses.forEach(b => { buses[b.id] = b; });

            // 1. Draw branches
            currentState.branches.forEach(br => {
                const u = buses[br.u];
                const v = buses[br.v];
                if (!u || !v) return;

                ctx.beginPath();
                ctx.moveTo(u.x, u.y);
                ctx.lineTo(v.x, v.y);

                if (!br.active) {
                    ctx.setLineDash([4, 4]);
                    ctx.strokeStyle = '#475569';
                    ctx.lineWidth = 1.2;
                } else {
                    ctx.setLineDash([]);
                    const util = br.utilization;
                    if (util > 90) {
                        ctx.strokeStyle = '#ef4444';   // червоний — критично
                        ctx.lineWidth = 3.5;
                    } else if (util > 50) {
                        ctx.strokeStyle = '#f59e0b';   // оранжевий — напружено
                        ctx.lineWidth = 2.6;
                    } else if (util > 25) {
                        ctx.strokeStyle = '#10b981';   // зелений — помірно
                        ctx.lineWidth = 2.0;
                    } else if (util > 10) {
                        ctx.strokeStyle = '#38bdf8';   // синій — норма
                        ctx.lineWidth = 1.5;
                    } else if (util > 2) {
                        ctx.strokeStyle = '#6366f1';   // індиго — слабкий
                        ctx.lineWidth = 1.1;
                    } else {
                        ctx.strokeStyle = '#4975AD';   // темно-сірий — майже нуль
                        ctx.lineWidth = 0.8;
                    }
                }
                ctx.stroke();
                // Підпис тільки для помітних ліній
                if (br.active && br.utilization > 20) {
                    const mx = (u.x + v.x) / 2;
                    const my = (u.y + v.y) / 2;
                    ctx.fillStyle = br.utilization > 60 ? '#fca5a5' : '#94a3b8';
                    ctx.font = 'bold 8px monospace';
                    ctx.fillText(`${br.utilization}%`, mx + 2, my - 2);
                }
            });

            ctx.setLineDash([]);

            // 2. Draw nodes (buses)
            currentState.buses.forEach(b => {
                ctx.beginPath();
                // Розмір вузла залежно від навантаження
const size = b.isolated ? 6 : Math.max(3, Math.min(8, 3 + Math.abs(b.load) * 2));
ctx.arc(b.x, b.y, size, 0, Math.PI * 2);
                if (b.isolated) {
                    ctx.fillStyle = '#ef4444';
                    ctx.strokeStyle = '#fca5a5';
                    ctx.lineWidth = 2;
                    ctx.stroke();
                } else {
                    ctx.fillStyle = b.load > 40 ? '#c084fc' : '#a855f7';
                }
                ctx.fill();

                // ID label
                ctx.fillStyle = '#64748b';
                ctx.font = '8px monospace';
                ctx.fillText(b.id, b.x + 5, b.y - 3);
            });
        }

        // Mouse hover interaction for tooltip
        canvas.addEventListener('mousemove', (e) => {
            if (!currentState) return;
            const rect = canvas.getBoundingClientRect();
            const mx = (e.clientX - rect.left) * (canvas.width / rect.width);
            const my = (e.clientY - rect.top) * (canvas.height / rect.height);

            // Check hovered node
            for (const b of currentState.buses) {
                const dist = Math.hypot(b.x - mx, b.y - my);
                if (dist < 10) {
                    tooltip.style.display = 'block';
                    tooltip.style.left = (e.clientX + 14) + 'px';
                    tooltip.style.top = (e.clientY + 14) + 'px';
                    const loadStr = b.load === 0 ? '0 (генератор/баланс)' : b.load.toFixed(3);
const statusStr = b.isolated ? '⚠️ Знеструмлено' : '✅ Активна';
tooltip.innerHTML = `<b>Підстанція #${b.id}</b><br>P_net: ${loadStr} МВт<br>Статус: ${statusStr}`;
                    return;
                }
            }

            tooltip.style.display = 'none';
        });

        fetchState();
    </script>
</body>
</html>
"""
def _run_chunk(topology_dict, k_fault, base_seed, chunk_size=25000):
    """Один чанк trials для Pool."""
    blackouts = 0
    for i in range(chunk_size):
        res = run_trial(topology_dict, k_fault=k_fault, seed=base_seed + i)
        if res["blackout"]:
            blackouts += 1
    return {"blackouts": blackouts, "trials": chunk_size}

GLOBAL_SESSION = None
_STRESS_MODE = False
_CURRENT_SAMPLE = 69411


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        global GLOBAL_SESSION
        if self.path in ("/", "/index.html"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode("utf-8"))
        elif self.path == "/api/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')
        elif self.path == "/api/state":
            if GLOBAL_SESSION is None:
                topo = GridTopology.from_dataset("/app/Datasets", sample_idx=_CURRENT_SAMPLE)
                GLOBAL_SESSION = InteractiveGridSession(topo)
            state = GLOBAL_SESSION.get_state()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(state).encode("utf-8"))
        else:
            self.send_error(404)

    def do_POST(self):
        global GLOBAL_SESSION, _STRESS_MODE, _CURRENT_SAMPLE

        if GLOBAL_SESSION is None:
            topo = GridTopology.build_default_ieee118()
            GLOBAL_SESSION = InteractiveGridSession(topo)

        if self.path == "/api/shock":
            k = 1
            GLOBAL_SESSION.trigger_shock(k_fault=k)
            state = GLOBAL_SESSION.get_state()
            self._send_json(state)
        elif self.path == "/api/step":
            state = GLOBAL_SESSION.step_cascade()
            self._send_json(state)
        elif self.path == "/api/reset":
            GLOBAL_SESSION.reset()
            state = GLOBAL_SESSION.get_state()
            self._send_json(state)
        elif self.path == "/api/stress":
            _STRESS_MODE = not _STRESS_MODE
            if _STRESS_MODE:
                topo = GridTopology.build_stressed_ieee118()
            else:
                topo = GridTopology.build_default_ieee118()
            GLOBAL_SESSION = InteractiveGridSession(topo, sample_idx=_CURRENT_SAMPLE)
            state = GLOBAL_SESSION.get_state()
            self._send_json(state)
        elif self.path == "/api/batch":
            topo = GridTopology.build_default_ieee118().to_dict()
            n_trials = 100000
            n_workers = 4
            chunk = n_trials // n_workers
            args = [(topo, 1, w * chunk) for w in range(n_workers)]
            start = time.perf_counter()
            with Pool(n_workers) as pool:
                chunk_results = pool.starmap(_run_chunk, args)
            elapsed = time.perf_counter() - start
            blackouts = sum(r["blackouts"] for r in chunk_results)
            self._send_json({
                "trials": n_trials,
                "blackouts": blackouts,
                "workers": n_workers,
                "elapsed_sec": round(elapsed, 4),
                "throughput_trials_per_sec": round(n_trials / elapsed, 2),
            })
        else:
            self.send_error(404)

    def _send_json(self, data):
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", 8080), Handler)
    print("Grid simulator with UI on port 8080")
    server.serve_forever()