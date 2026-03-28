import { useState, useEffect, useRef, useCallback } from 'react';

export const useGameSocket = (url) => {
    const [messages, setMessages] = useState([]);
    const [isConnected, setIsConnected] = useState(false);
    const [isStreaming, setIsStreaming] = useState(false);
    const [gameState, setGameState] = useState({
        character: {
            name: 'Adventurer',
            level: 1,
            hp_current: 10,
            hp_max: 10,
            armor_class: 10,
            gold_pieces: 0,
            inventory: [],
            status_effects: [],
            hunger_level: 'Sated',
            morality_score: 50,
        },
        world: {},
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

            // state_update from event bus — merges delta, no chat bubble
            if (message_type === 'state_update' && metadata?.delta) {
                setGameState(prev => ({
                    ...prev,
                    character: {
                        ...prev.character,
                        ...metadata.delta,
                    },
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
        if (!socketRef.current || !isConnected) return;

        // Send a special system message that ws_router uses to
        // seed session_context with the full character + world
        const payload = {
            sender:       'System',
            message_type: 'session_init',
            content:      'Session initialised.',
            metadata:     {
            character: sessionData.character,
            world:     sessionData.world,
            },
        };
        socketRef.current.send(JSON.stringify(payload));
    }, [isConnected]);

    // Single return at the bottom — includes gameState
    return { messages, isConnected, isStreaming, sendMessage, gameState, initSession };

};