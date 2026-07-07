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
        if (t > nextBlink) {

            blink += delta * 10

            const value = Math.sin(blink)

            if (currentVRM.expressionManager) {

                currentVRM.expressionManager.setValue(
                    "blink",
                    Math.max(0, value)
                )

            }

            if (blink > Math.PI) {

                blink = 0

                nextBlink =
                    t + 2 + Math.random() * 4

            }

        }
        // Gentle idle rotation
        currentVRM.scene.rotation.y =
            Math.sin(t * 0.5) * 0.08;

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