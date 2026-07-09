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

const params = new URLSearchParams(window.location.search);

const avatar =
    params.get("avatar") || "Chidvi.vrm";

function disposeCurrentVRM() {
    if (!currentVRM) {
        console.info("[CHIDVI avatar] dispose skipped: no active VRM")
        return
    }

    const oldName = currentVRM.meta?.name || currentVRM.scene?.name || "unknown"
    console.info(`[CHIDVI avatar] disposing current VRM: ${oldName}`)
    scene.remove(currentVRM.scene)
    VRMUtils.deepDispose(currentVRM.scene)
    currentVRM = null
    console.info("[CHIDVI avatar] current VRM disposed")
}

function loadAvatar(avatarFile) {
    const nextAvatar = avatarFile || "Chidvi.vrm"
    console.info(`[CHIDVI avatar] load request received: ${nextAvatar}`)
    disposeCurrentVRM()

    loader.load(

        `/${nextAvatar}`,

        (gltf) => {

            const vrm = gltf.userData.vrm

            VRMUtils.rotateVRM0(vrm)

            scene.add(vrm.scene)

            currentVRM = vrm
            activeAction = null
            blink = 0
            nextBlink = clock.elapsedTime + 1 + Math.random() * 2
            applyEmotionTarget(avatarEmotion)
            applyProceduralPose(clock.elapsedTime, 1)
            console.info(
                `[CHIDVI avatar] loaded ${nextAvatar}; scene children=${scene.children.length}; expressions=${Boolean(vrm.expressionManager)}; humanoid=${Boolean(vrm.humanoid)}`
            )

        },

        (progress) => {

            console.info(`[CHIDVI avatar] loading ${nextAvatar}: ${progress.loaded}`)

        },

        (error) => {

            console.error(`[CHIDVI avatar] failed to load ${nextAvatar}`, error)

        }

    )
}

window.loadAvatar = loadAvatar

const clock = new THREE.Clock()

loadAvatar(avatar)

function animate() {

    requestAnimationFrame(animate)

    const delta = clock.getDelta()

    if (currentVRM) {

        currentVRM.update(delta);

        const t = clock.elapsedTime;
        const expressionManager = currentVRM.expressionManager

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

        currentVRM.scene.rotation.y =
            Math.sin(t * (0.45 + speaking * 0.35)) * (0.06 + attentive * 0.03);
        currentVRM.scene.rotation.x =
            Math.sin(t * 0.7) * 0.015 - thoughtful * 0.04;

        // Breathing
        const breathe =
            1 + Math.sin(t * 2.2) * 0.012;

        currentVRM.scene.scale.set(
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
