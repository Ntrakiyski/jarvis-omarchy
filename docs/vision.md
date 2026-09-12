# OMA Vision

A small MIT-licensed, Omarchy-first camera companion. Python's standard library
handles local IPC and model requests; FFmpeg reads V4L2 and FFplay displays a native
window. It has no Electron/browser runtime, Python package dependency, bundled
model weights, or required GPU. The cloud model itself is proprietary; the app can
also use open-weight models served locally through compatible APIs.

Say **“OMA, look at this”** or **“What is this connector?”**. The `camera_view`
tool opens a visible preview, takes a fresh frame, asks the configured model, and
returns a timestamped observation to the conversation. Follow-up questions get
fresh images and a bounded previous observation for continuity. Screen/browser
questions continue to use the screen/browser tools.

Close the preview, press **Q/Escape** inside it, say **“stop looking”**, or mute
OMA to stop camera capture. A manually opened preview is independent until a voice
inspection takes ownership. The camera also stops on idle timeout, maximum session
duration, device/preview failure, voice process exit, or a detected Omarchy lock.
The companion checks the shell lock state every two seconds while active; failure
to establish it stops capture. Completed observations are snapshots, not continuous
awareness. A changed scene during inference is described with the original capture
time, never passed off as a new frame.

## Commands

```sh
omarchy-vision start                       # local preview, no API call
omarchy-vision inspect "What is this?"      # one image request
omarchy-vision status                      # local metadata only
omarchy-vision stop
omarchy-vision quit                        # also exit the companion
omarchy-voice vision inspect "Read the connector markings"
```

`omarchy voice vision ...` is available if the optional Omarchy command wrappers
were installed. OMA Vision also appears in the app launcher. From a checkout use
`python3 bin/omarchy-vision ...`. The companion starts automatically, and exits
after 15 seconds without an active camera. `--config /path/to/config.toml` selects
an alternative configuration. No separate enabled-at-login service is needed.

Optional `--region X Y W H` crops the image using normalized coordinates from
0 to 1000. For example, `--region 250 250 500 500` inspects the central quarter
of the zoomed view. The preview keeps its configured framing. Cropping changes the field of view;
it cannot recover unreadable detail. Image pixels are never synthesized.

## Configuration and model switching

Settings live in the `[vision]` section of the existing
`~/.config/omarchy-voice/config.toml`; all defaults are in
`share/config.example.toml`. Astra is the initial model, with low reasoning and a
768-token output limit. The observer asks for a concise answer, decisive evidence,
uncertainty, and a helpful next view. If reasoning consumes the output budget the
request fails visibly without a retry; raise the limit if needed.

The default `crop_percent = 30.0` trims 15% from each edge, retaining the central
70% of the width and height (about 1.43× digital zoom). Both the preview and model
see this framing. `sharpen = 0.4` adds gentle luminance sharpening without changing
colors or inventing detail. Set either value to `0` to disable it. Cropping trades
field of view for a larger subject on screen; it cannot recover missing detail.
An explicit `region` crop uses coordinates within this zoomed view. Stop the
camera and restart OMA after changing settings.

To switch OpenAI models, change `model`. To switch API providers or use an
open-weight local model, change `protocol`, `base_url`, `model` and any optional
provider parameters. This example targets an existing compatible local server;
replace the model value with a vision model actually loaded on that server:

```toml
[vision]
model = "your-loaded-vision-model"
protocol = "chat_completions"
base_url = "http://127.0.0.1:8000/v1"
api_key_env = ""
reasoning_effort = ""
detail = ""
```

The endpoint must implement streaming image input via Responses or Chat
Completions. Vendor-specific APIs such as a native model-server chat endpoint
need an adapter; this app does not pretend every VLM has the same API. Local
compatibility is tested against the wire contract, not every inference server.
No OpenAI credential is implicitly forwarded to a custom endpoint. If a custom
provider needs authentication, set `api_key_env` to its dedicated variable in
OMA's private `env` file. Remote endpoints require HTTPS; loopback HTTP is allowed.
Redirects are refused. Provider URLs/credentials cannot be changed by the voice tool.

After edits, run `omarchy-vision quit` and restart the voice service to reload its
configuration. Standalone CLI commands read configuration on every invocation;
an inactive companion automatically restarts for changed settings. Changes to an
active companion require stopping it first. `enabled = false` removes the camera
tool from OMA; stop an already active preview when disabling it.

## Latency and resource use

- The native MJPEG capture path copies compressed camera frames without encoding
  them again. Other V4L2 formats use FFmpeg's JPEG encoder.
- Capture keeps exactly one latest JPEG. Preview uses a separate bounded pipe;
  a stalled preview stops the camera instead of building a backlog.
- Each inspection waits for a frame captured after the request. Camera startup
  is paid once per visual session. Only explicit inspections invoke a model;
  holding the preview open does not make periodic paid calls.
- Capture retains the source JPEG; FFplay applies the default crop and sharpening
  to the preview. Only selected inspection frames are transformed and re-encoded.
  A 1920×1080 source becomes 1344×756 at the default crop, without upscaling.
  Use `image_width` to reduce upload size further while preserving aspect ratio.
- Only one inference runs at a time. Concurrent inspections return busy; no
  frame queue accumulates. Provider requests run in a killable process so camera
  stop, timeout and shutdown can cancel local processing promptly. Providers may
  still charge work already submitted after a local cancellation.
- Returned metrics include `first_text_ms`, `model_ms`, `total_ms`, image bytes,
  capture timestamp, and observation age. These do not include OMA's subsequent
  spoken output. First text may be a heading rather than a useful identification.

There is no production dollar ledger because provider prices vary. Session time,
request count and output limits bound work; these are not account billing caps.

## Privacy and lifecycle

Preview pixels and selected JPEGs stay in RAM and are not written to disk. An
inspection sends the current question, selected frame, and up to 1,200 characters
of the previous visual observation to the configured endpoint. Responses requests
use `store: false`; provider retention policies still apply. OMA's ordinary
conversation/tool logs may contain the resulting descriptions. Closing the camera
clears the companion's last frame and observation. It does not delete voice logs.

Control uses an owner-only Unix socket under OMA's private runtime directory with
same-user peer checks; there is no HTTP listener. The companion log contains
startup errors, not images or provider response bodies. Camera and model settings
are local configuration, never model-generated shell commands. Captured labels
are treated as evidence, not instructions to operate the computer.

## Development

The implementation is split into `vision.py` (tool/config/client), `vision_app.py`
(camera/preview/lifecycle), and `vision_provider.py` (small provider adapters).
Add new provider wire formats at that boundary while preserving cancellation,
freshness, bounded payloads, and the no-retry behavior. Both voice engines use the
same tool through the existing policy gate. A dry run never opens the camera.

```sh
python3 -m unittest discover -s tests -p 'test_vision.py'
```

Use `v4l2-ctl --list-devices` and `v4l2-ctl --list-formats-ext` to find the proper
device and capture profile. The default expects a V4L2 camera supporting
1920×1080 MJPEG at 30 fps; adjust it for your device. A device-in-use error requires releasing another capture
app, not killing unrelated processes. Install FFmpeg if either `ffmpeg` or `ffplay`
is missing. `omarchy-voice doctor` reports the vision configuration and dependencies.
