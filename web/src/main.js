import './style.css'

import * as THREE from 'three'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'
import { VRMLoaderPlugin, VRMUtils } from '@pixiv/three-vrm'

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
let avatarLoadSerial = 0
let avatarSwitchInProgress = false
let queuedAvatarFile = null
let avatarUpdatePaused = false
let blink = 0
let nextBlink = 2
let avatarEmotion = "idle"
let mouthPhase = 0
let activeAction = null
let actionStartedAt = 0
const expressionTargets = {}

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
}

window.setAvatarEmotion = applyEmotionTarget
window.setAvatarState = applyEmotionTarget
window.performAvatarAction = (action) => {
    activeAction = String(action || "").toLowerCase()
    actionStartedAt = clock.elapsedTime
    if (activeAction === "smile") {
        applyEmotionTarget("happy")
    } else if (activeAction === "laugh") {
        applyEmotionTarget("laughing")
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
        setBoneRotation("rightUpperArm", -0.75, -0.15, -2.15, blend)
        setBoneRotation("rightLowerArm", -0.75, -0.3, -0.35 + pulse * 0.55, blend)
        setBoneRotation("rightHand", 0.1, pulse * 0.35, -0.2, blend)
    } else if (activeAction === "nod") {
        setBoneRotation("head", -0.22 + pulse * 0.18, 0, 0, blend)
    } else if (activeAction === "shake_head") {
        setBoneRotation("head", 0, pulse * 0.35, 0, blend)
    } else if (activeAction === "bow") {
        setBoneRotation("chest", -0.42 * once, 0, 0, blend)
        setBoneRotation("head", -0.22 * once, 0, 0, blend)
    } else if (activeAction === "look_left") {
        setBoneRotation("head", 0, 0.45 * once, 0, blend)
    } else if (activeAction === "look_right") {
        setBoneRotation("head", 0, -0.45 * once, 0, blend)
    } else if (activeAction === "look_up") {
        setBoneRotation("head", 0.24 * once, 0, 0, blend)
    } else if (activeAction === "look_down") {
        setBoneRotation("head", -0.24 * once, 0, 0, blend)
    }
}

function logAvatar(stage, status = "OK", details = "") {
    const suffix = details ? `: ${details}` : ""
    console.info(`[AVATAR] ${stage} -> ${status}${suffix}`)
}

const params = new URLSearchParams(window.location.search);

const avatar =
    params.get("avatar") || "Chidvi.vrm";

function pauseAvatarRuntime() {
    avatarUpdatePaused = true
    activeAction = null
    resetEmotionTargets()
    logAvatar("Current avatar paused")
    logAvatar("Animation stopped")
    logAvatar("Emotion controller detached")
    logAvatar("Lip sync detached")
    logAvatar("Look-at detached")
}

function resumeAvatarRuntime() {
    avatarUpdatePaused = false
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
        return
    }

    const oldName = currentAvatarFile || currentVRM.meta?.name || currentVRM.scene?.name || "unknown"
    const oldScene = currentVRM.scene
    logAvatar("Dispose old VRM", "START", oldName)
    scene.remove(oldScene)
    logAvatar("Old VRM removed from scene", "OK", oldName)
    disposeSceneResources(oldScene)
    currentVRM = null
    currentAvatarFile = null
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
        console.error(`[AVATAR] Rollback failed -> ERROR: ${previousAvatar}`, error)
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
        logAvatar("Avatar switch completed", "OK", nextAvatar)
        return true
    } catch (error) {
        console.error(`[AVATAR] Avatar switch failed -> ERROR: ${nextAvatar}`, error)
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
    logAvatar("Avatar switch requested", "START", `${nextAvatar}; request=${requestSerial}`)

    if (avatarSwitchInProgress) {
        queuedAvatarFile = nextAvatar
        logAvatar("Avatar switch queued", "OK", nextAvatar)
        return false
    }

    avatarSwitchInProgress = true

    try {
        return await switchAvatarNow(nextAvatar, requestSerial)
    } catch (error) {
        console.error(`[AVATAR] Unhandled avatar switch error -> ERROR: ${nextAvatar}`, error)
        return false
    } finally {
        resumeAvatarRuntime()
        avatarSwitchInProgress = false
        await drainQueuedAvatarSwitch()
    }
}

window.loadAvatar = loadAvatar
window.avatarDiagnostics = () => ({
    currentAvatarFile,
    hasActiveVRM: Boolean(currentVRM),
    avatarSwitchInProgress,
    queuedAvatarFile,
    avatarUpdatePaused,
    sceneChildren: scene.children.length,
    emotion: avatarEmotion,
    activeAction,
})

const clock = new THREE.Clock()

loadAvatar(avatar)

function animate() {

    requestAnimationFrame(animate)

    const delta = clock.getDelta()

    if (!avatarUpdatePaused && currentVRM) {

        const vrm = currentVRM

        vrm.update(delta);

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
