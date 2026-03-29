import React, { useEffect, useState } from 'react';
import { Sword, Trash2, Plus, Clock } from 'lucide-react';

function formatDate(ts) {
    if (!ts) return '';
    return new Date(ts * 1000).toLocaleDateString('en-US', {
        month: 'short', day: 'numeric',
        hour: '2-digit', minute: '2-digit',
    });
}

function formatWorld(name) {
    const map = {
        'The Ashen Wastes': 'Ashen Wastes',
        'Iron & Rust':      'Iron & Rust',
        'The Primal Circuit': 'Primal Circuit',
    };
    return map[name] ?? name;
}

export default function SaveSlots({ onNewGame, onLoadGame }) {
    const [sessions, setSessions] = useState([]);
    const [loading, setLoading]   = useState(true);
    const [deleting, setDeleting] = useState(null);

    useEffect(() => {
        fetch('http://localhost:8000/api/sessions')
            .then(r => r.json())
            .then(d => { setSessions(d.sessions ?? []); setLoading(false); })
            .catch(() => setLoading(false));
    }, []);

    const handleDelete = async (e, sessionId) => {
        e.stopPropagation();
        setDeleting(sessionId);
        await fetch(`http://localhost:8000/api/sessions/${sessionId}`, {
            method: 'DELETE',
        });
        setSessions(prev => prev.filter(s => s.session_id !== sessionId));
        setDeleting(null);
    };

    return (
        <div className="min-h-screen flex flex-col items-center justify-center bg-zinc-950 px-4 py-12 font-mono">
            <div className="w-full max-w-lg">

                {/* Title */}
                <div className="text-center mb-10">
                    <h1 className="text-3xl font-bold text-emerald-400 tracking-widest mb-2">
                        Chronicles
                    </h1>
                    <p className="text-zinc-600 text-sm">of the Forgotten Realm</p>
                </div>

                {/* New game button */}
                <button
                    onClick={onNewGame}
                    className="w-full flex items-center justify-center gap-2 py-3.5 mb-4 rounded-lg bg-emerald-700 hover:bg-emerald-600 text-white font-bold transition-colors"
                >
                    <Plus size={16} />
                    New Chronicle
                </button>

                {/* Save slots */}
                <div className="space-y-2">
                    <p className="text-xs text-zinc-600 mb-3">
                        {sessions.length > 0 ? 'Continue a chronicle' : 'No saved chronicles'}
                    </p>

                    {loading && (
                        <div className="text-center py-8 text-zinc-600 text-sm">
                            Loading chronicles...
                        </div>
                    )}

                    {sessions.map(s => (
                        <div
                            key={s.session_id}
                            onClick={() => !s.is_dead && onLoadGame(s.session_id)}
                            className={`
                                flex items-center gap-3 px-4 py-3 rounded-lg border
                                transition-all duration-150
                                ${s.is_dead
                                    ? 'border-red-900/50 bg-red-950/20 cursor-not-allowed opacity-60'
                                    : 'border-zinc-800 bg-zinc-900/50 hover:border-zinc-600 cursor-pointer'
                                }
                            `}
                        >
                            <Sword size={14} className={s.is_dead ? 'text-red-600' : 'text-emerald-600'} />

                            <div className="flex-1 min-w-0">
                                <div className="flex items-center gap-2">
                                    <span className="text-sm font-bold text-zinc-100 truncate">
                                        {s.char_name}
                                    </span>
                                    <span className="text-xs text-zinc-500">
                                        {s.char_race} {s.char_class}
                                    </span>
                                    {s.is_dead && (
                                        <span className="text-xs text-red-500 font-bold">DEAD</span>
                                    )}
                                </div>
                                <div className="flex items-center gap-3 mt-0.5">
                                    <span className="text-xs text-zinc-600">
                                        {formatWorld(s.world_bible)}
                                    </span>
                                    <span className="text-xs text-zinc-700">·</span>
                                    <span className="text-xs text-zinc-600">
                                        {s.turn_count} turns
                                    </span>
                                    <span className="text-xs text-zinc-700">·</span>
                                    <span className="text-xs text-zinc-600 flex items-center gap-1">
                                        <Clock size={10} />
                                        {formatDate(s.last_played)}
                                    </span>
                                </div>
                            </div>

                            <button
                                onClick={(e) => handleDelete(e, s.session_id)}
                                disabled={deleting === s.session_id}
                                className="text-zinc-700 hover:text-red-400 transition-colors p-1 shrink-0"
                                title="Delete chronicle"
                            >
                                <Trash2 size={14} />
                            </button>
                        </div>
                    ))}
                </div>

            </div>
        </div>
    );
}