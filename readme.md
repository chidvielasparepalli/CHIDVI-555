# ⚡ CHIDVI-555

### Cross-Platform Personal AI Assistant

**CHIDVI-555** is a desktop AI assistant built around real-time voice interaction, Gemini-powered reasoning, tool execution, computer automation, memory, vision, and interactive VRM avatars.

> **Project status:** Active prototype / research project. Some advanced capabilities are experimental and may require additional configuration or external services.

---

## ✨ What CHIDVI-555 Does

CHIDVI is designed to move beyond a simple chat interface and act as a computer companion that can **listen → understand → act → respond**.

| Capability | Status |
|---|---|
| 🎙️ Gemini Live voice conversation | Active |
| 🧠 CHIDVI / HINATA personalities | Active |
| 💾 Persistent memory | Active |
| 🖥️ Desktop automation | Active / platform-dependent |
| 🌐 Browser automation | Active / platform-dependent |
| 📂 File processing | Active |
| 👁️ Screen / image understanding | Available through tools |
| 🤖 Gemini function calling | Active |
| 🔊 Streaming voice output | Active |
| 🎭 VRM avatar rendering | Active |
| 😊 Avatar expressions / blinking | Active in web renderer |
| 🧩 Multi-step automation | Experimental |
| 📱 Phone control | Experimental |
| 🧪 Offline AI features | Experimental |

---

## 🧠 Core Interaction Loop

```text
User
  ↓
Voice / Keyboard
  ↓
Speech + Intent Processing
  ↓
Gemini
  ↓
Tool / Automation Selection
  ↓
┌───────────────┬───────────────┬───────────────┐
│ Desktop       │ Browser       │ File / Vision │
│ Automation    │ Automation    │ Tools         │
└───────────────┴───────────────┴───────────────┘
  ↓
Result + Memory Update
  ↓
Voice + UI + Avatar Response
```

---

## 🎭 VRM Avatar System

CHIDVI-555 includes a browser-based Three.js renderer using **`@pixiv/three-vrm`**.

Available avatars:

- `Chidvi.vrm`
- `Hinata.vrm`

The renderer now treats legacy **VRM 0.x** and modern **VRM 1.0** models differently instead of applying legacy conversion to every model. Avatar selection is restricted to the bundled models, load failures are surfaced cleanly, and rendering uses a capped device pixel ratio for better stability.

VRM assets used by the web renderer live in:

```text
web/public/Chidvi.vrm
web/public/Hinata.vrm
```

The desktop UI selects the personality avatar through the local Vite page.

---

## 🎤 Voice Pipeline

```text
Microphone
   ↓
Speech / Gemini Live
   ↓
Intent + Reasoning
   ↓
Tool Execution
   ↓
Response
   ↓
Streaming Audio + Avatar State
```

The application is designed for continuous interaction with interruption handling rather than one-shot text commands.

---

## 🛠️ Tool & Automation Layer

Current integrations include modules for:

- Application launching
- Desktop controls
- Browser navigation and automation
- Web search
- YouTube
- Weather
- Flight search
- File processing and file control
- Screenshots / screen processing
- Code assistance
- Developer workflows
- Reminders
- Messaging
- Game updates
- Computer settings

Individual capabilities depend on the operating system, installed applications, permissions, API keys, and external services.

---

## 💾 Memory

The memory layer is intended to preserve useful context between sessions, including:

- User preferences
- Previous conversations
- Projects and workflow context
- Frequently used information
- Long-term assistant state

Memory components are kept under `memory/` and are accessed by the main assistant runtime.

---

## 🎨 Personalities

### CHIDVI

- Professional
- Technical
- Direct
- Task-oriented

### HINATA

- Friendly
- Conversational
- Caring
- Emotion-oriented

Personality selection also controls the corresponding avatar and UI theme.

---

## 📁 Project Structure

```text
CHIDVI-555/
├── actions/          # Computer, browser, files, web and task actions
├── agent/            # Agent-oriented modules and planning placeholders
├── api/              # API helpers / key management
├── automation/       # Planning, execution and error handling
├── avatar/            # VRM assets and animation engine
├── avatars/           # Avatar state, events and service layer
├── commands/          # Command routing
├── config/            # Runtime configuration
├── core/              # Core assistant services, speech and personality
├── memory/            # Persistent memory components
├── offline/           # Experimental offline components
├── personality/       # CHIDVI and HINATA personalities
├── plugins/           # Plugin infrastructure
├── security/          # Authentication / permission experiments
├── ui_core/           # UI support modules and themes
├── vision/            # Vision-related components
├── voice/             # Voice module structure
├── web/               # Three.js + VRM avatar renderer
├── main.py            # Main application entry point
├── ui.py              # Desktop UI
└── requirements.txt   # Python dependencies
```

---

## ⚙️ Requirements

- Python **3.11+**
- Node.js + npm
- Microphone for voice interaction
- Internet connection for Gemini-powered features
- Gemini API key
- Windows / Linux / macOS (some automation features are OS-specific)

---

## 🚀 Installation

### 1. Clone

```bash
git clone https://github.com/chidvielasparepalli/CHIDVI-555.git
cd CHIDVI-555
```

### 2. Create the Python environment

```bash
python -m venv .venv
```

**Windows:**

```powershell
.venv\Scripts\activate
```

**Linux / macOS:**

```bash
source .venv/bin/activate
```

### 3. Install Python dependencies

```bash
pip install -r requirements.txt
```

If the project uses Playwright-based browser automation on your machine:

```bash
playwright install
```

### 4. Configure the Gemini key

Create a `.env` file in the repository root:

```env
GEMINI_API_KEY=your_gemini_api_key
```

Keep API keys out of Git. `config/api_keys.json`, `.env`, logs, Python caches, `node_modules`, and build output are ignored by Git.

### 5. Install the VRM web renderer

```bash
cd web
npm install
```

### 6. Start the web renderer

```bash
npm run dev
```

The renderer serves the bundled VRM models from `web/public/`.

### 7. Start CHIDVI

From the repository root:

```bash
python main.py
```

The desktop UI expects the local web renderer to be available when avatar rendering is enabled.

---

## 🔧 VRM Troubleshooting

If an avatar does not appear:

1. Confirm `web/public/Chidvi.vrm` or `web/public/Hinata.vrm` exists.
2. Start the Vite renderer with `npm run dev` inside `web/`.
3. Open the local renderer directly and check the browser console.
4. Verify the VRM file is a valid VRM/GLB asset.
5. Use only the bundled avatar names when testing:

```text
?avatar=Chidvi.vrm
?avatar=Hinata.vrm
```

The renderer intentionally avoids calling `VRMUtils.rotateVRM0()` on modern VRM 1.0 models because that conversion is intended for legacy VRM 0.x assets.

---

## 🔐 Safety & Permissions

CHIDVI can interact with the local computer, so automation should be treated as a privileged capability.

Recommended practice:

- Keep API keys private.
- Review automation commands before using them for destructive actions.
- Grant only the permissions required by each feature.
- Do not run untrusted tools or scripts with elevated privileges.
- Keep personal files and authentication data outside the repository.

---

## 🧪 Development Status

CHIDVI-555 is a large prototype that contains both working components and experimental architecture. Empty or placeholder modules may exist for future systems; they are intentionally separated from the active runtime rather than being treated as completed features.

The practical focus of this version is:

**Voice → Reasoning → Tools → Computer Interaction → Memory → Avatar/UI**

---

## 🛣️ Direction

The project is evolving toward a more modular assistant architecture with:

- Better agent planning
- Stronger memory retrieval
- More reliable tool execution
- Computer vision
- Improved voice interaction
- Robust avatar state synchronization
- Multi-agent experimentation
- Safer permission handling

---

## 📜 License

No explicit open-source license is currently declared in this repository. Treat the project as **all rights reserved** unless a license is added by the project owner.

---

<div align="center">

**CHIDVI-555 — Listen. Understand. Act. Remember.** ⚡

</div>
