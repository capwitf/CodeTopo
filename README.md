# CodeToPo

CodeToPo 是一个本地运行的代码结构分析工具。你选择项目目录和目标源码文件后，后端会构建仓库调用关系图，并结合大模型生成针对目标文件的分析说明。

## 功能

- 选择本地项目目录并点选目标文件
- 构建跨文件调用关系
- 生成 Mermaid 调用拓扑图
- 输出带行号的目标源码
- 生成 Markdown 格式的 AI 分析结果
- 支持多种模型提供商
  - DeepSeek
  - OpenAI
  - Kimi
  - Anthropic
  - GLM
  - MiniMax
  - OpenAI-Compatible

## 支持语言

- Python `.py`
- Java `.java`
- Go `.go`
- C `.c`
- C Header `.h`

## 项目结构

```text
.
├─ frontend/              # 浏览器前端
├─ core/                  # 分析服务、调用图和核心逻辑
├─ languages/             # Tree-sitter 语言解析器
├─ tests/                 # 单元测试
├─ local_api.py           # 本地 HTTP API 入口
├─ requirements.txt       # Python 依赖
└─ start_local_api.bat    # Windows 启动脚本
```

## 环境要求

- Python 3.11 或更高版本
- 可用的模型 API Key

## 安装

```powershell
python -m venv .venv
.\.venv\Scripts\pip.exe install -r .\requirements.txt
```

## 启动

启动本地后端：

```powershell
.\.venv\Scripts\python.exe .\local_api.py
```

或使用批处理脚本：

```powershell
.\start_local_api.bat
```

启动后在浏览器打开：

[http://127.0.0.1:8765/](http://127.0.0.1:8765/)

## 使用方法

1. 启动本地后端
2. 打开浏览器页面
3. 选择模型提供商并填写 API Key
4. 选择本地项目文件夹
5. 在文件列表中点击要分析的目标文件
6. 点击“开始分析”

页面会返回以下结果：

- AI 分析结果
- Mermaid 调用图
- 带行号的目标源码

## 测试

```powershell
python -m unittest discover -s tests -q
```

## 说明

- 后端默认监听 `http://127.0.0.1:8765`
- 使用 `OpenAI-Compatible` 时需要手动填写 `Base URL`
- 该项目使用 Tree-sitter 做静态解析，使用大模型生成解释性分析
- `.venv`、缓存目录和编辑器配置不建议提交到仓库

## License

MIT
