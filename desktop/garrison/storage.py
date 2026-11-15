from __future__ import annotations
import base64
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import tempfile
import time


def user_dir():
    path = Path(os.environ.get('GARRISON_DATA_DIR', Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'GarrisonAssistant'))
    path.mkdir(parents=True, exist_ok=True)
    return path


def atomic_json(path, data):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.writing-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2); f.flush(); os.fsync(f.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name): os.unlink(name)


def read_json(path, default):
    try: return json.loads(Path(path).read_text(encoding='utf-8'))
    except FileNotFoundError: return default
    except (ValueError, OSError):
        # Preserve a damaged file for recovery instead of overwriting it silently.
        p = Path(path)
        if p.exists(): p.rename(p.with_suffix(f'.damaged-{int(time.time())}.json'))
        return default


class Blob(ctypes.Structure):
    _fields_ = [('cbData', wintypes.DWORD), ('pbData', ctypes.POINTER(ctypes.c_byte))]


def protect(text, decrypt=False):
    if not text: return ''
    raw = base64.b64decode(text) if decrypt else text.encode('utf-8')
    buffer = ctypes.create_string_buffer(raw)
    src = Blob(len(raw), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte))); dst = Blob()
    api = ctypes.windll.crypt32.CryptUnprotectData if decrypt else ctypes.windll.crypt32.CryptProtectData
    if not api(ctypes.byref(src), None, None, None, None, 1, ctypes.byref(dst)):
        raise OSError('Windows 无法解密此密钥，请在当前账户重新填写')
    try:
        result = ctypes.string_at(dst.pbData, dst.cbData)
        return result.decode('utf-8') if decrypt else base64.b64encode(result).decode('ascii')
    finally:
        ctypes.windll.kernel32.LocalFree(dst.pbData)


DEFAULT_SETTINGS = {
    'main_hotkey': 'Ctrl+Shift+F10', 'overlay_hotkey': 'Ctrl+Shift+F11',
    'capture_hotkey': 'Ctrl+Shift+F9', 'coach_hotkey': 'Ctrl+Shift+F8',
    'overlay_opacity': 0.88, 'overlay_scale': 100, 'floating_size': 56, 'reduce_motion': False,
    'capture_interval': 1.5, 'stable_frames': 2, 'recognition_threshold': 0.92,
    'opening_stable_frames': 2, 'shop_stable_frames': 2,
    'auto_apply': False, 'opening_auto_confirm': True, 'battle_enabled': True, 'capture_profiles': [], 'capture_profile': '',
    'ai_profiles': [], 'ai_profile': '', 'ai_enabled': False, 'ai_auto': True,
    'ai_on_change': False, 'ai_timeout': 20, 'ai_min_interval': 12,
    'ai_limit': 40, 'database_override': '', 'client': '官方 PC 端',
    'disabled_guide_routes':[],
}


class Storage:
    def __init__(self):
        self.root = user_dir()
        saved = read_json(self.root / 'settings.json', {})
        self.settings = {**DEFAULT_SETTINGS, **saved}
        # Existing profiles inherit their former shared timing until edited separately.
        for key in ('opening_stable_frames', 'shop_stable_frames'):
            value = saved.get(key, saved.get('stable_frames', DEFAULT_SETTINGS[key]))
            try: value = int(value)
            except (ValueError, TypeError, OverflowError): value = DEFAULT_SETTINGS[key]
            self.settings[key] = max(1, min(6, value))
        # Online analysis and continuous capture require a deliberate start each launch.
        self.settings['ai_enabled'] = False
        self.teams = read_json(self.root / 'teams.json', [])
        self.guides = read_json(self.root / 'guides.json', [])
        self.tracking = read_json(self.root / 'tracking.json', [])

    def save_settings(self): atomic_json(self.root / 'settings.json', self.settings)
    def save_state(self, state): atomic_json(self.root / 'session.json', state)
    def save_teams(self): atomic_json(self.root / 'teams.json', self.teams)
    def save_guides(self): atomic_json(self.root / 'guides.json', self.guides)
    def save_tracking(self,items):
        self.tracking=items
        atomic_json(self.root / 'tracking.json',items)

    def save_key(self, profile_id, value):
        path = self.root / 'secrets.json'; secrets = read_json(path, {})
        secrets[profile_id] = protect(value); atomic_json(path, secrets)

    def get_key(self, profile_id):
        value = read_json(self.root / 'secrets.json', {}).get(profile_id, '')
        return protect(value, decrypt=True) if value else ''

    def delete_key(self,profile_id):
        path=self.root/'secrets.json';secrets=read_json(path,{})
        if profile_id in secrets:
            secrets.pop(profile_id);atomic_json(path,secrets)

    def archive_session(self, state):
        atomic_json(self.root / 'sessions' / (state['session_id'] + '.json'), state)

    def export_team(self, path, state, version):
        # Explicit allowlist excludes keys, endpoints, window titles and capture profiles.
        fields = ('schema', 'name', 'units', 'inventory', 'target', 'stacks', 'ursas_fixed',
                  'ursas_temporary', 'strategies', 'notes')
        atomic_json(path, {'format': 'garrison-team', 'version': version,
                           'state': {k: state[k] for k in fields}})
