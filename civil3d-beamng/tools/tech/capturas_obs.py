"""Record an explicitly selected CAD window through the official OBS WebSocket API.

Only integration code lives here; obsws-python/OBS are external dependencies.
Authentication stays in the local OBS configuration, never in the session receipt.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import logging
from pathlib import Path
import re
import time


def select_window(items, title_fragment, executable="acad.exe"):
    """Require exactly one OBS-enumerated match; never fall back to another window."""
    if not title_fragment.strip():
        raise ValueError("An explicit window title fragment is required.")
    matches = [item for item in items if item.get("itemEnabled", True)
               and title_fragment.casefold() in item["itemName"].casefold()
               and item["itemValue"].rsplit(":", 1)[-1].casefold() == executable.casefold()]
    if len(matches) != 1:
        raise ValueError(f"Expected one capture window, found {len(matches)}.")
    return matches[0]["itemValue"]


class CaptureSession:
    """One isolated OBS profile/collection with receipts and explicit restoration."""

    def __init__(self, config, directory, name):
        import obsws_python
        if not re.fullmatch(r"CDCRD-[A-Za-z0-9_-]+", name):
            raise ValueError("Use a unique CDCRD- prefixed session name.")
        self.directory = Path(directory).resolve()
        self.name = name
        self.scene = name + "-Civil3D"
        self.source = name + "-Window"
        settings = json.loads(Path(config).read_text(encoding="utf-8-sig"))
        if not settings.get("auth_required") or not settings.get("server_password"):
            raise ValueError("Authenticated local OBS WebSocket required.")
        logging.getLogger("obsws_python").setLevel(logging.WARNING)
        self.client = obsws_python.ReqClient(
            host="127.0.0.1", port=settings["server_port"],
            password=settings["server_password"], timeout=15,
        )
        self.state_path = self.directory / "obs-session.json"
        self.state = None
        if self.state_path.exists():
            self.state = json.loads(self.state_path.read_text(encoding="utf-8"))
            if self.state["session"] != name or Path(self.state["directory"]) != self.directory:
                raise ValueError("Session receipt does not match this directory/name.")

    def call(self, request, **data):
        return self.client.send(request, data or None, raw=True)

    def save_state(self):
        temporary = self.state_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.state, indent=2), encoding="utf-8")
        temporary.replace(self.state_path)

    def idle(self):
        active = [item["outputName"] for item in self.call("GetOutputList")["outputs"]
                  if item["outputActive"]]
        if active:
            raise RuntimeError(f"OBS has active outputs: {active}")

    def guard(self):
        if (self.call("GetProfileList")["currentProfileName"] != self.name
                or self.call("GetSceneCollectionList")["currentSceneCollectionName"] != self.name):
            raise RuntimeError("OBS session changed; refusing to change another profile/collection.")

    def wait_selected(self):
        # OBS can acknowledge profile/collection creation before its queued
        # frontend switch is observable. Poll reads only; never repeat creation.
        deadline = time.monotonic() + 5
        while True:
            try:
                self.guard()
                return
            except RuntimeError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(.2)

    def select_profile(self, name):
        self.call("SetCurrentProfile", profileName=name)
        deadline = time.monotonic() + 10
        while self.call("GetProfileList")["currentProfileName"] != name:
            if time.monotonic() >= deadline:
                raise TimeoutError("OBS profile selection was not confirmed.")
            time.sleep(.2)

    def wait_recording(self, active, timeout=15):
        deadline = time.monotonic() + timeout
        while True:
            status = self.call("GetRecordStatus")
            if status["outputActive"] == active:
                return status
            if time.monotonic() >= deadline:
                raise TimeoutError(f"OBS did not confirm recording active={active}.")
            time.sleep(.2)

    def prepare(self):
        if self.state is not None or self.directory.exists():
            raise ValueError("Preparation requires a new output directory and session.")
        self.idle()
        profiles = self.call("GetProfileList")
        collections = self.call("GetSceneCollectionList")
        if self.name in profiles["profiles"] or self.name in collections["sceneCollections"]:
            raise ValueError("OBS session name already exists.")
        self.directory.mkdir(parents=True)
        self.state = {"session": self.name, "directory": str(self.directory),
                      "created_utc": datetime.now(timezone.utc).isoformat(),
                      "previous_profile": profiles["currentProfileName"],
                      "previous_collection": collections["currentSceneCollectionName"],
                      "phase": "preparing", "recordings": [], "window": None}
        self.save_state()
        self.call("CreateProfile", profileName=self.name)
        self.call("CreateSceneCollection", sceneCollectionName=self.name)
        self.wait_selected()
        return self.finish_preparation()

    def finish_preparation(self):
        """Finish a known interrupted setup only after inspecting its saved phase."""
        if self.state is None or self.state["phase"] != "preparing":
            raise RuntimeError("Only an inspected preparation may be completed.")
        self.guard()
        self.idle()
        if self.scene in [item["sceneName"] for item in self.call("GetSceneList")["scenes"]]:
            raise RuntimeError("Capture scene already exists; inspect partial setup.")
        self.call("SetVideoSettings", fpsNumerator=30, fpsDenominator=1,
                  baseWidth=1920, baseHeight=1080, outputWidth=1920, outputHeight=1080)
        for category, parameter, value in [
            ("Output", "Mode", "Simple"),
            ("SimpleOutput", "RecQuality", "HQ"),
            ("SimpleOutput", "RecFormat2", "mkv"),
        ]:
            self.call("SetProfileParameter", parameterCategory=category,
                      parameterName=parameter, parameterValue=value)
        self.call("SetRecordDirectory", recordDirectory=str(self.directory))
        # SetProfileParameter persists values but does not rebuild the live
        # output handler. Reactivate this isolated profile before recording.
        self.select_profile(self.state["previous_profile"])
        self.select_profile(self.name)
        self.guard()
        # New collections may contain global audio inputs. Silence those only in
        # this collection; neither desktop audio nor a microphone is requested.
        for item in self.call("GetInputList")["inputs"]:
            if item["inputKind"] in {"wasapi_input_capture", "wasapi_output_capture"}:
                self.call("SetInputMute", inputName=item["inputName"], inputMuted=True)
        self.call("CreateScene", sceneName=self.scene)
        result = self.call("CreateInput", sceneName=self.scene, inputName=self.source,
                           inputKind="window_capture", sceneItemEnabled=False,
                           inputSettings={"cursor": False, "client_area": True,
                                          "capture_audio": False, "priority": 0})
        self.state["item_id"] = result["sceneItemId"]
        self.call("SetCurrentProgramScene", sceneName=self.scene)
        self.state["phase"] = "ready_without_target"
        self.save_state()
        return self.state

    def windows(self):
        self.guard()
        return self.call("GetInputPropertiesListPropertyItems", inputName=self.source,
                         propertyName="window")["propertyItems"]

    def target(self, title_fragment):
        self.guard()
        self.idle()
        selected = select_window(self.windows(), title_fragment)
        methods = self.call("GetInputPropertiesListPropertyItems", inputName=self.source,
                            propertyName="method")["propertyItems"]
        if not any(item["itemValue"] == 2 and item.get("itemEnabled", True) for item in methods):
            raise RuntimeError("Modern WGC capture is required for the accelerated CAD viewport.")
        self.call("SetInputSettings", inputName=self.source, overlay=True,
                  inputSettings={"window": selected, "priority": 0,
                                 "cursor": False, "capture_audio": False, "method": 2})
        self.call("SetSceneItemTransform", sceneName=self.scene,
                  sceneItemId=self.state["item_id"], sceneItemTransform={
                      "positionX": 0, "positionY": 0, "alignment": 5,
                      "boundsType": "OBS_BOUNDS_SCALE_INNER", "boundsAlignment": 0,
                      "boundsWidth": 1920, "boundsHeight": 1080,
                  })
        self.call("SetSceneItemEnabled", sceneName=self.scene,
                  sceneItemId=self.state["item_id"], sceneItemEnabled=True)
        self.state["window"] = selected
        self.state["phase"] = "target_selected"
        self.save_state()
        return selected

    def snapshot(self, name):
        self.guard()
        if not re.fullmatch(r"[A-Za-z0-9_-]+", name):
            raise ValueError("Invalid snapshot name.")
        target = self.directory / (name + ".png")
        if target.exists():
            raise FileExistsError(target)
        self.call("SaveSourceScreenshot", sourceName=self.scene, imageFormat="png",
                  imageFilePath=str(target), imageWidth=1920, imageHeight=1080)
        return str(target)

    @contextmanager
    def recording(self, label):
        self.guard()
        self.idle()
        if not re.fullmatch(r"[A-Za-z0-9_-]+", label) or not self.state.get("window"):
            raise ValueError("A named take and an explicit capture window are required.")
        if Path(self.call("GetRecordDirectory")["recordDirectory"]).resolve() != self.directory:
            raise RuntimeError("Recording directory changed.")
        self.call("SetCurrentProgramScene", sceneName=self.scene)
        self.call("SetProfileParameter", parameterCategory="Output",
                  parameterName="FilenameFormatting", parameterValue=label + "_%CCYY-%MM-%DD_%hh-%mm-%ss")
        start = time.monotonic()
        self.state["phase"] = "start_requested"
        self.save_state()
        # A timeout leaves an explicit uncertain phase; never blindly retry StartRecord.
        self.call("StartRecord")
        self.wait_recording(True)
        self.state["phase"] = "recording"
        self.save_state()
        completed = False
        try:
            yield
            completed = True
        finally:
            self.guard()
            self.state["phase"] = "stop_requested"
            self.save_state()
            stopped = self.call("StopRecord")
            self.wait_recording(False, timeout=30)
            path = Path(stopped["outputPath"]).resolve()
            if not path.is_relative_to(self.directory) or not path.is_file():
                raise RuntimeError("OBS returned a recording outside this session.")
            with path.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            self.state["recordings"].append({"label": label, "path": str(path),
                "bytes": path.stat().st_size, "sha256": digest,
                "elapsed_seconds": round(time.monotonic() - start, 3),
                "action_completed": completed, "visual_reviewed": False})
            self.state["phase"] = "stopped"
            self.save_state()

    def restore(self):
        self.guard()
        self.idle()
        self.call("SetCurrentSceneCollection", sceneCollectionName=self.state["previous_collection"])
        self.select_profile(self.state["previous_profile"])
        deadline = time.monotonic() + 10
        while self.call("GetSceneCollectionList")["currentSceneCollectionName"] != self.state["previous_collection"]:
            if time.monotonic() >= deadline:
                raise TimeoutError("OBS previous collection was not confirmed.")
            time.sleep(.2)
        self.state["phase"] = "restored"
        self.save_state()

    def close(self):
        self.client.disconnect()
