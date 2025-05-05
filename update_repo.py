import logging
import subprocess
import requests
import shutil
import os
import sys
import re
import zipfile

from enum import IntEnum
from pathlib import Path
from xml.etree import ElementTree
from requests import HTTPError

logging.basicConfig(stream=sys.stdout, level=logging.INFO)

REPO_DIR = Path("repo")
ADDONS_LIST_FILE = "addons_list.txt"


class AddonStatus(IntEnum):
    ERROR = -1
    NOT_INSTALLED = 0
    UP_TO_DATE = 1
    NEEDS_UPDATE = 2


class Addon:
    def __init__(self, name: str):
        self.name = name

    def load(self) -> bool:
        match = re.match(r"^([a-zA-Z0-9._-]+)-(\d+(?:\.\d+)*)\.zip$", self.name)
        if not match:
            return False

        self.id = match.group(1)
        self.version = match.group(2)

        return True

    def check(self) -> AddonStatus:
        path = Path(os.path.join("repo", self.id, "addon.xml"))
        if not path.exists():
            return AddonStatus.NOT_INSTALLED

        tree = ElementTree.parse(path)
        root = tree.getroot()
        version: str = root.attrib.get("version")

        if not version or not re.match(r"^\d+\.\d+\.\d+$", version):
            return AddonStatus.ERROR

        return (
            AddonStatus.UP_TO_DATE
            if self.version == version
            else AddonStatus.NEEDS_UPDATE
        )


def download(url: str, path: str) -> bool:
    logging.info(f"Downloading from '{url}'...")
    try:
        response = requests.get(url)
        response.raise_for_status()

        with open(path, "wb") as f:
            f.write(response.content)

        return True
    except ValueError:
        logging.error(f"Invalid URL: '{url}'")
    except HTTPError as e:
        logging.error(f"Download failed: {e}")

    return False


def extract(path: str | Path):
    logging.info(f"Extracting zip '{path}'...")
    try:
        with zipfile.ZipFile(path, "r") as zip_ref:
            zip_ref.extractall(REPO_DIR)
            return True
    except Exception:
        logging.error(f"Extracting failed: '{path}'")
    return False


def read_addons() -> list[str] | None:
    try:
        with open(ADDONS_LIST_FILE, "r") as f:
            urls = [line.strip() for line in f if line.strip()]
        return urls
    except OSError:
        logging.error("Could not read addons")
    return None


def run_update() -> bool:
    download_links = read_addons()
    if not download_links:
        return False

    for download_link in download_links:
        filename = download_link.split("/")[-1]
        zip_path = REPO_DIR / filename

        addon = Addon(filename)
        if not addon.load():
            return False

        addon_status = addon.check()
        if addon_status == AddonStatus.ERROR:
            return False

        if addon_status == AddonStatus.UP_TO_DATE:
            logging.info(f"Addon '{addon.id}' is up to date. Skipping...")
            continue

        if addon_status == AddonStatus.NEEDS_UPDATE:
            # delete old version
            target_path = REPO_DIR / addon.id
            if target_path.exists():
                shutil.rmtree(target_path)

        if not download(download_link, zip_path):
            return False

        if not extract(zip_path):
            return False

        zip_path.unlink()

        logging.info(f"Succesfully processed: '{filename}'")

    logging.info(f"All addons from '{ADDONS_LIST_FILE}' updated!")
    return True


def cleanup():
    logging.info("Addons repository update failed!")
    subprocess.run(["git", "reset", "--hard"], check=True)
    subprocess.run(["git", "clean", "-fd"], check=True)


if __name__ == "__main__":
    # Ensure the repo folder exists
    REPO_DIR.mkdir(exist_ok=True)

    if not run_update():
        cleanup()
        sys.exit(1)

    logging.info("Updating submodule addons...")
    subprocess.run(["git", "submodule", "update", "--remote"], check=True)
    logging.info("All addons were successfully updated!")

    logging.info("Don't forget to push actual changes!")
