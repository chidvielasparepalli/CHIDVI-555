import * as THREE from 'three'

/**
 * AnimationManager
 * ----------------
 * Loads, caches, blends, and plays pre-retargeted FBX animations on the
 * currently active VRM.
 *
 * RETARGETING IS DONE OFFLINE IN BLENDER (tools/blender_pipeline/).
 * Runtime does NO bone correction, NO quaternion conversion, NO rest-pose
 * estimation, NO pose reconstruction.  Animations are loaded and played as-is.
 *
 * Pipeline:
 *   Mixamo FBX → Blender (retarget + bake to VRM skeleton) →
 *   Export FBX with VRM bone names → FBXLoader → AnimationClip →
 *   AnimationMixer → crossfade → play
 *
 * The AnimationMixer maps clip track names to scene objects by name, so
 * the exported FBX must use the same bone names as the VRM humanoid
 * (hips, spine, chest, upperChest, neck, head, …).
 */

// ---------------------------------------------------------------------------
// Animation registry — semantic name → file URL under /public/animations/
// ---------------------------------------------------------------------------
const ANIMATION_MAP = {
    // --- Idle loops ---
    idle:           '/animations/idle.fbx',
    breathing_idle: '/animations/breathing_idle.fbx',
    sad_idle:       '/animations/sad_idle.fbx',

    // --- Greetings / one-shot gestures ---
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

    // --- Emotions ---
    happy:          '/animations/happy.fbx',
    laughing:       '/animations/laughing.fbx',
    angry:          '/animations/angry.fbx',
    bashful:        '/animations/bashful.fbx',
    cheer:          '/animations/cheer.fbx',
    yell:           '/animations/yell.fbx',
    thinking:       '/animations/thinking.fbx',

    // --- Talking variants ---
    talking:        '/animations/talking.fbx',
    talking2:       '/animations/talking2.fbx',
    secret:         '/animations/secret.fbx',
    pointing:       '/animations/pointing.fbx',

    // --- Command-router aliases ---
    point:          '/animations/pointing.fbx',
    greeting:       '/animations/wave.fbx',
    laugh:          '/animations/laughing.fbx',
    sad:            '/animations/sad_idle.fbx',
    excited:        '/animations/cheer.fbx',
}

// ---------------------------------------------------------------------------
// State → animation name
// ---------------------------------------------------------------------------
const STATE_ANIMATIONS = {
    listening:   'breathing_idle',
    thinking:    'thinking',
    speaking:    'talking',
    idle:        'idle',
}

// ---------------------------------------------------------------------------
// Emotion → animation name
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

const DEFAULT_CROSS_FADE = 0.35
const DEFAULT_IDLE = 'idle'
const EPSILON = 0.0001

const GESTURES = [
    'wave', 'wave2', 'salute', 'bow', 'clap', 'point', 'pointing',
    'greeting', 'shrug', 'nod', 'shake_head', 'jump',
]

// Dynamic personality profiles map — can be extended at runtime via registerProfile()
const PERSONALITY_PROFILES = new Map([
    ['CHIDVI', {
        idle: 'idle',
        listening: 'breathing_idle',
        thinking: 'thinking',
        speaking: ['talking', 'talking2'],
        minimalGestures: true,
        name: 'CHIDVI',
    }],
    ['HINATA', {
        idle: 'breathing_idle',
        listening: 'breathing_idle',
        thinking: 'thinking',
        speaking: ['talking', 'talking2', 'secret'],
        minimalGestures: false,
        name: 'HINATA',
    }],
])

const PRIORITY = {
    MANUAL_GESTURE: 10,
    EMOTION: 8,
    SPEAKING: 6,
    LISTENING: 4,
    IDLE: 0,
}

// ---------------------------------------------------------------------------
// Reference: VRM humanoid bone names
// After Blender pipeline the FBX clip tracks use these names directly.
// ---------------------------------------------------------------------------
const VRM_BONE_NAMES = [
    'hips', 'spine', 'chest', 'upperChest', 'neck', 'head',
    'leftShoulder', 'rightShoulder',
    'leftUpperArm', 'rightUpperArm',
    'leftLowerArm', 'rightLowerArm',
    'leftHand', 'rightHand',
    'leftUpperLeg', 'rightUpperLeg',
    'leftLowerLeg', 'rightLowerLeg',
    'leftFoot', 'rightFoot',
    'leftToes', 'rightToes',
    'leftThumbMetacarpal', 'rightThumbMetacarpal',
    'leftThumbProximal', 'rightThumbProximal',
    'leftThumbDistal', 'rightThumbDistal',
    'leftIndexProximal', 'rightIndexProximal',
    'leftIndexIntermediate', 'rightIndexIntermediate',
    'leftIndexDistal', 'rightIndexDistal',
    'leftMiddleProximal', 'rightMiddleProximal',
    'leftMiddleIntermediate', 'rightMiddleIntermediate',
    'leftMiddleDistal', 'rightMiddleDistal',
    'leftRingProximal', 'rightRingProximal',
    'leftRingIntermediate', 'rightRingIntermediate',
    'leftRingDistal', 'rightRingDistal',
    'leftLittleProximal', 'rightLittleProximal',
    'leftLittleIntermediate', 'rightLittleIntermediate',
    'leftLittleDistal', 'rightLittleDistal',
]

/**
 * Build an AnimationManager bound to a THREE.FBXLoader instance.
 */
export function createAnimationManager(loader) {
    const clipCache = new Map()
    const actionCache = new Map()
    let mixer = null
    let activeVRM = null
    let mixerGeneration = 0
    let currentAction = null
    let idleAction = null
    let idleName = DEFAULT_IDLE
    let currentState = 'idle'
    let queue = []
    let pendingFade = null
    let fbxActive = false
    let crossFadeDuration = DEFAULT_CROSS_FADE
    let debug = false

    let activeName = null
    let currentProfile = PERSONALITY_PROFILES.get('CHIDVI')
    let currentPriority = PRIORITY.IDLE
    let currentActionIsOneShot = false
    let activeGesture = null
    let activeEmotion = null

    let finishedHandler = null

    // Diagnostics counters
    let totalClipsLoaded = 0
    let totalClipsPlayed = 0
    const warnings = []
    const errors = []

    // -----------------------------------------------------------------
    // Helpers
    // -----------------------------------------------------------------

    function log(...args) {
        if (debug) console.info('[AnimManager]', ...args)
    }

    function warn(...args) {
        console.warn('[AnimManager]', ...args)
    }

    function pushWarning(msg) {
        warnings.push(msg)
        if (warnings.length > 50) warnings.shift()
        warn(msg)
    }

    function pushError(msg) {
        errors.push(msg)
        if (errors.length > 20) errors.shift()
        console.error('[AnimManager]', msg)
    }

    function urlFor(name) {
        return ANIMATION_MAP[name] || null
    }

    function isCurrentBinding(expectedMixer, expectedGeneration) {
        return mixer === expectedMixer && mixerGeneration === expectedGeneration
    }

    function randomItem(arr) {
        return arr[Math.floor(Math.random() * arr.length)]
    }

    function entryToName(entry) {
        if (!entry) return null
        if (ANIMATION_MAP[entry]) return entry
        for (const [n, u] of Object.entries(ANIMATION_MAP)) {
            if (u === entry) return n
        }
        return null
    }

    // -----------------------------------------------------------------
    // Loading — NO RETARGETING
    // -----------------------------------------------------------------

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

            // Transitional check: warn if FBX still uses Mixamo bone names
            for (const clip of clips) {
                for (const track of clip.tracks) {
                    if (track.name.startsWith('mixamorig')) {
                        pushWarning(
                            `"${name}" has Mixamo bone names — use Blender pipeline ` +
                            '(tools/blender_pipeline/retarget_workflow.md) to retarget ' +
                            'before loading at runtime'
                        )
                        break
                    }
                }
            }

            clipCache.set(url, clips)
            totalClipsLoaded += clips.length
            log(`Loaded ${name} (${clips.length} clip(s)) from ${url}`)
            return clips
        } catch (err) {
            pushError(`Failed to load animation ${name} (${url}): ${err?.message || err}`)
            return null
        }
    }

    // -----------------------------------------------------------------
    // Action management — NO RETARGETING
    // -----------------------------------------------------------------

    function actionFor(clip) {
        if (!mixer) return null
        const key = clip.uuid
        if (actionCache.has(key)) {
            return actionCache.get(key)
        }
        // Use the clip directly — all retargeting is offline in Blender.
        const action = mixer.clipAction(clip)
        if (action) {
            actionCache.set(key, action)
        }
        return action
    }

    function stopAction(action, fadeSeconds = 0) {
        if (!action) return
        if (fadeSeconds > 0) {
            action.fadeOut(fadeSeconds)
        } else {
            action.stop()
        }
    }

    function startCrossFade(fromAction, toAction, duration, onDone) {
        if (!toAction) {
            if (onDone) onDone()
            return
        }
        toAction.reset()
        toAction.setEffectiveWeight(0)
        toAction.enabled = true
        toAction.play()

        pendingFade = {
            from: fromAction,
            to: toAction,
            t: 0,
            duration: Math.max(EPSILON, duration),
            onDone: onDone || null,
        }
    }

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

    function priorityForState(state) {
        if (state === 'speaking' || state === 'thinking') return PRIORITY.SPEAKING
        if (state === 'listening') return PRIORITY.LISTENING
        return PRIORITY.IDLE
    }

    function animationForState(state) {
        const profileAnimation = currentProfile[state] || STATE_ANIMATIONS[state]
        return Array.isArray(profileAnimation) ? randomItem(profileAnimation) : profileAnimation
    }

    // -----------------------------------------------------------------
    // Idle / loop / one-shot
    // -----------------------------------------------------------------

    function ensureIdle() {
        if (!mixer) return null
        if (idleAction) return idleAction
        const expectedMixer = mixer
        const expectedGeneration = mixerGeneration
        loadClips(idleName).then((clips) => {
            if (!clips || !isCurrentBinding(expectedMixer, expectedGeneration) || idleAction) return
            const action = actionFor(clips[0])
            if (!action) return
            action.setLoop(THREE.LoopRepeat, Infinity)
            action.clampWhenFinished = false
            action.setEffectiveWeight(currentAction ? 0 : 1)
            action.enabled = true
            action.play()
            idleAction = action
            log(`Idle loop started: ${idleName}`)
        })
        return null
    }

    function onActionFinished() {
        log(`Action finished: ${activeName}`)
        currentAction = null
        activeName = null
        currentActionIsOneShot = false
        currentPriority = priorityForState(currentState)
        activeGesture = null
        activeEmotion = null

        if (queue.length > 0) {
            const next = queue.shift()
            log(`Queue -> playing next: ${next}`)
            playOneShot(next, null)
            return
        }

        const stateAnimation = animationForState(currentState)
        if (currentState !== 'idle' && stateAnimation) {
            playLooping(stateAnimation)
            return
        }

        if (idleAction) {
            startCrossFade(currentAction || null, idleAction, crossFadeDuration, () => {
                setFBXActive(false)
            })
        } else {
            setFBXActive(false)
            ensureIdle()
        }
    }

    function playOneShot(name, afterPlay, priority = PRIORITY.MANUAL_GESTURE) {
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
                currentActionIsOneShot = true
                currentPriority = priority
                totalClipsPlayed++
                setFBXActive(true)
                log(`Playing: ${name}`)
            })
        })
    }

    function playLooping(name, fromAction = null) {
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

            const from = fromAction || currentAction || idleAction
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
                currentActionIsOneShot = false
                currentPriority = priorityForState(currentState)
                totalClipsPlayed++
                log(`Looping: ${name}`)
            })
        })
    }

    // -----------------------------------------------------------------
    // Public API
    // -----------------------------------------------------------------

    const api = {
        /**
         * Bind a new AnimationMixer and VRM. Resets all action state.
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
            currentActionIsOneShot = false
            activeGesture = null
            activeEmotion = null
            pendingFade = null
            currentPriority = PRIORITY.IDLE
            setFBXActive(false)
            // Clear transient warnings on re-bind
            warnings.length = 0
            errors.length = 0
            log(`Mixer bound: ${mixer ? 'yes' : 'no'}`)
        },

        /**
         * Preload animation clips into cache (non-blocking).
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
         * Play the idle animation loop.
         */
        playIdle(name) {
            if (name) {
                idleName = name
            }
            currentState = 'idle'
            currentPriority = PRIORITY.IDLE
            ensureIdle()
        },

        /**
         * Play an animation by name.
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
         * Play a gesture animation (one-shot, high priority).
         */
        playGesture(name, afterPlay) {
            if (!GESTURES.includes(name)) {
                warn(`Unknown gesture: ${name}`)
                return
            }
            activeGesture = name
            playOneShot(name, afterPlay || null, PRIORITY.MANUAL_GESTURE)
        },

        /**
         * Queue an animation to play after the current one finishes.
         */
        queueAnimation(name) {
            if (!urlFor(name)) {
                warn(`Unknown queued animation: ${name}`)
                return
            }
            if (!currentActionIsOneShot) {
                playOneShot(name, null)
                return
            }
            queue.push(name)
            log(`Queued: ${name} (queue len=${queue.length})`)
        },

        /**
         * Clear the animation queue.
         */
        clearQueue() {
            queue.length = 0
        },

        /**
         * Stop current animation and return to idle.
         */
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
         * React to a state or emotion change.
         * State changes drive looping animations; emotions play as one-shots.
         */
        onStateChange(stateOrEmotion) {
            const key = String(stateOrEmotion || 'idle').toLowerCase()

            if (STATE_ANIMATIONS[key]) {
                let anim = STATE_ANIMATIONS[key]
                if (key === 'speaking') {
                    anim = animationForState('speaking')
                }
                currentState = key
                if (currentActionIsOneShot && currentPriority > priorityForState(key)) {
                    return
                }
                if (key === 'idle') {
                    api.playIdle(idleName)
                } else {
                    playLooping(anim)
                }
                return
            }

            if (EMOTION_ANIMATIONS[key]) {
                activeEmotion = key
                if (!currentActionIsOneShot || currentPriority <= PRIORITY.EMOTION) {
                    playOneShot(EMOTION_ANIMATIONS[key], null, PRIORITY.EMOTION)
                }
                return
            }

            currentState = 'idle'
            api.playIdle(idleName)
        },

        /**
         * Per-frame update (drives crossfades).
         */
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

        setDebug(value) {
            debug = Boolean(value)
        },

        /**
         * Return a diagnostics snapshot.
         */
        getDiagnostics() {
            const health = { ok: 0, warn: 0, error: 0 }

            let humanoidBoneCount = 0
            const availableBones = []
            const missingBones = []
            if (activeVRM?.humanoid) {
                for (const boneName of VRM_BONE_NAMES) {
                    const node = activeVRM.humanoid.getRawBoneNode(boneName)
                    if (node) {
                        humanoidBoneCount++
                        availableBones.push(boneName)
                    } else {
                        missingBones.push(boneName)
                    }
                }
            }

            const activeGestures = []
            if (activeGesture) activeGestures.push(activeGesture)
            if (activeEmotion) activeGestures.push(activeEmotion)

            // Compute health status
            if (mixer) health.ok++
            else health.error++
            if (activeVRM) health.ok++
            else health.warn++
            if (idleAction) health.ok++
            else health.warn++
            if (errors.length === 0) health.ok++
            else health.error += errors.length
            if (warnings.length < 3) health.ok++
            else health.warn++

            return {
                // Status
                status: errors.length > 0 ? 'error' : warnings.length > 3 ? 'warning' : 'healthy',
                health,

                // Binding
                mixerBound: Boolean(mixer),
                vrmLoaded: Boolean(activeVRM),
                currentVRM: activeVRM?.meta?.name || activeVRM?.scene?.name || null,

                // Playback
                activeName,
                currentState,
                idleName,
                idleActionAlive: Boolean(idleAction),
                hasCurrentAction: Boolean(currentAction),
                fbxActive,
                currentPriority,
                currentActionIsOneShot,

                // Blend state
                pendingFade: Boolean(pendingFade),
                blendProgress: pendingFade ? Math.min(1, pendingFade.t / pendingFade.duration) : 1,
                crossFadeDuration,

                // Queue
                queueLength: queue.length,
                queue: [...queue],

                // Gesture & emotion
                activeGesture,
                activeEmotion,
                availableGestures: GESTURES,
                availableEmotions: Object.keys(EMOTION_ANIMATIONS),

                // Profile
                currentProfile: currentProfile.name,

                // Cache
                cachedClips: clipCache.size,
                cachedClipNames: Array.from(clipCache.keys()).map(url => {
                    for (const [n, u] of Object.entries(ANIMATION_MAP)) {
                        if (u === url) return n
                    }
                    return url
                }),
                totalClipsLoaded,
                totalClipsPlayed,

                // Skeleton
                humanoidBones: humanoidBoneCount,
                totalBonesInVRM: VRM_BONE_NAMES.length,
                missingBones,

                // Warnings & errors
                warnings: [...warnings],
                errors: [...errors],

                // FPS (caller should supply delta)
                animationFPS: (delta) => delta > 0 ? Math.round(1 / delta) : 0,
            }
        },

        /**
         * Play an emotion animation.
         */
        playEmotion(name, afterPlay) {
            const anim = EMOTION_ANIMATIONS[name.toLowerCase()]
            if (anim) {
                activeEmotion = name.toLowerCase()
                if (!currentActionIsOneShot || currentPriority <= PRIORITY.EMOTION) {
                    playOneShot(anim, afterPlay, PRIORITY.EMOTION)
                }
            } else {
                warn(`Unknown emotion: ${name}`)
            }
        },

        queueGesture(name) {
            if (GESTURES.includes(name)) {
                api.queueAnimation(name)
            }
        },

        queueEmotion(name) {
            const anim = EMOTION_ANIMATIONS[name.toLowerCase()]
            if (anim) api.queueAnimation(anim)
        },

        setProfile(profileName) {
            const profile = PERSONALITY_PROFILES.get(profileName.toUpperCase())
            if (profile) {
                currentProfile = profile
                idleName = profile.idle || DEFAULT_IDLE
                log(`Set animation profile: ${profile.name}`)
            } else {
                warn(`Unknown profile: ${profileName}`)
            }
        },

        /**
         * Register a new personality profile at runtime (for plugin system).
         */
        registerProfile(name, config) {
            if (!name || !config) return
            const key = name.toUpperCase()
            PERSONALITY_PROFILES.set(key, {
                idle: config.idle || 'idle',
                listening: config.listening || 'breathing_idle',
                thinking: config.thinking || 'thinking',
                speaking: Array.isArray(config.speaking) ? config.speaking : [config.speaking || 'talking'],
                minimalGestures: Boolean(config.minimalGestures),
                name: key,
            })
            log(`Registered animation profile: ${key}`)
        },

        getCurrentProfile() {
            return currentProfile.name
        },

        playState(stateOrEmotion) {
            api.onStateChange(stateOrEmotion)
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
            currentActionIsOneShot = false
            activeGesture = null
            activeEmotion = null
            pendingFade = null
            currentPriority = PRIORITY.IDLE
            queue.length = 0
            setFBXActive(false)
            mixer = null
            activeVRM = null
            mixerGeneration += 1
            log('Unbound mixer (clips kept cached)')
        },

        dispose() {
            api.unbindMixer()
            clipCache.clear()
            log('Disposed')
        },
    }

    return api
}
