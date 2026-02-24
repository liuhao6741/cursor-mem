# 发布指南：GitHub 与 PyPI

## 一、推送到 GitHub

### 1. 在 GitHub 上创建新仓库

1. 打开 https://github.com/new
2. Repository name 填：`cursor-mem`
3. 选择 Public，**不要**勾选 "Add a README"（本地已有）
4. 创建后记下仓库 URL，例如：`https://github.com/YOUR_USERNAME/cursor-mem.git`

### 2. 关联远程并推送

在 **cursor-mem 项目根目录**执行（把 `YOUR_USERNAME` 换成你的 GitHub 用户名）：

```bash
cd cursor-mem

# 添加远程仓库
git remote add origin https://github.com/YOUR_USERNAME/cursor-mem.git

# 推送到 main
git push -u origin main
```

若使用 SSH：

```bash
git remote add origin git@github.com:YOUR_USERNAME/cursor-mem.git
git push -u origin main
```

### 3. 更新 pyproject.toml 中的链接（可选）

推送成功后，把 `pyproject.toml` 里的 `YOUR_USERNAME` 全部替换为你的 GitHub 用户名，然后提交并再推一次：

```bash
# 编辑 pyproject.toml 中 [project.urls] 的 YOUR_USERNAME
git add pyproject.toml && git commit -m "chore: set project URLs" && git push
```

---

## 二、发布到 PyPI

### 1. 准备 PyPI 账号与 Token

1. 注册/登录 https://pypi.org
2. 进入 Account settings → API tokens → Add API token
3. 创建 Token，Scope 选 “Entire account” 或只选 “cursor-mem” 项目
4. 复制生成的 token（形如 `pypi-...`），只显示一次

### 2. 安装构建与上传工具

```bash
pip install build twine
```

### 3. 修改作者信息（可选）

编辑 `pyproject.toml`，在 `[project]` 下可增加或修改 `authors = [{name = "你的名字", email = "your@email.com"}]`。

### 4. 构建分发包

```bash
cd cursor-mem

# 清理旧的 dist
rm -rf dist/

# 构建 sdist 和 wheel
python -m build
```

完成后 `dist/` 下会有 `cursor-mem-0.1.0.tar.gz` 和 `cursor_mem-0.1.0-py3-none-any.whl`。

### 5. 上传到 PyPI

**首次发布（正式 PyPI）：**

```bash
twine upload dist/*
```

按提示输入：
- Username: `__token__`
- Password: 粘贴你的 PyPI API token

**先传到测试 PyPI 验证：**

```bash
twine upload --repository testpypi dist/*
```

安装测试：

```bash
pip install -i https://test.pypi.org/simple/ cursor-mem
```

### 6. 发布后验证

```bash
pip install cursor-mem
cursor-mem --version
```

---

## 三、后续发版流程

1. 在 `cursor_mem/__init__.py` 和 `pyproject.toml` 中把 `version` 改为新版本（如 `0.1.1`）
2. 在 **cursor-mem 根目录**提交并打 tag：
   ```bash
   cd cursor-mem
   git add -A && git commit -m "Release v0.1.1"
   git tag v0.1.1
   git push && git push origin v0.1.1
   ```
3. 重新构建并上传：
   ```bash
   cd cursor-mem
   rm -rf dist/ && python -m build && twine upload dist/*
   ```
