"""Generate a PyInstaller version-info file from pyproject.toml metadata."""

import argparse
import re
import sys
from pathlib import Path

from packaging.version import Version

REPO_ROOT = Path(__file__).resolve().parents[3]

VERSION_INFO_TEMPLATE = """\
# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({major}, {minor}, {patch}, 0),
    prodvers=({major}, {minor}, {patch}, 0),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '040904B0',
        [
          StringStruct('CompanyName', 'BUZZARDGTA'),
          StringStruct('FileDescription', 'AMD Adrenalin Control'),
          StringStruct('FileVersion', '{version}'),
          StringStruct('InternalName', 'amd-adrenalin-control'),
          StringStruct('OriginalFilename', 'amd-adrenalin-control.exe'),
          StringStruct('ProductName', 'AMD Adrenalin Control'),
          StringStruct('ProductVersion', '{version}')
        ]
      )
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""

VERSION_PATTERN = re.compile(r'^version\s*=\s*"(?P<version>[0-9]+\.[0-9]+\.[0-9]+)"\s*$', re.MULTILINE)


def read_version(pyproject_path: Path) -> Version:
    """Read the project version string from pyproject.toml."""
    content = pyproject_path.read_text(encoding="utf-8")
    match = VERSION_PATTERN.search(content)
    if not match:
        print(f"ERROR: Could not find a valid version in {pyproject_path}", file=sys.stderr)
        sys.exit(1)
    return Version(match.group("version"))


def generate(version: Version, output_path: Path) -> None:
    """Write a PyInstaller version-info file for the given version."""
    content = VERSION_INFO_TEMPLATE.format(
        major=version.major,
        minor=version.minor,
        patch=version.micro,
        version=version,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    print(f"Generated version info for v{version} -> {output_path}")


def main() -> None:
    """Parse arguments and generate the version-info file."""
    parser = argparse.ArgumentParser(description="Generate PyInstaller version-info from pyproject.toml")
    parser.add_argument(
        "-o", "--output",
        type=Path,
        default=REPO_ROOT / ".github" / "workflows" / "version_info.txt",
        help="Output path for the generated version-info file",
    )
    args = parser.parse_args()

    pyproject_path = REPO_ROOT / "pyproject.toml"
    version = read_version(pyproject_path)
    generate(version, args.output)


if __name__ == "__main__":
    main()
