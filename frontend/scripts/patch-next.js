const fs = require('fs');
const path = require('path');

const targetFile = path.join(__dirname, '..', 'node_modules', 'next', 'dist', 'build', 'index.js');
if (fs.existsSync(targetFile)) {
  let content = fs.readFileSync(targetFile, 'utf8');

  // Fix 1: Ensure customAppGetInitialPropsPromise checks pagesDir in pure App Router projects
  if (content.includes('const customAppGetInitialPropsPromise = pagesStaticWorkers.hasCustomGetInitialProps')) {
    content = content.replace(
      'const customAppGetInitialPropsPromise = pagesStaticWorkers.hasCustomGetInitialProps',
      'const customAppGetInitialPropsPromise = pagesDir ? pagesStaticWorkers.hasCustomGetInitialProps'
    );
    content = content.replace(
      'checkingApp: true\n                });',
      'checkingApp: true\n                }) : Promise.resolve(false);'
    );
  }

  // Fix 2: Ensure namedExportsPromise checks pagesDir in pure App Router projects
  if (content.includes('const namedExportsPromise = pagesStaticWorkers.getDefinedNamedExports')) {
    content = content.replace(
      'const namedExportsPromise = pagesStaticWorkers.getDefinedNamedExports',
      'const namedExportsPromise = pagesDir ? pagesStaticWorkers.getDefinedNamedExports'
    );
    content = content.replace(
      'runtimeEnvConfig\n                });',
      'runtimeEnvConfig\n                }) : Promise.resolve([]);'
    );
  }

  fs.writeFileSync(targetFile, content, 'utf8');
  console.log('[patch-next] Successfully patched Next.js pure App Router build check.');
}
