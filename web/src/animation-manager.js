import * as THREE from 'three'

/**
 * AnimationManager
 * ----------------
 * Loads, caches, blends, and plays Mixamo FBX animations on the
 * currently active VRM. Supports cross-fading, queueing, and an
 * automatic return-to-idle loop.
 *
 * Design notes:
 * - No side effects on import. Call createAnimationManager(loader) to build one.
 * - Owns no mixer. The renderer binds the current mixer via bindMixer()
 *   after every avatar load/switch so clips always target the live skeleton.
 * - Mixamo FBX clips use generic bone names ("mixamorigHips", ...). Before an
 *   action is created, their tracks are retargeted to the active VRM raw bones.
 * - Procedural bone animation in main.js must back off whenever an FBX clip is
 *   active. Use isFBXActive() to gate it.
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
// Phase 3: runtime state -> animation name
// ---------------------------------------------------------------------------
const STATE_ANIMATIONS = {
    listening:   'breathing_idle',
    thinking:    'thinking',
    speaking:    'talking',
    idle:        'idle',
}

// ---------------------------------------------------------------------------
// Phase 5: emotion -> animation name
// ---------------------------------------------------------------------------
const EMOTION_ANIMATIONS = {
    happy:       'happy',
    sad:         'sad_idle',
    thinking:    'thinking',
    excited:     'cheer',
    embarrassed: 'bashful',
    angry:       'angry',
    laughing:    'laughing',
}

const DEFAULT_CROSS_FADE = 0.35   // seconds
const DEFAULT_IDLE = 'idle'
const EPSILON = 0.0001

// Phase 6: Available gestures
const GESTURES = [
    'wave', 'wave2', 'salute', 'bow', 'clap', 'point',
    'shrug', 'nod', 'shake_head', 'jump'
]

// Phase 8: Personality animation profiles
const PERSONALITY_PROFILES = {
    CHIDVI: {
        idle: 'idle',
        listening: 'breathing_idle',
        thinking: 'thinking',
        speaking: ['talking', 'talking2'],
        minimalGestures: true,
        name: 'CHIDVI'
    },
    HINATA: {
        idle: 'breathing_idle',
        listening: 'breathing_idle',
        thinking: 'thinking',
        speaking: ['talking', 'talking2', 'secret'],
        minimalGestures: false,
        name: 'HINATA'
    }
}

// Phase 9: Priority levels
const PRIORITY = {
    MANUAL_GESTURE: 10,
    EMOTION: 8,
    SPEAKING: 6,
    LISTENING: 4,
    IDLE: 0
}

const MIXAMO_TO_VRM_BONE = {
    mixamorigHips: 'hips',
    mixamorigSpine: 'spine',
    mixamorigSpine1: 'chest',
    mixamorigSpine2: 'upperChest',
    mixamorigNeck: 'neck',
    mixamorigHead: 'head',
    mixamorigLeftShoulder: 'leftShoulder',
    mixamorigLeftArm: 'leftUpperArm',
    mixamorigLeftForeArm: 'leftLowerArm',
    mixamorigLeftHand: 'leftHand',
    mixamorigRightShoulder: 'rightShoulder',
    mixamorigRightArm: 'rightUpperArm',
    mixamorigRightForeArm: 'rightLowerArm',
    mixamorigRightHand: 'rightHand',
    mixamorigLeftUpLeg: 'leftUpperLeg',
    mixamorigLeftLeg: 'leftLowerLeg',
    mixamorigLeftFoot: 'leftFoot',
    mixamorigLeftToeBase: 'leftToes',
    mixamorigRightUpLeg: 'rightUpperLeg',
    mixamorigRightLeg: 'rightLowerLeg',
    mixamorigRightFoot: 'rightFoot',
    mixamorigRightToeBase: 'rightToes',
    mixamorigLeftHandThumb1: 'leftThumbMetacarpal',
    mixamorigLeftHandThumb2: 'leftThumbProximal',
    mixamorigLeftHandThumb3: 'leftThumbDistal',
    mixamorigLeftHandIndex1: 'leftIndexProximal',
    mixamorigLeftHandIndex2: 'leftIndexIntermediate',
    mixamorigLeftHandIndex3: 'leftIndexDistal',
    mixamorigLeftHandMiddle1: 'leftMiddleProximal',
    mixamorigLeftHandMiddle2: 'leftMiddleIntermediate',
    mixamorigLeftHandMiddle3: 'leftMiddleDistal',
    mixamorigLeftHandRing1: 'leftRingProximal',
    mixamorigLeftHandRing2: 'leftRingIntermediate',
    mixamorigLeftHandRing3: 'leftRingDistal',
    mixamorigLeftHandPinky1: 'leftLittleProximal',
    mixamorigLeftHandPinky2: 'leftLittleIntermediate',
    mixamorigLeftHandPinky3: 'leftLittleDistal',
    mixamorigRightHandThumb1: 'rightThumbMetacarpal',
    mixamorigRightHandThumb2: 'rightThumbProximal',
    mixamorigRightHandThumb3: 'rightThumbDistal',
    mixamorigRightHandIndex1: 'rightIndexProximal',
    mixamorigRightHandIndex2: 'rightIndexIntermediate',
    mixamorigRightHandIndex3: 'rightIndexDistal',
    mixamorigRightHandMiddle1: 'rightMiddleProximal',
    mixamorigRightHandMiddle2: 'rightMiddleIntermediate',
    mixamorigRightHandMiddle3: 'rightMiddleDistal',
    mixamorigRightHandRing1: 'rightRingProximal',
    mixamorigRightHandRing2: 'rightRingIntermediate',
    mixamorigRightHandRing3: 'rightRingDistal',
    mixamorigRightHandPinky1: 'rightLittleProximal',
    mixamorigRightHandPinky2: 'rightLittleIntermediate',
    mixamorigRightHandPinky3: 'rightLittleDistal',
}

/**
 * Build an AnimationManager bound to a THREE.FBXLoader instance.
 *
 * @param {THREE.FBXLoader} loader
 * @returns {object} AnimationManager API
 */
export function createAnimationManager(loader) {
    // --- state -------------------------------------------------------------
    // URL -> THREE.AnimationGroup-like object (the FBX root scene with .animations)
    const clipCache = new Map()      // url -> AnimationClip[]
    const actionCache = new Map()    // clip.uuid -> AnimationAction (per mixer lifecycle)
    let mixer = null
    let activeVRM = null
    let mixerGeneration = 0
    let currentAction = null         // currently playing non-idle action (or null)
    let idleAction = null            // looping idle action (always alive while bound)
    let idleName = DEFAULT_IDLE
    let currentState = 'idle'
    let queue = []
    let pendingFade = null           // { from, to, t, duration, onDone }
    let fbxActive = false            // true while an FBX clip drives the skeleton
    let crossFadeDuration = DEFAULT_CROSS_FADE
    let debug = false

    // Active action metadata so the renderer/procedural layer can introspect.
    let activeName = null
    let currentProfile = PERSONALITY_PROFILES.CHIDVI
    let currentPriority = PRIORITY.IDLE

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

    function isCurrentBinding(expectedMixer, expectedGeneration) {
        return mixer === expectedMixer && mixerGeneration === expectedGeneration
    }

    function retargetClip(sourceClip) {
        if (!activeVRM?.humanoid) return null

        const tracks = []
        let skippedTracks = 0
        for (const sourceTrack of sourceClip.tracks) {
            const propertyIndex = sourceTrack.name.lastIndexOf('.')
            if (propertyIndex < 1) {
                skippedTracks += 1
                continue
            }

            const sourceBoneName = sourceTrack.name.slice(0, propertyIndex)
            const targetBoneName = MIXAMO_TO_VRM_BONE[sourceBoneName]
            const targetNode = targetBoneName
                ? activeVRM.humanoid.getRawBoneNode(targetBoneName)
                : null
            if (!targetNode?.name) {
                skippedTracks += 1
                continue
            }

            const targetTrack = sourceTrack.clone()
            targetTrack.name = `${targetNode.name}${sourceTrack.name.slice(propertyIndex)}`
            tracks.push(targetTrack)
        }

        if (!tracks.length) {
            warn(`Cannot retarget ${sourceClip.name}: no compatible VRM tracks`)
            return null
        }

        log(`Retargeted ${sourceClip.name}: ${tracks.length} tracks, skipped ${skippedTracks}`)
        return new THREE.AnimationClip(sourceClip.name, sourceClip.duration, tracks)
    }

    function randomItem(arr) {
        return arr[Math.floor(Math.random() * arr.length)]
    }

    /**
     * Load (and cache) the AnimationClip[] for a semantic animation name.
     * Mixamo FBX files expose their clip on result.animations.
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
        const retargetedClip = retargetClip(clip)
        if (!retargetedClip) return null
        const action = mixer.clipAction(retargetedClip)
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
     * Weights are driven here each frame via update().
     */
    function startCrossFade(fromAction, toAction, duration, onDone) {
        if (!toAction) {
            if (onDone) onDone()
            return
        }
        toAction.reset()
        toAction.setEffectiveWeight(0)
        toAction.enabled = true;
        toAction.play()

        pendingFade = {
            from: fromAction,
            to: toAction,
            t: 0,
            duration: Math.max(EPSILON, duration),
            onDone: onDone || null,
        }

        if (fromAction) {
            // three's built-in crossFadeTo also works, but managing weights
            // ourselves lets us keep the idle action alive underneath.
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

    /**
     * Mark the manager as driving the skeleton (so procedural pose backs off),
     * or not (so procedural idle can resume).
     */
    function setFBXActive(value) {
        fbxActive = value
    }

    /**
     * Play the idle loop (looping). If a non-idle action is currently active
     * it is left alone; idle is faded in underneath so it is ready when the
     * one-shot ends.
     */
    function ensureIdle() {
        if (!mixer) return null
        if (idleAction) {
            // Already created for this mixer lifecycle.
            return idleAction
        }
        // Async: load if needed, then start looping.
        const expectedMixer = mixer
        const expectedGeneration = mixerGeneration
        loadClips(idleName).then((clips) => {
            if (!clips || !isCurrentBinding(expectedMixer, expectedGeneration) || idleAction) return
            const action = actionFor(clips[0])
            if (!action) return
            action.setLoop(THREE.LoopRepeat, Infinity)
            action.clampWhenFinished = false
            action.setEffectiveWeight(currentAction ? 0 : 1)
            action.enabled = true;
            action.play()
            idleAction = action
            log(`Idle loop started: ${idleName}`)
        })
        return null
    }

    /**
     * Called when a non-idle action finishes (one-shot gesture/emotion).
     * Drains the queue, otherwise returns to idle.
     */
    function onActionFinished() {
        log(`Action finished: ${activeName}`)
        const finishedAction = currentAction
        currentAction = null
        activeName = null

        if (queue.length > 0) {
            const next = queue.shift()
            log(`Queue -> playing next: ${next}`)
            playOneShot(next, null)
            return
        }

        // Return to idle: fade idle weight back up, fade out the finished clip.
        if (idleAction && finishedAction) {
            startCrossFade(finishedAction, idleAction, crossFadeDuration, () => {
                setFBXActive(false)
                // idle is now the only thing driving bones -> procedural resumes.
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
     * Play a one-shot (non-looping) animation, cross-fading from whatever is
     * currently driving the skeleton.
     */
    function playOneShot(name, afterPlay) {
        const expectedMixer = mixer
        const expectedGeneration = mixerGeneration
        loadClips(name).then((clips) => {
            if (!clips || !isCurrentBinding(expectedMixer, expectedGeneration)) {
                warn(`Cannot play ${name}: no clips or no mixer`)
                return
            }
            const clip = clips[0]
            const next = actionFor(clip)
            if (!next) return

            next.setLoop(THREE.LoopOnce, 1)
            next.clampWhenFinished = true
            next.time = 0

            // Clear any stale 'finished' listener from a prior action.
            mixer.removeEventListener('finished', finishedHandler)
            finishedHandler = (event) => {
                if (event.action === next) {
                    onActionFinished()
                    if (afterPlay) afterPlay()
                }
            }
            mixer.addEventListener('finished', finishedHandler)

            const from = currentAction || idleAction
            startCrossFade(from, next, crossFadeDuration, () => {
                currentAction = next
                activeName = name
                setFBXActive(true)
                log(`Playing: ${name}`)
            })
        })
    }

    // Holder for the current mixer 'finished' listener so we can swap it.
    let finishedHandler = null

    // -------------------------------------------------------------------------
    // Public API
    // -------------------------------------------------------------------------

    const api = {
        /**
         * Attach to the renderer's current AnimationMixer. Called after every
         * avatar load/switch. Resets per-mixer caches.
         */
        bindMixer(newMixer, newVRM) {
            if (mixer === newMixer && activeVRM === newVRM) return
            if (finishedHandler && mixer) {
                mixer.removeEventListener('finished', finishedHandler)
            }
            mixer = newMixer
            activeVRM = newVRM || null
            mixerGeneration += 1
            actionCache.clear()
            currentAction = null
            idleAction = null
            activeName = null
            pendingFade = null
            setFBXActive(false)
            log(`Mixer bound: ${mixer ? 'yes' : 'no'}`)
        },

        /**
         * Preload a list of semantic animation names (or raw URLs).
         */
        async preload(names) {
            const list = Array.isArray(names) ? names : [names]
            await Promise.all(
                list.map(async (entry) => {
                    const name = entryToName(entry)
                    if (name) await loadClips(name)
                })
            )
        },

        /**
         * Start (or restart) the idle loop. Optionally change which animation
         * is used as the idle.
         */
        playIdle(name) {
            if (name) {
                idleName = name
            }
            currentState = 'idle'
            ensureIdle()
        },

        /**
         * Play a named animation with options.
         * @param {string} name semantic animation name
         * @param {object} [options]
         *   - loop: boolean (default false)
         *   - crossFadeDuration: number (seconds)
         *   - afterPlay: function called when a non-loop finishes
         */
        play(name, options = {}) {
            if (options.crossFadeDuration != null) {
                crossFadeDuration = options.crossFadeDuration
            }
            if (options.loop) {
                playLooping(name)
            } else {
                playOneShot(name, options.afterPlay || null)
            }
        },

        /**
         * Play a one-shot gesture then return to idle. Convenience wrapper.
         */
        playGesture(name, afterPlay) {
            playOneShot(name, afterPlay || null)
        },

        /**
         * Add an animation to the playback queue. Played when the current
         * one-shot finishes.
         */
        queueAnimation(name) {
            queue.push(name)
            log(`Queued: ${name} (queue len=${queue.length})`)
        },

        /** Empty the queue. */
        clearQueue() {
            queue.length = 0
        },

        /** Fade out whatever is playing and return to idle immediately. */
        stop() {
            queue.length = 0
            if (currentAction) {
                startCrossFade(currentAction, idleAction, crossFadeDuration, () => {
                    setFBXActive(false)
                })
                currentAction = null
                activeName = null
            }
        },

        /**
         * Phase 3 hook: called when the runtime emotion/state string changes.
         * Maps the state to its animation and plays it. States that map to
         * looping clips (idle/listening/speaking) play as loops; one-shot
         * emotions fall back to play().
         */
        onStateChange(stateOrEmotion) {
            const key = String(stateOrEmotion || 'idle').toLowerCase()

            // Try runtime-state mapping first.
            if (STATE_ANIMATIONS[key]) {
                let anim = STATE_ANIMATIONS[key]
                if (key === 'speaking') {
                    // Random talking variation for Phase5
                    anim = randomItem(['talking', 'talking2', 'secret'])
                }
                currentState = key
                if (key === 'idle') {
                    api.playIdle(idleName)
                } else {
                    // Listening / thinking / speaking are sustained loops.
                    playLooping(anim)
                }
                return
            }

            // Then emotion mapping (Phase 5).
            if (EMOTION_ANIMATIONS[key]) {
                playOneShot(EMOTION_ANIMATIONS[key], null)
                return
            }

            // Unknown -> idle is the safe default.
            currentState = 'idle'
            api.playIdle(idleName)
        },

        /** Per-frame update. Call from the render loop with the frame delta. */
        update(delta) {
            if (!mixer) return
            tickCrossFade(delta)
        },

        /** True when an FBX clip is driving the skeleton (procedural should back off). */
        isFBXActive() {
            return fbxActive
        },

        /** True if the semantic name is a known animation. */
        hasAnimation(name) {
            return Boolean(urlFor(name))
        },

        /** Current semantic name being played (or null). */
        getActiveName() {
            return activeName
        },

        /** Current runtime state string. */
        getCurrentState() {
            return currentState
        },

        /** Enable/disable verbose console logging. */
        setDebug(value) {
            debug = Boolean(value)
        },

        /** Snapshot for diagnostics. */
        getDiagnostics() {
            return {
                mixerBound: Boolean(mixer),
                fbxActive,
                activeName,
                currentState,
                idleName,
                idleActionAlive: Boolean(idleAction),
                hasCurrentAction: Boolean(currentAction),
                queueLength: queue.length,
                queue,
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
                availableEmotions: Object.keys(EMOTION_ANIMATIONS),
                currentProfile: currentProfile.name
            }
        },

        // Phase 7: Emotion dispatcher
        playEmotion(name, afterPlay) {
            const anim = EMOTION_ANIMATIONS[name.toLowerCase()]
            if (anim) {
                playOneShot(anim, afterPlay)
            } else {
                warn(`Unknown emotion: ${name}`)
            }
        },

        // Phase 6 & 7: Convenience queue methods
        queueGesture(name) {
            if (GESTURES.includes(name)) {
                queue.push(name)
            }
        },
        queueEmotion(name) {
            const anim = EMOTION_ANIMATIONS[name.toLowerCase()]
            if (anim) queue.push(anim)
        },

        // Phase 8: Personality profile
        setProfile(profileName) {
            const profile = PERSONALITY_PROFILES[profileName.toUpperCase()]
            if (profile) {
                currentProfile = profile
                idleName = profile.idle || DEFAULT_IDLE
                log(`Set animation profile: ${profile.name}`)
            } else {
                warn(`Unknown profile: ${profileName}`)
            }
        },

        getCurrentProfile() {
            return currentProfile.name
        },

        // Phase 5: Play state explicitly
        playState(stateOrEmotion) {
            api.onStateChange(stateOrEmotion)
        },

        /**
         * Release actions bound to the current mixer but KEEP the clip cache,
         * so FBX files are not re-downloaded on every avatar switch.
         * Called from disposeCurrentVRM() before the mixer is torn down.
         */
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
            queue.length = 0
            setFBXActive(false)
            mixer = null
            activeVRM = null
            mixerGeneration += 1
            log('Unbound mixer (clips kept cached)')
        },

        /** Tear down everything including the clip cache. */
        dispose() {
            api.unbindMixer()
            clipCache.clear()
            log('Disposed')
        },
    }

    /**
     * Play a looping clip (e.g. idle/listening/speaking). The idle action is
     * faded out while a non-idle loop runs; when stopped it fades back.
     */
    function playLooping(name) {
        const expectedMixer = mixer
        const expectedGeneration = mixerGeneration
        loadClips(name).then((clips) => {
            if (!clips || !isCurrentBinding(expectedMixer, expectedGeneration)) {
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
            startCrossFade(from, next, crossFadeDuration, () => {
                // If this loop replaces the idle, keep idleAction reference but
                // it remains at weight 0 underneath.
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
                log(`Looping: ${name}`)
            })
        })
    }

    function entryToName(entry) {
        if (!entry) return null
        if (ANIMATION_MAP[entry]) return entry
        // Allow passing a raw URL.
        for (const [n, u] of Object.entries(ANIMATION_MAP)) {
            if (u === entry) return n
        }
        return null
    }

    return api
}
