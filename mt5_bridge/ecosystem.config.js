// PM2 ecosystem config — MT5 Bridge
// Run this on the Windows machine where MetaTrader 5 is installed.
//
// Usage:
//   pm2 start ecosystem.config.js
//   pm2 stop edgetrade-bridge
//   pm2 logs edgetrade-bridge
//   pm2 save && pm2 startup   ← auto-start on Windows boot
//
// Prerequisites on the Windows machine:
//   1. Python 3.10+ installed
//   2. cd mt5_bridge && python -m venv venv
//   3. venv\Scripts\pip install -r requirements.txt
//   4. Copy .env.example → .env and fill in MT5 credentials

const isWin = process.platform === 'win32';
const python = isWin ? 'venv\\Scripts\\python.exe' : 'venv/bin/python';

module.exports = {
  apps: [
    {
      name: "edgetrade-bridge",
      script: python,
      args: "bridge.py",
      interpreter: "none",             // execute Python binary directly, not via Node
      cwd: __dirname,                  // always run from mt5_bridge/

      // --- process model ---
      instances: 1,
      exec_mode: "fork",
      autorestart: true,
      watch: false,
      max_memory_restart: "256M",

      // --- restart policy ---
      // Bridge may restart briefly if MT5 terminal isn't open yet at boot.
      // Backoff: keep retrying until MT5 comes up.
      restart_delay: 5000,            // wait 5s between restarts
      max_restarts: 20,               // allow many restarts (MT5 may take time to open)
      min_uptime: "15s",

      // --- logs ---
      out_file: "logs/bridge.out.log",
      error_file: "logs/bridge.error.log",
      merge_logs: true,
      log_date_format: "YYYY-MM-DD HH:mm:ss Z",

      // --- environment ---
      // These override / supplement the .env file in this directory.
      env_production: {
        PYTHONUNBUFFERED: "1",
        BRIDGE_HOST: "0.0.0.0",
        BRIDGE_PORT: "9000",
      },
    },
  ],
};
