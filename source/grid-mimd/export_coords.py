#!/usr/bin/env python3
"""Експорт координат вузлів IEEE-118 через kamada_kawai_layout."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from engine import GridTopology


def export_coords(out_file: Path = Path("ieee118_coords.json")):
    import networkx as nx
    
    topo = GridTopology.build_default_ieee118()
    G = nx.Graph()
    for br in topo.branches:
        G.add_edge(br["from_bus"], br["to_bus"])
    
    # kamada_kawai — як у visualize_grid_graph.py
    pos = nx.kamada_kawai_layout(G)
    
    # Масштабуємо координати з [-1, 1] у пікселі Canvas 1000x720
    xs = [p[0] for p in pos.values()]
    ys = [p[1] for p in pos.values()]
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)
    
    coords = {}
    for bus_id, (x, y) in pos.items():
        # Нормалізація у [0, 1] → [padding, 1-padding]
        nx_x = (x - x_min) / (x_max - x_min)
        nx_y = (y - y_min) / (y_max - y_min)
        # Canvas 1000x720, padding 60px
        coords[bus_id] = (
            round(60 + nx_x * 880, 1),
            round(60 + nx_y * 600, 1)  # інверсія Y (у canvas Y росте вниз)
        )
    
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(coords, f, indent=2)
    print(f"Збережено {len(coords)} координат у {out_file}")


if __name__ == "__main__":
    export_coords()