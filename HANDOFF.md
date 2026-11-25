# Marketing engine v0.1 handover
Start with README.zh-CN.md and docs/STAGES.md. The verified deliverable is a local rendering pipeline with an English fixed-script sample at examples/demo/video.mp4. 31 offline/mocked tests passed during development. No live brand campaign was launched. The last-run report describes demo jobs only.
## Production gates
Inspect the actual Windows installation and its state before restoring anything. Never overwrite a newer brand configuration or publishing database with this snapshot. See docs/NEEDED-FROM-YOU.md for onboarding and docs/PLATFORM-NOTES.md for platform access. Replace machine-specific paths in config/machine.json when relocating. Verify local Ollama, commercial-use media, voice, target accounts and a real brand sample. YouTube and Instagram require live account validation. TikTok and Xiaohongshu currently produce manual packages. Confirm leads through tagged traffic and actual CRM data.
## Scheduling
The ChatGPT marketing check was paused. Check Windows Task Scheduler separately. Use only one production worker. Reconcile unknown uploads in the target account before retrying. Account tokens and the live database are intentionally excluded.
## GitHub delivery
In a freshly extracted copy, run Publish-GitHub.ps1 with Git and authenticated GitHub CLI. It requires the owner SiyaoGui and creates a private repository local-marketing-engine. No separate conversation is required. See Notion for handover status.
