"""Push-to-talk adapter for xAI batch voice and local Optis commands."""

import json
import re
from collections import deque
from threading import Condition, Thread
from time import monotonic
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4


AUDIO_FILES = {"audio/webm": "voice.webm", "audio/mp4": "voice.mp4", "audio/wav": "voice.wav"}
MAX_AUDIO_BYTES = 1_000_000


def command(text):
    destination = re.fullmatch(r"(?:take me to|walk to|navigate to|start (?:the )?route to)\s+(.+)", text.strip(), re.I)
    if destination:
        query = re.sub(r"\s+from\s+.+$", "", destination[1].rstrip(".?!").strip(), flags=re.I)
        if query:
            return {"kind": "navigate_to", "query": query[:200]}
    normalized = re.sub(r"[^a-z0-9 ]", "", text.lower().strip())
    if normalized in {"whats ahead", "what is ahead", "what do you see", "describe the scene"}:
        return {"kind": "scene"}
    route_commands = {
        "start route replay": {"kind": "start_route", "route_id": "standard"},
        "next replay step": {"kind": "next"},
        "pause route": {"kind": "pause"},
        "resume route": {"kind": "resume"},
        "stop route": {"kind": "stop"},
        "stop navigation": {"kind": "stop"},
        "recalculate route": {"kind": "recalculate"},
        "recalculate": {"kind": "recalculate"},
    }
    if normalized in route_commands:
        return route_commands[normalized]
    choice = re.fullmatch(r"(?:choose|select|the)\s+(first|second|third|fourth|fifth|sixth|[1-6])(?:\s+(?:one|destination|result))?", normalized)
    if choice:
        return {"kind": "choose_destination", "choice": {"first": 1, "second": 2, "third": 3,
                "fourth": 4, "fifth": 5, "sixth": 6}.get(choice[1], int(choice[1]) if choice[1].isdigit() else 0)}
    for item in ("keys", "phone", "bottle"):
        if normalized in {f"where are my {item}", f"where is my {item}", f"find my {item}", f"find {item}"}:
            return {"kind": "find", "item": item}
    return None


class VoiceError(Exception):
    pass


class SpeechQueue:
    """Bounded, generation-scoped TTS work. Network I/O never holds the route lock."""

    def __init__(self, adapter):
        self.adapter = adapter
        self.condition = Condition()
        self.pending = deque()
        self.ready = deque(maxlen=3)
        self.seen = set()
        self.generation = 0
        self.error = None
        for priority, name in ((0, "urgent"), (1, "routine")):
            Thread(target=self._worker, args=(priority,), daemon=True,
                   name="optis-route-speech-" + name).start()

    def clear(self):
        with self.condition:
            self.generation += 1
            self.pending.clear()
            self.ready.clear()
            self.seen.clear()
            self.error = None
            self.condition.notify_all()

    def submit(self, cue):
        if not cue or not cue.get("speech"):
            return
        with self.condition:
            key = (cue["status"], cue["data"].get("step"), cue["speech"])
            if key in self.seen:
                return
            self.seen.add(key)
            priority = 0 if cue["status"] in {"weak_signal", "missed_turn", "detour", "stopped"} else 1
            item = (priority, monotonic(), self.generation, cue["speech"])
            self.pending.append(item)
            if len(self.pending) > 3:
                self.pending.remove(max(self.pending, key=lambda value: (value[0], -value[1])))
            self.condition.notify_all()

    def take(self):
        with self.condition:
            while self.ready and self.ready[0]["generation"] != self.generation:
                self.ready.popleft()
            return self.ready.popleft() if self.ready else None

    def status(self):
        with self.condition:
            return {"audio_error": self.error, "generation": self.generation}

    def _worker(self, priority):
        while True:
            with self.condition:
                while not any(item[0] == priority for item in self.pending):
                    self.condition.wait()
                item = min((value for value in self.pending if value[0] == priority),
                           key=lambda value: value[1])
                self.pending.remove(item)
            priority, queued, generation, text = item
            if monotonic() - queued > 15:
                continue
            adapter = self.adapter()
            if adapter is None:
                with self.condition:
                    if generation == self.generation:
                        self.error = "xAI voice is not configured; guidance remains visible."
                continue
            try:
                audio, media_type = adapter.speak(text)
                if not audio or not media_type.startswith("audio/"):
                    raise VoiceError("xAI returned empty or invalid audio.")
            except Exception as error:
                with self.condition:
                    if generation == self.generation:
                        self.error = str(error) if isinstance(error, VoiceError) else "xAI voice is unavailable."
                continue
            with self.condition:
                if generation == self.generation and monotonic() - queued <= 15:
                    self.ready.append({"generation": generation, "audio": audio,
                                       "audio_type": media_type, "text": text})
                    self.error = None


class XaiVoice:
    def __init__(self, key):
        self.key = key

    def request(self, path, content_type, body):
        request = Request("https://api.x.ai/v1/" + path, data=body, headers={
            "Authorization": "Bearer " + self.key, "Content-Type": content_type,
        })
        try:
            with urlopen(request, timeout=10) as response:
                return response.read(2_000_000), response.headers.get_content_type()
        except HTTPError as error:
            raise VoiceError(f"xAI voice returned HTTP {error.code}.") from None
        except (URLError, TimeoutError):
            raise VoiceError("Could not reach xAI voice.") from None

    def transcribe(self, audio, media_type):
        boundary = uuid4().hex
        filename = AUDIO_FILES[media_type]
        body = (
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            f'Content-Type: {media_type}\r\n\r\n'
        ).encode() + audio + f"\r\n--{boundary}--\r\n".encode()
        raw, _ = self.request("stt", "multipart/form-data; boundary=" + boundary, body)
        try:
            transcript = json.loads(raw)["text"]
            if not isinstance(transcript, str):
                raise TypeError("Expected text")
            return transcript
        except (ValueError, KeyError, TypeError):
            raise VoiceError("xAI returned an invalid transcript.") from None

    def speak(self, text):
        body = json.dumps({"text": text, "voice_id": "eve", "language": "en"}).encode()
        audio, media_type = self.request("tts", "application/json", body)
        if not media_type.startswith("audio/"):
            raise VoiceError("xAI returned an invalid audio type.")
        return audio, media_type
