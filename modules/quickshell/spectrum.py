"""Feed one CAVA stream to Quickshell while the default output has audible playback."""
import signal
import subprocess
import sys

import pulsectl


def playback_output(pulse):
    sink = pulse.sink_default_get()
    if sink.mute or not any(sink.volume.values):
        return None
    for stream in pulse.sink_input_list():
        if stream.sink == sink.index and not stream.corked and not stream.mute and any(stream.volume.values):
            return sink.name
    return None


def refresh(_event):
    raise pulsectl.PulseLoopStop


def stop(child):
    if child is not None:
        child.terminate()
        try:
            child.wait(timeout=0.5)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()


def monitor(command):
    child = output = None
    with pulsectl.Pulse("Quickshell spectrum") as pulse:
        pulse.event_mask_set("server", "sink", "sink_input")
        pulse.event_callback_set(refresh)
        try:
            while True:
                selected = playback_output(pulse)
                if selected != output or (child is not None and child.poll() is not None):
                    stop(child)
                    child = subprocess.Popen(command) if selected else None
                    output = selected
                # Events drive changes. The timeout also recovers from a missed
                # event during introspection or an independently exited analyzer.
                pulse.event_listen(timeout=5)
        finally:
            stop(child)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    try:
        monitor(sys.argv[1:])
    except (pulsectl.PulseError, pulsectl.PulseDisconnected):
        sys.exit(1)  # Quickshell retries the subscription after the audio server returns.
