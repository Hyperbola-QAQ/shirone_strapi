# Obsidian 写作与 Strapi

在 Obsidian 打开并保存笔记后，通过命令面板使用：

- **检查当前文章**：分别比较本地内容与 Strapi 草稿、已发布版本。
- **推送当前文章到 Strapi**：写入 Strapi 草稿；已有草稿内容不同时会提示确认。
  已发布版本不变，需要在 Strapi 后台另行发布。

插件安装于 Vault 的第三方插件目录。若未加载，在 Obsidian「设置 → 第三方插件」
启用 **Shirone Strapi Publisher**；受限模式开启时，按界面提示处理。

笔记至少需要 `title`；网站公开文章还需要有效的 `published` 日期。例如：

```yaml
---
title: 我的文章
published: 2026-11-15
draft: false
tags: [技术]
---
```

当 Strapi 自上次推送后发生变化时会提示；检查后本地、线上版本发生变化时，
推送会停止。上次请求结果不确定时也会停止，请先核对后台。比较和写入之间没有原子
条件写入，避免两个人同时修改同一篇文章。移动笔记可能改变按路径生成的 slug；
需要保留原地址时，在 frontmatter 显式设置 `slug`。

本地图片、Obsidian 双链与 MDX 还不支持自动转换，推送会提示并停止；检查操作
仍可使用。文章正文和 frontmatter 不会被插件改写。

## 接入已有 Strapi

1. 按独立插件仓库的安装说明，将插件安装到目标 Vault 并启用。[插件安装说明](https://github.com/Hyperbola-QAQ/shirone_strapi_obsidian#安装)
2. 建立指向项目 Strapi 的私有隧道。默认本机入口为 `http://127.0.0.1:13370`，可通过 `STRAPI_URL` 指定其他本机端口。
3. 管理员从主仓库根目录运行 `node cms/scripts/setup-obsidian-token.cjs`。工具默认从 `~/.local/state/shirone-strapi/admin-stage/admin.json` 读取含 `email` 和 `password` 的凭据，也可通过 `SHIRONE_ADMIN_FILE` 指定已有凭据文件。文件须由当前用户持有，权限为 `0600`。
4. 工具将限定为文章读取、创建和更新权限的令牌写入 `~/.local/state/shirone-obsidian/`。若设置 `SHIRONE_OBSIDIAN_STATE`，插件与工具应使用同一状态目录。打开一篇已保存的 Markdown 笔记，先执行「检查当前文章」核对目标草稿。
