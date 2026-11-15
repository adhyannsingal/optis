"""Prepare a local open-vocabulary checkpoint. Run this explicitly with Ultralytics installed."""

from contextlib import chdir
from pathlib import Path

from ultralytics import YOLOE


if __name__ == "__main__":
    directory = Path("models").resolve()
    directory.mkdir(exist_ok=True)
    with chdir(directory):
        model = YOLOE("yoloe-26s-seg.pt")
        model.set_classes(["keyring"])
        model.save("keyring-yoloe-26s-seg.pt")
    print(directory / "keyring-yoloe-26s-seg.pt")
