'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const rendererSource = fs.readFileSync(path.join(__dirname, '..', 'src', 'main.jsx'), 'utf8');
const packageJson = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'package.json'), 'utf8'));

test('renderer imports createRoot from React DOM before mounting', () => {
  assert.match(rendererSource, /import\s+\{\s*createRoot\s*\}\s+from\s+['"]react-dom\/client['"]/);
  assert.match(rendererSource, /createRoot\(document\.getElementById\(['"]root['"]\)\)\.render/);
});

test('desktop development server fails instead of drifting from port 5173', () => {
  assert.match(packageJson.scripts['desktop:dev'], /vite --host 127\.0\.0\.1 --strictPort/);
});
