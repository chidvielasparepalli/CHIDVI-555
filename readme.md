🤖 C.H.I.D.V.I.E.L.A.S (CHIDVI 555)
The Next-Generation Cross-Platform Personal AI Assistant

Designed & Developed by Chidvielas Parepalli

An intelligent desktop AI assistant capable of hearing, speaking, remembering, seeing, understanding, and controlling your computer in real time. Built with Google Gemini Live, advanced desktop automation, long-term memory, tool execution, and multiple AI personalities.

✨ Overview

CHIDVI 555 is the latest evolution of the JARVIS project, transforming traditional AI assistants into a complete desktop operating companion.

Rather than simply answering questions, CHIDVI understands natural conversations, performs computer automation, executes intelligent workflows, analyzes files, remembers user preferences, and adapts its behavior through multiple personalities.

The goal is to provide a seamless Human-AI interaction experience where voice, vision, automation, memory, and intelligence work together.

🚀 Core Capabilities
Feature	Description
🎙️ Real-Time Voice Conversation	Ultra-low latency voice interaction powered by Gemini Live
🧠 Multiple AI Personalities	Instantly switch between CHIDVI and HINATA personalities
💾 Long-Term Memory	Remembers projects, preferences, conversations, and user context
🖥️ Desktop Automation	Open applications, control windows, execute system commands
🌐 Browser Automation	Google search, LinkedIn, YouTube, websites, form filling
📂 Intelligent File Processing	Analyze PDFs, Images, Code, Documents, CSV, JSON and more
👁️ Vision Support	Understand screenshots and uploaded images
⚡ AI Tool Calling	Executes Python tools automatically using Gemini Function Calling
💬 Hybrid Input	Voice + Keyboard commands simultaneously
🔊 Streaming Voice Output	Natural streaming AI speech with interruption support
🎨 Adaptive Modern UI	Responsive futuristic desktop interface
🧩 Multi-Step Task Planning	Breaks complex goals into executable tasks
🔄 Cross-Platform Support	Windows • Linux • macOS
🆕 Latest Features
🎭 Multiple AI Personalities

CHIDVI 555 now supports dynamic personality switching.

CHIDVI
Professional
Logical
Task-oriented
Technical assistant
Efficient responses

HINATA
Friendly
Caring
Emotional
Natural conversations
Human-like interactions

Users can switch personalities instantly during runtime without restarting the application.

🧠 Persistent Memory System

The assistant now remembers:

Previous conversations
User preferences
Ongoing projects
Frequently used tools
Personal workflow
Context between sessions

This enables personalized conversations over time.

🛠️ AI Tool Execution

The assistant can intelligently decide when to use tools.

Supported automation includes:

Browser Control
Application Launching
Website Navigation
Google Search
LinkedIn
YouTube
File Analysis
Weather
Flight Search
System Commands
File Management
Desktop Automation
📂 Advanced File Intelligence

Upload and analyze:

PDF
DOCX
TXT
Images
Source Code
CSV
JSON
Excel
Audio
Video

Capabilities include:

Summarization
OCR
Translation
Code Review
Bug Detection
Documentation
AI Explanation
🎤 Gemini Live Voice Engine

Built using Google's Gemini Live API.

Features include:

Streaming speech recognition
Streaming AI responses
Real-time interruption handling
Continuous conversations
Low-latency communication
🎨 Redesigned Desktop Interface

The latest interface introduces:

Modern futuristic dashboard
Live AI status indicators
Animated response logs
Dynamic themes
Responsive layouts
Video-based avatar support
Personality-specific themes
🤖 Intelligent Automation Engine

CHIDVI can:

Open software
Close applications
Search the web
Manage files
Execute terminal commands
Navigate websites
Perform repetitive workflows

without requiring manual interaction.

🔥 Performance Improvements
Faster Gemini response streaming
Improved asynchronous architecture
Better audio queue management
Reduced latency
More stable tool execution
Enhanced browser automation
Improved UI responsiveness
🏗️ Architecture
                User

         Voice / Keyboard

                │

        Speech Recognition

                │

         Gemini Live API

                │

      Intent & Tool Detection

                │

      ┌──────────────────────┐
      │                      │
      ▼                      ▼

 Desktop Automation     AI Conversation

      │                      │

 Browser            Memory System

 Applications       File Processing

 Vision             Tool Execution

      │

      ▼

 Animated UI + Voice Response
📋 Requirements
Requirement	Version
Python	3.11+
OS	Windows / Linux / macOS
Microphone	Required
Internet	Required for Gemini
Gemini API Key	Required
⚡ Installation
git clone https://github.com/chidvielasparepalli/CHIDVI-555.git

cd CHIDVI-555

python -m venv .venv

source .venv/bin/activate
# Windows
.venv\Scripts\activate

pip install -r requirements.txt

playwright install

python main.py
🛣️ Roadmap

Upcoming features planned for future releases:

🎥 Video-based animated AI avatars
😊 Emotion-aware avatar expressions
👄 Automatic lip synchronization
🧠 Local Whisper speech recognition
🧠 Offline LLM support
👀 Continuous screen understanding
📱 Android companion app
🏠 Smart Home integration
🔌 Plugin ecosystem
🌍 Multi-language personality packs
👨‍💻 About the Creator

CHIDVI 555 is an independent research and development project focused on building a true next-generation desktop AI assistant that combines conversational intelligence, automation, memory, vision, and adaptive personalities into a unified experience.

⭐ Support the Project

If you enjoy CHIDVI 555, consider:

⭐ Starring the repository
🍴 Forking the project
🐞 Reporting issues
💡 Suggesting new features
🤝 Contributing to development

Structure :

D:\PROJECTS\CHIDVI-555\
├── .env                          # Gemini API key
├── .gitignore
├── ARCHITECTURAL_AUDIT_REPORT.md
├── ARCHITECTURE.md               # Full architecture documentation
├── INTEGRATION_EXAMPLE.py
├── main.py                       # ★ MAIN ENTRY POINT
├── package-lock.json
├── PHASE_1_COMPLETE.md
├── PHASE_1_SUMMARY.py
├── QUICK_START.py
├── readme.md                     # Project README
├── README_REFACTOR.md
├── REFACTORING_CHECKLIST.py
├── requirements.txt              # Python dependencies (27 packages)
├── setup.py                      # Install script
├── ui.py                         # ★ PyQt6 Desktop UI (1400+ lines)
├── wake_listener.py              # Wake word listener + face auth
│
├── actions/                      # Tool/action modules (called by Gemini)
│   ├── browser_control.py        # Playwright browser automation
│   ├── code_helper.py            # Code writing/editing/running
│   ├── computer_control.py       # pyautogui direct control
│   ├── computer_settings.py      # Volume, brightness, window mgmt
│   ├── desktop.py                # Wallpaper, organize, clean
│   ├── dev_agent.py              # Multi-file project builder
│   ├── file_controller.py        # File/folder CRUD operations
│   ├── file_processor.py         # Multi-format file analysis
│   ├── flight_finder.py          # Google Flights search
│   ├── game_updater.py           # Steam/Epic game management
│   ├── open_app.py               # Application launcher
│   ├── reminder.py               # Windows Task Scheduler reminders
│   ├── screen_processor.py       # Screenshot/webcam + Gemini Vision
│   ├── send_message.py           # WhatsApp/Telegram messaging
│   ├── weather_report.py         # Weather lookup
│   ├── web_search.py             # DuckDuckGo web search
│   └── youtube_video.py          # YouTube play/summarize/trending
│
├── api/
│   └── key_pool.py               # Multi-key rotation + rate limit mgmt
│
├── assets/
│   ├── avatars/
│   │   ├── Chidvi.vrm            # VRM avatar model (CHIDVI personality)
│   │   └── Hinata.vrm            # VRM avatar model (HINATA personality)
│   └── automations/
│       ├── error_handler.py
│       ├── executor.py
│       ├── planner.py
│       ├── task_queue.py          # Priority task queue for agent tasks
│       ├── actions/               # FBX animations (Mixamo)
│       │   ├── Blow A Kiss.fbx, Blow A Kiss (1).fbx
│       │   ├── cheer.fbx, clap.fbx, jum.fbx, nod.fbx
│       │   ├── Salute.fbx, shaking Head No.fbx, shrug.fbx
│       │   ├── thinking.fbx, yelling.fbx
│       ├── emotions/
│       │   ├── angry.fbx, bashful.fbx, happy.fbx, laughing.fbx
│       ├── greetings/
│       │   ├── bow.fbx, wave.fbx, wave2.fbx
│       ├── idle/
│       │   ├── breathing Idle.fbx, idle.fbx, sad idle.fbx
│       └── talking/
│           ├── pointing.fbx, secret.fbx, talking1.fbx
│
├── avatars/                      # Python-side avatar management
│   ├── __init__.py
│   ├── animation_controller.py   # Maps emotions -> AvatarState
│   ├── avatar_events.py          # Event enum (IDLE, SPEAKING, etc.)
│   ├── avatar_logger.py
│   ├── avatar_manager.py         # State machine for avatar states
│   ├── avatar_service.py         # ★ Facade: unifies all avatar subsystems
│   ├── avatar_state.py           # AvatarState enum (18 states)
│   ├── expression_controller.py  # Emotion -> animation routing
│   └── test_avatar.py
│
├── CHIDVI/                       # (empty or reserved directory)
│
├── commands/
│   └── router.py                 # ★ Command Router (LOCAL vs REMOTE)
│
├── config/
│   ├── __init__.py
│   ├── api_keys.json             # Gemini API key pool
│   ├── personality_state.json    # Persisted active personality
│   └── settings.json
│
├── core/                         # ★ Core system modules
│   ├── audio/
│   │   ├── __init__.py
│   │   ├── diagnostics.py        # Thread-safe audio metrics
│   │   ├── microphone.py         # sounddevice input -> async queue
│   │   └── speaker.py            # Queue -> sounddevice output + boost
│   ├── speech/                   # (reserved)
│   ├── config.py                 # ★ Centralized ConfigManager singleton
│   ├── event_bus.py              # ★ Pub/sub event system (20+ event types)
│   ├── logging.py                # Structured logging
│   ├── personality_manager.py    # ★ SINGLE SOURCE OF TRUTH for personality
│   ├── prompt.txt                # System prompt template
│   ├── runtime.py                # ★ App bootstrap (Vite server, threads)
│   ├── session_manager.py        # Gemini session lifecycle
│   └── state_manager.py          # ★ Thread-safe AppState (RuntimeState)
│
├── logs/                         # Log output directory
│
├── media/
│   ├── background_song.mp3       # Startup wake music
│   ├── final work bgm.mp3        # Working background music
│   ├── interface_video.mp4       # Background HUD video
│   └── README.txt
│
├── memory/
│   ├── __init__.py
│   ├── long_term.json            # Persistent user memory store
│   └── memory_manager.py         # ★ CRUD + prompt formatting for memory
│
├── offline/
│   ├── __init__.py
│   ├── offline_chat.py
│   ├── offline_manager.py        # Online/offline mode tracking
│   ├── offline_status.py         # Network connectivity check
│   ├── test_chat.py
│   └── test_offline.py
│
├── personality/                  # ★ AI personality definitions
│   ├── __init__.py
│   ├── chidvi.py                 # CHIDVI system prompt (professional)
│   ├── emotion_engine.py         # Emotion state + prompt injection
│   ├── hinata.py                 # HINATA system prompt (affectionate/jealous)
│   └── personality_loader.py
│
├── security/
│   ├── face_auth.py              # Face recognition auth (face_recognition lib)
│   └── owner.jpg                 # Reference face image
│
├── tests/                        # Test suite
│   ├── test_actions.py
│   ├── test_audio_diagnostics.py
│   ├── test_audio_microphone.py
│   ├── test_audio_speaker.py
│   ├── test_memory.py
│   ├── test_personality.py
│   ├── test_runtime_bootstrap.py
│   ├── test_runtime_refactor.py
│   ├── test_state_manager.py
│   └── test_voice.py
│
├── ui_core/
│   ├── __init__.py
│   └── themes/
│       ├── __init__.py
│       ├── chidvi_theme.py       # Blue/cyan theme (#00D8FF)
│       ├── hinata_theme.py       # Pink/purple theme (#FF69B4)
│       └── theme_manager.py      # Theme switching singleton
│
├── voice/                        # (reserved for future voice modules)
│
└── web/                          # ★ Three.js VRM avatar renderer
    ├── .gitignore
    ├── index.html                # Vite entry HTML
    ├── package.json              # three + @pixiv/three-vrm
    ├── package-lock.json
    ├── public/
    │   ├── Chidvi.vrm            # Deployed VRM model
    │   ├── Hinata.vrm            # Deployed VRM model
    │   ├── favicon.svg
    │   ├── icons.svg
    │   ├── index.html
    │   ├── assets/               # Built assets
    │   │   ├── index-BYKbi2HN.js
    │   │   └── index-CsUDhMuy.css
    │   └── animations/           # 26 FBX animation files
    │       ├── idle.fbx, breathing_idle.fbx, sad_idle.fbx
    │       ├── wave.fbx, wave2.fbx, bow.fbx, clap.fbx
    │       ├── nod.fbx, shake_head.fbx, shrug.fbx, salute.fbx
    │       ├── jump.fbx, blow_kiss.fbx, blow_kiss2.fbx
    │       ├── happy.fbx, laughing.fbx, angry.fbx, bashful.fbx
    │       ├── cheer.fbx, yell.fbx, thinking.fbx
    │       ├── talking.fbx, talking2.fbx, secret.fbx, pointing.fbx
    ├── src/
    │   ├── main.js               # ★ Three.js VRM renderer (654 lines)
    │   ├── animation-manager.js  # ★ AnimationManager (893 lines)
    │   └── style.css
    ├── dist/                     # Built output
    └── node_modules/