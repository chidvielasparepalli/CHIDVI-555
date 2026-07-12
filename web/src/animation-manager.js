import * as THREE from 'three'

/**
 * AnimationManager
 * ----------------
 * Loads, caches, blends, and plays Mixamo FBX animations on the
 * currently active VRM. Supports cross-fading, priority queuing,
 * automatic return-to-idle loop, state mapping, emotion mapping,
 * and personality profiles.
 *
 * Design notes:
 * - No side effects on import. Call createAnimationManager(loader) to build one.
 * - Owns no mixer. The renderer binds the current mixer via bindMixer()
 *   after every avatar load/switch so clips always target the live skeleton.
 */

// ---------------------------------------------------------------------------
// Animation registry
// Semantic name -> file URL under /public/animations/
// ---------------------------------------------------------------------------
const ANIMATION_MAP = {
    // Idle loops
    idle:           '/animations/idle.fbx',
    breathing_idle: '/animations/breathing_idle.fbx',
    sad_idle:       '/animations/sad_idle.fbx',
    // Greetings / one-shot gestures
    wave:           '/animations/wave.fbx',
    wave2:          '/animations/wave2.fbx',
    bow:            '/animations/bow.fbx',
    clap:           '/animations/clap.fbx',
    nod:            '/animations/nod.fbx',
    shake_head:     '/animations/shake_head.fbx',
    shrug:          '/animations/shrug.fbx',
    salute:         '/animations/salute.fbx',
    jump:           '/animations/jump.fbx',
    blow_kiss:      '/animations/blow_kiss.fbx',
    blow_kiss2:     '/animations/blow_kiss2.fbx',
    // Emotions
    happy:          '/animations/happy.fbx',
    laughing:       '/animations/laughing.fbx',
    angry:          '/animations/angry.fbx',
    bashful:        '/animations/bashful.fbx',
    cheer:          '/animations/cheer.fbx',
    yell:           '/animations/yell.fbx',
    thinking:       '/animations/thinking.fbx',
    // Talking variants
    talking:        '/animations/talking.fbx',
    talking2:       '/animations/talking2.fbx',
    secret:         '/animations/secret.fbx',
    pointing:       '/animations/pointing.fbx',
}

// ---------------------------------------------------------------------------
// Phase 8: Personality animation profiles
// ---------------------------------------------------------------------------
const PERSONALITY_PROFILES = {
    CHIDVI: {
        idle: 'idle',
        listening: 'breathing_idle',
        thinking: 'thinking',
        speaking: ['talking', 'talking2'],
        gestures: ['wave', 'nod', 'clap'],
        minimalGestures: true,
        name: 'CHIDVI'
    },
    HINATA: {
        idle: 'breathing_idle',
        listening: 'breathing_idle',
        thinking: 'thinking',
        speaking: ['talking', 'talking2', 'secret'],
        gestures: ['wave2', 'bow', 'clap', 'cheer', 'jump', 'bashful'],
        minimalGestures: false,
        name: 'HINATA'
    }
}

// ---------------------------------------------------------------------------
// Phase 9: Priority levels (higher number = higher priority)
// ---------------------------------------------------------------------------
const PRIORITY = {
    MANUAL_GESTURE: 10,
    EMOTION: 8,
    SPEAKING: 6,
    LISTENING: 4,
    IDLE: 0
}

// ---------------------------------------------------------------------------
// Phase 5: runtime state -> animation name
// ---------------------------------------------------------------------------
const STATE_ANIMATIONS = {
    listening:   'breathing_idle',
    thinking:    'thinking',
    speaking:    'talking',
    idle:        'idle',
}

// ---------------------------------------------------------------------------
// Phase 7: emotion -> animation name
// ---------------------------------------------------------------------------
const EMOTION_ANIMATIONS = {
    happy:       'happy',
    sad:         'sad_idle',
    thinking:    'thinking',
    excited:     'cheer',
    embarrassed: 'bashful',
    angry:       'angry',
    laughing:    'laughing',
    laugh:       'laughing',
}

// ---------------------------------------------------------------------------
// Phase 6: Available gestures
// ---------------------------------------------------------------------------
const GESTURES = [
    'wave', 'wave2', 'salute', 'bow', 'clap', 'point',
    'shrug', 'nod', 'shake_head', 'jump'
]

const DEFAULT_CROSS_FADE = 0.35   // seconds
const DEFAULT_IDLE = 'idle'
const EPSILON = 0.0001

/**
 * Build an AnimationManager bound to a THREE.FBXLoader instance.
 *
 * @param {THREE.FBXLoader} loader
 * @returns {object} AnimationManager API
 */
export function createAnimationManager(loader) {
    // --- state -------------------------------------------------------------
    const clipCache = new Map()      // url -> AnimationClip[]
    const actionCache = new Map()    // clip.uuid -> AnimationAction (per mixer lifecycle)
    let mixer = null
    let currentAction = null
    let idleAction = null
    let idleName = DEFAULT_IDLE
    let currentState = 'idle'
    let pendingFade = null
    let fbxActive = false
    let crossFadeDuration = DEFAULT_CROSS_FADE
    let debug = false
    let activeName = null
    let currentPriority = PRIORITY.IDLE
    let currentProfile = PERSONALITY_PROFILES.CHIDVI
    const priorityQueue = [] // { name, priority, type, afterPlay }

    // -------------------------------------------------------------------------
    // Internal helpers
    // -------------------------------------------------------------------------

    function log(...args) {
        if (debug) console.info('[AnimManager]', ...args)
    }

    function warn(...args) {
        console.warn('[AnimManager]', ...args)
    }

    function urlFor(name) {
        return ANIMATION_MAP[name] || null
    }

    function randomItem(arr) {
        return arr[Math.floor(Math.random() * arr.length)]
    }

    /**
     * Load (and cache) the AnimationClip[] for a semantic animation name.
     */
    async function loadClips(name) {
        const url = urlFor(name)
        if (!url) {
            warn(`Unknown animation name: ${name}`)
            return null
        }
        if (clipCache.has(url)) {
            return clipCache.get(url)
        }
        try {
            const result = await loader.loadAsync(url)
            const clips = result.animations || []
            if (clips.length === 0) {
                warn(`No animations found in ${url}`)
                return null
            }
            clipCache.set(url, clips)
            log(`Loaded ${name} (${clips.length} clip(s)) from ${url}`)
            return clips
        } catch (err) {
            warn(`Failed to load animation ${name} (${url}):`, err?.message || err)
            return null
        }
    }

    /**
     * Create or fetch a cached AnimationAction for a clip on the current mixer.
     */
    function actionFor(clip) {
        if (!mixer) return null
        const key = clip.uuid
        if (actionCache.has(key)) {
            return actionCache.get(key)
        }
        const action = mixer.clipAction(clip)
        actionCache.set(key, action)
        return action
    }

    /**
     * Stop and forget a single action (fade out gracefully if requested).
     */
    function stopAction(action, fadeSeconds = 0) {
        if (!action) return
        if (fadeSeconds > 0) {
            action.fadeOut(fadeSeconds)
        } else {
            action.stop()
        }
    }

    /**
     * Begin a managed cross-fade between two actions.
     */
    function startCrossFade(fromAction, toAction, duration, onDone) {
        if (!toAction) {
            if (onDone) onDone()
            return
        }
        toAction.reset()
        toAction.setEffectiveWeight(0)
        toAction.setEnabled(true)
        toAction.play()

        pendingFade = {
            from: fromAction,
            to: toAction,
            t: 0,
            duration: Math.max(EPSILON, duration),
            onDone: onDone || null,
        }
    }

    /**
     * Advance the active cross-fade. Called every frame from update().
     */
    function tickCrossFade(delta) {
        if (!pendingFade) return
        pendingFade.t += delta
        const k = Math.min(1, pendingFade.t / pendingFade.duration)

        if (pendingFade.from) {
            pendingFade.from.setEffectiveWeight(1 - k)
        }
        if (pendingFade.to) {
            pendingFade.to.setEffectiveWeight(k)
        }

        if (k >= 1) {
            if (pendingFade.from) {
                pendingFade.from.stop()
                pendingFade.from.setEffectiveWeight(1)
            }
            const done = pendingFade.onDone
            pendingFade = null
            if (done) done()
        }
    }

    function setFBXActive(value) {
        fbxActive = value
    }

    /**
     * Play the idle loop (looping).
     */
    function ensureIdle() {
        if (!mixer) return null
        if (idleAction) {
            return idleAction
        }
        loadClips(idleName).then((clips) => {
            if (!clips || !mixer || idleAction) return
            const action = actionFor(clips[0])
            if (!action) return
            action.setLoop(THREE.LoopRepeat, Infinity)
            action.clampWhenFinished = false
            action.setEffectiveWeight(currentAction ? 0 : 1)
            action.setEnabled(true)
            action.play()
            idleAction = action
            log(`Idle loop started: ${idleName}`)
        })
        return null
    }

    /**
     * Called when a non-idle action finishes.
     * Drains the priority queue, otherwise returns to idle.
     */
    function onActionFinished() {
        log(`Action finished: ${activeName}`)
        const finishedAction = currentAction
        currentAction = null
        activeName = null
        currentPriority = PRIORITY.IDLE

        // Check priority queue for next item
        if (priorityQueue.length > 0) {
            // Sort queue by priority descending, then pick first
            priorityQueue.sort((a, b) => b.priority - a.priority)
            const next = priorityQueue.shift()
            log(`Priority queue -> playing next: ${next.name} (priority: ${next.priority})`)
            if (next.type === 'gesture') {
                playGesture(next.name, next.afterPlay)
            } else if (next.type === 'emotion') {
                playEmotion(next.name, next.afterPlay)
            } else if (next.type === 'state') {
                playState(next.name)
            }
            return
        }

        // Return to idle
        if (idleAction && finishedAction) {
            startCrossFade(finishedAction, idleAction, crossFadeDuration, () => {
                setFBXActive(false)
            })
        } else if (idleAction) {
            idleAction.setEffectiveWeight(1)
            setFBXActive(false)
        } else {
            setFBXActive(false)
            ensureIdle()
        }
    }

    /**
     * Play a one-shot (non-looping) animation.
     */
    function playOneShot(name, afterPlay, priorityOverride) {
        const priority = priorityOverride || PRIORITY.EMOTION
        if (currentPriority > priority) {
            log(`Skipping ${name} (priority ${priority}) - current is higher (${currentPriority})`)
            return
        }

        loadClips(name).then((clips) => {
            if (!clips || !mixer) {
                warn(`Cannot play ${name}: no clips or no mixer`)
                return
            }
            const clip = clips[0]
            const next = actionFor(clip)
            if (!next) return

            next.setLoop(THREE.LoopOnce, 1)
            next.clampWhenFinished = true
            next.time = 0

            mixer.removeEventListener('finished', finishedHandler)
            finishedHandler = (event) => {
                if (event.action === next) {
                    onActionFinished()
                    if (afterPlay) afterPlay()
                }
            }
            mixer.addEventListener('finished', finishedHandler)

            const from = currentAction || idleAction
            currentPriority = priority
            startCrossFade(from, next, crossFadeDuration, () => {
                currentAction = next
                activeName = name
                setFBXActive(true)
                log(`Playing: ${name} (priority: ${priority})`)
            })
        })
    }

    /**
     * Play a looping animation (for states like listening, thinking, speaking).
     */
    function playLooping(name, priorityOverride) {
        const priority = priorityOverride || PRIORITY.LISTENING
        if (currentPriority > priority) {
            log(`Skipping looping ${name} (priority ${priority}) - current is higher (${currentPriority})`)
            return
        }

        loadClips(name).then((clips) => {
            if (!clips || !mixer) {
                warn(`Cannot play loop ${name}: no clips or no mixer`)
                return
            }
            const clip = clips[0]
            const next = actionFor(clip)
            if (!next) return

            next.setLoop(THREE.LoopRepeat, Infinity)
            next.clampWhenFinished = false
            next.time = 0

            const from = currentAction || idleAction
            currentPriority = priority
            startCrossFade(from, next, crossFadeDuration, () => {
                if (name === idleName) {
                    idleAction = next
                    currentAction = null
                    activeName = null
                    setFBXActive(false)
                } else {
                    currentAction = next
                    activeName = name
                    setFBXActive(true)
                }
                log(`Looping: ${name} (priority: ${priority})`)
            })
        })
    }

    // Holder for the current mixer 'finished' listener
    let finishedHandler = null

    // -------------------------------------------------------------------------
    // Phase 5: State mapping
    // -------------------------------------------------------------------------
    function playState(state) {
        const key = String(state || 'idle').toLowerCase()
        currentState = key

        if (currentPriority > PRIORITY.LISTENING) {
            log(`Skipping state change to ${key} - higher priority action active`)
            return
        }

        if (key === 'idle') {
            playIdle()
        } else if (key === 'speaking') {
            // Random talking variation
            const speakingAnim = randomItem(currentProfile.speaking || ['talking', 'talking2'])
            playLooping(speakingAnim, PRIORITY.SPEAKING)
        } else if (key === 'thinking') {
            playLooping('thinking', PRIORITY.LISTENING)
        } else if (key === 'listening') {
            playLooping(currentProfile.listening || 'breathing_idle', PRIORITY.LISTENING)
        }
    }

    // -------------------------------------------------------------------------
    // Phase 6: Gesture dispatcher
    // -------------------------------------------------------------------------
    function playGesture(name, afterPlay) {
        if (!GESTURES.includes(name)) {
            warn(`Unknown gesture: ${name}`)
            return
        }

        if (currentPriority > PRIORITY.MANUAL_GESTURE) {
            log(`Queuing gesture ${name} (priority ${PRIORITY.MANUAL_GESTURE})`)
            priorityQueue.push({ name, priority: PRIORITY.MANUAL_GESTURE, type: 'gesture', afterPlay })
            return
        }

        playOneShot(name, afterPlay, PRIORITY.MANUAL_GESTURE)
    }

    function queueGesture(name, afterPlay) {
        priorityQueue.push({ name, priority: PRIORITY.MANUAL_GESTURE, type: 'gesture', afterPlay })
        log(`Queued gesture: ${name} (priority ${PRIORITY.MANUAL_GESTURE})`)
    }

    // -------------------------------------------------------------------------
    // Phase 7: Emotion dispatcher
    // -------------------------------------------------------------------------
    function playEmotion(name, afterPlay) {
        const anim = EMOTION_ANIMATIONS[name.toLowerCase()]
        if (!anim) {
            warn(`Unknown emotion: ${name}`)
            return
        }

        if (currentPriority > PRIORITY.EMOTION) {
            log(`Queuing emotion ${name} (priority ${PRIORITY.EMOTION})`)
            priorityQueue.push({ name: anim, priority: PRIORITY.EMOTION, type: 'emotion', afterPlay })
            return
        }

        playOneShot(anim, afterPlay, PRIORITY.EMOTION)
    }

    function queueEmotion(name, afterPlay) {
        const anim = EMOTION_ANIMATIONS[name.toLowerCase()]
        if (anim) {
            priorityQueue.push({ name: anim, priority: PRIORITY.EMOTION, type: 'emotion', afterPlay })
            log(`Queued emotion: ${name} (priority ${PRIORITY.EMOTION})`)
        }
    }

    // -------------------------------------------------------------------------
    // Public API
    // -------------------------------------------------------------------------

    const api = {
        bindMixer(newMixer) {
            if (mixer === newMixer) return
            if (finishedHandler && mixer) {
                mixer.removeEventListener('finished', finishedHandler)
            }
            mixer = newMixer
            actionCache.clear()
            currentAction = null
            idleAction = null
            activeName = null
            pendingFade = null
            priorityQueue.length = 0
            currentPriority = PRIORITY.IDLE
            setFBXActive(false)
            log(`Mixer bound: ${mixer ? 'yes' : 'no'}`)
        },

        async preload(names) {
            const list = Array.isArray(names) ? names : [names]
            await Promise.all(
                list.map(async (entry) => {
                    const name = entryToName(entry)
                    if (name) await loadClips(name)
                })
            )
        },

        playIdle(name) {
            if (name) {
                idleName = name
            } else {
                idleName = currentProfile.idle || DEFAULT_IDLE
            }
            currentState = 'idle'
            currentPriority = PRIORITY.IDLE
            ensureIdle()
        },

        play(name, options = {}) {
            if (options.crossFadeDuration != null) {
                crossFadeDuration = options.crossFadeDuration
            }
            if (options.loop) {
                playLooping(name, options.priority)
            } else {
                playOneShot(name, options.afterPlay || null, options.priority)
            }
        },

        playGesture,
        queueGesture,

        playEmotion,
        queueEmotion,

        playState,

        setProfile(profileName) {
            const profile = PERSONALITY_PROFILES[profileName.toUpperCase()]
            if (profile) {
                currentProfile = profile
                idleName = profile.idle || DEFAULT_IDLE
                log(`Set profile: ${profile.name}`)
            } else {
                warn(`Unknown profile: ${profileName}`)
            }
        },

        queueAnimation(name) {
            priorityQueue.push({ name, priority: PRIORITY.EMOTION, type: 'gesture' })
            log(`Queued: ${name} (queue len=${priorityQueue.length})`)
        },

        clearQueue() {
            priorityQueue.length = 0
        },

        stop() {
            priorityQueue.length = 0
            if (currentAction) {
                startCrossFade(currentAction, idleAction, crossFadeDuration, () => {
                    setFBXActive(false)
                    currentPriority = PRIORITY.IDLE
                })
                currentAction = null
                activeName = null
            }
        },

        onStateChange(stateOrEmotion) {
            const key = String(stateOrEmotion || 'idle').toLowerCase()
            if (STATE_ANIMATIONS[key]) {
                playState(key)
            } else if (EMOTION_ANIMATIONS[key]) {
                playEmotion(key)
            } else {
                currentState = 'idle'
                playIdle()
            }
        },

        update(delta) {
            if (!mixer) return
            tickCrossFade(delta)
        },

        isFBXActive() {
            return fbxActive
        },

        hasAnimation(name) {
            return Boolean(urlFor(name))
        },

        getActiveName() {
            return activeName
        },

        getCurrentState() {
            return currentState
        },

        getCurrentProfile() {
            return currentProfile.name
        },

        setDebug(value) {
            debug = Boolean(value)
        },

        // Phase 10: Enhanced diagnostics
        getDiagnostics() {
            return {
                mixerBound: Boolean(mixer),
                fbxActive,
                activeName,
                currentState,
                idleName,
                idleActionAlive: Boolean(idleAction),
                hasCurrentAction: Boolean(currentAction),
                currentPriority,
                currentProfile: currentProfile.name,
                queue: [...priorityQueue],
                queueLength: priorityQueue.length,
                cachedClips: clipCache.size,
                cachedClipNames: Array.from(clipCache.keys()).map(url => {
                    for (const [name, u] of Object.entries(ANIMATION_MAP)) {
                        if (u === url) return name
                    }
                    return url
                }),
                pendingFade: Boolean(pendingFade),
                blendProgress: pendingFade ? Math.min(1, pendingFade.t / pendingFade.duration) : 1,
                availableGestures: GESTURES,
                availableEmotions: Object.keys(EMOTION_ANIMATIONS)
            }
        },

        unbindMixer() {
            if (finishedHandler && mixer) {
                mixer.removeEventListener('finished', finishedHandler)
            }
            finishedHandler = null
            actionCache.forEach((action) => {
                try { action.stop() } catch (_) { /* noop */ }
            })
            actionCache.clear()
            currentAction = null
            idleAction = null
            activeName = null
            pendingFade = null
            priorityQueue.length = 0
            currentPriority = PRIORITY.IDLE
            setFBXActive(false)
            mixer = null
            log('Unbound mixer (clips kept cached)')
        },

        dispose() {
            api.unbindMixer()
            clipCache.clear()
            log('Disposed')
        },
    }

    function entryToName(entry) {
        if (!entry) return null
        if (ANIMATION_MAP[entry]) return entry
        for (const [n, u] of Object.entries(ANIMATION_MAP)) {
            if (u === entry) return n
        }
        return null
    }

    return api
}
