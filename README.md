# RL Overlay Studio

### Rocket League overlays for players, content creators and streamers

**Beta 8.46 · Windows 10/11 · OBS · TikTok Live Studio · In-Game · Discord**

[![Version](https://img.shields.io/badge/version-Beta%208.46-7C5CFC?style=for-the-badge)](https://github.com/Lukiseven/RL-Overlay-Studio/releases/latest) ![Windows](https://img.shields.io/badge/Windows-10%20%2F%2011-0078D4?style=for-the-badge&logo=windows11&logoColor=white) ![Public audit](https://img.shields.io/badge/source-public%20audit-22C55E?style=for-the-badge)

**[Download the latest release](https://github.com/Lukiseven/RL-Overlay-Studio/releases/latest)** · **[Join our Discord](https://discord.gg/Qed73c5kd9)** · **[Source audit scope](AUDIT_SCOPE.md)**

RL Overlay Studio is an external Windows companion for Rocket League. It tracks session activity and displays rank/MMR, wins, losses, streaks and match information through customizable overlays. Stream to OBS or TikTok Live Studio, or use optional In-Game components. The application does **not** inject code into Rocket League.

> **About these screenshots:** The streamer overlays, Players MMR and Showmatch are flattened Chromium renders of the original Beta 8.46 HTML/CSS/JavaScript templates. Desktop application pages and Dock panels are accurate **HTML presentations reconstructed from the PyQt6 source**, not direct Windows application captures. The corrected Dock geometry follows the original uncompiled Beta 8.46 source. Player names, scores, MMR and ranks are sample values. All screenshots are static, with no live API requests.

---

## 01 · Application overview

![RL Overlay Studio Beta 8.46 — complete desktop application and live overlay preview](media/readme/captures/application_overview.png)

### Dashboard

Session wins/losses, current streak, rank and MMR, match status, connection indicators and quick actions.

![Dashboard: session statistics, rank and quick actions](media/readme/captures/application_ui_00_dashboard.png)

### Application pages and configuration

The desktop interface includes OBS/TikTok Live Studio controls, session management, overlay options and diagnostics. The source screenshots preserve the layout and controls represented in the Beta 8.46 application.

**OBS and TikTok Live Studio configuration**

![OBS and TikTok Live Studio configuration](media/readme/captures/application_ui_01_overlay_obs_tiktok.png)

**Session management and saved statistics**

![Session management and saved statistics](media/readme/captures/application_ui_02_sessions.png)

**Overlay settings and customization**

![Overlay settings and customization](media/readme/captures/application_ui_03_options_overlay.png)

**Application settings and diagnostics**

![Application settings and diagnostics](media/readme/captures/application_ui_04_reglages.png)

---

## 02 · Streaming overlays

Each layout targets a different on-stream arrangement while presenting the Rocket League session. Compact layouts and the Rank Tower are Premium presentations.

### Classic Banner default view

![Classic Banner default view](media/readme/captures/overlay_banner_00_neutre.png)

### Compact Vertical premium layout

![Compact Vertical premium layout](media/readme/captures/overlay_vertical_00_vertical.png)

### Compact Horizontal premium layout

![Compact Horizontal premium layout](media/readme/captures/overlay_horizontal_00_horizontal.png)

### Premium Rank Tower

![Premium Rank Tower](media/readme/captures/premium_rank_tower_00_tour_premium.png)

**Supported information:** current playlist and rank/division, MMR, wins, losses, streaks, Top Rank (when applicable) and match events.

---

## 03 · Classic Banner — states and effects

The banner can represent match events, rank changes, Top Rank levels and MMR pop-ups. The following images are **individual static captures of demonstration states**, not animated playback. Effects that depend on timing may look identical in a still frame; for example, Freeplay/private context or Rank Up can change underlying behavior without a permanently different visual.

### Session & streaks

| | |
| :---: | :---: |
| ![Neutral — Ranked session](media/readme/captures/overlay_banner_00_neutre.png) | ![Win streak](media/readme/captures/overlay_banner_01_win_streak.png) |
| ![Loss streak](media/readme/captures/overlay_banner_02_loss_streak.png) | ![Rank Up example](media/readme/captures/overlay_banner_09_rank_up.png) |
| ![Rank Down example](media/readme/captures/overlay_banner_10_rank_down.png) | ![Freeplay context](media/readme/captures/overlay_banner_15_freeplay.png) |
| ![Private match context](media/readme/captures/overlay_banner_16_partie_privee.png) | ![Direct In-Game context](media/readme/captures/overlay_banner_17_direct_in_game.png) |

### Top Rank & rank availability

- **Top 1–5:** red.
- **Top 6–100:** gold.
- **Top 101–200:** silver.
- **Outside Top 200:** Top Rank hidden.

| | |
| :---: | :---: |
| ![Top Rank #1–5 (red)](media/readme/captures/overlay_banner_03_top_15_rouge.png) | ![Top Rank #6–100 (gold)](media/readme/captures/overlay_banner_04_top_6100_or.png) |
| ![Top Rank #101–200 (silver)](media/readme/captures/overlay_banner_05_top_101200_argent.png) | ![Top Rank hidden](media/readme/captures/overlay_banner_06_sans_top_rank.png) |
| ![MMR unavailable](media/readme/captures/overlay_banner_07_mmr_absent.png) | ![Supersonic Legend](media/readme/captures/overlay_banner_08_supersonic_legend.png) |

### Positionable MMR pop-ups

| | |
| :---: | :---: |
| ![MMR popup — bottom](media/readme/captures/overlay_banner_11_pop_up_en_bas.png) | ![MMR popup — top](media/readme/captures/overlay_banner_12_pop_up_en_haut.png) |
| ![MMR popup — left](media/readme/captures/overlay_banner_13_pop_up_a_gauche.png) | ![MMR popup — right](media/readme/captures/overlay_banner_14_pop_up_a_droite.png) |

**These are different presentation states of the original overlay renderer**, displayed without exposing its proprietary HTML templates or protected MMR/ranking implementation.

---

## 04 · Players MMR (In-Game)

Displays the other players' platform markers, ranks, divisions and available MMR information, with positioning and player-departure states.

### Players MMR — right-aligned

![Players MMR — right-aligned](media/readme/captures/players_mmr_00_droite.png)

### Players MMR — left-aligned

![Players MMR — left-aligned](media/readme/captures/players_mmr_01_gauche.png)

### Players MMR — player departed

![Players MMR — player departed](media/readme/captures/players_mmr_02_joueur_parti.png)

---

## 05 · Showmatch — competitive series

Showmatch presentation supports **BO3, BO5, BO7 and BO9**, series scores, current game and completed-series winner states. The screenshots below show selected source-rendered states.

| | |
| :---: | :---: |
| ![Showmatch BO5 — live series](media/readme/captures/showmatch_00_bo5_live.png) | ![Showmatch BO7 — live series](media/readme/captures/showmatch_01_bo7_live.png) |
| ![Showmatch — left side wins](media/readme/captures/showmatch_02_victoire_gauche.png) | ![Showmatch — right side wins](media/readme/captures/showmatch_03_victoire_droite.png) |

---

## 06 · In-Game Dock — original Beta 8.46 geometry

The following **seven static presentations** retain the corrected radial-button positions from the uncompiled Beta 8.46 `InGameQuickMenu` source rather than approximated semicircle positions.

- **Main Menu:** 60 × 60 px.
- **Five categories:** 48 × 48 px, radius 108 px; angles **118°, 149°, 180°, 211° and 242°**.
- **Show Application:** 36 × 36 px, vertically aligned above Menu, with an 8 px gap.
- **Discord:** 36 × 36 px, vertically aligned below Menu, with an 8 px gap.
- **Category panel:** 452 × 536 px, with an 18 px horizontal gap to the nearest radial category button.

| | |
| :---: | :---: |
| ![Dock — Actions](media/readme/dock_actions.png) | ![Dock — Overlay](media/readme/dock_overlay.png) |
| ![Dock — Appearance](media/readme/dock_appearance.png) | ![Dock — Players MMR](media/readme/dock_players.png) |
| ![Dock — Sessions](media/readme/dock_sessions.png) | ![Dock — Premium unavailable](media/readme/dock_premium_off.png) |

**Dock closed**

![Dock — collapsed](media/readme/dock_closed.png)

The category views are **Actions, Overlay, Appearance, Players MMR and Sessions**, plus the Premium-unavailable and collapsed presentations. No animated GIF, interactive demo or external gallery is required to view them.

---

## 07 · Capabilities

- **Session tracking:** wins, losses, streaks, ranked and selected casual handling, match-state detection, saved sessions.
- **Overlays:** Classic Banner, Compact Vertical, Compact Horizontal, Premium Rank Tower, Players MMR and Showmatch.
- **Streaming:** OBS/TikTok Browser Sources and network relay support.
- **In-Game:** optional radial Dock, status displays, configurable visibility and controls.
- **Access:** Discord authentication and Premium feature gating.
- **Localization:** French and English.
- **Updates & diagnostics:** GitHub release checks, local logs and connection status indicators.

---

## 08 · Technical architecture

```mermaid
flowchart LR
    RL["Rocket League"] -->|"StatsAPI / local"| APP["RL Overlay Studio"]
    LOG["Rocket League logs"] --> APP
    APP -->|"Protected MMR requests"| PRIVATE["Private MMR service"]
    APP -->|"Local HTTP / WebSocket"| LOCAL["Local overlays"]
    APP -->|"Authentication"| DISCORD["Discord"]
    APP -->|"Network relay"| STREAM["OBS / TikTok Live Studio"]
```

The app is built with **Python, PyQt6, PyQt6 WebEngine, HTML/CSS/JavaScript, local HTTP/WebSockets, and Discord OAuth**.

### Public audit source

This repository provides a **sanitized, non-buildable security-review copy derived from Beta 8.46** in [`src/`](src/). It exposes the application's high-level structure, local networking, diagnostics, configuration, authentication flow and update architecture while withholding proprietary ranking/MMR internals, private endpoints, keys and production artwork.

- [Audit scope](AUDIT_SCOPE.md)
- [Redactions and exclusions](REDACTIONS.md)
- [Third-party dependencies](THIRD_PARTY_DEPENDENCIES.md)
- [Security policy](SECURITY.md)
- [Audit-use license](LICENSE.txt)

The published screenshots are flattened, demonstration-only presentations. Their inclusion does not provide complete or reproducible production source code.

---

## 09 · Beta 8.46 release integrity

[Release verification instructions](RELEASE_VERIFICATION.md)

```text
ZIP SHA-256: fcced4298a0952b109b4e657c82aa1c79c911f9875a43cc7974e862731adb4f6
EXE SHA-256: c7aaea996bbfafb9fe1c2aa11e2f8cd75a8a4557c7c847cc1dfc2418fb9f7e87
```

---

**RL Overlay Studio · Beta 8.46** — Built for the Rocket League community.

[Latest release](https://github.com/Lukiseven/RL-Overlay-Studio/releases/latest) · [Discord](https://discord.gg/Qed73c5kd9)
