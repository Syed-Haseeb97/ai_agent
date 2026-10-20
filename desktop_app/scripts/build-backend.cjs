const { spawnSync } = require('node:child_process');
const path = require('node:path');

const python = process.env.RUBY_BUILD_PYTHON || process.env.PYTHON || (process.platform === 'win32' ? 'python' : 'python3');
const args = [
  '-m', 'PyInstaller', '--noconfirm', '--clean', '--onedir', '--name', 'ruby-backend',
  '--distpath', 'backend-dist', '--workpath', '.pyinstaller-work', '--specpath', '.pyinstaller-work', '--paths', '..',
  '--collect-submodules', 'uvicorn.protocols', '--collect-submodules', 'uvicorn.loops',
  '--collect-submodules', 'uvicorn.lifespan', path.join('..', 'packaging', 'ruby_backend.py'),
];
const result = spawnSync(python, args, { cwd: process.cwd(), stdio: 'inherit', windowsHide: true });
if (result.error) {
  process.stderr.write(`Could not start the Python packager: ${result.error.message}\n`);
  process.exit(1);
}
process.exit(result.status ?? 1);
