#!/usr/bin/env python3
"""Generate the gold-on-navy architecture diagrams in app/static/img/architecture/.

These are simple starting points - replace them with your own diagrams
(draw.io / Excalidraw export) in the admin panel (Media → upload) at any time.
"""
import random
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "app" / "static" / "img" / "architecture"
G, W, D = "#cfaa5d", "#ffffff", "#9aa6cf"


def head(h=320):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 480 {h}" '
            'font-family="Kode Mono, ui-monospace, monospace">'
            f'<defs><marker id="a" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" '
            f'markerHeight="6" orient="auto"><path d="M0 0L10 5L0 10z" fill="{G}"/></marker></defs>')


def box(x, y, w, h, label, sub=""):
    s = (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" fill="none" '
         f'stroke="{G}" stroke-width="2.5"/>')
    cy = y + h / 2 + (-3 if sub else 5)
    s += f'<text x="{x + w / 2}" y="{cy}" text-anchor="middle" font-size="13" font-weight="700" fill="{W}">{label}</text>'
    if sub:
        s += f'<text x="{x + w / 2}" y="{cy + 16}" text-anchor="middle" font-size="10" fill="{G}">{sub}</text>'
    return s


def ar(x1, y1, x2, y2):
    return (f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{G}" stroke-width="2.5" '
            'stroke-dasharray="3 6" stroke-linecap="round" marker-end="url(#a)"/>')


def label(x, y, t, size=11, anchor="start", color=G):
    return f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}" text-anchor="{anchor}">{t}</text>'


def area(x, y, w, h, t):
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="none" stroke="{D}" '
            f'stroke-width="1.5" stroke-dasharray="4 5"/>' + label(x + 10, y + 16, t, 10, color=D))


def jenkins():
    st = ["Checkout", "Terraform", "Ansible", "Build", "Test", "Docker image", "Push", "Deploy", "Verify"]
    s = head(330) + label(240, 22, "Jenkins pipeline · 9 stages", 13, "middle", W)
    pos = []
    for n in range(9):
        r = n // 3
        c = n % 3 if r % 2 == 0 else 2 - n % 3
        x, y = 24 + c * 156, 44 + r * 96
        pos.append((x, y))
        s += box(x, y, 120, 58, st[n], f"stage {n + 1}")
    for n in range(8):
        (x1, y1), (x2, y2) = pos[n], pos[n + 1]
        if y1 == y2:
            s += ar(x1 + 120, y1 + 29, x2 - 4, y2 + 29) if x2 > x1 else ar(x1, y1 + 29, x2 + 124, y2 + 29)
        else:
            s += ar(x1 + 60, y1 + 58, x2 + 60, y2 - 4)
    return s + label(24, 322, "Git push → infrastructure → configuration → image → deploy", 10, color=D) + "</svg>"


def aws():
    s = head(340) + box(180, 10, 120, 40, "Route 53", "DNS") + ar(240, 50, 240, 72)
    s += area(16, 76, 448, 250, "VPC")
    s += box(170, 92, 140, 40, "ALB", "load balancer") + ar(240, 132, 150, 166) + ar(240, 132, 330, 166)
    s += area(36, 152, 408, 82, "Auto Scaling group")
    s += box(90, 172, 120, 46, "EC2", "app") + box(270, 172, 120, 46, "EC2", "app")
    s += ar(150, 218, 175, 256) + ar(330, 218, 305, 256)
    s += box(110, 262, 120, 46, "RDS", "database") + box(270, 262, 120, 46, "S3", "assets")
    return s + label(458, 320, "IAM roles · Terraform modules", 10, "end", D) + "</svg>"


def optifaas():
    s = head() + box(20, 40, 130, 56, "Workload", "generator") + ar(150, 68, 190, 50) + ar(150, 68, 190, 106)
    s += box(195, 30, 120, 40, "AWS Lambda") + box(195, 86, 120, 40, "GCP Functions")
    s += ar(315, 50, 350, 78) + ar(315, 106, 350, 94)
    s += box(355, 58, 110, 56, "Metrics", "latency · cost") + ar(410, 114, 410, 168)
    s += box(330, 174, 140, 56, "Analysis", "scalability")
    s += box(20, 174, 130, 56, "Prototypes", "Java · Docker") + ar(150, 202, 190, 202)
    s += box(195, 174, 120, 56, "Benchmarks", "repeatable") + ar(315, 202, 326, 202)
    return s + label(240, 290, "Event-driven FaaS research · TU Berlin", 11, "middle", D) + "</svg>"


def heteng():
    rnd = random.Random(4)
    s = head() + label(240, 22, "Heterogeneous IoT clustering", 13, "middle", W)
    bs = (420, 250)
    for hx, hy in [(110, 110), (230, 200), (360, 100)]:
        for k in range(6):
            nx, ny = hx + rnd.randint(-60, 60), hy + rnd.randint(-50, 50)
            s += f'<line x1="{nx}" y1="{ny}" x2="{hx}" y2="{hy}" stroke="{D}" stroke-width="1"/>'
            s += f'<circle cx="{nx}" cy="{ny}" r="{4 if k % 2 else 6}" fill="none" stroke="{W}" stroke-width="1.5"/>'
        s += f'<circle cx="{hx}" cy="{hy}" r="13" fill="none" stroke="{G}" stroke-width="3"/>'
        s += ar(hx + 12, hy + 8, bs[0] - 34, bs[1] - 12)
    s += box(bs[0] - 32, bs[1] - 12, 72, 46, "Base", "station")
    return s + label(20, 306, "● cluster head   ○ sensor node", 10, color=D) + "</svg>"


def home():
    s = head() + area(16, 30, 180, 250, "Home")
    for n, (t, sub) in enumerate([("Sensors", "motion · door"), ("Camera", "video"), ("Gateway", "controller")]):
        s += box(40, 56 + n * 74, 132, 52, t, sub)
    s += ar(106, 108, 106, 126) + ar(106, 182, 106, 200)
    s += ar(172, 226, 240, 166) + box(245, 130, 110, 56, "Server", "events · alerts")
    s += ar(355, 158, 378, 158) + box(384, 130, 84, 56, "App", "remote")
    return s + "</svg>"


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for name, fn in [("jenkins-pipeline", jenkins), ("aws-multi-tier", aws), ("optifaas", optifaas),
                     ("heteng", heteng), ("home-monitoring", home)]:
        (OUT / f"{name}.svg").write_text(fn(), encoding="utf-8")
        print("wrote", name)
