#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RL Overlay Studio — Windows desktop app + OBS Browser Overlay + Remote Control

This app reads Rocket League StatsAPI/SOS-like JSON events from localhost TCP,
broadcasts the live state to OBS/remote pages over WebSocket, and provides a
modern PyQt dashboard. It does not inject into Rocket League and does not modify
game memory. It only consumes local telemetry exposed by your StatsAPI source.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import os
import queue
import shutil
import subprocess
import re
import secrets
import socket
import sys
import tempfile
import threading
import time
import traceback
import urllib.parse
import urllib.request
import urllib.error
import html
import faulthandler
import webbrowser
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

try:
    import websockets
except Exception:  # pragma: no cover - handled at runtime
    websockets = None

from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject, QPoint, QRect
from PyQt6.QtGui import QColor, QFont, QGuiApplication, QIcon, QPainter, QPen, QBrush, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QFileDialog,
    QMessageBox,
)

APP_NAME = "RL Overlay Studio"
HTTP_PORT = 49124
WS_PORT = 49125
APP_VERSION = "Beta 3.8"
APP_VERSION_LABEL = "Beta 3.8 By Luki7 / Eraclesss / Julianout"

# Mise à jour automatique GitHub
# Option 1 recommandée : mets ton dépôt GitHub ici, exemple : "Luki7/RL-Overlay-Studio"
# L'application lira automatiquement la dernière Release GitHub.
GITHUB_UPDATE_REPO = "Lukiseven/RL-Overlay-Studio"

# Option 2 : mets directement l'URL d'un update.json public si tu préfères un manifest personnalisé.
# Exemple : "https://raw.githubusercontent.com/Luki7/RL-Overlay-Studio/main/update.json"
GITHUB_UPDATE_MANIFEST_URL = ""

AUTO_UPDATE_CHECK_DELAY_MS = 3500
DEFAULT_STATSAPI_PORT = 49123

if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).resolve().parent
    RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", BASE_DIR)).resolve()
else:
    BASE_DIR = Path(__file__).resolve().parent
    RESOURCE_DIR = BASE_DIR

# Chemins runtime.
# Important : aucun dossier/fichier n'est créé au lancement.
# Les fichiers Configs/Crash/Sauvegardes ne sont créés que lorsqu'une sauvegarde explicite
# ou un vrai crash nécessite une écriture.
#
# Demande Beta 2.3 :
# écrire les fichiers de sauvegarde dans %AppData% afin d'éviter
# C:\Program Files et le dossier de téléchargement/lancement.
APPDATA_ROOT = Path(
    os.environ.get(
        "APPDATA",
        str(Path.home() / "AppData" / "Roaming")
    )
)
APP_DATA_DIR = APPDATA_ROOT / "RL Overlay Studio" / "AppData"
CONFIG_DIR = APP_DATA_DIR / "Configs"
CRASH_DIR = APP_DATA_DIR / "Crash"
CONFIG_PATH = CONFIG_DIR / "config.json"
CRASH_LOG_PATH = CRASH_DIR / "crash.log"
LEGACY_CONFIG_PATH = BASE_DIR / "config.json"

APP_ICON_PNG = RESOURCE_DIR / "assets" / "app_icon.png"
APP_ICON_ICO = RESOURCE_DIR / "assets" / "app_icon.ico"

PLAYLIST_NAMES = {
    "1v1": "Ranked Duel 1v1",
    "2v2": "Ranked Doubles 2v2",
    "3v3": "Ranked Standard 3v3",
}
NO_PLAYLIST_LABEL = "Aucune playlist"
PLAYLIST_COMBO_ITEMS = [NO_PLAYLIST_LABEL, "1v1", "2v2", "3v3"]

TRACKER_PLAYLIST_LABELS = {
    "1v1": "Ranked Duel 1v1",
    "2v2": "Ranked Doubles 2v2",
    "3v3": "Ranked Standard 3v3",
}
TRACKER_LEADERBOARD_PLAYLIST_IDS = {"1v1": 10, "2v2": 11, "3v3": 13}

TRACKER_PLATFORM_LABELS = {
    "epic": "Epic Games",
    "steam": "Steam",
    "xbl": "Xbox Live",
    "psn": "PlayStation Network",
    "switch": "Nintendo Switch",
}

RLS_API_BASE = "http://vps-5d4cfceb.vps.ovh.net:6102"
RLS_API_KEY = "rls_bd3f6b0ca10c4e63aef88ed1ecddd9a988a1af1ee265a776"


# Paliers FireTeaM Saison 21 (2026). Ces seuils servent à afficher un rank
# localement dès qu'un MMR est disponible dans l'API ou saisi/lu depuis l'écran.
# Format: (min_inclus, max_inclus ou None, label court, label complet, asset png)
RANK_TABLES: Dict[str, List[Tuple[int, Optional[int], str, str, str]]] = {
    "1v1": [
        (0, 154, "B1", "Bronze 1", "bronze_1.png"),
        (155, 214, "B2", "Bronze 2", "bronze_2.png"),
        (215, 275, "B3", "Bronze 3", "bronze_3.png"),
        (276, 334, "S1", "Argent 1", "silver_1.png"),
        (335, 394, "S2", "Argent 2", "silver_2.png"),
        (395, 454, "S3", "Argent 3", "silver_3.png"),
        (455, 514, "G1", "Or 1", "gold_1.png"),
        (515, 574, "G2", "Or 2", "gold_2.png"),
        (575, 634, "G3", "Or 3", "gold_3.png"),
        (635, 694, "P1", "Platine 1", "platinum_1.png"),
        (695, 754, "P2", "Platine 2", "platinum_2.png"),
        (755, 814, "P3", "Platine 3", "platinum_3.png"),
        (815, 874, "D1", "Diamant 1", "diamond_1.png"),
        (875, 934, "D2", "Diamant 2", "diamond_2.png"),
        (935, 994, "D3", "Diamant 3", "diamond_3.png"),
        (995, 1054, "C1", "Champion 1", "champion_1.png"),
        (1055, 1114, "C2", "Champion 2", "champion_2.png"),
        (1115, 1174, "C3", "Champion 3", "champion_3.png"),
        (1175, 1234, "GC1", "Grand Champion 1", "grand_champion_1.png"),
        (1235, 1295, "GC2", "Grand Champion 2", "grand_champion_2.png"),
        (1296, 1355, "GC3", "Grand Champion 3", "grand_champion_3.png"),
        (1356, None, "SSL", "Supersonic Legend", "supersonic_legend.png"),
    ],
    "2v2": [
        (0, 174, "B1", "Bronze 1", "bronze_1.png"),
        (175, 234, "B2", "Bronze 2", "bronze_2.png"),
        (235, 294, "B3", "Bronze 3", "bronze_3.png"),
        (295, 354, "S1", "Argent 1", "silver_1.png"),
        (355, 414, "S2", "Argent 2", "silver_2.png"),
        (415, 474, "S3", "Argent 3", "silver_3.png"),
        (475, 534, "G1", "Or 1", "gold_1.png"),
        (535, 594, "G2", "Or 2", "gold_2.png"),
        (595, 654, "G3", "Or 3", "gold_3.png"),
        (655, 714, "P1", "Platine 1", "platinum_1.png"),
        (715, 774, "P2", "Platine 2", "platinum_2.png"),
        (775, 834, "P3", "Platine 3", "platinum_3.png"),
        (835, 914, "D1", "Diamant 1", "diamond_1.png"),
        (915, 994, "D2", "Diamant 2", "diamond_2.png"),
        (995, 1074, "D3", "Diamant 3", "diamond_3.png"),
        (1075, 1194, "C1", "Champion 1", "champion_1.png"),
        (1195, 1314, "C2", "Champion 2", "champion_2.png"),
        (1315, 1434, "C3", "Champion 3", "champion_3.png"),
        (1435, 1574, "GC1", "Grand Champion 1", "grand_champion_1.png"),
        (1575, 1705, "GC2", "Grand Champion 2", "grand_champion_2.png"),
        (1706, 1875, "GC3", "Grand Champion 3", "grand_champion_3.png"),
        (1876, None, "SSL", "Supersonic Legend", "supersonic_legend.png"),
    ],
    "3v3": [
        (0, 175, "B1", "Bronze 1", "bronze_1.png"),
        (176, 234, "B2", "Bronze 2", "bronze_2.png"),
        (235, 294, "B3", "Bronze 3", "bronze_3.png"),
        (295, 354, "S1", "Argent 1", "silver_1.png"),
        (355, 414, "S2", "Argent 2", "silver_2.png"),
        (415, 474, "S3", "Argent 3", "silver_3.png"),
        (475, 534, "G1", "Or 1", "gold_1.png"),
        (535, 594, "G2", "Or 2", "gold_2.png"),
        (595, 654, "G3", "Or 3", "gold_3.png"),
        (655, 714, "P1", "Platine 1", "platinum_1.png"),
        (715, 774, "P2", "Platine 2", "platinum_2.png"),
        (775, 834, "P3", "Platine 3", "platinum_3.png"),
        (835, 914, "D1", "Diamant 1", "diamond_1.png"),
        (915, 994, "D2", "Diamant 2", "diamond_2.png"),
        (995, 1074, "D3", "Diamant 3", "diamond_3.png"),
        (1075, 1194, "C1", "Champion 1", "champion_1.png"),
        (1195, 1315, "C2", "Champion 2", "champion_2.png"),
        (1316, 1434, "C3", "Champion 3", "champion_3.png"),
        (1435, 1575, "GC1", "Grand Champion 1", "grand_champion_1.png"),
        (1576, 1716, "GC2", "Grand Champion 2", "grand_champion_2.png"),
        (1717, 1869, "GC3", "Grand Champion 3", "grand_champion_3.png"),
        (1870, None, "SSL", "Supersonic Legend", "supersonic_legend.png"),
    ],
}

PLAYLIST_ID_MAP = {
    10: "1v1",  # Ranked Duel
    11: "2v2",  # Ranked Doubles
    13: "3v3",  # Ranked Standard
}
RANKED_PLAYLIST_IDS = set(PLAYLIST_ID_MAP)
NON_COMPETITIVE_KEYWORDS = (
    "freeplay", "free play", "jeu libre", "mode libre", "libre", "entrainement", "entraînement", "training", "practice",
    "tutorial", "workshop", "garage", "mainmenu", "main menu", "menu",
    "replay", "spectator", "spectateur", "casual", "unranked", "offline"
)


def rank_from_mmr(playlist: str, mmr: Optional[int]) -> Dict[str, str]:
    if mmr is None:
        return {"label": "", "short": "", "asset": ""}
    try:
        value = int(mmr)
    except Exception:
        return {"label": "", "short": "", "asset": ""}
    for low, high, short, label, asset in RANK_TABLES.get(playlist, RANK_TABLES["3v3"]):
        if value >= low and (high is None or value <= high):
            return {"label": label, "short": short, "asset": asset}
    return {"label": "", "short": "", "asset": ""}



def rank_from_text(text_value: str, playlist: str = "3v3") -> Dict[str, str]:
    """Map a manual rank label to the local rank asset."""
    text = str(text_value or "").strip().lower()
    if not text:
        return {"label": "", "short": "", "asset": ""}
    aliases = {
        "ssl": "supersonic legend",
        "supersonic": "supersonic legend",
        "gc1": "grand champion 1", "gc2": "grand champion 2", "gc3": "grand champion 3",
        "c1": "champion 1", "c2": "champion 2", "c3": "champion 3",
        "d1": "diamond 1", "d2": "diamond 2", "d3": "diamond 3",
        "p1": "platinum 1", "p2": "platinum 2", "p3": "platinum 3",
        "g1": "gold 1", "g2": "gold 2", "g3": "gold 3",
        "s1": "silver 1", "s2": "silver 2", "s3": "silver 3",
        "b1": "bronze 1", "b2": "bronze 2", "b3": "bronze 3",
    }
    compact = re.sub(r"[^a-z0-9]", "", text)
    if compact in aliases:
        text = aliases[compact]
    text = text.replace("platine", "platinum").replace("diamant", "diamond").replace("argent", "silver").replace("or ", "gold ")
    for _low, _high, short, label, asset in RANK_TABLES.get(playlist, RANK_TABLES["3v3"]):
        label_l = label.lower()
        label_compact = re.sub(r"[^a-z0-9]", "", label_l)
        if label_l in text or label_compact in compact or short.lower() == compact:
            return {"label": label, "short": short, "asset": asset}
    return {"label": str(text_value or ""), "short": str(text_value or ""), "asset": ""}



def normalize_display_leader_rank(value: Any) -> str:
    """Retourne le Top rank affichable uniquement entre 1 et 999.

    Exemple :
    - "#11 • Top 0.1%" -> "11"
    - "999" -> "999"
    - "1000" -> ""
    - "" -> ""
    """
    raw = str(value or "").strip()
    if not raw:
        return ""

    # Priorité au nombre juste après "#", pour ne pas mélanger avec "Top 0.1%".
    hash_match = re.search(r"#\s*([0-9][0-9,\s\.]*)", raw)
    if hash_match:
        digits = re.sub(r"\D", "", hash_match.group(1))
    else:
        digits = re.sub(r"\D", "", raw)

    if not digits:
        return ""
    try:
        rank = int(digits)
    except Exception:
        return ""
    if 1 <= rank <= 999:
        return str(rank)
    return ""



def normalize_playlist(value: Any) -> Optional[str]:
    """Normalise uniquement une vraie valeur de playlist/mode Rocket League.

    On évite volontairement les déductions trop larges : par exemple un ancien
    build pouvait convertir n'importe quel texte contenant "standard" en 3v3.
    Ici, 3v3 n'est retenu que si le nom de game/playlist du JSON le dit vraiment
    ou si un vrai PlaylistID ranked officiel est présent.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return PLAYLIST_ID_MAP.get(int(value))

    raw = str(value or "").strip()
    if not raw:
        return None
    if raw.isdigit():
        return PLAYLIST_ID_MAP.get(int(raw))

    text = raw.lower().replace("_", " ").replace("-", " ")
    compact = re.sub(r"\s+", " ", text).strip()

    if re.search(r"\b1\s*v\s*1\b", compact) or "ranked duel" in compact or compact in {"duel", "duels"}:
        return "1v1"
    if re.search(r"\b2\s*v\s*2\b", compact) or "ranked double" in compact or compact in {"double", "doubles"}:
        return "2v2"
    if re.search(r"\b3\s*v\s*3\b", compact) or "ranked standard" in compact or compact in {"standard", "triple", "triples"}:
        return "3v3"
    return None


def _is_playlist_name_path(path: str) -> bool:
    """True seulement pour les champs JSON qui décrivent le nom/id de la game/playlist."""
    tail = path.lower().replace("-", "_").split(".")[-1]
    tail = re.sub(r"\[[0-9]+\]", "", tail)
    allowed_tails = {
        "playlist", "playlistid", "playlist_id", "playlistnum", "playlist_num",
        "playlistname", "playlist_name", "gamemode", "game_mode",
        "gamemodename", "game_mode_name", "matchtype", "match_type",
        "queuename", "queue_name", "queue",
    }
    return tail in allowed_tails


def iter_json_values(obj: Any, path: str = ""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            key_path = f"{path}.{k}" if path else str(k)
            yield key_path, v
            yield from iter_json_values(v, key_path)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from iter_json_values(v, f"{path}[{i}]")


def extract_winner_team_from_payload(*payloads: Any) -> Optional[int]:
    """Best-effort winner extraction for normal end, surrender/forfeit and overtime events.

    Some StatsAPI/SOS payloads expose the final result as WinnerTeamNum, WinningTeam,
    winning_team, bWinner, Result, etc. We keep this generic so a forfeit at 1-1 can
    still be resolved from the official end-of-match information instead of score only.
    """
    direct_keys = (
        "winnerteamnum",
        "winningteamnum",
        "winner_team_num",
        "winning_team_num",
        "winnerteam",
        "winningteam",
        "winner_team",
        "winning_team",
        "forfeitwinnerteamnum",
        "surrenderwinnerteamnum",
        "winningteamid",
        "winnerteamid",
    )
    for payload in payloads:
        for path, value in iter_json_values(payload):
            p = path.lower().replace(".", "_")
            if any(k in p for k in direct_keys):
                try:
                    if isinstance(value, dict):
                        for inner_key in ("TeamNum", "teamNum", "team_num", "Team", "team", "id", "Id"):
                            if inner_key in value:
                                parsed_inner = parse_team_num_value(value.get(inner_key))
                                if parsed_inner in (0, 1):
                                    return parsed_inner
                                by_name_inner = team_number_from_name(value.get(inner_key), extract_teams_collection(*payloads))
                                if by_name_inner in (0, 1):
                                    return by_name_inner
                        by_name_dict = team_number_from_name(team_display_name(value), extract_teams_collection(*payloads))
                        if by_name_dict in (0, 1):
                            return by_name_dict
                    if isinstance(value, bool):
                        continue
                    parsed = parse_team_num_value(value)
                    if parsed in (0, 1):
                        return parsed
                    by_name = team_number_from_name(value, extract_teams_collection(*payloads))
                    if by_name in (0, 1):
                        return by_name
                except Exception:
                    continue

    # Fallback : a players/teams list may mark the winner directly.
    for payload in payloads:
        for path, value in iter_json_values(payload):
            p = path.lower().replace(".", "_")
            if any(k in p for k in ("iswinner", "bwinner", "winner")) and isinstance(value, bool) and value:
                parent_path = path.rsplit(".", 1)[0] if "." in path else ""
                # Search sibling TeamNum near the same parent path.
                for path2, value2 in iter_json_values(payload):
                    if parent_path and path2.startswith(parent_path) and path2.lower().endswith(("teamnum", "team_num", "team")):
                        try:
                            parsed = parse_team_num_value(value2)
                            if parsed in (0, 1):
                                return parsed
                            by_name = team_number_from_name(value2, extract_teams_collection(payload))
                            if by_name in (0, 1):
                                return by_name
                        except Exception:
                            pass
    return None


def extract_playlist_from_payload(*payloads: Any) -> Optional[str]:
    """Lit la playlist depuis les vrais champs JSON de game/playlist.

    Priorité au nom/ID fourni par StatsAPI/SOS. On ne parcourt pas des chemins
    trop larges pour éviter qu'une ancienne valeur ou un libellé non lié à la
    game force 3v3 pendant une 1v1.
    """
    for payload in payloads:
        for path, value in iter_json_values(payload):
            if not _is_playlist_name_path(path):
                continue
            normalized = normalize_playlist(value)
            if normalized:
                return normalized
    return None


def resolve_playlist_from_game_and_players(
    api_playlist: Optional[str],
    player_playlist: Optional[str],
    players_available: bool = True,
) -> Optional[str]:
    """Combine le nom de game JSON et le nombre de joueurs présents.

    - Si les deux sources existent et concordent, la playlist est fiable.
    - Si elles se contredisent, on n'applique rien pour éviter un faux 3v3.
    - Si l'API ne donne aucun nom de game, la déduction joueurs peut suffire.
    - Si aucun joueur n'est encore lisible, on autorise le nom API pour ne pas
      bloquer les payloads pauvres, mais dès que des joueurs sont présents la
      cohérence des joueurs devient obligatoire.
    """
    if api_playlist and player_playlist:
        return api_playlist if api_playlist == player_playlist else None
    if player_playlist and not api_playlist:
        return player_playlist
    if api_playlist and not players_available:
        return api_playlist
    return None


def extract_mmr_from_payload(*payloads: Any) -> Optional[int]:
    preferred = ("mmr", "skillrating", "skill_rating", "rankpoints", "rank_points", "rating")
    candidates: List[int] = []
    for payload in payloads:
        for path, value in iter_json_values(payload):
            p = path.lower().replace(".", "_")
            if not any(k in p for k in preferred):
                continue
            if isinstance(value, bool):
                continue
            if isinstance(value, (int, float)):
                iv = int(value)
                if 0 <= iv <= 4000:
                    candidates.append(iv)
            elif isinstance(value, str):
                for match in re.findall(r"\b(\d{2,4})\b", value):
                    iv = int(match)
                    if 0 <= iv <= 4000:
                        candidates.append(iv)
    return candidates[0] if candidates else None


def extract_playlist_id_from_payload(*payloads: Any) -> Optional[int]:
    numeric_tails = {"playlistid", "playlist_id", "playlistnum", "playlist_num"}
    playlist_tails = {"playlist"}
    for payload in payloads:
        for path, value in iter_json_values(payload):
            if isinstance(value, bool):
                continue
            tail = path.lower().replace("-", "_").split(".")[-1]
            tail = re.sub(r"\[[0-9]+\]", "", tail)
            if tail in numeric_tails:
                if isinstance(value, (int, float)):
                    return int(value)
                if isinstance(value, str):
                    m = re.fullmatch(r"\s*(\d{1,3})\s*", value)
                    if m:
                        return int(m.group(1))
            elif tail in playlist_tails:
                # Ne jamais extraire le "3" de "Ranked Standard 3v3" : seuls les vrais champs numériques comptent.
                if isinstance(value, (int, float)):
                    return int(value)
                if isinstance(value, str) and value.strip().isdigit():
                    return int(value.strip())
    return None


def detect_non_competitive_context(*payloads: Any) -> Optional[str]:
    """Return a reason if the API payload clearly describes training/freeplay/non-ranked."""
    playlist_id = extract_playlist_id_from_payload(*payloads)
    if playlist_id is not None and playlist_id not in RANKED_PLAYLIST_IDS:
        return f"playlist non ranked #{playlist_id}"

    interesting_paths = ("game", "match", "playlist", "mode", "state", "map", "training", "freeplay")
    for payload in payloads:
        for path, value in iter_json_values(payload):
            if isinstance(value, str):
                lower_path = path.lower()
                if not any(key in lower_path for key in interesting_paths):
                    continue
                text = value.lower().replace("_", " ").replace("-", " ")
                for keyword in NON_COMPETITIVE_KEYWORDS:
                    if keyword in text:
                        return keyword
    return None




def target_team_zero_training(*payloads: Any) -> bool:
    """Compatibility helper.

    Team 0 in Rocket League usually means the blue team, not training.
    Older builds used this as a training signal; now it is only used as a
    "target has a valid team" hint when other players are present.
    """
    for payload in payloads:
        if not isinstance(payload, (dict, list)):
            continue
        for path, value in iter_json_values(payload):
            p = path.lower()
            if p.endswith("target.teamnum") or p.endswith("target.team_num") or p.endswith("target.team"):
                try:
                    if int(value) == 0:
                        return True
                except Exception:
                    continue
    return False


def target_has_colored_team(*payloads: Any) -> bool:
    """True if the tracked player is assigned to a real team/color.

    Team 0 = blue and Team 1 = orange. Both are valid match teams.
    Training/freeplay usually has no real team assignment and no match timer.
    """
    for payload in payloads:
        if not isinstance(payload, (dict, list)):
            continue
        for path, value in iter_json_values(payload):
            p = path.lower()
            try:
                if p.endswith(("target.teamnum", "target.team_num", "target.team")):
                    if int(value) in (0, 1):
                        return True
            except Exception:
                pass
            if p.endswith(("target.teamcolor", "target.team_color", "target.color", "target.colour")):
                if str(value).strip().lower() in {"blue", "orange", "bleu", "orange team"}:
                    return True
    return False


def payload_has_match_time_limit(*payloads: Any) -> bool:
    """Detect the presence of a real match timer.

    User rule: if there is no timer in the game, it is Freeplay/Libre and must not
    count. We check timer PRESENCE, not only positive value, because a real match
    can show 0, 0:00 or overtime states while still having a timer object.
    """
    time_keys = (
        "timeremaining", "time_remaining", "remainingtime", "remaining_time",
        "gametimeremaining", "game_timer_remaining",
        "gametime", "game_time", "matchtime", "match_time",
        "secondsremaining", "seconds_remaining",
        "totaltime", "total_time",
        "countdown", "count_down",
        "overtime", "over_time",
        "clock", "gameclock", "game_clock",
        "time_seconds", "seconds"
    )
    for payload in payloads:
        if not isinstance(payload, (dict, list)):
            continue
        for path, value in iter_json_values(payload):
            p = path.lower().replace(".", "_").replace("-", "_")
            if not any(k in p for k in time_keys):
                continue
            if isinstance(value, bool):
                # A boolean overtime flag alone is not enough, but it means a time context exists
                # only if the key itself explicitly says overtime.
                if "overtime" in p or "over_time" in p:
                    return True
                continue
            if value is None:
                continue
            text_value = str(value).strip().lower()
            if text_value in {"", "none", "null", "false"}:
                continue
            # Any numeric/string timer value means a real match timer is present.
            return True
    return False

def is_strict_training_context(players: Any, *payloads: Any) -> bool:
    """Heuristic training detection when there is no explicit Freeplay/Training label."""
    player_count = count_distinct_players(players)
    if player_count >= 2:
        return False
    if players_have_multiple_teams(players):
        return False
    if target_has_colored_team(*payloads):
        return False
    if payload_has_match_time_limit(*payloads):
        return False
    reason = detect_non_competitive_context(*payloads)
    if reason:
        reason_l = str(reason).lower()
        return any(k in reason_l for k in ("training", "freeplay", "free play", "entraînement", "entrainement", "workshop", "tutorial", "playlist non ranked"))
    return False


def normalize_players_collection(players: Any) -> List[Dict[str, Any]]:
    """Normalise la liste joueurs.

    StatsAPI/SOS ne renvoie pas toujours Players sous la même forme :
    - Steam/BakkesMod : souvent list[dict]
    - Epic : souvent dict indexé par EpicID/UniqueID
    """
    normalized: List[Dict[str, Any]] = []

    if isinstance(players, list):
        iterable = players
    elif isinstance(players, dict):
        # Si le dict ressemble lui-même à un joueur, on le garde.
        player_like_keys = {"Name", "name", "PlayerName", "playerName", "TeamNum", "team", "Team", "EpicID", "UniqueId", "unique_id", "PrimaryId", "PrimaryID", "primaryId", "primary_id"}
        if any(k in players for k in player_like_keys):
            iterable = [players]
        else:
            iterable = list(players.values())
    else:
        iterable = []

    for item in iterable:
        if isinstance(item, dict):
            normalized.append(item)

    return normalized


def normalize_teams_collection(teams: Any) -> List[Dict[str, Any]]:
    if isinstance(teams, list):
        return [t for t in teams if isinstance(t, dict)]
    if isinstance(teams, dict):
        if any(k in teams for k in ("TeamNum", "team", "Team", "Score", "score", "Name", "name")):
            return [teams]
        return [t for t in teams.values() if isinstance(t, dict)]
    return []


def parse_team_num_value(value: Any) -> Optional[int]:
    """Normalise une valeur team API en 0/1 quand c'est possible.

    Certaines APIs renvoient TeamNum=0/1, d'autres Team="Blue"/"Orange"
    ou Team="Team 0"/"Team 1". Une vraie chaîne de nom d'équipe
    n'est pas convertie ici : elle sera résolue via la collection Teams.
    """
    if isinstance(value, bool) or value is None:
        return None
    try:
        if isinstance(value, (int, float)):
            v = int(value)
            return v if v in (0, 1) else None
        txt = str(value).strip().lower()
        if not txt:
            return None
        if txt.lstrip("-").isdigit():
            v = int(txt)
            return v if v in (0, 1) else None
        compact = re.sub(r"[^a-z0-9àâäéèêëîïôöùûüç]+", " ", txt).strip()
        if compact in {"blue", "bleu", "team blue", "blue team", "equipe bleue", "équipe bleue", "team 0"}:
            return 0
        if compact in {"orange", "team orange", "orange team", "equipe orange", "équipe orange", "team 1"}:
            return 1
        m = re.fullmatch(r"(?:team|equipe|équipe)\s*([01])", compact)
        if m:
            return int(m.group(1))
    except Exception:
        return None
    return None


def team_display_name(team: Dict[str, Any]) -> str:
    for key in ("Name", "name", "TeamName", "teamName", "ClubName", "clubName", "DisplayName", "displayName"):
        value = team.get(key)
        if value not in (None, "", False):
            return str(value).strip()
    return ""


def is_generic_team_label(value: Any) -> bool:
    """True pour les libellés API par défaut qui ne prouvent pas une vraie équipe.

    StatsAPI peut renvoyer "Team 0" / "Team 1" même en entraînement ou
    quand seul le joueur local est présent. Ces libellés désignent uniquement la
    couleur/côté blue/orange et ne doivent donc pas valider la présence d'une
    team adverse.
    """
    text = str(value or "").strip().lower()
    if not text:
        return False
    compact = re.sub(r"[^a-z0-9àâäéèêëîïôöùûüç]+", " ", text).strip()
    return compact in {
        "0", "1",
        "team 0", "team 1",
        "equipe 0", "equipe 1", "équipe 0", "équipe 1",
        "blue", "bleu", "orange",
        "blue team", "team blue", "orange team", "team orange",
        "equipe bleue", "équipe bleue", "equipe orange", "équipe orange",
    }


def team_has_real_display_name(team: Dict[str, Any]) -> bool:
    name = team_display_name(team)
    return bool(name and not is_generic_team_label(name))


def team_number_from_obj(team: Dict[str, Any], fallback: Optional[int] = None) -> Optional[int]:
    for key in (
        "TeamNum", "teamNum", "team_num",
        "TeamIndex", "teamIndex", "team_index",
        "Index", "index", "Id", "id", "TeamID", "teamID", "teamId", "team_id",
        "Team", "team", "Color", "color", "Colour", "colour", "TeamColor", "teamColor", "team_color",
    ):
        if key in team:
            parsed = parse_team_num_value(team.get(key))
            if parsed in (0, 1):
                return parsed
    if fallback in (0, 1):
        return int(fallback)
    return None


def team_number_from_name(team_name: Any, teams: Any) -> Optional[int]:
    wanted = str(team_name or "").strip().lower()
    if not wanted:
        return None
    normalized = normalize_teams_collection(teams)
    for idx, team in enumerate(normalized):
        name = team_display_name(team).lower()
        if name and name == wanted:
            return team_number_from_obj(team, idx if len(normalized) >= 2 else None)
    return None


def team_score_from_obj(team: Dict[str, Any]) -> Optional[int]:
    for key in ("Score", "score", "Goals", "goals", "TeamScore", "teamScore", "team_score"):
        if key not in team:
            continue
        value = team.get(key)
        if isinstance(value, bool) or value is None:
            continue
        try:
            return int(value)
        except Exception:
            m = re.search(r"-?\d+", str(value))
            if m:
                try:
                    return int(m.group(0))
                except Exception:
                    pass
    return None


def extract_players_collection(*payloads: Any) -> List[Dict[str, Any]]:
    """Trouve la collection Players, même si elle est dans Game.Players ou players."""
    candidates: List[Any] = []
    for payload in payloads:
        if not isinstance(payload, (dict, list)):
            continue
        if isinstance(payload, dict):
            for direct_key in ("Players", "players", "PlayerStates", "playerStates"):
                if direct_key in payload:
                    candidates.append(payload.get(direct_key))
            game = payload.get("Game") or payload.get("game")
            if isinstance(game, dict):
                for direct_key in ("Players", "players", "PlayerStates", "playerStates"):
                    if direct_key in game:
                        candidates.append(game.get(direct_key))

        for path, value in iter_json_values(payload):
            tail = path.lower().split(".")[-1]
            if tail in {"players", "playerstates", "player_states"} and isinstance(value, (list, dict)):
                candidates.append(value)

    best: List[Dict[str, Any]] = []
    for candidate in candidates:
        normalized = normalize_players_collection(candidate)
        if len(normalized) > len(best):
            best = normalized
    return best


def _first_player_from_collection(players: Any) -> Optional[Dict[str, Any]]:
    normalized = normalize_players_collection(players)
    return normalized[0] if normalized else None


def _expand_statsapi_payloads(*payloads: Any) -> List[Any]:
    expanded_payloads: List[Any] = []
    for payload in payloads:
        expanded_payloads.append(payload)
        if isinstance(payload, dict):
            data = payload.get("Data") if "Data" in payload else payload.get("data")
            if isinstance(data, str):
                try:
                    data = json.loads(data)
                except Exception:
                    data = None
            if isinstance(data, dict):
                expanded_payloads.append(data)
    return expanded_payloads


def _players_collections_with_priority(*payloads: Any) -> List[List[Dict[str, Any]]]:
    """Collections Players ordonnées pour trouver le joueur local.

    On garde d'abord le tableau direct `Players` du payload courant, car dans la
    StatsAPI utilisée par l'app c'est celui qui est placé juste sous MatchGUID.
    `Game.Players` et les collections imbriquées restent des fallbacks.
    """
    collections: List[List[Dict[str, Any]]] = []
    seen_ids: set = set()

    def add_collection(candidate: Any) -> None:
        normalized = normalize_players_collection(candidate)
        if not normalized:
            return
        key = tuple(id(p) for p in normalized)
        if key in seen_ids:
            return
        seen_ids.add(key)
        collections.append(normalized)

    expanded = _expand_statsapi_payloads(*payloads)

    for payload in expanded:
        if not isinstance(payload, dict):
            continue
        for direct_key in ("Players", "players", "PlayerStates", "playerStates"):
            if direct_key in payload:
                add_collection(payload.get(direct_key))

    for payload in expanded:
        if not isinstance(payload, dict):
            continue
        game = payload.get("Game") or payload.get("game")
        if isinstance(game, dict):
            for direct_key in ("Players", "players", "PlayerStates", "playerStates"):
                if direct_key in game:
                    add_collection(game.get(direct_key))

    for payload in expanded:
        if not isinstance(payload, (dict, list)):
            continue
        for path, value in iter_json_values(payload):
            tail = path.lower().split(".")[-1]
            if tail in {"players", "playerstates", "player_states"} and isinstance(value, (list, dict)):
                add_collection(value)

    return collections


def player_identity_values(player: Dict[str, Any]) -> List[str]:
    values: List[str] = []
    if not isinstance(player, dict):
        return values
    identity_keys = {
        "name", "playername", "player_name", "displayname", "display_name",
        "epicid", "epic_id", "epicaccountid", "epic_account_id",
        "uniqueid", "unique_id", "primaryid", "primary_id", "primaryaccountid", "primary_account_id",
        "id", "uid", "userid", "user_id",
        "steamid", "steam_id", "steamid64", "steam_id64",
        "platformid", "platform_id", "onlineid", "online_id",
    }
    for path, value in iter_json_values(player):
        if isinstance(value, (dict, list)) or value in (None, "", False):
            continue
        tail = path.lower().split(".")[-1].replace("-", "_")
        compact = tail.replace("_", "")
        if tail in identity_keys or compact in {k.replace("_", "") for k in identity_keys}:
            values.append(str(value).strip())
    return [v for v in values if v]




def _normalize_rls_platform_token(platform: Any) -> str:
    token = str(platform or "auto").strip().lower()
    token = token.replace("onlineplatform_", "")
    token = token.replace("platform_", "")
    token = token.replace("platform", "")
    token = token.replace(" ", "").replace("-", "").replace(".", "")
    mapping = {
        "automatic": "auto",
        "detect": "auto",
        "autodetect": "auto",
        "steamworks": "steam",
        "steam": "steam",
        "epicgames": "epic",
        "epicgame": "epic",
        "epic": "epic",
        "eos": "epic",
        "egs": "epic",
        "xbox": "xbl",
        "xboxlive": "xbl",
        "live": "xbl",
        "xbl": "xbl",
        "playstation": "psn",
        "playstationnetwork": "psn",
        "ps4": "psn",
        "ps5": "psn",
        "psn": "psn",
        "nintendo": "switch",
        "nintendoswitch": "switch",
        "switch": "switch",
    }
    return mapping.get(token, "auto")


def split_rls_platform_and_primary_id(value: Any, fallback_platform: str = "auto") -> Tuple[str, str]:
    """Nettoie un PrimaryId StatsAPI/SOS et retourne (platform, id).

    Exemple correct :
    OnlinePlatform_Epic|ABC123|...  -> ("epic", "ABC123")
    OnlinePlatform_Steam|7656...|... -> ("steam", "7656...")

    La plateforme est toujours en minuscule.
    L'id retourné ne contient jamais la plateforme, pour éviter :
    /player/epic/OnlinePlatform_Epic|id|...
    """
    platform = _normalize_rls_platform_token(fallback_platform)
    raw = str(value or "").strip()
    if not raw:
        return platform, ""

    blocked = {
        "auto", "automatic", "detect", "autodetect",
        "steam", "steamworks", "epic", "epicgames", "eos", "egs",
        "xbl", "xbox", "xboxlive", "psn", "playstation", "switch",
        "onlineplatform_steam", "onlineplatform_epic", "onlineplatform_eos",
        "platform_steam", "platform_epic", "platform_eos",
        "true", "false", "none", "null", "0", "1",
    }

    def clean_part(part: Any) -> str:
        s = str(part or "").strip().strip("\"'` ").strip()
        s = s.strip("[]{}()").strip()
        low_key = s.split("=", 1)[0].split(":", 1)[0].strip().lower().replace("_", "")
        if "=" in s and low_key in {"primaryid", "primaryaccountid", "id", "value", "uid"}:
            s = s.split("=", 1)[1].strip()
        elif ":" in s and low_key in {"primaryid", "primaryaccountid", "id", "value", "uid"}:
            s = s.split(":", 1)[1].strip()

        # Retire la plateforme si elle est encore collée à l'identifiant.
        s = re.sub(
            r"^(?:onlineplatform_|platform_)?(?:steamworks|steam|epicgames|epic|eos|egs|xbl|xboxlive|xbox|psn|playstation|switch|nintendo)(?:\s|:|-|/|\|)+",
            "",
            s,
            flags=re.I,
        )
        return s.strip().strip("|").strip()

    def detect_platform_in_text(part: Any) -> str:
        s = str(part or "").strip().lower()
        if not s:
            return "auto"
        for pattern, normalized in (
            (r"(?:onlineplatform_|platform_)?(?:steamworks|steam)\b", "steam"),
            (r"(?:onlineplatform_|platform_)?(?:epicgames|epic|eos|egs)\b", "epic"),
            (r"(?:onlineplatform_|platform_)?(?:xbl|xboxlive|xbox)\b", "xbl"),
            (r"(?:onlineplatform_|platform_)?(?:psn|playstation)\b", "psn"),
            (r"(?:onlineplatform_|platform_)?(?:switch|nintendo)\b", "switch"),
        ):
            if re.search(pattern, s, flags=re.I):
                return normalized
        return _normalize_rls_platform_token(s)

    # On garde la priorité à ce qui est inscrit entre | |
    # Exemple : OnlinePlatform_Epic|PRIMARY_ID|... => PRIMARY_ID
    raw_parts: List[str] = []
    if "|" in raw:
        raw_parts.extend([p for p in raw.split("|") if str(p).strip()])
        raw_parts = re.findall(r"\|([^|]+)\|", raw) + raw_parts
    else:
        raw_parts.append(raw)

    candidates: List[str] = []
    for idx, part in enumerate(raw_parts):
        part_s = str(part or "").strip()
        detected_platform = detect_platform_in_text(part_s)
        if detected_platform != "auto":
            platform = detected_platform
            # si la plateforme est avant l'id, prend le morceau suivant
            if idx + 1 < len(raw_parts):
                nxt = clean_part(raw_parts[idx + 1])
                if nxt and _normalize_rls_platform_token(nxt) == "auto":
                    candidates.append(nxt)
            continue
        candidates.append(clean_part(part_s))

    candidates.append(clean_part(raw))

    for candidate in candidates:
        candidate = clean_part(candidate)
        if not candidate:
            continue
        low = candidate.casefold().replace(" ", "").replace("-", "_")
        if low in blocked:
            continue
        if _normalize_rls_platform_token(candidate) != "auto":
            continue
        if len(candidate) < 3:
            continue
        return platform, candidate

    return platform, ""


def _valid_primary_id_value(value: Any) -> str:
    _platform, primary_id = split_rls_platform_and_primary_id(value)
    return primary_id


def extract_primary_id_from_player_obj(player: Dict[str, Any]) -> str:
    """Retourne uniquement le PrimaryId du joueur local quand il existe.

    Pour l'API RLS, le PrimaryId est plus fiable que le pseudo affiché dans
    `Player/Name`, surtout si le pseudo change ou si plusieurs joueurs sont
    présents dans le JSON.
    """
    if not isinstance(player, dict):
        return ""

    direct_keys = (
        "PrimaryId", "PrimaryID", "primaryId", "primaryID", "primary_id",
        "PrimaryID64", "primaryID64", "primary_id64",
        "PrimaryAccountId", "primaryAccountId", "primary_account_id",
    )
    for key in direct_keys:
        pid = _valid_primary_id_value(player.get(key))
        if pid:
            return pid

    for path, value in iter_json_values(player):
        pid = _valid_primary_id_value(value)
        if not pid:
            continue

        path_l = path.lower().replace("-", "_")
        tail = path_l.split(".")[-1]
        compact_tail = tail.replace("_", "")
        compact_path = path_l.replace("_", "")

        if compact_tail in {
            "primaryid", "primaryid64", "primaryaccountid",
            "primaryuniqueid", "primaryplatformid",
        }:
            return pid

        # Cas où PrimaryId est un objet : {"PrimaryId": {"Id": "..."}}
        if "primaryid" in compact_path and compact_tail in {"id", "value", "uid", "uniqueid", "accountid"}:
            return pid

    return ""


def tracker_platform_from_primary_id(player: Dict[str, Any], primary_id: str, configured_platform: str = "auto") -> str:
    """Déduit la plateforme RLS en minuscule sans dupliquer la plateforme dans l'id."""
    configured = _normalize_rls_platform_token(configured_platform)
    if configured != "auto":
        return configured

    pid = str(primary_id or "").strip()

    if isinstance(player, dict):
        for path, value in iter_json_values(player):
            if isinstance(value, (dict, list)) or value in (None, "", False):
                continue

            platform, clean_id = split_rls_platform_and_primary_id(value)
            if platform != "auto" and (not pid or clean_id == pid or pid in str(value)):
                return platform

            path_l = str(path or "").lower()
            value_l = str(value or "").lower()
            platform_from_path = _normalize_rls_platform_token(path_l)
            platform_from_value = _normalize_rls_platform_token(value_l)
            if platform_from_path != "auto":
                return platform_from_path
            if platform_from_value != "auto":
                return platform_from_value

    if re.fullmatch(r"7656119\d{10}", pid) or re.fullmatch(r"\d{15,20}", pid):
        return "steam"

    return "epic"


def player_matches_identity_hint(player: Dict[str, Any], hint: Any) -> bool:
    hint_s = str(hint or "").strip()
    if not hint_s or not isinstance(player, dict):
        return False
    hint_cf = hint_s.casefold()
    for value in player_identity_values(player):
        if value.casefold() == hint_cf:
            return True
    return False


def find_player_by_identity_hint(players: Any, hint: Any) -> Optional[Dict[str, Any]]:
    for player in normalize_players_collection(players):
        if player_matches_identity_hint(player, hint):
            return player
    return None


def _truthy_local_marker(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return int(value) == 1
    if isinstance(value, str):
        return value.strip().casefold() in {"1", "true", "yes", "y", "on", "local", "self", "me"}
    return False


def player_has_local_marker(player: Dict[str, Any]) -> bool:
    """Détecte les champs explicites qui désignent le joueur de ce PC/app."""
    if not isinstance(player, dict):
        return False
    exact_local_keys = {
        "islocal", "local", "localplayer", "islocalplayer", "bislocal", "bislocalplayer",
        "isprimary", "primary", "primaryplayer", "isprimaryplayer",
        "isme", "is_me", "self", "isself", "is_self",
        "owningplayer", "owner", "isowner", "is_owner",
        "iscontrolled", "is_controlled", "playercontrolled", "player_controlled",
    }
    for path, value in iter_json_values(player):
        tail = path.lower().split(".")[-1].replace("-", "_")
        compact = tail.replace("_", "")
        if compact in {k.replace("_", "") for k in exact_local_keys} and _truthy_local_marker(value):
            return True
        if "local" in compact and "team" not in compact and _truthy_local_marker(value):
            return True
    return False


def extract_local_identity_hints_from_payload(*payloads: Any) -> List[str]:
    """Cherche des indices explicites de joueur local hors du tableau Players."""
    hints: List[str] = []
    identity_tails = {
        "name", "playername", "player_name", "displayname", "display_name",
        "epicid", "epic_id", "uniqueid", "unique_id", "primaryid", "primary_id",
        "steamid", "steam_id", "id", "onlineid", "online_id", "platformid", "platform_id",
    }
    local_tokens = ("local", "primary", "self", "own", "main")
    for payload in _expand_statsapi_payloads(*payloads):
        if not isinstance(payload, (dict, list)):
            continue
        for path, value in iter_json_values(payload):
            if isinstance(value, (dict, list)) or value in (None, "", False):
                continue
            path_l = path.lower().replace("-", "_")
            tail = path_l.split(".")[-1]
            compact_tail = tail.replace("_", "")
            if not any(token in path_l for token in local_tokens):
                continue
            if tail in identity_tails or compact_tail in {t.replace("_", "") for t in identity_tails}:
                hints.append(str(value).strip())
    # ordre stable sans doublons
    out: List[str] = []
    seen: set = set()
    for hint in hints:
        key = hint.casefold()
        if hint and key not in seen:
            seen.add(key)
            out.append(hint)
    return out


def extract_local_player_candidate_from_payload(
    *payloads: Any,
    current_player_name: str = "",
    forced_player_hint: str = "",
) -> Tuple[Optional[Dict[str, Any]], str]:
    """Retourne le joueur local de l'app, jamais un autre joueur au hasard.

    Le pseudo/ID saisi dans API RLS ne doit pas décider des stats principales :
    il sert aux requêtes RLS uniquement. Pour l'overlay principal, on utilise les
    indices fiables du JSON, le joueur Freeplay déjà verrouillé, puis seulement
    `Players[0]` comme fallback compatible StatsAPI/SOS.
    """
    collections = _players_collections_with_priority(*payloads)
    all_players = [player for collection in collections for player in collection]

    # forced_player_hint est conservé dans la signature pour compatibilité avec
    # les anciens appels, mais il est volontairement ignoré pour les stats
    # principales : API RLS ne doit plus forcer detected_player_name.

    for player in all_players:
        if player_has_local_marker(player):
            return player, "champ local du JSON"

    for hint in extract_local_identity_hints_from_payload(*payloads):
        for player in all_players:
            if player_matches_identity_hint(player, hint):
                return player, "indice local du JSON"

    if current_player_name:
        for player in all_players:
            if player_matches_identity_hint(player, current_player_name):
                return player, "joueur déjà verrouillé"

    if collections and collections[0]:
        return collections[0][0], "fallback Players[0]"

    return None, "aucun joueur local"


def extract_primary_player_from_payload(*payloads: Any) -> Optional[Dict[str, Any]]:
    player, _reason = extract_local_player_candidate_from_payload(*payloads)
    return player


def player_display_name_from_obj(player: Dict[str, Any]) -> str:
    for key in ("Name", "name", "PlayerName", "playerName", "player_name", "DisplayName", "displayName", "display_name", "EpicID", "UniqueId", "unique_id"):
        value = player.get(key)
        if value not in (None, "", False):
            return str(value).strip()
    return ""


def player_team_num_from_obj(player: Dict[str, Any], teams: Any = None) -> Optional[int]:
    for key in ("TeamNum", "teamNum", "team_num", "Team", "team", "TeamIndex", "teamIndex", "team_index"):
        if key not in player:
            continue
        parsed = parse_team_num_value(player.get(key))
        if parsed in (0, 1):
            return int(parsed)
        if teams is not None:
            by_name = team_number_from_name(player.get(key), teams)
            if by_name in (0, 1):
                return int(by_name)
    return None


def extract_teams_collection(*payloads: Any) -> List[Dict[str, Any]]:
    candidates: List[Any] = []
    for payload in payloads:
        if not isinstance(payload, (dict, list)):
            continue
        if isinstance(payload, dict):
            game = payload.get("Game") or payload.get("game")
            if isinstance(game, dict):
                for direct_key in ("Teams", "teams"):
                    if direct_key in game:
                        candidates.append(game.get(direct_key))
            for direct_key in ("Teams", "teams"):
                if direct_key in payload:
                    candidates.append(payload.get(direct_key))

        for path, value in iter_json_values(payload):
            tail = path.lower().split(".")[-1]
            if tail in {"teams"} and isinstance(value, (list, dict)):
                candidates.append(value)

    best: List[Dict[str, Any]] = []
    for candidate in candidates:
        normalized = normalize_teams_collection(candidate)
        if len(normalized) > len(best):
            best = normalized
    return best


def teams_have_multiple_sides(teams: Any) -> bool:
    normalized = normalize_teams_collection(teams)
    if len(normalized) < 2:
        return False

    # Les noms génériques "Team 0" / "Team 1" ne prouvent pas une vraie
    # équipe adverse : ce sont seulement les côtés blue/orange. En solo, ils
    # peuvent apparaître en freeplay et ne doivent pas déclencher un comptage.
    real_named_team_count = sum(1 for team in normalized if team_has_real_display_name(team))
    if real_named_team_count >= 1:
        return True

    # Si deux objets ont simplement TeamNum=0/1, Name=Team 0/Team 1 ou des
    # scores par défaut, on ne les considère pas comme une détection team.
    # Les vrais matchs restent validés par les joueurs détectés (>= 2) ou par
    # une vraie team nommée ci-dessus.
    return False


def normalize_runtime_platform(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = text.replace("onlineplatform_", "").replace("platform_", "").replace(" ", "")
    if text in {"steam", "steamworks"}:
        return "steam"
    if text in {"epic", "epicgames", "eos", "egs", "epicgamesstore"}:
        return "epic"
    return "auto"


def detect_api_platform_context(configured_platform: str, players: Any, *payloads: Any) -> str:
    """Détection simple Steam/Epic pour la logique match/freeplay/privé."""
    configured = normalize_runtime_platform(configured_platform)
    if configured in {"steam", "epic"}:
        return configured

    for player in normalize_players_collection(players):
        keys = {str(k).lower(): v for k, v in player.items()}
        if any(k in keys for k in ("epicid", "epic_id", "epicuserid", "epic_user_id", "eosid", "productuserid", "product_user_id")):
            return "epic"
        if any(k in keys for k in ("steamid", "steam_id", "steamid64", "steam_id64")):
            return "steam"
        for key in ("platform", "platformtype", "onlineplatform", "platformname"):
            if key in keys:
                p = normalize_runtime_platform(keys.get(key))
                if p in {"steam", "epic"}:
                    return p
        for value in keys.values():
            s = str(value or "")
            if re.fullmatch(r"7656119\d{10}", s):
                return "steam"

    for payload in payloads:
        if not isinstance(payload, (dict, list)):
            continue
        for path, value in iter_json_values(payload):
            p = path.lower().replace(".", "_").replace("-", "_")
            v = str(value or "").strip()
            nv = normalize_runtime_platform(v)
            if any(k in p for k in ("platform", "onlineplatform", "provider", "accounttype", "account_type")) and nv in {"steam", "epic"}:
                return nv
            if any(k in p for k in ("epic", "eos", "product_user", "productuserid")) and value not in (None, "", False):
                return "epic"
            if any(k in p for k in ("steam", "steamid", "steam_id")) and value not in (None, "", False):
                return "steam"
            if re.fullmatch(r"7656119\d{10}", v):
                return "steam"

    return "auto"


def detect_unlimited_boost_context(*payloads: Any) -> Optional[str]:
    """Epic Freeplay : joueur seul + boost illimité."""
    for payload in payloads:
        if not isinstance(payload, (dict, list)):
            continue
        for path, value in iter_json_values(payload):
            p = path.lower().replace(".", "_").replace("-", "_")
            if "boost" not in p and not (isinstance(value, str) and "boost" in value.lower()):
                continue

            if any(k in p for k in (
                "unlimitedboost", "unlimited_boost", "boostunlimited", "boost_unlimited",
                "infiniteboost", "infinite_boost", "boostamount", "boost_amount",
                "boostoption", "boost_option", "mutator_boost", "mutators_boost"
            )):
                if _truthy_api_value(value):
                    return path
                if isinstance(value, str):
                    txt = value.lower().replace("_", " ").replace("-", " ")
                    if any(k in txt for k in ("unlimited", "infinite", "illimité", "illimite", "illimitee")):
                        return f"{path}={value}"

            if isinstance(value, str):
                txt = value.lower().replace("_", " ").replace("-", " ")
                if "boost" in txt and any(k in txt for k in ("unlimited", "infinite", "illimité", "illimite", "illimitee")):
                    return f"{path}={value}"

    return None


def detect_private_explicit_context(*payloads: Any) -> Optional[str]:
    """Indices explicites match privé/custom, volontairement stricts."""
    for payload in payloads:
        if not isinstance(payload, (dict, list)):
            continue
        for path, value in iter_json_values(payload):
            p = path.lower().replace(".", "_").replace("-", "_")
            txt = str(value or "").lower().replace("_", " ").replace("-", " ")

            if any(k in p for k in (
                "private_match", "privatematch", "is_private", "isprivate",
                "custom_match", "custommatch", "is_custom", "iscustom",
                "exhibition", "showmatch"
            )) and value not in (None, "", False):
                return path

            if isinstance(value, str) and any(k in txt for k in (
                "private match", "privatematch", "match privé", "match prive",
                "custom match", "custom game", "partie privée", "partie privee",
                "exhibition", "showmatch"
            )):
                return f"{path}={value}"

    return None


def detect_spectator_observer_context(*payloads: Any) -> Optional[str]:
    """Match privé : présence d'un mode spectateur / observateur.

    Détection volontairement simple :
    - clé API contenant spectator / spectate / observer / observateur ;
    - valeur texte contenant spectator / observer / observateur ;
    - joueur explicitement placé en team Spectator/Observer ou TeamNum = -1.

    Aucun indice de lobby, admin, custom ou server n'est utilisé ici.
    """
    for payload in payloads:
        if not isinstance(payload, (dict, list)):
            continue

        for path, value in iter_json_values(payload):
            p = path.lower().replace(".", "_").replace("-", "_")
            txt = str(value or "").strip().lower().replace("_", " ").replace("-", " ")

            if any(k in p for k in (
                "spectator", "spectate", "spectating",
                "observer", "observateur", "observers"
            )):
                if value not in (None, "", False, [], {}):
                    if isinstance(value, str) and txt in {"false", "0", "none", "null", "no", "off"}:
                        continue
                    return path

            if isinstance(value, str) and any(k in txt for k in (
                "spectator", "spectate", "spectating",
                "observer", "observateur", "mode observateur"
            )):
                return f"{path}={value}"

            # Certains payloads indiquent un joueur observateur par team -1.
            tail = p.split("_")[-1]
            if tail in {"teamnum", "team", "teamindex"}:
                try:
                    if int(value) == -1:
                        return f"{path}=-1"
                except Exception:
                    pass

    return None



def classify_rl_match_context(platform: str, players: Any, teams: Any, *payloads: Any) -> Dict[str, Any]:
    """Détection propre du mode de jeu : Freeplay / Privé / Ranked.

    Règles demandées :
    1. Freeplay / jeu libre si le seul joueur détecté est le joueur principal,
       sans team adverse et sans autre joueur.
    2. Match privé si présence d'un mode spectateur / observateur.
    3. Match ranked si au moins 2 joueurs ou 2 teams sont détectés, et aucune
       condition Freeplay/Privé.
    """
    normalized_players = normalize_players_collection(players)
    player_count = count_distinct_players(normalized_players)
    playlist = extract_playlist_from_payload(*payloads)
    platform = normalize_runtime_platform(platform)

    boost_reason = detect_unlimited_boost_context(*payloads)
    spectator_reason = detect_spectator_observer_context(*payloads)
    competitive_reason = detect_competitive_context(*payloads)
    private_reason = detect_private_context(*payloads)
    team_match_present = teams_have_multiple_sides(teams)

    # Priorité 1 : Freeplay solo strict.
    # Si l'API ne voit que le joueur principal, sans autre joueur et sans deux
    # teams réelles, on considère que c'est du Freeplay même si un champ ranked
    # temporaire reste dans le payload. Une vraie partie reprendra le dessus dès
    # qu'un adversaire ou deux teams seront détectés.
    if player_count < 2 and not team_match_present:
        return {
            "type": "freeplay",
            "reason": f"joueur seul détecté sans team adverse ({player_count})",
            "playlist": playlist,
            "player_count": player_count,
            "platform": platform,
        }

    # Priorité 2 : ranked explicite. Les playlists officielles 10/11/13 et les
    # champs isRanked/competitive sont pris en compte seulement après avoir exclu
    # le cas solo/freeplay strict ci-dessus.
    if competitive_reason:
        return {
            "type": "ranked",
            "reason": f"ranked détecté ({competitive_reason})",
            "playlist": playlist,
            "player_count": player_count,
            "platform": platform,
        }

    # Priorité 3 : Freeplay / jeu libre par boost illimité.

    if boost_reason and not team_match_present and not private_reason and not spectator_reason:
        return {
            "type": "freeplay",
            "reason": f"boost illimité détecté ({boost_reason})",
            "playlist": playlist,
            "player_count": player_count,
            "platform": platform,
        }

    # Priorité 4 : match privé via spectateur/observateur OU champs private/custom.
    if spectator_reason or private_reason:
        reason = spectator_reason or private_reason
        return {
            "type": "private",
            "reason": f"match privé/showmatch détecté ({reason})",
            "playlist": playlist,
            "player_count": player_count,
            "platform": platform,
        }

    # Priorité 5 : fallback ranked si 2 joueurs minimum ou deux teams et aucune condition au-dessus.
    # Utile pour les APIs qui ne renvoient pas clairement le flag ranked pendant le live.
    return {
        "type": "ranked",
        "reason": f"{player_count} joueurs ou équipes détectés, aucun freeplay/privé explicite",
        "playlist": playlist,
        "player_count": player_count,
        "platform": platform,
    }


def payload_has_epic_private_player_hint(*payloads: Any) -> Optional[str]:
    """Indices privés Epic/SOS stricts.

    Important : ne pas utiliser `match_guid`, `server_name` ou un simple lobby non vide
    comme preuve de match privé, car ces champs existent aussi en ranked.
    """
    for payload in payloads:
        if not isinstance(payload, (dict, list)):
            continue
        for path, value in iter_json_values(payload):
            p = path.lower().replace(".", "_").replace("-", "_")
            txt = str(value or "").lower().replace("_", " ").replace("-", " ")

            # Clés réellement privées/custom. On évite les clés génériques présentes en ranked.
            if any(k in p for k in (
                "private_match", "privatematch",
                "custom_match", "custommatch",
                "custom_game", "customgame",
                "is_private", "isprivate",
                "is_custom", "iscustom",
                "showmatch", "exhibition",
            )):
                if value not in (None, "", False):
                    return path

            if isinstance(value, str) and any(k in txt for k in (
                "private match", "privatematch", "private",
                "custom match", "custom game", "custom",
                "exhibition", "showmatch"
            )):
                return f"{path}={value}"

    return None


def count_distinct_players(players: Any) -> int:
    normalized = normalize_players_collection(players)
    names = set()
    ids = set()
    total = 0
    for p in normalized:
        name = str(
            p.get("Name")
            or p.get("name")
            or p.get("PlayerName")
            or p.get("playerName")
            or p.get("PersonaName")
            or ""
        ).strip().lower()
        uid = str(
            p.get("UniqueId")
            or p.get("unique_id")
            or p.get("EpicID")
            or p.get("epic_id")
            or p.get("SteamID")
            or p.get("steam_id")
            or p.get("PlatformID")
            or ""
        ).strip().lower()

        if name:
            names.add(name)
        if uid:
            ids.add(uid)
        total += 1

    # Sur Epic, les noms peuvent parfois être vides mais les IDs existent.
    return max(total, len(names), len(ids))


def players_have_multiple_teams(players: Any) -> bool:
    normalized = normalize_players_collection(players)
    teams = set()
    for p in normalized:
        for key in ("TeamNum", "team_num", "Team", "team", "TeamIndex", "teamIndex"):
            if key in p:
                try:
                    teams.add(int(p.get(key)))
                    break
                except Exception:
                    pass
    return len(teams) >= 2


def _truthy_api_value(value: Any) -> bool:
    if isinstance(value, bool):
        return bool(value)
    if isinstance(value, (int, float)):
        return int(value) == 1
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "oui", "on", "ranked", "competitive", "private", "custom"}


def detect_competitive_context(*payloads: Any) -> Optional[str]:
    """Détecte un vrai match compétitif/ranked via l'API.

    Priorité :
    - PlaylistId ranked officiel : 10 = 1v1, 11 = 2v2, 13 = 3v3
    - booléens/valeurs API du type isRanked, ranked, competitive
    - textes explicites Ranked / Competitive dans les champs Game/Match/Playlist/Mode
    """
    playlist_id = extract_playlist_id_from_payload(*payloads)
    if playlist_id in RANKED_PLAYLIST_IDS:
        return f"playlist ranked #{playlist_id}"

    bool_keys = (
        "isranked", "is_ranked", "ranked",
        "iscompetitive", "is_competitive", "competitive",
        "bcompetitive", "branked", "matchmakingranked", "matchmaking_ranked",
    )
    text_paths = ("game", "match", "playlist", "mode", "state", "type", "queue")
    negative_words = ("unranked", "not ranked", "non ranked", "casual", "private", "privé", "prive", "custom", "exhibition")

    for payload in payloads:
        if not isinstance(payload, (dict, list)):
            continue
        for path, value in iter_json_values(payload):
            p = path.lower().replace(".", "_").replace("-", "_")
            if any(key in p for key in bool_keys):
                if _truthy_api_value(value):
                    return path

            if isinstance(value, str):
                lower_path = path.lower()
                if not any(key in lower_path for key in text_paths):
                    continue
                txt = value.lower().replace("_", " ").replace("-", " ")
                if any(neg in txt for neg in negative_words):
                    continue
                if "ranked" in txt or "competitive" in txt or "compétitif" in txt or "competitif" in txt:
                    return f"{path}={value}"

    return None


def detect_private_context(*payloads: Any) -> Optional[str]:
    """Détecte un match privé/custom/exhibition via l'API.

    Cette détection est distincte de l'entraînement/freeplay :
    private/custom/exhibition = match privé comptable si un joueur est présent.
    """
    private_keywords = (
        "private", "privé", "prive", "privatematch", "private match",
        "custom", "custommatch", "custom match", "custom game",
        "exhibition", "showmatch", "party match", "lobby match"
    )
    bool_keys = (
        "isprivate", "is_private", "private", "privatematch", "private_match",
        "iscustom", "is_custom", "custom", "custommatch", "custom_match",
        "isexhibition", "is_exhibition", "exhibition",
        "showmatch", "isshowmatch", "is_showmatch",
    )
    interesting_paths = (
        "game", "match", "playlist", "mode", "state", "map",
        "private", "custom", "exhibition", "showmatch",
        "type", "queue", "lobby", "server", "epic"
    )

    for payload in payloads:
        if not isinstance(payload, (dict, list)):
            continue
        for path, value in iter_json_values(payload):
            p = path.lower().replace(".", "_").replace("-", "_")

            if any(key in p for key in bool_keys):
                if _truthy_api_value(value):
                    return path

            if isinstance(value, str):
                lower_path = path.lower()
                if not any(key in lower_path for key in interesting_paths):
                    continue
                txt = value.lower().replace("_", " ").replace("-", " ")
                for keyword in private_keywords:
                    if keyword in txt:
                        return f"{path}={value}"

    # Fallback spécial Epic/SOS : certains payloads privés ne contiennent pas
    # littéralement "private", mais exposent des champs de lobby/custom/server.
    hint = payload_has_epic_private_player_hint(*payloads)
    if hint:
        return hint

    return None

def detect_explicit_training_freeplay_context(*payloads: Any) -> Optional[str]:
    """Detect clear Freeplay / Training context.

    This intentionally does NOT include private/custom/exhibition, because private
    matches must still be counted. It is used before the stricter heuristic so
    "Freeplay / Libre" cannot be counted as a real match just because the player
    appears as Team 0/blue in the API.
    """
    hard_keywords = (
        "freeplay", "free play", "jeu libre", "mode libre", "libre",
        "training", "practice", "entrainement", "entraînement",
        "tutorial", "workshop", "garage", "mainmenu", "main menu", "menu",
        "replay", "spectator", "spectateur",
    )
    interesting_paths = ("game", "match", "playlist", "mode", "state", "map", "training", "freeplay", "practice")
    for payload in payloads:
        if not isinstance(payload, (dict, list)):
            continue
        for path, value in iter_json_values(payload):
            if not isinstance(value, str):
                continue
            lower_path = path.lower()
            if not any(key in lower_path for key in interesting_paths):
                continue
            normalized = value.lower().replace("_", " ").replace("-", " ")
            compact = re.sub(r"[^a-z0-9àâäéèêëîïôöùûüç]+", " ", normalized).strip()
            for keyword in hard_keywords:
                if keyword == "libre":
                    # Avoid false positives like a random word containing "libre".
                    if re.search(r"(^|\s)libre($|\s)", compact):
                        return "mode libre / freeplay"
                elif keyword in compact:
                    return keyword
    return None


def extract_server_match_key(*payloads: Any) -> str:
    """Lit le meilleur identifiant match/serveur disponible dans l'API.

    Utilisé uniquement pour savoir si Rocket League vient de changer de serveur/match.
    Cet identifiant ne décide jamais si la partie est Freeplay, privée ou ranked.
    """
    priority_keys = (
        "matchguid", "matchuuid", "matchid",
        "gameguid", "gameuuid", "gameid",
        "serverguid", "serveruuid", "serverid",
        "reservationid", "reservationguid",
        "sessionid", "instanceid",
    )
    secondary_keys = (
        "servername", "serverip", "serveraddress",
        "hostserver", "hostaddress",
    )

    def clean_value(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, (dict, list, tuple, set)):
            return ""
        txt = str(value).strip()
        if not txt:
            return ""
        if txt.lower() in {"0", "none", "null", "false", "undefined", "nan"}:
            return ""
        return txt

    # Priorité aux identifiants stables : match_guid, server_id, reservation_id, etc.
    for payload in payloads:
        if not isinstance(payload, (dict, list)):
            continue
        for path, value in iter_json_values(payload):
            full = re.sub(r"[^a-z0-9]", "", str(path).lower())
            tail = re.sub(r"[^a-z0-9]", "", str(path).split(".")[-1].lower())
            if tail in priority_keys or any(full.endswith(k) for k in priority_keys):
                txt = clean_value(value)
                if txt:
                    return f"api:{tail or 'server'}:{txt}"

    # Fallback : nom/adresse serveur si aucun ID stable n'existe.
    for payload in payloads:
        if not isinstance(payload, (dict, list)):
            continue
        for path, value in iter_json_values(payload):
            full = re.sub(r"[^a-z0-9]", "", str(path).lower())
            tail = re.sub(r"[^a-z0-9]", "", str(path).split(".")[-1].lower())
            if tail in secondary_keys or any(full.endswith(k) for k in secondary_keys):
                txt = clean_value(value)
                if txt:
                    return f"api:{tail or 'server'}:{txt}"

    return ""


def extract_match_key_from_payload(*payloads: Any) -> str:
    """Compatibilité : l'ancienne clé de match utilise maintenant la clé serveur/match."""
    return extract_server_match_key(*payloads)



DEFAULT_CONFIG: Dict[str, Any] = {
    "app_version": APP_VERSION,
    "updater_enabled": True,
    "updater_github_repo": GITHUB_UPDATE_REPO,
    "updater_manifest_url": GITHUB_UPDATE_MANIFEST_URL,
    "updater_last_check": "",
    "statsapi_host": "127.0.0.1",
    "statsapi_port": DEFAULT_STATSAPI_PORT,
    "selected_playlist": "",
    "main_overlay_enabled": True,
    "overlay_exclusive_mode": True,
    "remote_key": "",
    "theme": {
        "mode": "banner",
        "title": "ROCKET LEAGUE LIVE",
        "accent": "#1A8CFF",
        "secondary": "#FF6B00",
        "success": "#3AE08A",
        "gold": "#FFD84D",
        "bg": "rgba(8, 10, 16, 0.88)",
        "text": "#F6F8FF",
        "muted": "#9CA7BC",
        "radius": 22,
        "scale": 100,
        "show_mmr": True,
        "animate": True,
    },
    "auto_detect_playlist": True,
    "auto_detect_mmr_api": True,
    "ignore_training_matches": True,
    "managed_statsapi_ini": "",
    "managed_statsapi_backup": "",
    "saved_sessions": [],
    "mode_sessions": {},
    "tracker_platform": "auto",
    "tracker_interval_sec": 20,
    "tracker_force_player": "",
    # Identité RLS détectée automatiquement depuis StatsAPI/SOS.
    # Elle est sauvegardée dans %AppData% après la première détection valide
    # pour continuer les recherches API RLS si le JSON ne renvoie plus PrimaryId.
    "rls_saved_platform": "",
    "rls_saved_primary_id": "",
    "rls_saved_endpoint": "",
    "rls_api_base": RLS_API_BASE,
    "rls_api_key": RLS_API_KEY,
    "showmatch": {
        "enabled": False,
        "bo": 5,
        "left_name": "Player",
        "right_name": "Opponent",
        "left_score": 0,
        "right_score": 0,
        "current_game": 1,
        "last_winner": "",
        "history": [],
    },
    "overlay_defaults_version": 6,
}



APP_STYLE = """
QWidget {
    background: #090B10;
    color: #E8ECF4;
    font-family: 'Segoe UI', 'Montserrat', Arial, sans-serif;
    font-size: 12px;
}
QMainWindow { background: #090B10; }
QTabWidget::pane { border: none; background: #090B10; border-radius: 10px; }
QTabBar::tab {
    background: #111521; color: #7C8599; padding: 10px 16px;
    border: none; border-top-left-radius: 9px; border-top-right-radius: 9px;
    font-weight: 700;
}
QTabBar::tab:selected { background: #1B2030; color: #FFFFFF; }
QLabel { background: transparent; }
QLineEdit, QComboBox, QSpinBox {
    background: #151A27; color: #F6F8FF; border: none;
    border-radius: 10px; padding: 8px 10px;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus { background:#182033; }
QTextEdit {
    background: #0F131D; color: #B8C1D6; border: none;
    border-radius: 12px; padding: 10px; font-family: 'Consolas', monospace;
}
QCheckBox { spacing: 10px; color: #E8ECF4; }
QCheckBox::indicator {
    width: 18px; height: 18px; border-radius: 6px; border: 1px solid #2A3348;
    background: #151A27;
}
QCheckBox::indicator:checked { background: #1A8CFF; border-color: #1A8CFF; }
QPushButton {
    background: #1B2030; color: #F6F8FF; border: none; border-radius: 11px;
    padding: 9px 13px; font-weight: 700;
}
QPushButton:hover { background: #26314A; }
QPushButton:pressed { background: #121725; }
QScrollArea { background: transparent; border: none; }

QFrame#ShellCard {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #111827, stop:1 #0B1020);
    border: 1px solid #25304A;
    border-radius: 22px;
}
QPushButton#NavButton {
    text-align: left;
    padding: 12px 14px;
    border-radius: 16px;
    background: #101624;
    color: #B8C1D6;
    font-weight: 900;
}
QPushButton#NavButton:hover { background: #182237; color: #FFFFFF; }
QPushButton#NavButton:checked { background: #1A8CFF; color: white; }

"""


def deep_merge(base: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = value
    return out


class Config:
    def _fresh_default_config(self) -> Dict[str, Any]:
        data = json.loads(json.dumps(DEFAULT_CONFIG))
        data["app_version"] = APP_VERSION
        return data

    # Ces valeurs restent en mémoire pour garder les fonctionnalités,
    # mais elles ne sont jamais écrites dans config.json.
    SENSITIVE_JSON_KEYS = {
        "rls_api_key",
        "rls_api_base",
        "tracker_force_player",
        "remote_key",
    }

    def __init__(self) -> None:
        self.data = self._fresh_default_config()
        self.startup_config_was_read = False
        self.startup_config_was_reset = False
        self.startup_config_path = CONFIG_PATH
        # Lecture immédiate du fichier config quand l'application s'ouvre.
        self.load()

        # Migrations et valeurs obligatoires uniquement en mémoire :
        # aucune écriture automatique au lancement.
        if int(self.data.get("overlay_defaults_version", 0) or 0) < 7:
            theme = dict(self.data.get("theme", {}))
            theme.update({
                "mode": "banner",
                "bg": "rgba(8,10,16,.88)",
                "radius": 22,
                "show_mmr": True,
                "animate": True,
            })
            self.data["theme"] = theme
            self.data["tracker_platform"] = self.data.get("tracker_platform", "auto") or "auto"
            self.data["tracker_interval_sec"] = 20
            self.data["overlay_defaults_version"] = 7

        if not isinstance(self.data.get("showmatch"), dict):
            self.data["showmatch"] = json.loads(json.dumps(DEFAULT_CONFIG["showmatch"]))
        else:
            self.data["showmatch"] = deep_merge(
                json.loads(json.dumps(DEFAULT_CONFIG["showmatch"])),
                self.data.get("showmatch", {})
            )

        if not isinstance(self.data.get("mode_sessions"), dict):
            self.data["mode_sessions"] = {}

        # Clé remote de session uniquement en mémoire.
        # Elle n'est pas sauvegardée dans le JSON.
        if not self.data.get("remote_key"):
            self.data["remote_key"] = secrets.token_urlsafe(10)

        # Si le fichier config a été écrasé au démarrage à cause d'une mise à jour,
        # on sauvegarde aussi les migrations/valeurs propres de cette nouvelle version.
        if self.startup_config_was_reset:
            self.save()

    def _strip_sensitive_json_values(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        clean = json.loads(json.dumps(payload))
        for key in self.SENSITIVE_JSON_KEYS:
            clean.pop(key, None)
        return clean

    def _sanitize_existing_config_file(self, loaded: Dict[str, Any]) -> Dict[str, Any]:
        """Nettoie un ancien config.json s'il contient des infos sensibles.

        Aucun fichier n'est créé si config.json n'existe pas.
        Si un ancien config.json existe déjà et contient des clés sensibles,
        il est réécrit sans ces clés.
        """
        if not isinstance(loaded, dict):
            return {}

        had_sensitive = any(key in loaded for key in self.SENSITIVE_JSON_KEYS)
        clean_loaded = self._strip_sensitive_json_values(loaded)

        if had_sensitive and CONFIG_PATH.exists():
            try:
                with CONFIG_PATH.open("w", encoding="utf-8") as f:
                    json.dump(clean_loaded, f, indent=2, ensure_ascii=False)
            except Exception:
                pass

        return clean_loaded

    def load(self) -> None:
        """Lit le fichier config dès l'ouverture de l'application.

        Si le fichier existe dans %AppData% et que sa version ne correspond pas
        à APP_VERSION, il est considéré comme un ancien fichier de mise à jour :
        on l'écrase complètement avec une config neuve et vide.
        """
        try:
            config_file = CONFIG_PATH if CONFIG_PATH.exists() else LEGACY_CONFIG_PATH
            self.startup_config_path = config_file

            if not config_file.exists():
                return

            self.startup_config_was_read = True

            with config_file.open("r", encoding="utf-8") as f:
                loaded = json.load(f)

            if not isinstance(loaded, dict):
                loaded = {}

            if config_file == CONFIG_PATH:
                loaded_version = str(loaded.get("app_version", "") or "").strip()

                # Lecture au démarrage + détection mise à jour.
                # Si la version du fichier n'est pas celle de l'application,
                # on vide/écrase complètement l'ancien config.
                if loaded_version != APP_VERSION:
                    self.data = self._fresh_default_config()
                    self.startup_config_was_reset = True
                    self.save()
                    return

                loaded = self._sanitize_existing_config_file(loaded)
            else:
                # Ancien fichier local legacy : on le lit mais on retire toute donnée sensible.
                loaded = self._strip_sensitive_json_values(loaded)

            self.data = deep_merge(self.data, loaded)
            self.data["app_version"] = APP_VERSION
        except Exception:
            # Si le fichier config est illisible/cassé, on repart proprement en mémoire.
            # On ne crée pas de fichier neuf sauf si un save explicite arrive ensuite.
            self.data = self._fresh_default_config()

    def save(self) -> None:
        try:
            CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            self.data["app_version"] = APP_VERSION
            safe_data = self._strip_sensitive_json_values(self.data)
            safe_data["app_version"] = APP_VERSION
            with CONFIG_PATH.open("w", encoding="utf-8") as f:
                json.dump(safe_data, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def __getitem__(self, key: str) -> Any:
        return self.data[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.data[key] = value
        self.save()

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)


@dataclass
class TrackerState:
    wins: int = 0
    losses: int = 0
    streak_val: int = 0
    streak_type: str = ""
    session_start: float = field(default_factory=time.time)
    selected_playlist: str = ""
    detected_player_name: str = ""
    statsapi_freeplay_locked_player: str = ""
    statsapi_freeplay_locked_at: float = 0.0
    pending_detected_player_name: str = ""
    pending_detected_player_since: float = 0.0
    pending_detected_player_last_seen: float = 0.0
    my_team: Optional[int] = None
    team_scores: Dict[int, int] = field(default_factory=dict)
    last_scores: Dict[int, int] = field(default_factory=dict)
    current_players: List[Dict[str, Any]] = field(default_factory=list)
    match_active: bool = False
    match_counted: bool = False
    match_id: str = ""
    current_match_key: str = ""
    current_server_key: str = ""
    last_server_key: str = ""
    last_server_change_at: float = 0.0
    last_closed_match_key: str = ""
    last_closed_match_at: float = 0.0
    recent_counted_results: List[Dict[str, Any]] = field(default_factory=list)
    training_active: bool = False
    current_match_ranked: bool = False
    current_match_private: bool = False
    current_match_no_stats: bool = False
    current_match_no_stats_reason: str = ""
    current_match_platform: str = "auto"
    current_match_has_timer: bool = False
    current_match_had_opponent: bool = False
    current_match_had_ranked_context: bool = False
    current_match_api_winner: Optional[int] = None
    current_match_end_reason: str = ""
    current_match_waiting_destroy: bool = False
    current_match_playlist_locked: bool = False
    current_match_locked_playlist: str = ""
    pending_match_playlist: str = ""
    pending_match_playlist_since: float = 0.0
    pending_match_playlist_last_seen: float = 0.0
    ignored_context: str = ""
    tracker_status: str = "API RLS : en attente"
    tracker_last_at: str = ""
    main_overlay_enabled: bool = True
    showmatch_enabled: bool = False
    showmatch_bo: int = 5
    showmatch_left_name: str = "Player"
    showmatch_right_name: str = "Opponent"
    showmatch_left_score: int = 0
    showmatch_right_score: int = 0
    showmatch_current_game: int = 1
    showmatch_left_team: Optional[int] = None
    showmatch_right_team: Optional[int] = None
    showmatch_last_winner: str = ""
    showmatch_history: List[Dict[str, Any]] = field(default_factory=list)
    showmatch_last_main_result_key: str = ""
    all_mmr: Dict[str, Dict[str, Any]] = field(
        default_factory=lambda: {
            k: {"mmr": None, "mmr_start": None, "mmr_change": 0, "rank": "", "rank_short": "", "rank_asset": "", "leader_rank": ""}
            for k in PLAYLIST_NAMES
        }
    )
    connection: str = "disconnected"
    connection_message: str = "Non connecté"
    last_event: str = ""
    last_event_at: str = ""
    last_raw_event: Dict[str, Any] = field(default_factory=dict)
    history: List[Dict[str, Any]] = field(default_factory=list)
    revision: int = 0
    last_publish_at: str = ""

    def to_dict(self, theme: Dict[str, Any]) -> Dict[str, Any]:
        total = self.wins + self.losses
        winrate = round(self.wins / total * 100) if total else 0
        playlist = self.selected_playlist
        mmr_data = self.all_mmr.get(playlist, {})
        rank_info = rank_from_mmr(playlist, mmr_data.get("mmr"))
        rank_label = mmr_data.get("rank") or rank_info.get("label", "")
        rank_short = mmr_data.get("rank_short") or rank_info.get("short", "")
        # Toujours privilégier l'asset recalculé depuis le MMR/mode actuel.
        # Cela évite qu'une ancienne session garde les anciens SVG générés.
        rank_asset = rank_info.get("asset") or mmr_data.get("rank_asset", "")
        if isinstance(rank_asset, str) and rank_asset.endswith(".svg"):
            rank_asset = rank_asset[:-4] + ".png"
        elapsed = int(time.time() - self.session_start)
        my_score = self.team_scores.get(self.my_team, 0) if self.my_team is not None else 0
        opp_score = self.team_scores.get(1 - self.my_team, 0) if self.my_team is not None else 0
        local_public_player = find_player_by_identity_hint(self.current_players, self.detected_player_name)
        if not local_public_player:
            local_public_player = _first_player_from_collection(self.current_players)
        return {
            "app": APP_NAME,
            "timestamp": int(time.time()),
            "timestamp_ms": int(time.time() * 1000),
            "revision": self.revision,
            "last_publish_at": self.last_publish_at,
            "connection": self.connection,
            "connection_message": self.connection_message,
            "main_overlay_enabled": bool(self.main_overlay_enabled),
            "main_overlay_visible": bool(self.main_overlay_enabled),
            "playlist": playlist,
            "playlist_name": PLAYLIST_NAMES.get(playlist, "Aucune"),
            "wins": self.wins,
            "losses": self.losses,
            "total": total,
            "winrate": winrate,
            "streak_val": self.streak_val,
            "streak_type": self.streak_type,
            "mmr": mmr_data.get("mmr"),
            "mmr_change": mmr_data.get("mmr_change", 0),
            "rank": rank_label,
            "rank_short": rank_short,
            "rank_asset": rank_asset,
            "rank_logo": f"/assets/ranks/{rank_asset}" if rank_asset else "",
            "leader_rank": str(mmr_data.get("leader_rank") or ""),
            "tracker_status": self.tracker_status,
            "tracker_last_at": self.tracker_last_at,
            "ignored_context": self.ignored_context,
            "private_match_active": bool(self.match_active and self.current_match_private and not self.training_active),
            "current_match_ranked": self.current_match_ranked,
            "current_match_private": self.current_match_private,
            "current_match_no_stats": self.current_match_no_stats,
            "current_match_no_stats_reason": self.current_match_no_stats_reason,
            "current_match_platform": self.current_match_platform,
            "player": self.detected_player_name,
            "showmatch": {
                "enabled": self.showmatch_enabled,
                "visible": bool(self.showmatch_enabled),
                "bo": self.showmatch_bo,
                "target": int(self.showmatch_bo // 2) + 1,
                "left_name": self.showmatch_left_name or (self.detected_player_name or "Player"),
                "right_name": self.showmatch_right_name or "Opponent",
                "left_score": self.showmatch_left_score,
                "right_score": self.showmatch_right_score,
                "left_team": self.showmatch_left_team,
                "right_team": self.showmatch_right_team,
                "left_color": "orange" if str(self.showmatch_left_team) == "1" else "blue",
                "right_color": "blue" if str(self.showmatch_left_team) == "1" else "orange",
                "last_winner": self.showmatch_last_winner,
                "completed": self.showmatch_left_score >= int(self.showmatch_bo // 2) + 1 or self.showmatch_right_score >= int(self.showmatch_bo // 2) + 1,
                "current_game": max(1, min(int(self.showmatch_current_game or 1), int(self.showmatch_bo))),
                "game_label": f"GAME {max(1, min(int(self.showmatch_current_game or 1), int(self.showmatch_bo)))} - BO{self.showmatch_bo}",
                "history": self.showmatch_history[-12:],
            },
            "my_team": self.my_team,
            "score": {"me": my_score, "opponent": opp_score, "teams": self.team_scores},
            # Pour l'overlay principal, on n'expose que le joueur local/principal.
            # La liste complète reste interne pour la détection playlist et le Showmatch.
            "players": [p for p in [local_public_player] if isinstance(p, dict)][:1],
            "players_count": count_distinct_players(self.current_players),
            "server_key": self.current_server_key,
            "elapsed": elapsed,
            "last_event": self.last_event,
            "last_event_at": self.last_event_at,
            "history": self.history[:12],
            "theme": theme,
        }


class Signals(QObject):
    state_changed = pyqtSignal(dict)
    log = pyqtSignal(str)
    status = pyqtSignal(str, str)
    remote_command = pyqtSignal(dict)


class RealtimeHub:
    """HTTP + WebSocket hub for OBS and remote control."""

    def __init__(
        self,
        get_state: Callable[[], Dict[str, Any]],
        on_command: Callable[[Dict[str, Any]], None],
        log: Callable[[str], None],
        http_port: int = HTTP_PORT,
        ws_port: int = WS_PORT,
    ) -> None:
        self.get_state = get_state
        self.on_command = on_command
        self.log = log
        self.http_port = http_port
        self.ws_port = ws_port
        self.ws_clients: Set[Any] = set()
        self.ws_loop: Optional[asyncio.AbstractEventLoop] = None
        self._http_server: Optional[ThreadingHTTPServer] = None
        self._http_thread: Optional[threading.Thread] = None
        self._ws_thread: Optional[threading.Thread] = None
        self._started = False
        self._stopping = False

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        self._stopping = False
        self._http_thread = threading.Thread(target=self._run_http, daemon=True, name="RLHTTP")
        self._ws_thread = threading.Thread(target=self._run_ws, daemon=True, name="RLWebSocket")
        self._http_thread.start()
        self._ws_thread.start()

    def stop(self) -> None:
        self._stopping = True
        try:
            if self._http_server:
                self._http_server.shutdown()
                self._http_server.server_close()
        except Exception:
            pass
        if self.ws_loop:
            try:
                fut = asyncio.run_coroutine_threadsafe(self._close_ws_clients(), self.ws_loop)
                try:
                    fut.result(timeout=0.4)
                except Exception:
                    pass
                self.ws_loop.call_soon_threadsafe(self.ws_loop.stop)
            except Exception:
                pass
        for th in (self._http_thread, self._ws_thread):
            try:
                if th and th.is_alive():
                    th.join(timeout=0.35)
            except Exception:
                pass
        self._started = False

    def broadcast(self, state: Dict[str, Any]) -> None:
        if not self.ws_loop or not self.ws_clients:
            return
        payload = json.dumps({"type": "state", "state": state}, ensure_ascii=False)
        try:
            asyncio.run_coroutine_threadsafe(self._broadcast(payload), self.ws_loop)
        except Exception:
            pass

    async def _broadcast(self, payload: str) -> None:
        dead = []
        for ws in list(self.ws_clients):
            try:
                await ws.send(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.ws_clients.discard(ws)

    async def _close_ws_clients(self) -> None:
        for ws in list(self.ws_clients):
            try:
                await ws.close()
            except Exception:
                pass
        self.ws_clients.clear()

    def _run_http(self) -> None:
        hub = self

        class Handler(BaseHTTPRequestHandler):
            def _send(self, code: int, body: bytes, content_type: str = "text/html; charset=utf-8") -> None:
                self.send_response(code)
                self.send_header("Content-Type", content_type)
                self.send_header("Cache-Control", "no-store")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self) -> None:  # noqa: N802
                parsed = urllib.parse.urlparse(self.path)
                path = parsed.path.rstrip("/") or "/"
                if path == "/api/state":
                    body = json.dumps(hub.get_state(), ensure_ascii=False).encode("utf-8")
                    self._send(HTTPStatus.OK, body, "application/json; charset=utf-8")
                    return
                if path == "/overlay":
                    self._send(HTTPStatus.OK, OVERLAY_HTML.encode("utf-8"))
                    return
                if path == "/showmatch":
                    self._send(HTTPStatus.OK, SHOWMATCH_HTML.encode("utf-8"))
                    return
                if path == "/remote":
                    self._send(HTTPStatus.OK, REMOTE_HTML.encode("utf-8"))
                    return
                if path == "/health":
                    self._send(HTTPStatus.OK, b"ok", "text/plain; charset=utf-8")
                    return
                if path.startswith("/assets/"):
                    try:
                        asset_root = (RESOURCE_DIR / "assets").resolve()
                        requested = (RESOURCE_DIR / path.lstrip("/")).resolve()
                        if not str(requested).startswith(str(asset_root)) or not requested.is_file():
                            self._send(HTTPStatus.NOT_FOUND, b"404", "text/plain; charset=utf-8")
                            return
                        suffix = requested.suffix.lower()
                        content_type = {
                            ".svg": "image/svg+xml; charset=utf-8",
                            ".png": "image/png",
                            ".ico": "image/x-icon",
                            ".jpg": "image/jpeg",
                            ".jpeg": "image/jpeg",
                            ".webp": "image/webp",
                        }.get(suffix, "application/octet-stream")
                        self._send(HTTPStatus.OK, requested.read_bytes(), content_type)
                    except Exception:
                        self._send(HTTPStatus.NOT_FOUND, b"404", "text/plain; charset=utf-8")
                    return
                if path == "/":
                    state = hub.get_state()
                    base = f"http://{self.headers.get('Host', '127.0.0.1:' + str(hub.http_port))}"
                    remote_key = state.get("remote_key", "")
                    html = LANDING_HTML.replace("{{BASE}}", base).replace("{{KEY}}", remote_key)
                    self._send(HTTPStatus.OK, html.encode("utf-8"))
                    return
                self._send(HTTPStatus.NOT_FOUND, b"404", "text/plain; charset=utf-8")

            def log_message(self, *_: Any) -> None:
                return

        try:
            self._http_server = ThreadingHTTPServer(("0.0.0.0", self.http_port), Handler)
            self.log(f"Serveur HTTP actif : http://127.0.0.1:{self.http_port}")
            self._http_server.serve_forever()
        except OSError as exc:
            self.log(f"[HTTP] Port {self.http_port} indisponible : {exc}")
        except Exception as exc:
            self.log(f"[HTTP] Erreur : {exc}")

    def _run_ws(self) -> None:
        if websockets is None:
            self.log("[WebSocket] Module 'websockets' manquant. Installe requirements.txt")
            return
        self.ws_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.ws_loop)

        async def runner() -> None:
            async with websockets.serve(
                self._ws_handler,
                "0.0.0.0",
                self.ws_port,
                ping_interval=15,
                ping_timeout=10,
                close_timeout=3,
            ):
                self.log(f"WebSocket actif : ws://127.0.0.1:{self.ws_port}/ws")
                await asyncio.Future()

        try:
            self.ws_loop.run_until_complete(runner())
        except OSError as exc:
            self.log(f"[WebSocket] Port {self.ws_port} indisponible : {exc}")
        except Exception as exc:
            if not self._stopping:
                self.log(f"[WebSocket] Erreur : {exc}")

    async def _ws_handler(self, websocket: Any, path: Optional[str] = None) -> None:
        self.ws_clients.add(websocket)
        self.log(f"Client WebSocket connecté · {len(self.ws_clients)} client(s)")
        try:
            await websocket.send(json.dumps({"type": "state", "state": self.get_state()}, ensure_ascii=False))
            async for message in websocket:
                try:
                    data = json.loads(message)
                    msg_type = data.get("type")
                    if msg_type == "command":
                        self.on_command(data)
                    elif msg_type == "ping":
                        await websocket.send(json.dumps({"type": "pong", "time": time.time()}))
                    elif msg_type == "subscribe":
                        await websocket.send(json.dumps({"type": "state", "state": self.get_state()}, ensure_ascii=False))
                except Exception as exc:
                    await websocket.send(json.dumps({"type": "error", "message": str(exc)}))
        finally:
            self.ws_clients.discard(websocket)
            self.log(f"Client WebSocket déconnecté · {len(self.ws_clients)} client(s)")


class StatsAPIClient:
    """TCP JSON event client compatible with the file's local StatsAPI approach."""

    def __init__(
        self,
        host_getter: Callable[[], str],
        port_getter: Callable[[], int],
        event_handler: Callable[[Dict[str, Any]], None],
        log: Callable[[str], None],
        status: Callable[[str, str], None],
    ) -> None:
        self.host_getter = host_getter
        self.port_getter = port_getter
        self.event_handler = event_handler
        self.log = log
        self.status = status
        self._running = False
        self._sock: Optional[socket.socket] = None
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="RLStatsAPI")
        self._thread.start()

    def reconnect(self) -> None:
        self.stop()
        time.sleep(0.15)
        self.start()

    def stop(self) -> None:
        self._running = False
        if self._sock:
            try:
                self._sock.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            try:
                self._sock.close()
            except Exception:
                pass
        self._sock = None
        try:
            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=0.45)
        except Exception:
            pass

    def _loop(self) -> None:
        while self._running:
            host = self.host_getter()
            port = self.port_getter()
            self.status("connecting", "Connexion StatsAPI…")
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(5)
                sock.connect((host, port))
                sock.settimeout(None)
                self._sock = sock
                self.status("connected", "StatsAPI connecté")
                self._read_stream(sock)
            except ConnectionRefusedError:
                self.status("error", "Connexion refusée — lance Rocket League + StatsAPI")
            except socket.timeout:
                self.status("error", "Timeout — StatsAPI actif ?")
            except OSError as exc:
                if self._running:
                    self.status("error", f"Socket fermé : {exc}")
            except Exception as exc:
                self.status("error", f"Erreur StatsAPI : {exc}")
            finally:
                try:
                    if self._sock:
                        self._sock.close()
                except Exception:
                    pass
                self._sock = None
                if self._running:
                    self.status("disconnected", "Déconnecté — nouvelle tentative dans 3s")
                    time.sleep(3)

    def _read_stream(self, sock: socket.socket) -> None:
        buffer = b""
        while self._running:
            try:
                chunk = sock.recv(8192)
            except (ConnectionResetError, ConnectionAbortedError, OSError) as exc:
                if self._running:
                    self.log(f"[StatsAPI] Lecture arrêtée proprement : {exc}")
                break
            except Exception as exc:
                self.log(f"[StatsAPI] Erreur lecture ignorée : {exc}")
                break
            if not chunk:
                break
            buffer += chunk
            while True:
                msg, buffer = self._extract_json(buffer)
                if msg is None:
                    break
                try:
                    event = json.loads(msg.decode("utf-8", errors="replace"))
                    self.event_handler(event)
                except Exception as exc:
                    self.log(f"[StatsAPI] Erreur parsing : {exc}")

    @staticmethod
    def _extract_json(buffer: bytes) -> tuple[Optional[bytes], bytes]:
        start = buffer.find(b"{")
        if start == -1:
            return None, b""
        buffer = buffer[start:]
        depth = 0
        in_string = False
        escaped = False
        for idx, value in enumerate(buffer):
            char = chr(value)
            if escaped:
                escaped = False
                continue
            if char == "\\" and in_string:
                escaped = True
                continue
            if char == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return buffer[: idx + 1], buffer[idx + 1 :]
        return None, buffer


# ────────────────────────────────────────────────────────────────────────────
# UI helpers
# ────────────────────────────────────────────────────────────────────────────


def card(title: str = "", subtitle: str = "") -> QFrame:
    frame = QFrame()
    frame.setStyleSheet(
        "QFrame { background: #111521; border: none; border-radius: 16px; }"
    )
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(12, 10, 12, 10)
    layout.setSpacing(6)
    if title:
        lab = QLabel(title.upper())
        lab.setStyleSheet("color:#8C96AC;font-size:10px;font-weight:800;letter-spacing:1.3px;")
        layout.addWidget(lab)
    if subtitle:
        sub = QLabel(subtitle)
        sub.setWordWrap(True)
        sub.setStyleSheet("color:#B8C1D6;font-size:11px;")
        layout.addWidget(sub)
    return frame


def primary_button(text: str, color: str = "#1A8CFF") -> QPushButton:
    b = QPushButton(text)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setStyleSheet(
        f"QPushButton{{background:{color};color:white;border:none;border-radius:12px;padding:10px 14px;font-weight:800;}}"
        f"QPushButton:hover{{background:{color}dd;}}"
    )
    return b


def muted_label(text: str) -> QLabel:
    lab = QLabel(text)
    lab.setStyleSheet("color:#8C96AC;font-size:11px;background:transparent;")
    return lab


def value_label(text: str, size: int = 22, color: str = "#F6F8FF") -> QLabel:
    lab = QLabel(text)
    lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lab.setStyleSheet(f"color:{color};font-size:{size}px;font-weight:900;background:transparent;")
    return lab



class RLOverlayStudio(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setFixedSize(1120, 700)
        icon_path = APP_ICON_PNG if APP_ICON_PNG.exists() else APP_ICON_ICO
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        self.config = Config()
        self.signals = Signals()
        self.lock = threading.RLock()
        configured_playlist = str(self.config.get("selected_playlist", "") or "")
        if configured_playlist not in PLAYLIST_NAMES:
            configured_playlist = ""
        self.state = TrackerState(selected_playlist=configured_playlist)
        self.state.main_overlay_enabled = bool(self.config.get("main_overlay_enabled", True))
        self._load_showmatch_config_into_state()
        with self.lock:
            self._load_mode_session_locked(self.state.selected_playlist, reset_if_missing=False)
        self.event_queue: "queue.Queue[Dict[str, Any]]" = queue.Queue(maxsize=300)
        self._closing = False
        self._tracker_busy = False
        self._last_tracker_fetch = 0.0
        self._last_tracker_key = ""
        self._request_rate_lock = threading.Lock()
        self._last_network_request_at = 0.0

        # Optimisation performance : on batch les JSON StatsAPI, on évite les
        # publications OBS/UI identiques ou trop rapprochées, et on limite les
        # écritures lourdes dans le panneau.
        self._batching_api_events = False
        self._pending_publish_revision = False
        self._last_publish_monotonic = 0.0
        self._last_raw_box_text = ""
        self._log_lines: List[str] = []
        self._last_log_message = ""
        self._recent_log_signatures: Dict[str, float] = {}
        # Sauvegarde automatique joueur : depuis Beta 0.10, elle se fait
        # uniquement quand une connexion StatsAPI qui a vraiment été active se déconnecte.
        self._api_connected_since_last_disconnect_save = False

        self.hub = RealtimeHub(
            get_state=self.get_public_state,
            on_command=lambda data: self.signals.remote_command.emit(data),
            log=self._log,
        )
        self.stats_client = StatsAPIClient(
            host_getter=lambda: str(self.config.get("statsapi_host", "127.0.0.1")),
            port_getter=lambda: int(self.config.get("statsapi_port", DEFAULT_STATSAPI_PORT)),
            event_handler=self._enqueue_api_event,
            log=self._log,
            status=lambda s, m: self.signals.status.emit(s, m),
        )

        self._build_ui()
        self._connect_signals()

        self.hub.start()
        self.stats_client.start()

        self.event_timer = QTimer(self)
        self.event_timer.timeout.connect(lambda: self._safe_call(self._drain_events, "Drain StatsAPI"))
        self.event_timer.start(50)

        self.publish_timer = QTimer(self)
        # Heartbeat léger : garde OBS/remote synchronisés sans incrémenter la révision API.
        self.publish_timer.timeout.connect(lambda: self._safe_call(lambda: self._publish_state(count_revision=False), "Publication état"))
        self.publish_timer.start(2000)


        # API RLS : pas de timer en continu.
        # Pour éviter les chutes de FPS en jeu, la recherche MMR automatique
        # se lance uniquement aux événements de fin de partie
        # MatchEnded / MatchDestroyed. Le bouton manuel reste disponible.
        self.tracker_timer = None

        self._refresh_urls()
        self._refresh_ui(self.get_public_state())
        self._log("Application prête. Ajoute /overlay dans OBS comme Browser Source.")

        # Vérification de mise à jour GitHub au démarrage.
        QTimer.singleShot(AUTO_UPDATE_CHECK_DELAY_MS, self._check_for_updates_on_startup)

    def closeEvent(self, event: Any) -> None:  # noqa: N802
        event.accept()
        self.shutdown_application(force_exit=True)

    def shutdown_application(self, force_exit: bool = False) -> None:
        if self._closing:
            return
        self._closing = True

        saved_player = ""
        try:
            with self.lock:
                saved_player = self._save_and_reset_session_before_app_close_locked()
        except Exception as exc:
            try:
                self._log(f"Sauvegarde/reset avant fermeture impossible : {exc}")
            except Exception:
                pass

        if saved_player:
            try:
                self._log(f"Fermeture : sauvegarde automatique de {saved_player} écrasée/mise à jour")
                self._log("Fermeture : stats, joueur, playlist et API RLS remis à zéro")
            except Exception:
                pass

        self._log("Fermeture complète en cours…")
        for timer_name in ("event_timer", "publish_timer", "tracker_timer"):
            timer = getattr(self, timer_name, None)
            try:
                if timer:
                    timer.stop()
            except Exception:
                pass
        try:
            self._remove_managed_statsapi_config()
        except Exception as exc:
            self._log(f"Nettoyage config StatsAPI impossible : {exc}")
        try:
            self.stats_client.stop()
        except Exception:
            pass
        try:
            self.hub.stop()
        except Exception:
            pass
        try:
            QApplication.instance().quit()
        except Exception:
            pass
        if force_exit:
            # Pas de os._exit automatique : sur certaines configs Windows/plein écran, un évènement
            # de focus peut déclencher une fermeture trop agressive. On laisse Qt terminer proprement
            # les threads daemon après arrêt du hub et de la StatsAPI.
            pass


    def _version_tuple(self, value: str) -> Tuple[int, ...]:
        """Convertit 'Beta 3.8' ou 'v3.8.1' en tuple comparable."""
        nums = [int(x) for x in re.findall(r"\d+", str(value or ""))]
        while len(nums) < 3:
            nums.append(0)
        return tuple(nums[:3])

    def _is_remote_version_newer(self, remote_version: str) -> bool:
        return self._version_tuple(remote_version) > self._version_tuple(APP_VERSION)

    def _update_user_agent(self) -> str:
        return f"{APP_NAME}/{APP_VERSION} (+GitHub Auto Update)"

    def _json_from_url(self, url: str, timeout: int = 12) -> Dict[str, Any]:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": self._update_user_agent(),
                "Accept": "application/vnd.github+json, application/json;q=0.9, */*;q=0.8",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read(1024 * 1024)
        return json.loads(raw.decode("utf-8", errors="replace"))

    def _text_from_url(self, url: str, timeout: int = 12) -> str:
        req = urllib.request.Request(url, headers={"User-Agent": self._update_user_agent()})
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read(256 * 1024)
        return raw.decode("utf-8", errors="replace").strip()

    def _github_latest_release_manifest(self, repo: str) -> Optional[Dict[str, Any]]:
        repo = str(repo or "").strip().strip("/")
        if not repo or "/" not in repo or "TON_" in repo.upper():
            return None

        release_url = f"https://api.github.com/repos/{repo}/releases/latest"
        data = self._json_from_url(release_url)

        assets = data.get("assets") if isinstance(data.get("assets"), list) else []
        zip_asset = None
        sha_asset = None

        for asset in assets:
            name = str(asset.get("name", "") or "")
            if name.lower().endswith(".zip") and zip_asset is None:
                zip_asset = asset
            if name.lower().endswith((".sha256", ".sha256.txt")) and sha_asset is None:
                sha_asset = asset

        if not zip_asset:
            return None

        sha256_value = ""
        if sha_asset and sha_asset.get("browser_download_url"):
            try:
                sha_text = self._text_from_url(str(sha_asset["browser_download_url"]))
                match = re.search(r"\b[a-fA-F0-9]{64}\b", sha_text)
                if match:
                    sha256_value = match.group(0).lower()
            except Exception:
                sha256_value = ""

        return {
            "version": str(data.get("tag_name") or data.get("name") or "").strip(),
            "download_url": str(zip_asset.get("browser_download_url") or "").strip(),
            "sha256": sha256_value,
            "mandatory": False,
            "changelog": str(data.get("body") or "").strip(),
            "source": "github_release",
        }

    def _load_update_manifest(self) -> Optional[Dict[str, Any]]:
        """Charge le manifest de mise à jour depuis GitHub."""
        if not bool(self.config.get("updater_enabled", True)):
            return None

        manifest_url = str(self.config.get("updater_manifest_url", "") or GITHUB_UPDATE_MANIFEST_URL or "").strip()
        repo = str(self.config.get("updater_github_repo", "") or GITHUB_UPDATE_REPO or "").strip()

        if manifest_url and "TON_" not in manifest_url.upper():
            data = self._json_from_url(manifest_url)
            if isinstance(data, dict):
                data.setdefault("source", "manifest")
                return data

        if repo:
            return self._github_latest_release_manifest(repo)

        return None

    def _check_for_updates_on_startup(self) -> None:
        """Vérifie automatiquement les mises à jour au démarrage."""
        try:
            manifest = self._load_update_manifest()
            if not manifest:
                return

            remote_version = str(manifest.get("version", "") or "").strip()
            download_url = str(manifest.get("download_url", "") or "").strip()

            if not remote_version or not download_url:
                return

            if not self._is_remote_version_newer(remote_version):
                return

            changelog = manifest.get("changelog", "")
            if isinstance(changelog, list):
                changelog_text = "\n".join(f"- {line}" for line in changelog)
            else:
                changelog_text = str(changelog or "").strip()

            if len(changelog_text) > 900:
                changelog_text = changelog_text[:900].rstrip() + "\n..."

            msg = (
                f"Une nouvelle version est disponible : {remote_version}\n\n"
                f"Version actuelle : {APP_VERSION}\n\n"
            )
            if changelog_text:
                msg += f"Nouveautés :\n{changelog_text}\n\n"
            msg += "Télécharger et installer cette mise à jour maintenant ?"

            answer = QMessageBox.question(
                self,
                "Mise à jour disponible",
                msg,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )

            if answer == QMessageBox.StandardButton.Yes:
                self._download_and_install_update(manifest)
        except Exception as exc:
            try:
                self._log(f"Mise à jour GitHub ignorée : {exc}")
            except Exception:
                pass

    def _download_file_with_hash(self, url: str, expected_sha256: str = "") -> Path:
        temp_dir = Path(tempfile.mkdtemp(prefix="rl_overlay_update_"))
        filename = Path(urllib.parse.urlparse(url).path).name or "rl_overlay_update.zip"
        if not filename.lower().endswith(".zip"):
            filename = "rl_overlay_update.zip"
        destination = temp_dir / filename

        req = urllib.request.Request(url, headers={"User-Agent": self._update_user_agent()})
        digest = hashlib.sha256()

        with urllib.request.urlopen(req, timeout=60) as response, destination.open("wb") as f:
            while True:
                chunk = response.read(1024 * 512)
                if not chunk:
                    break
                f.write(chunk)
                digest.update(chunk)

        actual_sha256 = digest.hexdigest().lower()
        expected_sha256 = str(expected_sha256 or "").strip().lower()

        if expected_sha256 and actual_sha256 != expected_sha256:
            raise RuntimeError(
                "SHA256 différent : téléchargement refusé.\n"
                f"Attendu : {expected_sha256}\n"
                f"Reçu : {actual_sha256}"
            )

        return destination

    def _app_install_dir(self) -> Path:
        if getattr(sys, "frozen", False):
            return Path(sys.executable).resolve().parent
        return Path(__file__).resolve().parent

    def _restart_target(self) -> List[str]:
        if getattr(sys, "frozen", False):
            return [str(Path(sys.executable).resolve())]
        return [sys.executable, str(Path(__file__).resolve())]

    def _write_python_updater(self, folder: Path) -> Path:
        updater_path = folder / "rl_overlay_updater.py"
        updater_source = r"""#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

def pick_source_dir(extracted: Path) -> Path:
    children = list(extracted.iterdir())
    dirs = [p for p in children if p.is_dir()]
    files = [p for p in children if p.is_file()]
    if len(dirs) == 1 and not files:
        candidate = dirs[0]
        if (candidate / "app.py").exists() or any(candidate.glob("*.exe")):
            return candidate
        inner_dirs = [p for p in candidate.iterdir() if p.is_dir()]
        if len(inner_dirs) == 1 and ((inner_dirs[0] / "app.py").exists() or any(inner_dirs[0].glob("*.exe"))):
            return inner_dirs[0]
    return extracted

def copy_tree(src: Path, dst: Path) -> None:
    for item in src.iterdir():
        if item.name.lower() in {"appdata", "__pycache__"}:
            continue
        target = dst / item.name
        if item.is_dir():
            if target.exists():
                shutil.rmtree(target, ignore_errors=True)
            shutil.copytree(item, target)
        else:
            try:
                shutil.copy2(item, target)
            except PermissionError:
                time.sleep(1.5)
                shutil.copy2(item, target)

def main() -> int:
    if len(sys.argv) < 5:
        return 2

    zip_path = Path(sys.argv[1]).resolve()
    install_dir = Path(sys.argv[2]).resolve()
    pid = int(sys.argv[3])
    restart_cmd = sys.argv[4:]

    for _ in range(40):
        try:
            os.kill(pid, 0)
            time.sleep(0.25)
        except OSError:
            break

    extract_dir = zip_path.parent / "extracted"
    if extract_dir.exists():
        shutil.rmtree(extract_dir, ignore_errors=True)
    extract_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path, "r") as z:
        z.extractall(extract_dir)

    source_dir = pick_source_dir(extract_dir)
    install_dir.mkdir(parents=True, exist_ok=True)
    copy_tree(source_dir, install_dir)

    time.sleep(0.5)
    try:
        subprocess.Popen(restart_cmd, cwd=str(install_dir))
    except Exception:
        pass

    return 0

if __name__ == "__main__":
    sys.exit(main())
"""
        updater_path.write_text(updater_source, encoding="utf-8")
        return updater_path

    def _write_powershell_updater(self, folder: Path) -> Path:
        updater_path = folder / "rl_overlay_updater.ps1"
        updater_path.write_text(r'''
param(
    [Parameter(Mandatory=$true)][string]$ZipPath,
    [Parameter(Mandatory=$true)][string]$InstallDir,
    [Parameter(Mandatory=$true)][int]$PidToWait,
    [Parameter(Mandatory=$true)][string]$Mode,
    [string]$PythonExe = "",
    [string]$AppPy = "",
    [string]$ExePath = ""
)

$ErrorActionPreference = "Stop"

function Pick-SourceDir([string]$ExtractedDir) {
    $children = Get-ChildItem -LiteralPath $ExtractedDir -Force
    $dirs = @($children | Where-Object { $_.PSIsContainer })
    $files = @($children | Where-Object { -not $_.PSIsContainer })

    if ($dirs.Count -eq 1 -and $files.Count -eq 0) {
        $candidate = $dirs[0].FullName
        if ((Test-Path (Join-Path $candidate "app.py")) -or (Get-ChildItem -LiteralPath $candidate -Filter "*.exe" -ErrorAction SilentlyContinue)) {
            return $candidate
        }

        $inner = @(Get-ChildItem -LiteralPath $candidate -Force | Where-Object { $_.PSIsContainer })
        if ($inner.Count -eq 1) {
            $innerCandidate = $inner[0].FullName
            if ((Test-Path (Join-Path $innerCandidate "app.py")) -or (Get-ChildItem -LiteralPath $innerCandidate -Filter "*.exe" -ErrorAction SilentlyContinue)) {
                return $innerCandidate
            }
        }
    }

    return $ExtractedDir
}

try {
    try {
        Wait-Process -Id $PidToWait -Timeout 20 -ErrorAction SilentlyContinue
    } catch {}

    Start-Sleep -Milliseconds 600

    $ExtractDir = Join-Path (Split-Path -Parent $ZipPath) "extracted"
    if (Test-Path $ExtractDir) {
        Remove-Item -LiteralPath $ExtractDir -Recurse -Force
    }
    New-Item -ItemType Directory -Force -Path $ExtractDir | Out-Null

    Expand-Archive -LiteralPath $ZipPath -DestinationPath $ExtractDir -Force
    $SourceDir = Pick-SourceDir $ExtractDir

    if (!(Test-Path $InstallDir)) {
        New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
    }

    Get-ChildItem -LiteralPath $SourceDir -Force | ForEach-Object {
        if ($_.Name.ToLower() -in @("appdata", "__pycache__")) {
            return
        }

        $target = Join-Path $InstallDir $_.Name
        if ($_.PSIsContainer) {
            if (Test-Path $target) {
                Remove-Item -LiteralPath $target -Recurse -Force
            }
            Copy-Item -LiteralPath $_.FullName -Destination $target -Recurse -Force
        } else {
            Copy-Item -LiteralPath $_.FullName -Destination $target -Force
        }
    }

    Start-Sleep -Milliseconds 700

    if ($Mode -eq "source" -and $PythonExe -and $AppPy) {
        Start-Process -FilePath $PythonExe -ArgumentList "`"$AppPy`"" -WorkingDirectory $InstallDir
    } elseif ($ExePath) {
        Start-Process -FilePath $ExePath -WorkingDirectory $InstallDir
    }
} catch {
    $log = Join-Path $env:TEMP "rl_overlay_update_error.txt"
    $_ | Out-File -FilePath $log -Encoding utf8
}
''', encoding="utf-8")
        return updater_path

    def _launch_update_installer(self, zip_path: Path) -> None:
        install_dir = self._app_install_dir()
        updater_ps1 = self._write_powershell_updater(zip_path.parent)

        if getattr(sys, "frozen", False):
            mode = "frozen"
            python_exe = ""
            app_py = ""
            exe_path = str(Path(sys.executable).resolve())
        else:
            mode = "source"
            python_exe = sys.executable
            app_py = str(Path(__file__).resolve())
            exe_path = ""

        subprocess.Popen(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(updater_ps1),
                "-ZipPath",
                str(zip_path),
                "-InstallDir",
                str(install_dir),
                "-PidToWait",
                str(os.getpid()),
                "-Mode",
                mode,
                "-PythonExe",
                python_exe,
                "-AppPy",
                app_py,
                "-ExePath",
                exe_path,
            ],
            cwd=str(install_dir),
            close_fds=True,
        )

    def _download_and_install_update(self, manifest: Dict[str, Any]) -> None:
        download_url = str(manifest.get("download_url", "") or "").strip()
        expected_sha256 = str(manifest.get("sha256", "") or "").strip()

        if not download_url:
            QMessageBox.warning(self, "Mise à jour", "URL de téléchargement absente du manifest.")
            return

        try:
            self._log("Mise à jour : téléchargement en cours…")
            zip_path = self._download_file_with_hash(download_url, expected_sha256)
            self._log(f"Mise à jour : archive téléchargée · {zip_path}")

            try:
                with self.lock:
                    self._save_and_reset_session_before_app_close_locked()
            except Exception:
                pass

            self._launch_update_installer(zip_path)

            QMessageBox.information(
                self,
                "Mise à jour",
                "La mise à jour va être installée.\n\n"
                "L'application va se fermer, remplacer les fichiers, puis tenter de redémarrer automatiquement.",
            )

            QTimer.singleShot(250, lambda: self.shutdown_application(force_exit=True))
        except Exception as exc:
            QMessageBox.critical(self, "Mise à jour impossible", str(exc))
            try:
                self._log(f"Mise à jour impossible : {exc}")
            except Exception:
                pass

    def _safe_call(self, fn: Callable[[], Any], label: str = "Action") -> Any:
        try:
            return fn()
        except Exception as exc:
            try:
                self._log(f"{label} ignoré après erreur : {exc}")
            except Exception:
                pass
            try:
                crash_path = CRASH_LOG_PATH
                crash_path.parent.mkdir(parents=True, exist_ok=True)
                with crash_path.open("a", encoding="utf-8") as f:
                    f.write(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] {label}\n")
                    f.write(traceback.format_exc())
            except Exception:
                pass
            return None

    def _connect_signals(self) -> None:
        self.signals.state_changed.connect(self._refresh_ui)
        self.signals.log.connect(self._append_log)
        self.signals.status.connect(self._on_status)
        self.signals.remote_command.connect(self._handle_remote_command)

    def _build_ui(self) -> None:
        shell = QWidget()
        root = QHBoxLayout(shell)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(14)

        sidebar = QFrame()
        sidebar.setObjectName("ShellCard")
        sidebar.setFixedWidth(230)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(14, 14, 14, 14)
        side.setSpacing(10)

        brand = QLabel("⚡ RL Overlay\nStudio")
        brand.setStyleSheet("color:#FFFFFF;font-size:24px;font-weight:1000;line-height:1.1;background:transparent;")
        side.addWidget(brand)
        sub = muted_label("Panneau compact · OBS · Remote")
        side.addWidget(sub)

        self.stack = QStackedWidget()
        self.nav_buttons: List[QPushButton] = []
        pages = [
            ("🏠 Accueil", self._build_dashboard_tab()),
            ("🎨 Overlay", self._build_overlay_tab()),
            ("💾 Sessions", self._build_sessions_tab()),
            ("📱 Remote", self._build_remote_tab()),
            ("⚙️ Réglages", self._build_settings_tab()),
        ]
        for idx, (label, page) in enumerate(pages):
            self.stack.addWidget(page)
            btn = QPushButton(label)
            btn.setObjectName("NavButton")
            btn.setCheckable(True)
            btn.clicked.connect(lambda _checked=False, i=idx: self._select_page(i))
            side.addWidget(btn)
            self.nav_buttons.append(btn)

        side.addStretch()

        self.main_overlay_toggle_btn = primary_button(
            "Masquer overlay Win/Lose" if self.state.main_overlay_enabled else "Afficher overlay Win/Lose",
            "#8B5CF6",
        )
        self.main_overlay_toggle_btn.clicked.connect(lambda: self.set_main_overlay_enabled(not bool(self.state.main_overlay_enabled)))
        side.addWidget(self.main_overlay_toggle_btn)

        self.sidebar_showmatch_toggle_btn = primary_button(
            "Masquer overlay Showmatch" if self.state.showmatch_enabled else "Afficher overlay Showmatch",
            "#1A8CFF",
        )
        self.sidebar_showmatch_toggle_btn.clicked.connect(lambda: self.set_showmatch_enabled(not bool(self.state.showmatch_enabled)))
        side.addWidget(self.sidebar_showmatch_toggle_btn)

        beta_btn = QPushButton("Beta 3.8 By Luki7 /\nEraclesss / Julianout")
        beta_btn.setEnabled(False)
        beta_btn.setCursor(Qt.CursorShape.ArrowCursor)
        beta_btn.setMinimumHeight(46)
        beta_btn.setStyleSheet(
            "QPushButton:disabled{background:#22C55E;color:white;border:none;"
            "border-radius:12px;padding:8px 10px;font-weight:950;font-size:10px;"
            "line-height:1.15;text-align:center;}"
        )
        side.addWidget(beta_btn)
        quit_btn = primary_button("Fermer proprement", "#FF6B00")
        quit_btn.clicked.connect(lambda: self.shutdown_application(force_exit=True))
        side.addWidget(quit_btn)

        root.addWidget(sidebar)
        root.addWidget(self.stack, 1)
        self.setCentralWidget(shell)
        self._select_page(0)
        self._refresh_session_ui()

    def _select_page(self, index: int) -> None:
        if hasattr(self, "stack"):
            self.stack.setCurrentIndex(index)
        for i, btn in enumerate(getattr(self, "nav_buttons", [])):
            btn.blockSignals(True)
            btn.setChecked(i == index)
            btn.blockSignals(False)

    def _create_eye_toggle(self, edit: QLineEdit, hidden: bool = True) -> QPushButton:
        """Mini bouton pour masquer/afficher uniquement le texte d'un champ sensible."""
        edit.setEchoMode(QLineEdit.EchoMode.Password if hidden else QLineEdit.EchoMode.Normal)
        btn = QPushButton("🙈" if hidden else "👁️")
        btn.setFixedSize(30, 30)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setToolTip("Afficher" if hidden else "Masquer")
        btn.setStyleSheet(
            "QPushButton{background:#1A2133;color:#F6F8FF;border:1px solid #2A3550;"
            "border-radius:10px;padding:0;font-size:13px;font-weight:900;}"
            "QPushButton:hover{background:#26314A;border-color:#3B82F6;}"
        )

        def toggle() -> None:
            is_hidden = edit.echoMode() != QLineEdit.EchoMode.Normal
            should_hide = not is_hidden
            edit.setEchoMode(QLineEdit.EchoMode.Password if should_hide else QLineEdit.EchoMode.Normal)
            btn.setText("🙈" if should_hide else "👁️")
            btn.setToolTip("Afficher" if should_hide else "Masquer")

        btn.clicked.connect(toggle)
        return btn


    def _build_dashboard_tab(self) -> QWidget:
        root = QWidget()
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)

        hero = QFrame()
        hero.setObjectName("ShellCard")
        h = QHBoxLayout(hero)
        h.setContentsMargins(18, 16, 18, 16)
        h.setSpacing(14)
        title_box = QVBoxLayout()
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(10)
        title = QLabel("Dashboard")
        title.setStyleSheet("font-size:26px;font-weight:1000;color:#FFFFFF;background:transparent;")
        auto_rl_btn = primary_button("⚙ Config RL", "#3AE08A")
        auto_rl_btn.setToolTip("Détecter automatiquement Rocket League et écrire PacketSendRate + Port")
        auto_rl_btn.setFixedHeight(30)
        auto_rl_btn.setMinimumWidth(112)
        auto_rl_btn.setStyleSheet(
            "QPushButton{background:#143322;color:#D9FFE9;border:1px solid rgba(58,224,138,.45);"
            "border-radius:10px;padding:6px 10px;font-size:11px;font-weight:900;}"
            "QPushButton:hover{background:#1F6B3E;color:white;border:1px solid rgba(58,224,138,.85);}"
        )
        auto_rl_btn.clicked.connect(self._install_statsapi_config)
        title_row.addWidget(title)
        title_row.addWidget(auto_rl_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        title_row.addStretch(1)
        self.status_dot = QLabel("●")
        self.status_dot.setStyleSheet("color:#8C96AC;font-size:22px;background:transparent;")
        self.status_text = QLabel("Non connecté")
        self.status_text.setStyleSheet("color:#B8C1D6;font-size:12px;font-weight:800;background:transparent;")
        status_line = QHBoxLayout()
        status_line.addWidget(self.status_dot)
        status_line.addWidget(self.status_text, 1)
        title_box.addLayout(title_row)
        title_box.addLayout(status_line)
        h.addLayout(title_box, 1)
        self.player_label = value_label("—", 24, "#F6F8FF")
        self.playlist_label = muted_label("Playlist : Aucune")
        player_col = QVBoxLayout()
        player_col.addWidget(muted_label("JOUEUR"), alignment=Qt.AlignmentFlag.AlignRight)
        player_col.addWidget(self.player_label, alignment=Qt.AlignmentFlag.AlignRight)
        player_col.addWidget(self.playlist_label, alignment=Qt.AlignmentFlag.AlignRight)
        h.addLayout(player_col)
        self.last_event_label = QLabel("—")
        self.last_event_label.hide()
        self.last_event_at_label = QLabel("—")
        self.last_event_at_label.hide()
        outer.addWidget(hero)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)
        self.stat_labels: Dict[str, QLabel] = {}
        stats = [
            ("wins", "Victoires", "#1A8CFF"),
            ("losses", "Défaites", "#FF6B00"),
            ("streak", "Streak", "#FFD84D"),
            ("mmr", "MMR", "#FFD84D"),
            ("score", "Score", "#F6F8FF"),
        ]
        for idx, (key, label, color) in enumerate(stats):
            c = card(label)
            c.setFixedHeight(76)
            lab = value_label("—", 24, color)
            self.stat_labels[key] = lab
            c.layout().addWidget(lab)
            grid.addWidget(c, 0, idx)
        outer.addLayout(grid)

        quick = QGridLayout()
        quick.setHorizontalSpacing(12)
        quick.setVerticalSpacing(12)

        controls = card("Actions rapides")
        crow = QGridLayout()
        buttons = [
            ("+ Win", "#1A8CFF", lambda: self.add_result("win")),
            ("+ Loss", "#FF6B00", lambda: self.add_result("loss")),
            ("− Win", "#26314A", lambda: self.remove_result("win")),
            ("− Loss", "#26314A", lambda: self.remove_result("loss")),
            ("Reset", "#A536FF", self.reset_session),
            ("Reconnect", "#26314A", self.stats_client.reconnect),
        ]
        for i, (txt, color, cb) in enumerate(buttons):
            b = primary_button(txt, color)
            b.clicked.connect(cb)
            crow.addWidget(b, i // 3, i % 3)
        controls.layout().addLayout(crow)
        quick.addWidget(controls, 0, 0)

        session = card("Sauvegarde session")
        self.home_session_name = QLineEdit()
        self.home_session_name.setPlaceholderText("Nom de sauvegarde clair")
        self.home_session_combo = QComboBox()
        save_btn = primary_button("Sauvegarder", "#3AE08A")
        load_btn = primary_button("Reprendre", "#1A8CFF")
        delete_btn = primary_button("Supprimer", "#26314A")
        save_btn.clicked.connect(lambda: self.save_current_session(self.home_session_name.text().strip()))
        load_btn.clicked.connect(lambda: self.load_saved_session(self.home_session_combo.currentText()))
        delete_btn.clicked.connect(lambda: self.delete_saved_session(self.home_session_combo.currentText()))
        session.layout().addWidget(self.home_session_name)
        session.layout().addWidget(self.home_session_combo)
        srow = QHBoxLayout()
        srow.addWidget(save_btn)
        srow.addWidget(load_btn)
        srow.addWidget(delete_btn)
        session.layout().addLayout(srow)
        quick.addWidget(session, 0, 1)

        logs_toggle_card = card("Logs live")
        logs_toggle_row = QHBoxLayout()
        logs_toggle_row.addWidget(muted_label("Masqués par défaut pour garder le dashboard compact."), 1)
        self.logs_toggle_btn = primary_button("Afficher les logs", "#26314A")
        self.logs_toggle_btn.clicked.connect(self._toggle_logs_panel)
        logs_toggle_row.addWidget(self.logs_toggle_btn)
        logs_toggle_card.layout().addLayout(logs_toggle_row)
        quick.addWidget(logs_toggle_card, 1, 0, 1, 2)

        self.log_card = card("Logs live")
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setFixedHeight(118)
        try:
            self.log_box.document().setMaximumBlockCount(20)
        except Exception:
            pass
        self.log_card.layout().addWidget(self.log_box)
        self.log_card.hide()
        quick.addWidget(self.log_card, 2, 0, 1, 2)
        outer.addLayout(quick, 1)
        return root

    def _build_overlay_tab(self) -> QWidget:
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        obs = card("OBS Browser Source", "URL à coller dans OBS. Le rendu reste dynamique quand tu actives/désactives des blocs.")
        url_row = QHBoxLayout()
        self.obs_url = QLineEdit()
        self.obs_url.setReadOnly(True)
        copy_obs = primary_button("Copier", "#1A8CFF")
        open_obs = primary_button("Ouvrir", "#26314A")
        copy_obs.clicked.connect(lambda: self._copy(self.obs_url.text()))
        open_obs.clicked.connect(lambda: webbrowser.open(self.obs_url.text()))
        url_row.addWidget(self.obs_url, 1)
        url_row.addWidget(self._create_eye_toggle(self.obs_url, hidden=True))
        url_row.addWidget(copy_obs)
        url_row.addWidget(open_obs)
        obs.layout().addLayout(url_row)
        layout.addWidget(obs)

        cards_grid = QGridLayout()
        cards_grid.setHorizontalSpacing(12)
        cards_grid.setVerticalSpacing(12)

        style_card = card("Overlay principal", "Format bannière verrouillé avec MMR, Wins, Losses et Streak.")
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        self.scale_spin = QSpinBox()
        self.scale_spin.setRange(60, 180)
        self.scale_spin.setSuffix(" %")
        self.scale_spin.setValue(int(self.config["theme"].get("scale", 100)))
        self.scale_spin.valueChanged.connect(lambda v: self.update_theme({"scale": v}))
        grid.addWidget(muted_label("Format"), 0, 0)
        grid.addWidget(muted_label("Bannière unique"), 0, 1)
        grid.addWidget(muted_label("Scale"), 1, 0)
        grid.addWidget(self.scale_spin, 1, 1)
        style_card.layout().addLayout(grid)

        options = card("Options actives")
        opts = QGridLayout()
        self.checks: Dict[str, QCheckBox] = {}
        for idx, (key, label) in enumerate([
            ("show_mmr", "Afficher MMR"),
            ("animate", "Dégradé streak animé"),
        ]):
            cb = QCheckBox(label)
            cb.setChecked(bool(self.config["theme"].get(key, True)))
            cb.toggled.connect(lambda checked, k=key: self.update_theme({k: bool(checked)}))
            self.checks[key] = cb
            opts.addWidget(cb, idx, 0)
        self.overlay_exclusive_cb = QCheckBox("Mode exclusif : masquer automatiquement l’autre overlay")
        self.overlay_exclusive_cb.setChecked(bool(self.config.get("overlay_exclusive_mode", True)))
        self.overlay_exclusive_cb.setToolTip("Activé : afficher Showmatch masque Win/Lose, et afficher Win/Lose masque Showmatch.")
        self.overlay_exclusive_cb.toggled.connect(self.set_overlay_exclusive_mode)
        opts.addWidget(self.overlay_exclusive_cb, 2, 0)
        options.layout().addLayout(opts)

        manual = card("Playlist / MMR manuel")
        mgrid = QGridLayout()
        self.playlist_combo = QComboBox()
        self.playlist_combo.addItems(PLAYLIST_COMBO_ITEMS)
        self.playlist_combo.setCurrentText(self.state.selected_playlist if self.state.selected_playlist in PLAYLIST_NAMES else NO_PLAYLIST_LABEL)
        self.playlist_combo.currentTextChanged.connect(self.select_playlist)
        self.mmr_edit = QLineEdit(); self.mmr_edit.setPlaceholderText("MMR ex: 1432")
        self.rank_edit = QLineEdit(); self.rank_edit.setPlaceholderText("Rank optionnel")
        set_mmr = primary_button("Mettre à jour", "#1A8CFF")
        set_mmr.clicked.connect(self._set_mmr_from_ui)
        mgrid.addWidget(self.playlist_combo, 0, 0)
        mgrid.addWidget(self.mmr_edit, 0, 1)
        mgrid.addWidget(self.rank_edit, 0, 2)
        mgrid.addWidget(set_mmr, 0, 3)
        manual.layout().addLayout(mgrid)

        showmatch = card("Overlay Showmatch", "Source OBS transparente contrôlée manuellement : affiche/masque l’overlay, choix BO, scores de série et game actuelle.")
        smgrid = QGridLayout()
        self.showmatch_url = QLineEdit(); self.showmatch_url.setReadOnly(True)
        sm_copy = primary_button("Copier URL", "#1A8CFF")
        sm_open = primary_button("Ouvrir", "#26314A")
        sm_copy.clicked.connect(lambda: self._copy(self.showmatch_url.text()))
        sm_open.clicked.connect(lambda: webbrowser.open(self.showmatch_url.text()))
        self.showmatch_toggle_btn = primary_button("Masquer overlay" if self.state.showmatch_enabled else "Afficher overlay", "#1A8CFF")
        self.showmatch_toggle_btn.clicked.connect(lambda: self.set_showmatch_enabled(not bool(self.state.showmatch_enabled)))
        self.showmatch_bo_combo = QComboBox(); self.showmatch_bo_combo.addItems(["BO3", "BO5", "BO7", "BO9"])
        self.showmatch_bo_combo.setCurrentText(f"BO{int(self.state.showmatch_bo)}")
        self.showmatch_bo_combo.currentTextChanged.connect(lambda v: self.set_showmatch_bo(int(str(v).replace("BO", "") or 5)))
        self.showmatch_game_spin = QSpinBox(); self.showmatch_game_spin.setRange(1, int(self.state.showmatch_bo))
        self.showmatch_game_spin.setValue(max(1, min(int(self.state.showmatch_current_game or 1), int(self.state.showmatch_bo))))
        self.showmatch_game_spin.valueChanged.connect(lambda v: self.set_showmatch_current_game(int(v)))
        self.showmatch_left_edit = QLineEdit(self.state.showmatch_left_name or "Player")
        self.showmatch_right_edit = QLineEdit(self.state.showmatch_right_name or "Opponent")
        self.showmatch_left_edit.setPlaceholderText("Nom joueur gauche")
        self.showmatch_right_edit.setPlaceholderText("Nom joueur droite")
        self.showmatch_left_edit.textChanged.connect(lambda v: self.set_showmatch_names(v, self.showmatch_right_edit.text()))
        self.showmatch_right_edit.textChanged.connect(lambda v: self.set_showmatch_names(self.showmatch_left_edit.text(), v))
        sm_add_left = primary_button("+ Game gauche", "#1A8CFF")
        sm_add_right = primary_button("+ Game droite", "#FF6B00")
        sm_reset = primary_button("Reset BO", "#FF6B00")
        sm_undo = primary_button("Annuler game", "#26314A")
        sm_add_left.clicked.connect(lambda: self.add_showmatch_manual_game("left"))
        sm_add_right.clicked.connect(lambda: self.add_showmatch_manual_game("right"))
        sm_reset.clicked.connect(self.reset_showmatch)
        sm_undo.clicked.connect(self.undo_showmatch_game)
        self.showmatch_status_label = muted_label("Showmatch : en attente")
        smgrid.addWidget(self.showmatch_url, 0, 0, 1, 3)
        smgrid.addWidget(self._create_eye_toggle(self.showmatch_url, hidden=True), 0, 3)
        smgrid.addWidget(sm_copy, 0, 4)
        smgrid.addWidget(sm_open, 0, 5)
        smgrid.addWidget(self.showmatch_toggle_btn, 1, 0, 1, 2)
        smgrid.addWidget(muted_label("Best of"), 1, 2)
        smgrid.addWidget(self.showmatch_bo_combo, 1, 3)
        smgrid.addWidget(muted_label("Game actuelle"), 1, 4)
        smgrid.addWidget(self.showmatch_game_spin, 1, 5)
        smgrid.addWidget(self.showmatch_left_edit, 2, 0, 1, 3)
        smgrid.addWidget(self.showmatch_right_edit, 2, 3, 1, 3)
        smgrid.addWidget(sm_add_left, 3, 0, 1, 2)
        smgrid.addWidget(sm_add_right, 3, 2, 1, 2)
        smgrid.addWidget(sm_reset, 3, 4)
        smgrid.addWidget(sm_undo, 3, 5)
        smgrid.addWidget(self.showmatch_status_label, 4, 0, 1, 6)
        showmatch.layout().addLayout(smgrid)

        cards_grid.addWidget(style_card, 0, 0)
        cards_grid.addWidget(options, 0, 1)
        cards_grid.addWidget(manual, 1, 0, 1, 2)
        cards_grid.addWidget(showmatch, 2, 0, 1, 2)
        layout.addLayout(cards_grid)
        layout.addStretch()
        return root

    def _build_sessions_tab(self) -> QWidget:
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        panel = card("Sessions sauvegardées", "Sauvegarde la session actuelle, renomme-la clairement, puis recharge-la plus tard pour continuer.")
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)
        self.session_name_edit = QLineEdit()
        self.session_name_edit.setPlaceholderText("Nom : Ranked soir / Stream Mawkzy / Placement 2v2…")
        self.session_combo = QComboBox()
        save = primary_button("Sauvegarder la session actuelle", "#3AE08A")
        load = primary_button("Reprendre la sauvegarde", "#1A8CFF")
        rename = primary_button("Renommer", "#A536FF")
        delete = primary_button("Supprimer", "#26314A")
        save.clicked.connect(lambda: self.save_current_session(self.session_name_edit.text().strip()))
        load.clicked.connect(lambda: self.load_saved_session(self.session_combo.currentText()))
        rename.clicked.connect(lambda: self.rename_saved_session(self.session_combo.currentText(), self.session_name_edit.text().strip()))
        delete.clicked.connect(lambda: self.delete_saved_session(self.session_combo.currentText()))
        grid.addWidget(muted_label("Nom / nouveau nom"), 0, 0)
        grid.addWidget(self.session_name_edit, 0, 1, 1, 3)
        grid.addWidget(muted_label("Dernière sauvegarde"), 1, 0)
        grid.addWidget(self.session_combo, 1, 1, 1, 3)
        grid.addWidget(save, 2, 0)
        grid.addWidget(load, 2, 1)
        grid.addWidget(rename, 2, 2)
        grid.addWidget(delete, 2, 3)
        self.session_info_label = muted_label("Aucune sauvegarde chargée.")
        grid.addWidget(self.session_info_label, 3, 0, 1, 4)
        panel.layout().addLayout(grid)
        layout.addWidget(panel)
        layout.addStretch()
        return root

    def _build_remote_tab(self) -> QWidget:
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)
        remote = card("Panneau de contrôle à distance", "Ouvre cette URL depuis un navigateur sur le même PC ou un téléphone connecté au même réseau Wi-Fi. Le token protège les commandes.")
        self.remote_url = QLineEdit()
        self.remote_url.setReadOnly(True)
        row = QHBoxLayout()
        copy_remote = primary_button("Copier", "#1A8CFF")
        open_remote = primary_button("Ouvrir", "#26314A")
        copy_remote.clicked.connect(lambda: self._copy(self.remote_url.text()))
        open_remote.clicked.connect(lambda: webbrowser.open(self.remote_url.text()))
        row.addWidget(self.remote_url, 1)
        row.addWidget(self._create_eye_toggle(self.remote_url, hidden=True))
        row.addWidget(copy_remote)
        row.addWidget(open_remote)
        remote.layout().addLayout(row)
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(14)

        ip = card("Accès téléphone")
        self.lan_url = QLineEdit()
        self.lan_url.setReadOnly(True)
        lan_row = QHBoxLayout()
        copy_lan = primary_button("Copier URL téléphone", "#1A8CFF")
        copy_lan.clicked.connect(lambda: self._copy(self.lan_url.text()))
        lan_row.addWidget(self.lan_url, 1)
        lan_row.addWidget(self._create_eye_toggle(self.lan_url, hidden=True))
        lan_row.addWidget(copy_lan)
        ip.layout().addLayout(lan_row)
        ip.layout().addWidget(muted_label("Autorise l'application dans le pare-feu Windows si ton téléphone ne se connecte pas."))

        security = card("Token remote")
        token_row = QHBoxLayout()
        self.token_edit = QLineEdit(self.config.get("remote_key", ""))
        regen = primary_button("Régénérer", "#A536FF")
        regen.clicked.connect(self._regenerate_token)
        token_row.addWidget(self.token_edit, 1)
        token_row.addWidget(self._create_eye_toggle(self.token_edit, hidden=True))
        token_row.addWidget(regen)
        security.layout().addLayout(token_row)
        grid.addWidget(remote, 0, 0)
        grid.addWidget(ip, 0, 1)
        grid.addWidget(security, 1, 0, 1, 2)
        layout.addLayout(grid)
        layout.addStretch()
        return root

    def _build_settings_tab(self) -> QWidget:
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        api = card("StatsAPI Rocket League", "Le fichier de configuration de ta source StatsAPI doit pointer vers le même port. Exemple : PacketSendRate=30 / Port=49123.")
        row = QHBoxLayout()
        self.host_edit = QLineEdit(str(self.config.get("statsapi_host", "127.0.0.1")))
        self.port_edit = QLineEdit(str(self.config.get("statsapi_port", DEFAULT_STATSAPI_PORT)))
        save = primary_button("Sauvegarder + reconnecter", "#1A8CFF")
        save.clicked.connect(self._save_api_settings)
        row.addWidget(muted_label("Host"))
        row.addWidget(self.host_edit)
        row.addWidget(self._create_eye_toggle(self.host_edit, hidden=True))
        row.addWidget(muted_label("Port"))
        row.addWidget(self.port_edit)
        row.addWidget(self._create_eye_toggle(self.port_edit, hidden=True))
        row.addWidget(save)
        api.layout().addLayout(row)
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(14)

        test = card("Test live")
        trow = QHBoxLayout()
        sim_update = primary_button("Simuler UpdateState", "#26314A")
        sim_win = primary_button("Simuler MatchEnded WIN", "#1A8CFF")
        sim_loss = primary_button("Simuler MatchEnded LOSS", "#FF6B00")
        sim_training = primary_button("Simuler entraînement ignoré", "#26314A")
        sim_update.clicked.connect(self.simulate_update_state)
        sim_win.clicked.connect(lambda: self.add_result("win", auto=True))
        sim_loss.clicked.connect(lambda: self.add_result("loss", auto=True))
        sim_training.clicked.connect(self.simulate_training_state)
        for b in (sim_update, sim_win, sim_loss, sim_training):
            trow.addWidget(b)
        test.layout().addLayout(trow)

        tracker = card("API RLS", "Recherche du MMR et de la position leaderboard via l'API RLS automatiquement 2s après MatchEnded / MatchDestroyed. Le bouton manuel reste disponible.")
        tr = QGridLayout()
        self.tracker_platform_combo = QComboBox()
        self.tracker_platform_combo.addItems(["auto", "epic", "steam", "xbl", "psn", "switch"])
        self.tracker_platform_combo.setCurrentText(str(self.config.get("tracker_platform", "auto")))
        self.tracker_platform_combo.currentTextChanged.connect(lambda v: self.config.__setitem__("tracker_platform", v))
        self.tracker_player_edit = QLineEdit(str(self.config.get("tracker_force_player", "")))
        self.tracker_player_edit.setPlaceholderText("Auto : plateforme + PrimaryId JSON uniquement")
        self.tracker_player_edit.textChanged.connect(self._on_tracker_force_player_changed)
        tracker_refresh = primary_button("Rafraîchir rank manuel", "#1A8CFF")
        tracker_refresh.clicked.connect(lambda: self._maybe_refresh_tracker_rank(True, "manuel forcé prioritaire"))
        tr.addWidget(muted_label("Plateforme"), 0, 0)
        tr.addWidget(self.tracker_platform_combo, 0, 1)
        tr.addWidget(self.tracker_player_edit, 1, 0, 1, 2)
        tr.addWidget(tracker_refresh, 2, 0, 1, 2)
        tracker.layout().addLayout(tr)

        raw = card("Dernier JSON reçu")
        self.raw_box = QTextEdit()
        self.raw_box.setReadOnly(True)
        self.raw_box.setMinimumHeight(250)
        raw.layout().addWidget(self.raw_box)
        grid.addWidget(api, 0, 0)
        grid.addWidget(test, 1, 0)
        grid.addWidget(tracker, 2, 0)
        grid.addWidget(raw, 0, 1, 3, 1)
        layout.addLayout(grid, 1)
        return root

    # ──────────────────────────────────────────────────────────────────────
    # State, publishing and UI refresh
    # ──────────────────────────────────────────────────────────────────────

    def get_public_state(self) -> Dict[str, Any]:
        with self.lock:
            try:
                # `showmatch_visible` n'existe pas dans l'état : la vraie valeur est
                # `showmatch_enabled`. L'ancien test empêchait la synchro des pseudos/teams
                # quand le Showmatch était affiché dans OBS.
                if getattr(self.state, "showmatch_enabled", False):
                    self._ensure_showmatch_names_locked()
            except Exception:
                pass
            public = self.state.to_dict(self.config["theme"])
            public["remote_key"] = self.config.get("remote_key", "")
            public["http_port"] = HTTP_PORT
            public["ws_port"] = WS_PORT
            public["ws_clients"] = len(self.hub.ws_clients)
            return public

    def _publish_state(self, count_revision: bool = True) -> None:
        try:
            # Pendant le traitement d'une rafale StatsAPI, on retarde les broadcasts.
            if getattr(self, "_batching_api_events", False):
                self._pending_publish_revision = bool(self._pending_publish_revision or count_revision)
                return

            now = time.time()
            # Les publications sans révision sont des statuts/heartbeats : pas besoin
            # de rafraîchir OBS/UI plusieurs fois par seconde.
            if not count_revision and now - float(getattr(self, "_last_publish_monotonic", 0.0) or 0.0) < 0.20:
                return
            self._last_publish_monotonic = now

            with self.lock:
                if count_revision:
                    self.state.revision += 1
                self.state.last_publish_at = time.strftime("%H:%M:%S")
            state = self.get_public_state()
            try:
                self.hub.broadcast(state)
            except Exception as exc:
                self._log(f"Broadcast OBS/remote ignoré : {exc}")
            try:
                # Ne jamais manipuler les widgets directement depuis un thread API/WebSocket.
                self.signals.state_changed.emit(state)
            except Exception as exc:
                self._log(f"Signal UI ignoré : {exc}")
        except Exception as exc:
            try:
                self._log(f"Publication état ignorée : {exc}")
            except Exception:
                pass


    def _refresh_ui(self, state: Dict[str, Any]) -> None:
        self.player_label.setText(state.get("player") or "—")
        self.playlist_label.setText(f"Playlist : {state.get('playlist_name') or 'Aucune'}")
        if hasattr(self, "playlist_combo"):
            combo_playlist = str(state.get("playlist") or "")
            combo_text = combo_playlist if combo_playlist in PLAYLIST_NAMES else NO_PLAYLIST_LABEL
            if self.playlist_combo.currentText() != combo_text:
                self.playlist_combo.blockSignals(True)
                self.playlist_combo.setCurrentText(combo_text)
                self.playlist_combo.blockSignals(False)
        self.last_event_label.setText(state.get("last_event") or "—")
        self.last_event_at_label.setText(state.get("last_event_at") or "En attente d'événement")
        self.stat_labels["wins"].setText(str(state.get("wins", 0)))
        self.stat_labels["losses"].setText(str(state.get("losses", 0)))
        sv = state.get("streak_val", 0)
        st = state.get("streak_type")
        self.stat_labels["streak"].setText(f"{sv}{'W' if st == 'win' else 'L' if st == 'loss' else ''}" if sv else "—")
        mmr = state.get("mmr")
        delta = state.get("mmr_change", 0)
        rank = state.get("rank") or ""
        rank_short = state.get("rank_short") or ""
        mmr_text = (f"{mmr} ({delta:+})" if delta else str(mmr)) if mmr else "—"
        self.stat_labels["mmr"].setText(f"{mmr_text} · {rank_short or rank}" if rank and mmr else mmr_text)
        score = state.get("score", {})
        self.stat_labels["score"].setText(f"{score.get('me', 0)} - {score.get('opponent', 0)}")
        if hasattr(self, "main_overlay_toggle_btn"):
            main_visible = bool(state.get("main_overlay_enabled", True))
            self.main_overlay_toggle_btn.setText("Masquer overlay Win/Lose" if main_visible else "Afficher overlay Win/Lose")
        if hasattr(self, "sidebar_showmatch_toggle_btn"):
            sm_state = state.get("showmatch", {}) or {}
            self.sidebar_showmatch_toggle_btn.setText("Masquer overlay Showmatch" if sm_state.get("enabled") else "Afficher overlay Showmatch")
        if hasattr(self, "showmatch_status_label"):
            sm = state.get("showmatch", {}) or {}
            status = f"Showmatch {sm.get('game_label', 'BO')} · {sm.get('left_name', 'Player')} {sm.get('left_score', 0)} - {sm.get('right_score', 0)} {sm.get('right_name', 'Opponent')}"
            if not sm.get("enabled"):
                status = "Showmatch masqué"
            elif sm.get("completed"):
                status += " · terminé"
            self.showmatch_status_label.setText(status)
            if hasattr(self, "showmatch_toggle_btn"):
                self.showmatch_toggle_btn.setText("Masquer overlay" if sm.get("enabled") else "Afficher overlay")
            if hasattr(self, "showmatch_game_spin"):
                current_game = int(sm.get("current_game", 1) or 1)
                bo = int(sm.get("bo", 5) or 5)
                self.showmatch_game_spin.blockSignals(True)
                self.showmatch_game_spin.setRange(1, bo)
                self.showmatch_game_spin.setValue(max(1, min(current_game, bo)))
                self.showmatch_game_spin.blockSignals(False)
        raw = state.get("last_raw_event") or self.state.last_raw_event
        if raw and hasattr(self, "raw_box"):
            try:
                raw_text = json.dumps(raw, ensure_ascii=False, separators=(",", ":"))[:5000]
            except Exception:
                raw_text = str(raw)[:5000]
            if raw_text != getattr(self, "_last_raw_box_text", ""):
                self._last_raw_box_text = raw_text
                self.raw_box.setPlainText(raw_text)

    def _on_status(self, status: str, message: str) -> None:
        color = {"connected": "#3AE08A", "connecting": "#FFD84D", "error": "#FF6B00", "disconnected": "#8C96AC"}.get(status, "#8C96AC")
        self.status_dot.setStyleSheet(f"color:{color};font-size:24px;background:transparent;")
        self.status_text.setText(message)
        saved_player = ""
        with self.lock:
            previous_status = str(self.state.connection or "")
            self.state.connection = status
            self.state.connection_message = message

            if status == "connected":
                # On arme une seule sauvegarde pour cette connexion API. Les boucles
                # de reconnexion sans connexion réelle ne créent pas de sauvegardes vides.
                self._api_connected_since_last_disconnect_save = True
            elif status == "disconnected" and self._api_connected_since_last_disconnect_save:
                # Toujours sauvegarder avant de nettoyer l'état courant : on garde
                # la session terminée dans les sauvegardes, puis l'app revient à zéro
                # pour accueillir le prochain compte / la prochaine session StatsAPI.
                saved_player = self._auto_save_current_player_on_api_disconnect_locked()
                self._reset_runtime_session_after_statsapi_disconnect_locked()
                self._api_connected_since_last_disconnect_save = False
            elif status == "disconnected":
                self._reset_runtime_session_after_statsapi_disconnect_locked()
            elif status in {"error", "connecting"} and previous_status != "connected":
                # Pas de sauvegarde si l'API n'a jamais été connectée depuis le dernier essai.
                pass

        if saved_player:
            self._refresh_session_ui()
            self._log(f"API déconnectée : sauvegarde automatique de {saved_player} écrasée/mise à jour")
            self._log("Session courante réinitialisée : stats, joueur, playlist et API RLS remis à zéro")
        if status == "disconnected":
            self._sync_tracker_inputs_from_config()
        # Le comptage Showmatch est fait dans _handle_match_ended /
        # _handle_match_destroyed_by_score. Ne rien recompter ici : cette méthode
        # reçoit seulement les changements de statut de connexion.
        self._publish_state()


    def _toggle_logs_panel(self) -> None:
        if not hasattr(self, "log_card") or not hasattr(self, "logs_toggle_btn"):
            return
        visible = self.log_card.isVisible()
        self.log_card.setVisible(not visible)
        self.logs_toggle_btn.setText("Masquer les logs" if not visible else "Afficher les logs")
        try:
            self.adjustSize()
        except Exception:
            pass

    def _log(self, message: str) -> None:
        self.signals.log.emit(message)

    def _compact_log_message(self, message: str) -> str:
        """Garde uniquement un log utile, lisible et court."""
        msg = re.sub(r"\s+", " ", str(message or "")).strip()
        # Les URLs et chemins longs rendent les logs illisibles : on les résume.
        msg = re.sub(r"https?://\S+", "[url]", msg)
        msg = re.sub(r"[A-Za-z]:\\[^\s]+", "[chemin]", msg)
        if len(msg) > 170:
            msg = msg[:167].rstrip() + "…"
        return msg

    def _log_signature(self, message: str) -> str:
        sig = str(message or "").lower()
        sig = re.sub(r"\[[0-9:]+\]", "", sig)
        sig = re.sub(r"\d{1,2}:\d{2}:\d{2}", "", sig)
        sig = re.sub(r"\d{8,}", "#", sig)
        sig = re.sub(r"\s+", " ", sig).strip()
        return sig

    def _append_log(self, message: str) -> None:
        if not hasattr(self, "log_box"):
            return
        msg = self._compact_log_message(message)
        if not msg:
            return

        now = time.time()
        signature = self._log_signature(msg)

        # On garde les vrais résultats/sauvegardes, mais on supprime les répétitions
        # de détection/recherche qui polluent les logs pendant les rafales StatsAPI.
        important_prefixes = (
            "Résultat ajouté", "Résultat retiré",
            "MatchEnded →", "MatchDestroyed early",
            "Session ", "Mode ", "MMR ",
            "Overlay Showmatch", "Showmatch :",
        )
        is_important = msg.startswith(important_prefixes)
        if not is_important:
            if msg == getattr(self, "_last_log_message", ""):
                return
            last_seen = float(getattr(self, "_recent_log_signatures", {}).get(signature, 0.0) or 0.0)
            if last_seen and now - last_seen < 20:
                return

        self._last_log_message = msg
        self._recent_log_signatures[signature] = now
        # Nettoyage mémoire des signatures anciennes.
        self._recent_log_signatures = {
            k: v for k, v in self._recent_log_signatures.items()
            if now - float(v or 0.0) < 120
        }

        line = f"[{time.strftime('%H:%M:%S')}] {msg}"
        self._log_lines.append(line)
        self._log_lines = self._log_lines[-20:]
        self.log_box.setPlainText("\n".join(self._log_lines))
        sb = self.log_box.verticalScrollBar()
        sb.setValue(sb.maximum())

    # ──────────────────────────────────────────────────────────────────────
    # StatsAPI processing
    # ──────────────────────────────────────────────────────────────────────

    def _enqueue_api_event(self, event: Dict[str, Any]) -> None:
        """Ajoute un event sans laisser la queue exploser si l'API spamme."""
        try:
            self.event_queue.put_nowait(event)
        except queue.Full:
            # On supprime un vieux payload intermédiaire. Les events importants
            # suivants restent traités et le dernier UpdateState est coalescé au drain.
            try:
                self.event_queue.get_nowait()
            except Exception:
                pass
            try:
                self.event_queue.put_nowait(event)
            except Exception:
                pass

    def _drain_events(self) -> None:
        raw_events: List[Dict[str, Any]] = []
        processed = 0
        while processed < 80:
            try:
                event = self.event_queue.get_nowait()
            except queue.Empty:
                break
            if isinstance(event, dict):
                raw_events.append(event)
            else:
                self._log(f"Événement StatsAPI ignoré : format inattendu {type(event).__name__}")
            processed += 1

        if not raw_events:
            return

        # Les UpdateState arrivent très vite. On conserve uniquement le dernier
        # UpdateState de chaque rafale, sans déplacer les events critiques.
        events: List[Dict[str, Any]] = []
        latest_update: Optional[Dict[str, Any]] = None
        for event in raw_events:
            event_name = str(event.get("Event", ""))
            if event_name in ("UpdateState", "GameUpdate", "GameTick"):
                latest_update = event
                continue
            if latest_update is not None:
                events.append(latest_update)
                latest_update = None
            events.append(event)
        if latest_update is not None:
            events.append(latest_update)

        self._batching_api_events = True
        try:
            for event in events:
                try:
                    self.process_api_event(event)
                except Exception as exc:
                    self._log(f"Événement StatsAPI ignoré après erreur : {exc}")
                    try:
                        CRASH_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
                        with (CRASH_LOG_PATH).open("a", encoding="utf-8") as f:
                            f.write(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] StatsAPI event error\n")
                            f.write(traceback.format_exc())
                            f.write("\nPayload: " + repr(event)[:4000] + "\n")
                    except Exception:
                        pass
        finally:
            self._batching_api_events = False

        # Une seule publication OBS/UI par rafale d'events au lieu d'une publication par JSON.
        pending_revision = bool(self._pending_publish_revision)
        self._pending_publish_revision = False
        self._publish_state(count_revision=True or pending_revision)

    def _handle_server_change_before_event(self, server_key: str, event: str) -> None:
        """Sécurise les changements de serveur/match.

        Objectif :
        - ne pas mélanger deux matchs différents ;
        - ne pas compter deux fois ;
        - si une ranked disparaît sans MatchEnded, tenter une fermeture par score/API.
        """
        if not server_key:
            return

        final_event = event in ("MatchEnded", "MatchDestroyed")
        with self.lock:
            current = self.state.current_server_key
            match_active = bool(self.state.match_active)
            already_counted = bool(self.state.match_counted)
            ranked_active = bool(
                self.state.current_match_ranked
                or self.state.current_match_had_ranked_context
            )
            no_stats_active = bool(
                self.state.training_active
                or self.state.current_match_private
                or self.state.current_match_no_stats
            )

            if not current:
                self.state.current_server_key = server_key
                if not self.state.current_match_key:
                    self.state.current_match_key = server_key
                return

            if server_key == current:
                return

            # Ne jamais couper une notification officielle de fin de match.
            if final_event:
                return

        # Changement de serveur avant event final :
        # si c'était une ranked non comptée, on ferme proprement par score/API.
        if match_active and ranked_active and not no_stats_active and not already_counted:
            self._log("Changement serveur détecté : fermeture de l'ancienne ranked par score/API avant nouvelle partie")
            self._handle_match_destroyed_by_score()
        elif match_active:
            self._log("Changement serveur détecté : nettoyage du contexte live précédent")
            self._clear_match_live_state()

        with self.lock:
            self.state.last_server_key = current
            self.state.current_server_key = server_key
            self.state.last_server_change_at = time.time()
            self.state.current_match_key = server_key
        self._log("Nouveau serveur/match détecté via API")

    def process_api_event(self, outer: Dict[str, Any]) -> None:
        event = str(outer.get("Event", ""))
        inner = outer.get("Data", {})
        if isinstance(inner, str):
            try:
                inner = json.loads(inner)
            except Exception:
                inner = {}

        final_winner = extract_winner_team_from_payload(outer, inner)
        with self.lock:
            self.state.last_event = event or "JSON"
            self.state.last_event_at = time.strftime("%H:%M:%S")
            self.state.last_raw_event = outer
            if final_winner is not None:
                self.state.current_match_api_winner = int(final_winner)
                self.state.current_match_end_reason = event or "end-info"

        inferred_playlist = None
        if isinstance(inner, dict):
            game = inner.get("Game", {}) if isinstance(inner.get("Game", {}), dict) else {}
            players = extract_players_collection(outer, inner)
            teams = extract_teams_collection(outer, inner)
            inferred_playlist = self._infer_playlist_from_players(players)
        else:
            players = []
            teams = []

        api_playlist = extract_playlist_from_payload(outer, inner)
        detected_playlist = resolve_playlist_from_game_and_players(
            api_playlist,
            inferred_playlist,
            players_available=bool(players),
        )
        if api_playlist and inferred_playlist and api_playlist != inferred_playlist:
            self._log(
                f"Playlist ignorée : JSON={api_playlist} mais joueurs présents={inferred_playlist} · attente cohérence"
            )
        server_key = extract_server_match_key(outer, inner)
        self._handle_server_change_before_event(server_key, event)
        configured_platform = str(self.config.get("tracker_platform", "auto") or "auto")
        api_platform = detect_api_platform_context(configured_platform, players, outer, inner)
        final_event = event in ("MatchEnded", "MatchDestroyed")

        with self.lock:
            ranked_mode_locked = bool(
                (self.state.match_active or self.state.current_match_had_ranked_context or self.state.current_match_ranked)
                and (self.state.current_match_ranked or self.state.current_match_had_ranked_context)
                and not self.state.current_match_private
                and not self.state.current_match_no_stats
                and not self.state.training_active
            )

        if ranked_mode_locked and not final_event:
            with self.lock:
                locked_playlist = self.state.current_match_locked_playlist if self.state.current_match_playlist_locked else ""
            match_context = {
                "type": "ranked",
                "reason": "ranked verrouillé jusqu'à MatchEnded/MatchDestroyed",
                # Ne jamais réutiliser selected_playlist comme détection : elle peut venir
                # d'une ancienne game. Seule une playlist déjà verrouillée est fiable.
                "playlist": locked_playlist or None,
            }
        else:
            match_context = classify_rl_match_context(api_platform, players, teams, outer, inner)
        player_count_now = count_distinct_players(players)
        team_context_now = bool(players_have_multiple_teams(players) or teams_have_multiple_sides(teams))
        # Règle globale : il faut avoir détecté un adversaire une fois dans la partie.
        # Dans certains matchs avec club/team, l'API ne renvoie pas toujours tous les
        # joueurs mais renvoie bien deux objets Team nommés/scorés : on valide alors
        # le match normalement au lieu de le confondre avec le Freeplay.
        opponent_present_now = bool(player_count_now >= 2 or team_context_now)
        context_type = str(match_context.get("type", "waiting"))
        context_reason = str(match_context.get("reason", ""))
        if not detected_playlist:
            detected_playlist = match_context.get("playlist")

        with self.lock:
            if opponent_present_now:
                self.state.current_match_had_opponent = True
            if context_type == "ranked":
                self.state.current_match_had_ranked_context = True

            active_ranked_match = bool(
                self.state.match_active
                and (self.state.current_match_ranked or self.state.current_match_had_ranked_context)
                and not self.state.current_match_private
                and not self.state.current_match_no_stats
            )
            active_no_stats = bool(self.state.current_match_no_stats)
            active_no_stats_private = bool(self.state.current_match_no_stats and self.state.current_match_private)
            ranked_seen_for_match = bool(self.state.current_match_had_ranked_context or self.state.current_match_ranked or context_type == "ranked")
            active_ranked_playlist = self.state.current_match_locked_playlist if self.state.current_match_playlist_locked else ""
            waiting_match_destroy = bool(getattr(self.state, "current_match_waiting_destroy", False))

        # Si une détection freeplay temporaire arrive avant le vrai contexte ranked,
        # on laisse le ranked reprendre la priorité. Un vrai privé reste bloqué no-stats.
        if active_no_stats and not active_no_stats_private and context_type == "ranked":
            with self.lock:
                self.state.current_match_no_stats = False
                self.state.current_match_no_stats_reason = ""
                self.state.training_active = False
            active_no_stats = False

        # Protection abandon ranked :
        # si un ranked est déjà actif, une fin de match avec moins d'infos joueurs
        # reste ranked pour traiter la win/loss API/score.
        if active_ranked_match and context_type in {"waiting"}:
            context_type = "ranked"
            context_reason = "match ranked déjà actif"
            if active_ranked_playlist:
                detected_playlist = active_ranked_playlist
        elif active_ranked_match and event in ("MatchEnded", "MatchDestroyed") and context_type in {"private", "freeplay"}:
            context_type = "ranked"
            context_reason = "fin de ranked protégée avant switch"
            if active_ranked_playlist:
                detected_playlist = active_ranked_playlist

        ranked_mode_detected = context_type == "ranked" or ranked_seen_for_match
        private_match_detected = context_type == "private"

        # Nouvelle règle : freeplay dès qu'il y a moins de 2 joueurs ou boost illimité.
        # Exception nécessaire : si une vraie ranked est déjà active, on protège uniquement
        # MatchEnded/MatchDestroyed pour comptabiliser la win/loss avant de nettoyer.
        freeplay_detected = context_type == "freeplay"
        if active_ranked_match and final_event and freeplay_detected:
            freeplay_detected = False
            ranked_mode_detected = True
            context_type = "ranked"
            context_reason = "fin de ranked protégée avant nettoyage"

        no_stats_detected = bool(private_match_detected or freeplay_detected or active_no_stats_private)

        if no_stats_detected:
            should_process_private_showmatch = bool(private_match_detected and event in ("UpdateState", "MatchEnded", "MatchDestroyed"))
            with self.lock:
                if event == "UpdateState" and context_type == "freeplay":
                    self._detect_player_name_from_payload_locked(inner if isinstance(inner, dict) else {}, "StatsAPI Freeplay")
                if context_type in {"private", "freeplay"}:
                    self.state.current_match_no_stats = True
                    self.state.current_match_no_stats_reason = context_reason
                reason = self.state.current_match_no_stats_reason or context_reason or "match ignoré"
                self.state.ignored_context = reason
                self.state.current_match_platform = api_platform
                self.state.training_active = bool(freeplay_detected or context_type == "freeplay")
                self.state.current_match_private = bool(private_match_detected or context_type == "private")
                self.state.current_match_ranked = False
                self.state.current_match_has_timer = False
                if event in ("MatchEnded", "MatchDestroyed"):
                    if should_process_private_showmatch:
                        self._log(f"{event} privé détecté → traitement Showmatch uniquement : {reason}")
                    else:
                        self._log(f"{event} ignoré : {reason}")
                        self._clear_match_context_locked()
                else:
                    label = "Freeplay / jeu libre" if freeplay_detected else "Match privé"
                    self._log(f"{label} détecté → aucune statistique overlay principal : {reason}")

            # Important : les matchs privés restent ignorés pour l'overlay principal,
            # mais ils doivent continuer à alimenter le Showmatch si le module est activé.
            if should_process_private_showmatch:
                if event == "UpdateState":
                    self._handle_update_state(inner if isinstance(inner, dict) else {})
                    self._publish_state(count_revision=False)
                    return
                if event == "MatchEnded":
                    self._handle_match_ended(inner if isinstance(inner, dict) else {})
                    self._maybe_refresh_tracker_rank(False, "api-match-ended")
                    return
                if event == "MatchDestroyed":
                    self._handle_match_destroyed_by_score()
                    self._maybe_refresh_tracker_rank(False, "api-match-destroyed")
                    return

            self._publish_state(count_revision=False)
            return

        if not ranked_mode_detected:
            # Si ce bloc arrive, on ignore simplement sans changer de statistiques.
            with self.lock:
                self.state.ignored_context = context_reason or "mode non-ranked"
                self.state.current_match_ranked = False
                self.state.current_match_private = False
                self.state.current_match_platform = api_platform
                self.state.last_event = f"{event or 'JSON'} ignoré"
            self._publish_state(count_revision=False)
            return

        with self.lock:
            if self.state.training_active or self.state.current_match_no_stats:
                label = PLAYLIST_NAMES.get(detected_playlist, detected_playlist or "ranked")
                self._log(f"Sortie contexte ignoré → ranked détecté : {label}")
            self.state.training_active = False
            self.state.current_match_no_stats = False
            self.state.current_match_no_stats_reason = ""
            self.state.ignored_context = ""
            self.state.current_match_platform = api_platform
            self.state.current_match_private = False
            self.state.current_match_ranked = True
            self.state.current_match_had_ranked_context = True
            if opponent_present_now:
                self.state.current_match_had_opponent = True
            # Playlist sécurisée : une playlist détectée doit rester inchangée 5 secondes
            # avant d'être appliquée, puis elle reste verrouillée jusqu'au MatchDestroyed.
            # Ça évite les faux changements de mode pendant la partie ou l'écran post-game.
            if detected_playlist in PLAYLIST_NAMES:
                self._consider_match_playlist_lock_locked(detected_playlist, event, "ranked détecté", inner if isinstance(inner, dict) else {})
            if event in ("UpdateState", "MatchCreated", "MatchStarted") and not active_ranked_match:
                self._log(f"Match ranked détecté : {context_reason}")

        self._auto_detect_playlist_and_mmr(outer, inner)

        if event == "UpdateState":
            self._handle_update_state(inner if isinstance(inner, dict) else {})
        elif event == "MatchEnded":
            self._handle_match_ended(inner if isinstance(inner, dict) else {})
            self._maybe_refresh_tracker_rank(False, "api-match-ended")
        elif event == "MatchDestroyed":
            self._handle_match_destroyed_by_score()
            # Ne pas changer de playlist sur l'écran de destruction : la playlist valide
            # de la partie devait déjà être verrouillée après 5 secondes stables.
            # Le MatchDestroyed sert uniquement à libérer le verrou pour la prochaine game.
            self._maybe_refresh_tracker_rank(False, "api-match-destroyed")
        elif event:
            pass

    def _is_statsapi_player_detection_source(self, source: str) -> bool:
        source_l = str(source or "").casefold()
        if not source_l:
            return True
        return "statsapi" in source_l or "api" in source_l

    def _lock_freeplay_player_until_api_disconnect_locked(self, player_name: str, source: str = "StatsAPI Freeplay") -> bool:
        """Verrouille le joueur local détecté en Freeplay jusqu'à la déconnexion StatsAPI.

        Le Freeplay est le seul moment fiable où l'app voit uniquement son joueur.
        Une fois ce pseudo trouvé, les payloads de match ne peuvent plus basculer
        l'overlay principal vers un teammate/adversaire tant que StatsAPI reste connecté.
        """
        name = str(player_name or "").strip()
        if not name:
            return False
        locked = str(self.state.statsapi_freeplay_locked_player or "").strip()
        if locked and locked.casefold() == name.casefold():
            return False
        if locked and locked.casefold() != name.casefold():
            # Tant que StatsAPI n'est pas déconnecté, on ne remplace pas le joueur
            # Freeplay déjà validé par un autre pseudo API.
            return False
        self.state.statsapi_freeplay_locked_player = name
        self.state.statsapi_freeplay_locked_at = time.time()
        try:
            self._log(f"Joueur principal verrouillé depuis Freeplay jusqu'à déconnexion StatsAPI : {name}")
        except Exception:
            pass
        return True

    def _clear_freeplay_player_lock_on_api_disconnect_locked(self) -> str:
        locked = str(self.state.statsapi_freeplay_locked_player or "").strip()
        self.state.statsapi_freeplay_locked_player = ""
        self.state.statsapi_freeplay_locked_at = 0.0
        self.state.pending_detected_player_name = ""
        self.state.pending_detected_player_since = 0.0
        self.state.pending_detected_player_last_seen = 0.0
        return locked

    def _detect_player_name_from_payload_locked(self, inner: Dict[str, Any], source: str = "StatsAPI") -> bool:
        """Détecte le vrai joueur local de l'application pour l'overlay principal.

        On essaie d'abord les indices fiables du JSON : joueur Freeplay verrouillé,
        champ local/self/primary, indices locaux du payload, puis le joueur déjà
        connu. `Players[0]` reste seulement un fallback compatible avec le format
        où le joueur local est placé juste sous MatchGUID. Le pseudo/ID API RLS ne
        force plus la détection des stats principales.
        """
        if not isinstance(inner, dict):
            return False
        game = inner.get("Game", {}) if isinstance(inner.get("Game", {}), dict) else {}
        target = game.get("Target", {}) if isinstance(game.get("Target", {}), dict) else {}
        players = extract_players_collection(inner)
        teams = extract_teams_collection(inner)
        source_l = str(source or "").casefold()
        is_freeplay_source = bool("freeplay" in source_l or "jeu libre" in source_l or self.state.training_active)
        # Le pseudo/ID API RLS reste disponible pour les requêtes MMR/rank, mais
        # il ne doit plus forcer l'identité utilisée par les stats principales.
        current_name = str(self.state.detected_player_name or "").strip()
        locked_freeplay_name = str(self.state.statsapi_freeplay_locked_player or "").strip()
        is_statsapi_detection = self._is_statsapi_player_detection_source(source)

        name = ""
        team_num: Optional[int] = None
        local_reason = ""

        if locked_freeplay_name and is_statsapi_detection:
            # Le joueur vu en Freeplay reste le joueur principal de l'application
            # jusqu'à la déconnexion StatsAPI. API RLS ne peut plus le remplacer.
            locked_player = find_player_by_identity_hint(players, locked_freeplay_name)
            if isinstance(locked_player, dict):
                name = player_display_name_from_obj(locked_player) or locked_freeplay_name
                team_num = player_team_num_from_obj(locked_player, teams)
            else:
                name = locked_freeplay_name
            local_reason = "joueur Freeplay verrouillé"
        else:
            local_player, local_reason = extract_local_player_candidate_from_payload(
                inner,
                current_player_name=current_name,
                forced_player_hint="",
            )

            if isinstance(local_player, dict):
                name = player_display_name_from_obj(local_player)
                team_num = player_team_num_from_obj(local_player, teams)

            # Fallback très limité : si aucune collection Players n'existe, on accepte
            # Game.Target uniquement en Freeplay/joueur seul. En match, Target peut pointer
            # vers une caméra, un mate ou un adversaire, donc il ne doit pas changer le
            # joueur principal.
            allow_target_fallback = bool(
                not name
                and target
                and not players
                and is_freeplay_source
            )
            if allow_target_fallback:
                name = player_display_name_from_obj(target)
                team_num = player_team_num_from_obj(target, teams)
                local_reason = "fallback Freeplay Target"

        if not name:
            return False

        detection_source = f"{source} · {local_reason}" if local_reason else source
        changed_player = self._set_detected_player_name_locked(name, detection_source)
        # Ne pas remplacer la team par celle d'un autre joueur si le nom candidat a été
        # refusé/gelé par la sécurité anti-switch.
        accepted_name = str(self.state.detected_player_name or "").strip()
        accepted = bool(accepted_name and accepted_name.casefold() == name.casefold())
        if accepted and is_freeplay_source:
            self._lock_freeplay_player_until_api_disconnect_locked(accepted_name, source)
        if accepted and team_num in (0, 1):
            self.state.my_team = int(team_num)
        if changed_player or (accepted and not current_name):
            suffix = f" · Team {team_num}" if team_num in (0, 1) else ""
            self._log(f"Joueur local application détecté : {name}{suffix} ({local_reason})")
        return accepted

    def _handle_update_state(self, inner: Dict[str, Any]) -> None:
        game = inner.get("Game", {}) if isinstance(inner.get("Game", {}), dict) else {}
        players = extract_players_collection(inner)
        teams = extract_teams_collection(inner)

        with self.lock:
            if self.state.training_active:
                # En Freeplay, on ne force aucune playlist, mais on conserve quand même le pseudo joueur.
                self._detect_player_name_from_payload_locked(inner, "StatsAPI Freeplay")
                # Récupère /{platform}/{id} en Freeplay une seule fois.
                self._try_save_rls_identity_from_payload_locked(inner, "Freeplay")
                return

            api_key = extract_match_key_from_payload(inner)
            if players or teams:
                if not self.state.match_active:
                    self.state.match_active = True
                    self.state.match_counted = False
                    # Le match peut être ranked OU privé.
                    # Ne pas forcer ranked ici : process_api_event classe le type juste avant.
                    # Si l'API donne un ID, on l'utilise. Sinon, on crée une clé locale unique au début du match.
                    self.state.current_match_key = api_key or self.state.current_server_key or f"local:{int(time.time() * 1000)}"
                    if self.state.current_match_key == self.state.last_closed_match_key and time.time() - self.state.last_closed_match_at < 120:
                        self.state.match_counted = True
                        self._log("Partie déjà comptabilisée : reprise d'événement ignorée")
                elif api_key and not self.state.current_match_key:
                    self.state.current_match_key = api_key
            if players:
                self.state.current_players = players
            if count_distinct_players(players) >= 2 or teams_have_multiple_sides(teams):
                self.state.current_match_had_opponent = True
            primary_player = extract_primary_player_from_payload(inner)
            if primary_player or self.state.my_team is None or not self.state.detected_player_name:
                self._detect_player_name_from_payload_locked(inner, "StatsAPI joueur principal")

            inferred = self._infer_playlist_from_players(players)
            if (
                inferred
                and self.state.current_match_ranked
                and not self.state.match_active
                and not self.state.current_match_private
                and not self.state.current_match_no_stats
                and self.config.get("auto_detect_playlist", True)
                and inferred != self.state.selected_playlist
            ):
                self._switch_playlist_locked(inferred, "ranked détecté par joueurs")

            for idx, team in enumerate(teams):
                try:
                    team_num = team_number_from_obj(team, idx if len(teams) >= 2 else None)
                    score = team_score_from_obj(team)
                    if team_num not in (0, 1) or score is None:
                        continue
                except Exception:
                    continue
                self.state.last_scores[int(team_num)] = int(score)
                self.state.team_scores[int(team_num)] = int(score)

            # Met à jour en live les pseudos et couleurs Showmatch selon les teams détectées.
            if self.state.showmatch_enabled:
                self._ensure_showmatch_names_locked()

    def _reset_match_playlist_lock_locked(self) -> None:
        self.state.current_match_playlist_locked = False
        self.state.current_match_locked_playlist = ""
        self.state.pending_match_playlist = ""
        self.state.pending_match_playlist_since = 0.0
        self.state.pending_match_playlist_last_seen = 0.0

    def _consider_match_playlist_lock_locked(self, playlist: Optional[str], event: str, source: str = "API", payload: Optional[Dict[str, Any]] = None) -> bool:
        """Verrouille la playlist d'une ranked seulement après 5 secondes stables.

        But : éviter qu'un UpdateState temporaire change la playlist au milieu d'une
        partie et comptabilise ensuite la win/loss dans le mauvais mode. Une fois
        verrouillée, la playlist reste identique jusqu'au MatchDestroyed.
        """
        if not self.config.get("auto_detect_playlist", True):
            return False
        if playlist not in PLAYLIST_NAMES:
            return False
        if event in ("MatchEnded", "MatchDestroyed"):
            return False
        if self.state.current_match_waiting_destroy:
            return False
        if self.state.current_match_playlist_locked:
            return False

        now = time.time()
        if self.state.pending_match_playlist != playlist:
            self.state.pending_match_playlist = playlist
            self.state.pending_match_playlist_since = now
            self.state.pending_match_playlist_last_seen = now
            try:
                self._log(f"Playlist détectée : {PLAYLIST_NAMES.get(playlist, playlist)} · attente stabilité 5s")
            except Exception:
                pass
            return False

        self.state.pending_match_playlist_last_seen = now
        stable_for = now - float(self.state.pending_match_playlist_since or now)
        if stable_for < 5.0:
            return False

        self.state.current_match_playlist_locked = True
        self.state.current_match_locked_playlist = playlist
        changed = False
        if playlist != self.state.selected_playlist:
            changed = self._switch_playlist_locked(playlist, "verrouillée après 5s")

        # Beta 3.6 : la récupération /{platform}/{id} se fait uniquement
        # après le verrouillage de la playlist, et plus à la création du match.
        if isinstance(payload, dict):
            self._try_save_rls_identity_from_payload_locked(payload, "playlist verrouillée")

        try:
            self._log(f"Playlist verrouillée jusqu'au MatchDestroyed : {PLAYLIST_NAMES.get(playlist, playlist)}")
        except Exception:
            pass
        return changed

    def _ensure_result_playlist_locked(self, source: str) -> bool:
        """Sécurise la playlist avant d'ajouter une win/loss.

        Si la playlist n'a pas pu être verrouillée pendant la game, on tente une
        dernière validation depuis les joueurs réellement présents. Ça empêche une
        ancienne sélection 3v3 de recevoir le résultat d'une 1v1.
        """
        if self.state.current_match_playlist_locked and self.state.current_match_locked_playlist in PLAYLIST_NAMES:
            playlist = self.state.current_match_locked_playlist
            if playlist != self.state.selected_playlist:
                self._switch_playlist_locked(playlist, f"restaurée avant résultat {source}")
            return True

        api_playlist = extract_playlist_from_payload(self.state.last_raw_event)
        inferred = self._infer_playlist_from_players(self.state.current_players)
        resolved = resolve_playlist_from_game_and_players(
            api_playlist,
            inferred,
            players_available=bool(self.state.current_players),
        )
        if resolved in PLAYLIST_NAMES:
            self.state.current_match_playlist_locked = True
            self.state.current_match_locked_playlist = resolved
            if resolved != self.state.selected_playlist:
                self._switch_playlist_locked(resolved, f"validée avant résultat {source}")
            try:
                self._log(f"Playlist résultat validée : {PLAYLIST_NAMES.get(resolved, resolved)}")
            except Exception:
                pass
            return True

        if api_playlist and inferred and api_playlist != inferred:
            self._log(
                f"Résultat ignoré : playlist incohérente JSON={api_playlist} / joueurs={inferred}"
            )
            return False

        if not self.config.get("auto_detect_playlist", True) and self.state.selected_playlist in PLAYLIST_NAMES:
            return True

        self._log("Résultat ignoré : playlist ranked non confirmée par le JSON et les joueurs présents")
        return False

    def _current_result_signature_locked(self) -> str:
        scores = ",".join(f"{k}:{v}" for k, v in sorted(self.state.team_scores.items()))
        local_player = find_player_by_identity_hint(self.state.current_players, self.state.detected_player_name)
        name = ""
        if isinstance(local_player, dict):
            name = player_display_name_from_obj(local_player)
        if not name:
            name = str(self.state.detected_player_name or "").strip()
        return f"{self.state.selected_playlist}|server:{self.state.current_server_key}|team:{self.state.my_team}|scores:{scores}|player:{name}"

    def _is_recent_result_counted_locked(self, signature: str, max_age: int = 180) -> bool:
        now = time.time()
        fresh = []
        found = False
        for item in self.state.recent_counted_results:
            try:
                age = now - float(item.get("time", 0))
            except Exception:
                age = max_age + 1
            if age <= max_age:
                fresh.append(item)
                if signature and item.get("signature") == signature:
                    found = True
        self.state.recent_counted_results = fresh[-20:]
        return found

    def _mark_current_match_counted_locked(self) -> None:
        self.state.match_counted = True
        key = self.state.current_match_key or self.state.match_id
        if key:
            self.state.last_closed_match_key = key
            self.state.last_closed_match_at = time.time()
        signature = self._current_result_signature_locked()
        self.state.recent_counted_results.append({"signature": signature, "time": time.time(), "key": key})
        self.state.recent_counted_results = self.state.recent_counted_results[-20:]

    def _mark_matchended_waiting_destroy_locked(self) -> None:
        """Conserve le contexte de la partie après MatchEnded jusqu'au vrai MatchDestroyed.

        Cela évite qu'un UpdateState post-game change automatiquement la playlist alors
        qu'on est toujours dans la même partie. Le changement auto de playlist est
        appliqué uniquement après MatchDestroyed.
        """
        self.state.current_match_waiting_destroy = True
        self.state.match_active = True

    def _handle_match_ended(self, inner: Dict[str, Any]) -> None:
        winner = extract_winner_team_from_payload(inner)
        with self.lock:
            private_match = bool(self.state.current_match_private)
            ranked_match = bool(self.state.current_match_ranked or self.state.current_match_had_ranked_context)
            no_stats_match = bool(
                (self.state.current_match_no_stats or self.state.training_active or self.state.current_match_private)
                and not self.state.current_match_had_ranked_context
            )
            no_stats_reason = self.state.current_match_no_stats_reason or self.state.ignored_context or "match privé/freeplay"
            opponent_seen = bool(self.state.current_match_had_opponent)
            ranked_seen = bool(self.state.current_match_had_ranked_context or self.state.current_match_ranked)
            # Un match privé est no-stats pour l'overlay principal, mais reste valide pour le Showmatch.
            if no_stats_match and not private_match:
                self._log(f"MatchEnded ignoré : {no_stats_reason}")
                self._clear_match_live_state()
                return
            if not opponent_seen:
                self._log("MatchEnded ignoré : joueur seul détecté sans team adverse → Freeplay")
                self._clear_match_live_state()
                return
            if not ranked_match and not private_match:
                self._log("MatchEnded ignoré : contexte non-ranked")
                return
            if ranked_match and not private_match and not self._ensure_result_playlist_locked("MatchEnded"):
                self._clear_match_live_state()
                return
            signature = self._current_result_signature_locked()
            if self.state.match_counted or self._is_recent_result_counted_locked(signature):
                self._log("MatchEnded ignoré : cette partie est déjà comptabilisée")
                return
            my_team = self.state.my_team
            scores = dict(self.state.team_scores)
            if winner is None:
                winner = self.state.current_match_api_winner
        if my_team not in (0, 1):
            # En Showmatch privé, l'application peut être spectatrice : il n'existe
            # alors pas de team locale, mais la team gagnante reste comptable.
            if private_match:
                try:
                    with self.lock:
                        winner_team = self._winner_team_from_scores_or_api_locked(winner)
                        if winner_team is None:
                            self._log("MatchEnded privé ignoré : winner/score introuvable pour le Showmatch")
                            return
                        if self.state.match_counted or self._is_recent_result_counted_locked(signature):
                            self._log("MatchEnded privé ignoré : cette partie est déjà comptabilisée")
                            return
                        self._mark_current_match_counted_locked()
                        updated = self._sync_showmatch_from_winner_team_locked(winner_team, "private_matchended_team")
                    if updated:
                        self._publish_state()
                    self._log(f"MatchEnded privé Showmatch → team {winner_team} gagnante comptabilisée")
                    self._clear_match_live_state()
                    self._publish_state(count_revision=False)
                except Exception as exc:
                    self._log(f"MatchEnded privé Showmatch ignoré : {exc}")
            return
        try:
            my_score = int(scores.get(my_team, 0))
            opp_score = int(scores.get(1 - my_team, 0))
            validated: Optional[int] = None
            reason = "score"

            # Priorité demandée :
            # 1) résultat/winner officiel renvoyé par l'API de fin de match ;
            # 2) score si l'API ne donne rien ;
            # 3) si score égalité, on retente l'API de fin de match.
            if winner is not None:
                validated = int(winner)
                reason = "api-fin-match"
            elif my_score > opp_score:
                validated = my_team
                reason = "score"
            elif opp_score > my_score:
                validated = 1 - my_team
                reason = "score"
            elif winner is not None:
                validated = int(winner)
                reason = "api-égalité"
            if validated is None:
                self._log("MatchEnded ignoré : score égal et winner API absent")
                return
            result = "win" if validated == my_team else "loss"
            with self.lock:
                if self.state.match_counted or self._is_recent_result_counted_locked(signature):
                    self._log("MatchEnded ignoré : doublon détecté avant ajout")
                    return
                self._mark_current_match_counted_locked()
            with self.lock:
                private_match = bool(self.state.current_match_private)
                is_1v1 = self.state.selected_playlist == "1v1"
            if private_match:
                # Partie privée : ne pas modifier les statistiques de l'overlay principal.
                # Le Showmatch prend le point depuis la team gagnante, pas depuis un
                # win/loss local, pour fonctionner aussi en spectateur/observer.
                with self.lock:
                    updated = self._sync_showmatch_from_winner_team_locked(validated, "private_matchended")
                if updated:
                    self._publish_state()
                self._log(f"MatchEnded privé → aucune stat overlay principal · team {validated} gagnante validée par {reason} ({my_score}-{opp_score})")
            else:
                self.add_result(result, auto=True)
                self._log(f"MatchEnded → {result.upper()} validé par {reason} ({my_score}-{opp_score})")
            with self.lock:
                self._mark_matchended_waiting_destroy_locked()
            self._publish_state(count_revision=False)
        except Exception as exc:
            self._log(f"MatchEnded ignoré : {exc}")


    def _auto_detect_playlist_and_mmr(self, outer: Dict[str, Any], inner: Any) -> None:
        event = str(outer.get("Event", ""))
        with self.lock:
            ranked_mode_locked = bool(
                event not in ("MatchEnded", "MatchDestroyed")
                and (self.state.match_active or self.state.current_match_had_ranked_context or self.state.current_match_ranked)
                and (self.state.current_match_ranked or self.state.current_match_had_ranked_context)
                and not self.state.current_match_private
                and not self.state.current_match_no_stats
                and not self.state.training_active
            )
        if ranked_mode_locked:
            return
        players = extract_players_collection(outer, inner)
        api_playlist = extract_playlist_from_payload(outer, inner)
        inferred_playlist = self._infer_playlist_from_players(players)
        detected_playlist = resolve_playlist_from_game_and_players(
            api_playlist,
            inferred_playlist,
            players_available=bool(players),
        )
        competitive_reason = detect_competitive_context(outer, inner)
        if event not in ("MatchEnded", "MatchDestroyed") and detected_playlist and competitive_reason and self.config.get("auto_detect_playlist", True):
            with self.lock:
                if self.state.current_match_ranked and not self.state.current_match_no_stats:
                    self._consider_match_playlist_lock_locked(detected_playlist, event, "détecté par API ranked", inner if isinstance(inner, dict) else {})
        if self.config.get("auto_detect_mmr_api", True):
            mmr = extract_mmr_from_payload(outer, inner)
            if mmr is not None:
                with self.lock:
                    # Sur MatchEnded / MatchDestroyed, on ne laisse pas le MMR provoquer
                    # un changement de playlist avant le nettoyage officiel de la partie.
                    # La playlist auto sera appliquée après MatchDestroyed uniquement.
                    if event in ("MatchEnded", "MatchDestroyed"):
                        playlist = self.state.current_match_locked_playlist if self.state.current_match_playlist_locked else ""
                    else:
                        playlist = detected_playlist
                if playlist in PLAYLIST_NAMES:
                    self.set_mmr(playlist, mmr, auto=True)

    def _infer_playlist_from_players(self, players: Any) -> Optional[str]:
        """Déduit la playlist uniquement avec les joueurs réellement présents.

        La déduction est volontairement stricte : il faut voir les deux teams et
        le même nombre de joueurs de chaque côté. Une liste partielle ne doit pas
        transformer une 1v1 en 3v3 pendant le chargement ou la fin de match.
        """
        normalized = normalize_players_collection(players)
        if not normalized:
            return None
        teams: Dict[int, int] = {}
        for p in normalized:
            team_num = None
            for key in ("TeamNum", "team_num", "Team", "team", "TeamIndex", "teamIndex"):
                if key in p:
                    team_num = parse_team_num_value(p.get(key))
                    if team_num is not None:
                        break
            if team_num not in (0, 1):
                continue
            teams[int(team_num)] = teams.get(int(team_num), 0) + 1

        if set(teams.keys()) != {0, 1}:
            return None
        if teams[0] != teams[1]:
            return None
        return {1: "1v1", 2: "2v2", 3: "3v3"}.get(teams[0])

    def _handle_match_destroyed_by_score(self) -> None:
        result: Optional[str] = None
        detail = ""
        private_winner_team: Optional[int] = None
        with self.lock:
            private_match = bool(self.state.current_match_private)
            ranked_match = bool(self.state.current_match_ranked or self.state.current_match_had_ranked_context)
            no_stats_match = bool(
                (self.state.current_match_no_stats or self.state.training_active or self.state.current_match_private)
                and not self.state.current_match_had_ranked_context
            )
            no_stats_reason = self.state.current_match_no_stats_reason or self.state.ignored_context or "match privé/freeplay"
            opponent_seen = bool(self.state.current_match_had_opponent)
            ranked_seen = bool(self.state.current_match_had_ranked_context or self.state.current_match_ranked)
            # Un match privé reste ignoré pour les stats principales, mais peut compter le Showmatch.
            if no_stats_match and not private_match:
                self._log(f"MatchDestroyed ignoré : {no_stats_reason}")
                self._clear_match_live_state()
                return
            if not opponent_seen:
                self._log("MatchDestroyed ignoré : joueur seul détecté sans team adverse → Freeplay")
                self._clear_match_live_state()
                return
            if not ranked_match and not private_match:
                self._log("MatchDestroyed ignoré : contexte non-ranked")
                self._clear_match_live_state()
                return
            if ranked_match and not private_match and not self._ensure_result_playlist_locked("MatchDestroyed"):
                self._clear_match_live_state()
                return
            my_team = self.state.my_team
            scores = dict(self.state.team_scores)
            signature = self._current_result_signature_locked()

            if private_match and my_team not in (0, 1):
                # Cas Showmatch spectateur : pas de win/loss local, mais on peut compter
                # gauche/droite depuis la team gagnante API ou le score final.
                if self.state.match_counted or self._is_recent_result_counted_locked(signature):
                    self._log("MatchDestroyed privé ignoré : cette partie est déjà comptabilisée")
                else:
                    winner_team = self._winner_team_from_scores_or_api_locked()
                    if winner_team is not None:
                        private_winner_team = int(winner_team)
                        self._mark_current_match_counted_locked()
                        detail = f"team {private_winner_team} · score {int(scores.get(0, 0))}-{int(scores.get(1, 0))}"
                    else:
                        self._log("MatchDestroyed privé ignoré : winner/score introuvable pour le Showmatch")
            else:
                should_count = (
                    self.state.match_active
                    and not self.state.match_counted
                    and my_team in (0, 1)
                    and not self._is_recent_result_counted_locked(signature)
                )
                if should_count:
                    my_score = int(scores.get(my_team, 0))
                    opp_score = int(scores.get(1 - my_team, 0))
                    # Early leave / abandon : priorité à l'API de fin de match si elle existe, puis au score.
                    if self.state.current_match_api_winner is not None:
                        result = "win" if int(self.state.current_match_api_winner) == int(my_team) else "loss"
                        detail = f"{my_score}-{opp_score} · API fin match team {self.state.current_match_api_winner}"
                    elif my_score > opp_score:
                        result = "win"
                        detail = f"{my_score}-{opp_score} · score"
                    elif opp_score > my_score:
                        result = "loss"
                        detail = f"{my_score}-{opp_score} · score"
                    if result:
                        self._mark_current_match_counted_locked()
                else:
                    if self.state.match_counted or self._is_recent_result_counted_locked(signature):
                        self._log("MatchDestroyed ignoré : cette partie est déjà comptabilisée")

        if private_winner_team is not None:
            with self.lock:
                updated = self._sync_showmatch_from_winner_team_locked(private_winner_team, "private_matchdestroyed_team")
            if updated:
                self._publish_state()
            self._log(f"MatchDestroyed privé Showmatch → {detail} comptabilisée")
            self._clear_match_live_state()
            self._publish_state(count_revision=False)
            return

        if result:
            with self.lock:
                private_match = bool(self.state.current_match_private)
            if private_match:
                # Partie privée : aucune stat sur l'overlay principal.
                with self.lock:
                    winner_team = self._winner_team_from_scores_or_api_locked(self.state.current_match_api_winner)
                    if winner_team is None:
                        winner_team = self.state.my_team if result == "win" else 1 - int(self.state.my_team)
                    updated = self._sync_showmatch_from_winner_team_locked(winner_team, "private_matchdestroyed")
                if updated:
                    self._publish_state()
                self._log(f"MatchDestroyed privé early leave → aucune stat overlay principal · team {winner_team} gagnante validée ({detail})")
            else:
                self.add_result(result, auto=True)
                self._log(f"MatchDestroyed early leave → {result.upper()} validé par score puis API si égalité ({detail})")
        self._clear_match_live_state()
        self._publish_state(count_revision=False)

    def _clear_match_live_state(self) -> None:
        with self.lock:
            self.state.my_team = None
            self.state.team_scores = {}
            self.state.last_scores = {}
            self.state.current_players = []
            self.state.match_active = False
            self.state.current_match_ranked = False
            self.state.current_match_private = False
            self.state.current_match_no_stats = False
            self.state.current_match_no_stats_reason = ""
            self.state.current_match_platform = "auto"
            self.state.current_match_has_timer = False
            self.state.current_match_had_opponent = False
            self.state.current_match_had_ranked_context = False
            self.state.current_match_api_winner = None
            self.state.current_match_end_reason = ""
            self.state.current_match_waiting_destroy = False
            self._reset_match_playlist_lock_locked()
            self.state.current_match_key = ""
            self.state.last_server_key = self.state.current_server_key
            self.state.current_server_key = ""

    # ──────────────────────────────────────────────────────────────────────
    # API RLS lookup
    # ──────────────────────────────────────────────────────────────────────

    def _normalize_tracker_platform(self, platform: str) -> str:
        platform = str(platform or "auto").strip().lower()
        platform = platform.replace("onlineplatform_", "").replace("platform_", "").replace(" ", "")
        if platform in {"automatic", "detect", "auto-detect", "autodetect", "auto"}:
            return "auto"
        if platform in {"steam", "steamworks"}:
            return "steam"
        if platform in {"epic", "epicgames", "eos", "egs"}:
            return "epic"
        if platform in {"xbox", "xbl", "xboxlive", "live"}:
            return "xbl"
        if platform in {"ps", "psn", "playstation", "playstationnetwork", "ps4", "ps5"}:
            return "psn"
        if platform in {"switch", "nintendo", "nintendoswitch"}:
            return "switch"
        if platform in {"steam", "epic", "xbl", "psn", "switch"}:
            return platform
        return "auto"

    def _iter_tracker_values(self, obj: Any, parent_key: str = ""):
        if isinstance(obj, dict):
            for key, value in obj.items():
                k = f"{parent_key}.{key}" if parent_key else str(key)
                yield k, value
                yield from self._iter_tracker_values(value, k)
        elif isinstance(obj, list):
            for idx, value in enumerate(obj):
                yield f"{parent_key}[{idx}]", value
                yield from self._iter_tracker_values(value, parent_key)

    def _normalize_rls_saved_endpoint_locked(self, platform: str, primary_id: str) -> Tuple[str, str, str]:
        """Retourne platform/id/endpoint propres pour l'API RLS."""
        platform = self._normalize_tracker_platform(platform).lower()
        parsed_platform, clean_primary_id = split_rls_platform_and_primary_id(primary_id, platform)
        platform = self._normalize_tracker_platform(parsed_platform or platform).lower()

        clean_primary_id = str(clean_primary_id or "").strip()
        if not clean_primary_id:
            return "", "", ""

        if platform == "auto":
            platform = "steam" if re.fullmatch(r"\d{15,20}", clean_primary_id) else "epic"

        endpoint = f"/{platform}/{clean_primary_id}"
        return platform, clean_primary_id, endpoint

    def _has_saved_rls_primary_identity_locked(self) -> bool:
        """Bloque toute nouvelle récupération si /{platform}/{id} est déjà sauvegardé."""
        saved_platform, saved_primary_id = self._get_saved_rls_primary_identity_locked()
        return bool(saved_platform and saved_primary_id)

    def _store_rls_primary_identity_locked(self, platform: str, primary_id: str, source: str = "") -> bool:
        """Sauvegarde définitivement /{platform}/{id} une seule fois.

        Dès que l'endpoint est sauvegardé une première fois, l'application ne
        refait plus de récupération depuis le JSON pour cette identité RLS.
        """
        platform, clean_primary_id, endpoint = self._normalize_rls_saved_endpoint_locked(platform, primary_id)
        if not clean_primary_id:
            return False

        # Si un endpoint est déjà sauvegardé, on bloque la récupération.
        # On ne remplace pas l'ancien joueur par une nouvelle valeur trouvée plus tard.
        existing_platform = str(self.config.data.get("rls_saved_platform", "") or "").lower()
        existing_primary_id = str(self.config.data.get("rls_saved_primary_id", "") or "").strip()
        existing_endpoint = str(self.config.data.get("rls_saved_endpoint", "") or "").strip()

        if existing_primary_id:
            if not existing_endpoint:
                self.config.data["rls_saved_endpoint"] = f"/{existing_platform or platform}/{existing_primary_id}"
                self.config.save()
            return False

        self.config.data["rls_saved_platform"] = platform
        self.config.data["rls_saved_primary_id"] = clean_primary_id
        self.config.data["rls_saved_endpoint"] = endpoint
        self.config.save()

        try:
            suffix = f" · {source}" if source else ""
            self._log(f"API RLS : endpoint sauvegardé définitivement · {endpoint}{suffix}")
        except Exception:
            pass

        return True

    def _get_saved_rls_primary_identity_locked(self) -> Tuple[str, str]:
        """Retourne la plateforme + PrimaryId sauvegardés dans %AppData%."""
        saved_platform = self._normalize_tracker_platform(
            str(self.config.get("rls_saved_platform", "") or "auto")
        ).lower()
        saved_primary_id = str(self.config.get("rls_saved_primary_id", "") or "").strip()
        saved_endpoint = str(self.config.get("rls_saved_endpoint", "") or "").strip()

        # Compatibilité : si seul /{platform}/{id} existe, on le relit.
        if saved_endpoint and not saved_primary_id:
            parts = [p for p in saved_endpoint.strip().split("/") if p]
            if len(parts) >= 2:
                saved_platform = self._normalize_tracker_platform(parts[0]).lower()
                saved_primary_id = parts[1].strip()

        if not saved_primary_id:
            return "", ""

        parsed_platform, clean_primary_id = split_rls_platform_and_primary_id(
            saved_primary_id,
            saved_platform
        )
        saved_platform = self._normalize_tracker_platform(parsed_platform or saved_platform).lower()
        clean_primary_id = str(clean_primary_id or "").strip()

        if not clean_primary_id:
            return "", ""

        if saved_platform == "auto":
            saved_platform = "steam" if re.fullmatch(r"\d{15,20}", clean_primary_id) else "epic"

        # Garde le JSON cohérent après migration ou nettoyage.
        clean_endpoint = f"/{saved_platform}/{clean_primary_id}"
        if (
            str(self.config.data.get("rls_saved_platform", "") or "").lower() != saved_platform
            or str(self.config.data.get("rls_saved_primary_id", "") or "").strip() != clean_primary_id
            or str(self.config.data.get("rls_saved_endpoint", "") or "").strip() != clean_endpoint
        ):
            self.config.data["rls_saved_platform"] = saved_platform
            self.config.data["rls_saved_primary_id"] = clean_primary_id
            self.config.data["rls_saved_endpoint"] = clean_endpoint
            self.config.save()

        return saved_platform, clean_primary_id

    def _try_save_rls_identity_from_payload_locked(self, inner: Dict[str, Any], source: str = "") -> bool:
        """Récupère /{platform}/{id} depuis Freeplay ou playlist verrouillée, une seule fois."""
        if self._has_saved_rls_primary_identity_locked():
            return False

        payloads: List[Any] = []

        primary_player = extract_primary_player_from_payload(inner)
        if primary_player:
            payloads.append(primary_player)

        players = extract_players_collection(inner)
        if players:
            current_hint = str(self.state.detected_player_name or "").strip()
            if current_hint:
                player_from_hint = find_player_by_identity_hint(players, current_hint)
                if player_from_hint:
                    payloads.append(player_from_hint)

            local_candidate, _reason = extract_local_player_candidate_from_payload(
                inner,
                current_player_name=current_hint,
                forced_player_hint="",
            )
            if local_candidate:
                payloads.append(local_candidate)

        # Supprime les doublons d'objets tout en gardant l'ordre.
        unique_payloads: List[Any] = []
        seen_ids = set()
        for payload in payloads:
            marker = id(payload)
            if marker in seen_ids:
                continue
            seen_ids.add(marker)
            unique_payloads.append(payload)

        for payload in unique_payloads:
            if not isinstance(payload, dict):
                continue
            primary_id = extract_primary_id_from_player_obj(payload)
            if not primary_id:
                continue

            platform = tracker_platform_from_primary_id(payload, primary_id, "auto")
            platform = self._normalize_tracker_platform(platform).lower()
            if platform == "auto":
                platform = "steam" if re.fullmatch(r"\d{15,20}", primary_id) else "epic"

            return self._store_rls_primary_identity_locked(platform, primary_id, source)

        return False

    def _detect_tracker_identity_locked(self) -> Tuple[str, str, str]:
        """Détecte l'identité à envoyer à l'API RLS.

        Règle Beta 2.5 :
        - si aucun pseudo/ID manuel n'est renseigné, l'appel automatique RLS
          doit utiliser uniquement le PrimaryId du joueur local trouvé dans le
          JSON reçu ;
        - la plateforme est déduite du JSON/PrimaryId, Epic comme Steam ;
        - le pseudo Player/Name n'est plus utilisé comme fallback automatique.
        """
        forced_player = str(self.config.get("tracker_force_player", "") or "").strip()
        configured = self._normalize_tracker_platform(
            str(self.config.get("tracker_platform", "auto") or "auto")
        )
        manual_identity = bool(forced_player)

        # Si /{platform}/{id} est déjà sauvegardé, on bloque toute nouvelle
        # récupération depuis le JSON et on réutilise toujours cette identité.
        saved_platform, saved_primary_id = self._get_saved_rls_primary_identity_locked()
        if saved_primary_id:
            return saved_platform, saved_primary_id, "Endpoint RLS sauvegardé"

        platform_hint = ""
        steam_id = ""
        epic_id = ""
        epic_hint = False
        psn_hint = False
        xbl_hint = False
        switch_hint = False

        payloads: List[Any] = []

        # L'identité API RLS doit suivre le même principe que l'overlay principal :
        # seul le joueur local/principal est utilisé, jamais les teammates/adversaires.
        if self.state.current_players:
            primary_current = None

            # En auto pur, on évite le pseudo Player/Name comme source RLS.
            # On garde seulement le joueur déjà verrouillé pour retrouver son objet JSON,
            # puis on extrait uniquement PrimaryId.
            if self.state.detected_player_name:
                primary_current = find_player_by_identity_hint(
                    self.state.current_players,
                    self.state.detected_player_name
                )

            # Si un champ manuel est renseigné, il peut seulement aider à retrouver
            # l'objet du joueur dans le JSON, mais l'appel RLS utilisera PrimaryId si présent.
            if not primary_current and manual_identity:
                primary_current = find_player_by_identity_hint(
                    self.state.current_players,
                    forced_player
                )

            if not primary_current:
                primary_current, _reason = extract_local_player_candidate_from_payload(
                    {"Players": self.state.current_players},
                    current_player_name=self.state.detected_player_name,
                    forced_player_hint=forced_player if manual_identity else "",
                )

            if primary_current:
                payloads.append(primary_current)

        if self.state.last_raw_event:
            primary_from_event, _reason = extract_local_player_candidate_from_payload(
                self.state.last_raw_event,
                current_player_name=self.state.detected_player_name,
                forced_player_hint=forced_player if manual_identity else "",
            )
            if primary_from_event:
                payloads.append(primary_from_event)

        # Priorité absolue pour l'appel automatique : plateforme + PrimaryId du JSON local.
        # L'id est toujours nettoyé pour éviter de dupliquer la plateforme dans l'URL.
        for payload in payloads:
            primary_id = extract_primary_id_from_player_obj(payload)
            if primary_id:
                primary_platform = tracker_platform_from_primary_id(
                    payload,
                    primary_id,
                    configured if manual_identity else "auto"
                )
                primary_platform = self._normalize_tracker_platform(primary_platform).lower()
                if primary_platform == "auto":
                    primary_platform = "steam" if re.fullmatch(r"\d{15,20}", primary_id) else "epic"
                self._store_rls_primary_identity_locked(primary_platform, primary_id, "PrimaryId JSON automatique")
                return primary_platform, primary_id, "PrimaryId JSON automatique"

        # Si aucun champ manuel n'est renseigné, on ne doit plus appeler l'API RLS
        # avec un pseudo Player/Name. On attend un PrimaryId valide dans le JSON
        # ou un PrimaryId déjà sauvegardé.
        if not manual_identity:
            return "", "", "PrimaryId JSON introuvable"

        # À partir d'ici uniquement : fallback manuel explicite.
        # On conserve la recherche historique pour les utilisateurs qui veulent forcer
        # un ID/pseudo dans les réglages.
        fallback_name = forced_player or str(self.state.detected_player_name or "").strip()

        for payload in payloads:
            for key, value in self._iter_tracker_values(payload):
                key_l = str(key).lower()
                value_s = str(value or "").strip()
                value_l = value_s.lower()
                normalized_value_platform = self._normalize_tracker_platform(value_s)

                steam_match = re.search(r"7656\d{13}", value_s)
                if steam_match:
                    steam_id = steam_match.group(0)
                    platform_hint = "steam"

                if normalized_value_platform in {"steam", "epic", "xbl", "psn", "switch"}:
                    platform_hint = normalized_value_platform

                if "steam" in key_l or "steam" in value_l:
                    platform_hint = "steam"
                    if re.fullmatch(r"\d{15,20}", value_s):
                        steam_id = value_s

                if any(token in key_l for token in ("epic", "eos", "epicaccount", "epic_account")) or "epic" in value_l:
                    epic_hint = True
                    if re.fullmatch(r"[0-9a-fA-F]{16,40}", value_s):
                        epic_id = value_s

                if any(token in key_l for token in ("xbox", "xbl", "liveid")) or "xbox" in value_l:
                    xbl_hint = True

                if any(token in key_l for token in ("psn", "playstation", "sony")) or "playstation" in value_l or value_l == "psn":
                    psn_hint = True

                if any(token in key_l for token in ("switch", "nintendo")) or "nintendo" in value_l or value_l == "switch":
                    switch_hint = True

        if configured != "auto" and fallback_name:
            return configured, fallback_name, "manuel forcé"

        if steam_id:
            return "steam", steam_id, "auto SteamID"
        if platform_hint == "steam" and fallback_name:
            return "steam", steam_id or fallback_name, "auto Steam"
        if platform_hint == "epic" and fallback_name:
            return "epic", epic_id or fallback_name, "auto Epic"
        if platform_hint == "xbl" and fallback_name:
            return "xbl", fallback_name, "auto Xbox"
        if platform_hint == "psn" and fallback_name:
            return "psn", fallback_name, "auto PlayStation"
        if platform_hint == "switch" and fallback_name:
            return "switch", fallback_name, "auto Nintendo Switch"
        if epic_hint and fallback_name:
            return "epic", epic_id or fallback_name, "auto Epic"
        if xbl_hint and fallback_name:
            return "xbl", fallback_name, "auto Xbox"
        if psn_hint and fallback_name:
            return "psn", fallback_name, "auto PlayStation"
        if switch_hint and fallback_name:
            return "switch", fallback_name, "auto Nintendo Switch"

        return "", "", "identité RLS introuvable"


    def _maybe_refresh_tracker_rank(self, force: bool = False, reason: str = "") -> None:
        def dbg(msg: str) -> None:
            try:
                self._log(msg)
            except Exception:
                pass

        def set_status(msg: str) -> None:
            with self.lock:
                self.state.tracker_status = msg
                self.state.tracker_last_at = time.strftime("%H:%M:%S")
            try:
                self._publish_state(count_revision=False)
            except Exception:
                pass

        try:
            reason_l = (reason or "").lower()
            final_event_refresh = any(k in reason_l for k in ("match-ended", "matchended", "match-destroyed", "matchdestroyed"))
            if not force and not final_event_refresh:
                return

            configured_platform = self._normalize_tracker_platform(str(self.config.get("tracker_platform", "auto") or "auto"))
            forced_player = str(self.config.get("tracker_force_player", "") or "").strip()

            with self.lock:
                playlist = self.state.selected_playlist
                training = bool(self.state.training_active)
                ignored = bool(self.state.ignored_context)

            if not force and (training or ignored):
                return

            with self.lock:
                auto_platform, auto_player, auto_note = self._detect_tracker_identity_locked()

            # Même en rafraîchissement manuel, le PrimaryId détecté dans le JSON
            # reste prioritaire sur le pseudo/ID saisi dans API RLS.
            if force and forced_player and "PrimaryId" not in str(auto_note):
                player = forced_player
                platform = configured_platform if configured_platform != "auto" else "auto"
                detection_note = "manuel forcé"
            else:
                platform, player, detection_note = auto_platform, auto_player, auto_note

            if playlist not in PLAYLIST_NAMES:
                msg = f"API RLS : playlist {playlist or 'inconnue'} non supportée"
                set_status(msg); dbg(msg)
                return
            if not player:
                msg = "API RLS : PrimaryId introuvable dans le JSON et aucune sauvegarde locale · renseigne un ID manuel si besoin"
                set_status(msg); dbg(msg)
                return

            platform = self._normalize_tracker_platform(platform).lower()
            if platform == "auto":
                platform = "steam" if re.fullmatch(r"\d{15,20}", player) else "epic"

            # Sécurité anti-doublon : si l'id contient encore une plateforme,
            # on la retire de l'id et on garde seulement /player/{platform}/{id}.
            parsed_platform, clean_player = split_rls_platform_and_primary_id(player, platform)
            platform = self._normalize_tracker_platform(parsed_platform or platform).lower()
            player = clean_player or player

            now = time.time()
            key = f"{platform}:{player}:{playlist}"
            if self._tracker_busy:
                msg = "API RLS : une requête est déjà en cours"
                set_status(msg); dbg(msg)
                return
            if force and key == self._last_tracker_key and now - self._last_tracker_fetch < 3:
                msg = "API RLS : dernière requête < 3s · patiente"
                set_status(msg); dbg(msg)
                return

            self._tracker_busy = True
            self._last_tracker_key = key
            self._last_tracker_fetch = now
            platform_label = platform.lower()
            msg = f"API RLS : appel {platform_label}/{player} · {playlist}"
            set_status(msg); dbg(msg)

            threading.Thread(
                target=self._tracker_worker,
                args=(platform, player, playlist, reason or detection_note),
                daemon=True,
                name="RLSAPILookup",
            ).start()
        except Exception as exc:
            self._tracker_busy = False
            err = f"API RLS non lancé : {exc}"
            try:
                set_status(err)
            except Exception:
                pass
            dbg(err)
            traceback.print_exc()

    def _rls_api_endpoints(self) -> Tuple[str, str]:
        api_base = str(self.config.get("rls_api_base", RLS_API_BASE) or RLS_API_BASE).strip().rstrip("/")
        api_key = str(self.config.get("rls_api_key", RLS_API_KEY) or RLS_API_KEY).strip()
        return api_base, api_key

    def _fetch_rls_player(self, platform: str, player_id: str) -> Tuple[Optional[Dict[str, Any]], str]:
        """Appelle l'API RLS avec /player/{platform}/{id}.

        La plateforme est forcée en minuscule et l'id est nettoyé pour éviter
        les doublons de plateforme dans l'URL.
        """
        api_base, api_key = self._rls_api_endpoints()
        if not api_base:
            return None, "API base URL manquante"
        if not api_key:
            return None, "API key manquante"

        platform = self._normalize_tracker_platform(platform).lower()
        if platform == "auto":
            platform = "steam" if re.fullmatch(r"\d{15,20}", str(player_id or "").strip()) else "epic"

        parsed_platform, clean_player_id = split_rls_platform_and_primary_id(player_id, platform)
        platform = self._normalize_tracker_platform(parsed_platform or platform).lower()
        player_id = clean_player_id or str(player_id or "").strip()

        encoded_platform = urllib.parse.quote(platform, safe="")
        encoded = urllib.parse.quote(str(player_id or "").strip(), safe="")
        if not encoded:
            return None, "identifiant joueur vide"

        url = f"{api_base}/player/{encoded_platform}/{encoded}?skills=10,11,13"
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "X-API-Key": api_key,
                    "Accept": "application/json",
                    "User-Agent": "rl_overlay_studio/1.0",
                },
            )
            with urllib.request.urlopen(req, timeout=12) as response:
                raw = response.read().decode("utf-8", errors="ignore")
        except urllib.error.HTTPError as exc:
            try:
                detail = exc.read().decode("utf-8", errors="ignore")[:200]
            except Exception:
                detail = ""
            return None, f"HTTP {exc.code}{(' · ' + detail) if detail else ''}"
        except urllib.error.URLError as exc:
            return None, f"connexion impossible : {exc.reason}"
        except Exception as exc:
            return None, str(exc)[:200]

        if not raw:
            return None, "réponse vide"
        try:
            data = json.loads(raw)
        except Exception as exc:
            return None, f"JSON invalide : {exc}"
        if not isinstance(data, dict):
            return None, "réponse JSON inattendue"
        return data, ""

    def _extract_all_rls_playlist_info(self, data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        """Extrait MMR + leaderboard rank pour chaque playlist 1v1/2v2/3v3 du payload RLS.

        Retourne un dict { "1v1": {"mmr": int|None, "leader_rank": str}, ... }.
        """
        results: Dict[str, Dict[str, Any]] = {
            playlist: {"mmr": None, "leader_rank": ""} for playlist in TRACKER_LEADERBOARD_PLAYLIST_IDS
        }
        if not isinstance(data, dict):
            return results

        root = data.get("data") if isinstance(data.get("data"), dict) else data
        ranks = root.get("ranks") if isinstance(root.get("ranks"), list) else []
        leaderboard = root.get("leaderboard") if isinstance(root.get("leaderboard"), dict) else {}

        ranks_by_pid: Dict[int, Dict[str, Any]] = {}
        for entry in ranks:
            if not isinstance(entry, dict):
                continue
            try:
                pid = int(entry.get("playlistId"))
            except Exception:
                continue
            ranks_by_pid[pid] = entry

        for playlist, pid in TRACKER_LEADERBOARD_PLAYLIST_IDS.items():
            entry = ranks_by_pid.get(int(pid))
            if isinstance(entry, dict):
                mmr_val = entry.get("mmr")
                if isinstance(mmr_val, (int, float)) and mmr_val > 0:
                    results[playlist]["mmr"] = int(mmr_val)

            lb_entry = leaderboard.get(str(pid)) or leaderboard.get(pid)
            if isinstance(lb_entry, dict):
                rank_val = lb_entry.get("rank")
                if isinstance(rank_val, (int, float)) and rank_val > 0:
                    results[playlist]["leader_rank"] = str(int(rank_val))

        return results

    def _tracker_worker(self, platform: str, player: str, playlist: str, reason: str = "") -> None:
        try:
            platform = self._normalize_tracker_platform(platform).lower()
            if platform == "auto":
                platform = "steam" if re.fullmatch(r"\d{15,20}", str(player or "").strip()) else "epic"

            parsed_platform, clean_player = split_rls_platform_and_primary_id(player, platform)
            platform = self._normalize_tracker_platform(parsed_platform or platform).lower()
            player = clean_player or player
            platform_label = platform.lower()

            reason_l = (reason or "").lower()
            post_match_delay = any(k in reason_l for k in ("match-ended", "matchended", "match-destroyed", "matchdestroyed"))
            if post_match_delay:
                with self.lock:
                    self.state.tracker_status = f"API RLS : attente 2s après fin de match · {platform_label} · {player} · {playlist}"
                    self.state.tracker_last_at = time.strftime("%H:%M:%S")
                self._publish_state(count_revision=False)
                time.sleep(2.0)

            with self.lock:
                self.state.tracker_status = f"API RLS : requête {platform_label} · {player} · {playlist}"
                self.state.tracker_last_at = time.strftime("%H:%M:%S")
            self._publish_state(count_revision=False)

            data, fetch_error = self._fetch_rls_player(platform, player)
            if data is None:
                status = f"API RLS : échec {platform_label} · {player} · {playlist} · {fetch_error or 'aucune donnée'}"
                with self.lock:
                    self.state.tracker_status = status
                    self.state.tracker_last_at = time.strftime("%H:%M:%S")
                self._publish_state(count_revision=False)
                self._log(status)
                return

            all_info = self._extract_all_rls_playlist_info(data)

            updated_parts: List[str] = []
            for pl, info in all_info.items():
                mmr_val = info.get("mmr")
                lb_val = str(info.get("leader_rank") or "")
                if mmr_val is not None:
                    self.set_mmr(pl, int(mmr_val), auto=True, leader_rank=lb_val)
                    part = f"{pl} MMR {int(mmr_val)}"
                    if lb_val:
                        part += f" Top {lb_val}"
                    updated_parts.append(part)
                else:
                    # Pas de MMR pour cette playlist : on efface au moins le leader_rank obsolète.
                    with self.lock:
                        slot = self.state.all_mmr.setdefault(pl, {
                            "mmr": None, "mmr_start": None, "mmr_change": 0,
                            "rank": "", "rank_short": "", "rank_asset": "", "leader_rank": "",
                        })
                        slot["leader_rank"] = lb_val

            if updated_parts:
                status = f"API RLS : {platform_label} · {player} · " + " · ".join(updated_parts)
            else:
                status = f"API RLS : aucun MMR retourné pour {platform_label} · {player}"

            with self.lock:
                self.state.tracker_status = status
                self.state.tracker_last_at = time.strftime("%H:%M:%S")
            self._publish_state(count_revision=False)
            self._log(status)
        except Exception as exc:
            err = f"API RLS : erreur · {str(exc)[:160]}"
            with self.lock:
                self.state.tracker_status = err
                self.state.tracker_last_at = time.strftime("%H:%M:%S")
            self._publish_state(count_revision=False)
            self._log(err)
        finally:
            self._tracker_busy = False


    # ──────────────────────────────────────────────────────────────────────
    # Actions
    # ──────────────────────────────────────────────────────────────────────

    def _load_showmatch_config_into_state(self) -> None:
        sm = self.config.get("showmatch", {}) or {}
        try:
            self.state.showmatch_enabled = bool(sm.get("enabled", False))
            self.state.showmatch_bo = int(sm.get("bo", 5)) if int(sm.get("bo", 5)) in (3, 5, 7, 9) else 5
            self.state.showmatch_left_name = str(sm.get("left_name", "Player") or "Player")
            self.state.showmatch_right_name = str(sm.get("right_name", "Opponent") or "Opponent")
            self.state.showmatch_left_score = int(sm.get("left_score", 0))
            self.state.showmatch_right_score = int(sm.get("right_score", 0))
            self.state.showmatch_current_game = int(sm.get("current_game", max(1, min(self.state.showmatch_left_score + self.state.showmatch_right_score + 1, self.state.showmatch_bo))))
            try:
                self.state.showmatch_left_team = int(sm.get("left_team")) if sm.get("left_team") is not None else self.state.showmatch_left_team
            except Exception:
                pass
            try:
                self.state.showmatch_right_team = int(sm.get("right_team")) if sm.get("right_team") is not None else self.state.showmatch_right_team
            except Exception:
                pass
            self.state.showmatch_last_winner = str(sm.get("last_winner", "") or "")
            history = sm.get("history", [])
            self.state.showmatch_history = history if isinstance(history, list) else []
        except Exception:
            self.state.showmatch_bo = 5
            self.state.showmatch_current_game = 1

    def _save_showmatch_config_locked(self) -> None:
        self.config.data["showmatch"] = {
            "enabled": bool(self.state.showmatch_enabled),
            "bo": int(self.state.showmatch_bo),
            "left_name": self.state.showmatch_left_name,
            "right_name": self.state.showmatch_right_name,
            "left_score": int(self.state.showmatch_left_score),
            "right_score": int(self.state.showmatch_right_score),
            "current_game": int(self.state.showmatch_current_game or 1),
            "left_team": self.state.showmatch_left_team,
            "right_team": self.state.showmatch_right_team,
            "last_winner": self.state.showmatch_last_winner,
            "history": self.state.showmatch_history[-30:],
        }
        self.config.save()

    def set_overlay_exclusive_mode(self, enabled: bool) -> None:
        enabled = bool(enabled)
        with self.lock:
            self.config.data["overlay_exclusive_mode"] = enabled
            # Si l'utilisateur réactive le mode exclusif alors que les deux overlays
            # sont déjà visibles, on garde le Win/Lose prioritaire et on masque
            # simplement le Showmatch sans perdre ses scores/BO en cours.
            auto_hidden = False
            if enabled and bool(self.state.main_overlay_enabled) and bool(self.state.showmatch_enabled):
                self.state.showmatch_enabled = False
                self._save_showmatch_config_locked()
                auto_hidden = True
            self.config.save()
        if auto_hidden:
            self._log("Mode exclusif activé : Overlay Showmatch masqué automatiquement")
        else:
            self._log("Mode exclusif overlays activé" if enabled else "Mode exclusif overlays désactivé · les deux overlays peuvent être visibles")
        self._publish_state()

    def set_main_overlay_enabled(self, enabled: bool) -> None:
        enabled = bool(enabled)
        auto_hidden_showmatch = False
        with self.lock:
            previous = bool(getattr(self.state, "main_overlay_enabled", True))

            # Option exclusive : afficher Win/Lose masque le Showmatch, sans supprimer
            # les points BO déjà saisis. L'utilisateur peut désactiver cette option
            # dans le panneau Overlay pour afficher les deux overlays ensemble.
            if enabled and bool(self.config.get("overlay_exclusive_mode", True)) and bool(self.state.showmatch_enabled):
                self.state.showmatch_enabled = False
                self._save_showmatch_config_locked()
                auto_hidden_showmatch = True

            if previous == enabled and not auto_hidden_showmatch:
                return

            # L'activation/désactivation de l'overlay principal ne doit pas casser
            # la détection de fin de match. Quand il est masqué, les stats Win/Lose
            # principales sont figées, mais le Showmatch peut continuer à recevoir
            # les points si son overlay est visible.
            self.state.main_overlay_enabled = enabled
            self.config.data["main_overlay_enabled"] = enabled
            self.config.save()
            action = "affiché" if enabled else "masqué"

        suffix = "stats principales actives" if enabled else "stats principales figées · Showmatch encore comptable s'il est visible"
        if auto_hidden_showmatch:
            suffix += " · Showmatch masqué automatiquement"
        self._log(f"Overlay Win/Lose {action} · {suffix}")
        self._publish_state()


    def set_showmatch_enabled(self, enabled: bool) -> None:
        enabled = bool(enabled)
        auto_hidden_main = False
        with self.lock:
            previous = bool(self.state.showmatch_enabled)

            # Option exclusive : afficher Showmatch masque automatiquement le Win/Lose.
            # La désactivation de l'option dans le panneau Overlay permet d'afficher
            # les deux overlays en même temps.
            if enabled and bool(self.config.get("overlay_exclusive_mode", True)) and bool(self.state.main_overlay_enabled):
                self.state.main_overlay_enabled = False
                self.config.data["main_overlay_enabled"] = False
                auto_hidden_main = True

            if previous == enabled and not auto_hidden_main:
                return

            self.state.showmatch_enabled = enabled
            if not enabled:
                # Masquer le Showmatch manuellement réinitialise son BO immédiatement.
                self.state.showmatch_left_score = 0
                self.state.showmatch_right_score = 0
                self.state.showmatch_current_game = 1
                self.state.showmatch_last_winner = ""
                self.state.showmatch_last_main_result_key = ""
                self.state.showmatch_history = []
            else:
                self._ensure_showmatch_names_locked()
            self._save_showmatch_config_locked()
            if auto_hidden_main:
                self.config.save()
        if enabled:
            msg = "Overlay Showmatch activé"
            if auto_hidden_main:
                msg += " · Win/Lose masqué automatiquement"
        else:
            msg = "Overlay Showmatch désactivé · BO réinitialisé"
        self._log(msg)
        self._publish_state()

    def set_showmatch_bo(self, bo: int) -> None:
        if bo not in (3, 5, 7, 9):
            bo = 5
        with self.lock:
            self.state.showmatch_bo = int(bo)
            target = int(bo // 2) + 1
            self.state.showmatch_left_score = min(int(self.state.showmatch_left_score), target)
            self.state.showmatch_right_score = min(int(self.state.showmatch_right_score), target)
            self.state.showmatch_current_game = max(
                1,
                min(
                    int(self.state.showmatch_current_game or 1),
                    int(bo),
                ),
            )
            self._save_showmatch_config_locked()
        self._publish_state()

    def set_showmatch_names(self, left: str, right: str) -> None:
        with self.lock:
            self.state.showmatch_left_name = (left or "Player").strip()
            self.state.showmatch_right_name = (right or "Opponent").strip()
            self._save_showmatch_config_locked()
        self._publish_state()

    def reset_showmatch(self) -> None:
        with self.lock:
            self.state.showmatch_left_score = 0
            self.state.showmatch_right_score = 0
            self.state.showmatch_current_game = 1
            self.state.showmatch_last_winner = ""
            self.state.showmatch_last_main_result_key = ""
            self.state.showmatch_history = []
            self._ensure_showmatch_names_locked()
            self._save_showmatch_config_locked()
        self._log("Showmatch BO réinitialisé")
        self._publish_state()

    def undo_showmatch_game(self) -> None:
        with self.lock:
            if not self.state.showmatch_history:
                return
            last = self.state.showmatch_history.pop()
            side = last.get("side")
            if side == "left" and self.state.showmatch_left_score > 0:
                self.state.showmatch_left_score -= 1
            elif side == "right" and self.state.showmatch_right_score > 0:
                self.state.showmatch_right_score -= 1
            self.state.showmatch_last_winner = ""
            self.state.showmatch_last_main_result_key = ""
            self.state.showmatch_current_game = max(
                1,
                min(
                    int(self.state.showmatch_left_score) + int(self.state.showmatch_right_score) + 1,
                    int(self.state.showmatch_bo or 5),
                ),
            )
            self._save_showmatch_config_locked()
        self._log("Dernière game showmatch annulée")
        self._publish_state()

    def set_showmatch_current_game(self, game_number: int) -> None:
        with self.lock:
            try:
                game_number = int(game_number)
            except Exception:
                game_number = 1
            self.state.showmatch_current_game = max(1, min(game_number, int(self.state.showmatch_bo or 5)))
            self._save_showmatch_config_locked()
        self._publish_state()

    def add_showmatch_manual_game(self, side: str) -> None:
        with self.lock:
            if not bool(getattr(self.state, "showmatch_enabled", False)):
                self._log("Showmatch ignoré : overlay masqué")
                return
            self._add_showmatch_game_locked(side, manual=True, source="manual")
            self._save_showmatch_config_locked()
        self._log(f"Showmatch : +1 game {'gauche' if side == 'left' else 'droite'}")
        self._publish_state()

    def _name_from_player_dict(self, player: Dict[str, Any]) -> str:
        for key in ("Name", "name", "PlayerName", "player_name", "DisplayName", "display_name"):
            value = player.get(key)
            if value:
                return str(value).strip()
        return ""

    def _team_from_player_dict(self, player: Dict[str, Any]) -> Optional[int]:
        for key in ("TeamNum", "team", "Team", "teamNum", "team_num"):
            try:
                value = player.get(key)
                if value is not None:
                    return int(value)
            except Exception:
                pass
        return None

    def _ensure_showmatch_names_locked(self) -> None:
        """Synchronise pseudos + couleurs du Showmatch avec les infos joueurs disponibles."""
        players = list(getattr(self.state, "current_players", []) or [])
        by_team: Dict[int, List[str]] = {0: [], 1: []}
        for player in players:
            if not isinstance(player, dict):
                continue
            team = self._team_from_player_dict(player)
            name = self._name_from_player_dict(player)
            if team in (0, 1) and name:
                by_team.setdefault(team, []).append(name)

        local_name = (getattr(self.state, "detected_player_name", "") or "").strip()
        my_team = getattr(self.state, "my_team", None)

        if my_team not in (0, 1) and local_name:
            local_lower = local_name.lower()
            for team, names in by_team.items():
                if any(name.lower() == local_lower for name in names):
                    my_team = team
                    break

        if my_team not in (0, 1):
            # Fallback stable : gauche bleu, droite orange.
            my_team = 0

        opponent_team = 1 - int(my_team)
        self.state.showmatch_left_team = int(my_team)
        self.state.showmatch_right_team = int(opponent_team)

        left_name = local_name or (by_team.get(int(my_team)) or ["Player"])[0]
        right_names = [n for n in by_team.get(int(opponent_team), []) if n]
        right_name = right_names[0] if right_names else (self.state.showmatch_right_name or "Opponent")

        if left_name:
            self.state.showmatch_left_name = left_name
        if right_name:
            self.state.showmatch_right_name = right_name

    def _add_showmatch_game_locked(self, side: str, manual: bool = False, source: str = "auto") -> bool:
        if side not in ("left", "right"):
            return False

        target = int(self.state.showmatch_bo // 2) + 1
        if self.state.showmatch_left_score >= target or self.state.showmatch_right_score >= target:
            return False

        if side == "left":
            self.state.showmatch_left_score += 1
            winner = self.state.showmatch_left_name
        else:
            self.state.showmatch_right_score += 1
            winner = self.state.showmatch_right_name

        self.state.showmatch_last_winner = winner
        self.state.showmatch_history.append({
            "side": side,
            "winner": winner,
            "time": time.strftime("%H:%M:%S"),
            "left_score": int(self.state.showmatch_left_score),
            "right_score": int(self.state.showmatch_right_score),
            "manual": bool(manual),
            "source": source,
        })
        self.state.showmatch_history = self.state.showmatch_history[-30:]
        self.state.showmatch_current_game = max(
            1,
            min(
                int(self.state.showmatch_left_score) + int(self.state.showmatch_right_score) + 1,
                int(self.state.showmatch_bo or 5),
            ),
        )
        return True

    def _showmatch_sync_key_locked(self, source: str, result_or_team: Any) -> str:
        score = getattr(self.state, "team_scores", {}) or {}
        try:
            score_sig = f"{score.get(0, '')}-{score.get(1, '')}"
        except Exception:
            score_sig = str(score)
        players_sig = ",".join(
            sorted(
                self._name_from_player_dict(player)
                for player in (getattr(self.state, "current_players", []) or [])
                if isinstance(player, dict) and self._name_from_player_dict(player)
            )
        )
        return "|".join([
            str(source),
            str(result_or_team),
            str(getattr(self.state, "selected_playlist", "")),
            str(getattr(self.state, "current_match_key", "")),
            score_sig,
            players_sig,
            str(getattr(self.state, "last_event", "")),
        ])

    def _sync_showmatch_from_winner_team_locked(self, winner_team: Any, source: str = "winner_team") -> bool:
        """Compte une game Showmatch depuis la team gagnante officielle/score.

        Cette voie est nécessaire en match privé quand l'app est spectatrice ou quand
        l'API ne fournit pas de joueur local exploitable : dans ce cas il n'y a pas de
        win/loss personnel, mais on peut tout de même ajouter le point à gauche/droite
        selon la team gagnante.
        """
        if not getattr(self.state, "showmatch_enabled", False):
            return False
        try:
            winner_team_int = int(winner_team)
        except Exception:
            return False
        if winner_team_int not in (0, 1):
            return False

        self._ensure_showmatch_names_locked()
        left_team = getattr(self.state, "showmatch_left_team", None)
        right_team = getattr(self.state, "showmatch_right_team", None)
        try:
            left_team = int(left_team) if left_team is not None else 0
        except Exception:
            left_team = 0
        try:
            right_team = int(right_team) if right_team is not None else 1
        except Exception:
            right_team = 1

        if winner_team_int == left_team:
            side = "left"
        elif winner_team_int == right_team:
            side = "right"
        else:
            # Fallback stable si les teams n'ont pas encore été synchronisées.
            side = "left" if winner_team_int == 0 else "right"

        key = self._showmatch_sync_key_locked(source, f"team:{winner_team_int}")
        if key and key == getattr(self.state, "showmatch_last_main_result_key", ""):
            return False

        if self._add_showmatch_game_locked(side, manual=False, source=source):
            self.state.showmatch_last_main_result_key = key
            self._save_showmatch_config_locked()
            try:
                self._log(f"Showmatch auto : team {winner_team_int} gagnante → point {'gauche' if side == 'left' else 'droite'}")
            except Exception:
                pass
            return True
        return False

    def _winner_team_from_scores_or_api_locked(self, winner: Any = None) -> Optional[int]:
        """Retourne la team gagnante sans dépendre du joueur local."""
        candidate = winner if winner is not None else self.state.current_match_api_winner
        try:
            if candidate is not None:
                value = int(candidate)
                if value in (0, 1):
                    return value
        except Exception:
            pass
        try:
            score0 = int((self.state.team_scores or {}).get(0, 0))
            score1 = int((self.state.team_scores or {}).get(1, 0))
            if score0 > score1:
                return 0
            if score1 > score0:
                return 1
        except Exception:
            pass
        return None

    def _sync_showmatch_from_main_result_locked(self, result: str, source: str = "main") -> bool:
        """Compte le BO Showmatch à partir du résultat déjà détecté par l'overlay principal."""
        if result not in ("win", "loss"):
            return False
        if not getattr(self.state, "showmatch_enabled", False):
            return False

        self._ensure_showmatch_names_locked()

        key = self._showmatch_sync_key_locked(source, result)

        if key and key == getattr(self.state, "showmatch_last_main_result_key", ""):
            return False

        side = "left" if result == "win" else "right"
        if self._add_showmatch_game_locked(side, manual=False, source=source):
            self.state.showmatch_last_main_result_key = key
            self._save_showmatch_config_locked()
            try:
                self._log(f"Showmatch auto : {result.upper()} principal → point {'gauche' if side == 'left' else 'droite'}")
            except Exception:
                pass
            return True
        return False

    def add_result(self, result: str, auto: bool = False) -> None:
        showmatch_updated = False
        main_stats_updated = False
        main_overlay_visible = True
        showmatch_visible = False

        with self.lock:
            if result not in ("win", "loss"):
                return

            main_overlay_visible = bool(getattr(self.state, "main_overlay_enabled", True))
            showmatch_visible = bool(getattr(self.state, "showmatch_enabled", False))

            if main_overlay_visible:
                # L'overlay principal est visible : on ajoute normalement la win/loss
                # dans la session ranked active et on conserve l'historique existant.
                if result == "win":
                    self.state.wins += 1
                else:
                    self.state.losses += 1

                if self.state.streak_type == result:
                    self.state.streak_val += 1
                else:
                    self.state.streak_type = result
                    self.state.streak_val = 1

                self.state.history.insert(
                    0,
                    {"type": result, "time": time.strftime("%H:%M:%S"), "auto": bool(auto)},
                )
                self.state.history = self.state.history[:30]
                self._save_active_mode_session_locked()
                main_stats_updated = True
            else:
                # L'overlay principal est masqué : on garde les anciennes stats
                # Win/Lose telles qu'elles étaient au moment du masquage. Les fins
                # de match continuent seulement à alimenter le Showmatch si lui est visible.
                main_stats_updated = False

            # Même si les stats principales sont figées, le Showmatch doit pouvoir
            # prendre le point depuis la même détection de fin de match.
            if showmatch_visible:
                source = "add_result" if main_overlay_visible else "main_hidden_add_result"
                showmatch_updated = self._sync_showmatch_from_main_result_locked(result, source)

        if main_stats_updated:
            self._log(f"Résultat ajouté : {result.upper()}{' · auto' if auto else ''}")
            if showmatch_updated:
                self._log("Overlay Showmatch actualisé depuis le résultat principal")
        elif showmatch_updated:
            self._log(f"Overlay Win/Lose masqué → stats principales conservées · Showmatch +1 {result.upper()}{' · auto' if auto else ''}")
        else:
            self._log(f"Overlay Win/Lose masqué → {result.upper()} détecté mais non ajouté aux stats principales")

        self._publish_state()
        # Sécurité visuelle : si l'événement vient d'un thread API/WebSocket,
        # on force aussi une mise à jour UI locale avec l'état public courant.
        try:
            self.signals.state_changed.emit(self.get_public_state())
        except Exception:
            pass

    def remove_result(self, result: str) -> None:
        with self.lock:
            if not bool(getattr(self.state, "main_overlay_enabled", True)):
                self._log("Action ignorée : overlay Win/Lose masqué")
                return
            if result == "win" and self.state.wins > 0:
                self.state.wins -= 1
            elif result == "loss" and self.state.losses > 0:
                self.state.losses -= 1
            else:
                return
            for idx, item in enumerate(self.state.history):
                if item.get("type") == result:
                    self.state.history.pop(idx)
                    break
            # Les boutons de stats principales ne modifient pas le BO Showmatch.
            self._recalc_streak_locked()
            self._save_active_mode_session_locked()
        self._log(f"Résultat retiré : {result.upper()}")
        self._publish_state()
        try:
            self.signals.state_changed.emit(self.get_public_state())
        except Exception:
            pass

    def _recalc_streak_locked(self) -> None:
        if not self.state.history:
            self.state.streak_val = 0
            self.state.streak_type = ""
            return
        first = self.state.history[0].get("type", "")
        self.state.streak_type = first
        self.state.streak_val = 0
        for item in self.state.history:
            if item.get("type") == first:
                self.state.streak_val += 1
            else:
                break

    def _mode_session_payload_locked(self, playlist: Optional[str] = None) -> Dict[str, Any]:
        """Snapshot léger de la session active du mode actuel."""
        playlist = playlist or self.state.selected_playlist
        return {
            "playlist": playlist,
            "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "wins": int(self.state.wins),
            "losses": int(self.state.losses),
            "streak_val": int(self.state.streak_val),
            "streak_type": str(self.state.streak_type or ""),
            "session_start": float(self.state.session_start or time.time()),
            "history": json.loads(json.dumps(self.state.history[-30:])),
        }

    def _empty_mode_session_payload(self, playlist: str) -> Dict[str, Any]:
        """Session vierge pour une playlist."""
        return {
            "playlist": playlist,
            "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "wins": 0,
            "losses": 0,
            "streak_val": 0,
            "streak_type": "",
            "session_start": time.time(),
            "history": [],
        }

    def _empty_all_mmr_payload(self) -> Dict[str, Dict[str, Any]]:
        """MMR vierge pour toutes les playlists suivies."""
        return {
            k: {"mmr": None, "mmr_start": None, "mmr_change": 0, "rank": "", "rank_short": "", "rank_asset": "", "leader_rank": ""}
            for k in PLAYLIST_NAMES
        }

    def _saved_all_mmr_payload_locked(self) -> Dict[str, Dict[str, Any]]:
        """Payload MMR destiné aux sauvegardes joueur.

        Les sauvegardes conservent le MMR/rank actuel de chaque playlist,
        mais jamais le +/- MMR de session. Au rechargement, ce MMR devient
        simplement la nouvelle base et les futures différences repartent de 0.
        """
        clean = self._empty_all_mmr_payload()
        for playlist in PLAYLIST_NAMES:
            source = self.state.all_mmr.get(playlist, {})
            if not isinstance(source, dict):
                continue
            mmr = source.get("mmr")
            try:
                mmr = int(mmr) if mmr is not None and str(mmr).strip() not in {"", "—", "-"} else None
            except Exception:
                mmr = None
            clean[playlist].update({
                "mmr": mmr,
                "mmr_start": mmr,
                "mmr_change": 0,
                "rank": str(source.get("rank") or ""),
                "rank_short": str(source.get("rank_short") or ""),
                "rank_asset": str(source.get("rank_asset") or ""),
                "leader_rank": str(source.get("leader_rank") or ""),
            })
        return clean

    def _sanitize_saved_session_mmr_payload(self, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        """Supprime toute différence MMR avant d'écrire une sauvegarde."""
        all_mmr = snapshot.get("all_mmr")
        if isinstance(all_mmr, dict):
            for playlist, data in list(all_mmr.items()):
                if not isinstance(data, dict):
                    continue
                mmr = data.get("mmr")
                try:
                    mmr = int(mmr) if mmr is not None and str(mmr).strip() not in {"", "—", "-"} else None
                except Exception:
                    mmr = None
                data["mmr"] = mmr
                data["mmr_start"] = mmr
                data["mmr_change"] = 0
        return snapshot

    def _mode_sessions_locked(self) -> Dict[str, Any]:
        sessions = self.config.data.get("mode_sessions")
        if not isinstance(sessions, dict):
            sessions = {}
            self.config.data["mode_sessions"] = sessions
        return sessions

    def _save_active_mode_session_locked(self, playlist: Optional[str] = None) -> None:
        """Enregistre en fond la session du mode actif sans toucher aux autres modes."""
        playlist = playlist or self.state.selected_playlist
        if playlist not in PLAYLIST_NAMES:
            return
        sessions = self._mode_sessions_locked()
        sessions[playlist] = self._mode_session_payload_locked(playlist)
        self.config.data["mode_sessions"] = sessions
        self.config.save()

    def _complete_mode_sessions_payload_locked(self) -> Dict[str, Any]:
        """Renvoie une sauvegarde complète 1v1 / 2v2 / 3v3."""
        if self.state.selected_playlist in PLAYLIST_NAMES:
            self._save_active_mode_session_locked(self.state.selected_playlist)
        sessions = json.loads(json.dumps(self._mode_sessions_locked()))
        for playlist in PLAYLIST_NAMES:
            if not isinstance(sessions.get(playlist), dict):
                sessions[playlist] = self._empty_mode_session_payload(playlist)
        return sessions

    def _reset_active_stats_locked(self) -> None:
        self.state.wins = 0
        self.state.losses = 0
        self.state.streak_val = 0
        self.state.streak_type = ""
        self.state.session_start = time.time()
        self.state.history = []

    def _reset_all_player_stats_locked(self) -> None:
        """Reset complet des stats 1v1 / 2v2 / 3v3 pour accueillir un nouveau compte joueur."""
        self._reset_active_stats_locked()
        self.state.all_mmr = self._empty_all_mmr_payload()
        self.config.data["mode_sessions"] = {
            playlist: self._empty_mode_session_payload(playlist)
            for playlist in PLAYLIST_NAMES
        }
        self.config.data["selected_playlist"] = self.state.selected_playlist
        self.config.save()
        self._clear_match_context_locked()

    def _clear_match_context_locked(self) -> None:
        self.state.match_active = False
        self.state.match_counted = False
        self.state.current_match_key = ""
        self.state.last_server_key = self.state.current_server_key
        self.state.current_server_key = ""
        self.state.current_match_has_timer = False
        self.state.current_match_had_opponent = False
        self.state.current_match_had_ranked_context = False
        self.state.training_active = False
        self.state.my_team = None
        self.state.team_scores = {}
        self.state.last_scores = {}
        self.state.current_players = []
        self.state.current_match_ranked = False
        self.state.current_match_private = False
        self.state.current_match_no_stats = False
        self.state.current_match_no_stats_reason = ""
        self.state.current_match_platform = "auto"
        self.state.current_match_api_winner = None
        self.state.current_match_end_reason = ""
        self.state.current_match_waiting_destroy = False
        self._reset_match_playlist_lock_locked()

    def _load_mode_session_locked(self, playlist: str, reset_if_missing: bool = True) -> bool:
        """Charge automatiquement la session sauvegardée du mode demandé."""
        if playlist not in PLAYLIST_NAMES:
            return False
        sessions = self._mode_sessions_locked()
        session = sessions.get(playlist)
        if isinstance(session, dict):
            self.state.wins = int(session.get("wins", 0))
            self.state.losses = int(session.get("losses", 0))
            self.state.streak_val = int(session.get("streak_val", 0))
            self.state.streak_type = str(session.get("streak_type", ""))
            self.state.session_start = float(session.get("session_start", time.time()))
            history = session.get("history", [])
            self.state.history = history[:30] if isinstance(history, list) else []
            return True

        if reset_if_missing:
            self._reset_active_stats_locked()
        return False


    def _switch_playlist_locked(self, playlist: str, source: str = "mode", clear_match: bool = False) -> bool:
        """Sauvegarde le mode actuel, charge le nouveau mode, sans perdre les autres sessions."""
        if playlist not in PLAYLIST_NAMES:
            return False
        old_playlist = self.state.selected_playlist
        if old_playlist == playlist:
            return False

        if old_playlist in PLAYLIST_NAMES:
            self._save_active_mode_session_locked(old_playlist)

        self.state.selected_playlist = playlist
        loaded = self._load_mode_session_locked(playlist, reset_if_missing=True)
        if clear_match:
            self._clear_match_context_locked()
        self.config.data["selected_playlist"] = playlist
        self.config.save()

        try:
            state_txt = "session reprise" if loaded else "nouvelle session"
            self._log(f"Mode {source} : {PLAYLIST_NAMES.get(playlist, playlist)} · {state_txt}")
        except Exception:
            pass
        return True


    def _session_snapshot(self, name: str) -> Dict[str, Any]:
        with self.lock:
            mode_sessions = self._complete_mode_sessions_payload_locked()
            selected = self.state.selected_playlist if self.state.selected_playlist in PLAYLIST_NAMES else ""
            if selected:
                active = mode_sessions.get(selected, self._empty_mode_session_payload(selected))
            else:
                active = self._mode_session_payload_locked("")
            return {
                "schema_version": 2,
                "name": name,
                "player": str(self.state.detected_player_name or ""),
                "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "selected_playlist": selected,
                "mode_sessions": mode_sessions,
                "all_mmr": json.loads(json.dumps(self._saved_all_mmr_payload_locked())),
                "tracker": {
                    "platform": str(self.config.get("tracker_platform", "auto") or "auto"),
                    "force_player": str(self.config.get("tracker_force_player", "") or ""),
                    # Identité API RLS sauvegardée avec la session précédente.
                    # Elle est restaurable plus tard, mais effacée de la session active
                    # dès que StatsAPI se déconnecte.
                    "rls_platform": str(self.config.get("rls_saved_platform", "") or ""),
                    "rls_primary_id": str(self.config.get("rls_saved_primary_id", "") or ""),
                    "rls_endpoint": str(self.config.get("rls_saved_endpoint", "") or ""),
                },
                "tracker_platform": str(self.config.get("tracker_platform", "auto") or "auto"),
                "tracker_force_player": str(self.config.get("tracker_force_player", "") or ""),
                "rls_saved_platform": str(self.config.get("rls_saved_platform", "") or ""),
                "rls_saved_primary_id": str(self.config.get("rls_saved_primary_id", "") or ""),
                "rls_saved_endpoint": str(self.config.get("rls_saved_endpoint", "") or ""),
                # Champs legacy conservés pour compatibilité avec l'ancien chargement.
                "wins": int(active.get("wins", 0)),
                "losses": int(active.get("losses", 0)),
                "streak_val": int(active.get("streak_val", 0)),
                "streak_type": str(active.get("streak_type", "")),
                "session_start": float(active.get("session_start", time.time())),
                "history": json.loads(json.dumps(active.get("history", []))),
            }

    def _saved_sessions(self) -> List[Dict[str, Any]]:
        sessions = self.config.get("saved_sessions", [])
        return sessions if isinstance(sessions, list) else []

    def _store_saved_session_locked(self, snapshot: Dict[str, Any]) -> None:
        name = str(snapshot.get("name") or "").strip()
        if not name:
            return
        snapshot = self._sanitize_saved_session_mmr_payload(snapshot)
        sessions = [s for s in self._saved_sessions() if str(s.get("name")) != name]
        sessions.insert(0, snapshot)
        self.config.data["saved_sessions"] = sessions[:20]
        self.config.save()

    def _on_tracker_force_player_changed(self, value: str) -> None:
        """Met à jour le pseudo/ID API RLS sans changer le joueur principal."""
        forced = str(value or "").strip()
        self.config.data["tracker_force_player"] = forced
        self.config.save()
        # Ce champ sert uniquement aux requêtes API RLS. Il ne doit plus écrire
        # dans detected_player_name ni déclencher reset/logs de stats principales.
        self._publish_state(count_revision=False)

    def _sync_tracker_inputs_from_config(self) -> None:
        """Garde les champs API RLS affichés alignés avec la config active."""
        try:
            if hasattr(self, "tracker_platform_combo"):
                platform = str(self.config.get("tracker_platform", "auto") or "auto")
                if platform not in {"auto", "epic", "steam", "xbl", "psn", "switch"}:
                    platform = "auto"
                self.tracker_platform_combo.blockSignals(True)
                self.tracker_platform_combo.setCurrentText(platform)
                self.tracker_platform_combo.blockSignals(False)
            if hasattr(self, "tracker_player_edit"):
                self.tracker_player_edit.blockSignals(True)
                self.tracker_player_edit.setText(str(self.config.get("tracker_force_player", "") or ""))
                self.tracker_player_edit.blockSignals(False)
        except Exception:
            pass

    def _restore_tracker_config_from_session_locked(self, session: Dict[str, Any]) -> None:
        """Restaure le profil API RLS enregistré avec une sauvegarde."""
        tracker = session.get("tracker") if isinstance(session.get("tracker"), dict) else {}
        platform = str(tracker.get("platform") or session.get("tracker_platform") or self.config.get("tracker_platform", "auto") or "auto")
        platform = self._normalize_tracker_platform(platform)
        force_player = str(tracker.get("force_player") if "force_player" in tracker else session.get("tracker_force_player", "") or "").strip()
        self.config.data["tracker_platform"] = platform or "auto"
        self.config.data["tracker_force_player"] = force_player

        rls_platform = str(tracker.get("rls_platform") or session.get("rls_saved_platform") or "").strip()
        rls_primary_id = str(tracker.get("rls_primary_id") or session.get("rls_saved_primary_id") or "").strip()
        rls_endpoint = str(tracker.get("rls_endpoint") or session.get("rls_saved_endpoint") or "").strip()

        # Compatibilité : si seul /{platform}/{id} est présent, on le relit.
        if rls_endpoint and not rls_primary_id:
            parts = [p for p in rls_endpoint.strip().split("/") if p]
            if len(parts) >= 2:
                rls_platform = parts[0]
                rls_primary_id = parts[1]

        if rls_primary_id:
            rls_platform, rls_primary_id, rls_endpoint = self._normalize_rls_saved_endpoint_locked(
                rls_platform or "auto",
                rls_primary_id,
            )
            self.config.data["rls_saved_platform"] = rls_platform
            self.config.data["rls_saved_primary_id"] = rls_primary_id
            self.config.data["rls_saved_endpoint"] = rls_endpoint
        else:
            # Ancienne sauvegarde sans identité RLS : on ne garde pas un endpoint
            # actif venant d'une session précédente.
            self.config.data["rls_saved_platform"] = ""
            self.config.data["rls_saved_primary_id"] = ""
            self.config.data["rls_saved_endpoint"] = ""

    def _clear_manual_tracker_profile_locked(self) -> None:
        """Efface uniquement le pseudo/ID joueur manuel au changement de joueur sans sauvegarde."""
        self.config.data["tracker_force_player"] = ""
        self._last_tracker_key = ""
        self._last_tracker_fetch = 0.0

    def _clear_active_rls_identity_locked(self) -> None:
        """Efface complètement /{platform}/{id} de la session active.

        Utilisé après la sauvegarde automatique à la déconnexion StatsAPI,
        pour que la prochaine connexion reparte sur une session vide.
        """
        self.config.data["rls_saved_platform"] = ""
        self.config.data["rls_saved_primary_id"] = ""
        self.config.data["rls_saved_endpoint"] = ""
        self._last_tracker_key = ""
        self._last_tracker_fetch = 0.0

    def _reset_runtime_session_after_statsapi_disconnect_locked(self) -> None:
        """Reset complet de la session courante après sauvegarde à la déconnexion StatsAPI.

        Les sauvegardes restent intactes. On nettoie uniquement l'état actif et les
        champs API RLS de la session en cours pour repartir sur un accueil vierge
        lors de la prochaine connexion StatsAPI.
        """
        connection = str(self.state.connection or "disconnected")
        connection_message = str(self.state.connection_message or "Non connecté")
        main_overlay_enabled = bool(self.state.main_overlay_enabled)
        showmatch_enabled = bool(self.state.showmatch_enabled)
        showmatch_bo = int(self.state.showmatch_bo or 5)
        if showmatch_bo not in (3, 5, 7, 9):
            showmatch_bo = 5

        # Stats principales / joueur / match courant.
        self.state.selected_playlist = ""
        self.state.detected_player_name = ""
        self.state.statsapi_freeplay_locked_player = ""
        self.state.statsapi_freeplay_locked_at = 0.0
        self.state.pending_detected_player_name = ""
        self.state.pending_detected_player_since = 0.0
        self.state.pending_detected_player_last_seen = 0.0
        self._reset_active_stats_locked()
        self.state.all_mmr = self._empty_all_mmr_payload()
        self.state.recent_counted_results = []
        self.state.match_id = ""
        self.state.last_closed_match_key = ""
        self.state.last_closed_match_at = 0.0
        self._clear_match_context_locked()

        # Infos affichées / API RLS.
        self.state.ignored_context = ""
        self.state.tracker_status = "API RLS : en attente"
        self.state.tracker_last_at = ""
        self.state.last_event = ""
        self.state.last_event_at = ""
        self.state.last_raw_event = {}
        self._last_tracker_key = ""
        self._last_tracker_fetch = 0.0

        # Showmatch : on garde uniquement le choix d'affichage et le BO,
        # mais on remet les scores/noms d'une nouvelle session à zéro.
        self.state.showmatch_enabled = showmatch_enabled
        self.state.showmatch_bo = showmatch_bo
        self.state.showmatch_left_name = "Player"
        self.state.showmatch_right_name = "Opponent"
        self.state.showmatch_left_score = 0
        self.state.showmatch_right_score = 0
        self.state.showmatch_current_game = 1
        self.state.showmatch_left_team = None
        self.state.showmatch_right_team = None
        self.state.showmatch_last_winner = ""
        self.state.showmatch_history = []
        self.state.showmatch_last_main_result_key = ""

        # On conserve les préférences générales, mais on nettoie les infos de session.
        self.state.connection = connection
        self.state.connection_message = connection_message
        self.state.main_overlay_enabled = main_overlay_enabled
        self.config.data["selected_playlist"] = ""
        self.config.data["mode_sessions"] = {
            playlist: self._empty_mode_session_payload(playlist)
            for playlist in PLAYLIST_NAMES
        }
        self.config.data["tracker_platform"] = "auto"
        self.config.data["tracker_force_player"] = ""
        # Après la sauvegarde automatique de la session précédente,
        # on efface complètement /{platform}/{id} de la session active.
        self._clear_active_rls_identity_locked()
        self.config.data["showmatch"] = {
            "enabled": showmatch_enabled,
            "bo": showmatch_bo,
            "left_name": "Player",
            "right_name": "Opponent",
            "left_score": 0,
            "right_score": 0,
            "current_game": 1,
            "left_team": None,
            "right_team": None,
            "last_winner": "",
            "history": [],
        }
        self.config.save()

    def _reset_mmr_baseline_for_loaded_session_locked(self) -> None:
        """Après chargement d'une sauvegarde, repart du MMR restauré comme base.

        Cela évite d'afficher un +/- MMR hérité de la session ou du joueur précédent.
        Les prochains gains/pertes MMR seront calculés uniquement après les nouvelles fins de match.
        """
        for playlist in PLAYLIST_NAMES:
            data = self.state.all_mmr.setdefault(playlist, {
                "mmr": None,
                "mmr_start": None,
                "mmr_change": 0,
                "rank": "",
                "rank_short": "",
                "rank_asset": "",
                "leader_rank": "",
            })
            mmr = data.get("mmr")
            if mmr is None or str(mmr).strip() in {"", "—", "-"}:
                data["mmr_start"] = None
                data["mmr_change"] = 0
                continue
            try:
                mmr_int = int(mmr)
            except Exception:
                data["mmr_start"] = None
                data["mmr_change"] = 0
                continue
            data["mmr"] = mmr_int
            data["mmr_start"] = mmr_int
            data["mmr_change"] = 0

    def _find_saved_session_for_player_locked(self, player_name: str) -> Optional[Dict[str, Any]]:
        target = str(player_name or "").strip().casefold()
        if not target:
            return None
        # Priorité au nom de sauvegarde, car les autosaves sont enregistrées au nom du joueur.
        for session in self._saved_sessions():
            if str(session.get("name") or "").strip().casefold() == target:
                return session
        for session in self._saved_sessions():
            if str(session.get("player") or "").strip().casefold() == target:
                return session
        return None

    def _apply_saved_session_locked(self, session: Dict[str, Any], detected_player_override: str = "") -> str:
        """Applique une sauvegarde complète 1v1/2v2/3v3 sans repasser par les boutons UI."""
        selected = str(session.get("selected_playlist", self.state.selected_playlist))
        if selected not in PLAYLIST_NAMES:
            selected = self.state.selected_playlist if self.state.selected_playlist in PLAYLIST_NAMES else ""

        if isinstance(session.get("mode_sessions"), dict):
            mode_sessions = json.loads(json.dumps(session.get("mode_sessions")))
            for playlist in PLAYLIST_NAMES:
                if not isinstance(mode_sessions.get(playlist), dict):
                    mode_sessions[playlist] = self._empty_mode_session_payload(playlist)
            self.config.data["mode_sessions"] = mode_sessions
            self.state.selected_playlist = selected
            if selected in PLAYLIST_NAMES:
                self._load_mode_session_locked(selected, reset_if_missing=True)
            else:
                self._reset_active_stats_locked()
        else:
            self.state.wins = int(session.get("wins", 0))
            self.state.losses = int(session.get("losses", 0))
            self.state.streak_val = int(session.get("streak_val", 0))
            self.state.streak_type = str(session.get("streak_type", ""))
            self.state.session_start = float(session.get("session_start", time.time()))
            self.state.selected_playlist = selected
            if isinstance(session.get("history"), list):
                self.state.history = session.get("history")[:30]
            if self.state.selected_playlist in PLAYLIST_NAMES:
                self._save_active_mode_session_locked(self.state.selected_playlist)

        if isinstance(session.get("all_mmr"), dict):
            loaded_mmr = self._empty_all_mmr_payload()
            for playlist, data in session.get("all_mmr", {}).items():
                if playlist in PLAYLIST_NAMES and isinstance(data, dict):
                    loaded_mmr[playlist].update(data)
            self.state.all_mmr = loaded_mmr
        else:
            self.state.all_mmr = self._empty_all_mmr_payload()

        self._reset_mmr_baseline_for_loaded_session_locked()

        player_name = str(detected_player_override or session.get("player") or session.get("name") or "").strip()
        if player_name:
            self.state.detected_player_name = player_name

        self._restore_tracker_config_from_session_locked(session)
        self._clear_match_context_locked()
        self.config.data["selected_playlist"] = self.state.selected_playlist
        self.config.save()
        return selected

    def _auto_save_previous_player_locked(self, previous_player: str) -> None:
        previous_player = (previous_player or "").strip()
        if not previous_player:
            return
        snapshot = self._session_snapshot(previous_player)
        snapshot["name"] = previous_player
        snapshot["player"] = previous_player
        snapshot["auto_saved_on_player_switch"] = True
        self._store_saved_session_locked(snapshot)

    def _auto_save_current_player_on_api_disconnect_locked(self) -> str:
        """Sauvegarde le joueur courant uniquement quand l'API se déconnecte.

        Si une sauvegarde porte exactement le même nom, _store_saved_session_locked
        la remplace par le nouveau snapshot. Cette sauvegarde inclut les 3 playlists
        et la configuration API RLS, sans enregistrer le +/- MMR de session.
        """
        player_name = str(self.state.detected_player_name or "").strip()
        if not player_name:
            return ""
        snapshot = self._session_snapshot(player_name)
        snapshot["name"] = player_name
        snapshot["player"] = player_name
        snapshot["auto_saved_on_api_disconnect"] = True
        snapshot.pop("auto_saved_on_player_switch", None)
        self._store_saved_session_locked(snapshot)
        return player_name


    def _save_and_reset_session_before_app_close_locked(self) -> str:
        """Sauvegarde la session puis vide Stats/API RLS avant fermeture.

        Même logique que la déconnexion StatsAPI :
        - sauvegarde automatique de la session active,
        - sauvegarde du /{platform}/{id} dans la session précédente,
        - effacement complet de l'identité API RLS active,
        - nouvelle session vide au prochain lancement.
        """
        self._save_active_mode_session_locked(self.state.selected_playlist)
        saved_player = self._auto_save_current_player_on_api_disconnect_locked()
        self._reset_runtime_session_after_statsapi_disconnect_locked()
        self._api_connected_since_last_disconnect_save = False
        self.config.save()
        return saved_player

    def _set_detected_player_name_locked(self, name: str, source: str = "api") -> bool:
        """Détecte un changement de compte joueur et restaure/initialise la bonne session."""
        new_name = str(name or "").strip()
        if not new_name:
            return False
        old_name = str(self.state.detected_player_name or "").strip()
        locked_freeplay_name = str(self.state.statsapi_freeplay_locked_player or "").strip()
        source_is_statsapi = self._is_statsapi_player_detection_source(source)
        source_l = str(source or "").casefold()
        manual_identity_confirmed = any(token in source_l for token in (
            "champ local du json",
            "indice local du json",
            "remote",
        ))
        if (
            locked_freeplay_name
            and source_is_statsapi
            and new_name.casefold() != locked_freeplay_name.casefold()
        ):
            # Le joueur validé en Freeplay reste définitif pour cette connexion StatsAPI.
            # API RLS ne peut plus remplacer cette identité pour les stats principales.
            # Les autres joueurs présents en match ne doivent générer ni log, ni reset,
            # ni changement de sauvegarde/statistiques de l'overlay principal.
            return False
        if old_name and old_name.casefold() != new_name.casefold():
            high_confidence_local = any(
                token in source_l
                for token in (
                    "champ local du json",
                    "indice local du json",
                    "remote",
                )
            )
            match_context_active = bool(
                self.state.match_active
                or self.state.current_match_ranked
                or self.state.current_match_private
                or self.state.current_match_no_stats
                or self.state.current_match_had_ranked_context
            )
            if match_context_active and not high_confidence_local:
                # Pendant une game, un autre joueur peut apparaître dans Players/Target.
                # On garde le joueur déjà verrouillé pour éviter logs, reset session ou
                # attribution de win/loss au mauvais compte. Le changement sera accepté
                # hors match, ou immédiatement si le JSON fournit un vrai marqueur local.
                now = time.time()
                if self.state.pending_detected_player_name.casefold() != new_name.casefold():
                    self.state.pending_detected_player_name = new_name
                    self.state.pending_detected_player_since = now
                self.state.pending_detected_player_last_seen = now
                return False
            self.state.pending_detected_player_name = ""
            self.state.pending_detected_player_since = 0.0
            self.state.pending_detected_player_last_seen = 0.0
            saved = self._find_saved_session_for_player_locked(new_name)
            if saved:
                self._apply_saved_session_locked(saved, detected_player_override=new_name)
                self._log(f"Nouveau joueur détecté ({source}) : sauvegarde de {new_name} chargée automatiquement")
            else:
                selected_playlist = self.state.selected_playlist if self.state.selected_playlist in PLAYLIST_NAMES else ""
                self._reset_all_player_stats_locked()
                self.state.selected_playlist = selected_playlist
                self.state.detected_player_name = new_name
                self.config.data["selected_playlist"] = selected_playlist
                # Un changement réel du joueur principal ne doit pas être causé par
                # API RLS. On ne nettoie donc plus automatiquement le champ API RLS ici :
                # il reste disponible pour les requêtes MMR/rank.
                self.config.save()
                clear_note = ""
                self._log(f"Nouveau joueur détecté ({source}) : aucune sauvegarde pour {new_name}, reset 1v1/2v2/3v3{clear_note}")
            try:
                self._refresh_session_ui()
                self._sync_tracker_inputs_from_config()
            except Exception:
                pass
            return True
        if not old_name:
            self.state.pending_detected_player_name = ""
            self.state.pending_detected_player_since = 0.0
            self.state.pending_detected_player_last_seen = 0.0
            saved = self._find_saved_session_for_player_locked(new_name)
            if saved:
                self._apply_saved_session_locked(saved, detected_player_override=new_name)
                self._log(f"Joueur détecté ({source}) : sauvegarde de {new_name} chargée automatiquement")
                try:
                    self._sync_tracker_inputs_from_config()
                except Exception:
                    pass
            else:
                self.state.detected_player_name = new_name
                # Premier joueur détecté sans sauvegarde : on évite de garder
                # un ancien ID joueur manuel qui viserait un autre compte, sauf si ce
                # même ID/pseudo manuel vient de confirmer le joueur local.
                # Ne pas effacer le champ API RLS quand le joueur principal est
                # détecté par StatsAPI : ce champ est indépendant des stats principales.
            return True
        return False

    def _refresh_session_ui(self) -> None:
        sessions = self._saved_sessions()
        names = [str(s.get("name", "Session")) for s in sessions]
        for attr in ("session_combo", "home_session_combo"):
            combo = getattr(self, attr, None)
            if combo is None:
                continue
            current = combo.currentText()
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(names)
            if current in names:
                combo.setCurrentText(current)
            combo.blockSignals(False)
        if hasattr(self, "session_info_label"):
            self.session_info_label.setText(f"{len(names)} sauvegarde(s) disponible(s).")

    def save_current_session(self, name: str = "") -> None:
        name = (name or time.strftime("Session %d/%m %H:%M")).strip()
        snapshot = self._session_snapshot(name)
        with self.lock:
            self._store_saved_session_locked(snapshot)
        self._refresh_session_ui()
        self._log(f"Sauvegarde complète créée : {name} · 1v1 / 2v2 / 3v3")

    def load_saved_session(self, name: str) -> None:
        name = (name or "").strip()
        session = next((s for s in self._saved_sessions() if str(s.get("name")) == name), None)
        if not session:
            self._log("Aucune sauvegarde sélectionnée")
            return
        with self.lock:
            self._apply_saved_session_locked(session)
        self._sync_tracker_inputs_from_config()
        self._log(f"Sauvegarde complète reprise : {name} · 1v1 / 2v2 / 3v3 + profil API RLS")
        self._publish_state()

    def rename_saved_session(self, old_name: str, new_name: str) -> None:
        old_name = (old_name or "").strip()
        new_name = (new_name or "").strip()
        if not old_name or not new_name:
            self._log("Renommage impossible : choisis une sauvegarde et un nouveau nom")
            return
        sessions = self._saved_sessions()
        for s in sessions:
            if str(s.get("name")) == old_name:
                s["name"] = new_name
                s["saved_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
                self.config["saved_sessions"] = sessions
                self._refresh_session_ui()
                if hasattr(self, "session_combo"):
                    self.session_combo.setCurrentText(new_name)
                if hasattr(self, "home_session_combo"):
                    self.home_session_combo.setCurrentText(new_name)
                self._log(f"Sauvegarde renommée : {old_name} → {new_name}")
                return
        self._log("Sauvegarde introuvable")

    def delete_saved_session(self, name: str) -> None:
        name = (name or "").strip()
        if not name:
            self._log("Aucune sauvegarde sélectionnée")
            return
        sessions = [s for s in self._saved_sessions() if str(s.get("name")) != name]
        self.config["saved_sessions"] = sessions
        self._refresh_session_ui()
        self._log(f"Sauvegarde supprimée : {name}")

    def reset_session(self) -> None:
        with self.lock:
            current_playlist = self.state.selected_playlist
            self._reset_active_stats_locked()
            self._clear_match_context_locked()

            sessions = self._mode_sessions_locked()
            if current_playlist in sessions:
                sessions.pop(current_playlist, None)
                self.config.data["mode_sessions"] = sessions

            # Reset Dashboard Beta 3.7 :
            # le bouton Reset efface aussi complètement le MMR affiché
            # et l'identité API RLS sauvegardée /{platform}/{id}.
            self.state.all_mmr = self._empty_all_mmr_payload()
            self.state.tracker_status = "API RLS : en attente"
            self.state.tracker_last_at = ""
            self._clear_active_rls_identity_locked()
            self.config.save()

        self._log(
            f"Session réinitialisée pour {PLAYLIST_NAMES.get(current_playlist, 'aucune playlist')} · "
            "MMR et API RLS effacés"
        )
        self._publish_state()

    def select_playlist(self, playlist: str) -> None:
        playlist = str(playlist or "").strip()
        if playlist == NO_PLAYLIST_LABEL:
            playlist = ""
        if playlist not in PLAYLIST_NAMES:
            with self.lock:
                if self.state.selected_playlist in PLAYLIST_NAMES:
                    self._save_active_mode_session_locked(self.state.selected_playlist)
                self.state.selected_playlist = ""
                self._reset_active_stats_locked()
                self._clear_match_context_locked()
            self.config["selected_playlist"] = ""
            self._log("Playlist sélectionnée : aucune")
            self._publish_state()
            return
        changed = False
        with self.lock:
            changed = self._switch_playlist_locked(playlist, "sélectionné", clear_match=True)
        self.config["selected_playlist"] = playlist
        if not changed:
            self._log(f"Playlist sélectionnée : {playlist}")
        self._publish_state()

    def set_mmr(self, playlist: str, mmr: Optional[int], rank: str = "", auto: bool = False, leader_rank: str = "") -> None:
        if playlist not in PLAYLIST_NAMES:
            return
        with self.lock:
            data = self.state.all_mmr[playlist]
            if mmr is not None:
                mmr = int(mmr)
                if data.get("mmr_start") is None:
                    data["mmr_start"] = mmr
                data["mmr_change"] = mmr - int(data.get("mmr_start") or mmr)
                data["mmr"] = mmr
                info = rank_from_mmr(playlist, mmr)
                data["rank"] = info.get("label", "")
                data["rank_short"] = info.get("short", "")
                data["rank_asset"] = info.get("asset", "")
            elif rank is not None:
                manual_info = rank_from_text(rank)
                data["rank"] = manual_info.get("label") or rank
                data["rank_short"] = manual_info.get("short") or rank
                data["rank_asset"] = manual_info.get("asset", "")
            if rank and mmr is None:
                manual_info = rank_from_text(rank)
                if manual_info.get("asset"):
                    data["rank"] = manual_info.get("label", rank)
                    data["rank_short"] = manual_info.get("short", rank)
                    data["rank_asset"] = manual_info.get("asset", "")
            display_leader_rank = normalize_display_leader_rank(leader_rank)
            if display_leader_rank:
                data["leader_rank"] = display_leader_rank
            else:
                data["leader_rank"] = ""
            if playlist != self.state.selected_playlist and self.config.get("auto_detect_playlist", True):
                # IMPORTANT : une mise à jour MMR/API RLS ne doit jamais changer la playlist.
                # L'API RLS retourne souvent 1v1/2v2/3v3 dans la même réponse ; avant ce correctif,
                # le dernier MMR reçu pouvait basculer l'overlay en 3v3 sans nouvelle game.
                # Désormais la playlist change uniquement via la détection StatsAPI d'une vraie partie
                # puis le verrouillage 5s jusqu'au MatchDestroyed, ou via une action manuelle.
                if not auto and not self.state.match_active and not self.state.current_match_waiting_destroy:
                    self._switch_playlist_locked(playlist, "MMR manuel")
        suffix = " · auto" if auto else ""
        self._log(f"MMR {playlist} mis à jour : {mmr or '—'} {rank_from_mmr(playlist, mmr).get('label', rank) if mmr else rank}{suffix}")
        self._publish_state()

    def update_theme(self, patch: Dict[str, Any]) -> None:
        theme = dict(self.config["theme"])
        patch = {k: v for k, v in dict(patch).items() if k != "radius"}
        theme.update(patch)
        theme["radius"] = 20
        theme["bg"] = "rgba(8,10,16,.88)"
        self.config["theme"] = theme
        self._publish_state()

    def _set_mmr_from_ui(self) -> None:
        playlist = self.playlist_combo.currentText()
        if playlist == NO_PLAYLIST_LABEL:
            self._log("MMR ignoré : aucune playlist sélectionnée")
            return
        mmr_text = self.mmr_edit.text().strip()
        rank = self.rank_edit.text().strip()
        mmr: Optional[int]
        try:
            mmr = int(mmr_text) if mmr_text else None
        except ValueError:
            self._log("MMR invalide : entre un nombre entier")
            return
        self.set_mmr(playlist, mmr, rank)

    def _handle_remote_command(self, data: Dict[str, Any]) -> None:
        key = data.get("key", "")
        if key != self.config.get("remote_key"):
            self._log("Commande remote refusée : token invalide")
            return
        action = data.get("action")
        value = data.get("value")
        try:
            if action == "add_result":
                self.add_result(str(value))
            elif action == "remove_result":
                self.remove_result(str(value))
            elif action == "reset":
                self.reset_session()
            elif action == "select_playlist":
                self.select_playlist(str(value))
                self.playlist_combo.setCurrentText(str(value))
            elif action == "set_theme":
                patch = data.get("patch", {})
                if isinstance(patch, dict):
                    self.update_theme(patch)
            elif action == "set_mmr":
                self.set_mmr(str(data.get("playlist", self.state.selected_playlist)), int(data["mmr"]) if str(data.get("mmr", "")).strip() else None, str(data.get("rank", "")))
            elif action == "set_player":
                with self.lock:
                    self._set_detected_player_name_locked(str(value or ""), "remote")
                self._publish_state()
            elif action == "main_overlay_enabled":
                self.set_main_overlay_enabled(bool(value))
            elif action == "showmatch_enabled":
                self.set_showmatch_enabled(bool(value))
            elif action == "showmatch_bo":
                self.set_showmatch_bo(int(value))
            elif action == "showmatch_reset":
                self.reset_showmatch()
            elif action == "showmatch_undo":
                self.undo_showmatch_game()
            elif action == "showmatch_add_left":
                self.add_showmatch_manual_game("left")
            elif action == "showmatch_add_right":
                self.add_showmatch_manual_game("right")
            elif action == "showmatch_current_game":
                self.set_showmatch_current_game(int(value))
            elif action == "simulate_update":
                self.simulate_update_state()
        except Exception as exc:
            self._log(f"Commande remote erreur : {exc}")

    def simulate_update_state(self) -> None:
        with self.lock:
            current = max(self.state.team_scores.get(0, 0), self.state.team_scores.get(1, 0))
        event = {
            "Event": "UpdateState",
            "Data": {
                "Game": {
                    "PlaylistId": 13,
                    "GameMode": "Ranked Standard 3v3",
                    "bHasTarget": True,
                    "Target": {"Name": self.state.detected_player_name or "Player", "TeamNum": 0},
                    "Teams": [
                        {"TeamNum": 0, "Score": current},
                        {"TeamNum": 1, "Score": max(0, current - 1)},
                    ],
                },
                "Players": [
                    {"Name": self.state.detected_player_name or "Player", "TeamNum": 0, "Goals": current, "Assists": 0, "Saves": 1},
                    {"Name": "Opponent", "TeamNum": 1, "Goals": max(0, current - 1), "Assists": 0, "Saves": 0},
                ],
            },
        }
        self.process_api_event(event)
        self._publish_state()

    def simulate_training_state(self) -> None:
        event = {
            "Event": "UpdateState",
            "Data": {
                "Game": {
                    "PlaylistId": 0,
                    "GameMode": "Freeplay Training",
                    "bHasTarget": True,
                    "Target": {"Name": self.state.detected_player_name or "Player", "TeamNum": 0},
                    "Teams": [{"TeamNum": 0, "Score": 9}, {"TeamNum": 1, "Score": 0}],
                },
                "Players": [{"Name": self.state.detected_player_name or "Player", "TeamNum": 0, "Goals": 9}],
            },
        }
        self.process_api_event(event)
        self._publish_state()

    # ──────────────────────────────────────────────────────────────────────
    # Settings + URLs
    # ──────────────────────────────────────────────────────────────────────

    def _candidate_rl_config_dirs(self, platform: str = "all") -> List[Path]:
        """Détecte automatiquement les dossiers Rocket League TAGame\\Config.

        La détection ne dépend pas d'un chemin fixe Steam/Epic :
        - Documents Windows
        - Documents redirigés OneDrive
        - Bibliothèques Steam depuis libraryfolders.vdf
        - Manifestes Epic Games Launcher
        - chemins d'installation classiques en dernier recours
        """
        candidates: List[Path] = []

        def add_candidate(path: Any) -> None:
            if not path:
                return
            try:
                p = Path(str(path)).expanduser()
            except Exception:
                return

            # Accepte soit TAGame\\Config directement, soit Rocket League / rocketleague,
            # soit TAGame, et normalise vers TAGame\\Config.
            parts_lower = [part.lower() for part in p.parts]
            if p.name.lower() == "config" and len(p.parts) >= 2 and p.parent.name.lower() == "tagame":
                target = p
            elif p.name.lower() == "tagame":
                target = p / "Config"
            elif p.name.lower() in {"rocket league", "rocketleague"}:
                target = p / "TAGame" / "Config"
            else:
                target = p

            if target not in candidates:
                candidates.append(target)

        home = Path.home()
        userprofile = Path(os.environ.get("USERPROFILE", str(home)))

        document_roots = [
            home / "Documents",
            userprofile / "Documents",
            userprofile / "OneDrive" / "Documents",
        ]

        for env_name in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
            env_value = os.environ.get(env_name)
            if env_value:
                document_roots.append(Path(env_value) / "Documents")

        for docs in document_roots:
            add_candidate(docs / "My Games" / "Rocket League" / "TAGame" / "Config")

        # Recherche limitée dans Documents/OneDrive pour les cas où le dossier est déplacé.
        for docs in document_roots:
            try:
                if not docs.exists():
                    continue
                for found in docs.rglob("Rocket League"):
                    add_candidate(found)
                for found in docs.rglob("rocketleague"):
                    add_candidate(found)
            except Exception:
                pass

        # Bibliothèques Steam officielles.
        steam_roots = [
            Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Steam",
            Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Steam",
        ]

        def parse_steam_libraryfolders(vdf_path: Path) -> List[Path]:
            libs: List[Path] = []
            try:
                raw = vdf_path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                return libs
            for match in re.finditer(r'"path"\s*"([^"]+)"', raw):
                value = match.group(1).replace("\\\\", "\\")
                try:
                    libs.append(Path(value))
                except Exception:
                    pass
            return libs

        for steam_root in steam_roots:
            add_candidate(steam_root / "steamapps" / "common" / "rocketleague" / "TAGame" / "Config")
            for lib in parse_steam_libraryfolders(steam_root / "steamapps" / "libraryfolders.vdf"):
                add_candidate(lib / "steamapps" / "common" / "rocketleague" / "TAGame" / "Config")

        # Manifestes Epic : permet de retrouver un chemin Epic déplacé.
        epic_manifest_dirs = [
            Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "Epic" / "EpicGamesLauncher" / "Data" / "Manifests",
        ]
        for manifest_dir in epic_manifest_dirs:
            try:
                if not manifest_dir.exists():
                    continue
                for manifest in manifest_dir.glob("*.item"):
                    try:
                        data = json.loads(manifest.read_text(encoding="utf-8", errors="ignore"))
                    except Exception:
                        continue
                    searchable = " ".join(str(data.get(k, "")) for k in ("AppName", "DisplayName", "CatalogNamespace", "InstallLocation")).lower()
                    if "rocket" in searchable and ("league" in searchable or "rocketleague" in searchable):
                        add_candidate(Path(str(data.get("InstallLocation", ""))) / "TAGame" / "Config")
            except Exception:
                pass

        # Chemins classiques Steam/Epic en dernier recours.
        classic_paths = [
            Path(r"C:\Program Files\Epic Games\rocketleague\TAGame\\Config"),
            Path(r"C:\Program Files (x86)\Epic Games\rocketleague\TAGame\\Config"),
            Path(r"C:\Program Files (x86)\Steam\steamapps\common\rocketleague\TAGame\\Config"),
            Path(r"C:\Program Files\Steam\steamapps\common\rocketleague\TAGame\\Config"),
        ]
        for path in classic_paths:
            add_candidate(path)

        # Garde uniquement les cibles plausibles.
        unique: List[Path] = []
        seen: Set[str] = set()
        for candidate in candidates:
            try:
                resolved_key = str(candidate.resolve()).lower() if candidate.exists() else str(candidate).lower()
            except Exception:
                resolved_key = str(candidate).lower()
            if resolved_key in seen:
                continue
            seen.add(resolved_key)

            # On accepte si TAGame\\Config existe, ou si TAGame existe et Config peut être créé.
            if candidate.exists() or candidate.parent.exists():
                unique.append(candidate)

        return unique

    def _normalize_rl_config_dir(self, folder: str) -> Optional[Path]:
        if not folder:
            return None
        p = Path(folder)
        if p.name.lower() == "config" and p.parent.name.lower() == "tagame":
            return p
        if p.name.lower() == "tagame":
            return p / "Config"
        if p.name.lower() in {"rocket league", "rocketleague"}:
            return p / "TAGame" / "Config"
        if (p / "TAGame" / "Config").exists():
            return p / "TAGame" / "Config"
        return p

    def _remove_managed_statsapi_config(self) -> None:
        ini_raw = str(self.config.get("managed_statsapi_ini", "") or "").strip()
        backup_raw = str(self.config.get("managed_statsapi_backup", "") or "").strip()
        if not ini_raw:
            return

        ini_items = [Path(p) for p in ini_raw.split("|") if p.strip()]
        backup_items = [Path(p) if p.strip() else None for p in backup_raw.split("|")]

        try:
            port = int(self.config.get("statsapi_port", DEFAULT_STATSAPI_PORT))
        except Exception:
            port = DEFAULT_STATSAPI_PORT

        expected = "[TAGame.MatchStatsExporter_TA]\nPacketSendRate=30\n" + f"Port={port}\n"

        for idx, ini_path in enumerate(ini_items):
            backup_path = backup_items[idx] if idx < len(backup_items) else None
            try:
                if backup_path and backup_path.exists():
                    ini_path.parent.mkdir(parents=True, exist_ok=True)
                    ini_path.write_bytes(backup_path.read_bytes())
                elif ini_path.exists() and ini_path.read_text(encoding="utf-8", errors="ignore") == expected:
                    ini_path.unlink()
            except Exception:
                pass

        self.config["managed_statsapi_ini"] = ""
        self.config["managed_statsapi_backup"] = ""

    def _write_statsapi_ini_to_dirs(self, target_dirs: List[Path], port: int) -> Tuple[List[Path], List[str], List[str]]:
        content = "[TAGame.MatchStatsExporter_TA]\nPacketSendRate=30\n" + f"Port={port}\n"
        written: List[Path] = []
        backups: List[str] = []
        errors: List[str] = []

        for target in target_dirs:
            try:
                target.mkdir(parents=True, exist_ok=True)
                ini_path = target / "DefaultStatsAPI.ini"
                backup_path = None

                if ini_path.exists():
                    backup_path = ini_path.with_suffix(ini_path.suffix + f".backup-{int(time.time())}")
                    backup_path.write_bytes(ini_path.read_bytes())

                ini_path.write_text(content, encoding="utf-8")
                written.append(ini_path)
                backups.append(str(backup_path) if backup_path else "")
                self._log(f"StatsAPI auto : écrit {ini_path}")
            except Exception as exc:
                errors.append(f"{target} : {exc}")
                self._log(f"StatsAPI auto : impossible d'écrire {target} : {exc}")

        return written, backups, errors

    def _install_statsapi_config(self) -> None:
        """Configure automatiquement PacketSendRate + Port pour Rocket League."""
        self._save_api_settings()

        try:
            port = int(self.config.get("statsapi_port", DEFAULT_STATSAPI_PORT))
        except Exception:
            port = DEFAULT_STATSAPI_PORT

        target_dirs = self._candidate_rl_config_dirs("all")

        # Si rien n'est détecté, fallback manuel propre.
        if not target_dirs:
            folder = QFileDialog.getExistingDirectory(
                self,
                "Sélectionne Rocket League, TAGame ou TAGame\\Config",
                str(Path.home()),
            )
            normalized = self._normalize_rl_config_dir(folder)
            if normalized:
                target_dirs = [normalized]

        if not target_dirs:
            QMessageBox.warning(
                self,
                "Configuration Rocket League",
                "Aucun dossier Rocket League TAGame\\Config n'a été trouvé.\n"
                "Tu peux relancer le bouton puis sélectionner le dossier manuellement."
            )
            return

        written, backups, errors = self._write_statsapi_ini_to_dirs(target_dirs, port)

        if written:
            self.config["managed_statsapi_ini"] = "|".join(str(p) for p in written)
            self.config["managed_statsapi_backup"] = "|".join(backups)
            self.config["rl_config_auto_paths"] = "|".join(str(p.parent) for p in written)
            self.config.save()

            message = (
                "Configuration Rocket League terminée.\n\n"
                "Fichier écrit automatiquement :\n\n"
                + "\n".join(str(p) for p in written)
                + "\n\nValeurs appliquées :\n"
                + "PacketSendRate=30\n"
                + f"Port={port}\n\n"
                + "Relance Rocket League ensuite."
            )
            if errors:
                message += "\n\nCertains emplacements n'ont pas pu être écrits :\n" + "\n".join(errors[:4])

            QMessageBox.information(self, "Rocket League configuré", message)
        else:
            details = "\n".join(errors[:6]) if errors else "Aucun chemin valide détecté."
            QMessageBox.warning(
                self,
                "Configuration Rocket League impossible",
                "Aucun fichier DefaultStatsAPI.ini n'a été écrit.\n\n" + details
            )

    def _save_api_settings(self) -> None:
        self.config["statsapi_host"] = self.host_edit.text().strip() or "127.0.0.1"
        try:
            self.config["statsapi_port"] = int(self.port_edit.text().strip())
        except ValueError:
            self.config["statsapi_port"] = DEFAULT_STATSAPI_PORT
            self.port_edit.setText(str(DEFAULT_STATSAPI_PORT))
        self._log("Paramètres StatsAPI sauvegardés")
        self.stats_client.reconnect()

    def _regenerate_token(self) -> None:
        self.config["remote_key"] = secrets.token_urlsafe(10)
        self.token_edit.setText(self.config["remote_key"])
        self._refresh_urls()
        self._publish_state()
        self._log("Token remote régénéré")

    def _refresh_urls(self) -> None:
        local = f"http://127.0.0.1:{HTTP_PORT}"
        lan_ip = get_lan_ip()
        key = self.config.get("remote_key", "")
        self.obs_url.setText(f"{local}/overlay")
        if hasattr(self, "showmatch_url"):
            self.showmatch_url.setText(f"{local}/showmatch")
        self.remote_url.setText(f"{local}/remote?key={urllib.parse.quote(key)}")
        self.lan_url.setText(f"http://{lan_ip}:{HTTP_PORT}/remote?key={urllib.parse.quote(key)}")

    def _copy(self, text: str) -> None:
        QGuiApplication.clipboard().setText(text)
        self._log("Copié dans le presse-papiers")


def get_lan_ip() -> str:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
        sock.close()
        return ip
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "127.0.0.1"


LANDING_HTML = r"""
<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>RL Overlay Studio</title><style>
body{margin:0;background:#090b10;color:#f6f8ff;font-family:Inter,Segoe UI,Arial,sans-serif;display:grid;place-items:center;min-height:100vh}.box{width:min(760px,92vw);background:#111521;border:1px solid #1b2030;border-radius:28px;padding:34px;box-shadow:0 30px 90px #0008}.pill{display:inline-flex;background:#1b2030;border-radius:999px;padding:8px 12px;color:#9ca7bc;font-weight:700;font-size:12px}h1{font-size:44px;margin:18px 0 6px}p{color:#b8c1d6;line-height:1.55}.grid{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:24px}a{display:block;text-decoration:none;color:#fff;background:linear-gradient(135deg,#1A8CFF,#A536FF);padding:18px;border-radius:20px;font-weight:900}.muted{background:#1b2030}@media(max-width:700px){.grid{grid-template-columns:1fr}h1{font-size:34px}}
</style></head><body><main class="box"><span class="pill">Serveur local actif</span><h1>RL Overlay Studio</h1><p>Utilise les liens ci-dessous pour OBS et le panneau de contrôle à distance.</p><section class="grid"><a href="{{BASE}}/overlay">Ouvrir l'overlay OBS</a><a class="muted" href="{{BASE}}/remote?key={{KEY}}">Ouvrir le remote</a></section></main></body></html>
"""

OVERLAY_HTML = r"""
<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>RL Overlay</title>
<style>
*{box-sizing:border-box}
:root{--scale:1}
html,body{
  width:100%;
  height:100%;
  margin:0;
  overflow:hidden;
  background:transparent;
  font-family:Inter,"Segoe UI Variable",Segoe UI,Roboto,Arial,sans-serif;
  -webkit-font-smoothing:antialiased;
  text-rendering:geometricPrecision;
  color:white;
}
body{display:grid;place-items:center}
.wrap{transform:scale(var(--scale));transform-origin:center}

.rl-overlay{
  position:relative;
  width:900px;
  max-width:100%;
  min-height:104px;
  display:grid;
  grid-template-columns:repeat(4,1fr);
  align-items:stretch;
  overflow:hidden;
  border-radius:22px;
  background:rgba(13,17,27,.94);
  border:1px solid rgba(120,190,255,.16);
  box-shadow:0 14px 38px rgba(0,0,0,.26), inset 0 1px 0 rgba(255,255,255,.06);
  isolation:isolate;
  transition:opacity .25s ease,transform .25s ease;
}

.rl-overlay.overlay-hidden{
  opacity:0;
  transform:translateY(-12px);
  pointer-events:none;
}

.rl-overlay::before{
  content:"";
  position:absolute;
  inset:0;
  z-index:1;
  opacity:.55;
  pointer-events:none;
  animation:streakInnerGlowBreath 2.8s ease-in-out infinite;
}

.rl-overlay::after{
  content:"";
  position:absolute;
  inset:0;
  z-index:2;
  background:linear-gradient(90deg,rgba(255,255,255,.07),transparent 24%,transparent 76%,rgba(255,255,255,.055));
  pointer-events:none;
}

/* Streak positif dès +1 : lueur interne rouge / orange en respiration */
.streak-positive::before{
  background:
    radial-gradient(circle at 14% 50%,rgba(255,98,18,.34),transparent 34%),
    radial-gradient(circle at 86% 50%,rgba(255,130,26,.26),transparent 36%),
    linear-gradient(90deg,rgba(255,32,14,.34) 0%,rgba(255,116,24,.20) 18%,transparent 42%,transparent 58%,rgba(255,116,24,.20) 82%,rgba(255,32,14,.34) 100%);
  box-shadow:
    inset 0 0 20px rgba(255,42,15,.42),
    inset 0 0 46px rgba(255,116,24,.28),
    inset 0 0 80px rgba(255,76,18,.18);
}

/* Streak négatif dès -1 : lueur interne bleu / blanc en respiration */
.streak-negative::before{
  background:
    radial-gradient(circle at 14% 50%,rgba(84,206,255,.34),transparent 34%),
    radial-gradient(circle at 86% 50%,rgba(255,255,255,.24),transparent 36%),
    linear-gradient(90deg,rgba(40,194,255,.34) 0%,rgba(216,248,255,.18) 20%,transparent 42%,transparent 58%,rgba(216,248,255,.18) 80%,rgba(40,194,255,.34) 100%);
  box-shadow:
    inset 0 0 20px rgba(76,205,255,.42),
    inset 0 0 46px rgba(255,255,255,.22),
    inset 0 0 80px rgba(90,214,255,.18);
}

.streak-neutral::before{
  opacity:0;
  animation:none;
}

.block{
  position:relative;
  z-index:3;
  min-width:0;
  padding:18px 24px;
  display:grid;
  align-content:center;
  gap:10px;
}

.block + .block::before{
  content:"";
  position:absolute;
  left:0;
  top:20px;
  bottom:20px;
  width:1px;
  background:rgba(255,255,255,.12);
}

.label{
  font-size:13px;
  font-weight:850;
  text-transform:uppercase;
  letter-spacing:.145em;
  color:rgba(214,230,255,.72);
  white-space:nowrap;
}

.leader-rank{
  color:#ff9b38;
  font-size:13px;
  font-weight:900;
  letter-spacing:.09em;
  margin-left:8px;
}

.value{
  display:flex;
  align-items:center;
  gap:12px;
  font-size:37px;
  line-height:1;
  font-weight:900;
  letter-spacing:-.045em;
  color:#fff;
  font-variant-numeric:tabular-nums;
  white-space:nowrap;
}

.delta{
  font-size:18px;
  font-weight:900;
  letter-spacing:-.02em;
}

.stat-icon{
  width:36px;
  height:36px;
  display:block;
  flex:0 0 36px;
  align-self:center;
  transform:translateY(-1px);
  filter:drop-shadow(0 0 10px currentColor);
}

.wins .value,
.losses .value,
.streak-block .value{
  align-items:center;
}

.value > .streak-icon:not(svg){
  width:36px;
  height:36px;
  display:inline-flex;
  align-items:center;
  justify-content:center;
  flex:0 0 36px;
}

.value > .streak-icon:not(svg) .stat-icon{
  width:36px;
  height:36px;
  flex-basis:36px;
}

.win-icon{color:#ffd85a}
.loss-icon{color:#ff5656}
.streak-icon{color:#ffffff}
.streak-icon.fire{color:#ff8b2a}
.streak-icon.ice{color:#78dfff}

.delta-positive{color:#3dff8f}
.delta-negative{color:#ff4343}
.delta-neutral{color:rgba(255,255,255,.58)}

.rank-img{
  position:absolute;
  right:18px;
  top:12px;
  width:46px;
  height:46px;
  object-fit:contain;
}

.mmr-missing .rank-img,.mmr-missing .leader-rank{display:none}

.streak-block{overflow:hidden}
.streak-block .label{font-size:14px}
.streak-block .value{font-size:38px}

.hidden{display:none!important}

@keyframes streakInnerGlowBreath{
  0%,100%{
    opacity:.38;
    filter:saturate(1) brightness(.95);
    transform:scale(1);
  }
  50%{
    opacity:.86;
    filter:saturate(1.28) brightness(1.12);
    transform:scale(1.015);
  }
}

@media (max-width:760px){
  .rl-overlay{grid-template-columns:repeat(2,1fr)}
  .block + .block::before{display:none}
}
</style>
</head>
<body>
<div class="wrap">
  <section id="overlay" class="rl-overlay streak-neutral mmr-missing">
    <div class="block wins">
      <div class="label">Wins</div>
      <div class="value"><span id="wins">0</span><svg class="stat-icon win-icon" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M18 4h2.5A1.5 1.5 0 0 1 22 5.5V7a5 5 0 0 1-4.44 4.97A6.04 6.04 0 0 1 13.5 16v2H17a1 1 0 1 1 0 2H7a1 1 0 1 1 0-2h3.5v-2a6.04 6.04 0 0 1-4.06-4.03A5 5 0 0 1 2 7V5.5A1.5 1.5 0 0 1 3.5 4H6V3.5A1.5 1.5 0 0 1 7.5 2h9A1.5 1.5 0 0 1 18 3.5V4Zm0 2v3.8A3 3 0 0 0 20 7V6h-2ZM4 6v1a3 3 0 0 0 2 2.8V6H4Z"/></svg></div>
    </div>

    <div class="block losses">
      <div class="label">Losses</div>
      <div class="value"><span id="losses">0</span><svg class="stat-icon loss-icon" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M6.35 4.93a1 1 0 0 1 1.42 0L12 9.17l4.23-4.24a1 1 0 1 1 1.42 1.42L13.41 10.6l4.24 4.23a1 1 0 0 1-1.42 1.42L12 12.01l-4.23 4.24a1 1 0 1 1-1.42-1.42l4.24-4.23-4.24-4.25a1 1 0 0 1 0-1.42Z"/></svg></div>
    </div>

    <div id="mmrStat" class="block mmr">
      <img id="rankLogo" class="rank-img" src="" alt="" />
      <div class="label">MMR <span id="leaderRank" class="leader-rank"></span></div>
      <div class="value"><span id="mmr">—</span><span id="delta" class="delta delta-neutral">0</span></div>
    </div>

    <div class="block streak-block">
      <div class="label">Streak</div>
      <div class="value"><span id="streak">0</span><span id="streakIcon" class="streak-icon"></span></div>
    </div>
  </section>
</div>

<script>
const $ = id => document.getElementById(id);
let last = {};
let state = null;
let ws = null;
let reconnectTimer = null;
let lastMessageAt = 0;

function wsUrl(){
  const host = location.hostname || '127.0.0.1';
  return `ws://${host}:49125/ws`;
}

function bump(el, value){
  if(!el) return;
  if(String(last[el.id]) !== String(value)){
    el.animate(
      [{transform:'scale(1)'},{transform:'scale(1.06)'},{transform:'scale(1)'}],
      {duration:260,easing:'ease'}
    );
    last[el.id] = value;
  }
}

function iconSvg(type){
  if(type === 'fire'){
    return `<svg class="stat-icon streak-icon fire" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M12.3 22C8.5 22 5.5 19.25 5.5 15.35c0-2.2 1.2-4.18 2.88-5.54.62-.5 1.4.15 1.12.9-.18.5-.28 1.02-.28 1.53 0 1.12.43 2.1 1.12 2.72-.17-1.95.48-3.7 1.72-5.35 1.14-1.52 1.5-3.28.84-5.18-.23-.67.48-1.22 1.08-.84 2.9 1.85 4.52 4.95 4.52 8.42 0 5.08-2.88 9.99-6.2 9.99Z"/></svg>`;
  }
  if(type === 'ice'){
    return `<svg class="stat-icon streak-icon ice" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M12 2a1 1 0 0 1 1 1v4.06l3.52-2.03a1 1 0 0 1 1 1.74L14 8.8l3.52 2.03a1 1 0 0 1-1 1.74L13 10.54v4.06a1 1 0 1 1-2 0v-4.06l-3.52 2.03a1 1 0 0 1-1-1.74L10 8.8 6.48 6.77a1 1 0 1 1 1-1.74L11 7.06V3a1 1 0 0 1 1-1Zm0 14.2a1 1 0 0 1 1 1V21a1 1 0 1 1-2 0v-3.8a1 1 0 0 1 1-1Z"/></svg>`;
  }
  return '';
}

function applyTheme(t = {}){
  document.documentElement.style.setProperty('--scale', (t.scale ?? 100) / 100);
  $('mmrStat').classList.toggle('hidden', t.show_mmr === false);
  const overlay = $('overlay');
  overlay.classList.toggle('no-anim', t.animate === false);
}

function render(s){
  if(!s) return;
  state = s;
  lastMessageAt = Date.now();

  const t = s.theme || {};
  applyTheme(t);

  const overlay = $('overlay');
  const active = s.main_overlay_enabled !== false && s.main_overlay_visible !== false;
  overlay.classList.toggle('overlay-hidden', !active);
  if(!active) return;

  const wins = Number(s.wins || 0);
  const losses = Number(s.losses || 0);

  $('wins').textContent = wins;
  bump($('wins'), wins);

  $('losses').textContent = losses;
  bump($('losses'), losses);

  const hasMmr = s.mmr !== null && s.mmr !== undefined && s.mmr !== '' && Number(s.mmr) > 0;
  const mmrVal = hasMmr ? String(s.mmr) : '—';
  $('mmr').textContent = mmrVal;
  bump($('mmr'), mmrVal);

  const d = Number(s.mmr_change || 0);
  $('delta').textContent = d > 0 ? `+${d}` : d < 0 ? `${d}` : '0';
  $('delta').className = 'delta ' + (d > 0 ? 'delta-positive' : d < 0 ? 'delta-negative' : 'delta-neutral');

  overlay.classList.remove('streak-positive','streak-negative','streak-neutral','mmr-missing');

  let streakText = '0';
  let streakIcon = '';
  const streakVal = Number(s.streak_val || 0);

  if(streakVal > 0 && s.streak_type === 'win'){
    streakText = `+${streakVal}`;
    streakIcon = 'fire';
    overlay.classList.add('streak-positive');
  } else if(streakVal > 0 && s.streak_type === 'loss'){
    streakText = `-${streakVal}`;
    streakIcon = 'ice';
    overlay.classList.add('streak-negative');
  } else {
    overlay.classList.add('streak-neutral');
  }

  $('streak').textContent = streakText;
  const streakIconEl = $('streakIcon');
  streakIconEl.innerHTML = iconSvg(streakIcon);
  streakIconEl.className = 'streak-icon ' + (streakIcon || '');
  bump($('streak'), streakText);

  const leaderRank = $('leaderRank');
  const leaderDigits = String(s.leader_rank || '').replace(/\D/g, '');
  const leaderNumber = leaderDigits ? Number(leaderDigits) : 0;
  if(hasMmr && leaderNumber >= 1 && leaderNumber <= 999){
    leaderRank.textContent = `Top ${leaderNumber}`;
  } else {
    leaderRank.textContent = '';
  }

  const rankLogo = $('rankLogo');
  if(hasMmr && s.rank_logo){
    rankLogo.src = s.rank_logo;
    rankLogo.alt = s.rank || '';
  } else {
    rankLogo.removeAttribute('src');
    rankLogo.alt = '';
    overlay.classList.add('mmr-missing');
  }
}

async function pollState(){
  try{
    const response = await fetch('/api/state?ts=' + Date.now(), {cache:'no-store'});
    if(response.ok) render(await response.json());
  }catch(err){}
}

function connect(){
  clearTimeout(reconnectTimer);
  try{
    ws = new WebSocket(wsUrl());
  }catch(err){
    reconnectTimer = setTimeout(connect, 1200);
    return;
  }
  ws.onopen = () => {
    ws.send(JSON.stringify({type:'subscribe',client:'obs-overlay'}));
    pollState();
  };
  ws.onmessage = e => {
    try{
      const message = JSON.parse(e.data);
      if(message.state) render(message.state);
    }catch(err){}
  };
  ws.onclose = () => { reconnectTimer = setTimeout(connect, 1200); };
  ws.onerror = () => { try{ ws.close(); }catch(err){} };
}

connect();
pollState();
setInterval(() => {
  if(ws && ws.readyState === WebSocket.OPEN){
    try{ ws.send(JSON.stringify({type:'ping',client:'obs-overlay'})); }catch(err){}
  }
  if(!state || Date.now() - lastMessageAt > 1800) pollState();
}, 1000);
</script>
</body>
</html>
"""


SHOWMATCH_HTML = r"""
<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>RL Showmatch BO Overlay</title>
<style>
:root{--blue:#1A8CFF;--orange:#FF6B00;--text:#F6F8FF;--muted:#AAB5CA;--glass:rgba(5,10,18,.54)}
*{box-sizing:border-box}html,body{width:100%;height:100%;margin:0;overflow:hidden;background:rgba(0,0,0,0)!important;font-family:Inter,Segoe UI,Montserrat,Arial,sans-serif;color:var(--text)}body{display:grid;place-items:start center;padding-top:6px}.showmatch{min-width:760px;max-width:980px;height:50px;display:flex;align-items:center;justify-content:center;gap:16px;padding:5px 18px;border-radius:0;background:transparent;border:0;box-shadow:none;backdrop-filter:none;transition:opacity .25s ease,transform .25s ease}.showmatch.hidden{opacity:0;transform:translateY(-12px)}.score-wrap{width:92px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:2px;text-align:center;text-shadow:0 2px 12px rgba(0,0,0,.95)}.score-name{max-width:110px;font-size:10px;line-height:1;font-weight:1000;text-transform:uppercase;letter-spacing:.65px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;opacity:.92}.team-blue{color:#BFEFFF}.team-orange{color:#FFE0B4}.score-wrap.team-blue .score{color:#63D5FF}.score-wrap.team-orange .score{color:#FFB248}.center{min-width:145px;text-align:center}.game{font-size:12px;font-weight:1000;letter-spacing:1px;text-transform:uppercase;color:#EAF2FF;text-shadow:0 2px 12px rgba(0,0,0,.95),0 0 18px rgba(26,140,255,.35)}.status{font-size:9px;font-weight:900;color:#DDE7FF;text-transform:uppercase;letter-spacing:1.2px;margin-top:1px;text-shadow:0 2px 10px rgba(0,0,0,.95)}.bars{display:flex;gap:8px;align-items:center}.bar{width:12px;height:12px;border-radius:50%;background:rgba(255,255,255,.28);box-shadow:inset 0 0 0 1px rgba(255,255,255,.16);overflow:hidden}.bar.on.blue{background:linear-gradient(135deg,#1A8CFF,#55D7FF);box-shadow:0 0 18px rgba(26,140,255,.82)}.bar.on.orange{background:linear-gradient(135deg,#FF6B00,#FFD24A);box-shadow:0 0 18px rgba(255,107,0,.82)}.score{font-size:18px;font-weight:1000;min-width:20px;text-align:center;text-shadow:0 2px 12px rgba(0,0,0,.95)}@media(max-width:800px){.showmatch{min-width:96vw;gap:10px}.score-wrap{width:68px}.score-name{font-size:9px;max-width:76px}.bar{width:10px;height:10px}}
</style>
</head>
<body>
<section id="box" class="showmatch hidden">
  <div id="leftWrap" class="score-wrap team-blue"><div class="score" id="leftScore">0</div><div id="leftName" class="score-name">Player</div></div>
  <div class="bars" id="leftBars"></div>
  <div class="center"><div id="gameLabel" class="game">GAME 1 - BO5</div><div id="status" class="status">Showmatch 1v1</div></div>
  <div class="bars" id="rightBars"></div>
  <div id="rightWrap" class="score-wrap team-orange"><div class="score" id="rightScore">0</div><div id="rightName" class="score-name">Opponent</div></div>
</section>
<script>
const $=id=>document.getElementById(id);let ws=null,reconnectTimer=null,lastMessageAt=0,state=null;
function wsUrl(){const host=location.hostname||'127.0.0.1';return `ws://${host}:49125/ws`;}
function teamColor(team,fallback){return Number(team)===1?'orange':Number(team)===0?'blue':(fallback||'blue');}
function applyScoreClass(el,color){if(!el)return;el.className='score-wrap team-'+color;}
function bars(container,count,score,side){container.innerHTML='';for(let i=0;i<count;i++){const b=document.createElement('span');b.className='bar '+(i<score?'on '+side:'');container.appendChild(b);}}
function render(s){state=s;lastMessageAt=Date.now();const sm=s.showmatch||{};const box=$('box');const active=!!sm.enabled && !!sm.visible;box.classList.toggle('hidden',!active);if(!active)return;const target=Number(sm.target||Math.floor((sm.bo||5)/2)+1);const leftColor=sm.left_color||teamColor(sm.left_team,'blue');const rightColor=sm.right_color||teamColor(sm.right_team,leftColor==='blue'?'orange':'blue');applyScoreClass($('leftWrap'),leftColor);applyScoreClass($('rightWrap'),rightColor);$('leftName').textContent=sm.left_name||s.player||'Player';$('rightName').textContent=sm.right_name||'Opponent';$('leftScore').textContent=sm.left_score||0;$('rightScore').textContent=sm.right_score||0;$('gameLabel').textContent=sm.game_label||`GAME ${Math.min((sm.left_score||0)+(sm.right_score||0)+1,sm.bo||5)} - BO${sm.bo||5}`;$('status').textContent=sm.completed?(sm.left_score>sm.right_score?`${sm.left_name||'Player'} gagne la série`:`${sm.right_name||'Opponent'} gagne la série`):`Showmatch BO${sm.bo||5}`;bars($('leftBars'),target,Number(sm.left_score||0),leftColor);bars($('rightBars'),target,Number(sm.right_score||0),rightColor);}
async function pollState(){try{const r=await fetch('/api/state?ts='+Date.now(),{cache:'no-store'});if(r.ok)render(await r.json());}catch(e){}}
function connect(){clearTimeout(reconnectTimer);try{ws=new WebSocket(wsUrl());}catch(e){reconnectTimer=setTimeout(connect,1200);return;}ws.onopen=()=>{ws.send(JSON.stringify({type:'subscribe',client:'showmatch-overlay'}));pollState();};ws.onmessage=e=>{try{const m=JSON.parse(e.data);if(m.state)render(m.state);}catch(err){}};ws.onclose=()=>{reconnectTimer=setTimeout(connect,1200);};ws.onerror=()=>{try{ws.close();}catch(e){}};}
connect();pollState();setInterval(()=>{if(ws&&ws.readyState===WebSocket.OPEN){try{ws.send(JSON.stringify({type:'ping',client:'showmatch-overlay'}));}catch(e){}}if(!state||Date.now()-lastMessageAt>1800)pollState();},1000);
</script>
</body>
</html>
"""

REMOTE_HTML = r"""
<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>RL Overlay Remote</title>
<style>
:root{--bg:#0b0f17;--card:#131a26;--text:#eef3ff;--muted:#97a4bf;--blue:#12a7ff;--orange:#ff7a18;--purple:#8e5cff;--green:#3ae08a}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font-family:Inter,Segoe UI,Montserrat,Arial,sans-serif}
.app{max-width:980px;margin:0 auto;padding:18px}
.top{display:flex;align-items:center;gap:12px;margin-bottom:14px}
.logo{width:40px;height:40px;border-radius:14px;background:#131a26;display:grid;place-items:center;color:var(--blue);font-weight:1000}
.status{color:var(--muted);font-size:13px}
.grid{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:10px;margin-bottom:12px}
.card{background:var(--card);border-radius:16px;padding:12px}
.label{color:var(--muted);font-size:10px;text-transform:uppercase;letter-spacing:1.2px;font-weight:900}
.value{font-size:24px;font-weight:1000;margin-top:6px;white-space:nowrap}
.controls,.panel{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
.btn{background:#20283a;color:var(--text);border:none;border-radius:13px;padding:10px 12px;font-weight:850;cursor:pointer}
.btn.win{background:var(--blue)}.btn.loss{background:var(--orange)}.btn.purple{background:var(--purple)}.btn.green{background:var(--green);color:#07101a}
.stack{display:grid;gap:9px}.row{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px}
.toggles{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px;margin-top:9px}
label{display:grid;gap:5px;color:var(--muted);font-size:12px;font-weight:750}
input,select{width:100%;background:#0f1521;color:var(--text);border:none;border-radius:12px;padding:10px 12px}
.showmatch-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:9px}
@media(max-width:760px){.grid,.controls,.panel,.row,.toggles,.showmatch-grid{grid-template-columns:1fr}}
</style>
</head>
<body>
<main class="app">
  <header class="top">
    <div class="logo">RL</div>
    <div>
      <h1 style="margin:0;font-size:22px">RL Overlay Remote</h1>
      <div id="status" class="status">Connexion…</div>
    </div>
  </header>

  <section class="grid">
    <div class="card"><div class="label">Wins</div><div id="wins" class="value">0</div></div>
    <div class="card"><div class="label">Losses</div><div id="losses" class="value">0</div></div>
    <div class="card"><div class="label">Streak</div><div id="streakVal" class="value">—</div></div>
    <div class="card"><div class="label">MMR</div><div id="mmrVal" class="value">—</div></div>
    <div class="card"><div class="label">Score</div><div id="scoreVal" class="value">0 - 0</div></div>
  </section>

  <section class="controls">
    <button class="btn win" onclick="cmd('add_result','win')">+ Win</button>
    <button class="btn loss" onclick="cmd('add_result','loss')">+ Loss</button>
    <button class="btn" onclick="cmd('remove_result','win')">− Win</button>
    <button class="btn" onclick="cmd('remove_result','loss')">− Loss</button>
    <button class="btn purple" onclick="cmd('reset')">Reset session</button>
  </section>

  <section class="panel" style="margin-top:12px">
    <div class="card stack">
      <div class="label">Overlay principal</div>
      <label>Scale<input id="scale" type="range" min="60" max="180" oninput="theme({scale:Number(this.value)})"></label>
      <div class="toggles">
        <label><input type="checkbox" id="show_mmr" onchange="theme({show_mmr:this.checked})"> Afficher MMR</label>
        <label><input type="checkbox" id="animate" onchange="theme({animate:this.checked})"> Dégradé animé</label>
      </div>
    </div>

    <div class="card stack">
      <div class="label">MMR / Playlist</div>
      <label>Playlist<select id="playlist" onchange="cmd('select_playlist',this.value)"><option>1v1</option><option>2v2</option><option>3v3</option></select></label>
      <div class="row">
        <label>MMR<input id="mmr" inputmode="numeric" placeholder="1432"></label>
        <label>Rank<input id="rank" placeholder="GC1 Div 2"></label>
      </div>
      <button class="btn win" onclick="setMMR()">Mettre à jour MMR</button>
    </div>
  </section>

  <section class="card stack" style="margin-top:12px">
    <div class="label">SHOWMATCH</div>
    <div id="showmatchStatus" class="status">En attente</div>
    <div class="showmatch-grid">
      <button class="btn green" onclick="toggleShowmatch()">Afficher / masquer</button>
      <select id="showmatchBo" onchange="cmd('showmatch_bo',Number(this.value))"><option value="3">BO3</option><option value="5">BO5</option><option value="7">BO7</option><option value="9">BO9</option></select>
      <button class="btn win" onclick="cmd('showmatch_add_left')">+ Gauche</button>
      <button class="btn loss" onclick="cmd('showmatch_add_right')">+ Droite</button>
      <button class="btn" onclick="cmd('showmatch_undo')">Annuler game</button>
      <button class="btn purple" onclick="cmd('showmatch_reset')">Reset BO</button>
      <input id="showmatchGame" type="number" min="1" max="9" value="1" onchange="cmd('showmatch_current_game',Number(this.value))">
      <button class="btn" onclick="cmd('simulate_update')">Test API</button>
    </div>
  </section>
</main>

<script>
const $=id=>document.getElementById(id);
let ws=null;
let lastMessageAt=0;
let lastTheme={};
let showmatchEnabled=false;

function key(){return new URLSearchParams(location.search).get('key')||'';}
function send(payload){
  payload.key=key();
  if(ws&&ws.readyState===WebSocket.OPEN){
    ws.send(JSON.stringify(payload));
  } else {
    fetch('/api/command',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}).catch(()=>{});
  }
}
function cmd(action,value){send({action,value});}
function theme(patch){send({action:'set_theme',patch});}
function setMMR(){send({action:'set_mmr',playlist:$('playlist').value,mmr:$('mmr').value,rank:$('rank').value});}
function toggleShowmatch(){send({action:'showmatch_enabled',value:!showmatchEnabled});}

async function pollState(){
  try{
    const r=await fetch('/api/state?ts='+Date.now(),{cache:'no-store'});
    if(r.ok) render(await r.json());
  }catch(err){}
}

function connect(){
  const host=location.hostname||'127.0.0.1';
  try{ws=new WebSocket(`ws://${host}:49125/ws`);}catch(err){setTimeout(connect,1200);return;}
  ws.onopen=()=>{try{ws.send(JSON.stringify({type:'subscribe',client:'remote'}));}catch(err){} pollState();};
  ws.onmessage=e=>{try{const m=JSON.parse(e.data); if(m.state) render(m.state);}catch(err){}};
  ws.onclose=()=>setTimeout(connect,1200);
  ws.onerror=()=>{try{ws.close();}catch(err){}};
}

function render(s){
  lastMessageAt=Date.now();
  $('wins').textContent=s.wins||0;
  $('losses').textContent=s.losses||0;
  const sv=s.streak_val||0, st=s.streak_type||'';
  $('streakVal').textContent=sv?((st==='win'?'+':'-')+sv+(st==='win'?'W':'L')):'—';
  const delta=Number(s.mmr_change||0);
  $('mmrVal').textContent=s.mmr?String(s.mmr)+(delta?` (${delta>0?'+':''}${delta})`:''):'—';
  const score=s.score||{};
  $('scoreVal').textContent=(score.me||0)+' - '+(score.opponent||0);
  $('status').textContent=(s.connection==='connected'?'API connectée':'API off')+' · '+(s.tracker_status||'API RLS en attente');

  const t=s.theme||{};
  if(JSON.stringify(t)!==JSON.stringify(lastTheme)){
    lastTheme=t;
    $('scale').value=t.scale||100;
    $('show_mmr').checked=t.show_mmr!==false;
    $('animate').checked=t.animate!==false;
  }
  $('playlist').value=s.playlist||'3v3';
  $('mmr').placeholder=s.mmr||'1432';
  $('rank').placeholder=s.rank||'Rank';

  const sm=s.showmatch||{};
  showmatchEnabled=!!sm.enabled;
  $('showmatchBo').value=String(sm.bo||5);
  $('showmatchGame').value=String(sm.current_game||1);
  $('showmatchStatus').textContent=(showmatchEnabled?'Visible':'Masqué')+' · '+(sm.game_label||'BO')+' · '+(sm.left_score||0)+' - '+(sm.right_score||0);
}

connect();
pollState();
setInterval(()=>{
  if(ws&&ws.readyState===WebSocket.OPEN){
    try{ws.send(JSON.stringify({type:'ping',client:'remote'}));}catch(err){}
  }
  if(Date.now()-lastMessageAt>1800) pollState();
},1000);
</script>
</body>
</html>
"""

def main() -> None:
    # Aucun crash.log n'est ouvert/créé au lancement.
    # Les logs crash sont écrits uniquement si une vraie erreur arrive.

    def _safe_excepthook(exc_type: Any, exc: BaseException, tb: Any) -> None:
        try:
            CRASH_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with (CRASH_LOG_PATH).open("a", encoding="utf-8") as f:
                f.write(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] Unhandled exception\n")
                traceback.print_exception(exc_type, exc, tb, file=f)
        except Exception:
            pass

    def _safe_threading_excepthook(args: Any) -> None:
        try:
            CRASH_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with (CRASH_LOG_PATH).open("a", encoding="utf-8") as f:
                f.write(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] Thread exception: {getattr(args, 'thread', None)}\n")
                traceback.print_exception(args.exc_type, args.exc_value, args.exc_traceback, file=f)
        except Exception:
            pass

    sys.excepthook = _safe_excepthook
    try:
        threading.excepthook = _safe_threading_excepthook
    except Exception:
        pass
    app = QApplication(sys.argv)
    # Empêche Qt de quitter si une fenêtre secondaire se ferme/se masque pendant un Alt-Tab ou un changement de focus.
    app.setQuitOnLastWindowClosed(False)
    icon_path = APP_ICON_PNG if APP_ICON_PNG.exists() else APP_ICON_ICO
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    app.setStyle("Fusion")
    app.setStyleSheet(APP_STYLE)
    font = QFont("Segoe UI", 10)
    app.setFont(font)
    win = RLOverlayStudio()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    try:
        main()
    except Exception:
        error_path = CRASH_LOG_PATH
        try:
            error_path.parent.mkdir(parents=True, exist_ok=True)
            with error_path.open("w", encoding="utf-8") as f:
                f.write(traceback.format_exc())
        except Exception:
            pass
        raise
