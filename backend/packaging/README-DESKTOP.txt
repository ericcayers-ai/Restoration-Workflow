Restoration Workflow — desktop package
======================================

After installing (Windows Setup / macOS DMG / Linux AppImage):

1. Launch Restoration Workflow from your Start Menu, Applications folder,
   or by running the AppImage.
2. Your browser opens the app at http://127.0.0.1:8765

No Python install is required. A GPU is optional — CPU works, just slower.
Model weights download only when you use a model (Settings → Manage Downloads,
or the first Simple Mode run).

macOS note: this build is unsigned. First launch may require right-click → Open,
or: xattr -cr "/Applications/Restoration Workflow.app"

Linux note: chmod +x the AppImage if your browser cleared the executable bit.
