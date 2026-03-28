Chronicles of the Forgotten Realm
A Solo D&D 5e Engine powered by Gemini & Local SLMs

This is a hybrid-AI tabletop engine. It uses Gemini 3 Flash for cinematic storytelling and a local Ollama (1B) instance for real-time game state tracking and rules enforcement.
The Tech Stack

    Frontend: React + Vite + Tailwind CSS

    Backend: FastAPI (Python 3.10+)

    Vector DB: ChromaDB (for D&D 5e Rules RAG)

    AI Models: * Gemini: Creative Narrative & Dialogue.

        Ollama (Llama 3.2 1B): State Extraction & Intent Routing.

Quick Start
1. The AI Brain (Ollama)

You must have Ollama installed and running. Pull the lightweight model we use for the game's "Accountant":
Bash

ollama pull llama3.2:1b

2. Backend Setup
Bash

cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

Environment Variables:
Create a .env file in the backend/ folder:
Code snippet

GEMINI_API_KEY=your_key_here
ANONYMIZED_TELEMETRY=False
OLLAMA_MODEL=llama3.2:1b

3. Frontend Setup
Bash

cd frontend
npm install
npm run dev

Current Workflow

    Session Zero: Create your character (React handles the logic).

    Narrative Loop: Gemini generates the story.

    State Extraction: Our local 1B model watches the story and updates your HP, Gold, and Inventory automatically.

    Bypassing Wards: Safety filters are currently set to BLOCK_NONE to allow for grimdark themes and fantasy combat.

Known Issues / Debugging

    HP Not Updating? Ensure the DM (Gemini) provides a concrete number (e.g., "You take 5 damage"). The 1B model cannot parse dice notation like 1d6.

    Terminal Spam: If you see ChromaDB telemetry errors, ensure export ANONYMIZED_TELEMETRY=False is set in your terminal session.

How to Contribute

    Branching: Create a new branch for every feature (git checkout -b feat/combat-system).

    Pull Requests: Explain what changed in the state extraction or UI.

    Don't Touch the Wards: Leave the safety settings in gemini_client.py as is—we like our rocks punchable.