import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { createServer } from 'node:http';
import { mkdtemp, mkdir, readFile, rm, stat, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { once } from 'node:events';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

test('token setup is scoped, private and idempotent', async t => {
  const temp = await mkdtemp(path.join(os.tmpdir(), 'shirone-token-test-'));
  t.after(() => rm(temp, { recursive: true, force: true }));
  const admin = path.join(temp, 'admin.json');
  await writeFile(admin, JSON.stringify({ email: 'test@example.invalid', password: 'fixture' }), { mode: 0o600 });
  const state = path.join(temp, 'state');
  await mkdir(state, { mode: 0o700 });
  let created = null, count = 0;
  const server = createServer(async (req, res) => {
    let body = ''; for await (const part of req) body += part;
    res.setHeader('Content-Type', 'application/json');
    if (req.url === '/admin/login') return res.end(JSON.stringify({ data: { token: 'admin-fixture', user: { id: 1 } } }));
    if (req.url === '/admin/api-tokens' && req.method === 'GET') return res.end(JSON.stringify({ data: created ? [created] : [] }));
    if (req.url === '/admin/api-tokens' && req.method === 'POST') {
      count++; created = { ...JSON.parse(body), id: 42, accessKey: 'writer-fixture' };
      return res.end(JSON.stringify({ data: created }));
    }
    if (req.url === '/admin/api-tokens/42') return res.end(JSON.stringify({ data: created }));
    if (req.url.startsWith('/api/posts?')) return res.end(JSON.stringify({ data: [] }));
    res.statusCode = 404; res.end('{}');
  });
  server.listen(0, '127.0.0.1'); await once(server, 'listening');
  t.after(() => server.close());
  async function run() {
    const child = spawn(process.execPath, [fileURLToPath(new URL('../scripts/setup-obsidian-token.cjs', import.meta.url))], {
      env: { ...process.env, STRAPI_URL: `http://127.0.0.1:${server.address().port}`, SHIRONE_ADMIN_FILE: admin, SHIRONE_OBSIDIAN_STATE: state } });
    let output = ''; child.stdout.on('data', part => { output += part; }); child.stderr.on('data', part => { output += part; });
    const [code] = await once(child, 'exit');
    assert.equal(code, 0, output); assert.doesNotMatch(output, /fixture/);
  }
  await run(); await run();
  assert.equal(count, 1);
  assert.equal((await stat(path.join(state, 'token'))).mode & 0o777, 0o600);
  assert.equal((await readFile(path.join(state, 'token'), 'utf8')).trim(), 'writer-fixture');
  assert.deepEqual(created.permissions, ['api::post.post.find', 'api::post.post.findOne', 'api::post.post.create', 'api::post.post.update']);
});
