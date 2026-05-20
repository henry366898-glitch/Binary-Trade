// PM2 ecosystem config — production
// Usage:
//   pm2 start ecosystem.config.js
//   pm2 reload ecosystem.config.js   ← zero-downtime reload
//   pm2 stop edgetrade-api
//   pm2 logs edgetrade-api
//   pm2 monit

module.exports = {
  apps: [
    {
      name: "edgetrade-api",
      script: "venv/bin/python",              // use the venv Python directly
      args: "-m uvicorn app.main:app --host 0.0.0.0 --port 8010 --workers 2 --loop uvloop --http httptools",
      interpreter: "none",                    // tell PM2: not a Node script, run the binary as-is
      cwd: __dirname,                         // always run from backend/

      // --- process model ---
      instances: 1,                            // PM2 manages 1 process; uvicorn handles workers internally
      exec_mode: "fork",                       // fork mode (not cluster — uvicorn manages its own workers)
      autorestart: true,
      watch: false,                            // never watch in production
      max_memory_restart: "512M",

      // --- restart policy ---
      restart_delay: 3000,                     // wait 3s before restart
      max_restarts: 10,
      min_uptime: "10s",                       // must stay up 10s to count as a successful start

      // --- logs ---
      out_file: "logs/api.out.log",
      error_file: "logs/api.error.log",
      merge_logs: true,
      log_date_format: "YYYY-MM-DD HH:mm:ss Z",

      // --- environment ---
      
    },
  ],
};
