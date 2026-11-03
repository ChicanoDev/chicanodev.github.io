"""Hardware-free stand-ins for the microphone, speakers and keyboard/screen."""
import numpy as np

import recorder


def tone(seconds=2.0, rate=48000, freq=440, amp=0.4):
    t = np.arange(int(seconds * rate)) / rate
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)


class FakeCapture:
    def __init__(self, samples, rate, error=None):
        self._samples, self.rate, self.error, self.elapsed = samples, rate, error, 0.0

    def stop(self):
        return self._samples, self.rate


class FakeBackend:
    """`recordings` are served in order; an Exception instance in the list is raised from start()."""

    def __init__(self, recordings=None, rate=48000, devices=None):
        self.recordings = list(recordings or [])
        self.rate, self.started, self.played, self.stopped_playback = rate, 0, [], 0
        self.capture_error = None
        self.devices = devices or [recorder.Device(1, "Fake Mic", float(rate), True)]

    def list_devices(self):
        return self.devices

    def resolve(self, spec=None):
        if spec is None:
            return self.devices[0]
        match = [d for d in self.devices if str(spec) in (str(d.id), d.name)]
        if not match:
            raise recorder.MicError(f"--device {spec!r} is not a microphone.")
        return match[0]

    def start(self, device):
        self.started += 1
        item = self.recordings.pop(0) if self.recordings else tone()
        if isinstance(item, Exception):
            raise item
        return FakeCapture(item, self.rate, self.capture_error)

    def play(self, path):
        self.played.append(path)

    def stop_playback(self):
        self.stopped_playback += 1


class FakeUI:
    """Keys come from a script; every screen is recorded in `events` as (name, payload)."""

    def __init__(self, keys, choose=None, confirms=None):
        self.keys, self.choices, self.confirms, self.events = list(keys), list(choose or []), list(confirms or []), []
        self.stop_interrupt = None  # set to an exception class to raise it while "recording"

    def log(self, name, payload=None):
        self.events.append((name, payload))

    def named(self, name):
        return [p for n, p in self.events if n == name]

    def notes(self):
        return " | ".join(text for kind, text in self.named("note"))

    def key(self, allowed=()):
        if not self.keys:
            raise EOFError
        key = self.keys.pop(0)
        self.log("key", key)
        return key

    def flush_input(self):
        pass

    def overview(self, info):
        self.log("overview", info)

    def segment(self, info):
        self.log("segment", info)

    def record_wait(self, capture):
        self.log("recording")
        if self.stop_interrupt:
            raise self.stop_interrupt
        self.key()  # the Enter that stops recording

    def review(self, info):
        self.log("review", info)

    def note(self, text, kind="info"):
        self.log("note", (kind, text))

    def choose(self, info):
        self.log("choose", info)
        if not self.choices:
            raise EOFError
        return self.choices.pop(0)

    def confirm(self, question):
        self.log("confirm", question)
        return self.confirms.pop(0) if self.confirms else False

    def complete(self, info):
        self.log("complete", info)
