// PM2 ecosystem config — MT5 Bridge
// Run this on the Windows machine where MetaTrader 5 is installed.
//
// Usage:
//   pm2 start ecosystem.config.js          ← start both processes
//   pm2 stop edgetrade-bridge              ← stop bridge
//   pm2 stop edgetrade-bridge-test         ← stop test app
//   pm2 logs edgetrade-bridge              ← bridge logs
//   pm2 logs edgetrade-bridge-test         ← test app logs
//   pm2 save && pm2 startup                ← auto-start on Windows boot
//
// Once running, open in browser:
//   http://<windows-machine-ip>:9001       ← live tick monitor
//   http://<windows-machine-ip>:9001/docs  ← Swagger API docs
//   http://<windows-machine-ip>:9001/health
//
// Prerequisites on the Windows machine:
//   1. Python 3.10+ installed
//   2. cd mt5_bridge && python -m venv venev
//   3. venev\Scripts\pip install -r requirements.txt
//   4. Copy .env.example → .env and fill in MT5 credentials

const isWin = process.platform === 'win32';
// Change 'venev' below to match whatever you named your virtualenv folder
const venvName = 'venev';
const python = isWin ? `${venvName}\\Scripts\\python.exe` : `${venvName}/bin/python`;

module.exports = {
  apps: [
    // ── 1. MT5 WebSocket bridge (bridge.py) ──────────────────────────────────
    {
      name: "edgetrade-bridge",
      script: python,
      args: "bridge.py",
      interpreter: "none",             // execute Python binary directly, not via Node
      cwd: __dirname,                  // always run from mt5_bridge/

      instances: 1,
      exec_mode: "fork",
      autorestart: true,
      watch: false,
      max_memory_restart: "256M",

      // Bridge may restart briefly if MT5 terminal isn't open yet at boot.
      restart_delay: 5000,            // wait 5s between restarts
      max_restarts: 20,               // keep retrying until MT5 comes up
      min_uptime: "15s",

      out_file: "logs/bridge.out.log",
      error_file: "logs/bridge.error.log",
      merge_logs: true,
      log_date_format: "YYYY-MM-DD HH:mm:ss Z",

      env_production: {
        PYTHONUNBUFFERED: "1",
        BRIDGE_HOST: "0.0.0.0",
        BRIDGE_PORT: "9000",
      },
    },

    // ── 2. FastAPI test / diagnostic app (test_app.py) ───────────────────────
    //    Opens at http://localhost:9001 — live tick monitor + REST endpoints.
    //    Connects to bridge on 127.0.0.1:9000 automatically.
    {
      name: "edgetrade-bridge-test",
      script: python,
      args: "test_app.py",
      interpreter: "none",
      cwd: __dirname,

      instances: 1,
      exec_mode: "fork",
      autorestart: true,
      watch: false,
      max_memory_restart: "128M",

      restart_delay: 3000,
      max_restarts: 10,
      min_uptime: "5s",

      out_file: "logs/test_app.out.log",
      error_file: "logs/test_app.error.log",
      merge_logs: true,
      log_date_format: "YYYY-MM-DD HH:mm:ss Z",

      env_production: {
        PYTHONUNBUFFERED: "1",
        BRIDGE_PORT: "9000",          // which bridge port to connect to
        TEST_PORT:   "9001",          // which port this test app listens on
      },
    },
  ],
};
