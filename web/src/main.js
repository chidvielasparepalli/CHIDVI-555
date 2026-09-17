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
  100,
)
camera.position.set(0, 1.4, 2.2)

const renderer = new THREE.WebGLRenderer({
  antialias: true,
  alpha: true,
  powerPreference: 'high-performance',
})
renderer.setSize(window.innerWidth, window.innerHeight)
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
renderer.outputColorSpace = THREE.SRGBColorSpace
renderer.toneMapping = THREE.ACESFilmicToneMapping
renderer.toneMappingExposure = 1.1

document.body.style.margin = '0'
document.body.appendChild(renderer.domElement)

scene.add(new THREE.HemisphereLight(0xffffff, 0x223344, 2.2))

const keyLight = new THREE.DirectionalLight(0xffffff, 2.0)
keyLight.position.set(1, 2, 3)
scene.add(keyLight)

const loader = new GLTFLoader()
loader.register((parser) => new VRMLoaderPlugin(parser))

let currentVRM = null
let blinkStartedAt = -1
let nextBlink = 2

const params = new URLSearchParams(window.location.search)
const requestedAvatar = params.get('avatar')
const allowedAvatars = new Set(['Chidvi.vrm', 'Hinata.vrm'])
const avatar = allowedAvatars.has(requestedAvatar) ? requestedAvatar : 'Chidvi.vrm'

function showError(message) {
  console.error(`[CHIDVI VRM] ${message}`)
  const el = document.createElement('div')
  el.textContent = message
  el.style.cssText = [
    'position:fixed', 'inset:0', 'display:grid', 'place-items:center',
    'padding:24px', 'box-sizing:border-box', 'font:14px system-ui,sans-serif',
    'color:#d8f7ff', 'background:rgba(0,6,10,.92)', 'text-align:center',
    'z-index:9999',
  ].join(';')
  document.body.appendChild(el)
}

loader.load(
  `/${encodeURIComponent(avatar)}`,
  (gltf) => {
    const vrm = gltf.userData.vrm
    if (!vrm) {
      showError('VRM model could not be initialized.')
      return
    }

    // rotateVRM0 is only valid for legacy VRM 0.x models.
    // Calling it unconditionally can break modern VRM 1.0 avatars.
    const specVersion = String(vrm.meta?.metaVersion ?? vrm.meta?.specVersion ?? '')
    if (specVersion.startsWith('0')) {
      VRMUtils.rotateVRM0(vrm)
    }

    // Reduce unnecessary geometry/joints when supported by the installed VRM version.
    if (typeof VRMUtils.removeUnnecessaryVertices === 'function') {
      VRMUtils.removeUnnecessaryVertices(gltf.scene)
    }
    if (typeof VRMUtils.removeUnnecessaryJoints === 'function') {
      VRMUtils.removeUnnecessaryJoints(gltf.scene)
    }

    scene.add(vrm.scene)
    currentVRM = vrm
  },
  undefined,
  (error) => {
    showError(`Unable to load ${avatar}. Check that the VRM file exists in web/public.`)
    console.error('[CHIDVI VRM] Load failed:', error)
  },
)

const clock = new THREE.Clock()

function animate() {
  requestAnimationFrame(animate)
  const delta = clock.getDelta()
  const t = clock.elapsedTime

  if (currentVRM) {
    currentVRM.update(delta)

    // Natural, lightweight blinking. Only write the expression when the model exposes it.
    const expressions = currentVRM.expressionManager
    if (expressions?.getExpression?.('blink')) {
      if (t >= nextBlink && blinkStartedAt < 0) blinkStartedAt = t

      if (blinkStartedAt >= 0) {
        const progress = Math.min((t - blinkStartedAt) / 0.16, 1)
        const value = Math.sin(progress * Math.PI)
        expressions.setValue('blink', value)
        if (progress >= 1) {
          expressions.setValue('blink', 0)
          blinkStartedAt = -1
          nextBlink = t + 2 + Math.random() * 4
        }
      }
    }

    // Subtle idle motion; preserve the model's base scale.
    currentVRM.scene.rotation.y = Math.sin(t * 0.5) * 0.06
    const breathe = 1 + Math.sin(t * 2.2) * 0.008
    currentVRM.scene.scale.setScalar(breathe)
  }

  renderer.render(scene, camera)
}

animate()

window.addEventListener('resize', () => {
  camera.aspect = window.innerWidth / window.innerHeight
  camera.updateProjectionMatrix()
  renderer.setSize(window.innerWidth, window.innerHeight)
})
