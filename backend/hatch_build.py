"""Builds the Review UI and puts it, with the Changelog, inside the package, so framewise
installs as one package that needs no Node.js."""

import shutil
import subprocess
from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

UI_BUILD = Path("frontend") / "dist" / "frontend" / "browser"


class ReviewUiBuildHook(BuildHookInterface):
    def initialize(self, version: str, build_data: dict) -> None:
        if version == "editable":
            return
        repo = Path(self.root).parent
        frontend = repo / "frontend"
        if not (frontend / "angular.json").is_file():
            # Building the wheel from the sdist, which carries both already.
            return
        npm = shutil.which("npm")
        if npm is None:
            raise RuntimeError("building framewise needs Node.js, to build the Review UI")
        subprocess.run([npm, "ci"], cwd=frontend, check=True)
        subprocess.run([npm, "exec", "--", "ng", "build"], cwd=frontend, check=True)

        package = "framewise" if self.target_name == "wheel" else "src/framewise"
        build_data["force_include"][str(repo / UI_BUILD)] = f"{package}/review_ui"
        build_data["force_include"][str(repo / "CHANGELOG.md")] = f"{package}/CHANGELOG.md"
