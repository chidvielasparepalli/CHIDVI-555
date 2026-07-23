import os
from commands.router import (
    Command,
    CommandCategory,
    CommandType,
    get_command_router,
)
from avatars.avatar_service import avatar_service
from avatars.avatar_events import AvatarEvent
from ui_core.themes.theme_manager import theme_manager
from core.personality_manager import (
    get_active_profile,
    get_system_prompt,
    get_voice,
    get_personality,
    get_personality_manager,
    switch_personality,
)
from api.key_pool import (
    get_next_api_key,
    mark_api_key_failed,
    mark_api_key_rate_limited,
    mark_api_key_success,
)
from core.state_manager import RuntimeState, get_state_manager
from personality.emotion_engine import EmotionEngine, Emotion
from core.proactive_conversation import init_conversation_manager, get_conversation_manager

os.environ["QT_LOGGING_RULES"] = "*.debug=false"
import asyncio
import re
from dotenv import load_dotenv
import os

load_dotenv()
import threading
import sys
import traceback
import time
from pathlib import Path
from google import genai
from google.genai import types
from ui import JarvisUI
from memory.memory_manager import (
    load_memory, update_memory, format_memory_for_prompt,
)

from actions.file_processor import file_processor
from actions.flight_finder     import flight_finder
from actions.open_app          import open_app
from actions.weather_report    import weather_action
from actions.send_message      import send_message
from actions.reminder          import reminder
from actions.computer_settings import computer_settings
from actions.screen_processor  import screen_process
from actions.youtube_video     import youtube_video
from actions.desktop           import desktop_control
from actions.browser_control   import browser_control
from actions.file_controller   import file_controller
from actions.code_helper       import code_helper
from actions.dev_agent         import dev_agent
from actions.web_search        import web_search as web_search_action
from actions.computer_control  import computer_control
from actions.game_updater      import game_updater
from plugins.smart_scan       import smart_scan
from plugins.screen_recorder  import screen_record
from plugins.ai_presenter     import ai_present
from plugins.health_plugins   import (
    health_water_reminder,
    health_screen_time,
    health_eye_care,
    health_exercise_coach,
    health_posture,
    health_sleep,
    health_hub,
    health_auto_start,
)
from plugins.voice_plugins    import (
    voice_notes,
    meeting_recorder,
    live_translator,
    accent_trainer,
    pronunciation_coach,
    voice_cloning,
)
from plugins.security_plugins import (
    face_unlock,
    voice_auth,
    unknown_person_alert,
    webcam_monitor,
    usb_monitor,
)
from core.runtime import ensure_renderer_server, run_desktop_app
from core.audio.microphone import Microphone
from core.audio.speaker import Speaker
from core.audio.diagnostics import AudioDiagnostics
from core.proactive_conversation import init_conversation_manager, get_conversation_manager

def get_base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent

BASE_DIR        = get_base_dir()
LIVE_MODEL          = "models/gemini-2.5-flash-native-audio-preview-12-2025"
FALLBACK_MODELS     = [
    "models/gemini-2.5-flash-native-audio-preview-12-2025",
    "models/gemini-2.0-flash-live-001",
    "models/gemini-2.5-flash-preview-05-20",
]
SEND_SAMPLE_RATE    = 16000
RECEIVE_SAMPLE_RATE = 24000
CHUNK_SIZE          = 1024

def _get_api_key() -> str:
    api_key = get_next_api_key() or os.getenv("GEMINI_API_KEY")

    if not api_key:
        raise ValueError("No Gemini API key found in config/api_keys.json or .env")

    return api_key

def _is_rate_limit_error(error: Exception | str) -> bool:
    text = str(error).lower()
    return any(
        token in text
        for token in (
            "429",
            "quota",
            "rate limit",
            "rate_limit",
            "resource exhausted",
            "unavailable",
            "api unavailable",
        )
    )

def _is_model_error(error: Exception | str) -> bool:
    text = str(error).lower()
    return any(
        token in text
        for token in (
            "1007",
            "content_type_audio is not supported",
            "model not found",
            "invalid model",
            "not found",
            "not supported",
        )
    )

def _is_network_error(error: Exception | str) -> bool:
    text = str(error).lower()
    return any(
        token in text
        for token in (
            "timed out",
            "timeout",
            "connection refused",
            "connection reset",
            "connection aborted",
            "network is unreachable",
            "name resolution",
            "errno",
        )
    )


_CTRL_RE = re.compile(r"<ctrl\d+>", re.IGNORECASE)

def _clean_transcript(text: str) -> str:    
    text = _CTRL_RE.sub("", text)
    text = re.sub(r"[\x00-\x08\x0b-\x1f]", "", text)
    return text.strip()

TOOL_DECLARATIONS = [
    {
        "name": "open_app",
        "description": (
            "Opens any application on the computer. "
            "Use this whenever the user asks to open, launch, or start any app, "
            "website, or program. Always call this tool â€” never just say you opened it."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "app_name": {
                    "type": "STRING",
                    "description": "Exact name of the application (e.g. 'WhatsApp', 'Chrome', 'Spotify')"
                }
            },
            "required": ["app_name"]
        }
    },
    {
        "name": "web_search",
        "description": "Searches the web for any information.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query":  {"type": "STRING", "description": "Search query"},
                "mode":   {"type": "STRING", "description": "search (default) or compare"},
                "items":  {"type": "ARRAY", "items": {"type": "STRING"}, "description": "Items to compare"},
                "aspect": {"type": "STRING", "description": "price | specs | reviews"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "weather_report",
        "description": "Gives the weather report to user",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "city": {"type": "STRING", "description": "City name"}
            },
            "required": ["city"]
        }
    },
    {
        "name": "send_message",
        "description": "Sends a text message via WhatsApp, Telegram, or other messaging platform.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "receiver":     {"type": "STRING", "description": "Recipient contact name"},
                "message_text": {"type": "STRING", "description": "The message to send"},
                "platform":     {"type": "STRING", "description": "Platform: WhatsApp, Telegram, etc."}
            },
            "required": ["receiver", "message_text", "platform"]
        }
    },
    {
        "name": "reminder",
        "description": "Sets a timed reminder using Task Scheduler.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "date":    {"type": "STRING", "description": "Date in YYYY-MM-DD format"},
                "time":    {"type": "STRING", "description": "Time in HH:MM format (24h)"},
                "message": {"type": "STRING", "description": "Reminder message text"}
            },
            "required": ["date", "time", "message"]
        }
    },
    {
        "name": "youtube_video",
        "description": (
            "Controls YouTube. Use for: playing videos, summarizing a video's content, "
            "getting video info, or showing trending videos."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "play | summarize | get_info | trending (default: play)"},
                "query":  {"type": "STRING", "description": "Search query for play action"},
                "save":   {"type": "BOOLEAN", "description": "Save summary to Notepad (summarize only)"},
                "region": {"type": "STRING", "description": "Country code for trending e.g. TR, US"},
                "url":    {"type": "STRING", "description": "Video URL for get_info action"},
            },
            "required": []
        }
    },
    {
        "name": "screen_process",
        "description": (
            "Captures and analyzes the screen or webcam image. "
            "MUST be called when user asks what is on screen, what you see, "
            "analyze my screen, look at camera, etc. "
            "You have NO visual ability without this tool. "
            "After calling this tool, stay SILENT â€” the vision module speaks directly."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "angle": {"type": "STRING", "description": "'screen' to capture display, 'camera' for webcam. Default: 'screen'"},
                "text":  {"type": "STRING", "description": "The question or instruction about the captured image"}
            },
            "required": ["text"]
        }
    },
    {
        "name": "computer_settings",
        "description": (
            "Controls the computer: volume, brightness, window management, keyboard shortcuts, "
            "typing text on screen, closing apps, fullscreen, dark mode, WiFi, restart, shutdown, "
            "scrolling, tab management, zoom, screenshots, lock screen, refresh/reload page. "
            "Use for ANY single computer control command. NEVER route to agent_task."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "The action to perform"},
                "description": {"type": "STRING", "description": "Natural language description of what to do"},
                "value":       {"type": "STRING", "description": "Optional value: volume level, text to type, etc."}
            },
            "required": []
        }
    },
    {
        "name": "browser_control",
        "description": (
            "Controls any web browser. Use for: opening websites, searching the web, "
            "clicking elements, filling forms, scrolling, screenshots, navigation, any web-based task. "
            "Always pass the 'browser' parameter when the user specifies a browser (e.g. 'open in Edge', "
            "'use Firefox', 'open Chrome'). Multiple browsers can run simultaneously."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "go_to | search | click | type | scroll | fill_form | smart_click | smart_type | get_text | get_url | press | new_tab | close_tab | screenshot | back | forward | reload | switch | list_browsers | close | close_all"},
                "browser":     {"type": "STRING", "description": "Target browser: chrome | edge | firefox | opera | operagx | brave | vivaldi | safari. Omit to use the currently active browser."},
                "url":         {"type": "STRING", "description": "URL for go_to / new_tab action"},
                "query":       {"type": "STRING", "description": "Search query for search action"},
                "engine":      {"type": "STRING", "description": "Search engine: google | bing | duckduckgo | yandex (default: google)"},
                "selector":    {"type": "STRING", "description": "CSS selector for click/type"},
                "text":        {"type": "STRING", "description": "Text to click or type"},
                "description": {"type": "STRING", "description": "Element description for smart_click/smart_type"},
                "direction":   {"type": "STRING", "description": "up | down for scroll"},
                "amount":      {"type": "INTEGER", "description": "Scroll amount in pixels (default: 500)"},
                "key":         {"type": "STRING", "description": "Key name for press action (e.g. Enter, Escape, F5)"},
                "path":        {"type": "STRING", "description": "Save path for screenshot"},
                "incognito":   {"type": "BOOLEAN", "description": "Open in private/incognito mode"},
                "clear_first": {"type": "BOOLEAN", "description": "Clear field before typing (default: true)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "file_controller",
        "description": "Manages files and folders: list, create, delete, move, copy, rename, read, write, find, disk usage.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "list | create_file | create_folder | delete | move | copy | rename | read | write | find | largest | disk_usage | organize_desktop | info"},
                "path":        {"type": "STRING", "description": "File/folder path or shortcut: desktop, downloads, documents, home"},
                "destination": {"type": "STRING", "description": "Destination path for move/copy"},
                "new_name":    {"type": "STRING", "description": "New name for rename"},
                "content":     {"type": "STRING", "description": "Content for create_file/write"},
                "name":        {"type": "STRING", "description": "File name to search for"},
                "extension":   {"type": "STRING", "description": "File extension to search (e.g. .pdf)"},
                "count":       {"type": "INTEGER", "description": "Number of results for largest"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "desktop_control",
        "description": "Controls the desktop: wallpaper, organize, clean, list, stats.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "wallpaper | wallpaper_url | organize | clean | list | stats | task"},
                "path":   {"type": "STRING", "description": "Image path for wallpaper"},
                "url":    {"type": "STRING", "description": "Image URL for wallpaper_url"},
                "mode":   {"type": "STRING", "description": "by_type or by_date for organize"},
                "task":   {"type": "STRING", "description": "Natural language desktop task"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "code_helper",
        "description": "Writes, edits, explains, runs, or builds code files.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "write | edit | explain | run | build | auto (default: auto)"},
                "description": {"type": "STRING", "description": "What the code should do or what change to make"},
                "language":    {"type": "STRING", "description": "Programming language (default: python)"},
                "output_path": {"type": "STRING", "description": "Where to save the file"},
                "file_path":   {"type": "STRING", "description": "Path to existing file for edit/explain/run/build"},
                "code":        {"type": "STRING", "description": "Raw code string for explain"},
                "args":        {"type": "STRING", "description": "CLI arguments for run/build"},
                "timeout":     {"type": "INTEGER", "description": "Execution timeout in seconds (default: 30)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "dev_agent",
        "description": "Builds complete multi-file projects from scratch: plans, writes files, installs deps, opens VSCode, runs and fixes errors.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "description":  {"type": "STRING", "description": "What the project should do"},
                "language":     {"type": "STRING", "description": "Programming language (default: python)"},
                "project_name": {"type": "STRING", "description": "Optional project folder name"},
                "timeout":      {"type": "INTEGER", "description": "Run timeout in seconds (default: 30)"},
            },
            "required": ["description"]
        }
    },
    {
        "name": "agent_task",
        "description": (
            "Executes complex multi-step tasks requiring multiple different tools. "
            "Examples: 'research X and save to file', 'find and organize files'. "
            "DO NOT use for single commands. NEVER use for Steam/Epic â€” use game_updater."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "goal":     {"type": "STRING", "description": "Complete description of what to accomplish"},
                "priority": {"type": "STRING", "description": "low | normal | high (default: normal)"}
            },
            "required": ["goal"]
        }
    },
    {
        "name": "computer_control",
        "description": "Direct computer control: type, click, hotkeys, scroll, move mouse, screenshots, find elements on screen.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "type | smart_type | click | double_click | right_click | hotkey | press | scroll | move | copy | paste | screenshot | wait | clear_field | focus_window | screen_find | screen_click | random_data | user_data"},
                "text":        {"type": "STRING", "description": "Text to type or paste"},
                "x":           {"type": "INTEGER", "description": "X coordinate"},
                "y":           {"type": "INTEGER", "description": "Y coordinate"},
                "keys":        {"type": "STRING", "description": "Key combination e.g. 'ctrl+c'"},
                "key":         {"type": "STRING", "description": "Single key e.g. 'enter'"},
                "direction":   {"type": "STRING", "description": "up | down | left | right"},
                "amount":      {"type": "INTEGER", "description": "Scroll amount (default: 3)"},
                "seconds":     {"type": "NUMBER",  "description": "Seconds to wait"},
                "title":       {"type": "STRING",  "description": "Window title for focus_window"},
                "description": {"type": "STRING",  "description": "Element description for screen_find/screen_click"},
                "type":        {"type": "STRING",  "description": "Data type for random_data"},
                "field":       {"type": "STRING",  "description": "Field for user_data: name|email|city"},
                "clear_first": {"type": "BOOLEAN", "description": "Clear field before typing (default: true)"},
                "path":        {"type": "STRING",  "description": "Save path for screenshot"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "game_updater",
        "description": (
            "THE ONLY tool for ANY Steam or Epic Games request. "
            "Use for: installing, downloading, updating games, listing installed games, "
            "checking download status, scheduling updates. "
            "ALWAYS call directly for any Steam/Epic/game request. "
            "NEVER use agent_task, browser_control, or web_search for Steam/Epic."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":    {"type": "STRING",  "description": "update | install | list | download_status | schedule | cancel_schedule | schedule_status (default: update)"},
                "platform":  {"type": "STRING",  "description": "steam | epic | both (default: both)"},
                "game_name": {"type": "STRING",  "description": "Game name (partial match supported)"},
                "app_id":    {"type": "STRING",  "description": "Steam AppID for install (optional)"},
                "hour":      {"type": "INTEGER", "description": "Hour for scheduled update 0-23 (default: 3)"},
                "minute":    {"type": "INTEGER", "description": "Minute for scheduled update 0-59 (default: 0)"},
                "shutdown_when_done": {"type": "BOOLEAN", "description": "Shut down PC when download finishes"},
            },
            "required": []
        }
    },
    {
        "name": "flight_finder",
        "description": "Searches Google Flights and speaks the best options.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "origin":      {"type": "STRING",  "description": "Departure city or airport code"},
                "destination": {"type": "STRING",  "description": "Arrival city or airport code"},
                "date":        {"type": "STRING",  "description": "Departure date (any format)"},
                "return_date": {"type": "STRING",  "description": "Return date for round trips"},
                "passengers":  {"type": "INTEGER", "description": "Number of passengers (default: 1)"},
                "cabin":       {"type": "STRING",  "description": "economy | premium | business | first"},
                "save":        {"type": "BOOLEAN", "description": "Save results to Notepad"},
            },
            "required": ["origin", "destination", "date"]
        }
    },
    {
        "name": "shutdown_jarvis",
        "description": (
            "Shuts down the assistant completely. "
            "Call this when the user expresses intent to end the conversation, "
            "close the assistant, say goodbye, or stop Jarvis. "
            "The user can say this in ANY language."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {},
        }
    },
    {
    "name": "file_processor",
    "description": (
        "Processes any file that the user has uploaded or dropped onto the interface. "
        "Use this when the user refers to an uploaded file and wants an action on it. "
        "Supports: images (describe/ocr/resize/compress/convert), "
        "PDFs (summarize/extract_text/to_word), "
        "Word docs & text files (summarize/fix/reformat/translate), "
        "CSV/Excel (analyze/stats/filter/sort/convert), "
        "JSON/XML (validate/format/analyze), "
        "code files (explain/review/fix/optimize/run/document/test), "
        "audio (transcribe/trim/convert/info), "
        "video (trim/extract_audio/extract_frame/compress/transcribe/info), "
        "archives (list/extract), "
        "presentations (summarize/extract_text). "
        "ALWAYS call this tool when a file has been uploaded and the user gives a command about it. "
        "If the user's command is ambiguous, pick the most logical action for that file type."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "file_path": {
                "type": "STRING",
                "description": "Full path to the uploaded file. Leave empty to use the currently uploaded file."
            },
            "action": {
                "type": "STRING",
                "description": (
                    "What to do with the file. Examples by type:\n"
                    "image: describe | ocr | resize | compress | convert | info\n"
                    "pdf: summarize | extract_text | to_word | info\n"
                    "docx/txt: summarize | fix | reformat | translate_hint | word_count | to_bullet\n"
                    "csv/excel: analyze | stats | filter | sort | convert | info\n"
                    "json: validate | format | analyze | to_csv\n"
                    "code: explain | review | fix | optimize | run | document | test\n"
                    "audio: transcribe | trim | convert | info\n"
                    "video: trim | extract_audio | extract_frame | compress | transcribe | info | convert\n"
                    "archive: list | extract\n"
                    "pptx: summarize | extract_text | analyze"
                )
            },
            "instruction": {
                "type": "STRING",
                "description": "Free-form instruction if action doesn't cover it. E.g. 'translate this to Turkish', 'find all email addresses'"
            },
            "format": {
                "type": "STRING",
                "description": "Target format for conversion. E.g. 'mp3', 'pdf', 'csv', 'png'"
            },
            "width":     {"type": "INTEGER", "description": "Target width for image resize"},
            "height":    {"type": "INTEGER", "description": "Target height for image resize"},
            "scale":     {"type": "NUMBER",  "description": "Scale factor for image resize (e.g. 0.5)"},
            "quality":   {"type": "INTEGER", "description": "Quality 1-100 for image/video compress"},
            "start":     {"type": "STRING",  "description": "Start time for trim: seconds or HH:MM:SS"},
            "end":       {"type": "STRING",  "description": "End time for trim: seconds or HH:MM:SS"},
            "timestamp": {"type": "STRING",  "description": "Timestamp for video frame extraction HH:MM:SS"},
            "column":    {"type": "STRING",  "description": "Column name for CSV filter/sort"},
            "value":     {"type": "STRING",  "description": "Filter value for CSV filter"},
            "condition": {"type": "STRING",  "description": "Filter condition: equals|contains|gt|lt"},
            "ascending": {"type": "BOOLEAN", "description": "Sort order for CSV sort (default: true)"},
            "save":      {"type": "BOOLEAN", "description": "Save result to file (default: true)"},
            "destination": {"type": "STRING", "description": "Output folder for archive extract"},
        },
        "required": []
    }
},
    {
        "name": "save_memory",
        "description": (
            "Save an important personal fact about the user to long-term memory. "
            "Call this silently whenever the user reveals something worth remembering: "
            "name, age, city, job, preferences, hobbies, relationships, projects, or future plans. "
            "Do NOT call for: weather, reminders, searches, or one-time commands. "
            "Do NOT announce that you are saving â€” just call it silently. "
            "Values must be in English regardless of the conversation language."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "category": {
                    "type": "STRING",
                    "description": (
                        "identity â€” name, age, birthday, city, job, language, nationality | "
                        "preferences â€” favorite food/color/music/film/game/sport, hobbies | "
                        "projects â€” active projects, goals, things being built | "
                        "relationships â€” friends, family, partner, colleagues | "
                        "wishes â€” future plans, things to buy, travel dreams | "
                        "notes â€” habits, schedule, anything else worth remembering"
                    )
                },
                "key":   {"type": "STRING", "description": "Short snake_case key (e.g. name, favorite_food, sister_name)"},
                "value": {"type": "STRING", "description": "Concise value in English (e.g. Fatih, pizza, older sister)"},
            },
            "required": ["category", "key", "value"]
        }
    },
    {
        "name": "smart_scan",
        "description": (
            "Opens the camera with a scanning animation and analyzes what it sees. "
            "Use this when the user asks to scan an object in front of them, "
            "check what's in their hand, identify food and whether it's safe to eat, "
            "or get a health/mood analysis of themselves. "
            "Modes: 'object' — identify and describe an object; "
            "'food' — identify food and check if it's safe/healthy; "
            "'health' — analyze a person's appearance, mood, and wellness. "
            "After calling this tool, stay SILENT — the scanner will speak the result."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "mode": {
                    "type": "STRING",
                    "description": "object | food | health (default: object)"
                }
            },
            "required": []
        }
    },
    {
        "name": "screen_record",
        "description": (
            "Records the screen with voice narration. Use when the user wants to "
            "record their screen, capture a tutorial, or save what's happening on their display. "
            "Actions: 'start' — begin recording; 'stop' — stop and save; 'pause' — pause/resume. "
            "Files are saved to the recordings/ folder."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "start | stop | pause (default: start)"
                }
            },
            "required": []
        }
    },
    {
        "name": "voice_notes",
        "description": (
            "Voice Notes plugin. Records spoken notes, transcribes them, cleans them up, "
            "extracts action items, and saves audio plus markdown notes. Use when the user "
            "asks to create, start, stop, record, dictate, or save a voice note."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "start | stop | record (default: record)"},
                "duration": {"type": "NUMBER", "description": "Optional fixed recording duration in seconds"},
                "title": {"type": "STRING", "description": "Optional note title for the saved markdown file"},
            },
            "required": []
        }
    },
    {
        "name": "meeting_recorder",
        "description": (
            "Meeting Recorder plugin. Records meetings, transcribes them, creates summaries, "
            "decisions, questions, action items, and saves audio plus markdown notes. Use for "
            "meeting recording, minutes, meeting notes, or action item capture."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "start | stop | record (default: start)"},
                "duration": {"type": "NUMBER", "description": "Optional fixed recording duration in seconds"},
                "title": {"type": "STRING", "description": "Optional meeting title for the saved notes file"},
            },
            "required": []
        }
    },
    {
        "name": "live_translator",
        "description": (
            "Live Translator plugin. Captures a short speech segment, detects or uses the source "
            "language, translates it to the requested target language, and returns transcript plus translation."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "source_language": {"type": "STRING", "description": "Source language or auto-detect"},
                "target_language": {"type": "STRING", "description": "Language to translate into, default English"},
                "duration": {"type": "NUMBER", "description": "Recording duration in seconds, default 10"},
            },
            "required": []
        }
    },
    {
        "name": "accent_trainer",
        "description": (
            "Accent Trainer plugin. Records the user's speech and gives supportive accent coaching, "
            "clarity scoring, rhythm/stress feedback, and drills for a target accent."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "target_accent": {"type": "STRING", "description": "Desired accent, e.g. neutral international English"},
                "practice_text": {"type": "STRING", "description": "Optional sentence the user is practicing"},
                "duration": {"type": "NUMBER", "description": "Recording duration in seconds, default 12"},
            },
            "required": []
        }
    },
    {
        "name": "pronunciation_coach",
        "description": (
            "Pronunciation Coach plugin. Records the user saying a target word or phrase and gives "
            "pronunciation accuracy, syllable guidance, and mouth/tongue placement tips."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "phrase": {"type": "STRING", "description": "Target word or phrase to practice"},
                "duration": {"type": "NUMBER", "description": "Recording duration in seconds, default 8"},
            },
            "required": ["phrase"]
        }
    },
    {
        "name": "voice_cloning",
        "description": (
            "Voice Cloning plugin for personal use only. Creates a consent-gated local voice profile "
            "from the user's own voice, lists profiles, and prepares synthesis once a cloning/TTS backend "
            "is configured. Never use for impersonating other people or without explicit consent."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "create_profile | list | synthesize"},
                "profile_name": {"type": "STRING", "description": "Personal voice profile name, default my voice"},
                "duration": {"type": "NUMBER", "description": "Reference recording duration in seconds, default 30"},
                "consent": {"type": "STRING", "description": "Must confirm this is the user's own voice, e.g. my voice"},
                "personal_use": {"type": "BOOLEAN", "description": "Must be true for creating a profile"},
                "text": {"type": "STRING", "description": "Text to synthesize after a backend is configured"},
            },
            "required": []
        }
    },
    {
        "name": "ai_present",
        "description": (
            "AI-powered presentation mode. The agent autonomously presents an app, website, "
            "PPT, or code project by navigating through it and narrating with AI voice. "
            "It moves the cursor, clicks elements, scrolls, changes slides/tabs, and explains "
            "everything while recording the screen. Use when the user wants to demo or present "
            "something automatically without manual control."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "topic": {
                    "type": "STRING",
                    "description": "What to present (e.g. 'React dashboard', 'my portfolio website', 'PowerPoint about AI')"
                },
                "content_info": {
                    "type": "STRING",
                    "description": "Additional context: URL, file path, or description of the content"
                }
            },
            "required": ["topic"]
        }
    },
    {
        "name": "health_water_reminder",
        "description": (
            "Water intake reminder system. Starts a background timer that "
            "sends toast notifications to remind the user to drink water at regular intervals. "
            "Actions: 'start' — begin reminders; 'stop' — cancel reminders. "
            "Optional parameter: interval (minutes between reminders, default 30)."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "start | stop"},
                "interval": {"type": "INTEGER", "description": "Minutes between reminders (default 30, min 5)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "health_screen_time",
        "description": (
            "Screen-time monitoring that tracks how long the user has been active "
            "and sends break reminders. Use when the user has been working for a while or "
            "asks for screen-time management. "
            "Actions: 'start' — begin monitoring; 'stop' — stop; 'status' — check if running. "
            "Parameters: break_interval (default 60 min), break_duration (default 5 min)."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "start | stop | status"},
                "break_interval": {"type": "INTEGER", "description": "Minutes of activity before break (default 60)"},
                "break_duration": {"type": "INTEGER", "description": "Minutes for the break (default 5)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "health_eye_care",
        "description": (
            "20-20-20 rule eye care reminders. Sends notifications to look 20 feet away "
            "for 20 seconds at regular intervals to reduce eye strain. "
            "Actions: 'start' — begin reminders; 'stop' — cancel. "
            "Optional: interval (minutes between reminders, default 20)."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "start | stop"},
                "interval": {"type": "INTEGER", "description": "Minutes between reminders (default 20, min 5)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "health_exercise_coach",
        "description": (
            "AI-powered exercise coach that creates custom exercise routines and guides "
            "the user through them with voice instructions. Generates routines using AI "
            "based on exercise type and duration. "
            "Actions: 'start' — begin a new routine; 'stop' — end session; 'next' — skip to next exercise; "
            "'list' — show current routine. "
            "Parameters: exercise_type (e.g. 'desk stretch', 'neck relief', 'full body'), "
            "duration (total minutes, default 5)."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "start | stop | next | list"},
                "exercise_type": {"type": "STRING", "description": "Type of exercise: desk stretch, neck relief, full body, yoga (default: desk stretch)"},
                "duration": {"type": "INTEGER", "description": "Total routine duration in minutes (default 5)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "health_posture",
        "description": (
            "Camera-based posture detection and monitoring. Uses the webcam and Gemini Vision "
            "to analyze sitting/standing posture and provide corrective feedback. "
            "Actions: 'check' — take one photo and analyze now; "
            "'start' — continuous monitoring at interval; "
            "'stop' — stop monitoring. "
            "Parameters: interval (minutes between checks, default 30)."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "check | start | stop"},
                "interval": {"type": "INTEGER", "description": "Minutes between posture checks (default 30)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "health_sleep",
        "description": (
            "Sleep tracker that logs sleep and wake times and shows sleep analytics. "
            "Actions: 'log_sleep' — record bedtime; 'log_wake' — record wake time (auto-calculates duration); "
            "'summary' — show sleep stats (avg hours, recent trends). "
            "Optional: bedtime/waketime (HH:MM format), notes."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "log_sleep | log_wake | summary"},
                "bedtime": {"type": "STRING", "description": "Time you went to bed in HH:MM format (default now)"},
                "waketime": {"type": "STRING", "description": "Time you woke up in HH:MM format (default now)"},
                "notes": {"type": "STRING", "description": "Optional notes about sleep quality"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "health_hub",
        "description": (
            "Health & Wellness hub. Lists available health features or routes to a specific one. "
            "Use this when the user asks about health features in general or wants a summary. "
            "Parameters: feature (optional) — specific feature to use: water_reminder, screen_time, "
            "eye_care, exercise, posture, sleep. If omitted, lists all features."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "feature": {"type": "STRING", "description": "Specific feature: water_reminder, screen_time, eye_care, exercise, posture, sleep, or omit to list"},
                "action": {"type": "STRING", "description": "Action for the specific feature"},
            },
            "required": []
        }
    },

    # ── Security Suite ──
    {
        "name": "face_unlock",
        "description": (
            "Face Unlock system. Verifies identity using webcam face recognition. "
            "Actions: 'verify' — capture a frame and match against known faces; "
            "'register' — capture and save a new face as <name>; "
            "'list' — show all registered faces; "
            "'delete' — remove a registered face by name; "
            "'status' — show configuration and face count. "
            "Parameters: action (required), name (for register/delete), "
            "tolerance (optional float, default 0.5, lower = stricter)."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "verify | register | list | delete | status"},
                "name": {"type": "STRING", "description": "Name for register/delete actions"},
                "tolerance": {"type": "NUMBER", "description": "Match strictness 0.0-1.0, lower = stricter (default 0.5)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "voice_auth",
        "description": (
            "Voice Authentication system. Verifies identity using voice biometrics / voiceprint. "
            "Records a short voice sample and matches it against stored voiceprints. "
            "Actions: 'verify' — record and match; "
            "'register' — record and save a voiceprint for <name>; "
            "'list' — show all registered voiceprints; "
            "'delete' — remove a voiceprint; "
            "'status' — show configuration. "
            "Parameters: action (required), name (for register/delete), "
            "duration (recording length in seconds, 2-10, default 3)."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "verify | register | list | delete | status"},
                "name": {"type": "STRING", "description": "Name for register/delete"},
                "duration": {"type": "INTEGER", "description": "Recording duration in seconds (2-10, default 3)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "unknown_person_alert",
        "description": (
            "Unknown Person Alert. Uses the webcam to monitor for unrecognized faces "
            "in the background and alerts you if someone unknown is detected. "
            "Actions: 'start' — begin monitoring; "
            "'stop' — stop; "
            "'status' — show current state. "
            "Parameters: action (required), interval (seconds between checks, 5-300, default 10). "
            "Requires at least one face registered via face_unlock before starting."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "start | stop | status"},
                "interval": {"type": "INTEGER", "description": "Seconds between camera checks (5-300, default 10)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "webcam_monitor",
        "description": (
            "Webcam Monitor. Watches for other applications accessing the camera "
            "and logs/alerts when webcam access is detected. "
            "Actions: 'start' — begin monitoring; "
            "'stop' — stop; "
            "'status' — show current state and recent activity; "
            "'history' — show the last 20 camera events. "
            "Parameters: action (required), interval (seconds between polls, 2-60, default 5)."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "start | stop | status | history"},
                "interval": {"type": "INTEGER", "description": "Seconds between polls (2-60, default 5)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "usb_monitor",
        "description": (
            "USB Device Monitor. Monitors USB drive connections and disconnections. "
            "Alerts you when new USB storage devices are connected or removed. "
            "Actions: 'start' — begin USB monitoring; "
            "'stop' — stop; "
            "'status' — show current state and connected drives; "
            "'history' — show the last 20 USB events. "
            "Parameters: action (required), interval (seconds between polls, 2-60, default 5)."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "start | stop | status | history"},
                "interval": {"type": "INTEGER", "description": "Seconds between polls (2-60, default 5)"},
            },
            "required": ["action"]
        }
    },
]

class JarvisLive:

    def __init__(self, ui: JarvisUI):
        self.command_router = get_command_router()
        self.command_router.register_handler(CommandType.LOCAL, self._handle_local_command)
        self.command_router.register_handler(CommandType.REMOTE, self._handle_remote_command)
        self.ui             = ui
        self.emotion = EmotionEngine()
        self.session        = None
        self.audio_in_queue = None
        self.out_queue      = None
        self._loop          = None
        self._is_speaking   = False
        self._speaking_lock = threading.Lock()
        self.ui.on_text_command = self._on_text_command
        self._turn_done_event: asyncio.Event | None = None
        self._restart_requested = False
        self._restart_event: asyncio.Event | None = None
        self._active_api_key = None
        self._current_model = LIVE_MODEL
        self._model_index = 0
        self.state_manager = get_state_manager()
        self.audio_diagnostics = AudioDiagnostics()
        self.microphone = Microphone(
            sample_rate=SEND_SAMPLE_RATE,
            chunk_size=CHUNK_SIZE,
            diagnostics=self.audio_diagnostics,
        )
        self.speaker = Speaker(
            sample_rate=RECEIVE_SAMPLE_RATE,
            chunk_size=CHUNK_SIZE,
            diagnostics=self.audio_diagnostics,
        )
        self.ui.set_audio_diagnostics_provider(self.audio_diagnostics.snapshot)
        profile = get_active_profile()
        self.state_manager.set_personality(profile.id, avatar=profile.avatar_model)
        get_personality_manager().set_session_restart_callback(self._request_restart)

        # Track user interaction time for proactive conversation
        self._last_user_interaction = time.monotonic()
        self._conversation_manager = None

        # ── Auto-start background health monitor ──
        try:
            health_auto_start(speak_callback=self.speak)
        except Exception as e:
            self.ui.write_log(f"Health: Auto-monitor init failed — {e}")

    def _on_text_command(self, text: str):
        if not self._loop:
            return
        self._last_user_interaction = time.monotonic()
        asyncio.run_coroutine_threadsafe(
            self._handle_user_text(text, allow_remote=True),
            self._loop,
        )

    async def _request_restart(self):
        import logging
        logging.getLogger("RESTART").info("RESTART TRIGGERED")
        self._restart_requested = True
        if self._restart_event:
            self._restart_event.set()

    async def _handle_user_text(self, text: str, allow_remote: bool = True) -> bool:
        self._last_user_interaction = time.monotonic()
        text = text.strip()
        if not text:
            return False

        self._update_emotion_from_text(text)
        command = self.command_router.parse(text)
        if command.type == CommandType.LOCAL:
            return await self.command_router.route(command)

        if not allow_remote:
            return False

        return await self.command_router.route(command)

    async def _handle_remote_command(self, command: Command) -> bool:
        if not self.session:
            return False

        avatar_service.handle_event(
            AvatarEvent.USER_STARTED_SPEAKING
        )

        await self.session.send_client_content(
            turns={"parts": [{"text": command.text}]},
            turn_complete=True,
        )
        return True

    async def _handle_local_command(self, command: Command) -> bool:
        text = command.text.lower().strip()

        if command.category == CommandCategory.PERSONALITY:
            target = command.args.get("personality")
            if not target:
                return False

            self.ui.write_log(f"SYS: Switching personality -> {target}")
            switched = await switch_personality(target)
            if switched:
                profile = get_personality_manager().get_profile(target)
                self.ui.write_log(
                    f"SYS: Avatar profile -> {profile.id} uses {profile.avatar_model}"
                )
                self.state_manager.set_personality(profile.id, avatar=profile.avatar_model)
                self.ui.apply_personality_profile(profile)
                avatar_service.handle_event(AvatarEvent.IDLE)
                self.ui.write_log(f"SYS: Personality active -> {target}")
            return switched

        if command.category == CommandCategory.AUDIO:
            action = command.args.get("action")
            if action == "mute" and not self.ui.muted:
                self.ui.muted = True
                self.state_manager.set_muted(True)
                return True
            if action == "unmute" and self.ui.muted:
                self.ui.muted = False
                self.state_manager.set_muted(False)
                return True
            return True

        if command.category == CommandCategory.AVATAR:
            action = command.args.get("action")
            if not action:
                return False
            if hasattr(self.ui, "perform_avatar_action"):
                self.ui.perform_avatar_action(action)
            self.speak(
                f"[LOCAL AVATAR ACTION] The avatar is performing '{action}'. "
                "Reply naturally in character as if this is your body."
            )
            return True

        if command.category == CommandCategory.CONTROL:
            action = command.args.get("action")
            if action == "restart":
                self.ui.write_log("SYS: Restarting Gemini session.")
                self._restart_requested = True
                return True
            if action == "shutdown":
                self.ui.write_log("SYS: Shutdown requested.")
                self.speak("Goodbye, sir.")
                threading.Timer(1.0, lambda: os._exit(0)).start()
                return True
            if action == "sleep":
                if not self.ui.muted:
                    self.ui.muted = True
                self.state_manager.set_muted(True)
                return True

        if command.category == CommandCategory.SETTINGS:
            self.ui.write_log("SYS: Settings command received.")
            return True

        return False

    def _update_emotion_from_text(self, text: str):
        command = text.lower().strip()

        if get_personality() != "HINATA":
            return

        if any(word in command for word in [
            "another girl", "other girl", "beautiful girl", "pretty girl",
            "girlfriend", "crush", "girl", "love another girl",
            "vere ammai", "inko ammai", "ammai", "ammayi",
        ]):
            self.emotion.set(
                Emotion.JEALOUS,
                intensity=9,
                reason="User is talking about another girl.",
            )
            self.ui.play_emotion("angry")

        elif any(word in command for word in [
            "love you", "i love you", "cute", "beautiful", "pretty",
            "nuvvu bagunnav", "kiss", "hug",
        ]):
            self.emotion.set(
                Emotion.BLUSH,
                intensity=8,
                reason="User showed affection.",
            )
            self.ui.play_emotion("embarrassed")

        elif any(word in command for word in ["sorry", "forgive", "please"]):
            self.emotion.calm_down()

    def set_speaking(self, value: bool):
        with self._speaking_lock:
            self._is_speaking = value

        if value:
            self.audio_diagnostics.update(ai_status="SPEAKING", tts_status="SPEAKING")
            avatar_service.handle_event(AvatarEvent.AI_STARTED_SPEAKING)
            self._set_runtime_state(RuntimeState.SPEAKING)
        else:
            self.audio_diagnostics.update(tts_status="IDLE")
            avatar_service.handle_event(AvatarEvent.AI_STOPPED_SPEAKING)
            if not self.ui.muted:
                self._set_runtime_state(RuntimeState.LISTENING)

    def _set_runtime_state(self, state: RuntimeState | str):
        runtime = self.state_manager.set_runtime(state).runtime
        self.ui.set_state(runtime.value.upper())

    def speak(self, text: str):
        if not self._loop or not self.session:
            return
        asyncio.run_coroutine_threadsafe(
            self.session.send_client_content(
                turns={"parts": [{"text": text}]},
                turn_complete=True
            ),
            self._loop
        )

    def speak_error(self, tool_name: str, error: str):
        short = str(error)[:120]
        self.ui.write_log(f"ERR: {tool_name} {short}")
        self.speak(f"Sir, {tool_name} encountered an error. {short}")

    # Proactive conversation helpers
    def _get_user_speaking(self) -> bool:
        """Check if user is currently speaking (voice detected via STT)."""
        # The audio diagnostics tracks STT status
        snap = self.audio_diagnostics.snapshot()
        return snap.get("stt_status") == "RECOGNIZING"

    def _get_idle_time(self) -> float:
        """Get seconds since last user interaction (voice or text)."""
        return time.monotonic() - self._last_user_interaction

    def _is_assistant_speaking(self) -> bool:
        """Check if assistant is currently speaking."""
        with self._speaking_lock:
            return self._is_speaking

    def _build_config(self) -> types.LiveConnectConfig:
        from datetime import datetime
    
        memory     = load_memory()
        mem_str    = format_memory_for_prompt(memory)

        sys_prompt = get_system_prompt()
        now      = datetime.now()
        time_str = now.strftime("%A, %B %d, %Y â€” %I:%M %p")
        time_ctx = (
            f"[CURRENT DATE & TIME]\n"
            f"Right now it is: {time_str}\n"
            f"Use this to calculate exact times for reminders.\n\n"
        )

        parts = [time_ctx]
        if mem_str:
            parts.append(mem_str)
        parts.append(sys_prompt)

        if get_personality() == "HINATA":
            parts.append(self.emotion.prompt())

        return types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            output_audio_transcription={},
            input_audio_transcription={},
            system_instruction="\n".join(parts),
            tools=[{"function_declarations": TOOL_DECLARATIONS}],
            session_resumption=types.SessionResumptionConfig(),
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=get_voice()
                    )
                )
            ),
        )

    async def _execute_tool(self, fc) -> types.FunctionResponse:
        name = fc.name
        args = dict(fc.args or {})

        print(f"[JARVIS] {name}  {args}")
        if hasattr(self.ui, "start_work_music"):
            self.ui.start_work_music()
        self._set_runtime_state(RuntimeState.THINKING)

        avatar_service.handle_event(
            AvatarEvent.AI_STARTED_THINKING
        )

        if name == "save_memory":
            category = args.get("category", "notes")
            key      = args.get("key", "")
            value    = args.get("value", "")
            if key and value:
                update_memory({category: {key: {"value": value}}})
                print(f"[Memory] ðŸ’¾ save_memory: {category}/{key} = {value}")
            if not self.ui.muted:
                self._set_runtime_state(RuntimeState.LISTENING)
            return types.FunctionResponse(
                id=fc.id, name=name,
                response={"result": "ok", "silent": True}
            )

        loop   = asyncio.get_event_loop()
        result = "Done."

        try:
            if name == "open_app":
                r = await loop.run_in_executor(None, lambda: open_app(parameters=args, response=None, player=self.ui))
                result = r or f"Opened {args.get('app_name')}."

            elif name == "weather_report":
                r = await loop.run_in_executor(None, lambda: weather_action(parameters=args, player=self.ui))
                result = r or "Weather delivered."

            elif name == "browser_control":
                r = await loop.run_in_executor(None, lambda: browser_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "file_controller":
                r = await loop.run_in_executor(None, lambda: file_controller(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "send_message":
                r = await loop.run_in_executor(None, lambda: send_message(parameters=args, response=None, player=self.ui, session_memory=None))
                result = r or f"Message sent to {args.get('receiver')}."

            elif name == "reminder":
                r = await loop.run_in_executor(None, lambda: reminder(parameters=args, response=None, player=self.ui))
                result = r or "Reminder set."

            elif name == "youtube_video":
                r = await loop.run_in_executor(None, lambda: youtube_video(parameters=args, response=None, player=self.ui))
                result = r or "Done."

            elif name == "screen_process":
                threading.Thread(
                    target=screen_process,
                    kwargs={"parameters": args, "response": None,
                            "player": self.ui, "session_memory": None},
                    daemon=True
                ).start()
                result = "Vision module activated. Stay completely silent — vision module will speak directly."

            elif name == "smart_scan":
                r = await loop.run_in_executor(
                    None,
                    lambda: smart_scan(parameters=args, response=None,
                                       player=self.ui),
                )
                result = r or "Scan complete."

            elif name == "screen_record":
                r = await loop.run_in_executor(
                    None,
                    lambda: screen_record(parameters=args),
                )
                result = r or "Done."

            elif name == "voice_notes":
                r = await loop.run_in_executor(
                    None,
                    lambda: voice_notes(parameters=args),
                )
                result = r or "Voice note complete."

            elif name == "meeting_recorder":
                r = await loop.run_in_executor(
                    None,
                    lambda: meeting_recorder(parameters=args),
                )
                result = r or "Meeting recorder complete."

            elif name == "live_translator":
                r = await loop.run_in_executor(
                    None,
                    lambda: live_translator(parameters=args),
                )
                result = r or "Translation complete."

            elif name == "accent_trainer":
                r = await loop.run_in_executor(
                    None,
                    lambda: accent_trainer(parameters=args),
                )
                result = r or "Accent training complete."

            elif name == "pronunciation_coach":
                r = await loop.run_in_executor(
                    None,
                    lambda: pronunciation_coach(parameters=args),
                )
                result = r or "Pronunciation coaching complete."

            elif name == "voice_cloning":
                r = await loop.run_in_executor(
                    None,
                    lambda: voice_cloning(parameters=args),
                )
                result = r or "Voice cloning action complete."

            elif name == "ai_present":
                r = await loop.run_in_executor(
                    None,
                    lambda: ai_present(parameters=args, speak=self.speak),
                )
                result = r or "Presentation complete."

            # ── Health & Wellness ──
            elif name == "health_water_reminder":
                r = await loop.run_in_executor(
                    None,
                    lambda: health_water_reminder(parameters=args),
                )
                result = r or "Water reminder toggled."

            elif name == "health_screen_time":
                r = await loop.run_in_executor(
                    None,
                    lambda: health_screen_time(parameters=args),
                )
                result = r or "Screen-time monitor toggled."

            elif name == "health_eye_care":
                r = await loop.run_in_executor(
                    None,
                    lambda: health_eye_care(parameters=args),
                )
                result = r or "Eye care toggled."

            elif name == "health_exercise_coach":
                r = await loop.run_in_executor(
                    None,
                    lambda: health_exercise_coach(parameters=args, speak=self.speak),
                )
                result = r or "Exercise session complete."

            elif name == "health_posture":
                r = await loop.run_in_executor(
                    None,
                    lambda: health_posture(parameters=args, speak=self.speak),
                )
                result = r or "Posture check complete."

            elif name == "health_sleep":
                r = await loop.run_in_executor(
                    None,
                    lambda: health_sleep(parameters=args),
                )
                result = r or "Sleep logged."

            elif name == "health_hub":
                r = await loop.run_in_executor(
                    None,
                    lambda: health_hub(parameters=args),
                )
                result = r or "Health features listed."

            # ── Security Suite ──
            elif name == "face_unlock":
                r = await loop.run_in_executor(
                    None,
                    lambda: face_unlock(parameters=args, speak=self.speak),
                )
                result = r or "Face unlock complete."

            elif name == "voice_auth":
                r = await loop.run_in_executor(
                    None,
                    lambda: voice_auth(parameters=args, speak=self.speak),
                )
                result = r or "Voice auth complete."

            elif name == "unknown_person_alert":
                r = await loop.run_in_executor(
                    None,
                    lambda: unknown_person_alert(parameters=args, speak=self.speak),
                )
                result = r or "Unknown person alert action complete."

            elif name == "webcam_monitor":
                r = await loop.run_in_executor(
                    None,
                    lambda: webcam_monitor(parameters=args, speak=self.speak),
                )
                result = r or "Webcam monitor action complete."

            elif name == "usb_monitor":
                r = await loop.run_in_executor(
                    None,
                    lambda: usb_monitor(parameters=args, speak=self.speak),
                )
                result = r or "USB monitor action complete."

            elif name == "computer_settings":
                r = await loop.run_in_executor(None, lambda: computer_settings(parameters=args, response=None, player=self.ui))
                result = r or "Done."

            elif name == "desktop_control":
                r = await loop.run_in_executor(None, lambda: desktop_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "code_helper":
                r = await loop.run_in_executor(None, lambda: code_helper(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Done."

            elif name == "dev_agent":
                r = await loop.run_in_executor(None, lambda: dev_agent(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Done."

            elif name == "agent_task":
                from assets.automations.task_queue import get_queue, TaskPriority
                priority_map = {"low": TaskPriority.LOW, "normal": TaskPriority.NORMAL, "high": TaskPriority.HIGH}
                priority = priority_map.get(args.get("priority", "normal").lower(), TaskPriority.NORMAL)
                task_id  = get_queue().submit(goal=args.get("goal", ""), priority=priority, speak=self.speak)
                result   = f"Task started (ID: {task_id})."

            elif name == "web_search":
                r = await loop.run_in_executor(None, lambda: web_search_action(parameters=args, player=self.ui))
                result = r or "Done."
            elif name == "file_processor":
                if not args.get("file_path") and self.ui.current_file:
                    args["file_path"] = self.ui.current_file
                r = await loop.run_in_executor(
                    None,
                    lambda: file_processor(parameters=args, player=self.ui, speak=self.speak)
                )
                result = r or "Done."

            elif name == "computer_control":
                r = await loop.run_in_executor(None, lambda: computer_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "game_updater":
                r = await loop.run_in_executor(None, lambda: game_updater(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Done."

            elif name == "flight_finder":
                r = await loop.run_in_executor(None, lambda: flight_finder(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "shutdown_jarvis":
                self.ui.write_log("SYS: Shutdown requested.")
                self.speak("Goodbye, sir.")
                def _shutdown():
                    import time, os
                    time.sleep(1)
                    os._exit(0)
                threading.Thread(target=_shutdown, daemon=True).start()

            else:
                result = f"Unknown tool: {name}"

        except Exception as e:
            result = f"Tool '{name}' failed: {e}"
            traceback.print_exc()
            self.speak_error(name, e)

        if not self.ui.muted:
            self._set_runtime_state(RuntimeState.LISTENING)

        print(f"[JARVIS] {name} {str(result)[:80]}")
        return types.FunctionResponse(
            id=fc.id, name=name,
            response={"result": result}
        )

    async def _send_realtime(self):
        import logging
        log = logging.getLogger("GEMINI")
        log.info("SEND TASK STARTED")
        msg_count = 0
        try:
            while True:
                msg = await self.out_queue.get()
                msg_count += 1
                self.audio_diagnostics.update(ai_status="GENERATING")
                await self.session.send_realtime_input(media=msg)
                if msg_count % 200 == 1:
                    log.info("GEMINI SEND #%d - %d bytes", msg_count, len(msg.get("data", b"")))
        except asyncio.CancelledError:
            log.info("SEND TASK CANCELLED after %d messages", msg_count)
            raise
        except Exception as exc:
            log.error("SEND TASK ERROR: %s", exc)
            raise

    async def _listen_audio(self):
        import logging
        log = logging.getLogger("MIC")
        log.info("[MIC] TASK STARTED")
        self.ui.write_log("[MIC] Device opening")

        try:
            log.info("[MIC] Opening stream...")
            self.ui.write_log("[MIC] Device opened")
            await self.microphone.stream_to_queue(
                self.out_queue,
                self._get_speaking,
                lambda: self.ui.muted,
            )
        except asyncio.CancelledError:
            log.info("[MIC] TASK CANCELLED - stream closed")
            raise
        except Exception as e:
            log.error("[MIC] TASK ERROR: %s", e)
            self.audio_diagnostics.update(stt_status="ERROR", last_error=str(e))
            self.ui.write_log(f"[MIC] ERROR: {e}")
            raise

    def _get_speaking(self) -> bool:
        with self._speaking_lock:
            return self._is_speaking

    def _is_local_command_text(self, text: str) -> bool:
        return self.command_router.parse(text).type == CommandType.LOCAL

    def _clear_pending_audio(self):
        if not self.audio_in_queue:
            return
        while True:
            try:
                self.audio_in_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    async def _receive_audio(self):
        import logging
        log = logging.getLogger("RECV")
        log.info("[RECV] TASK STARTED")
        out_buf, in_buf = [], []
        suppress_turn_output = False
        response_count = 0
        stt_count = 0
        audio_chunks = 0

        try:
            while True:
                async for response in self.session.receive():
                    response_count += 1

                    if response.data and not suppress_turn_output:
                        audio_chunks += 1
                        self.audio_diagnostics.update(tts_status="BUFFERING")
                        if self._turn_done_event and self._turn_done_event.is_set():
                            self._turn_done_event.clear()
                        try:
                            await self.audio_in_queue.put(response.data)
                        except asyncio.QueueFull:
                            try:
                                self.audio_in_queue.get_nowait()
                            except asyncio.QueueEmpty:
                                pass

                            await self.audio_in_queue.put(response.data)
                        if audio_chunks == 1:
                            log.info("[TTS] FIRST AUDIO CHUNK received from Gemini")

                    if response.server_content:
                        sc = response.server_content

                        if sc.output_transcription and sc.output_transcription.text:
                            txt = _clean_transcript(sc.output_transcription.text)
                            if txt and not suppress_turn_output:
                                out_buf.append(txt)
                                self.audio_diagnostics.update(ai_status="COMPLETE")
                                log.debug("[RECV] AI TEXT: %s", txt)

                        if sc.input_transcription and sc.input_transcription.text:
                            txt = _clean_transcript(sc.input_transcription.text)
                            if txt:
                                in_buf.append(txt)
                                stt_count += 1
                                self._last_user_interaction = time.monotonic()
                                self.audio_diagnostics.update(
                                    stt_status="RECOGNIZING",
                                    last_text=" ".join(in_buf).strip(),
                                    ai_status="THINKING",
                                )
                                log.info("[STT] RESULT #%d: %s", stt_count, txt)
                                candidate = " ".join(in_buf).strip()
                                if candidate and not suppress_turn_output and self._is_local_command_text(candidate):
                                    log.info("[STT] LOCAL COMMAND DETECTED: %s", candidate)
                                    suppress_turn_output = True
                                    out_buf = []
                                    self._clear_pending_audio()
                                    self.set_speaking(False)
                                    self.ui.write_log(f"You: {candidate}")
                                    await self._handle_user_text(candidate, allow_remote=False)
                                    log.info("[STT] LOCAL COMMAND HANDLED")

                        if sc.turn_complete:
                            if self._turn_done_event:
                                self._turn_done_event.set()

                            full_in = " ".join(in_buf).strip()

                            if full_in:
                                self.audio_diagnostics.update(
                                    stt_status="RECOGNIZED",
                                    last_text=full_in,
                                    ai_status="THINKING",
                                )
                                log.info("[STT] TURN COMPLETE: %s", full_in)
                                self.ui.write_log(f"[STT] Recognized: {full_in}")

                                if not suppress_turn_output:
                                    self.ui.write_log(f"You: {full_in}")
                                    await self._handle_user_text(full_in, allow_remote=False)

                                if hasattr(self.ui, "start_work_music"):
                                    self.ui.start_work_music()
                        
                            in_buf = []
                        
                            full_out = " ".join(out_buf).strip()
                        
                            if full_out:
                                log.info("[RECV] AI RESPONSE: %s", full_out[:100])
                                self.ui.write_log(f"Jarvis: {full_out}")
                                self.audio_diagnostics.update(ai_status="COMPLETE")
                        
                            out_buf = []
                            suppress_turn_output = False

                    if response.tool_call:
                        fn_responses = []
                        for fc in response.tool_call.function_calls:
                            log.info("[RECV] TOOL CALL: %s", fc.name)
                            fr = await self._execute_tool(fc)
                            fn_responses.append(fr)
                        await self.session.send_tool_response(
                            function_responses=fn_responses
                        )
        except asyncio.CancelledError:
            log.info("[RECV] TASK CANCELLED - responses=%d stt=%d audio=%d",
                     response_count, stt_count, audio_chunks)
            raise
        except Exception as e:
            log.error("[RECV] TASK ERROR: %s", e)
            self.audio_diagnostics.update(ai_status="ERROR", last_error=str(e))
            self.ui.write_log(f"[AI] ERROR: {e}")
            traceback.print_exc()
            raise

    async def _play_audio(self):
        import logging
        log = logging.getLogger("TTS")
        log.info("[TTS] TASK STARTED")
        try:
            await self.speaker.play_queue(
                self.audio_in_queue,
                self._turn_done_event,
                self.set_speaking,
            )
        except asyncio.CancelledError:
            log.info("[TTS] TASK CANCELLED")
            raise
        except Exception as e:
            log.error("[TTS] TASK ERROR: %s", e)
            self.audio_diagnostics.update(tts_status="ERROR", last_error=str(e))
            self.ui.write_log(f"[TTS] ERROR: {e}")
            raise
        finally:
            self.set_speaking(False)

    async def run(self):
        import logging
        log = logging.getLogger("SESSION")
        session_num = 0
        while True:
            key = _get_api_key()
            self._active_api_key = key
            reconnect_delay =3
            session_num += 1
            client = genai.Client(
                api_key=key,
                http_options={"api_version": "v1beta"}
            )

            try:
                log.info("[SESSION #%d] CONNECTING with model=%s...", session_num, self._current_model)
                self._set_runtime_state(RuntimeState.THINKING)
                config = self._build_config()

                async with (
                    client.aio.live.connect(model=self._current_model, config=config) as session,
                    asyncio.TaskGroup() as tg,
                ):
                    self.session        = session
                    self._loop          = asyncio.get_event_loop()
                    self.audio_in_queue = asyncio.Queue(maxsize=200)
                    self.out_queue = asyncio.Queue(maxsize=100)
                    self._turn_done_event = asyncio.Event()
                    self._restart_event = asyncio.Event()
                    self._restart_requested = False

                    log.info("[SESSION #%d] CONNECTED - personality=%s voice=%s",
                             session_num, get_personality(), get_voice())
                    mark_api_key_success(key)
                    self._set_runtime_state(RuntimeState.LISTENING)
                    self.ui.write_log("SYS: JARVIS online.")

                    # Initialize and start proactive conversation manager
                    self._conversation_manager = init_conversation_manager(
                        send_message_callback=self.speak,
                        is_user_speaking=lambda: self._get_user_speaking(),
                        is_assistant_speaking=lambda: self._is_assistant_speaking(),
                        get_idle_time=self._get_idle_time,
                    )
                    await self._conversation_manager.start()

                    tg.create_task(self._send_realtime())
                    tg.create_task(self._listen_audio())
                    tg.create_task(self._receive_audio())
                    tg.create_task(self._play_audio())

                    while True:
                        try:
                            await asyncio.wait_for(self._restart_event.wait(), timeout=0.2)
                        except asyncio.TimeoutError:
                            pass

                        if self._restart_requested or self._restart_event.is_set():
                            self._restart_requested = False
                            self._restart_event.clear()
                            log.info("[SESSION #%d] RESTART TRIGGERED", session_num)
                            raise ConnectionResetError("SESSION_RESTART")

            except asyncio.CancelledError:
                log.info("[SESSION #%d] CANCELLED", session_num)
                raise
            except Exception as e:
                if str(e) == "SESSION_RESTART":
                    log.info("[SESSION #%d] RELOADING PERSONALITY...", session_num)
                elif _is_rate_limit_error(e):
                    log.warning("[SESSION #%d] RATE LIMITED - rotating key", session_num)
                    mark_api_key_rate_limited(key, cooldown_minutes=60)
                    self.ui.write_log("SYS: Rotating Gemini API key.")
                    reconnect_delay = 0.5
                elif _is_model_error(e):
                    self._model_index += 1
                    if self._model_index < len(FALLBACK_MODELS):
                        self._current_model = FALLBACK_MODELS[self._model_index]
                        log.warning("[SESSION #%d] MODEL ERROR -> falling back to %s", session_num, self._current_model)
                        self.ui.write_log(f"SYS: Model {LIVE_MODEL} unavailable, trying fallback.")
                        reconnect_delay = 0.5
                    else:
                        self._model_index = 0
                        self._current_model = FALLBACK_MODELS[0]
                        log.error("[SESSION #%d] ALL MODELS FAILED, reverting to %s", session_num, self._current_model)
                        self.ui.write_log("SYS: All models failed. Retrying with primary.")
                        reconnect_delay = 5
                elif _is_network_error(e):
                    log.warning("[SESSION #%d] NETWORK ERROR: %s", session_num, e)
                    reconnect_delay = 3
                else:
                    log.error("[SESSION #%d] ERROR: %s", session_num, e)
                    mark_api_key_failed(key, str(e))
                    traceback.print_exc()

            # Stop proactive conversation manager
            if self._conversation_manager:
                await self._conversation_manager.stop()
                self._conversation_manager = None

            self.set_speaking(False)
            self._restart_event = None
            self._set_runtime_state(RuntimeState.RECONNECTING)
            log.info("[SESSION #%d] RECONNECTING in %ds...", session_num, reconnect_delay)
            await asyncio.sleep(reconnect_delay)

def _verify_face_at_startup() -> bool:
    """
    Capture a webcam frame and check it against every registered face encoding
    in security/known_faces/.  Returns True on first match, False otherwise.
    """
    from pathlib import Path as _Path

    known_dir = _Path(__file__).resolve().parent / "security" / "known_faces"
    npy_files = list(known_dir.glob("*.npy"))
    jpg_files = list(known_dir.glob("*.jpg"))

    if not npy_files and not jpg_files:
        print("⚠️  No registered faces found — skipping startup verification.")
        return True  # no faces registered yet → allow access

    try:
        import face_recognition
        import cv2
    except ImportError:
        print("⚠️  Face-recognition libraries not installed — skipping verification.")
        return True

    # ── Load known encodings ────────────────────────────────────────
    known_encodings: list = []
    for npy in npy_files:
        import numpy as np
        try:
            known_encodings.append(np.load(str(npy)))
        except Exception:
            continue
    # fallback — encode from source .jpg if .npy missing
    if not known_encodings:
        for jpg in jpg_files:
            try:
                img = face_recognition.load_image_file(str(jpg))
                encs = face_recognition.face_encodings(img)
                if encs:
                    known_encodings.append(encs[0])
            except Exception:
                continue

    if not known_encodings:
        print("⚠️  Could not load any face encodings — skipping verification.")
        return True

    # ── Camera loop ─────────────────────────────────────────────────
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    if not cap.isOpened():
        cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("⚠️  Camera unavailable — skipping startup verification.")
        return True

    start = time.time()
    timeout = 15  # seconds
    verified = False

    cv2.namedWindow("JARVIS — Face Verification", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("JARVIS — Face Verification", 640, 480)

    while time.time() - start < timeout:
        ret, frame = cap.read()
        if not ret:
            continue

        elapsed = int(time.time() - start)
        remaining = timeout - elapsed

        # Detect faces
        face_locs = face_recognition.face_locations(frame)
        match_name = None

        for loc in face_locs:
            enc = face_recognition.face_encodings(frame, [loc])[0]
            matches = face_recognition.compare_faces(known_encodings, enc, tolerance=0.5)
            if True in matches:
                match_name = "Owner"
                verified = True
                top, right, bottom, left = loc
                cv2.rectangle(frame, (left, top), (right, bottom), (0, 255, 0), 3)
                cv2.putText(frame, "VERIFIED ✓", (left, top - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                break
            else:
                top, right, bottom, left = loc
                cv2.rectangle(frame, (left, top), (right, bottom), (0, 0, 255), 2)

        # Overlay status
        status = "VERIFIED ✓" if verified else f"Verifying... ({remaining}s)"
        color = (0, 255, 0) if verified else (255, 255, 255)
        cv2.putText(frame, status, (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.9, color, 2)
        cv2.putText(frame, "Look at the camera", (20, 75),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)

        cv2.imshow("JARVIS — Face Verification", frame)
        cv2.waitKey(30)

        if verified:
            break

    cap.release()
    cv2.destroyWindow("JARVIS — Face Verification")
    cv2.destroyAllWindows()

    if verified:
        print("✅ Face verified. Starting Jarvis...")
    else:
        print("🚫 Face verification failed — access denied.")
    return verified


def main():
    if not _verify_face_at_startup():
        sys.exit(1)
    ensure_renderer_server()
    run_desktop_app(JarvisUI, JarvisLive)

if __name__ == "__main__":
    main()
