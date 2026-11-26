#!/usr/bin/env node
'use strict';
// Create a single scoped writing token through the existing private admin tunnel.
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');

const root = path.resolve(process.env.SHIRONE_OBSIDIAN_STATE || path.join(os.homedir(), '.local/state/shirone-obsidian'));
const adminFile = path.resolve(process.env.SHIRONE_ADMIN_FILE || path.join(os.homedir(), '.local/state/shirone-strapi/admin-stage/admin.json'));
const base = new URL(process.env.STRAPI_URL || 'http://127.0.0.1:13370');
if (base.protocol !== 'http:' || !['127.0.0.1', 'localhost', '[::1]'].includes(base.hostname) || base.username || base.password || base.pathname !== '/' || base.search || base.hash) throw new Error('只允许使用本机私有隧道');
const permissions = ['api::post.post.find', 'api::post.post.findOne', 'api::post.post.create', 'api::post.post.update'];
const matchesPermissions = actual => Array.isArray(actual) && actual.length === permissions.length && [...actual].sort().every((p, i) => p === [...permissions].sort()[i]);
function secure(file, directory = false) {
  const s = fs.lstatSync(file);
  if (s.isSymbolicLink() || (directory ? !s.isDirectory() : !s.isFile()) || s.uid !== process.getuid() || (s.mode & 0o077) || (!directory && s.nlink !== 1)) throw new Error('凭据文件或目录权限不安全');
}
function syncDir() { const fd = fs.openSync(root, 'r'); try { fs.fsyncSync(fd); } finally { fs.closeSync(fd); } }
function writeNew(file, value) {
  const fd = fs.openSync(file, fs.constants.O_WRONLY | fs.constants.O_CREAT | fs.constants.O_EXCL | fs.constants.O_NOFOLLOW, 0o600);
  try { fs.writeFileSync(fd, value); fs.fsyncSync(fd); } finally { fs.closeSync(fd); }
  syncDir();
}
async function request(route, { method = 'GET', token, data } = {}) {
  const response = await fetch(base.origin + route, { method, redirect: 'error', signal: AbortSignal.timeout(10000),
    headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(data ? { 'Content-Type': 'application/json' } : {}) },
    ...(data ? { body: JSON.stringify(data) } : {}) });
  if (!response.ok) throw new Error(`Strapi ${method} ${route.split('?')[0]} 返回 HTTP ${response.status}`);
  return response.json();
}
async function main() {
  fs.mkdirSync(root, { recursive: true, mode: 0o700 }); secure(root, true); secure(adminFile);
  const admin = JSON.parse(fs.readFileSync(adminFile, 'utf8'));
  if (!admin.email || !admin.password) throw new Error('管理员凭据不完整');
  const lock = path.join(root, 'token-setup.lock');
  fs.mkdirSync(lock, { mode: 0o700 }); syncDir();
  try {
    const login = await request('/admin/login', { method: 'POST', data: { email: admin.email, password: admin.password } });
    const session = login?.data?.token || login?.data?.accessToken;
    if (!session || !login?.data?.user?.id) throw new Error('管理员身份验证失败');
    const list = (await request('/admin/api-tokens', { token: session }))?.data;
    if (!Array.isArray(list)) throw new Error('无法核对令牌列表');
    const existing = list.filter(item => item.name === 'shirone-obsidian-writer');
    const tokenFile = path.join(root, 'token');
    const receipt = path.join(root, 'token.json');
    const pending = path.join(root, 'token.pending');
    if (fs.existsSync(pending)) throw new Error('上次创建令牌的结果不确定，请先人工核对');
    if (fs.existsSync(tokenFile) || fs.existsSync(receipt)) {
      secure(tokenFile); secure(receipt);
      const saved = JSON.parse(fs.readFileSync(receipt, 'utf8'));
      if (existing.length !== 1 || existing[0].id !== saved.id) throw new Error('本地令牌与 Strapi 记录不一致');
      const detail = (await request(`/admin/api-tokens/${saved.id}`, { token: session }))?.data;
      if (detail?.type !== 'custom' || !matchesPermissions(detail.permissions)) throw new Error('令牌权限已改变');
    } else {
      if (existing.length) throw new Error('已有同名令牌但本地没有凭据，停止创建');
      writeNew(pending, 'outcome-unknown\n');
      const data = (await request('/admin/api-tokens', { method: 'POST', token: session,
        data: { name: 'shirone-obsidian-writer', type: 'custom', permissions, lifespan: null } }))?.data;
      if (!data?.accessKey || !data.id || !matchesPermissions(data.permissions)) throw new Error('令牌创建结果不完整，保留待核对标记');
      writeNew(tokenFile, `${data.accessKey}\n`);
      writeNew(receipt, JSON.stringify({ id: data.id, name: data.name, permissions }));
      await request('/api/posts?status=draft&pagination[pageSize]=1', { token: data.accessKey });
      fs.unlinkSync(pending); syncDir();
    }
    console.log('Obsidian 写作令牌已就绪，凭据保存在私有状态目录。');
  } finally { fs.rmdirSync(lock); syncDir(); }
}
main().catch(error => { console.error(`令牌配置停止：${error.message}`); process.exitCode = 1; });
