# 语料自动生成工具

一个基于 DeepSeek API 的自动化语料生成工具，支持大规模、高质量的对话语料生成。

## 功能特性

- 🚀 **自动化生成**：自动解析配置，生成所有组合任务（20个领域 × 8种类型 × 5种轮次 = 800个任务）
- 📊 **智能管理**：自动管理会话、token 估算、数据补齐
- 💾 **断点续传**：支持中断后继续生成，自动跳过已完成的任务
- 🔧 **模块化设计**：代码结构清晰，易于扩展和维护
- ⚙️ **灵活配置**：支持多种配置方式，适应不同需求

## 项目结构

```
corpus_generator/
├── generate_corpus.py          # 主程序入口
├── config.py                   # 主程序配置（路径、任务参数、Token估算）
├── utils.py                    # 工具函数（JSON提取、数据统计、保存）
├── requirements.txt            # Python依赖
├── .gitignore                  # Git忽略文件
├── initial_prompt.txt          # 初始提示词文件
├── client/                     # 客户端模块
│   ├── __init__.py
│   └── deepseek_client.py     # DeepSeek API客户端实现
├── command_generation/         # 命令生成模块
│   ├── __init__.py
│   ├── parser.py              # 解析生成计划、构建指令
│   └── generation_plan.txt     # 生成计划配置文件
└── output/                     # 输出目录（自动创建）
    └── {领域}/{类型}/{轮次}_round.json
```

## 快速开始

### 1. 环境准备

#### 安装依赖

```bash
pip install -r requirements.txt
```

或手动安装：

```bash
pip install requests
```

#### 获取 DeepSeek API Key

1. 访问 [DeepSeek 官网](https://www.deepseek.com/)
2. 注册/登录账号
3. 在控制台获取 API Key

#### 设置环境变量

**Linux/Mac:**
```bash
export DEEPSEEK_API_KEY='your-api-key-here'
```

**Windows (PowerShell):**
```powershell
$env:DEEPSEEK_API_KEY='your-api-key-here'
```

**Windows (CMD):**
```cmd
set DEEPSEEK_API_KEY=your-api-key-here
```

或者创建 `.env` 文件（需要安装 `python-dotenv`）：
```
DEEPSEEK_API_KEY=your-api-key-here
```

### 2. 运行脚本

```bash
cd corpus_generator
python generate_corpus.py
```

## 详细使用说明

### 工作流程

1. **初始化**：
   - 读取 `initial_prompt.txt` 作为系统提示词
   - 解析 `command_generation/generation_plan.txt` 获取任务配置
   - 初始化 DeepSeek 客户端

2. **任务生成**：对每个组合（领域×类型×轮次）：
   - 检查已有数据量，跳过已完成的任务
   - 构建生成指令
   - 发送给 DeepSeek API
   - 提取返回的 JSON 数据
   - 保存到 `output/{领域}/{类型}/{轮次}_round.json`

3. **自动补齐**：如果生成的数据不足目标数量，脚本会：
   - 自动发送补齐请求
   - 在同一会话中继续对话
   - 直到达到目标数量（默认50条）

4. **会话管理**：
   - 每个任务开始时重置会话（只保留 system prompt）
   - 当会话长度接近限制时，自动开启新会话
   - 利用 Context Caching 机制节省 token 费用

### 输出文件结构

```
data/cautious_secretary_raw/
├── Beauty_Hairdressing/
│   ├── constraint_missing/
│   │   ├── 1_round.json
│   │   ├── 2_round.json
│   │   ├── 3_round.json
│   │   ├── 4_round.json
│   │   └── 5_round.json
│   ├── condition_missing/
│   │   └── ...
│   └── ...
├── Education_Learning/
│   └── ...
└── incomplete_tasks.txt        # 未完成任务记录
```

### 断点续传

脚本会自动检查已生成的数据量：
- 如果某个任务已经完成（已有目标数量的数据），会自动跳过
- 如果任务未完成，会继续生成剩余的数据
- 支持随时中断和恢复

## 配置说明

### 客户端配置 (`client/deepseek_client.py`)

客户端相关的配置直接定义在 `client/deepseek_client.py` 文件顶部：

#### API 配置

```python
DEEPSEEK_API_BASE = "https://api.deepseek.com/chat/completions"
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
```

#### Token 限制配置

```python
MAX_TOKENS_OUTPUT_REASONER_MAX = 64000  # reasoner模型最大输出token数
MAX_TOKENS_OUTPUT_STANDARD = 8000       # 标准模型的最大输出token数
MAX_CONTEXT_LENGTH = 110000             # 会话总长度限制
REASONING_TOKENS_BUFFER = 5000          # reasoner模型推理token缓冲
```

#### 模型配置

```python
MODEL_NAME = os.getenv("DEEPSEEK_MODEL", "deepseek-reasoner")
TEMPERATURE = 0.7  # 控制生成随机性
```

**模型选择**：
- `deepseek-chat`: 标准模型，速度快，适合简单任务
- `deepseek-reasoner`: 推理模型，质量高但速度稍慢，适合复杂任务（默认）

### 主程序配置 (`config.py`)

#### 路径配置

```python
PROJECT_ROOT = Path(__file__).parent
INITIAL_PROMPT_FILE = PROJECT_ROOT / "initial_prompt.txt"
OUTPUT_BASE_DIR = PROJECT_ROOT / "data" / "cautious_secretary_raw"
```

#### Token 估算配置

```python
TOKENS_PER_ITEM_BY_ROUND = {
    1: 365,   # 1轮：每条约365 tokens
    2: 344,   # 2轮：每条约344 tokens
    3: 354,   # 3轮：每条约354 tokens
    4: 481,   # 4轮：每条约481 tokens
    5: 425,   # 5轮：每条约425 tokens
}
```

#### 任务配置

```python
TARGET_ITEMS_PER_TASK = 50    # 每个任务的目标数据条数
MAX_RETRIES = 3                # 最多重试次数
RETRY_DELAY = 2                # 重试延迟（秒）
SUCCESS_DELAY = 3              # 成功处理后的延迟（秒）
```

### 环境变量配置

```bash
# 必需：API Key
export DEEPSEEK_API_KEY='your-api-key'

# 可选：模型选择（默认 deepseek-reasoner）
export DEEPSEEK_MODEL='deepseek-reasoner'  # 或 'deepseek-chat'
```

## 代码结构说明

### 模块说明

#### `client/` - 客户端模块

包含不同 API 客户端的实现，当前支持 DeepSeek。

- **`deepseek_client.py`**: DeepSeek API 客户端
  - `DeepSeekClient`: 主要客户端类
  - 功能：API 请求、会话管理、token 估算、错误处理

#### `command_generation/` - 命令生成模块

处理生成计划的解析和指令构建。

- **`parser.py`**: 解析和构建函数
  - `parse_generation_plan()`: 解析生成计划文件
  - `extract_domain_code()`: 提取领域代码
  - `extract_type_code()`: 提取类型代码
  - `extract_round_num()`: 提取轮次数
  - `build_generation_instruction()`: 构建生成指令

- **`generation_plan.txt`**: 生成计划配置文件
  - 定义领域列表（20个）
  - 定义模糊类型列表（8种）
  - 定义对话轮次列表（5种）

#### `utils.py` - 工具函数

提供 JSON 处理、数据统计等功能。

- `extract_json_from_text()`: 从文本中提取 JSON 数组
- `_extract_partial_json_array()`: 处理截断的 JSON 数组
- `count_data_items()`: 统计 JSON 文件中的数据条数
- `save_json_data()`: 保存 JSON 数据到文件

#### `generate_corpus.py` - 主程序

协调各个模块，执行生成任务。

- `generate_single_task()`: 生成单个任务的数据
- `main()`: 主函数，协调整个生成流程

## 优化策略

### 1. Context Caching 机制

- 使用 `system` message 存储固定的 initial prompt
- DeepSeek API 会自动缓存重复的 system prompt
- 大幅节省 token 费用（缓存命中率通常 > 95%）
- 脚本会显示缓存命中率，便于监控

### 2. 智能 Token 管理

- **动态估算**：根据轮次和数据量动态估算输出 token
- **反比例 Buffer**：数据量越少，buffer 比例越高（最高 50%）
- **推理 Token 缓冲**：为 reasoner 模型预留推理 token 空间
- **自动调整**：超过模型限制时自动调整数据量

### 3. 会话管理

- 每个任务开始时重置会话（只保留 system prompt）
- 接近限制时自动开启新会话
- 利用 Context Caching，新会话的 system prompt 会被缓存

### 4. 错误处理和重试

- 自动检测输出截断
- 支持自动重试（最多 3 次）
- 详细的错误日志和调试信息
- 保存调试文件便于问题排查

## 不同轮次的数据量说明

| 轮次 | 每条数据token数 | 50条总token数 | 推荐模型 | 生成策略 |
|------|----------------|--------------|---------|---------|
| 1轮 | ~365 | ~18,250 | deepseek-chat | 可能需要2-3次请求 |
| 2轮 | ~344 | ~17,200 | deepseek-chat | 需要2-3次请求 |
| 3轮 | ~354 | ~17,700 | deepseek-chat | 需要2-3次请求 |
| 4轮 | ~481 | ~24,050 | deepseek-reasoner | 需要2-3次请求 |
| 5轮 | ~425 | ~21,250 | deepseek-reasoner | 需要2-3次请求 |

**注意**：
- 由于 API 限制，无法一次生成 50 条数据
- 脚本会自动分批生成并补齐
- reasoner 模型支持更大的输出（最大 64K tokens）

## 调整建议

### 如果生成质量不够

- 使用 `deepseek-reasoner` 模型（默认已启用）
- 检查 `initial_prompt.txt` 是否清晰明确
- 调整 `TEMPERATURE` 参数（在 `client/deepseek_client.py` 中）

### 如果数据经常被截断

- **这是正常现象**！脚本会自动检测并分批补齐
- 对于 5 轮对话，通常需要 2-3 次请求才能完成 50 条
- 如果频繁截断，检查是否使用了正确的模型

### 如果 Token 消耗过多

- 检查 Context Cache 命中率（脚本会显示）
- 确保 system prompt 固定不变，以触发缓存
- 分批生成是正常的，不会浪费 token

### 如果经常需要开启新会话

- 可以适当提高 `MAX_CONTEXT_LENGTH`（在 `client/deepseek_client.py` 中）
- 但要注意留出足够的 buffer（至少 10K tokens）避免超限
- 对于大数据量场景，开启新会话是正常的

## 故障排查

### API Key 未设置

```
❌ 错误: 未设置DEEPSEEK_API_KEY环境变量
```

**解决**：按照上述步骤设置环境变量

### JSON 解析失败

如果遇到 JSON 解析错误，脚本会：
1. 尝试多种方式提取 JSON（包括处理截断情况）
2. 如果失败，会将原始响应保存到 `{轮次}_round_debug.txt` 文件
3. 保持原有数据量，不会丢失已生成的数据

### 网络错误

脚本会自动重试，如果持续失败，请检查：
1. 网络连接是否稳定
2. API Key 是否有效
3. API 配额是否充足
4. 查看错误日志中的详细提示

### 导入错误

如果遇到模块导入错误：

```bash
# 确保在 corpus_generator 目录下运行
cd corpus_generator
python generate_corpus.py
```

或者使用 Python 模块方式运行：

```bash
python -m corpus_generator.generate_corpus
```

## 示例输出

```
📖 解析生成计划...
✅ 解析完成:
   - 领域: 20个
   - 模糊类型: 8种
   - 对话轮次: 5种
   - 总任务数: 800个

🤖 使用模型: deepseek-reasoner
📊 配置信息:
   - 最大输出tokens: 64000 (reasoner模型)
   - 最大上下文长度: 110000
   - Temperature: 0.7
   - max_tokens将根据预估输出长度动态设置

📝 初始化未完成任务记录文件: output/incomplete_tasks.txt

📊 进度: 1/800
================================================================================
📝 开始生成: 美容美发 (Beauty_Hairdressing) - constraint_missing（约束缺失） - 5轮：用户-助手追问-用户回答-助手追问-用户回答-助手追问-用户回答-助手追问-用户回答-助手总结
================================================================================
✅ 新会话已开启 (system prompt: 6175 tokens)
📊 当前已有 0 条数据，需要生成 50 条
📊 估算输出token数: 30625 tokens
📤 发送生成指令（要求生成50条数据，max_tokens=30625）...
💾 Context Cache命中: 6848/6868 tokens (99.7%)
📊 Token使用: 输入=6868 (缓存命中=6848, 未命中=20), 输出=18432 (推理=5234, 内容=13198), 总计=25300, max_tokens=30625
🔍 提取JSON数据...
✅ 已保存 48 条新数据到 output/Beauty_Hairdressing/constraint_missing/5_round.json (总计: 48 条)
✅ 首次生成: 48 条数据
📊 当前数据量: 48/50，需要补齐 2 条
📊 估算补齐需要约4676 tokens
📤 发送补齐请求（需要2条，max_tokens=4676）...
📊 Token使用: 输入=8920, 输出=4675 (推理=4415, 内容=260), 总计=13595, max_tokens=4676
🔍 提取JSON数据...
✅ 已保存 2 条新数据到 output/Beauty_Hairdressing/constraint_missing/5_round.json (总计: 50 条)
✅ 任务完成！最终数据量: 50/50
⏳ 等待5秒，避免API限流...
✅ 任务 1/800 完成
```

## 注意事项

1. **API 费用**：生成 800 个任务（每个 50 条数据）会产生大量 API 调用，请注意费用
   - 建议先测试小规模任务
   - 利用 Context Caching 可以大幅节省费用

2. **网络稳定性**：确保网络连接稳定
   - 脚本会自动重试，但建议在稳定的网络环境下运行
   - 支持断点续传，可以随时中断和恢复

3. **运行时间**：完整生成所有数据可能需要较长时间
   - 建议在后台运行或使用 `nohup`/`screen`/`tmux` 等工具
   - 可以使用 `nohup python generate_corpus.py > output.log 2>&1 &` 在后台运行

4. **数据验证**：生成完成后，建议检查数据质量
   - 确保 JSON 格式正确
   - 检查数据条数是否符合预期
   - 查看 `incomplete_tasks.txt` 了解未完成的任务

## 扩展开发

### 添加新的客户端

1. 在 `client/` 目录下创建新的客户端文件（如 `openai_client.py`）
2. 实现相同的接口方法
3. 在 `client/__init__.py` 中导出
4. 在新客户端文件中定义相关配置常量

### 自定义生成计划

1. 编辑 `command_generation/generation_plan.txt`
2. 按照现有格式添加新的领域、类型或轮次
3. 脚本会自动解析并生成所有组合

### 修改配置

- **客户端配置**：编辑 `client/deepseek_client.py` 文件顶部的配置常量
- **主程序配置**：编辑 `config.py`
- **环境变量**：通过环境变量覆盖默认配置（如 `DEEPSEEK_API_KEY`、`DEEPSEEK_MODEL`）

## 许可证

本项目采用 [Apache-2.0](LICENSE) 许可证。

## 打赏

如果这个项目对您有帮助，欢迎打赏支持！您的支持是我持续改进的动力。

- **GitHub Sponsors**: [点击支持](https://github.com/sponsors/your-username) （如果已设置）
- **支付宝/微信**: （可以添加二维码或收款码）

**原始仓库地址**: `https://github.com/your-username/corpus_generator` （请替换为实际地址）

## 贡献

欢迎提交 Issue 和 Pull Request！

## 更新日志

### v2.0.0
- ✨ 代码模块化重构
- ✨ 分离客户端配置和主程序配置
- ✨ 添加 `client/` 模块支持多客户端
- ✨ 添加 `command_generation/` 模块
- ✨ 优化错误处理和日志输出

### v1.0.0
- 🎉 初始版本发布
- ✨ 支持 DeepSeek API
- ✨ 自动生成和补齐功能
- ✨ 断点续传支持
