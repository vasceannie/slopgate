# Slopgate dashboard

React + Vite UI for Slopgate hook traces and config. See the root [README](../README.md#dashboard) for how to run it.

Quick reference:

```bash
# Production-style (canvas + API on :18834)
python3 scripts/build-standalone.py --logs-dir ~/.config/slopgate/logs
python3 scripts/serve.py

# Frontend dev only (:8080, mock or file drop)
npm install && npm run dev
```
