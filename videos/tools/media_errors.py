"""The failures a user can fix; the CLI prints these as messages instead of tracebacks."""
import compose
import narration
import pipeline
import retime

EXPECTED = (narration.MissingTakes, narration.AmbiguousTake, narration.BadAudio, retime.SyncError,
            pipeline.SyncFailed, compose.MediaError, ValueError, FileNotFoundError)
