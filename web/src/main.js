import './style.css'

import * as THREE from 'three'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'
import { FBXLoader } from 'three/examples/jsm/loaders/FBXLoader.js'
import { VRMLoaderPlugin, VRMUtils } from '@pixiv/three-vrm'
import { createAnimationManager } from './animation-manager.js'

const scene = new THREE.Scene()
scene.background = new THREE.Color(0x00060a)

const camera = new THREE.PerspectiveCamera(
    30,
    window.innerWidth / window.innerHeight,
    0.1,
    100
)

camera.position.set(0, 1.4, 2.2)

const renderer = new THREE.WebGLRenderer({
    antialias: true,
    alpha: true
})

renderer.setSize(window.innerWidth, window.innerHeight)
renderer.setPixelRatio(window.devicePixelRatio)
renderer.setClearColor(0x00060a, 1)

document.body.style.margin = "0"
document.body.style.background = "#00060a"
document.body.appendChild(renderer.domElement)

scene.add(new THREE.AmbientLight(0xffffff, 2))

const light = new THREE.DirectionalLight(0xffffff, 2)
light.position.set(1, 2, 3)
scene.add(light)

const loader = new GLTFLoader()

loader.register((parser) => {
    return new VRMLoaderPlugin(parser)
})

let currentVRM = null
let currentAvatarFile = null
let currentMixer = null
let avatarLoadSerial = 0
let avatarSwitchInProgress = false
let queuedAvatarFile = null
let avatarUpdatePaused = false
let lastAvatarSwitchStatus = "initializing"
let lastAvatarSwitchError = null
let avatarEmotion = "idle"
let mouthPhase = 0
let activeAction = null
let actionStartedAt = 0
const expressionTargets = {}

// AnimationManager: loads/caches/plays pre-retargeted FBX clips on the active VRM.
// No runtime retargeting — all bone correction is done offline in Blender.
const fbxLoader = new FBXLoader()
const animManager = createAnimationManager(fbxLoader)

const emotionExpressions = {
    idle: { relaxed: 0.35 },
    listening: { relaxed: 0.2, happy: 0.08 },
    thinking: { surprised: 0.12 },
    speaking: { happy: 0.12 },
    happy: { happy: 0.8 },
    excited: { happy: 1.0, surprised: 0.2 },
    angry: { angry: 0.85 },
    sad: { sad: 0.85 },
    embarrassed: { sad: 0.15, happy: 0.2 },
    blushing: { happy: 0.3 },
    blush: { happy: 0.3 },
    jealous: { angry: 0.35, sad: 0.25 },
    laughing: { happy: 1.0, aa: 0.45 },
    confused: { surprised: 0.25 },
    surprised: { surprised: 0.9 },
    sleepy: { relaxed: 0.8, blink: 0.35 },
}

function setExpressionTarget(name, value) {
    expressionTargets[name] = Math.max(0, Math.min(1, value))
}

function resetEmotionTargets() {
    for (const key of Object.keys(expressionTargets)) {
        expressionTargets[key] = 0
    }
}

function applyEmotionTarget(emotion, { animate = true } = {}) {
    avatarEmotion = String(emotion || "idle").toLowerCase()
    resetEmotionTargets()
    const values = emotionExpressions[avatarEmotion] || emotionExpressions.idle
    for (const [name, value] of Object.entries(values)) {
        setExpressionTarget(name, value)
    }
    if (animate) {
        animManager.onStateChange(avatarEmotion)
    }
}

window.setAvatarEmotion = (emotion) => applyEmotionTarget(emotion)
window.setAvatarState = (state) => applyEmotionTarget(state)
window.performAvatarAction = (action) => {
    const a = String(action || "").toLowerCase()
    if (animManager.hasAnimation(a)) {
        animManager.playGesture(a)
        if (a === "smile" || a === "happy") {
            applyEmotionTarget("happy", { animate: false })
        } else if (a === "laugh" || a === "laughing") {
            applyEmotionTarget("laughing", { animate: false })
        } else if (a === "thinking") {
            applyEmotionTarget("thinking", { animate: false })
        } else if (a === "greeting" || a === "wave" || a === "salute") {
            applyEmotionTarget("happy", { animate: false })
        } else if (a === "angry") {
            applyEmotionTarget("angry", { animate: false })
        } else if (a === "sad") {
            applyEmotionTarget("sad", { animate: false })
        }
        return
    }
    // Fallback to procedural bone animation for actions without FBX
    activeAction = a
    actionStartedAt = clock.elapsedTime
    if (activeAction === "smile") {
        applyEmotionTarget("happy")
    } else if (activeAction === "laugh") {
        applyEmotionTarget("laughing")
    } else if (activeAction === "thinking") {
        applyEmotionTarget("thinking")
    } else if (activeAction === "greeting") {
        applyEmotionTarget("happy")
    }
}

function getBone(name) {
    return currentVRM?.humanoid?.getNormalizedBoneNode(name) || null
}

function setBoneRotation(name, x = 0, y = 0, z = 0, blend = 1) {
    const bone = getBone(name)
    if (!bone) return
    bone.rotation.x = THREE.MathUtils.lerp(bone.rotation.x, x, blend)
    bone.rotation.y = THREE.MathUtils.lerp(bone.rotation.y, y, blend)
    bone.rotation.z = THREE.MathUtils.lerp(bone.rotation.z, z, blend)
}

function setBonePosition(name, x = 0, y = 0, z = 0, blend = 1) {
    const bone = getBone(name)
    if (!bone) return
    bone.position.x = THREE.MathUtils.lerp(bone.position.x, x, blend)
    bone.position.y = THREE.MathUtils.lerp(bone.position.y, y, blend)
    bone.position.z = THREE.MathUtils.lerp(bone.position.z, z, blend)
}

function clampRotation(value) {
    // Clamp to safe human range (-PI/2 to PI/2 for most joints)
    return Math.max(-Math.PI * 0.45, Math.min(Math.PI * 0.45, value))
}

// ---------------------------------------------------------------------------
// BEHAVIOUR DIRECTOR
// ---------------------------------------------------------------------------
// Drives naturalistic micro-behaviours: breathing, blinking, weight shifts,
// gaze, head micro-movements, shoulder rolls, hand fidgets, posture changes.
//
// Runs every frame. Coexists with FBX-driven animations via animManager.
// When animManager.isFBXActive() is true, the director backs off arm/shoulder
// manipulation but continues breathing, blinking, and subtle body motion.
// ---------------------------------------------------------------------------

const BehaviourDirector = (() => {
    // --- Blink state ---
    let blinkPhase = 0          // 0=open, 1=closing, 2=closed, 3=opening
    let blinkSpeed = 0
    let nextBlinkTime = 2 + Math.random() * 3
    let lastBlinkT = 0

    // --- Breath state ---
    let breathPhase = 0
    let breathBaseRate = 0.35
    let breathDepth = 0.025
    let breathTargetDepth = 0.025
    let sighTimer = 0
    let isSighing = false

    // --- Weight shift state ---
    let weightShiftPhase = 0
    let nextWeightShiftTime = 8 + Math.random() * 12
    let weightShiftTarget = { x: 0, y: 0, z: 0 }
    let weightShiftCurrent = { x: 0, y: 0, z: 0 }

    // --- Gaze state ---
    let nextGazeShiftTime = 3 + Math.random() * 5
    let gazeTarget = { yaw: 0, pitch: 0 }
    let gazeCurrent = { yaw: 0, pitch: 0 }
    let gazeVelocity = { yaw: 0, pitch: 0 }

    // --- Head micro-motion ---
    let headNoisePhase = 0

    // --- Shoulder state ---
    let nextShoulderRollTime = 5 + Math.random() * 10
    let shoulderRollPhase = 0
    let shoulderRollSide = 1

    // --- Hand fidget state ---
    let nextHandFidgetTime = 7 + Math.random() * 15
    let handFidgetPhase = 0
    let handFidgetSide = 'leftHand'

    // --- Nod state (listening) ---
    let nodPhase = 0
    let nextNodTime = 10 + Math.random() * 20

    // --- Posture state ---
    let posturePhase = 0
    let postureTarget = { spine: 0, chest: 0 }
    let postureCurrent = { spine: 0, chest: 0 }

    // Configuration per state
    const configs = {
        idle: {
            blinkInterval: [3, 6],
            blinkDuration: 0.15,
            breathRate: 0.35,
            breathDepth: 0.025,
            weightShiftInterval: [10, 20],
            weightShiftAmount: 0.02,
            gazeShiftInterval: [4, 8],
            gazeAmount: 0.25,
            headMicroAmount: 0.02,
            shoulderRollInterval: [8, 15],
            shoulderRollAmount: 0.08,
            handFidgetInterval: [10, 20],
            handFidgetAmount: 0.15,
            nodInterval: [99, 99],    // disabled
            postureShiftInterval: [15, 30],
        },
        listening: {
            blinkInterval: [4, 7],
            blinkDuration: 0.12,
            breathRate: 0.3,
            breathDepth: 0.02,
            weightShiftInterval: [15, 25],
            weightShiftAmount: 0.015,
            gazeShiftInterval: [6, 12],
            gazeAmount: 0.15,
            headMicroAmount: 0.015,
            shoulderRollInterval: [12, 20],
            shoulderRollAmount: 0.05,
            handFidgetInterval: [15, 30],
            handFidgetAmount: 0.08,
            nodInterval: [8, 18],     // occasional nods during listening
            postureShiftInterval: [20, 40],
        },
        speaking: {
            blinkInterval: [2, 4],
            blinkDuration: 0.1,
            breathRate: 0.5,
            breathDepth: 0.04,
            weightShiftInterval: [8, 15],
            weightShiftAmount: 0.025,
            gazeShiftInterval: [3, 6],
            gazeAmount: 0.35,
            headMicroAmount: 0.03,
            shoulderRollInterval: [6, 12],
            shoulderRollAmount: 0.1,
            handFidgetInterval: [5, 12],
            handFidgetAmount: 0.2,
            nodInterval: [99, 99],    // no nods while speaking
            postureShiftInterval: [10, 20],
        },
        thinking: {
            blinkInterval: [3, 5],
            blinkDuration: 0.18,
            breathRate: 0.25,
            breathDepth: 0.015,
            weightShiftInterval: [12, 20],
            weightShiftAmount: 0.02,
            gazeShiftInterval: [5, 10],
            gazeAmount: 0.3,
            headMicroAmount: 0.025,
            shoulderRollInterval: [10, 18],
            shoulderRollAmount: 0.06,
            handFidgetInterval: [8, 15],
            handFidgetAmount: 0.12,
            nodInterval: [99, 99],    // no nods
            postureShiftInterval: [15, 25],
        },
    }

    function getConfig() {
        return configs[avatarEmotion] || configs.idle
    }

    function lerp(a, b, t) {
        return a + (b - a) * t
    }

    function clamp(v, min, max) {
        return Math.max(min, Math.min(max, v))
    }

    function smoothNoise(t, freq) {
        return Math.sin(t * freq) * 0.5 + Math.sin(t * freq * 1.7) * 0.3 + Math.sin(t * freq * 3.1) * 0.2
    }

    // Main update function called every frame
    function update(delta, t) {
        const cfg = getConfig()
        const isFBXActive = animManager.isFBXActive()

        // -------------------------------------------------------------------
        // BLINKING — natural eyelid closure with variable speed
        // -------------------------------------------------------------------
        if (t >= nextBlinkTime && blinkPhase === 0 && t - lastBlinkT > 0.05) {
            blinkPhase = 1
            blinkSpeed = 1 / (cfg.blinkDuration * 0.5)
            lastBlinkT = t
        }

        if (blinkPhase > 0) {
            const expressionManager = currentVRM?.expressionManager
            if (expressionManager) {
                if (blinkPhase === 1) {
                    blinkPhase += delta * blinkSpeed * 2
                    if (blinkPhase >= 1) {
                        blinkPhase = 2
                        blinkSpeed = 1 / (cfg.blinkDuration * 0.5)
                    }
                } else if (blinkPhase === 2) {
                    blinkPhase += delta * blinkSpeed * 2
                    if (blinkPhase >= 2) {
                        blinkPhase = 0
                        nextBlinkTime = t + cfg.blinkInterval[0] + Math.random() * (cfg.blinkInterval[1] - cfg.blinkInterval[0])
                    }
                }

                const blinkValue = blinkPhase <= 1 ? blinkPhase : 2 - blinkPhase
                const currentBlink = expressionTargets.blink || 0
                expressionManager.setValue('blink', Math.max(currentBlink, blinkValue))
            }
        }

        // -------------------------------------------------------------------
        // BREATHING — variable-rate with occasional deep breaths / sighs
        // -------------------------------------------------------------------
        if (!isFBXActive) {
            // Occasionally take a deeper breath
            sighTimer += delta
            if (!isSighing && sighTimer > 15 + Math.random() * 20) {
                isSighing = true
                breathTargetDepth = cfg.breathDepth * 2.5
            }
            if (isSighing) {
                breathDepth = lerp(breathDepth, breathTargetDepth, delta * 1.5)
                if (Math.abs(breathDepth - breathTargetDepth) < 0.001) {
                    isSighing = false
                    breathTargetDepth = cfg.breathDepth
                    sighTimer = 0
                }
            } else {
                breathDepth = lerp(breathDepth, breathTargetDepth, delta * 0.5)
            }

            const rate = cfg.breathRate * (isSighing ? 0.4 : 1)
            breathPhase += delta * rate * Math.PI * 2
            const breathe = Math.sin(breathPhase) * breathDepth

            // Spine and chest follow the breath
            setBoneRotation('chest', clampRotation(breathe * 0.5), 0, 0, 0.3)
            setBoneRotation('spine', clampRotation(breathe * 0.3), 0, 0, 0.3)
            setBoneRotation('upperChest', clampRotation(breathe * 0.2), 0, 0, 0.3)

            // Subtle shoulder lift with breath
            if (!isFBXActive) {
                setBoneRotation('leftShoulder', 0, 0, clampRotation(-breathe * 0.3), 0.3)
                setBoneRotation('rightShoulder', 0, 0, clampRotation(breathe * 0.3), 0.3)
            }
        }

        // -------------------------------------------------------------------
        // WEIGHT SHIFT — natural hip sway and posture changes
        // -------------------------------------------------------------------
        if (t >= nextWeightShiftTime && weightShiftPhase === 0) {
            weightShiftPhase = 1
            weightShiftTarget = {
                x: (Math.random() - 0.5) * cfg.weightShiftAmount,
                y: (Math.random() - 0.5) * cfg.weightShiftAmount * 0.5,
                z: (Math.random() - 0.5) * cfg.weightShiftAmount,
            }
        }

        if (weightShiftPhase > 0) {
            const speed = 0.3
            weightShiftCurrent.x = lerp(weightShiftCurrent.x, weightShiftTarget.x, delta * speed)
            weightShiftCurrent.y = lerp(weightShiftCurrent.y, weightShiftTarget.y, delta * speed)
            weightShiftCurrent.z = lerp(weightShiftCurrent.z, weightShiftTarget.z, delta * speed)

            if (!isFBXActive) {
                const hsx = clampRotation(weightShiftCurrent.x)
                const hsy = clampRotation(weightShiftCurrent.y)
                const hsz = clampRotation(weightShiftCurrent.z)
                setBoneRotation('hips', hsx, hsy, hsz, 0.2)
                setBoneRotation('spine', clampRotation(-hsx * 0.5), 0, clampRotation(-hsz * 0.5), 0.2)
            }

            const dist = Math.abs(weightShiftCurrent.x - weightShiftTarget.x) +
                         Math.abs(weightShiftCurrent.y - weightShiftTarget.y) +
                         Math.abs(weightShiftCurrent.z - weightShiftTarget.z)
            if (dist < 0.0005) {
                weightShiftPhase = 0
                weightShiftTarget = { x: 0, y: 0, z: 0 }
                nextWeightShiftTime = t + cfg.weightShiftInterval[0] + Math.random() * (cfg.weightShiftInterval[1] - cfg.weightShiftInterval[0])
            }
        }

        // -------------------------------------------------------------------
        // GAZE — smooth eye saccades with natural velocity
        // -------------------------------------------------------------------
        if (t >= nextGazeShiftTime &&
            Math.abs(gazeCurrent.yaw - gazeTarget.yaw) < 0.001 &&
            Math.abs(gazeCurrent.pitch - gazeTarget.pitch) < 0.001) {
            gazeTarget = {
                yaw: (Math.random() - 0.5) * cfg.gazeAmount * 2,
                pitch: (Math.random() - 0.5) * cfg.gazeAmount * 0.5,
            }
            // Saccade velocity: fast jump then settle
            gazeVelocity.yaw = (gazeTarget.yaw - gazeCurrent.yaw) * 3
            gazeVelocity.pitch = (gazeTarget.pitch - gazeCurrent.pitch) * 3
            nextGazeShiftTime = t + cfg.gazeShiftInterval[0] + Math.random() * (cfg.gazeShiftInterval[1] - cfg.gazeShiftInterval[0])
        }

        // Smooth gaze with natural deceleration
        gazeCurrent.yaw = lerp(gazeCurrent.yaw, gazeTarget.yaw, delta * 4)
        gazeCurrent.pitch = lerp(gazeCurrent.pitch, gazeTarget.pitch, delta * 4)
        gazeVelocity.yaw = lerp(gazeVelocity.yaw, 0, delta * 8)
        gazeVelocity.pitch = lerp(gazeVelocity.pitch, 0, delta * 8)

        // Apply gaze to eyes
        const gYaw = clamp(gazeCurrent.yaw + gazeVelocity.yaw * 0.01, -0.5, 0.5)
        const gPitch = clamp(gazeCurrent.pitch + gazeVelocity.pitch * 0.01, -0.3, 0.3)
        if (!isFBXActive) {
            setBoneRotation('leftEye', 0, gYaw, 0, 0.5)
            setBoneRotation('rightEye', 0, gYaw, 0, 0.5)
            // Head follows eyes with reduced amplitude
            setBoneRotation('head', clampRotation(gPitch * 0.3), clampRotation(gYaw * 0.4), 0, 0.3)
            setBoneRotation('neck', clampRotation(gPitch * 0.2), clampRotation(gYaw * 0.3), 0, 0.3)
        }

        // -------------------------------------------------------------------
        // HEAD MICRO-MOVEMENTS — continuous subtle motion (perlin-like)
        // -------------------------------------------------------------------
        headNoisePhase += delta * 0.7
        if (!isFBXActive) {
            const nYaw = smoothNoise(headNoisePhase, 0.9) * cfg.headMicroAmount
            const nPitch = smoothNoise(headNoisePhase, 1.1) * cfg.headMicroAmount * 0.5
            const nRoll = smoothNoise(headNoisePhase, 0.6) * cfg.headMicroAmount * 0.3

            const head = getBone('head')
            if (head) {
                const targetYaw = clampRotation(gYaw * 0.4 + nYaw)
                const targetPitch = clampRotation(gPitch * 0.3 + nPitch)
                const targetRoll = clampRotation(nRoll)
                head.rotation.y = THREE.MathUtils.lerp(head.rotation.y, targetYaw, 0.3)
                head.rotation.x = THREE.MathUtils.lerp(head.rotation.x, targetPitch, 0.3)
                head.rotation.z = THREE.MathUtils.lerp(head.rotation.z, targetRoll, 0.3)
            }
        }

        // -------------------------------------------------------------------
        // SHOULDER ROLLS — occasional subtle shifts
        // -------------------------------------------------------------------
        if (t >= nextShoulderRollTime && shoulderRollPhase === 0) {
            shoulderRollPhase = 1
            shoulderRollSide = Math.random() > 0.5 ? 1 : -1
        }

        if (shoulderRollPhase > 0) {
            shoulderRollPhase += delta * 1.5
            const roll = Math.sin(shoulderRollPhase * Math.PI) * cfg.shoulderRollAmount * shoulderRollSide

            if (!isFBXActive) {
                setBoneRotation('leftShoulder', 0, 0, clampRotation(roll * 0.5), 0.3)
                setBoneRotation('rightShoulder', 0, 0, clampRotation(-roll * 0.5), 0.3)
            }

            if (shoulderRollPhase >= 1) {
                shoulderRollPhase = 0
                nextShoulderRollTime = t + cfg.shoulderRollInterval[0] + Math.random() * (cfg.shoulderRollInterval[1] - cfg.shoulderRollInterval[0])
            }
        }

        // -------------------------------------------------------------------
        // HAND FIDGETS — subtle finger/hand movement
        // -------------------------------------------------------------------
        if (t >= nextHandFidgetTime && handFidgetPhase === 0) {
            handFidgetPhase = 1
            handFidgetSide = Math.random() > 0.5 ? 'leftHand' : 'rightHand'
        }

        if (handFidgetPhase > 0) {
            handFidgetPhase += delta * 2
            const fidget = Math.sin(handFidgetPhase * Math.PI * 2) * cfg.handFidgetAmount

            if (!isFBXActive) {
                const fRotX = clampRotation(fidget * 0.5)
                const fRotY = clampRotation(fidget * 0.3)
                const fRotZ = clampRotation(fidget * 0.2)
                setBoneRotation(handFidgetSide, fRotX, fRotY, fRotZ, 0.4)
                const lowerArm = handFidgetSide === 'leftHand' ? 'leftLowerArm' : 'rightLowerArm'
                setBoneRotation(lowerArm, clampRotation(fidget * 0.3), 0, clampRotation(fidget * 0.2), 0.4)
            }

            if (handFidgetPhase >= 1) {
                handFidgetPhase = 0
                nextHandFidgetTime = t + cfg.handFidgetInterval[0] + Math.random() * (cfg.handFidgetInterval[1] - cfg.handFidgetInterval[0])
            }
        }

        // -------------------------------------------------------------------
        // NODDING — occasional head nods while listening
        // -------------------------------------------------------------------
        if (cfg.nodInterval[0] < 99 && t >= nextNodTime && nodPhase === 0) {
            nodPhase = 1
        }

        if (nodPhase > 0) {
            nodPhase += delta * 2
            const nodAmount = Math.sin(nodPhase * Math.PI) * 0.08

            if (!isFBXActive) {
                const head = getBone('head')
                if (head) {
                    head.rotation.x = THREE.MathUtils.lerp(head.rotation.x, clampRotation(nodAmount), 0.4)
                }
            }

            if (nodPhase >= 1) {
                nodPhase = 0
                nextNodTime = t + cfg.nodInterval[0] + Math.random() * (cfg.nodInterval[1] - cfg.nodInterval[0])
            }
        }

        // -------------------------------------------------------------------
        // POSTURE SHIFTS — slow-changing spine/chest curvature
        // -------------------------------------------------------------------
        posturePhase += delta * 0.05
        if (posturePhase >= 1) {
            posturePhase = 0
            postureTarget = {
                spine: (Math.random() - 0.5) * 0.02,
                chest: (Math.random() - 0.5) * 0.015,
            }
        }

        postureCurrent.spine = lerp(postureCurrent.spine, postureTarget.spine, delta * 0.1)
        postureCurrent.chest = lerp(postureCurrent.chest, postureTarget.chest, delta * 0.1)

        if (!isFBXActive) {
            setBoneRotation('spine', clampRotation(postureCurrent.spine), 0, 0, 0.1)
            setBoneRotation('chest', clampRotation(postureCurrent.chest), 0, 0, 0.1)
        }
    }

    return {
        update,
        triggerBlink() {
            if (blinkPhase === 0) {
                blinkPhase = 1
                blinkSpeed = 20
            }
        },
        triggerWeightShift() {
            if (weightShiftPhase === 0) {
                weightShiftPhase = 1
                weightShiftTarget = {
                    x: (Math.random() - 0.5) * 0.03,
                    y: (Math.random() - 0.5) * 0.015,
                    z: (Math.random() - 0.5) * 0.03,
                }
            }
        },
    }
})()

function logAvatar(stage, status = "OK", details = "") {
    const suffix = details ? `: ${details}` : ""
    console.info(`[VRM] ${stage} -> ${status}${suffix}`)
}

const params = new URLSearchParams(window.location.search);

const avatar =
    params.get("avatar") || "Chidvi.vrm";

function pauseAvatarRuntime() {
    avatarUpdatePaused = true
    activeAction = null
    resetEmotionTargets()
    logAvatar("Renderer paused")
    logAvatar("Animation stopped")
    logAvatar("Idle animation stopped")
    logAvatar("Emotion controller detached")
    logAvatar("Lip sync detached")
    logAvatar("Look-at detached")
    logAvatar("Controllers detached")
}

function resumeAvatarRuntime() {
    avatarUpdatePaused = false
    logAvatar("Renderer resumed")
}

function formatAvatarError(error) {
    return error?.stack || error?.message || String(error)
}

function disposeSceneResources(root) {
    const counts = {
        geometry: 0,
        material: 0,
        texture: 0,
        skeleton: 0,
    }
    const disposedTextures = new Set()

    root.traverse((object) => {
        if (object.geometry?.dispose) {
            object.geometry.dispose()
            counts.geometry += 1
        }

        const materials = Array.isArray(object.material)
            ? object.material
            : object.material
              ? [object.material]
              : []

        for (const material of materials) {
            for (const value of Object.values(material)) {
                if (value?.isTexture && !disposedTextures.has(value)) {
                    value.dispose()
                    disposedTextures.add(value)
                    counts.texture += 1
                }
            }
            if (material.dispose) {
                material.dispose()
                counts.material += 1
            }
        }

        if (object.skeleton?.dispose) {
            object.skeleton.dispose()
            counts.skeleton += 1
        }
    })

    logAvatar("Geometry disposed", "OK", String(counts.geometry))
    logAvatar("Textures disposed", "OK", String(counts.texture))
    logAvatar("Materials disposed", "OK", String(counts.material))
    logAvatar("Skeleton disposed", "OK", String(counts.skeleton))
}

async function garbageCollectionSafePoint() {
    await new Promise((resolve) => requestAnimationFrame(() => resolve()))
    logAvatar("Garbage collection safe point")
}

async function disposeCurrentVRM() {
    if (!currentVRM) {
        logAvatar("Dispose old VRM", "SKIPPED", "no active VRM")
        currentAvatarFile = null
        currentMixer = null
        return
    }

    // Release AnimationManager actions bound to the outgoing mixer.
    // Clips stay cached so they are not re-downloaded after a switch.
    animManager.unbindMixer()

    const oldName = currentAvatarFile || currentVRM.meta?.name || currentVRM.scene?.name || "unknown"
    const oldVRM = currentVRM
    const oldScene = currentVRM.scene
    logAvatar("Dispose old VRM", "START", oldName)
    currentVRM = null
    currentAvatarFile = null
    currentMixer = null
    logAvatar("Animation mixer disposed", "OK", oldName)
    scene.remove(oldScene)
    logAvatar("Old VRM removed from scene", "OK", oldName)
    disposeSceneResources(oldScene)
    if (oldVRM.springBoneManager?.dispose) {
        oldVRM.springBoneManager.dispose()
        logAvatar("Physics disposed", "OK", oldName)
    } else {
        logAvatar("Physics disposed", "SKIPPED", "none")
    }
    logAvatar("Dispose old VRM", "OK", oldName)
    await garbageCollectionSafePoint()
}

async function loadVRMModel(avatarFile) {
    logAvatar(`Loading ${avatarFile}`)
    const gltf = await loader.loadAsync(`/${avatarFile}`)
    const vrm = gltf.userData.vrm
    if (!vrm) {
        throw new Error(`No VRM data found in ${avatarFile}`)
    }
    logAvatar("VRM loaded successfully", "OK", avatarFile)
    return vrm
}

function attachVRM(vrm, avatarFile) {
    VRMUtils.rotateVRM0(vrm)
    scene.add(vrm.scene)

    currentVRM = vrm
    currentAvatarFile = avatarFile
    currentMixer = new THREE.AnimationMixer(vrm.scene)
    // Bind the AnimationManager to the new mixer and start the idle loop.
    animManager.bindMixer(currentMixer, vrm)
    animManager.playIdle()
    logAvatar("Mixer created", "OK", avatarFile)
    activeAction = null
    applyEmotionTarget("idle")

    logAvatar(
        "Controllers attached",
        "OK",
        `avatar=${avatarFile}; expressions=${Boolean(vrm.expressionManager)}; humanoid=${Boolean(vrm.humanoid)}`
    )
    logAvatar("Idle animation started", "OK", avatarFile)
}

async function restorePreviousAvatar(previousAvatar, failedAvatar) {
    if (!previousAvatar) {
        logAvatar("Rollback", "SKIPPED", "no previous avatar")
        return
    }

    try {
        logAvatar("Rollback", "START", `${failedAvatar} -> ${previousAvatar}`)
        const previousVRM = await loadVRMModel(previousAvatar)
        attachVRM(previousVRM, previousAvatar)
        logAvatar("Rollback", "OK", previousAvatar)
    } catch (error) {
        lastAvatarSwitchStatus = "rollback_failed"
        lastAvatarSwitchError = formatAvatarError(error)
        console.error(`[VRM] Rollback failed -> ERROR: ${previousAvatar}`, lastAvatarSwitchError)
    }
}

async function switchAvatarNow(nextAvatar, requestSerial) {
    const previousAvatar = currentAvatarFile

    pauseAvatarRuntime()
    await disposeCurrentVRM()

    try {
        const vrm = await loadVRMModel(nextAvatar)
        if (requestSerial !== avatarLoadSerial) {
            logAvatar(
                "Stale avatar load ignored",
                "SKIPPED",
                `${nextAvatar}; request=${requestSerial}; active=${avatarLoadSerial}`
            )
            VRMUtils.deepDispose(vrm.scene)
            return false
        }
        attachVRM(vrm, nextAvatar)
        lastAvatarSwitchStatus = "ready"
        lastAvatarSwitchError = null
        logAvatar("Avatar switch completed", "OK", nextAvatar)
        logAvatar("Avatar Ready", "OK", nextAvatar)
        return true
    } catch (error) {
        lastAvatarSwitchStatus = "failed"
        lastAvatarSwitchError = formatAvatarError(error)
        console.error(`[VRM] Avatar switch failed -> ERROR: ${nextAvatar}`, lastAvatarSwitchError)
        await restorePreviousAvatar(previousAvatar, nextAvatar)
        return false
    }
}

async function drainQueuedAvatarSwitch() {
    if (!queuedAvatarFile || queuedAvatarFile === currentAvatarFile) {
        queuedAvatarFile = null
        return
    }

    const queued = queuedAvatarFile
    queuedAvatarFile = null
    await loadAvatar(queued)
}

async function loadAvatar(avatarFile) {
    const nextAvatar = avatarFile || "Chidvi.vrm"
    const requestSerial = ++avatarLoadSerial
    lastAvatarSwitchStatus = "requested"
    lastAvatarSwitchError = null
    logAvatar("Avatar switch requested", "START", `${nextAvatar}; request=${requestSerial}`)

    if (nextAvatar === currentAvatarFile && currentVRM && !avatarSwitchInProgress) {
        lastAvatarSwitchStatus = "ready"
        logAvatar("Avatar switch requested", "SKIPPED", `${nextAvatar} already active`)
        logAvatar("Avatar Ready", "OK", nextAvatar)
        return true
    }

    if (avatarSwitchInProgress) {
        queuedAvatarFile = nextAvatar
        lastAvatarSwitchStatus = "queued"
        logAvatar("Avatar switch queued", "OK", nextAvatar)
        return false
    }

    avatarSwitchInProgress = true
    lastAvatarSwitchStatus = "switching"

    try {
        return await switchAvatarNow(nextAvatar, requestSerial)
    } catch (error) {
        lastAvatarSwitchStatus = "failed"
        lastAvatarSwitchError = formatAvatarError(error)
        console.error(`[VRM] Unhandled avatar switch error -> ERROR: ${nextAvatar}`, lastAvatarSwitchError)
        return false
    } finally {
        resumeAvatarRuntime()
        avatarSwitchInProgress = false
        await drainQueuedAvatarSwitch()
    }
}

let lastFrameTime = 0
let frameCount = 0
let fpsDisplay = 0
let fpsTimer = 0

window.loadAvatar = loadAvatar
window.playAnimation = (name, options) => {
    animManager.play(name, options || {})
}
window.playGesture = (name, afterPlay) => {
    animManager.playGesture(name, afterPlay)
}
window.playEmotion = (name, afterPlay) => {
    animManager.playEmotion(name, afterPlay)
}
window.playState = (state) => {
    animManager.playState(state)
}
window.setAnimationProfile = (profileName) => {
    animManager.setProfile(profileName)
}
window.avatarDiagnostics = () => {
    const animDiag = animManager.getDiagnostics()
    return {
        // Avatar status
        currentAvatarFile,
        hasActiveVRM: Boolean(currentVRM),
        hasMixer: Boolean(currentMixer),
        avatarSwitchInProgress,
        queuedAvatarFile,
        avatarUpdatePaused,
        lastAvatarSwitchStatus,
        lastAvatarSwitchError,
        sceneChildren: scene.children.length,

        // Emotion & action
        emotion: avatarEmotion,
        activeAction,

        // Render FPS
        renderFPS: fpsDisplay,

        // Full animation diagnostics from AnimationManager
        animation: animDiag,
    }
}

const clock = new THREE.Clock()

loadAvatar(avatar)

// Preload the most-used clips so the first state/gesture switch is instant.
animManager.preload([
    'idle',
    'breathing_idle',
    'talking',
    'thinking',
    'wave',
]).catch((err) => console.warn('[VRM] Animation preload error:', err))

function animate() {

    requestAnimationFrame(animate)

    const delta = Math.min(clock.getDelta(), 0.05) // cap to prevent spiral of death
    const t = clock.elapsedTime

    // FPS counter
    frameCount++
    fpsTimer += delta
    if (fpsTimer >= 1) {
        fpsDisplay = Math.round(frameCount / fpsTimer)
        frameCount = 0
        fpsTimer = 0
    }

    if (!avatarUpdatePaused && currentVRM) {

        const vrm = currentVRM

        vrm.update(delta)
        if (currentMixer) {
            currentMixer.update(delta)
            // Drive AnimationManager cross-fades every frame.
            animManager.update(delta)
        }

        const expressionManager = vrm.expressionManager

        if (expressionManager) {
            // Lip sync during speaking/laughing
            if (avatarEmotion === "speaking" || avatarEmotion === "laughing") {
                mouthPhase += delta * 12
                setExpressionTarget("aa", 0.18 + Math.abs(Math.sin(mouthPhase)) * 0.55)
            } else if (expressionTargets.aa) {
                setExpressionTarget("aa", expressionTargets.aa * 0.82)
            }

            // Smooth expression lerp
            for (const [name, target] of Object.entries(expressionTargets)) {
                const current = expressionManager.getValue(name) || 0
                expressionManager.setValue(
                    name,
                    THREE.MathUtils.lerp(current, target, Math.min(1, delta * 8))
                )
            }
        }

        // Behaviour Director: drives breathing, blinking, weight shifts, gaze, micro-movements
        BehaviourDirector.update(delta, t)

        // Natural scene rotation — adds subtle full-body emphasis
        const attentive = avatarEmotion === "listening" ? 1 : 0
        const thoughtful = avatarEmotion === "thinking" || avatarEmotion === "confused" ? 1 : 0
        const speaking = avatarEmotion === "speaking" || avatarEmotion === "laughing" ? 1 : 0

        vrm.scene.rotation.y =
            Math.sin(t * (0.45 + speaking * 0.35)) * (0.06 + attentive * 0.03)
        vrm.scene.rotation.x =
            Math.sin(t * 0.7) * 0.015 - thoughtful * 0.04

        // Apply procedural action poses (look directions)
        applyActionPose(t, delta)
    }

    renderer.render(scene, camera)
}

animate()

window.addEventListener("resize", () => {
    camera.aspect = window.innerWidth / window.innerHeight
    camera.updateProjectionMatrix()
    renderer.setSize(window.innerWidth, window.innerHeight)
})

function applyActionPose(t, delta) {
    if (!activeAction) return

    const elapsed = t - actionStartedAt
    if (elapsed > 2.8) {
        activeAction = null
        return
    }

    const blend = Math.min(1, delta * 12)
    const once = Math.sin(Math.min(1, elapsed / 1.4) * Math.PI)

    if (activeAction === "look_left") {
        setBoneRotation("head", 0, clampRotation(0.5 * once), 0, blend)
        setBoneRotation("neck", 0, clampRotation(0.3 * once), 0, blend)
        setBoneRotation("leftEye", 0, clampRotation(0.6 * once), 0, blend)
        setBoneRotation("rightEye", 0, clampRotation(0.6 * once), 0, blend)
    } else if (activeAction === "look_right") {
        setBoneRotation("head", 0, clampRotation(-0.5 * once), 0, blend)
        setBoneRotation("neck", 0, clampRotation(-0.3 * once), 0, blend)
        setBoneRotation("leftEye", 0, clampRotation(-0.6 * once), 0, blend)
        setBoneRotation("rightEye", 0, clampRotation(-0.6 * once), 0, blend)
    } else if (activeAction === "look_up") {
        setBoneRotation("head", clampRotation(0.3 * once), 0, 0, blend)
        setBoneRotation("neck", clampRotation(0.2 * once), 0, 0, blend)
        setBoneRotation("leftEye", clampRotation(0.4 * once), 0, 0, blend)
        setBoneRotation("rightEye", clampRotation(0.4 * once), 0, 0, blend)
    } else if (activeAction === "look_down") {
        setBoneRotation("head", clampRotation(-0.3 * once), 0, 0, blend)
        setBoneRotation("neck", clampRotation(-0.2 * once), 0, 0, blend)
        setBoneRotation("leftEye", clampRotation(-0.4 * once), 0, 0, blend)
        setBoneRotation("rightEye", clampRotation(-0.4 * once), 0, 0, blend)
    } else if (activeAction === "look_forward") {
        setBoneRotation("head", -0.02, 0, 0, blend)
        setBoneRotation("neck", -0.02, 0, 0, blend)
    }
}
