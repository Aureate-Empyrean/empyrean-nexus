// Explicit build-time vendoring; no runtime dependency on a sibling checkout.
// Modules that implement the navigation contract keep a byte-identical copy of the SDK.
import {readFile, writeFile, mkdir} from 'node:fs/promises';
const source = new URL('../frontend/navigation-protocol.js', import.meta.url);
const targets = ['mnemosyne', 'meridian'].map(module =>
  new URL(`../../${module}/frontend/vendor/nexus-navigation.js`, import.meta.url));
const contents = await readFile(source);
for (const target of targets) {
  if (process.argv.includes('--check')) {
    if (!contents.equals(await readFile(target))) throw Error(`${target.pathname} is out of sync`);
  } else {
    await mkdir(new URL('.', target), {recursive:true});
    await writeFile(target, contents);
  }
}
