# Intelligent Customer Service

基于 LangGraph 的智能客服主流程，复用两个独立 pipeline 组件：

- `retrieve_skill`：知识库多路召回（Milvus 稠密 + BM25 稀疏 + RRF），返回父块上下文。
- `nl2sql_skill`：自然语言转只读 SQL 并可选执行，返回结果集与摘要。

项目包含 `common_core`、`retrieve_skill`、`nl2sql_skill` 三个本地组件副本，不依赖本机
外部目录，也不要求这些组件先发布到 PyPI。

## Docker 一键启动

前置条件：安装 Docker Desktop，并确保 Docker 服务已启动。

```powershell
Copy-Item .env.example .env
```

编辑 `.env`，至少填写自己的 LLM 配置：

```dotenv
LLM_BASE_URL=https://your-openai-compatible-endpoint/v1
LLM_API_KEY=your-api-key
LLM_MODEL=your-model

NL2SQL_LLM_BASE_URL=https://your-openai-compatible-endpoint/v1
NL2SQL_LLM_API_KEY=your-api-key
NL2SQL_LLM_MODEL=your-model
```

启动完整环境：

```powershell
docker compose up -d --build
docker compose ps
```

仓库推送后，GitHub Actions 会自动构建
`ghcr.io/pnj-star/intelligent-customer-service:latest`。也可以在镜像发布后直接使用：

```powershell
docker compose pull
docker compose up -d --no-build
```

首次启动会自动完成：

- 创建 MySQL 并导入 `commerce`、`rag_test` 数据。
- 创建 Milvus 的 `mushroom_knowledge` 集合并导入 371 条向量数据。
- 启动 Redis、Milvus、Attu 和智能客服 API。

首次实际执行知识库检索时，应用会下载并缓存
`BAAI/bge-small-zh-v1.5` 嵌入模型。模型保存在 Docker 卷 `hf_cache` 中，后续重启
不会重复下载。国内网络可在 `.env` 设置：

```dotenv
HF_ENDPOINT=https://hf-mirror.com
```

如果你希望完全离线启动，可提前准备 HuggingFace 缓存，或者把
`hf_cache` 卷替换为团队内部的模型缓存。

服务地址：

| 服务 | 地址 |
| --- | --- |
| 智能客服 API | `http://127.0.0.1:8000` |
| Milvus Attu | `http://127.0.0.1:8002` |
| MySQL | `127.0.0.1:3307` |
| Redis | `127.0.0.1:6380` |
| Milvus | `127.0.0.1:19531` |

健康检查：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

发送一条消息：

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/chat `
  -ContentType 'application/json' `
  -Body '{"message":"那它的价格是多少","session_id":"session-1"}'
```

## 数据是否随项目一起下载

是。以下内容已在仓库内：

- `docker/mysql/init/01_schema_and_seed.sql`：`commerce` 和 `rag_test` 的结构与数据。
- `docker/milvus/mushroom_knowledge.jsonl`：`mushroom_knowledge` 的 371 条向量种子数据。
- `docker/milvus/bootstrap_milvus.py`：首次启动时自动创建集合、索引并导入数据。

数据库和向量库不需要使用者再手工导入。删除本地卷后重新启动，会再次自动初始化：

```powershell
docker compose down -v
docker compose up -d --build
```

注意：LLM 的地址、API Key 和模型不会也不会被写入仓库。每个使用者需要填写自己的
OpenAI 兼容配置；没有有效 LLM 配置时，容器和数据库仍能启动，但聊天生成不可用。

## 目录

```text
components/                 # common_core / retrieve_skill / nl2sql_skill
config/business_config.py   # 客服话术与默认参数
src/customer_service/       # state / memory / nodes / graph / app
docker/mysql/init/          # MySQL 首次启动初始化 SQL
docker/milvus/              # Milvus 建集合、导入与种子数据
scripts/                    # 检查和导出工具
tests/                      # fake provider 单元与全链路测试
langgraph.json              # LangGraph 入口
run.py                      # FastAPI 启动入口
```

## 本地 Python 开发

推荐 Python 3.11 或 3.12：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

python -m pip install --no-deps -e .\components\common_core
python -m pip install --no-deps -e .\components\retrieve_skill
python -m pip install --no-deps -e .\components\nl2sql_skill
python -m pip install --no-deps -e .

Copy-Item .env.example .env
python run.py
```

本地运行时应先把 Docker 的 MySQL、Redis、Milvus 启动起来。`.env.example` 默认使用
`127.0.0.1` 和 Compose 映射端口；容器内启动时，Compose 会自动把这些地址覆盖为
服务名 `mysql`、`redis`、`milvus`。

## MCP 服务

```powershell
# streamable-http，默认 8001
python run_mcp.py

# stdio，供本地 MCP client 拉起
python -m customer_service.mcp
```

Windows 也可以直接运行 `start_mcp.cmd` 或 `start_api.cmd`。

## LangGraph Studio

```powershell
$env:PYTHONUTF8 = "1"
$env:PYTHONPATH = "$PWD\src;$PWD\components\common_core\src;$PWD\components\retrieve_skill\src;$PWD\components\nl2sql_skill\src"
langgraph dev --allow-blocking
```

默认地址为 `http://127.0.0.1:2024`。

## 测试

```powershell
python -B -m pytest -q -p no:cacheprovider tests
```

测试使用 fake provider，不依赖 Milvus、MySQL、Redis 或真实 LLM。

## 主流程

```text
entry -> cache -> intent(指代消解+实体回填) -> route
  chat     -> LLM 闲聊 -> finalize
  rag      -> retrieve_pipeline -> answer -> finalize
  sql      -> nl2sql_pipeline   -> answer -> finalize
  rag+sql  -> asyncio.gather(return_exceptions=True) 并行合并 -> answer -> finalize
```

追问（`needs_clarification`）直接结束本轮，下一轮消息通过
`pending_clarification` 跳过缓存检查、重新进入 `intent` 节点。

## GitHub 更新

首次初始化并绑定远程仓库：

```powershell
git init -b main
git remote add origin https://github.com/pnj-star/Intelligent-Customer-Service.git
git add .
git commit -m "Initial commit"
git push -u origin main
```

以后修改后更新：

```powershell
git add .
git commit -m "Describe the change"
git push
```

`.env`、本地模型缓存、IDE 配置和运行日志已加入 `.gitignore`，不会被上传。
