import React, { useState } from 'react';
import { Sword, Shield, Zap, Wind, ChevronRight } from 'lucide-react';

// ── Helpers ───────────────────────────────────────────────────────────────────

function HpBar({ current, max }) {
    const pct = max > 0 ? Math.min(100, (current / max) * 100) : 0;
    const color = pct > 60 ? '#16a34a' : pct > 30 ? '#d97706' : '#dc2626';
    return (
        <div className="flex items-center gap-1.5 flex-1">
            <div className="flex-1 h-1.5 bg-zinc-800 rounded-full overflow-hidden">
                <div
                    className="h-full rounded-full transition-all duration-500"
                    style={{ width: `${pct}%`, backgroundColor: color }}
                />
            </div>
            <span className="text-xs tabular-nums text-zinc-400 w-12 text-right">
                {current}/{max}
            </span>
        </div>
    );
}

function CombatantRow({ combatant }) {
    const isDefeated = combatant.hp_current <= 0;
    return (
        <div className={`
            flex items-center gap-2 px-3 py-2 rounded-lg border transition-all
            ${combatant.is_active
                ? 'border-amber-600 bg-amber-900/20'
                : isDefeated
                ? 'border-zinc-800 opacity-40'
                : 'border-zinc-800 bg-zinc-900/40'
            }
        `}>
            {/* Active indicator */}
            <div className={`w-1.5 h-1.5 rounded-full shrink-0 ${
                combatant.is_active ? 'bg-amber-400 animate-pulse' : 'bg-zinc-700'
            }`} />

            {/* Name + type */}
            <div className="flex-1 min-w-0">
                <div className="flex items-center gap-1.5">
                    <span className={`text-xs font-bold truncate ${
                        combatant.is_player ? 'text-emerald-400' : 'text-red-400'
                    }`}>
                        {combatant.name}
                    </span>
                    {combatant.is_active && (
                        <ChevronRight size={10} className="text-amber-400 shrink-0" />
                    )}
                </div>
                <HpBar current={combatant.hp_current} max={combatant.hp_max} />
            </div>

            {/* Initiative + AC */}
            <div className="text-right shrink-0">
                <div className="text-xs text-zinc-500">Init {combatant.initiative}</div>
                <div className="text-xs text-zinc-500">AC {combatant.ac}</div>
            </div>
        </div>
    );
}

const ACTION_ICONS = {
    action:   <Sword size={11} />,
    bonus:    <Zap size={11} />,
    reaction: <Shield size={11} />,
    movement: <Wind size={11} />,
};

const ACTION_COLORS = {
    action:   'border-blue-800 text-blue-300 bg-blue-900/20',
    bonus:    'border-purple-800 text-purple-300 bg-purple-900/20',
    reaction: 'border-orange-800 text-orange-300 bg-orange-900/20',
    movement: 'border-teal-800 text-teal-300 bg-teal-900/20',
};

function ActionChip({ action }) {
    const color = ACTION_COLORS[action.type] ?? ACTION_COLORS.action;
    const icon  = ACTION_ICONS[action.type] ?? ACTION_ICONS.action;
    return (
        <div
            className={`flex items-center gap-1 px-2 py-1 rounded border text-xs ${color}`}
            title={action.desc}
        >
            {icon}
            <span>{action.name}</span>
        </div>
    );
}

// ── Action Economy Bar ────────────────────────────────────────────────────────

function ActionEconomy({ combat }) {
    const slots = [
        { label: 'Action',   used: combat.action_used,   color: 'bg-blue-500'   },
        { label: 'Bonus',    used: combat.bonus_used,    color: 'bg-purple-500' },
        { label: 'Reaction', used: combat.reaction_used, color: 'bg-orange-500' },
    ];
    const movePct = Math.min(100, ((combat.movement_used ?? 0) / 30) * 100);

    return (
        <div className="space-y-1.5 px-3 py-2 bg-zinc-900/60 rounded-lg border border-zinc-800">
            <p className="text-xs text-zinc-500 mb-1">Action economy</p>
            <div className="flex gap-2">
                {slots.map(s => (
                    <div key={s.label} className="flex items-center gap-1">
                        <div className={`w-2.5 h-2.5 rounded-sm border ${
                            s.used ? 'border-zinc-600 bg-zinc-700' : `border-zinc-600 ${s.color}`
                        }`} />
                        <span className={`text-xs ${s.used ? 'text-zinc-600 line-through' : 'text-zinc-400'}`}>
                            {s.label}
                        </span>
                    </div>
                ))}
            </div>
            {/* Movement bar */}
            <div className="flex items-center gap-2">
                <span className="text-xs text-zinc-500 w-14">Movement</span>
                <div className="flex-1 h-1 bg-zinc-800 rounded-full overflow-hidden">
                    <div
                        className="h-full bg-teal-600 rounded-full transition-all duration-300"
                        style={{ width: `${movePct}%` }}
                    />
                </div>
                <span className="text-xs text-zinc-500">
                    {30 - (combat.movement_used ?? 0)}ft left
                </span>
            </div>
        </div>
    );
}

// ── Root CombatPanel ──────────────────────────────────────────────────────────

export default function CombatPanel({ combat }) {
    if (!combat?.active) return null;

    const isPlayerTurn = combat.current_turn?.is_player;
    const availableActions = combat.available_actions ?? [];

    return (
        <div className="border border-amber-900/60 bg-zinc-950 rounded-xl overflow-hidden mb-2 animate-in slide-in-from-bottom duration-300">

            {/* Header */}
            <div className="flex items-center justify-between px-3 py-2 bg-amber-900/20 border-b border-amber-900/40"onClick={() => setExpanded(e => !e)}>
                <div className="flex items-center gap-2">
                    <Sword size={13} className="text-amber-400" />
                    <span className="text-xs font-bold text-amber-300">
                        Combat — Round {combat.round}
                    </span>
                    {!expanded && (
                        <span className="text-xs text-zinc-500 ml-2">
                            {combat.combatants?.map(c =>
                                `${c.name} ${c.hp_current}/${c.hp_max}`
                            ).join(' · ')}
                        </span>
                    )}
                </div>
                <span className={`text-xs px-2 py-0.5 rounded border ${
                    isPlayerTurn
                        ? 'border-emerald-700 text-emerald-400 bg-emerald-900/20'
                        : 'border-red-800 text-red-400 bg-red-900/20'
                }`}>
                    {isPlayerTurn ? 'Your turn' : `${combat.current_turn?.name}'s turn`}
                </span>
                <span className="text-zinc-600 text-xs">{expanded ? '▲' : '▼'}</span>
            </div>
            {expanded && (

            <div className="p-3 space-y-3">

                {/* Initiative order */}
                <div className="space-y-1.5">
                    {(combat.combatants ?? []).map(c => (
                        <CombatantRow key={c.id} combatant={c} />
                    ))}
                </div>

                {/* Action economy — only show on player turn */}
                {isPlayerTurn && <ActionEconomy combat={combat} />}

                {/* Available actions */}
                {isPlayerTurn && availableActions.length > 0 && (
                    <div>
                        <p className="text-xs text-zinc-500 mb-1.5">Available this turn</p>
                        <div className="flex flex-wrap gap-1.5">
                            {availableActions.map(a => (
                                <ActionChip key={a.id} action={a} />
                            ))}
                        </div>
                        <p className="text-xs text-zinc-600 mt-1.5 italic">
                            Describe your action freely — the DM enforces the rules.
                        </p>
                    </div>
                )}

            </div>
            )}
        </div>
    );
}
