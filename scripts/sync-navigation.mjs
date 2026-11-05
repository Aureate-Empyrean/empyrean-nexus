// Explicit build-time vendoring; no runtime dependency on a sibling checkout.
import {readFile, writeFile, mkdir} from 'node:fs/promises';
const source = new URL('../frontend/navigation-protocol.js', import.meta.url);
const target = new URL('../../mnemosyne/frontend/vendor/nexus-navigation.js', import.meta.url);
const contents = await readFile(source);
if (process.argv.includes('--check')) {
  if (!contents.equals(await readFile(target))) throw Error('Mnemosyne navigation adapter is out of sync');
} else {
  await mkdir(new URL('.', target), {recursive:true});
  await writeFile(target, contents);
}
