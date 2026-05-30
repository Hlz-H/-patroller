module.exports = {
  apps: [{
    name: 'patroller-backend',
    script: 'dist/index.js',
    cwd: __dirname,
    instances: 1,
    exec_mode: 'fork',
    env: {
      NODE_ENV: 'production',
      PORT: '3099',
    },
    error_file: '../logs/backend-error.log',
    out_file: '../logs/backend-out.log',
    merge_logs: true,
    max_restarts: 10,
    restart_delay: 3000,
    max_memory_restart: '512M',
    autorestart: true,
    watch: false,
  }],
};
