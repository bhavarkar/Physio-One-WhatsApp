/**
 * Post-install patch for Next.js 14.2.x pure App Router static worker and Windows filesystem locks.
 *
 * Upstream Issues Addressed:
 * 1. Pure App Router Worker Bug (Next.js 14.2.0 - 14.2.35):
 *    In projects using solely `src/app/` without a `pages/` directory, `pagesDir` is undefined.
 *    `next/dist/build/index.js` unconditionally queried `pagesStaticWorkers.hasCustomGetInitialProps`
 *    and `pagesStaticWorkers.getDefinedNamedExports`, causing `PageNotFoundError: Cannot find module for page: /_document`.
 *    Resolved by conditioning those calls on `pagesDir ? ... : fallback`.
 *
 * 2. Windows Filesystem / OneDrive Directory Lock on Temp Export Cleanup (Next.js on Win32):
 *    In `next/dist/build/index.js` (line ~2032) and `next/dist/export/index.js` (line ~254),
 *    `_fs.promises.rm(exportOptions.outdir, { recursive: true, force: true })`
 *    encounters transient `EPERM: operation not permitted, rmdir` when background file indexers
 *    (such as OneDrive on Windows) momentarily hold directory handles on `.next/export`.
 *    Resolved by providing `maxRetries: 10, retryDelay: 200` and catching transient EPERM on win32.
 *
 * Safety & Compatibility:
 * - Version-guarded to Next.js 14.2.x. If a different major version is detected or the code is already
 *   patched/refactored upstream, this script logs an informational message and exits cleanly without error.
 */

const fs = require('fs');
const path = require('path');

function patchNext() {
  const nextPkgPath = path.join(__dirname, '..', 'node_modules', 'next', 'package.json');
  if (!fs.existsSync(nextPkgPath)) {
    console.log('[patch-next] Next.js not found in node_modules, skipping patch.');
    return;
  }

  try {
    const nextPkg = JSON.parse(fs.readFileSync(nextPkgPath, 'utf8'));
    const version = nextPkg.version || '';
    if (!version.startsWith('14.2.')) {
      console.log(`[patch-next] Next.js version ${version} is not in 14.2.x range; skipping patch.`);
      return;
    }

    // 1. Patch build/index.js
    const buildIndexFile = path.join(__dirname, '..', 'node_modules', 'next', 'dist', 'build', 'index.js');
    if (fs.existsSync(buildIndexFile)) {
      let content = fs.readFileSync(buildIndexFile, 'utf8');
      let modified = false;

      // Fix pure App Router check
      if (content.includes('const customAppGetInitialPropsPromise = pagesStaticWorkers.hasCustomGetInitialProps')) {
        content = content.replace(
          'const customAppGetInitialPropsPromise = pagesStaticWorkers.hasCustomGetInitialProps',
          'const customAppGetInitialPropsPromise = pagesDir ? pagesStaticWorkers.hasCustomGetInitialProps'
        );
        content = content.replace(
          'checkingApp: true\n                });',
          'checkingApp: true\n                }) : Promise.resolve(false);'
        );
        modified = true;
      }

      if (content.includes('const namedExportsPromise = pagesStaticWorkers.getDefinedNamedExports')) {
        content = content.replace(
          'const namedExportsPromise = pagesStaticWorkers.getDefinedNamedExports',
          'const namedExportsPromise = pagesDir ? pagesStaticWorkers.getDefinedNamedExports'
        );
        content = content.replace(
          'runtimeEnvConfig\n                });',
          'runtimeEnvConfig\n                }) : Promise.resolve([]);'
        );
        modified = true;
      }

      // Fix temp export rm in build/index.js
      const targetExportRm = 'await _fs.promises.rm(exportOptions.outdir, {\n                        recursive: true,\n                        force: true\n                    });';
      const replacementExportRm = 'await _fs.promises.rm(exportOptions.outdir, {\n                        recursive: true,\n                        force: true,\n                        maxRetries: 10,\n                        retryDelay: 200\n                    }).catch((err) => { if (process.platform === "win32" && err.code === "EPERM") { /* safe ignore on transient lock */ } else { throw err; } });';

      if (content.includes(targetExportRm)) {
        content = content.replace(targetExportRm, replacementExportRm);
        modified = true;
      }

      if (modified) {
        fs.writeFileSync(buildIndexFile, content, 'utf8');
        console.log('[patch-next] Successfully patched build/index.js.');
      } else {
        console.log('[patch-next] build/index.js already up to date.');
      }
    }

    // 2. Patch export/index.js
    const exportIndexFile = path.join(__dirname, '..', 'node_modules', 'next', 'dist', 'export', 'index.js');
    if (fs.existsSync(exportIndexFile)) {
      let content = fs.readFileSync(exportIndexFile, 'utf8');
      const targetPattern = 'await _fs.promises.rm(outDir, {\n        recursive: true,\n        force: true\n    });';
      const replacement = 'await _fs.promises.rm(outDir, {\n        recursive: true,\n        force: true,\n        maxRetries: 10,\n        retryDelay: 200\n    }).catch((err) => { if (process.platform === "win32" && err.code === "EPERM") { /* safe ignore on transient lock */ } else { throw err; } });';

      if (content.includes(targetPattern)) {
        content = content.replace(targetPattern, replacement);
        fs.writeFileSync(exportIndexFile, content, 'utf8');
        console.log('[patch-next] Successfully patched export/index.js.');
      }
    }
  } catch (err) {
    console.warn('[patch-next] Warning: Non-fatal error while evaluating Next.js patch:', err.message);
  }
}

patchNext();
