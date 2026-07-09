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

const params = new URLSearchParams(window.location.search);

const avatar =
    params.get("avatar") || "Chidvi.vrm";

loader.load(

    `/${avatar}`,

    (gltf) => {

        const vrm = gltf.userData.vrm

        VRMUtils.rotateVRM0(vrm)

        scene.add(vrm.scene)

        currentVRM = vrm
        applyEmotionTarget(avatarEmotion)

    },

    (progress) => {

        console.log(progress.loaded)

    },

    (error) => {

        console.error(error)

    }

)

const clock = new THREE.Clock()

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

    }

    renderer.render(scene, camera)

}

animate()  

window.addEventListener("resize", () => {

    camera.aspect = window.innerWidth / window.innerHeight

    camera.updateProjectionMatrix()

    renderer.setSize(window.innerWidth, window.innerHeight)

})
