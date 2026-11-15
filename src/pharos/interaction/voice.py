"""Push-to-talk adapter for xAI batch voice and local PHAROS commands."""

import json
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4


AUDIO_FILES = {"audio/webm": "voice.webm", "audio/mp4": "voice.mp4", "audio/wav": "voice.wav"}
MAX_AUDIO_BYTES = 1_000_000


def command(text):
    destination = re.fullmatch(r"(?:take me to|walk to|navigate to|start (?:the )?route to)\s+(.+)", text.strip(), re.I)
    if destination:
        query = destination[1].rstrip(".?!").strip()
        if query:
            return {"kind": "find_destination", "query": query[:200]}
    normalized = re.sub(r"[^a-z0-9 ]", "", text.lower().strip())
    if normalized in {"whats ahead", "what is ahead", "what do you see", "describe the scene"}:
        return {"kind": "scene"}
    route_commands = {
        "start route replay": {"kind": "start_route", "route_id": "standard"},
        "next replay step": {"kind": "next"},
        "pause route": {"kind": "pause"},
        "resume route": {"kind": "resume"},
        "stop route": {"kind": "stop"},
    }
    if normalized in route_commands:
        return route_commands[normalized]
    for item in ("keys", "phone", "bottle"):
        if normalized in {f"where are my {item}", f"where is my {item}", f"find my {item}", f"find {item}"}:
            return {"kind": "find", "item": item}
    return None


class VoiceError(Exception):
    pass


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
