import React, { useState, useRef, useEffect, useCallback } from 'react';
import { useGameSocket } from './hooks/useGameSocket';
import { Send, ScrollText, X, Sword, Heart, Coins, Package, Skull } from 'lucide-react';
import SessionZero from './components/SessionZero';
import CombatPanel from './components/CombatPanel';

// ── Helpers ───────────────────────────────────────────────────────────────────

function getHpColour(current, max) {
    const pct = max > 0 ? current / max : 1;
    if (pct > 0.6) return { bar: '#16a34a', glow: 'shadow-green-900' };  // green
    if (pct > 0.3) return { bar: '#d97706', glow: 'shadow-amber-900' };  // amber
    return { bar: '#dc2626', glow: 'shadow-red-900' };                   // red
}

function getMoralityLabel(score) {
    if (score >= 80) return { label: 'Virtuous',  colour: '#7c3aed' };
    if (score >= 60) return { label: 'Good',      colour: '#2563eb' };
    if (score >= 40) return { label: 'Neutral',   colour: '#6b7280' };
    if (score >= 20) return { label: 'Wicked',    colour: '#ea580c' };
    return                  { label: 'Malevolent', colour: '#dc2626' };
}

function getHungerColour(level) {
    const map = {
        Sated:    'bg-emerald-900/60 text-emerald-300 border-emerald-800',
        Peckish:  'bg-yellow-900/60  text-yellow-300  border-yellow-800',
        Hungry:   'bg-orange-900/60  text-orange-300  border-orange-800',
        Starving: 'bg-red-900/60     text-red-300     border-red-800',
    };
    return map[level] ?? map.Sated;
}

// ── Sub-components ────────────────────────────────────────────────────────────

function AnimatedHpBar({ current, max }) {
    const pct = max > 0 ? Math.min(100, Math.max(0, (current / max) * 100)) : 0;
    const { bar } = getHpColour(current, max);
    const isCritical = pct <= 20;

    return (
        <div className="space-y-1">
            <div className="flex justify-between items-center">
                <span className="text-xs text-zinc-400 flex items-center gap-1">
                    <Heart size={11} className="text-red-500" />
                    HP
                </span>
                <span
                    className={`text-xs font-bold tabular-nums transition-colors duration-500 ${
                        isCritical ? 'text-red-400 animate-pulse' : 'text-zinc-200'
                    }`}
                >
                    {current} / {max}
                </span>
            </div>
            <div className="w-full h-2.5 bg-zinc-800 rounded-full overflow-hidden border border-zinc-700">
                <div
                    className={`h-full rounded-full transition-all duration-700 ease-out ${
                        isCritical ? 'animate-pulse' : ''
                    }`}
                    style={{
                        width: `${pct}%`,
                        backgroundColor: bar,
                        transition: 'width 0.7s ease-out, background-color 0.5s ease',
                    }}
                />
            </div>
        </div>
    );
}

function MoralityBar({ score }) {
    const pct = Math.min(100, Math.max(0, score));
    const { label, colour } = getMoralityLabel(score);

    return (
        <div className="space-y-1">
            <div className="flex justify-between items-center">
                <span className="text-xs text-zinc-400">Morality</span>
                <span className="text-xs text-zinc-400">{label}</span>
            </div>
            <div className="w-full h-1.5 bg-zinc-800 rounded-full overflow-hidden border border-zinc-700">
                <div
                    className="h-full rounded-full transition-all duration-700 ease-out"
                    style={{
                        width: `${pct}%`,
                        backgroundColor: colour,
                        transition: 'width 0.7s ease-out, background-color 0.5s ease',
                    }}
                />
            </div>
        </div>
    );
}

function StatusEffectPill({ effect }) {
    const dangerous = ['Poisoned', 'Exhaustion', 'Unconscious', 'Paralyzed', 'Stunned'];
    const warning   = ['Prone', 'Frightened', 'Restrained', 'Grappled', 'Blinded'];
    const isDanger  = dangerous.includes(effect);
    const isWarning = warning.includes(effect);

    const cls = isDanger
        ? 'bg-red-900/50 text-red-300 border-red-800'
        : isWarning
        ? 'bg-orange-900/50 text-orange-300 border-orange-800'
        : 'bg-zinc-800 text-zinc-300 border-zinc-700';

    return (
        <span className={`text-xs px-2 py-0.5 rounded border ${cls} font-mono`}>
            {effect}
        </span>
    );
}

function CharacterDrawer({ character, isOpen, onClose }) {
    const char = character || {};

    return (
        <>
            {isOpen && (
                <div
                    className="fixed inset-0 bg-black/40 z-20 transition-opacity"
                    onClick={onClose}
                />
            )}
            <div
                className={`
                    fixed top-0 right-0 h-full w-72 z-30
                    bg-zinc-950 border-l border-zinc-800
                    flex flex-col
                    transform transition-transform duration-300 ease-in-out
                    ${isOpen ? 'translate-x-0' : 'translate-x-full'}
                `}
            >
                <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800">
                    <div>
                        <p className="text-sm font-bold text-zinc-100">{char.name || 'Unknown Adventurer'}</p>
                        <p className="text-xs text-zinc-500">
                            Level {char.level || 1}
                            {char.char_class ? ` ${char.char_class}` : ''}
                        </p>
                    </div>
                    <button
                        onClick={onClose}
                        className="text-zinc-500 hover:text-zinc-200 transition-colors p-1 rounded"
                    >
                        <X size={16} />
                    </button>
                </div>

                <div className="flex-1 overflow-y-auto px-4 py-4 space-y-5">
                    <AnimatedHpBar
                        current={char.hp_current || 0}
                        max={char.hp_max || 0}
                    />

                    <div className="flex items-center justify-between">
                        <span className="text-xs text-zinc-400">Hunger</span>
                        <span className={`text-xs px-2 py-0.5 rounded border ${getHungerColour(char.hunger_level || 'Sated')}`}>
                            {char.hunger_level || 'Sated'}
                        </span>
                    </div>

                    <MoralityBar score={char.morality_score || 50} />

                    {char.status_effects?.length > 0 && (
                        <div className="space-y-1.5">
                            <span className="text-xs text-zinc-400 flex items-center gap-1">
                                <Skull size={11} /> Conditions
                            </span>
                            <div className="flex flex-wrap gap-1.5">
                                {char.status_effects.map((e) => (
                                    <StatusEffectPill key={e} effect={e} />
                                ))}
                            </div>
                        </div>
                    )}

                    <hr className="border-zinc-800" />

                    <div className="flex items-center justify-between">
                        <span className="text-xs text-zinc-400 flex items-center gap-1">
                            <Coins size={11} className="text-yellow-500" /> Gold
                        </span>
                        <span className="text-xs font-bold text-yellow-400 tabular-nums">
                            {typeof char.gold_pieces === 'number'
                                ? char.gold_pieces % 1 === 0
                                    ? `${char.gold_pieces} GP`
                                    : `${char.gold_pieces.toFixed(1)} GP`
                                : '0 GP'}
                        </span>
                    </div>

                    <div className="space-y-1.5">
                        <span className="text-xs text-zinc-400 flex items-center gap-1">
                            <Package size={11} /> Inventory
                        </span>
                        {char.inventory?.length > 0 ? (
                            <ul className="space-y-1">
                                {char.inventory.map((item, i) => (
                                    <li
                                        key={`${item}-${i}`}
                                        className="text-xs text-zinc-300 flex items-start gap-1.5"
                                    >
                                        <span className="text-zinc-600 mt-px">·</span>
                                        {item}
                                    </li>
                                ))}
                            </ul>
                        ) : (
                            <p className="text-xs text-zinc-600 italic">Nothing carried.</p>
                        )}
                    </div>
                </div>

                {char.armor_class && (
                    <div className="px-4 py-3 border-t border-zinc-800 flex items-center justify-between">
                        <span className="text-xs text-zinc-500 flex items-center gap-1">
                            <Sword size={11} /> Armour Class
                        </span>
                        <span className="text-xs font-bold text-zinc-200">
                            {char.armor_class}
                        </span>
                    </div>
                )}
            </div>
        </>
    );
}

function StreamingCursor() {
    return (
        <span className="inline-block w-1.5 h-3.5 bg-emerald-400 ml-0.5 align-middle animate-pulse" />
    );
}

function MessageBubble({ msg }) {
    const isUser   = msg.sender === 'User';
    const isSystem = msg.sender === 'System';
    const isError  = msg.message_type === 'error';

    if (isSystem && !isError) {
        return (
            <div className="flex justify-center">
                <span className="text-xs text-zinc-600 italic px-3 py-1">
                    {msg.content}
                </span>
            </div>
        );
    }

    const bubbleCls = isUser
        ? 'bg-emerald-900/30 border border-emerald-800/50 text-emerald-100'
        : isError
        ? 'bg-red-900/20 border border-red-800/50 text-red-300'
        : 'bg-zinc-800/60 border border-zinc-700/50 text-zinc-200';

    return (
        <div className={`flex flex-col ${isUser ? 'items-end' : 'items-start'}`}>
            <span className="text-xs text-zinc-600 mb-1 px-1">
                {isUser ? 'You' : isError ? 'System' : 'Aldrathas'}
            </span>
            <div
                className={`
                    px-3 py-2.5 rounded-lg max-w-[88%]
                    text-sm leading-relaxed whitespace-pre-wrap
                    ${bubbleCls}
                `}
            >
                {msg.content}
                {msg.streaming && <StreamingCursor />}
            </div>
        </div>
    );
}

function HudStrip({ character, onOpenDrawer }) {
    const char = character || {};
    const { current: hp_current, max: hp_max } = {
        current: char.hp_current || 0,
        max: char.hp_max || 0,
    };
    const pct = hp_max > 0 ? Math.min(100, (hp_current / hp_max) * 100) : 0;
    const { bar } = getHpColour(hp_current, hp_max);
    const isCritical = pct <= 20;

    return (
        <div
            className="flex items-center gap-3 px-3 py-2 bg-zinc-900/80 border border-zinc-800 rounded-lg cursor-pointer hover:border-zinc-600 transition-colors"
            onClick={onOpenDrawer}
            title="Open character sheet"
        >
            <div className="flex items-center gap-1.5 min-w-0">
                <Heart
                    size={12}
                    className={isCritical ? 'text-red-500 animate-pulse' : 'text-red-600'}
                />
                <div className="w-20 h-1.5 bg-zinc-800 rounded-full overflow-hidden">
                    <div
                        className="h-full rounded-full"
                        style={{
                            width: `${pct}%`,
                            backgroundColor: bar,
                            transition: 'width 0.7s ease-out, background-color 0.5s ease',
                        }}
                    />
                </div>
                <span className={`text-xs tabular-nums ${isCritical ? 'text-red-400 font-bold' : 'text-zinc-400'}`}>
                    {hp_current}/{hp_max}
                </span>
            </div>

            <span className="text-zinc-700">|</span>

            <span className={`text-xs px-1.5 py-0.5 rounded border ${getHungerColour(char.hunger_level || 'Sated')}`}>
                {char.hunger_level || 'Sated'}
            </span>

            {char.status_effects?.slice(0, 2).map((e) => (
                <StatusEffectPill key={e} effect={e} />
            ))}
            {char.status_effects?.length > 2 && (
                <span className="text-xs text-zinc-500">
                    +{char.status_effects.length - 2}
                </span>
            )}

            <div className="ml-auto flex items-center gap-1">
                <Coins size={11} className="text-yellow-600" />
                <span className="text-xs text-yellow-500 tabular-nums">
                    {Math.floor(char.gold_pieces ?? 0)} GP
                </span>
            </div>

            <ScrollText size={13} className="text-zinc-600 shrink-0" />
        </div>
    );
}

// ── Root App ──────────────────────────────────────────────────────────────────

// ── The Active Game Component (Only loads AFTER character creation) ──────────

function ActiveGame({ sessionData }) {
    const {
        messages,
        isConnected,
        isStreaming,
        sendMessage,
        gameState,
        initSession,
        loadSession,
    } = useGameSocket('ws://localhost:8000/ws/game');

    useEffect(() => {
        if (loadSessionId) {
            loadSession(loadSessionId);  // returning player
        } else if (sessionData) {
            initSession(sessionData);    // new character
        }
    }, [sessionData, loadSessionId]);

    const [input, setInput]           = useState('');
    const [drawerOpen, setDrawerOpen] = useState(false);
    const bottomRef                   = useRef(null);

    // Initialize the backend session once when this component mounts
    useEffect(() => {
        initSession(sessionData);
    }, [sessionData, initSession]);

    // Auto-scroll on every new token
    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages]);

    const handleSend = useCallback((e) => {
        e.preventDefault();
        const trimmed = input.trim();
        if (!trimmed || !isConnected || isStreaming) return;
        sendMessage(trimmed);
        setInput('');
    }, [input, isConnected, isStreaming, sendMessage]);

    const canSend = isConnected && !isStreaming && input.trim().length > 0;

    // --- THE FIX: STRICT IDENTITY CHECK ---
    // The socket starts with hardcoded dummy data (like "Adventurer" and 10 HP).
    // We force the UI to use your rolled SessionZero data until the backend 
    // StateExtractor successfully syncs and returns your actual character name.
    
    const char = gameState?.character || sessionData?.character || {};
    // --------------------------------------

    return (
        <div className="flex flex-col h-screen max-w-3xl mx-auto font-mono relative overflow-hidden">
            <CharacterDrawer
                character={char}
                isOpen={drawerOpen}
                onClose={() => setDrawerOpen(false)}
            />

            <header className="flex items-center justify-between px-4 py-3 border-b border-zinc-800 shrink-0">
                <div>
                    <h1 className="text-base font-bold text-emerald-400 tracking-wide">
                        Chronicles of the Forgotten Realm
                    </h1>
                    <p className="text-xs text-zinc-600">Solo D&amp;D 5e Engine</p>
                </div>
                <div className="flex items-center gap-3">
                    <div className={`w-2 h-2 rounded-full transition-colors ${
                        isStreaming   ? 'bg-amber-400 animate-pulse' :
                        isConnected   ? 'bg-emerald-500' :
                                        'bg-red-500 animate-pulse'
                    }`} />
                    <span className="text-xs text-zinc-500">
                        {isStreaming ? 'Narrating...' : isConnected ? 'Online' : 'Offline'}
                    </span>
                    <button
                        onClick={() => setDrawerOpen(true)}
                        className="flex items-center gap-1.5 text-xs text-zinc-400 hover:text-emerald-400 transition-colors border border-zinc-700 hover:border-emerald-700 rounded px-2 py-1"
                        title="Open character sheet"
                    >
                        <ScrollText size={13} />
                        Sheet
                    </button>
                </div>
            </header>

            <main className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
                {messages.length === 0 && (
                    <div className="flex items-center justify-center h-full">
                        <p className="text-zinc-700 text-sm italic">
                            The realm awaits your first action...
                        </p>
                    </div>
                )}
                {messages.map((msg) => (
                    <MessageBubble key={msg.id} msg={msg} />
                ))}
                <div ref={bottomRef} />
            </main>

            <footer className="px-4 pb-4 pt-2 border-t border-zinc-800 space-y-2 shrink-0">
                
                {/* Combat panel — slides in above HUD when combat is active */}
                <CombatPanel combat={gameState?.combat} />
                <HudStrip
                    character={char}
                    onOpenDrawer={() => setDrawerOpen(true)}
                />

                <form onSubmit={handleSend} className="flex gap-2">
                    <input
                        type="text"
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        placeholder={isStreaming ? 'Wait for the DM...' : 'What do you do?'}
                        disabled={!isConnected || isStreaming}
                        className="
                            flex-1 bg-zinc-900 border border-zinc-700 rounded-lg
                            px-4 py-2.5 text-sm text-zinc-100 placeholder-zinc-600
                            focus:outline-none focus:border-emerald-600
                            focus:ring-1 focus:ring-emerald-600/40
                            disabled:opacity-40 transition-colors
                        "
                    />
                    <button
                        type="submit"
                        disabled={!canSend}
                        className="
                            bg-emerald-700 hover:bg-emerald-600 active:bg-emerald-800
                            text-white px-5 py-2.5 rounded-lg transition-colors
                            flex items-center justify-center
                            disabled:opacity-30 disabled:cursor-not-allowed
                        "
                    >
                        <Send size={15} />
                    </button>
                </form>
            </footer>
        </div>
    );
}

// ── Root App Router ───────────────────────────────────────────────────────────

export default function App() {
    // screen: 'slots' | 'session_zero' | 'game'
    const [screen, setScreen]         = useState('slots');
    const [sessionData, setSessionData] = useState(null);
    const [loadSessionId, setLoadSessionId] = useState(null);

    const handleNewGame = () => setScreen('session_zero');

    const handleLoadGame = (sessionId) => {
        setLoadSessionId(sessionId);
        setScreen('game');
    };

    const handleSessionComplete = (data) => {
        const c = data.character;
        c.hp_max      = c.maxHp      || c.hp_max      || 10;
        c.hp_current  = c.hp_max;
        c.armor_class = c.armorClass  || c.armor_class || 10;
        c.gold_pieces = c.startingGp  ?? c.gold_pieces ?? 0;
        c.char_class  = c.charClass   || c.char_class  || "";
        setSessionData(data);
        setScreen('game');
    };

    if (screen === 'slots') {
        return (
            <SaveSlots
                onNewGame={handleNewGame}
                onLoadGame={handleLoadGame}
            />
        );
    }

    if (screen === 'session_zero') {
        return <SessionZero onComplete={handleSessionComplete} />;
    }

    return (
        <ActiveGame
            sessionData={sessionData}
            loadSessionId={loadSessionId}
        />
    );
}