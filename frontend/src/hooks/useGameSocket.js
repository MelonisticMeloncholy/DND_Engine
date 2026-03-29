import { useState, useEffect, useRef, useCallback } from 'react';

export const useGameSocket = (url) => {
    const [messages, setMessages] = useState([]);
    const [isConnected, setIsConnected] = useState(false);
    const [isStreaming, setIsStreaming] = useState(false);
    const [gameState, setGameState] = useState(() => {
        const defaultState = {
            character: {
                name: 'Adventurer', level: 1,
                hp_current: 10, hp_max: 10,
                armor_class: 10, gold_pieces: 0,
                inventory: [], status_effects: [],
                hunger_level: 'Sated', morality_score: 50,
            },
            world: {},
            combat: null,
        };
        try {
            const saved = sessionStorage.getItem('chronicles_gamestate');
            if (!saved) return defaultState;
            const parsed = JSON.parse(saved);
            // Validate it has the required shape before trusting it
            if (!parsed?.character?.name) return defaultState;
            return parsed;
        } catch {
            sessionStorage.clear(); // nuke corrupted state
            return defaultState;
        }
    });

    const socketRef = useRef(null);
    const activeTurnRef = useRef(null);  // tracks the current streaming bubble ID

    useEffect(() => {
        const ws = new WebSocket(url);
        socketRef.current = ws;

        ws.onopen = () => {
            console.log('[WS] Connected to The Forgotten Realm');
            setIsConnected(true);
        };

        ws.onmessage = (event) => {
            let msg;
            try {
                msg = JSON.parse(event.data);
            } catch {
                console.error('[WS] Could not parse message:', event.data);
                return;
            }

            const { sender, message_type, content, metadata } = msg;

            // stream_start — create empty DM bubble
            if (message_type === 'system_alert' && content === 'stream_start') {
                const turnId = metadata?.turn_id ?? Date.now().toString();
                activeTurnRef.current = turnId;
                setIsStreaming(true);
                setMessages(prev => [...prev, {
                    id: turnId,
                    sender: 'DM',
                    message_type: 'narrative',
                    content: '',
                    streaming: true,
                }]);
                return;
            }

            // Streaming chunk — append token to active bubble
            if (
                sender === 'DM' &&
                message_type === 'narrative' &&
                metadata?.chunk === true &&
                activeTurnRef.current
            ) {
                const turnId = activeTurnRef.current;
                setMessages(prev => prev.map(m =>
                    m.id === turnId ? { ...m, content: m.content + content } : m
                ));
                return;
            }

            // stream_end — finalize bubble
            if (message_type === 'system_alert' && content === 'stream_end') {
                const turnId = activeTurnRef.current;
                setIsStreaming(false);
                activeTurnRef.current = null;
                setMessages(prev => prev.map(m =>
                    m.id === turnId ? { ...m, streaming: false } : m
                ));
                return;
            }
            if (message_type === 'session_ready' && metadata) {
                if (metadata.character) {
                    setGameState(prev => {
                        const next = {
                            ...prev,
                            character: { ...prev.character, ...metadata.character },
                            world:     metadata.world ?? prev.world,
                        };
                        try { sessionStorage.setItem('chronicles_gamestate', JSON.stringify(next)); } catch {}
                        return next;
                    });
                }
                return;
            }

            // state_update from event bus — merges delta, no chat bubble
            if (message_type === 'state_update' && metadata?.delta) {
                setGameState(prev => ({
                    ...prev,
                    character: {
                        ...prev.character,
                        ...metadata.delta,
                    },
                    // Combat state lives at top level, not inside character
                    ...(metadata.delta.combat !== undefined && {
                        combat: metadata.delta.combat,
                    }),
                }));
                return;
            }

            // Everything else — errors, unhandled system alerts
            setMessages(prev => [...prev, {
                id: Date.now().toString(),
                sender,
                message_type,
                content,
                metadata,
                streaming: false,
            }]);
        };

        ws.onclose = () => {
            console.log('[WS] Disconnected');
            setIsConnected(false);
            setIsStreaming(false);
            activeTurnRef.current = null;
        };

        ws.onerror = (err) => {
            console.error('[WS] Error:', err);
        };

        return () => ws.close();
    }, [url]);

    const sendMessage = useCallback((content) => {
        if (!socketRef.current || !isConnected) return;

        const payload = {
            sender: 'User',
            message_type: 'narrative',
            content,
            metadata: {},
        };

        // Optimistic UI — show user message immediately without waiting for server
        setMessages(prev => [...prev, {
            id: Date.now().toString(),
            sender: 'User',
            message_type: 'narrative',
            content,
            streaming: false,
        }]);

        socketRef.current.send(JSON.stringify(payload));
    }, [isConnected]);

    const initSession = useCallback((sessionData) => {
        if (!socketRef.current) return;

        // Seed gameState immediately with Session Zero data
        // so the name is present before any state_update arrives
        if (sessionData?.character) {
            setGameState(prev => ({
                ...prev,
                character: {
                    ...prev.character,
                    ...sessionData.character,
                },
            }));
        }

        // Wait for connection before sending the init message
        const sendInit = () => {
            const payload = {
                sender:       'System',
                message_type: 'session_init',
                content:      'Session initialised.',
                metadata: {
                    character: sessionData.character,
                    world:     sessionData.world,
                },
            };
            socketRef.current.send(JSON.stringify(payload));
        };

        // Socket may not be open yet if this fires right after mount
        if (socketRef.current.readyState === WebSocket.OPEN) {
            sendInit();
        } else {
            socketRef.current.addEventListener('open', sendInit, { once: true });
        }
    }, []);
    const loadSession = useCallback((sessionId) => {
        const send = () => {
            const payload = {
                sender:       'System',
                message_type: 'session_load',
                content:      'Loading saved session.',
                metadata:     { session_id: sessionId },
            };
            socketRef.current.send(JSON.stringify(payload));
        };

        if (socketRef.current?.readyState === WebSocket.OPEN) {
            send();
        } else {
            socketRef.current?.addEventListener('open', send, { once: true });
        }
    }, []);

    // Single return at the bottom — includes gameState
    return { messages, isConnected, isStreaming, sendMessage, gameState, initSession };

};