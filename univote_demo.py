#!/usr/bin/env python3
"""
UniVote — локальный демо-сервер
Запуск: python3 app.py
Открыть: http://localhost:8000
"""

import json
import hashlib
import random
import time
import math
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from datetime import datetime, timedelta

# ─────────────────────────────────────────────────────────────────────────────
#  In-memory "database"
# ─────────────────────────────────────────────────────────────────────────────

OPTION_LABELS = ["А", "Б", "В", "Г", "Д", "Е"]

def make_nullifier(wallet, poll_id):
    raw = f"{wallet.lower()}:{poll_id}"
    return hashlib.sha256(raw.encode()).hexdigest()

def make_commitment(wallet):
    return hashlib.sha256(f"secret:{wallet.lower()}".encode()).hexdigest()

now = int(time.time())

# Test wallets (students)
WALLETS = [
    "0xA1b2C3d4E5f6A1b2C3d4E5f6A1b2C3d4E5f6A1b2",
    "0xB2c3D4e5F6a1B2c3D4e5F6a1B2c3D4e5F6a1B2c3",
    "0xC3d4E5f6A1b2C3d4E5f6A1b2C3d4E5f6A1b2C3d4",
    "0xD4e5F6a1B2c3D4e5F6a1B2c3D4e5F6a1B2c3D4e5",
    "0xE5f6A1b2C3d4E5f6A1b2C3d4E5f6A1b2C3d4E5f6",
    "0xF6a1B2c3D4e5F6a1B2c3D4e5F6a1B2c3D4e5F6a1",
    "0x1122334455667788990011223344556677889900AA",
    "0x2233445566778899001122334455667788990011BB",
]

STUDENTS = [
    {"wallet": w, "name": n, "group": g, "commitment": make_commitment(w), "whitelisted": True}
    for w, n, g in zip(WALLETS, [
        "Алексей Петров",    "Мария Сидорова",  "Дмитрий Козлов",
        "Анна Новикова",     "Иван Морозов",    "Екатерина Волкова",
        "Сергей Лебедев",   "Ольга Соколова",
    ], [
        "ИТ-31", "ИТ-31", "ИТ-32", "ИТ-32",
        "ИТ-33", "ИТ-33", "ИТ-34", "ИТ-34",
    ])
]

WHITELIST = {s["wallet"].lower(): s for s in STUDENTS}

# Demo polls with varied states
POLLS = {
    "1": {
        "id": "1",
        "title": "Выборы старосты группы ИТ-31",
        "description": "Ежегодные выборы старосты. Проголосуйте за одного из кандидатов.",
        "options": ["Алексей Петров", "Мария Сидорова", "Дмитрий Козлов"],
        "start_time": now - 3600,
        "end_time": now + 86400,
        "votes": [14, 9, 7],
        "nullifiers": set(),
        "state": "active",
        "category": "Студенческое самоуправление",
    },
    "2": {
        "id": "2",
        "title": "Лучший преподаватель семестра",
        "description": "Выберите преподавателя, который внёс наибольший вклад в ваше обучение в этом семестре.",
        "options": ["Проф. Иванов А.В.", "Доц. Смирнова К.Б.", "Ст. преп. Фёдоров П.Н.", "Проф. Белова Е.С."],
        "start_time": now - 7200,
        "end_time": now + 172800,
        "votes": [22, 18, 5, 11],
        "nullifiers": set(),
        "state": "active",
        "category": "Академическое качество",
    },
    "3": {
        "id": "3",
        "title": "Формат проведения зимней сессии",
        "description": "Определите предпочтительный формат сдачи экзаменов в зимнюю сессию.",
        "options": ["Очно в аудитории", "Онлайн через платформу", "Гибридный формат"],
        "start_time": now - 86400 * 3,
        "end_time": now - 3600,
        "votes": [45, 38, 62],
        "nullifiers": set(),
        "state": "ended",
        "category": "Учебный процесс",
    },
    "4": {
        "id": "4",
        "title": "Тема хакатона студенческого клуба",
        "description": "Выберите тему для ближайшего хакатона. Мероприятие пройдёт в конце февраля.",
        "options": ["AI и машинное обучение", "Blockchain и Web3", "Кибербезопасность", "IoT и умный город", "Геймдев"],
        "start_time": now + 86400 * 2,
        "end_time": now + 86400 * 7,
        "votes": [0, 0, 0, 0, 0],
        "nullifiers": set(),
        "state": "upcoming",
        "category": "Студенческий клуб",
    },
    "5": {
        "id": "5",
        "title": "Расписание спортивных секций",
        "description": "Когда вам удобнее посещать спортивные секции университета?",
        "options": ["Утро (8:00–10:00)", "День (13:00–15:00)", "Вечер (18:00–20:00)"],
        "start_time": now - 86400 * 10,
        "end_time": now - 86400 * 5,
        "votes": [31, 19, 58],
        "nullifiers": set(),
        "state": "ended",
        "category": "Студенческая жизнь",
    },
    "6": {
        "id": "6",
        "title": "Доработка учебного плана по программированию",
        "description": "Какой язык программирования вы хотели бы добавить в обязательную программу?",
        "options": ["Rust", "Go", "Kotlin", "Swift"],
        "start_time": now - 1800,
        "end_time": now + 43200,
        "votes": [8, 12, 6, 4],
        "nullifiers": set(),
        "state": "active",
        "category": "Учебный процесс",
    },
}

# Track who voted where
VOTE_LOG = []  # {"wallet", "poll_id", "option", "nullifier", "ts"}

# Current "connected" wallet (simulated)
SESSION = {"wallet": None}

# ─────────────────────────────────────────────────────────────────────────────
#  API logic
# ─────────────────────────────────────────────────────────────────────────────

def get_poll_status(poll):
    t = int(time.time())
    if poll["state"] == "ended" or t > poll["end_time"]:
        return "ended"
    if t < poll["start_time"]:
        return "upcoming"
    return "active"

def api_polls():
    return [
        {
            "id": p["id"],
            "title": p["title"],
            "category": p["category"],
            "status": get_poll_status(p),
            "total_votes": sum(p["votes"]),
            "options_count": len(p["options"]),
            "start_time": p["start_time"],
            "end_time": p["end_time"],
        }
        for p in POLLS.values()
    ]

def api_poll(poll_id):
    p = POLLS.get(poll_id)
    if not p:
        return None
    total = sum(p["votes"]) or 1
    wallet = SESSION["wallet"]
    already_voted = False
    if wallet:
        null = make_nullifier(wallet, poll_id)
        already_voted = null in p["nullifiers"]
    return {
        "id": p["id"],
        "title": p["title"],
        "description": p["description"],
        "category": p["category"],
        "status": get_poll_status(p),
        "options": p["options"],
        "votes": p["votes"],
        "percentages": [round(v / total * 100) for v in p["votes"]],
        "total_votes": sum(p["votes"]),
        "start_time": p["start_time"],
        "end_time": p["end_time"],
        "already_voted": already_voted,
    }

def api_cast_vote(poll_id, option_index, wallet):
    p = POLLS.get(poll_id)
    if not p:
        return {"ok": False, "error": "Голосование не найдено"}
    if get_poll_status(p) != "active":
        return {"ok": False, "error": "Голосование не активно"}
    if option_index < 0 or option_index >= len(p["options"]):
        return {"ok": False, "error": "Неверный вариант ответа"}

    student = WHITELIST.get(wallet.lower())
    if not student:
        return {"ok": False, "error": "Вы не в списке избирателей"}

    nullifier = make_nullifier(wallet, poll_id)
    if nullifier in p["nullifiers"]:
        return {"ok": False, "error": "Вы уже проголосовали в этом опросе"}

    # Simulate ZK proof generation delay
    time.sleep(0.5)

    p["nullifiers"].add(nullifier)
    p["votes"][option_index] += 1
    VOTE_LOG.append({
        "wallet": wallet[:8] + "…",
        "poll_id": poll_id,
        "option": p["options"][option_index],
        "nullifier": nullifier[:16] + "…",
        "ts": int(time.time()),
    })

    return {
        "ok": True,
        "nullifier": nullifier[:16] + "…",
        "tx_hash": "0x" + hashlib.sha256(f"{nullifier}{time.time()}".encode()).hexdigest(),
        "message": "Голос успешно засчитан!"
    }

def api_connect(wallet):
    student = WHITELIST.get(wallet.lower())
    if not student:
        return {"ok": False, "error": "Кошелёк не в вайтлисте"}
    SESSION["wallet"] = wallet
    return {"ok": True, "student": student}

def api_disconnect():
    SESSION["wallet"] = None
    return {"ok": True}

def api_stats():
    total_votes = sum(sum(p["votes"]) for p in POLLS.values())
    active = sum(1 for p in POLLS.values() if get_poll_status(p) == "active")
    return {
        "total_polls": len(POLLS),
        "active_polls": active,
        "total_votes": total_votes,
        "registered_students": len(STUDENTS),
        "recent_votes": VOTE_LOG[-5:][::-1],
    }

# ─────────────────────────────────────────────────────────────────────────────
#  HTML (single-file SPA)
# ─────────────────────────────────────────────────────────────────────────────

HTML = r"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>UniVote</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Onest:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
<style>
:root {
  --bg:        #0a0c10;
  --surface:   #111318;
  --surface2:  #181b22;
  --border:    rgba(255,255,255,.07);
  --border2:   rgba(255,255,255,.12);
  --blue:      #3b82f6;
  --blue-dim:  rgba(59,130,246,.12);
  --blue-glow: rgba(59,130,246,.25);
  --green:     #22c55e;
  --green-dim: rgba(34,197,94,.12);
  --amber:     #f59e0b;
  --amber-dim: rgba(245,158,11,.1);
  --red:       #ef4444;
  --red-dim:   rgba(239,68,68,.12);
  --text:      #e8eaf0;
  --text2:     #8b90a0;
  --text3:     #4b5060;
  --mono:      'JetBrains Mono', monospace;
}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
html{font-size:16px;scroll-behavior:smooth}
body{
  font-family:'Onest',sans-serif;
  background:var(--bg);
  color:var(--text);
  min-height:100vh;
  overflow-x:hidden;
}

/* noise texture overlay */
body::before{
  content:'';position:fixed;inset:0;
  background-image:url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)' opacity='0.03'/%3E%3C/svg%3E");
  pointer-events:none;z-index:0;opacity:.4;
}

/* ── Grid lines bg ── */
.grid-bg{
  position:fixed;inset:0;z-index:0;pointer-events:none;
  background-image:
    linear-gradient(rgba(59,130,246,.04) 1px, transparent 1px),
    linear-gradient(90deg, rgba(59,130,246,.04) 1px, transparent 1px);
  background-size:60px 60px;
}

/* ── Layout ── */
.app{position:relative;z-index:1;min-height:100vh;display:flex;flex-direction:column}

/* ── Header ── */
header{
  display:flex;align-items:center;gap:1.5rem;
  padding:0 2rem;height:64px;
  border-bottom:1px solid var(--border);
  background:rgba(10,12,16,.8);
  backdrop-filter:blur(12px);
  position:sticky;top:0;z-index:100;
}
.logo{
  font-size:1.25rem;font-weight:800;letter-spacing:-.02em;
  color:var(--text);display:flex;align-items:center;gap:.5rem;
  cursor:pointer;
}
.logo-dot{
  width:8px;height:8px;border-radius:50%;
  background:var(--blue);
  box-shadow:0 0 10px var(--blue);
  animation:pulse 2s ease-in-out infinite;
}
@keyframes pulse{0%,100%{box-shadow:0 0 10px var(--blue)}50%{box-shadow:0 0 20px var(--blue),0 0 40px var(--blue-dim)}}

nav{display:flex;gap:.25rem;flex:1}
.nav-btn{
  padding:.4rem .9rem;border-radius:6px;
  background:none;border:none;cursor:pointer;
  color:var(--text2);font-size:.875rem;font-weight:500;font-family:'Onest',sans-serif;
  transition:all .15s;
}
.nav-btn:hover{background:var(--surface2);color:var(--text)}
.nav-btn.active{background:var(--blue-dim);color:var(--blue)}

.wallet-section{display:flex;align-items:center;gap:.75rem;margin-left:auto}
.wallet-pill{
  display:flex;align-items:center;gap:.6rem;
  padding:.4rem .85rem;border-radius:8px;
  border:1px solid var(--border2);
  background:var(--surface2);
  font-size:.82rem;font-family:var(--mono);color:var(--text2);
  cursor:pointer;transition:all .15s;
}
.wallet-pill:hover{border-color:var(--blue-glow);color:var(--text)}
.wallet-indicator{width:7px;height:7px;border-radius:50%}
.wallet-indicator.connected{background:var(--green);box-shadow:0 0 6px var(--green)}
.wallet-indicator.disconnected{background:var(--text3)}

.connect-btn{
  padding:.45rem 1rem;border-radius:8px;
  background:var(--blue);border:none;
  color:white;font-size:.875rem;font-weight:600;font-family:'Onest',sans-serif;
  cursor:pointer;transition:all .15s;
}
.connect-btn:hover{background:#2563eb;box-shadow:0 0 20px var(--blue-glow)}

/* ── Main ── */
main{flex:1;max-width:1200px;width:100%;margin:0 auto;padding:2rem 2rem 4rem}

/* ── Page transitions ── */
.page{animation:fadeIn .25s ease}
@keyframes fadeIn{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}

/* ── Stats row ── */
.stats-row{
  display:grid;grid-template-columns:repeat(4,1fr);gap:1rem;margin-bottom:2rem;
}
.stat-card{
  background:var(--surface);border:1px solid var(--border);border-radius:12px;
  padding:1.1rem 1.2rem;position:relative;overflow:hidden;
}
.stat-card::before{
  content:'';position:absolute;inset:0;opacity:0;
  transition:opacity .2s;
  background:radial-gradient(ellipse at top left, var(--blue-dim), transparent 70%);
}
.stat-card:hover::before{opacity:1}
.stat-label{font-size:.75rem;color:var(--text3);text-transform:uppercase;letter-spacing:.06em;font-weight:600;margin-bottom:.4rem}
.stat-value{font-size:1.8rem;font-weight:800;letter-spacing:-.03em;color:var(--text)}
.stat-sub{font-size:.78rem;color:var(--text2);margin-top:.2rem}

/* ── Section header ── */
.section-hdr{display:flex;align-items:center;justify-content:space-between;margin-bottom:1.25rem}
.section-title{font-size:1.1rem;font-weight:700;letter-spacing:-.01em}
.section-tag{
  font-size:.72rem;font-weight:600;padding:.25rem .7rem;border-radius:999px;
  background:var(--surface2);border:1px solid var(--border2);color:var(--text2);
}

/* ── Poll cards ── */
.polls-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:1rem}

.poll-card{
  background:var(--surface);border:1px solid var(--border);border-radius:14px;
  padding:1.4rem;cursor:pointer;
  transition:all .2s;position:relative;overflow:hidden;
}
.poll-card::after{
  content:'';position:absolute;inset:0;
  background:radial-gradient(ellipse at top right, var(--blue-dim), transparent 60%);
  opacity:0;transition:opacity .25s;pointer-events:none;
}
.poll-card:hover{border-color:rgba(59,130,246,.3);transform:translateY(-2px);box-shadow:0 8px 30px rgba(0,0,0,.3)}
.poll-card:hover::after{opacity:1}

.poll-card-top{display:flex;align-items:flex-start;justify-content:space-between;gap:.5rem;margin-bottom:.75rem}
.poll-category{font-size:.72rem;color:var(--text3);font-weight:600;text-transform:uppercase;letter-spacing:.05em}
.status-badge{
  display:inline-flex;align-items:center;gap:.35rem;
  padding:.2rem .65rem;border-radius:999px;
  font-size:.72rem;font-weight:700;letter-spacing:.02em;white-space:nowrap;
  flex-shrink:0;
}
.badge-active{background:var(--green-dim);color:var(--green);border:1px solid rgba(34,197,94,.2)}
.badge-ended{background:var(--surface2);color:var(--text3);border:1px solid var(--border)}
.badge-upcoming{background:var(--amber-dim);color:var(--amber);border:1px solid rgba(245,158,11,.2)}
.badge-dot{width:5px;height:5px;border-radius:50%;background:currentColor}

.poll-title{font-size:1rem;font-weight:700;line-height:1.4;margin-bottom:.5rem;letter-spacing:-.01em}
.poll-meta{display:flex;gap:1.2rem;font-size:.8rem;color:var(--text2)}
.poll-meta span{display:flex;align-items:center;gap:.3rem}

.mini-bar{height:3px;border-radius:2px;background:var(--surface2);margin-top:1rem;display:flex;gap:2px;overflow:hidden}
.mini-bar-seg{height:100%;border-radius:2px;transition:width .4s ease}

/* ── Poll detail page ── */
.back-btn{
  display:inline-flex;align-items:center;gap:.5rem;
  color:var(--text2);font-size:.875rem;cursor:pointer;
  border:none;background:none;font-family:'Onest',sans-serif;
  margin-bottom:1.5rem;transition:color .15s;padding:0;
}
.back-btn:hover{color:var(--text)}

.poll-detail-grid{display:grid;grid-template-columns:1fr 380px;gap:1.5rem;align-items:start}
@media(max-width:800px){.poll-detail-grid{grid-template-columns:1fr}}

.detail-card{
  background:var(--surface);border:1px solid var(--border);border-radius:16px;padding:1.75rem;
}
.detail-title{font-size:1.6rem;font-weight:800;letter-spacing:-.03em;line-height:1.3;margin-bottom:.5rem}
.detail-desc{color:var(--text2);line-height:1.7;margin-bottom:1.5rem;font-size:.92rem}
.detail-meta{display:flex;flex-wrap:wrap;gap:.75rem;margin-bottom:1.5rem}
.meta-chip{
  display:flex;align-items:center;gap:.4rem;
  padding:.3rem .75rem;border-radius:8px;
  background:var(--surface2);border:1px solid var(--border);
  font-size:.8rem;color:var(--text2);
}

/* ── Results ── */
.results-title{font-size:.875rem;font-weight:700;color:var(--text2);text-transform:uppercase;letter-spacing:.06em;margin-bottom:1rem}
.result-row{margin-bottom:.9rem}
.result-top{display:flex;justify-content:space-between;align-items:center;margin-bottom:.35rem}
.result-label{font-size:.9rem;font-weight:500}
.result-nums{display:flex;align-items:center;gap:.6rem}
.result-pct{font-size:.85rem;font-weight:700;color:var(--blue)}
.result-count{font-size:.75rem;color:var(--text3);font-family:var(--mono)}
.bar-track{height:6px;border-radius:3px;background:var(--surface2);overflow:hidden}
.bar-fill{height:100%;border-radius:3px;background:linear-gradient(90deg,var(--blue),#60a5fa);transition:width .6s cubic-bezier(.4,0,.2,1)}
.bar-fill.winner{background:linear-gradient(90deg,var(--green),#4ade80)}

/* ── Vote panel ── */
.vote-card{
  background:var(--surface);border:1px solid var(--border);border-radius:16px;padding:1.5rem;
  position:sticky;top:80px;
}
.vote-card-title{font-size:1rem;font-weight:700;margin-bottom:1.25rem;display:flex;align-items:center;gap:.5rem}
.vote-card-title svg{color:var(--blue)}

.options-list{display:flex;flex-direction:column;gap:.5rem;margin-bottom:1.25rem}
.option-btn{
  display:flex;align-items:center;gap:.75rem;
  width:100%;padding:.8rem 1rem;
  background:var(--surface2);border:1.5px solid var(--border);border-radius:10px;
  cursor:pointer;text-align:left;font-family:'Onest',sans-serif;
  transition:all .15s;color:var(--text);font-size:.9rem;
}
.option-btn:hover:not(:disabled){border-color:rgba(59,130,246,.4);background:var(--blue-dim)}
.option-btn.selected{border-color:var(--blue);background:var(--blue-dim);color:var(--text)}
.option-btn:disabled{opacity:.4;cursor:not-allowed}
.option-letter{
  width:28px;height:28px;border-radius:7px;
  background:var(--surface);border:1px solid var(--border2);
  display:flex;align-items:center;justify-content:center;
  font-size:.78rem;font-weight:700;color:var(--text2);flex-shrink:0;
  transition:all .15s;font-family:var(--mono);
}
.option-btn.selected .option-letter{background:var(--blue);border-color:var(--blue);color:white}
.option-text{font-weight:500}

.vote-submit{
  width:100%;padding:.8rem;border-radius:10px;
  background:var(--blue);border:none;
  color:white;font-size:.9rem;font-weight:700;font-family:'Onest',sans-serif;
  cursor:pointer;transition:all .2s;letter-spacing:.01em;
}
.vote-submit:hover:not(:disabled){background:#2563eb;box-shadow:0 4px 20px var(--blue-glow)}
.vote-submit:disabled{opacity:.4;cursor:not-allowed}

.vote-note{
  margin-top:.9rem;padding:.75rem;border-radius:8px;
  background:var(--surface2);border:1px solid var(--border);
  font-size:.78rem;color:var(--text3);line-height:1.6;text-align:center;
}

.info-box{
  padding:.9rem 1rem;border-radius:10px;
  font-size:.85rem;line-height:1.6;margin-bottom:1rem;
}
.info-box.warn{background:var(--amber-dim);color:var(--amber);border:1px solid rgba(245,158,11,.2)}
.info-box.success{background:var(--green-dim);color:var(--green);border:1px solid rgba(34,197,94,.2)}
.info-box.info{background:var(--blue-dim);color:#93c5fd;border:1px solid rgba(59,130,246,.2)}
.info-box.error{background:var(--red-dim);color:var(--red);border:1px solid rgba(239,68,68,.2)}

/* ── ZK progress ── */
.zk-progress{margin-bottom:1rem}
.zk-step{
  display:flex;align-items:center;gap:.65rem;
  padding:.5rem 0;font-size:.82rem;color:var(--text2);
  border-bottom:1px solid var(--border);
}
.zk-step:last-child{border-bottom:none}
.zk-icon{font-size:1rem;width:20px;text-align:center;flex-shrink:0}
.zk-spinner{
  width:14px;height:14px;border:2px solid var(--border2);
  border-top-color:var(--blue);border-radius:50%;
  animation:spin .6s linear infinite;flex-shrink:0;
}
@keyframes spin{to{transform:rotate(360deg)}}

/* ── Connect modal ── */
.modal-overlay{
  position:fixed;inset:0;z-index:200;
  background:rgba(0,0,0,.7);backdrop-filter:blur(4px);
  display:flex;align-items:center;justify-content:center;
  animation:fadeIn .15s ease;
}
.modal{
  background:var(--surface);border:1px solid var(--border2);border-radius:20px;
  padding:2rem;width:min(480px,90vw);
  animation:slideUp .2s ease;
}
@keyframes slideUp{from{transform:translateY(16px);opacity:0}to{transform:translateY(0);opacity:1}}
.modal-title{font-size:1.25rem;font-weight:800;margin-bottom:.5rem;letter-spacing:-.02em}
.modal-sub{font-size:.875rem;color:var(--text2);margin-bottom:1.5rem;line-height:1.6}

.wallet-list{display:flex;flex-direction:column;gap:.5rem;margin-bottom:1rem}
.wallet-option{
  display:flex;align-items:center;gap:.9rem;
  width:100%;padding:.9rem 1rem;
  background:var(--surface2);border:1.5px solid var(--border);border-radius:11px;
  cursor:pointer;font-family:'Onest',sans-serif;
  transition:all .15s;text-align:left;
}
.wallet-option:hover{border-color:rgba(59,130,246,.4);background:var(--blue-dim)}
.wallet-avatar{
  width:36px;height:36px;border-radius:10px;
  display:flex;align-items:center;justify-content:center;
  font-size:1.1rem;background:var(--surface);border:1px solid var(--border2);flex-shrink:0;
}
.wallet-name{font-size:.9rem;font-weight:600;color:var(--text)}
.wallet-addr{font-size:.75rem;color:var(--text2);font-family:var(--mono)}
.wallet-group{font-size:.72rem;color:var(--text3)}

.modal-close{
  width:100%;padding:.65rem;border-radius:9px;
  background:none;border:1px solid var(--border2);
  color:var(--text2);font-family:'Onest',sans-serif;font-size:.875rem;
  cursor:pointer;transition:all .15s;margin-top:.5rem;
}
.modal-close:hover{background:var(--surface2);color:var(--text)}

/* ── Admin page ── */
.admin-grid{display:grid;grid-template-columns:1fr 1fr;gap:1.5rem}
@media(max-width:700px){.admin-grid{grid-template-columns:1fr}}
.admin-card{
  background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:1.4rem;
}
.admin-card-title{font-size:.9rem;font-weight:700;margin-bottom:1rem;color:var(--text2);text-transform:uppercase;letter-spacing:.05em}
.student-row{
  display:flex;align-items:center;gap:.75rem;
  padding:.6rem 0;border-bottom:1px solid var(--border);
}
.student-row:last-child{border-bottom:none}
.student-dot{width:7px;height:7px;border-radius:50%;background:var(--green);flex-shrink:0}
.student-name{font-size:.875rem;font-weight:500;flex:1}
.student-meta{font-size:.75rem;color:var(--text3)}
.commit-hash{font-family:var(--mono);font-size:.7rem;color:var(--text3)}

.log-entry{
  padding:.5rem 0;border-bottom:1px solid var(--border);
  font-size:.8rem;
}
.log-entry:last-child{border-bottom:none}
.log-time{color:var(--text3);font-family:var(--mono);font-size:.72rem}
.log-nullifier{font-family:var(--mono);font-size:.72rem;color:var(--blue)}

/* ── Empty state ── */
.empty{text-align:center;padding:4rem 2rem;color:var(--text3)}
.empty-icon{font-size:3rem;margin-bottom:1rem;opacity:.4}
.empty h3{font-size:1.1rem;font-weight:700;color:var(--text2);margin-bottom:.4rem}
.empty p{font-size:.875rem;line-height:1.6}

/* ── Filter bar ── */
.filter-bar{display:flex;gap:.4rem;margin-bottom:1.5rem;flex-wrap:wrap}
.filter-btn{
  padding:.35rem .85rem;border-radius:7px;
  background:var(--surface2);border:1px solid var(--border);
  color:var(--text2);font-size:.8rem;font-weight:500;font-family:'Onest',sans-serif;
  cursor:pointer;transition:all .15s;
}
.filter-btn:hover{border-color:var(--border2);color:var(--text)}
.filter-btn.active{background:var(--blue-dim);border-color:rgba(59,130,246,.4);color:var(--blue)}

/* ── Time display ── */
.time-display{font-family:var(--mono);font-size:.78rem;color:var(--text2)}

/* ── Toast ── */
.toast{
  position:fixed;bottom:2rem;right:2rem;z-index:300;
  padding:.9rem 1.2rem;border-radius:12px;
  font-size:.875rem;font-weight:500;
  box-shadow:0 8px 32px rgba(0,0,0,.4);
  animation:toastIn .25s ease;
  max-width:320px;line-height:1.5;
}
@keyframes toastIn{from{transform:translateX(20px);opacity:0}to{transform:translateX(0);opacity:1}}
.toast.success{background:#14532d;border:1px solid rgba(34,197,94,.3);color:#86efac}
.toast.error{background:#7f1d1d;border:1px solid rgba(239,68,68,.3);color:#fca5a5}
.toast.info{background:#1e3a8a;border:1px solid rgba(59,130,246,.3);color:#93c5fd}

/* ── Responsive ── */
@media(max-width:640px){
  header{padding:0 1rem}
  main{padding:1.25rem 1rem 3rem}
  .stats-row{grid-template-columns:repeat(2,1fr)}
  nav .nav-btn:not(.active) span{display:none}
}
</style>
</head>
<body>
<div class="grid-bg"></div>
<div class="app">

<header>
  <div class="logo" onclick="navigate('home')">
    <div class="logo-dot"></div>
    UniVote
  </div>
  <nav>
    <button class="nav-btn active" id="nav-home" onclick="navigate('home')"><span>Главная</span></button>
    <button class="nav-btn" id="nav-polls" onclick="navigate('polls')"><span>Голосования</span></button>
    <button class="nav-btn" id="nav-admin" onclick="navigate('admin')"><span>Студенты</span></button>
  </nav>
  <div class="wallet-section">
    <div id="wallet-display" class="wallet-pill" onclick="openConnectModal()">
      <div class="wallet-indicator disconnected" id="wallet-indicator"></div>
      <span id="wallet-label">Подключить</span>
    </div>
  </div>
</header>

<main id="main-content"></main>

</div>

<!-- Connect Modal -->
<div id="connect-modal" class="modal-overlay" style="display:none">
  <div class="modal">
    <div class="modal-title">🔐 Выбрать аккаунт</div>
    <div class="modal-sub">Выберите студента для входа. В реальной системе это ваш MetaMask-кошелёк с ZK-удостоверением.</div>
    <div class="wallet-list" id="wallet-list"></div>
    <button class="modal-close" onclick="closeModal()">Отмена</button>
  </div>
</div>

<div id="toast-container"></div>

<script>
// ─── State ───────────────────────────────────────────────────────────────────
let currentPage = 'home';
let currentPollId = null;
let selectedOption = null;
let currentWallet = null;
let currentStudent = null;
let pollsFilter = 'all';
let stats = null;

// ─── Router ───────────────────────────────────────────────────────────────────
function navigate(page, pollId) {
  currentPage = page;
  currentPollId = pollId || null;
  selectedOption = null;
  document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
  const navMap = {home:'nav-home', polls:'nav-polls', admin:'nav-admin', poll:'nav-polls'};
  const el = document.getElementById(navMap[page]);
  if (el) el.classList.add('active');
  render();
  window.scrollTo(0,0);
}

// ─── API ──────────────────────────────────────────────────────────────────────
async function api(method, path, body) {
  const opts = {method, headers:{'Content-Type':'application/json'}};
  if (body) opts.body = JSON.stringify(body);
  const r = await fetch('/api' + path, opts);
  return r.json();
}

// ─── Toast ────────────────────────────────────────────────────────────────────
function toast(msg, type='info') {
  const t = document.createElement('div');
  t.className = 'toast ' + type;
  t.textContent = msg;
  document.getElementById('toast-container').appendChild(t);
  setTimeout(() => t.style.opacity='0', 2500);
  setTimeout(() => t.remove(), 2800);
}

// ─── Connect Modal ────────────────────────────────────────────────────────────
async function openConnectModal() {
  if (currentWallet) {
    await api('POST', '/disconnect');
    currentWallet = null; currentStudent = null;
    updateWalletUI();
    toast('Отключено', 'info');
    render(); return;
  }
  const students = await api('GET', '/students');
  const list = document.getElementById('wallet-list');
  list.innerHTML = '';
  students.forEach(s => {
    const el = document.createElement('button');
    el.className = 'wallet-option';
    el.innerHTML = `
      <div class="wallet-avatar">🎓</div>
      <div>
        <div class="wallet-name">${s.name}</div>
        <div class="wallet-addr">${s.wallet.slice(0,6)}…${s.wallet.slice(-4)}</div>
        <div class="wallet-group">${s.group}</div>
      </div>`;
    el.onclick = () => connectAs(s.wallet);
    list.appendChild(el);
  });
  document.getElementById('connect-modal').style.display = 'flex';
}
function closeModal() { document.getElementById('connect-modal').style.display = 'none'; }

async function connectAs(wallet) {
  closeModal();
  const res = await api('POST', '/connect', {wallet});
  if (res.ok) {
    currentWallet = wallet;
    currentStudent = res.student;
    updateWalletUI();
    toast(`Подключено: ${res.student.name}`, 'success');
    render();
  } else {
    toast(res.error, 'error');
  }
}

function updateWalletUI() {
  const ind = document.getElementById('wallet-indicator');
  const lbl = document.getElementById('wallet-label');
  if (currentWallet) {
    ind.className = 'wallet-indicator connected';
    lbl.textContent = currentStudent.name.split(' ')[0] + ' · ' + currentWallet.slice(0,6)+'…'+currentWallet.slice(-4);
  } else {
    ind.className = 'wallet-indicator disconnected';
    lbl.textContent = 'Подключить';
  }
}

// ─── Time utils ───────────────────────────────────────────────────────────────
function fmtTime(unix) {
  const d = new Date(unix * 1000);
  return d.toLocaleString('ru', {day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'});
}
function timeLeft(unix) {
  const diff = unix - Date.now()/1000;
  if (diff < 0) return 'Завершено';
  const h = Math.floor(diff/3600), m = Math.floor((diff%3600)/60);
  if (h > 48) return `${Math.floor(h/24)} дн.`;
  if (h > 0) return `${h}ч ${m}м`;
  return `${m} мин`;
}

// ─── Badge HTML ───────────────────────────────────────────────────────────────
function badgeHtml(status) {
  const map = {
    active:   ['badge-active',   'Активно'],
    ended:    ['badge-ended',    'Завершено'],
    upcoming: ['badge-upcoming', 'Скоро'],
  };
  const [cls, label] = map[status] || ['badge-ended','—'];
  return `<span class="status-badge ${cls}"><span class="badge-dot"></span>${label}</span>`;
}

// ─── Render pages ─────────────────────────────────────────────────────────────

async function render() {
  const el = document.getElementById('main-content');
  if (currentPage === 'home')  return renderHome(el);
  if (currentPage === 'polls') return renderPolls(el);
  if (currentPage === 'poll')  return renderPoll(el);
  if (currentPage === 'admin') return renderAdmin(el);
}

// HOME
async function renderHome(el) {
  const [s, polls] = await Promise.all([api('GET','/stats'), api('GET','/polls')]);
  stats = s;
  const active = polls.filter(p=>p.status==='active');
  el.innerHTML = `<div class="page">
    <div class="stats-row">
      <div class="stat-card">
        <div class="stat-label">Активных голосований</div>
        <div class="stat-value">${s.active_polls}</div>
        <div class="stat-sub">из ${s.total_polls} всего</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Всего голосов</div>
        <div class="stat-value">${s.total_votes}</div>
        <div class="stat-sub">анонимных ZK-голосов</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Студентов</div>
        <div class="stat-value">${s.registered_students}</div>
        <div class="stat-sub">в вайтлисте</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">ZK-алгоритм</div>
        <div class="stat-value" style="font-size:1.1rem;letter-spacing:-.01em">Groth16</div>
        <div class="stat-sub">Merkle Tree · Poseidon</div>
      </div>
    </div>

    <div class="section-hdr">
      <div class="section-title">Активные голосования</div>
      <span class="section-tag">${active.length} активных</span>
    </div>

    <div class="polls-grid">
      ${active.map(p => pollCardHtml(p)).join('')}
    </div>

    ${s.recent_votes.length ? `
    <div class="section-hdr" style="margin-top:2rem">
      <div class="section-title">Последние голоса</div>
      <span class="section-tag">анонимно</span>
    </div>
    <div class="admin-card" style="background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:1.2rem">
      ${s.recent_votes.map(v=>`
        <div class="log-entry">
          <div style="display:flex;align-items:center;justify-content:space-between;gap:.5rem">
            <span style="font-size:.82rem">🗳 <strong>Голос засчитан</strong> — ${v.option}</span>
            <span class="log-time">${fmtTime(v.ts)}</span>
          </div>
          <div style="margin-top:.2rem">
            <span class="log-nullifier">nullifier: ${v.nullifier}</span>
          </div>
        </div>`).join('')}
    </div>` : ''}
  </div>`;

  el.querySelectorAll('.poll-card').forEach(c => {
    c.addEventListener('click', () => navigate('poll', c.dataset.id));
  });
}

// POLLS
async function renderPolls(el) {
  const polls = await api('GET', '/polls');
  const filters = [
    {key:'all', label:'Все'},
    {key:'active', label:'Активные'},
    {key:'upcoming', label:'Предстоящие'},
    {key:'ended', label:'Завершённые'},
  ];
  const filtered = pollsFilter==='all' ? polls : polls.filter(p=>p.status===pollsFilter);

  el.innerHTML = `<div class="page">
    <div class="section-hdr">
      <div class="section-title">Все голосования</div>
    </div>
    <div class="filter-bar">
      ${filters.map(f=>`<button class="filter-btn ${pollsFilter===f.key?'active':''}" onclick="setFilter('${f.key}')">${f.label} <span style="opacity:.5;font-size:.7rem">${f.key==='all'?polls.length:polls.filter(p=>p.status===f.key).length}</span></button>`).join('')}
    </div>
    ${filtered.length ? `<div class="polls-grid">${filtered.map(p=>pollCardHtml(p)).join('')}</div>`
      : `<div class="empty"><div class="empty-icon">🗳</div><h3>Голосований нет</h3><p>В этой категории пока нет голосований.</p></div>`}
  </div>`;

  el.querySelectorAll('.poll-card').forEach(c => {
    c.addEventListener('click', () => navigate('poll', c.dataset.id));
  });
}

function setFilter(f) { pollsFilter = f; renderPolls(document.getElementById('main-content')); }

function pollCardHtml(p) {
  const totalVotes = p.total_votes;
  return `<div class="poll-card" data-id="${p.id}">
    <div class="poll-card-top">
      <div class="poll-category">${p.category}</div>
      ${badgeHtml(p.status)}
    </div>
    <div class="poll-title">${p.title}</div>
    <div class="poll-meta">
      <span>🗳 ${totalVotes} голосов</span>
      <span>${p.status==='active' ? '⏱ '+timeLeft(p.end_time) : p.status==='upcoming' ? '🕐 Через '+timeLeft(p.start_time) : '✓ Завершено'}</span>
    </div>
    <div class="mini-bar">
      ${Array.from({length:p.options_count},(_,i)=>{
        const w = totalVotes>0 ? Math.round(100/p.options_count) : (100/p.options_count);
        return `<div class="mini-bar-seg" style="width:${w}%;background:hsl(${210+i*40},70%,60%)"></div>`;
      }).join('')}
    </div>
  </div>`;
}

// POLL DETAIL
async function renderPoll(el) {
  const poll = await api('GET', `/poll/${currentPollId}`);
  if (!poll) { el.innerHTML='<div class="page"><div class="empty"><h3>Не найдено</h3></div></div>'; return; }

  const labels = ['А','Б','В','Г','Д','Е'];
  const maxVotes = Math.max(...poll.votes, 1);
  const winnerIdx = poll.votes.indexOf(Math.max(...poll.votes));

  el.innerHTML = `<div class="page">
    <button class="back-btn" onclick="navigate('polls')">← Назад к голосованиям</button>

    <div class="poll-detail-grid">
      <!-- Left: info + results -->
      <div>
        <div class="detail-card" style="margin-bottom:1rem">
          <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:.5rem;margin-bottom:.75rem">
            <div style="font-size:.75rem;color:var(--text3);text-transform:uppercase;letter-spacing:.05em">${poll.category}</div>
            ${badgeHtml(poll.status)}
          </div>
          <div class="detail-title">${poll.title}</div>
          <div class="detail-desc">${poll.description}</div>
          <div class="detail-meta">
            <div class="meta-chip">🗳 ${poll.total_votes} голосов</div>
            <div class="meta-chip">📅 ${fmtTime(poll.start_time)}</div>
            <div class="meta-chip">⏰ ${fmtTime(poll.end_time)}</div>
            ${poll.status==='active' ? `<div class="meta-chip" style="color:var(--green)">⏱ Осталось: ${timeLeft(poll.end_time)}</div>` : ''}
          </div>
        </div>

        <div class="detail-card">
          <div class="results-title">Результаты в реальном времени</div>
          ${poll.options.map((opt, i) => {
            const pct = poll.percentages[i];
            const isWinner = poll.status !== 'active' && i === winnerIdx && poll.total_votes > 0;
            return `<div class="result-row">
              <div class="result-top">
                <div class="result-label">${labels[i]}. ${opt}</div>
                <div class="result-nums">
                  <span class="result-pct">${pct}%</span>
                  <span class="result-count">${poll.votes[i]}г</span>
                </div>
              </div>
              <div class="bar-track">
                <div class="bar-fill ${isWinner?'winner':''}" style="width:${pct}%"></div>
              </div>
            </div>`;
          }).join('')}
        </div>
      </div>

      <!-- Right: vote panel -->
      <div>
        <div class="vote-card" id="vote-card">
          ${renderVotePanel(poll)}
        </div>
      </div>
    </div>
  </div>`;
}

function renderVotePanel(poll) {
  const labels = ['А','Б','В','Г','Д','Е'];

  if (poll.status === 'ended') return `
    <div class="vote-card-title">Голосование завершено</div>
    <div class="info-box info">Голосование закрыто. Результаты окончательны и записаны в блокчейн.</div>`;

  if (poll.status === 'upcoming') return `
    <div class="vote-card-title">Скоро начнётся</div>
    <div class="info-box warn">Голосование откроется через ${timeLeft(poll.start_time)}.</div>`;

  if (!currentWallet) return `
    <div class="vote-card-title">🗳 Проголосовать</div>
    <div class="info-box warn">Подключите кошелёк, чтобы проголосовать.</div>
    <button class="vote-submit" onclick="openConnectModal()">Подключить кошелёк</button>`;

  if (poll.already_voted) return `
    <div class="vote-card-title">✓ Вы проголосовали</div>
    <div class="info-box success">Ваш анонимный голос засчитан. Nullifier hash записан в контракт — повторное голосование невозможно.</div>
    <div class="vote-note">🔒 ZK-proof верифицирован on-chain</div>`;

  return `
    <div class="vote-card-title">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
      Анонимное голосование
    </div>
    <div class="options-list" id="options-list">
      ${poll.options.map((opt,i)=>`
        <button class="option-btn" id="opt-${i}" onclick="selectOption(${i})">
          <span class="option-letter">${labels[i]}</span>
          <span class="option-text">${opt}</span>
        </button>`).join('')}
    </div>
    <button class="vote-submit" id="vote-submit-btn" onclick="submitVote()" disabled>
      Проголосовать
    </button>
    <div class="vote-note">
      🔒 Ваша личность защищена ZK-доказательством.<br>
      Nullifier hash предотвращает двойное голосование.
    </div>`;
}

function selectOption(i) {
  selectedOption = i;
  document.querySelectorAll('.option-btn').forEach((b,j) => {
    b.classList.toggle('selected', j===i);
  });
  const btn = document.getElementById('vote-submit-btn');
  if (btn) btn.disabled = false;
}

async function submitVote() {
  if (selectedOption === null || !currentWallet) return;

  // Show ZK progress
  const card = document.getElementById('vote-card');
  card.innerHTML = `
    <div class="vote-card-title">🔐 Генерация ZK-доказательства</div>
    <div class="zk-progress">
      <div class="zk-step" id="step-1"><div class="zk-spinner"></div> Загрузка identity из хранилища...</div>
      <div class="zk-step" id="step-2" style="opacity:.3">⏳ Получение Merkle proof...</div>
      <div class="zk-step" id="step-3" style="opacity:.3">⏳ Вычисление nullifier hash...</div>
      <div class="zk-step" id="step-4" style="opacity:.3">⏳ Генерация Groth16 proof...</div>
      <div class="zk-step" id="step-5" style="opacity:.3">⏳ Отправка транзакции...</div>
    </div>
    <div class="vote-note">Пожалуйста, подождите. В реальной системе генерация ZK-proof занимает 10–30 секунд.</div>`;

  // Animate steps
  const steps = [
    [1, 600],
    [2, 1000],
    [3, 700],
    [4, 1200],
    [5, 600],
  ];

  let delay = 0;
  for (const [stepNum, dur] of steps) {
    await new Promise(r => setTimeout(r, delay));
    const el = document.getElementById(`step-${stepNum}`);
    if (el) {
      el.style.opacity = '1';
      el.innerHTML = `<div class="zk-spinner"></div> ${el.textContent.trim().replace('⏳ ','')}`;
    }
    delay = dur;
  }

  await new Promise(r => setTimeout(r, delay));

  // Submit
  const res = await api('POST', '/vote', {
    poll_id: currentPollId,
    option_index: selectedOption,
    wallet: currentWallet,
  });

  if (res.ok) {
    card.innerHTML = `
      <div class="vote-card-title">✅ Голос засчитан!</div>
      <div class="info-box success">${res.message}</div>
      <div style="margin-top:1rem;font-size:.8rem;color:var(--text3)">
        <div style="margin-bottom:.4rem">Nullifier hash:</div>
        <div class="log-nullifier" style="word-break:break-all">${res.nullifier}</div>
        <div style="margin-top:.75rem;margin-bottom:.4rem">Transaction hash:</div>
        <div class="log-nullifier" style="word-break:break-all">${res.tx_hash}</div>
      </div>
      <div class="vote-note" style="margin-top:1rem">🔒 Proof верифицирован смарт-контрактом. Ваша личность не раскрыта.</div>`;
    toast('Голос успешно засчитан! 🎉', 'success');
    // Refresh results after a moment
    setTimeout(() => renderPoll(document.getElementById('main-content')), 1500);
  } else {
    card.innerHTML = `
      <div class="vote-card-title">⚠ Ошибка</div>
      <div class="info-box error">${res.error}</div>
      <button class="vote-submit" onclick="renderPoll(document.getElementById('main-content'))" style="margin-top:1rem">Попробовать снова</button>`;
    toast(res.error, 'error');
  }
}

// ADMIN
async function renderAdmin(el) {
  const [students, s] = await Promise.all([api('GET','/students'), api('GET','/stats')]);

  el.innerHTML = `<div class="page">
    <div class="section-hdr">
      <div class="section-title">Студенты и вайтлист</div>
      <span class="section-tag">${students.length} зарегистрировано</span>
    </div>
    <div class="admin-grid">
      <div class="admin-card">
        <div class="admin-card-title">📋 Реестр избирателей</div>
        ${students.map(s=>`
          <div class="student-row">
            <div class="student-dot"></div>
            <div style="flex:1">
              <div class="student-name">${s.name}</div>
              <div style="display:flex;gap:.75rem;margin-top:.15rem">
                <span class="student-meta">${s.group}</span>
                <span class="student-meta" style="font-family:var(--mono)">${s.wallet.slice(0,8)}…${s.wallet.slice(-6)}</span>
              </div>
              <div class="commit-hash">commitment: ${s.commitment.slice(0,20)}…</div>
            </div>
          </div>`).join('')}
      </div>

      <div>
        <div class="admin-card" style="margin-bottom:1rem">
          <div class="admin-card-title">📊 Статистика блокчейна</div>
          ${[
            ['Всего голосований', s.total_polls],
            ['Активных', s.active_polls],
            ['Голосов записано', s.total_votes],
            ['Студентов в вайтлисте', s.registered_students],
          ].map(([l,v])=>`
            <div class="student-row" style="justify-content:space-between">
              <span style="font-size:.85rem;color:var(--text2)">${l}</span>
              <span style="font-weight:700;font-family:var(--mono)">${v}</span>
            </div>`).join('')}
        </div>

        <div class="admin-card">
          <div class="admin-card-title">🔗 ZK-лог голосований</div>
          ${s.recent_votes.length ? s.recent_votes.map(v=>`
            <div class="log-entry">
              <div style="font-size:.82rem;font-weight:600">${v.option}</div>
              <div style="display:flex;gap:.75rem;margin-top:.2rem;flex-wrap:wrap">
                <span class="log-nullifier">${v.nullifier}</span>
                <span class="log-time">${fmtTime(v.ts)}</span>
              </div>
            </div>`).join('')
          : '<div style="font-size:.85rem;color:var(--text3);padding:.5rem 0">Голосов пока нет</div>'}
        </div>
      </div>
    </div>
  </div>`;
}

// ─── Init ─────────────────────────────────────────────────────────────────────
document.getElementById('connect-modal').addEventListener('click', e => {
  if (e.target === document.getElementById('connect-modal')) closeModal();
});
render();
setInterval(() => { if (currentPage === 'home' || currentPage === 'polls') render(); }, 30000);
</script>
</body>
</html>"""

# ─────────────────────────────────────────────────────────────────────────────
#  HTTP Handler (acts as mini FastAPI)
# ─────────────────────────────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        pass  # suppress default access log

    def send_json(self, data, status=200):
        body = json.dumps(data, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def send_html(self, html):
        body = html.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        if length:
            return json.loads(self.rfile.read(length))
        return {}

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path   = parsed.path

        if path == "/" or path == "/index.html":
            return self.send_html(HTML)

        if path == "/api/polls":
            return self.send_json(api_polls())

        if path.startswith("/api/poll/"):
            pid = path.split("/api/poll/")[-1]
            result = api_poll(pid)
            if result is None:
                return self.send_json({"error": "not found"}, 404)
            return self.send_json(result)

        if path == "/api/students":
            return self.send_json(STUDENTS)

        if path == "/api/stats":
            return self.send_json(api_stats())

        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        parsed = urlparse(self.path)
        path   = parsed.path
        body   = self.read_body()

        if path == "/api/connect":
            return self.send_json(api_connect(body.get("wallet", "")))

        if path == "/api/disconnect":
            return self.send_json(api_disconnect())

        if path == "/api/vote":
            return self.send_json(
                api_cast_vote(
                    body.get("poll_id", ""),
                    body.get("option_index", -1),
                    body.get("wallet", ""),
                )
            )

        self.send_response(404)
        self.end_headers()


# ─────────────────────────────────────────────────────────────────────────────
#  Entry point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    PORT = 8000
    server = HTTPServer(("", PORT), Handler)
    print(f"""
╔══════════════════════════════════════════════════╗
║           UniVote — Демо-сервер запущен          ║
╠══════════════════════════════════════════════════╣
║  🌐  http://localhost:{PORT}                       ║
║                                                  ║
║  📋  6 тестовых голосований                      ║
║  🎓  8 студентов в вайтлисте                     ║
║  🔐  Симуляция ZK-proof (Groth16 + Merkle)       ║
║                                                  ║
║  Для остановки: Ctrl+C                           ║
╚══════════════════════════════════════════════════╝
""")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nСервер остановлен.")
