# Both launchers share a single Python/Tk runtime and dependency directory.
from pathlib import Path

project = Path(SPECPATH).parent
analysis = Analysis([str(project / "repair_mp4.py")], pathex=[str(project)])
archive = PYZ(analysis.pure)
desktop = EXE(archive, analysis.scripts, [], exclude_binaries=True,
              name="MP4 Reference Repair", console=False, upx=False)
command = EXE(archive, analysis.scripts, [], exclude_binaries=True,
              name="mp4repair", console=True, upx=False)
package = COLLECT(desktop, command, analysis.binaries, analysis.datas,
                  name="MP4 Reference Repair", upx=False)
