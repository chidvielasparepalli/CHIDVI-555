# CHIDVI 555 Architectural Audit Report

Generated from the current worktree. This report treats the current files as the source of truth, including the uncommitted refactor work already present in `main.py`, `commands/router.py`, `api/key_pool.py`, `ui.py`, `web/src/main.js`, and related compatibility wrappers.

## Executive Summary

CHIDVI 555 currently has a working real-time runtime centered in `main.py` and `ui.py`, plus several partially built architecture folders (`core`, `ai`, `voice`, `ui_core`, `avatar`, `avatars`). The intended production architecture exists in outline, but many modules are empty placeholders while critical runtime responsibilities remain concentrated in large files.

The highest-risk areas are:

- Gemini Live session lifecycle, audio streaming, tool routing, command routing, and emotion state are all still coupled inside `main.py`.
- UI state, command-box behavior, setup/config handling, media playback, and the VRM web view are coupled inside `ui.py`.
- API key access is duplicated across many tools and automation modules, bypassing the new key pool.
- Emotion/avatar logic is split between `core/emotion_engine.py`, `personality/emotion_engine.py`, `avatar/animation_engine.py`, and `avatars/*`.
- Voice pipeline modules exist but are mostly empty; the real microphone/playback path is still in `main.py`.
- There are no meaningful tests in `tests/`; the current test files are empty.

No direct Python import cycles were found by AST import graph analysis, but there are many duplicated responsibilities and unused placeholder modules.

## Current Working Tree Note

The worktree already contains uncommitted changes from the first refactor pass:

- `commands/router.py`: canonical command router with structured local command parsing started.
- `core/speech/command_router.py`: compatibility wrapper.
- `personality/personality_loader.py`: compatibility wrapper around `core.personality_manager`.
- `api/key_pool.py` and `core/config.py`: multi-key configuration and rotation support started.
- `main.py`: typed input now routes through the canonical router and no longer double-sends typed text.
- `ui.py` and `web/src/main.js`: UI state starts driving the VRM web avatar.
- `core/speech/whisper_engine.py` and `core/speech/local_recognizer.py`: lazy Faster Whisper wrapper started.

These changes should be split into small logical commits before further broad refactoring.

## Repository Inventory

Python file count: 140.

Major runtime folders:

- `main.py`: live runtime, Gemini session, audio pipeline, tool execution, command dispatch, emotion hooks.
- `ui.py`: PyQt UI, setup overlay, command box, logging, media, mute state, VRM web view.
- `commands/router.py`: canonical local/remote command parser.
- `core/personality_manager.py`: intended personality source of truth.
- `api/key_pool.py`: intended Gemini API key pool.
- `web/src/main.js`: Three.js/VRM avatar renderer.
- `avatar/animation_engine.py`: richer but mostly disconnected avatar animation controller.
- `avatars/*`: simpler state/event facade used by `main.py`.

Mostly empty placeholder folders:

- `ai/*`
- `voice/*`
- `ui_core/main_window.py`, `ui_core/avatar.py`, `ui_core/widgets/*`
- `core/state_manager.py`, `core/conversation_manager.py`, `core/event_manager.py`, `core/language_manager.py`
- several `memory`, `vision`, `security`, `agent`, and `HINATA/Health` files

## Duplicate Code and Responsibilities

### API Key Loading

Duplicate `_get_api_key` implementations exist in:

- `main.py`
- `actions/code_helper.py`
- `actions/computer_settings.py`
- `actions/desktop.py`
- `actions/dev_agent.py`
- `actions/file_processor.py`
- `actions/flight_finder.py`
- `actions/web_search.py`
- `actions/youtube_video.py`
- `automation/error_handler.py`
- `automation/executor.py`
- `automation/planner.py`
- plus direct `gemini_api_key` reads in `actions/computer_control.py`, `actions/screen_processor.py`, `memory/config_manager.py`, and `ui.py`

Impact: tools can still hit rate limits independently and expose failures even if `main.py` rotates keys correctly.

### Base Directory Helpers

Duplicate `_base_dir`, `_get_base_dir`, and `get_base_dir` helpers exist across `ui.py`, actions, automation, memory, `core/config.py`, and `core/logging.py`.

Impact: frozen-app behavior and config/media paths can diverge.

### Emotion Engines

Two emotion systems exist:

- `core/emotion_engine.py`: generic emotions such as `CALM`, `FOCUSED`, `CARING`.
- `personality/emotion_engine.py`: Hinata-style emotions such as `BLUSH`, `JEALOUS`, `SHY`.

Impact: emotion is not actually independent from personality; prompt state and avatar state can diverge.

### Avatar Animation Systems

Two avatar systems exist:

- `avatar/animation_engine.py`: rich profile-based state/emotion/lip-sync architecture, but mostly disconnected.
- `avatars/*`: simple state facade used by `main.py`.

Impact: improvements in one avatar system do not automatically affect the live VRM renderer.

### UI Systems

`ui.py` is the real UI. `ui_core/*` mostly contains empty or unused placeholders plus themes.

Impact: new UI work can accidentally target unused files and not affect the app.

## Broken or Weak State Management

### Personality State

Current direction is correct: `core/personality_manager.py` should be the source of truth, and the old `personality/personality_loader.py` is now a wrapper.

Remaining risks:

- `main.py` still owns restart timing through `_restart_requested`.
- `ui.switch_theme(target)` is called from the local command handler before/alongside `switch_personality(target)`, so UI update and personality manager events are not fully transactional.
- Active personality is not persisted to disk, so restart always defaults to CHIDVI.
- Voice/avatar/theme/prompt update is not coordinated by a single transaction object.

### Runtime Session State

`core/session_manager.py` exists, but `main.py` still directly owns the real Gemini Live session, queues, task group, reconnect loop, and API key selection.

Remaining risks:

- No explicit task registry outside the `TaskGroup`.
- Session restart is implemented by raising `ConnectionResetError("SESSION_RESTART")`.
- Rate-limit handling rotates keys in the outer loop, but tool modules still bypass it.
- There is no integration test proving exactly one active session after personality switches.

### UI State

Mute state lives in `ui.py`; `main.py` reads `ui.muted`.

Remaining risks:

- UI state is not represented in a shared state manager.
- Command box creates a new thread for every send.
- File upload auto-message also invokes `on_text_command` on a thread, sharing the same callback path but without backpressure.

## Race Conditions and Concurrency Risks

No direct race was proven by runtime testing, but these are high-risk patterns:

- `ui.py` starts daemon threads for command sends while `main.py` schedules async work on the event loop.
- `main.py` audio callback writes to `out_queue` from a sounddevice callback thread.
- `main.py` uses `_restart_requested` as a shared boolean read by the async loop and written by command handlers.
- `JarvisLive.session` is read by typed-command forwarding while the reconnect loop can replace/clear it.
- `api/key_pool.py` publishes events while holding the key-pool lock and calls `get_next_key()` inside `mark_rate_limit()`, which is safe only because the lock is re-entrant but can produce side effects during event construction.
- Tool execution uses background threads for some actions (`screen_process`, shutdown) and executor threads for others.

## Circular Imports

AST import graph analysis found zero direct internal Python import cycles in the current repository.

This is good, but the absence of import cycles does not mean responsibilities are clean. Most coupling is runtime/service coupling inside `main.py` and duplicated global singletons.

## Personality System Issues

Fixed or improved in current uncommitted work:

- Typed `switch to hinata` is routed locally before Gemini.
- Legacy personality loader now wraps `core.personality_manager`.
- Typed input no longer appears to double-send to Gemini.

Remaining issues:

- Voice audio still streams to Gemini Live first; local command interception only sees Gemini input transcription after the model/session has already received audio.
- Faster Whisper is present as a lazy wrapper, but it is not yet integrated into the microphone stream.
- Personality switch is not yet a single atomic operation spanning session stop, prompt, voice, avatar, theme, emotion reset, and reconnect.
- Active personality is not persisted across app restarts.
- Future personality discovery is hardcoded to CHIDVI/HINATA.

## Command Routing Issues

Current direction:

- `commands/router.py` is the correct canonical router.
- `core/speech/command_router.py` is now a compatibility wrapper.

Remaining issues:

- Local command handlers are registered inside `JarvisLive`, not in a dedicated command service.
- Router has parser tests missing.
- Voice path is not fully pre-Gemini because the microphone stream still goes directly to Gemini Live.
- Commands like OS-level mute/unmute in `actions/computer_settings.py` are separate from assistant microphone mute/unmute.

## Audio Pipeline Issues

Current real path:

`sounddevice.InputStream` in `main.py` -> `out_queue` -> `session.send_realtime_input()` -> Gemini Live -> `session.receive()` -> `audio_in_queue` -> `sounddevice.RawOutputStream`.

Issues:

- `voice/audio_manager.py`, `voice/stt_engine.py`, `voice/tts_engine.py`, and `voice/voice_manager.py` are empty.
- Faster Whisper is not inserted before Gemini for local commands.
- Playback device is hardcoded as `device=3`.
- No central audio state machine prevents overlapping audio beyond `_is_speaking`.
- No audio tests.
- No proof that duplicate callbacks/tasks cannot happen after reconnect.

## Gemini Live Session Issues

Current direction:

- Outer loop reconnects on errors.
- Rate-limit-like errors mark the current key as rate-limited and reconnect quickly.

Remaining issues:

- Real session lifecycle is not using `core/session_manager.py`.
- Tool modules can make independent Gemini requests with direct keys.
- No retry of the interrupted user turn after key rotation.
- No structured cancellation/cleanup report after session close.
- No end-to-end test proving one active session and no orphan tasks.

## API Key Rotation Issues

Current direction:

- `api/key_pool.py` supports multiple keys.
- `core/config.py` supports `keys`, `gemini_keys`, and legacy `gemini_api_key`.

Remaining issues:

- Many action/automation modules bypass the key pool.
- `config/api_keys.json` is still partly legacy (`gemini_api_key`) for UI compatibility.
- UI setup writes only `gemini_api_key`, not `keys`.
- No standardized helper for all Gemini clients.

## VRM and Avatar Issues

Current direction:

- `web/src/main.js` loads `Chidvi.vrm` or `Hinata.vrm` from URL query.
- `ui.switch_theme()` reloads the web view with the target avatar.
- UI state now calls `window.setAvatarState(...)`.

Remaining issues:

- Reloading the web view is a coarse avatar switch, not an in-page unload/load with verified cleanup.
- `avatar/animation_engine.py` is not connected to the Three.js renderer.
- `avatars/*` state facade is not enough for full VRM expression manager control.
- Lip sync is synthetic state-based mouth motion, not audio-amplitude driven.
- No Playwright or browser screenshot verification.

## UI Synchronization Issues

Current direction:

- Theme switch and avatar reload are in `ui.switch_theme()`.
- Prompt/voice read from `core.personality_manager` when building Gemini config.

Remaining issues:

- Theme/avatar changes can occur before Gemini session has fully restarted.
- No single "personality transition complete" state.
- UI command log and Gemini input transcription can both log the same spoken command depending on path.
- The setup overlay and config writer are not aligned with multi-key config.

## Implementation Plan: Small Runnable Commits

Each commit should pass at least:

- `python -m py_compile` for touched Python files.
- `python -m unittest discover -s tests` once tests exist.
- `npm.cmd run build` when web files change.
- `git diff --check`.

### Commit 1: Audit and Regression Harness

Purpose: lock down current expected behavior before deeper refactor.

Changes:

- Add `ARCHITECTURAL_AUDIT_REPORT.md`.
- Add stdlib `unittest` tests for command parsing, personality source of truth, API key pool rotation, and config key formats.
- Keep runtime behavior unchanged.

Why: future commits need a safety rail, and `pytest` is not installed.

### Commit 2: Command Router Hardening

Purpose: make local command routing deterministic for text and future speech input.

Changes:

- Finalize structured command args (`personality`, `action`).
- Add parser coverage for polite suffixes, punctuation, and non-command mentions of personality names.
- Keep `core/speech/command_router.py` as compatibility wrapper.

Why: Gemini must never receive local commands, and normal conversation mentioning a personality must not trigger a switch.

### Commit 3: API Key Access Consolidation

Purpose: route all Gemini key reads through a shared API service.

Changes:

- Add a small helper module around `api.key_pool`.
- Migrate action/automation `_get_api_key()` implementations to the helper.
- Update UI setup to write both legacy `gemini_api_key` and `keys`.

Why: key rotation cannot be reliable while tools bypass the pool.

### Commit 4: Personality Transition Service

Purpose: make personality switching an atomic runtime operation.

Changes:

- Add transition object/service for prompt, voice, avatar model, theme, emotion reset, and session restart.
- Move local personality handler out of `main.py` into a dedicated service.
- Persist active personality in config/state.

Why: UI, voice, prompt, and avatar must not diverge.

### Commit 5: Gemini Session Lifecycle Extraction

Purpose: move real Live API lifecycle into `core/session_manager.py` or a new `core/live` module.

Changes:

- Extract session creation, reconnect, key rotation, and task cleanup from `main.py`.
- Replace `_restart_requested` boolean with an async event/command queue.
- Add tests with fake session creator for restart and rate-limit rotation.

Why: one active Live session and clean cancellation are core production requirements.

### Commit 6: Audio Pipeline Service

Purpose: make the mic/transcription/playback path single and testable.

Changes:

- Move `InputStream`, `send_realtime_input`, receive, and playback queues into `core/audio` or `core/speech`.
- Replace hardcoded output device with config/default selection.
- Add queue/task lifecycle tests with fakes.

Why: duplicate callbacks, overlapping audio, and reconnect leaks must be prevented at the architecture level.

### Commit 7: Faster Whisper Pre-Router Integration

Purpose: detect local voice commands before Gemini receives them.

Changes:

- Add local audio chunk buffering/VAD path for command-sized utterances.
- Run Faster Whisper local recognizer for wake/personality/local commands.
- Gate Gemini forwarding when a local command is detected.

Why: the requirement explicitly says local commands should be intercepted before Gemini.

### Commit 8: Unified Emotion Engine

Purpose: make emotion independent from personality while allowing personality-specific reactions.

Changes:

- Merge `core/emotion_engine.py` and `personality/emotion_engine.py` into one engine.
- Support required emotions: idle, happy, excited, thinking, listening, speaking, angry, sad, embarrassed, blushing, jealous, laughing, confused, surprised, sleepy.
- Publish avatar emotion events.

Why: current emotion state is split and cannot reliably control prompt and avatar together.

### Commit 9: VRM Runtime Bridge

Purpose: connect the Python avatar/emotion state to the actual Three.js VRM renderer.

Changes:

- Replace web-view reload switching with in-page VRM unload/load API.
- Send avatar state/emotion/lip-sync values via `runJavaScript` bridge.
- Ensure old VRM scenes are removed and disposed.

Why: avatar switching should not require full page reload and should not leak scene resources.

### Commit 10: UI Synchronization and Setup Config

Purpose: align UI state with runtime state.

Changes:

- Add UI subscriptions to personality/session/audio/emotion events.
- Ensure command box, voice transcript, and file-upload sends all go through one ingress.
- Update API key setup for multi-key config.

Why: UI changes must reflect actual runtime state, not a parallel guess.

### Commit 11: Runtime Verification Pass

Purpose: prove the critical flows.

Checks:

- Typed conversation works.
- Typed personality switch works.
- Voice/local command switch works using Faster Whisper path.
- Gemini reconnects once per switch.
- API key rotation works with fake 429/resource-exhausted errors.
- UI theme/avatar/prompt/voice stay synchronized.
- VRM state changes without full process restart.

Why: the task is only complete after verified behavior, not after code movement.

## Immediate Next Step

The next action should be Commit 1: add regression tests and commit the audit/report plus tests. After that, split the existing uncommitted implementation changes into the smallest runnable commits instead of bundling everything into one large refactor commit.
