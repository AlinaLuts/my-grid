#!/usr/bin/env python3
"""
CLI, Benchmark Runner & Interactive Web UI for IEEE-118 Power Grid Cascade Simulation.
Course: Cloud and Grid Systems
Stage 1: MIMD PC Benchmark & Interactive Real-Time Cascade Visualizer.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from multiprocessing import cpu_count
from pathlib import Path
from typing import List

# Додаємо поточну директорію для імпорту engine
sys.path.insert(0, str(Path(__file__).resolve().parent))
from engine import (
    GridSimulationEngine,
    GridTopology,
    InteractiveGridSession,
    compute_node_coordinates,
)

# Прапорець поточного режиму мережі (normal / stressed)
_STRESS_MODE: bool = False

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

# Глобальна сесія та стан для веб-сервера
GLOBAL_SESSION: InteractiveGridSession | None = None
_CURRENT_SAMPLE: int = 87554
_DATA_PATH: Path = Path("Datasets")


class GridHandler(BaseHTTPRequestHandler):
    """Обробник HTTP запитів для інтерактивного веб-симулятора."""

    def log_message(self, format, *args):
        # Пригнічуємо спам стандартних логів HTTP
        return

    def do_GET(self):
        global GLOBAL_SESSION
        if self.path in ("/", "/index.html"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode("utf-8"))
        elif self.path == "/api/state":
            if GLOBAL_SESSION is None:
                topo = GridTopology.build_default_ieee118()
                GLOBAL_SESSION = InteractiveGridSession(topo)
            state = GLOBAL_SESSION.get_state()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(state).encode("utf-8"))
        else:
            self.send_error(404)

    def do_POST(self):
        global GLOBAL_SESSION, _STRESS_MODE, _CURRENT_SAMPLE, _DATA_PATH
        if GLOBAL_SESSION is None:
            topo = GridTopology.build_default_ieee118()
            GLOBAL_SESSION = InteractiveGridSession(topo,sample_idx=_CURRENT_SAMPLE, 
        source_label="dataset"
)

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else b"{}"
        data = json.loads(body.decode("utf-8")) if body else {}

        if self.path == "/api/shock":
            k = int(data.get("k", 1))
            line_id = data.get("line_id", None)
            GLOBAL_SESSION.trigger_shock(k_fault=k, line_id=line_id)
            state = GLOBAL_SESSION.get_state()
        elif self.path == "/api/step":
            state = GLOBAL_SESSION.step_cascade()
        elif self.path == "/api/reset":
            sample = data.get("sample", None)
            stress = data.get("stress", _STRESS_MODE)
            _STRESS_MODE = bool(stress)
            if sample is not None:
                sid = int(sample)
                topo = GridTopology.from_dataset(_DATA_PATH, sample_idx=sid)
                GLOBAL_SESSION = InteractiveGridSession(topo, sample_idx=sid, source_label="dataset")
                _CURRENT_SAMPLE = sid
                _STRESS_MODE = False 
            else:
                # Просто скидає стан до початкових даних датасету
                GLOBAL_SESSION.reset()
            state = GLOBAL_SESSION.get_state()
        elif self.path == "/api/stress":
            _STRESS_MODE = bool(data.get("stress", False))
            if _STRESS_MODE:
                topo = GridTopology.build_stressed_ieee118()
                GLOBAL_SESSION = InteractiveGridSession(topo, sample_idx=_CURRENT_SAMPLE, source_label="stressed")
            else:
                topo = GridTopology.from_dataset(_DATA_PATH, sample_idx=_CURRENT_SAMPLE)
                GLOBAL_SESSION = InteractiveGridSession(topo, sample_idx=_CURRENT_SAMPLE, source_label="dataset")
            state = GLOBAL_SESSION.get_state()
        elif self.path == "/api/restore":
            # Повернення до оригінальних даних датасету для поточного sample
            _STRESS_MODE = False
            topo = GridTopology.from_dataset(_DATA_PATH, sample_idx=_CURRENT_SAMPLE)
            GLOBAL_SESSION = InteractiveGridSession(topo, sample_idx=_CURRENT_SAMPLE, source_label="dataset")
            state = GLOBAL_SESSION.get_state()
        else:
            self.send_error(404)
            return

        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(state).encode("utf-8"))


def start_web_server(port: int = 8080, sample_idx: int = 87554, data_path: Path = Path("Datasets")):
    """Запускає вбудований легковагий веб-сервер для візуалізації каскадів."""
    global GLOBAL_SESSION, _CURRENT_SAMPLE, _DATA_PATH
    _CURRENT_SAMPLE = sample_idx
    _DATA_PATH = data_path
    print(f"Ініціалізація топології зі зрізом s={sample_idx}...")
    topo = GridTopology.from_dataset(data_path, sample_idx=sample_idx)
    GLOBAL_SESSION = InteractiveGridSession(topo, sample_idx=sample_idx, source_label="dataset")

    server = HTTPServer(("0.0.0.0", port), GridHandler)
    print("=" * 70)
    print(f"🚀 ВЕБ-СИМУЛЯТОР УСПІШНО ЗАПУЩЕНО!")
    print(f"👉 Відкрийте у браузері: http://localhost:{port}")
    print(f"   (Для зупинки сервера натисніть Ctrl+C)")
    print("=" * 70)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nСервер зупинено.")
        server.server_close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="MIMD PC Benchmark & Interactive Web Simulator for IEEE-118 Power Grid"
    )
    parser.add_argument(
        "--serve",
        action="store_true",
        help="Запустити інтерактивний веб-сервер візуалізації на http://localhost:8080"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Порт для веб-сервера (за замовчуванням: 8080)"
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
            # Один и тот же набор случайных сценариев для каждого числа воркеров.
            base_seed=100_000
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


def main() -> None:
    args = parse_args()

    # Якщо користувач запустив інтерактивний сервер
    if args.serve:
        start_web_server(port=args.port, sample_idx=args.sample, data_path=args.data)
        return

    # Валідація параметрів CLI
    if not (1 <= args.k <= 5):
        print(f"Помилка: параметр k повинен бути в межах від 1 до 5 (передано: {args.k}).", file=sys.stderr)
        sys.exit(1)

    if args.trials <= 0:
        print(f"Помилка: параметр --trials повинен бути додатним числом (передано: {args.trials}).", file=sys.stderr)
        sys.exit(1)

    if args.sample < 0:
        print(f"Помилка: параметр --sample не може бути від'ємним (передано: {args.sample}).", file=sys.stderr)
        sys.exit(1)

     # Список воркерів
    if args.workers:
        try:
            workers_list = sorted(list(set(int(x.strip()) for x in args.workers.split(","))))
            if any(w <= 0 for w in workers_list):
                raise ValueError("Кількість воркерів повинна бути > 0")
        except ValueError as err:
            print(f"Помилка формату --workers ({err}). Приклад: --workers 1,2,4", file=sys.stderr)
            sys.exit(1)
        
        # Перевірка на перевищення ядер
        max_cpus = cpu_count()
        too_many = [w for w in workers_list if w > max_cpus]
        if too_many:
            print(f"Помилка: воркери {too_many} перевищують кількість ядер ({max_cpus}).", file=sys.stderr)
            print(f"Рекомендовано: --workers 1,2,4,...,{max_cpus}", file=sys.stderr)
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
