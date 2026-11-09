import { it } from 'node:test';
import assert from 'node:assert/strict';

// Regression: the package entry point failed to load (it re-exported a name the
// processor module does not define), so `import 'anosys-sdk-openai-agents'` threw.
it('the package entry point loads and exports the logger', async () => {
  const mod = await import('../src/index.js');
  assert.equal(typeof mod.AnosysOpenAIAgentsLogger, 'function');
  assert.equal(mod.AnosysOpenAILogger, mod.AnosysOpenAIAgentsLogger);
  assert.equal(typeof mod.AnosysHttpExporter, 'function');
});
