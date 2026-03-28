Chronicles of the Forgotten Realm — Engine Architecture & Design Document

Version: 1.0.0 (Pre-Build Final)
Status: Architecture Locked. Ready for Phase 1 Schema Definition.
1. Project Overview

What is this?
A fully automated, multi-agent TTRPG (Tabletop Role-Playing Game) engine. It acts as an unbiased, highly immersive Dungeon Master capable of running a solo D&D 5e campaign.

The Core Philosophy:
Traditional LLM chatbots fail at running RPGs due to context rot, rate limits, and hallucinated mechanics. This engine solves these issues by decoupling the "Storyteller" from the "Game Logic." It uses a heavy cloud LLM strictly for narrative generation, while a swarm of lightweight, local LLMs and Python scripts handle the math, rules, memory, and safety in the background.
2. System Architecture & Tech Stack

The engine operates on a highly responsive, event-driven architecture (Pub/Sub model) to ensure zero UI latency.

    Frontend: React (via Vite) + Tailwind CSS. Handles the dynamic UI, dice widgets, and persistent character sheets.

    Backend: FastAPI (Python). Manages the Event Bus, WebSockets for text streaming, and parallel agent execution.

    Cloud LLM (The Story): Gemini 2.0 Flash (with API key rotation and Context Caching).

    Local LLM (The Logic): Ollama running Llama 3.2 3B. Operates entirely locally for zero API cost.

    Vector Database: ChromaDB for long-term RAG (Retrieval-Augmented Generation) memory.

    Relational Database: SQLite for immutable turn logs and campaign archiving.

    Deployment: Docker Compose (Frontend, Backend, Ollama, ChromaDB containers).

High-Level Data Flow (The Critical Path)
[ React UI ] ──(WebSocket Input)──> [ Bouncer (Security) ] ──> [ Intent Router ]
                                                                      |
    ┌─────────────────────────────────────────────────────────────────┘
    |
[ Rules Lawyer (RAG) ] ──(Context Assembly)──> [ DM Agent (Gemini Flash) ]
                                                      |
    ┌────────────────(Streams Text via WebSockets)────┘
    ▼
[ React UI ] <──(User reads text)
    |
    └─(Background Trigger)──> [ The Event Bus (State, Archivist, Handler, etc.) ]
    
3. The Agent Ecosystem

Agents are strictly divided into synchronous (blocking the UI) and asynchronous (running in the background while the player reads).
A. The Frontline (Synchronous / Critical Path)

These agents execute sequentially the moment the player hits "Send."

    The Bouncer (Security)

        Model: Lightweight local classifier.

        Role: The hard-line filter. Allows mature themes/gore but immediately blocks prohibited content (e.g., SA, harm to minors) before it reaches the pipeline.

    The Intent Router

        Model: Local Llama 3B.

        Role: The traffic cop. Determines if the input is a game action ("I attack"), a UI query ("What's my AC?"), or a rules question, routing it instantly to save cloud tokens.

    The Rules Lawyer

        Model: Local Llama 3B + ChromaDB.

        Role: The mechanic. Queries the D&D 5e SRD for exact rules relevant to the player's action and silently injects them into the DM's prompt.

    The DM Agent

        Model: Gemini 2.0 Flash.

        Role: The Storyteller. Consumes the World Bible, rules, and working memory to stream the cinematic narrative back to the player. It does not do math or track stats.

B. The Background (Asynchronous / Event Bus)

These agents listen to the DM's output and trigger locally without making the player wait.

    The State Extractor

        Model: Local Llama 3B (forced JSON output).

        Role: Translates the DM's prose into hard data (e.g., {"hp_change": -8}). Pushes updates to the UI via WebSockets instantly.

    The Tactician

        Model: Local Llama 3B / Python Engine.

        Role: Takes over during combat. Enforces strict grid spacing, initiative order, and momentum.

    The Quartermaster

        Model: Local Llama 3B / Python Tables.

        Role: Handles the economy. Rolls on strict loot tables based on enemy Challenge Rating (CR) to prevent the DM from giving away game-breaking items.

    The Puppeteer

        Model: Local Llama 3B.

        Role: Manages NPC psychology. Injects hidden directives (e.g., [NPC is lying, terrified of the player]) into the DM's prompt to maintain consistent personalities.

    The Handler / Butterfly

        Model: Local Llama 3B.

        Role: Tracks the grand chessboard. Updates faction reputation, Nemesis adaptations, and dispatches bounty hunters based on player actions.

    The Architect

        Model: Local Llama 3B / Procedural Python Script.

        Role: Generates non-linear, looping JSON node graphs for dungeons based on the World Bible, or loads static landmark maps.

    The Confessor

        Model: Local Llama 3B.

        Role: Tracks alignment shifts, crimes committed, and deep NPC relationship affinity scores.

    The Physician

        Model: Local logic script.

        Role: Tracks survival mechanics (hunger, exhaustion, days since rest) and lingering physical injuries.

    The Chronicler

        Model: Local Llama 3B.

        Role: Scans the story for clues and updates an "Investigation Board" JSON for tracking mysteries.

    The Archivist

        Model: Local Llama 3B.

        Role: Every 10 turns, compresses the raw chat log into a dense paragraph and saves it to ChromaDB to prevent context rot.

4. Reusable Tools (Function Calling)

The DM Agent is provided a "Tool Belt" of Python functions it can call instead of guessing outcomes.

    request_player_roll(skill, reason, DC): Pauses the DM generation, sends a WebSocket trigger to React, and spawns the 3D dice UI. The player's roll is fed back to the DM.

    resolve_stealth(player_stealth, enemy_perception, lighting): Calculates the exact mechanics of a stealth attempt.

    calculate_travel(start_node, end_node, pace): Calculates days passed, rations consumed, and triggers random encounters.

5. Game Mechanics & Features
Character Creation (Session Zero)

    Dice-Rolled Stats: Players roll 4d6 (drop the lowest) natively in the UI to generate their starting D&D stats.

    Power Scaling Tag: Defines the realism physics of the world (Gritty, Heroic, or Mythic). A Gritty level 1 character treats a stab wound as a lethal emergency; a Heroic level 10 character brushes it off.

    Backstory Anchors: 3-4 bullet points defining the character (e.g., "Valren: Ex-Syndicate Enforcer"). The engine uses these to trigger specific faction interactions immediately.

World Bibles (The Anchors)

500-word static JSON templates injected into the DM's context to completely eliminate generic fantasy tropes.

    Example: The Primal Circuit (Tribal survivalists hunting colossal mechanical beasts).

    Example: Iron & Rust (Claustrophobic, irradiated underground metro tunnels).

    Example: The Ashen Wastes (Brutalist, failing light, cryptic dark fantasy).

Brutal Survival & Consequences

    Permadeath: No save scumming. If a character fails three death saving throws, the campaign SQLite file locks into "Read-Only" mode. Game Over.

    Lingering Injuries: Critical hits can trigger permanent consequences (e.g., losing an eye or a hand), which dynamically updates the UI to lock out two-handed weapons.

Zero-Cost UI Atmosphere

    The Cartographer (Visuals): React reads location tags from the State Extractor and alters CSS variables. A toxic swamp turns the UI interface sickly green with spore particle effects.

    The Soundweaver (Audio): React reads a dynamically generated "Tension Score" (1-10). If tension hits 8 during a boss fight, the UI automatically crossfades the ambient audio into heavy, driving instrumental tracks (e.g., local MP3s of Dream Theater or Behemoth riffs).

6. Development Roadmap

    Phase 1: Core Pipeline. FastAPI, React, WebSocket streaming, and manual UI dice rolling.

    Phase 2: The Critical Path. Implement The Bouncer, Intent Router, and the Gemini DM Agent.

    Phase 3: The Event Bus. Integrate Ollama. Build the State Extractor to make the UI health bars and inventory reactive.

    Phase 4: Memory & Mechanics. ChromaDB integration, The Rules Lawyer, and The Archivist.

    Phase 5: The Living World. Implement the Architect, Quartermaster, Handler, and survival mechanics.

    Phase 6: Polish. Add the Soundweaver audio crossfading, CSS environmental shifts, and Docker Compose finalization.
