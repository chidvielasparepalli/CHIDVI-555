import './style.css'

import * as THREE from 'three'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'
import { FBXLoader } from 'three/examples/jsm/loaders/FBXLoader.js'
import { VRMLoaderPlugin, VRMUtils } from '@pixiv/three-vrm'
import { createAnimationManager } from './animation-manager.js'

const scene = new THREE.Scene()
scene.background = null

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

document.body.style.margin = "0"
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
let blink = 0
let nextBlink = 2
let avatarEmotion = "idle"
let mouthPhase = 0
let activeAction = null
let actionStartedAt = 0
const expressionTargets = {}

// AnimationManager: loads/caches/plays Mixamo FBX clips on the active VRM.
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

function applyEmotionTarget(emotion) {
    avatarEmotion = String(emotion || "idle").toLowerCase()
    resetEmotionTargets()
    const values = emotionExpressions[avatarEmotion] || emotionExpressions.idle
    for (const [name, value] of Object.entries(values)) {
        setExpressionTarget(name, value)
    }
    // Phase 3/5: drive skeleton animations from the runtime state/emotion.
    animManager.onStateChange(avatarEmotion)
}

window.setAvatarEmotion = applyEmotionTarget
window.setAvatarState = applyEmotionTarget
window.performAvatarAction = (action) => {
    const a = String(action || "").toLowerCase()
    // Prefer a real Mixamo FBX clip when one is available for this action.
    if (animManager.hasAnimation(a)) {
        animManager.playGesture(a)
        // Keep facial expression in sync for actions that carry an emotion.
        if (a === "smile" || a === "happy") {
            applyEmotionTarget("happy")
        } else if (a === "laugh" || a === "laughing") {
            applyEmotionTarget("laughing")
        } else if (a === "thinking") {
            applyEmotionTarget("thinking")
        } else if (a === "greeting" || a === "wave" || a === "salute") {
            applyEmotionTarget("happy")
        } else if (a === "angry") {
            applyEmotionTarget("angry")
        } else if (a === "sad") {
            applyEmotionTarget("sad")
        }
        return
    }
    // Fall back to procedural bone animation for actions without an FBX
    // (e.g. look_left, look_right, look_up, look_down, look_forward).
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
    if (!bone) {
        return
    }
    bone.rotation.x = THREE.MathUtils.lerp(bone.rotation.x, x, blend)
    bone.rotation.y = THREE.MathUtils.lerp(bone.rotation.y, y, blend)
    bone.rotation.z = THREE.MathUtils.lerp(bone.rotation.z, z, blend)
}

function applyProceduralPose(t, delta) {
    // Back off when an FBX clip is driving the skeleton to avoid fighting it.
    if (animManager.isFBXActive()) return
    const blend = Math.min(1, delta * 7)
    const breathing = Math.sin(t * 2.1) * 0.025
    const sway = Math.sin(t * 0.7) * 0.035
    const attentive = avatarEmotion === "listening" ? 1 : 0
    const thoughtful = avatarEmotion === "thinking" || avatarEmotion === "confused" ? 1 : 0
    const speaking = avatarEmotion === "speaking" || avatarEmotion === "laughing" ? 1 : 0

    setBoneRotation("chest", breathing, sway * 0.3, -sway * 0.2, blend)
    setBoneRotation("spine", breathing * 0.45, 0, sway * 0.15, blend)
    setBoneRotation("neck", -0.03 * attentive, 0, sway * 0.25, blend)
    setBoneRotation("head", -0.05 * thoughtful + Math.sin(t * 0.9) * 0.018, sway * 0.4, sway * 0.15, blend)

    // Relaxed arm posture to avoid static T-pose.
    setBoneRotation("leftUpperArm", 0.25 + speaking * 0.08, 0.08, 1.15, blend)
    setBoneRotation("rightUpperArm", 0.25 + speaking * 0.08, -0.08, -1.15, blend)
    setBoneRotation("leftLowerArm", 0.12, 0.03, 0.25, blend)
    setBoneRotation("rightLowerArm", 0.12, -0.03, -0.25, blend)
    setBoneRotation("leftHand", 0, 0, 0.08, blend)
    setBoneRotation("rightHand", 0, 0, -0.08, blend)

    const eyeYaw = Math.sin(t * 0.45) * 0.08
    setBoneRotation("leftEye", 0, eyeYaw, 0, blend)
    setBoneRotation("rightEye", 0, eyeYaw, 0, blend)
}

function applyActionPose(t, delta) {
    if (!activeAction) {
        return
    }

    const elapsed = t - actionStartedAt
    if (elapsed > 2.8) {
        activeAction = null
        return
    }

    const blend = Math.min(1, delta * 12)
    const pulse = Math.sin(elapsed * Math.PI * 4)
    const once = Math.sin(Math.min(1, elapsed / 1.4) * Math.PI)

    if (activeAction === "wave") {
        setBoneRotation("rightUpperArm", -0.55, -0.25, -1.85, blend)
        setBoneRotation("rightLowerArm", -0.8, -0.2, -0.45 + pulse * 0.45, blend)
        setBoneRotation("rightHand", 0.08, pulse * 0.32, -0.18, blend)
    } else if (activeAction === "point") {
        setBoneRotation("chest", -0.04, 0.08 * once, 0, blend)
        setBoneRotation("rightUpperArm", -1.05, -0.28, -1.2, blend)
        setBoneRotation("rightLowerArm", -0.38, -0.12, -0.08, blend)
        setBoneRotation("rightHand", 0, -0.08, -0.02, blend)
        setBoneRotation("head", -0.02, 0.08 * once, 0, blend)
    } else if (activeAction === "clap") {
        const clap = Math.abs(Math.sin(elapsed * Math.PI * 3))
        setBoneRotation("leftUpperArm", -0.45, 0.25, 0.85 - clap * 0.35, blend)
        setBoneRotation("rightUpperArm", -0.45, -0.25, -0.85 + clap * 0.35, blend)
        setBoneRotation("leftLowerArm", -0.45, 0.15, 0.65 - clap * 0.45, blend)
        setBoneRotation("rightLowerArm", -0.45, -0.15, -0.65 + clap * 0.45, blend)
        setBoneRotation("leftHand", 0, 0, 0.22 - clap * 0.2, blend)
        setBoneRotation("rightHand", 0, 0, -0.22 + clap * 0.2, blend)
    } else if (activeAction === "nod") {
        setBoneRotation("head", -0.22 + pulse * 0.18, 0, 0, blend)
    } else if (activeAction === "shake_head") {
        setBoneRotation("head", 0, pulse * 0.35, 0, blend)
    } else if (activeAction === "bow") {
        setBoneRotation("chest", -0.42 * once, 0, 0, blend)
        setBoneRotation("head", -0.22 * once, 0, 0, blend)
    } else if (activeAction === "laugh") {
        setBoneRotation("chest", Math.sin(elapsed * Math.PI * 5) * 0.045, 0, 0, blend)
        setBoneRotation("head", -0.08 + Math.sin(elapsed * Math.PI * 5) * 0.05, 0, 0, blend)
        setBoneRotation("leftUpperArm", 0.18, 0.08, 1.0, blend)
        setBoneRotation("rightUpperArm", 0.18, -0.08, -1.0, blend)
    } else if (activeAction === "thinking") {
        setBoneRotation("head", -0.08, 0.1 * once, 0.04, blend)
        setBoneRotation("rightUpperArm", -0.45, -0.18, -0.95, blend)
        setBoneRotation("rightLowerArm", -1.05, -0.18, -0.45, blend)
        setBoneRotation("rightHand", -0.18, -0.12, -0.08, blend)
    } else if (activeAction === "greeting") {
        setBoneRotation("chest", -0.16 * once, 0, 0, blend)
        setBoneRotation("head", -0.08 * once, 0, 0, blend)
        setBoneRotation("rightUpperArm", -0.65, -0.18, -1.72, blend)
        setBoneRotation("rightLowerArm", -0.7, -0.18, -0.35 + pulse * 0.22, blend)
    } else if (activeAction === "look_left") {
        setBoneRotation("head", 0, 0.45 * once, 0, blend)
    } else if (activeAction === "look_right") {
        setBoneRotation("head", 0, -0.45 * once, 0, blend)
    } else if (activeAction === "look_up") {
        setBoneRotation("head", 0.24 * once, 0, 0, blend)
    } else if (activeAction === "look_down") {
        setBoneRotation("head", -0.24 * once, 0, 0, blend)
    } else if (activeAction === "look_forward") {
        setBoneRotation("head", -0.02, 0, 0, blend)
        setBoneRotation("neck", -0.02, 0, 0, blend)
    }
}

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
    animManager.bindMixer(currentMixer)
    animManager.playIdle()
    logAvatar("Mixer created", "OK", avatarFile)
    activeAction = null
    blink = 0
    nextBlink = clock.elapsedTime + 1 + Math.random() * 2
    applyEmotionTarget("idle")
    applyProceduralPose(clock.elapsedTime, 1)

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
window.avatarDiagnostics = () => ({
    currentAvatarFile,
    hasActiveVRM: Boolean(currentVRM),
    hasMixer: Boolean(currentMixer),
    avatarSwitchInProgress,
    queuedAvatarFile,
    avatarUpdatePaused,
    lastAvatarSwitchStatus,
    lastAvatarSwitchError,
    sceneChildren: scene.children.length,
    emotion: avatarEmotion,
    activeAction,
    animation: animManager.getDiagnostics(),
})

const clock = new THREE.Clock()

loadAvatar(avatar)

// Preload the most-used clips so the first state/gesture switch is instant.
// Non-blocking: errors only log a warning.
animManager.preload([
    'idle',
    'breathing_idle',
    'talking',
    'thinking',
    'wave',
]).catch((err) => console.warn('[VRM] Animation preload error:', err))

function animate() {

    requestAnimationFrame(animate)

    const delta = clock.getDelta()

    if (!avatarUpdatePaused && currentVRM) {

        const vrm = currentVRM

        vrm.update(delta);
        if (currentMixer) {
            currentMixer.update(delta)
            // Drive AnimationManager cross-fades every frame.
            animManager.update(delta)
        }

        const t = clock.elapsedTime;
        const expressionManager = vrm.expressionManager

        if (expressionManager) {
            if (avatarEmotion === "speaking" || avatarEmotion === "laughing") {
                mouthPhase += delta * 12
                setExpressionTarget("aa", 0.18 + Math.abs(Math.sin(mouthPhase)) * 0.55)
            } else if (expressionTargets.aa) {
                setExpressionTarget("aa", expressionTargets.aa * 0.82)
            }

            for (const [name, target] of Object.entries(expressionTargets)) {
                const current = expressionManager.getValue(name) || 0
                expressionManager.setValue(
                    name,
                    THREE.MathUtils.lerp(current, target, Math.min(1, delta * 8))
                )
            }
        }

        if (t > nextBlink) {

            blink += delta * 10

            const value = Math.sin(blink)

            if (expressionManager) {

                expressionManager.setValue(
                    "blink",
                    Math.max(expressionTargets.blink || 0, value)
                )

            }

            if (blink > Math.PI) {

                blink = 0

                nextBlink =
                    t + 2 + Math.random() * 4

            }

        }
        const attentive = avatarEmotion === "listening" ? 1 : 0
        const thoughtful = avatarEmotion === "thinking" || avatarEmotion === "confused" ? 1 : 0
        const speaking = avatarEmotion === "speaking" || avatarEmotion === "laughing" ? 1 : 0

        vrm.scene.rotation.y =
            Math.sin(t * (0.45 + speaking * 0.35)) * (0.06 + attentive * 0.03);
        vrm.scene.rotation.x =
            Math.sin(t * 0.7) * 0.015 - thoughtful * 0.04;

        // Breathing
        const breathe =
            1 + Math.sin(t * 2.2) * 0.012;

        vrm.scene.scale.set(
            breathe,
            breathe,
            breathe
        );

        applyProceduralPose(t, delta)
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
