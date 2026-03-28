import React, { useState, useEffect, useRef, useCallback } from 'react';
import { ChevronRight, ChevronLeft, Dice6, RefreshCw, Check } from 'lucide-react';

// ── Static Data ───────────────────────────────────────────────────────────────

const RACES = [
  { name: 'Human',      bonus: { str:1, dex:1, con:1, int:1, wis:1, cha:1 } },
  { name: 'Elf',        bonus: { dex:2, wis:1 } },
  { name: 'Dwarf',      bonus: { con:2, wis:1 } },
  { name: 'Halfling',   bonus: { dex:2, cha:1 } },
  { name: 'Half-Orc',   bonus: { str:2, con:1 } },
  { name: 'Gnome',      bonus: { int:2, con:1 } },
  { name: 'Tiefling',   bonus: { cha:2, int:1 } },
  { name: 'Dragonborn', bonus: { str:2, cha:1 } },
];

const CLASSES = [
  { name: 'Barbarian', hitDie: 12, primaryStat: 'str', saves: ['str','con'] },
  { name: 'Bard',      hitDie: 8,  primaryStat: 'cha', saves: ['dex','cha'] },
  { name: 'Cleric',    hitDie: 8,  primaryStat: 'wis', saves: ['wis','cha'] },
  { name: 'Druid',     hitDie: 8,  primaryStat: 'wis', saves: ['int','wis'] },
  { name: 'Fighter',   hitDie: 10, primaryStat: 'str', saves: ['str','con'] },
  { name: 'Monk',      hitDie: 8,  primaryStat: 'dex', saves: ['str','dex'] },
  { name: 'Paladin',   hitDie: 10, primaryStat: 'str', saves: ['wis','cha'] },
  { name: 'Ranger',    hitDie: 10, primaryStat: 'dex', saves: ['str','dex'] },
  { name: 'Rogue',     hitDie: 8,  primaryStat: 'dex', saves: ['dex','int'] },
  { name: 'Sorcerer',  hitDie: 6,  primaryStat: 'cha', saves: ['con','cha'] },
  { name: 'Warlock',   hitDie: 8,  primaryStat: 'cha', saves: ['wis','cha'] },
  { name: 'Wizard',    hitDie: 6,  primaryStat: 'int', saves: ['int','wis'] },
];

const BACKGROUNDS = [
  'Acolyte', 'Criminal', 'Folk Hero', 'Noble', 'Sage', 'Soldier',
];

const ALIGNMENTS = [
  ['Lawful Good',    'Neutral Good',    'Chaotic Good'   ],
  ['Lawful Neutral', 'True Neutral',    'Chaotic Neutral'],
  ['Lawful Evil',    'Neutral Evil',    'Chaotic Evil'   ],
];

const WORLD_BIBLES = [
  {
    id: 'ashen_wastes',
    name: 'The Ashen Wastes',
    tagline: 'Brutalist. Failing light. Cryptic dark fantasy.',
    description: 'A dying world of ash-choked ruins and forgotten gods. Civilisation clings to fortified citadels while corrupted things stalk the wastes between them.',
  },
  {
    id: 'iron_rust',
    name: 'Iron & Rust',
    tagline: 'Claustrophobic. Irradiated. Underground metro tunnels.',
    description: 'The surface is dead. Humanity survives in a vast labyrinth of crumbling metro tunnels, fighting over clean water, power cells, and breathable air.',
  },
  {
    id: 'primal_circuit',
    name: 'The Primal Circuit',
    tagline: 'Tribal survivalists hunting colossal mechanical beasts.',
    description: 'Ancient megafauna made of steel and steam roam a wilderness of overgrown technology. Tribal hunters worship the machines they kill for parts.',
  },
];

const STAT_KEYS = ['str', 'dex', 'con', 'int', 'wis', 'cha'];
const STAT_LABELS = {
  str: 'Strength', dex: 'Dexterity', con: 'Constitution',
  int: 'Intelligence', wis: 'Wisdom', cha: 'Charisma',
};

// ── Dice helpers ──────────────────────────────────────────────────────────────

function roll4d6DropLowest() {
  const rolls = Array.from({ length: 4 }, () => Math.ceil(Math.random() * 6));
  const sorted = [...rolls].sort((a, b) => a - b);
  const dropped = sorted[0];
  const total = sorted.slice(1).reduce((s, n) => s + n, 0);
  return { rolls, dropped, total };
}

function modifier(score) {
  const m = Math.floor((score - 10) / 2);
  return m >= 0 ? `+${m}` : `${m}`;
}

function calcHp(cls, conScore) {
  if (!cls) return 8;
  return cls.hitDie + Math.floor((conScore - 10) / 2);
}

function calcAc(dexScore) {
  return 10 + Math.floor((dexScore - 10) / 2);
}

// ── Step indicator ────────────────────────────────────────────────────────────

function StepDots({ current, total }) {
  return (
    <div className="flex items-center gap-2">
      {Array.from({ length: total }).map((_, i) => (
        <div
          key={i}
          className={`h-1.5 rounded-full transition-all duration-300 ${
            i < current
              ? 'w-6 bg-emerald-500'
              : i === current
              ? 'w-6 bg-emerald-400'
              : 'w-3 bg-zinc-700'
          }`}
        />
      ))}
    </div>
  );
}

// ── Pill picker ───────────────────────────────────────────────────────────────

function PillPicker({ options, selected, onSelect, getLabel }) {
  return (
    <div className="flex flex-wrap gap-2">
      {options.map((opt) => {
        const label = getLabel ? getLabel(opt) : opt;
        const isSelected = selected === (opt.name ?? opt);
        return (
          <button
            key={label}
            type="button"
            onClick={() => onSelect(opt)}
            className={`px-3 py-1.5 rounded-lg text-xs border transition-all duration-150 ${
              isSelected
                ? 'bg-emerald-700 border-emerald-500 text-emerald-100'
                : 'bg-zinc-900 border-zinc-700 text-zinc-400 hover:border-zinc-500 hover:text-zinc-200'
            }`}
          >
            {label}
          </button>
        );
      })}
    </div>
  );
}

// ── Screen 1: Identity ────────────────────────────────────────────────────────

function ScreenIdentity({ form, setForm }) {
  const updateAnchor = (i, val) => {
    const next = [...form.backstoryAnchors];
    next[i] = val;
    setForm(f => ({ ...f, backstoryAnchors: next }));
  };

  return (
    <div className="space-y-6">

      {/* Name */}
      <div>
        <label className="text-xs text-zinc-400 mb-1.5 block">Character name</label>
        <input
          type="text"
          value={form.name}
          onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
          placeholder="e.g. Valren Ashford"
          className="w-full bg-zinc-900 border border-zinc-700 rounded-lg px-4 py-2.5 text-sm text-zinc-100 placeholder-zinc-600 focus:outline-none focus:border-emerald-600 focus:ring-1 focus:ring-emerald-600/40"
        />
      </div>

      {/* Race */}
      <div>
        <label className="text-xs text-zinc-400 mb-1.5 block">Race</label>
        <PillPicker
          options={RACES}
          selected={form.race}
          onSelect={r => setForm(f => ({ ...f, race: r.name, racialBonus: r.bonus }))}
          getLabel={r => r.name}
        />
        {form.race && (
          <p className="text-xs text-zinc-600 mt-1.5">
            Racial bonuses: {
              Object.entries(RACES.find(r => r.name === form.race)?.bonus ?? {})
                .map(([k, v]) => `+${v} ${STAT_LABELS[k]}`)
                .join(', ')
            }
          </p>
        )}
      </div>

      {/* Class */}
      <div>
        <label className="text-xs text-zinc-400 mb-1.5 block">Class</label>
        <PillPicker
          options={CLASSES}
          selected={form.charClass}
          onSelect={c => setForm(f => ({ ...f, charClass: c.name, classData: c }))}
          getLabel={c => c.name}
        />
        {form.classData && (
          <p className="text-xs text-zinc-600 mt-1.5">
            Hit die: d{form.classData.hitDie} &nbsp;·&nbsp;
            Primary: {STAT_LABELS[form.classData.primaryStat]} &nbsp;·&nbsp;
            Saves: {form.classData.saves.map(s => STAT_LABELS[s]).join(', ')}
          </p>
        )}
      </div>

      {/* Background */}
      <div>
        <label className="text-xs text-zinc-400 mb-1.5 block">Background</label>
        <PillPicker
          options={BACKGROUNDS}
          selected={form.background}
          onSelect={b => setForm(f => ({ ...f, background: b }))}
        />
      </div>

      {/* Alignment */}
      <div>
        <label className="text-xs text-zinc-400 mb-1.5 block">Alignment</label>
        <div className="grid grid-cols-3 gap-1.5">
          {ALIGNMENTS.flat().map(a => (
            <button
              key={a}
              type="button"
              onClick={() => setForm(f => ({ ...f, alignment: a }))}
              className={`px-2 py-2 rounded text-xs border transition-all ${
                form.alignment === a
                  ? 'bg-emerald-700 border-emerald-500 text-emerald-100'
                  : 'bg-zinc-900 border-zinc-700 text-zinc-400 hover:border-zinc-500'
              }`}
            >
              {a}
            </button>
          ))}
        </div>
      </div>

      {/* World Bible */}
      <div>
        <label className="text-xs text-zinc-400 mb-1.5 block">Campaign setting</label>
        <div className="space-y-2">
          {WORLD_BIBLES.map(wb => (
            <button
              key={wb.id}
              type="button"
              onClick={() => setForm(f => ({ ...f, worldBible: wb.id }))}
              className={`w-full text-left px-4 py-3 rounded-lg border transition-all ${
                form.worldBible === wb.id
                  ? 'bg-emerald-900/30 border-emerald-700 text-emerald-100'
                  : 'bg-zinc-900/50 border-zinc-700 text-zinc-300 hover:border-zinc-500'
              }`}
            >
              <p className="text-sm font-bold">{wb.name}</p>
              <p className="text-xs text-zinc-500 mt-0.5 italic">{wb.tagline}</p>
            </button>
          ))}
        </div>
      </div>

      {/* Backstory anchors */}
      <div>
        <label className="text-xs text-zinc-400 mb-1.5 block">
          Backstory anchors
          <span className="text-zinc-600 ml-1">— the DM will use these immediately</span>
        </label>
        {form.backstoryAnchors.map((anchor, i) => (
          <input
            key={i}
            type="text"
            value={anchor}
            onChange={e => updateAnchor(i, e.target.value)}
            placeholder={[
              'e.g. Ex-Syndicate enforcer, left after a job went wrong',
              'e.g. Searching for a younger sibling who vanished in the wastes',
              'e.g. Owes a life-debt to the Ashwalker cult',
            ][i]}
            className="w-full bg-zinc-900 border border-zinc-700 rounded-lg px-4 py-2 text-sm text-zinc-100 placeholder-zinc-600 focus:outline-none focus:border-emerald-600 mb-2"
          />
        ))}
      </div>

    </div>
  );
}

// ── Screen 2: Ability Scores ──────────────────────────────────────────────────

function Dieface({ value, isDropped }) {
  return (
    <span className={`
      inline-flex items-center justify-center
      w-7 h-7 rounded border text-xs font-bold
      ${isDropped
        ? 'border-zinc-700 text-zinc-600 line-through bg-zinc-900'
        : 'border-emerald-700 text-emerald-300 bg-emerald-900/30'
      }
    `}>
      {value}
    </span>
  );
}

function ScreenStats({ form, setForm }) {
  const [rolls, setRolls] = useState(form.rollResults ?? null);
  const [assigned, setAssigned] = useState(form.assignedStats ?? {});
  const [dragging, setDragging] = useState(null);
  const [rolling, setRolling] = useState(false);

  // Which roll indices are already assigned
  const usedRollIndices = new Set(Object.values(assigned));

  const doRoll = useCallback(() => {
    setRolling(true);
    setAssigned({});
    setForm(f => ({ ...f, assignedStats: {} }));

    // Fake dice animation — replace values rapidly for 600ms
    let ticks = 0;
    const interval = setInterval(() => {
      setRolls(Array.from({ length: 6 }, () => roll4d6DropLowest()));
      ticks++;
      if (ticks > 10) {
        clearInterval(interval);
        const final = Array.from({ length: 6 }, () => roll4d6DropLowest());
        setRolls(final);
        setForm(f => ({ ...f, rollResults: final }));
        setRolling(false);
      }
    }, 60);
  }, [setForm]);

  // Auto-roll on first visit
  useEffect(() => {
    if (!rolls) doRoll();
  }, []);

  const handleDrop = (statKey) => {
    if (dragging === null) return;
    const next = { ...assigned, [statKey]: dragging };
    setAssigned(next);
    setForm(f => ({ ...f, assignedStats: next }));
    setDragging(null);
  };

  const unassign = (statKey) => {
    const next = { ...assigned };
    delete next[statKey];
    setAssigned(next);
    setForm(f => ({ ...f, assignedStats: next }));
  };

  const racialBonus = form.racialBonus ?? {};

  const getFinalScore = (statKey) => {
    if (assigned[statKey] === undefined || !rolls) return null;
    const base = rolls[assigned[statKey]].total;
    return base + (racialBonus[statKey] ?? 0);
  };

  return (
    <div className="space-y-6">

      {/* Roll button */}
      <div className="flex items-center justify-between">
        <p className="text-xs text-zinc-400">
          Roll 4d6, drop the lowest. Drag each result to a stat.
        </p>
        <button
          type="button"
          onClick={doRoll}
          disabled={rolling}
          className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded border border-zinc-700 text-zinc-400 hover:border-emerald-700 hover:text-emerald-400 transition-colors disabled:opacity-40"
        >
          <RefreshCw size={12} className={rolling ? 'animate-spin' : ''} />
          Re-roll all
        </button>
      </div>

      {/* Roll results */}
      {rolls && (
        <div className="grid grid-cols-3 gap-2">
          {rolls.map((r, i) => {
            const isUsed = usedRollIndices.has(i);
            return (
              <div
                key={i}
                draggable={!isUsed && !rolling}
                onDragStart={() => setDragging(i)}
                onDragEnd={() => setDragging(null)}
                className={`
                  flex flex-col items-center gap-1.5 p-2.5 rounded-lg border
                  transition-all duration-150 select-none
                  ${isUsed
                    ? 'opacity-30 border-zinc-800 cursor-not-allowed'
                    : dragging === i
                    ? 'border-emerald-500 bg-emerald-900/20 scale-95'
                    : 'border-zinc-700 bg-zinc-900 cursor-grab hover:border-zinc-500'
                  }
                `}
              >
                <div className="flex gap-1">
                  {r.rolls.map((d, di) => (
                    <Dieface key={di} value={d} isDropped={d === r.dropped && di === r.rolls.indexOf(r.dropped)} />
                  ))}
                </div>
                <span className={`text-lg font-bold tabular-nums ${isUsed ? 'text-zinc-600' : 'text-zinc-100'}`}>
                  {r.total}
                </span>
              </div>
            );
          })}
        </div>
      )}

      {/* Stat assignment targets */}
      <div className="grid grid-cols-2 gap-2">
        {STAT_KEYS.map(key => {
          const isAssigned  = assigned[key] !== undefined;
          const finalScore  = getFinalScore(key);
          const bonus       = racialBonus[key];

          return (
            <div
              key={key}
              onDragOver={e => e.preventDefault()}
              onDrop={() => handleDrop(key)}
              onClick={() => isAssigned && unassign(key)}
              className={`
                flex items-center justify-between
                px-3 py-2.5 rounded-lg border transition-all duration-150
                ${dragging !== null && !isAssigned
                  ? 'border-emerald-600/60 bg-emerald-900/10 cursor-copy'
                  : isAssigned
                  ? 'border-emerald-700 bg-emerald-900/20 cursor-pointer'
                  : 'border-zinc-700 bg-zinc-900'
                }
              `}
            >
              <span className="text-xs text-zinc-400">{STAT_LABELS[key]}</span>
              <div className="flex items-center gap-2">
                {bonus && isAssigned && (
                  <span className="text-xs text-emerald-600">+{bonus}</span>
                )}
                <span className={`text-sm font-bold tabular-nums ${isAssigned ? 'text-zinc-100' : 'text-zinc-600'}`}>
                  {finalScore ?? '—'}
                </span>
                {isAssigned && (
                  <span className="text-xs text-zinc-500">
                    ({modifier(finalScore)})
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {Object.keys(assigned).length === 6 && (
        <p className="text-xs text-emerald-500 text-center">
          All stats assigned. Click any stat to unassign it.
        </p>
      )}

    </div>
  );
}

// ── Screen 3: Confirm ─────────────────────────────────────────────────────────

function ScreenConfirm({ form, onBegin, isLoading }) {
  const racialBonus = form.racialBonus ?? {};
  const rolls       = form.rollResults ?? [];
  const assigned    = form.assignedStats ?? {};

  const getScore = (key) => {
    if (assigned[key] === undefined || !rolls.length) return 10;
    return (rolls[assigned[key]]?.total ?? 10) + (racialBonus[key] ?? 0);
  };

  const conScore = getScore('con');
  const dexScore = getScore('dex');
  const hp       = calcHp(form.classData, conScore);
  const ac       = calcAc(dexScore);
  const wb       = WORLD_BIBLES.find(w => w.id === form.worldBible);

  return (
    <div className="space-y-5">

      {/* Identity summary */}
      <div className="p-4 bg-zinc-900/60 border border-zinc-700 rounded-lg space-y-1">
        <p className="text-base font-bold text-zinc-100">{form.name || 'Unnamed'}</p>
        <p className="text-xs text-zinc-400">
          {form.race} {form.charClass} &nbsp;·&nbsp; {form.background} &nbsp;·&nbsp; {form.alignment}
        </p>
        {wb && (
          <p className="text-xs text-emerald-600 italic mt-1">{wb.name} — {wb.tagline}</p>
        )}
      </div>

      {/* Stat grid */}
      <div className="grid grid-cols-3 gap-2">
        {STAT_KEYS.map(key => (
          <div key={key} className="text-center p-2 bg-zinc-900 border border-zinc-800 rounded-lg">
            <p className="text-xs text-zinc-500">{STAT_LABELS[key].slice(0,3).toUpperCase()}</p>
            <p className="text-lg font-bold text-zinc-100 tabular-nums">{getScore(key)}</p>
            <p className="text-xs text-zinc-500">{modifier(getScore(key))}</p>
          </div>
        ))}
      </div>

      {/* Derived stats */}
      <div className="flex gap-3">
        <div className="flex-1 text-center p-3 bg-red-900/20 border border-red-900/50 rounded-lg">
          <p className="text-xs text-red-400">Max HP</p>
          <p className="text-2xl font-bold text-red-300 tabular-nums">{hp}</p>
        </div>
        <div className="flex-1 text-center p-3 bg-blue-900/20 border border-blue-900/50 rounded-lg">
          <p className="text-xs text-blue-400">Armour Class</p>
          <p className="text-2xl font-bold text-blue-300 tabular-nums">{ac}</p>
        </div>
        <div className="flex-1 text-center p-3 bg-yellow-900/20 border border-yellow-900/50 rounded-lg">
          <p className="text-xs text-yellow-400">Starting GP</p>
          <p className="text-2xl font-bold text-yellow-300 tabular-nums">50</p>
        </div>
      </div>

      {/* Backstory anchors */}
      {form.backstoryAnchors.some(a => a.trim()) && (
        <div className="p-3 bg-zinc-900 border border-zinc-700 rounded-lg space-y-1">
          <p className="text-xs text-zinc-500 mb-2">Backstory anchors</p>
          {form.backstoryAnchors.filter(a => a.trim()).map((a, i) => (
            <p key={i} className="text-xs text-zinc-300">· {a}</p>
          ))}
        </div>
      )}

      {/* Begin button */}
      <button
        type="button"
        onClick={onBegin}
        disabled={isLoading}
        className="w-full py-3 rounded-lg bg-emerald-700 hover:bg-emerald-600 text-white font-bold text-sm transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
      >
        {isLoading ? (
          <>
            <RefreshCw size={16} className="animate-spin" />
            The realm stirs...
          </>
        ) : (
          <>
            <Check size={16} />
            Begin the Chronicle
          </>
        )}
      </button>

    </div>
  );
}

// ── Loading Cinematic ─────────────────────────────────────────────────────────

function LoadingCinematic({ worldBible }) {
  const wb     = WORLD_BIBLES.find(w => w.id === worldBible);
  const lines  = [
    'The threads of fate are being woven...',
    'Ancient forces take notice...',
    `The ${wb?.name ?? 'Forgotten Realm'} awaits...`,
    'Your chronicle begins.',
  ];
  const [lineIdx, setLineIdx] = useState(0);

  useEffect(() => {
    if (lineIdx >= lines.length - 1) return;
    const t = setTimeout(() => setLineIdx(i => i + 1), 1400);
    return () => clearTimeout(t);
  }, [lineIdx]);

  return (
    <div className="fixed inset-0 bg-zinc-950 flex flex-col items-center justify-center z-50">
      <div className="text-center space-y-6 px-8 max-w-sm">
        <div className="flex justify-center gap-1.5">
          {[0,1,2].map(i => (
            <div
              key={i}
              className="w-2 h-2 rounded-full bg-emerald-500 animate-bounce"
              style={{ animationDelay: `${i * 0.2}s` }}
            />
          ))}
        </div>
        <p className="text-zinc-300 text-sm italic transition-all duration-700">
          {lines[lineIdx]}
        </p>
        {wb && (
          <p className="text-zinc-600 text-xs">{wb.description}</p>
        )}
      </div>
    </div>
  );
}

// ── Root SessionZero ──────────────────────────────────────────────────────────

const INITIAL_FORM = {
  name:            '',
  race:            '',
  racialBonus:     {},
  charClass:       '',
  classData:       null,
  background:      '',
  alignment:       '',
  worldBible:      '',
  backstoryAnchors: ['', '', ''],
  rollResults:     null,
  assignedStats:   {},
};

function canAdvance(step, form) {
  if (step === 0) {
    return (
      form.name.trim() &&
      form.race &&
      form.charClass &&
      form.background &&
      form.alignment &&
      form.worldBible
    );
  }
  if (step === 1) {
    return Object.keys(form.assignedStats).length === 6;
  }
  return true;
}

export default function SessionZero({ onComplete }) {
  const [step, setStep]       = useState(0);
  const [form, setForm]       = useState(INITIAL_FORM);
  const [loading, setLoading] = useState(false);
  const [cinematic, setCinematic] = useState(false);

  const STEPS = [
    { label: 'Identity',       component: <ScreenIdentity form={form} setForm={setForm} /> },
    { label: 'Ability Scores', component: <ScreenStats    form={form} setForm={setForm} /> },
    { label: 'Confirm',        component: null },
  ];

  const handleBegin = async () => {
    setLoading(true);

    // Build the character payload
    const racialBonus  = form.racialBonus ?? {};
    const rolls        = form.rollResults ?? [];
    const assigned     = form.assignedStats ?? {};
    const getScore     = (k) => (rolls[assigned[k]]?.total ?? 10) + (racialBonus[k] ?? 0);
    const conScore     = getScore('con');
    const dexScore     = getScore('dex');
    const hp           = calcHp(form.classData, conScore);
    const ac           = calcAc(dexScore);
    const wb           = WORLD_BIBLES.find(w => w.id === form.worldBible);

    const character = {
      name:           form.name,
      race:           form.race,
      char_class:     form.charClass,
      background:     form.background,
      alignment:      form.alignment,
      level:          1,
      hp_current:     hp,
      hp_max:         hp,
      armor_class:    ac,
      gold_pieces:    50,
      inventory:      ['Bedroll', 'Rations (5 days)', 'Torch (3)'],
      status_effects: [],
      hunger_level:   'Sated',
      morality_score: 50,
      ability_scores: {
        str: getScore('str'), dex: getScore('dex'), con: getScore('con'),
        int: getScore('int'), wis: getScore('wis'), cha: getScore('cha'),
      },
    };

    const world = {
      world_bible:      form.worldBible,
      world_bible_name: wb?.name ?? '',
      world_description: wb?.description ?? '',
      backstory_anchors: form.backstoryAnchors.filter(a => a.trim()),
      current_location: 'Unknown',
      time_of_day:      'Dawn',
      tension_level:    1,
    };

    try {
      // POST to backend — initialises session_context
      await fetch('http://localhost:8000/api/session/create', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ character, world }),
      });
    } catch (err) {
      console.error('[SessionZero] Backend POST failed:', err);
      // Continue anyway — ws_router will use defaults
    }

    setLoading(false);
    setCinematic(true);

    // Show cinematic for 5.6s then enter game
    setTimeout(() => onComplete({ character, world }), 5600);
  };

  if (cinematic) {
    return <LoadingCinematic worldBible={form.worldBible} />;
  }

  const currentCan = canAdvance(step, form);

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-zinc-950 px-4 py-8">
      <div className="w-full max-w-xl">

        {/* Header */}
        <div className="mb-8 text-center">
          <h1 className="text-2xl font-bold text-emerald-400 tracking-wide mb-1">
            Session Zero
          </h1>
          <p className="text-zinc-600 text-sm">Forge your legend before the chronicle begins.</p>
        </div>

        {/* Step dots */}
        <div className="flex items-center justify-between mb-6">
          <StepDots current={step} total={STEPS.length} />
          <span className="text-xs text-zinc-600">{STEPS[step].label}</span>
        </div>

        {/* Screen body */}
        <div className="bg-zinc-900/40 border border-zinc-800 rounded-xl p-6 mb-6">
          {step === 2
            ? <ScreenConfirm form={form} onBegin={handleBegin} isLoading={loading} />
            : STEPS[step].component
          }
        </div>

        {/* Navigation */}
        {step < 2 && (
          <div className="flex items-center justify-between">
            <button
              type="button"
              onClick={() => setStep(s => Math.max(0, s - 1))}
              disabled={step === 0}
              className="flex items-center gap-1 text-xs text-zinc-500 hover:text-zinc-300 disabled:opacity-20 transition-colors"
            >
              <ChevronLeft size={14} /> Back
            </button>
            <button
              type="button"
              onClick={() => setStep(s => s + 1)}
              disabled={!currentCan}
              className="flex items-center gap-1.5 text-sm px-5 py-2.5 rounded-lg bg-emerald-700 hover:bg-emerald-600 text-white font-medium transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
            >
              {step === 1 ? 'Review' : 'Next'} <ChevronRight size={14} />
            </button>
          </div>
        )}

      </div>
    </div>
  );
}