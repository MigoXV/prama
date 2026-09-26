# prama

`prama` 是一个基于 `sclite` 的语音识别评估引擎，用于在 Python 中计算 ASR 结果的 WER（Word Error Rate）和 CER（Character Error Rate），并返回可继续分析的对齐结果、汇总统计和 `sclite` 报告文本。

当前包支持文本列表的 WER/CER 评估和布尔 mask 的 VAD 帧级、段级评估，底层保留 `ScliteClient` 以便直接调用 `sclite` 对齐能力。

## 功能特性

- 计算 WER 和 CER。
- 使用纯 NumPy 计算 VAD 帧级和段级指标，不依赖 SciPy。
- 支持多条 utterance 批量评估。
- 返回总体统计、分组统计、逐 token 对齐结果和 PRA 文本报告。
- 封装 `libsclite.so`，默认从包内 `src/prama/lib/libsclite.so` 查找动态库。
- 支持通过 `SCLITE_LIB_PATH` 或初始化参数指定自定义 `libsclite.so` 路径。

## 环境要求

- Python `>=3.10, <3.13`
- NumPy `>=2.2, <2.3`（随包自动安装）
- Linux 环境
- Poetry

安装依赖：

```bash
poetry install
```

运行测试：

```bash
poetry run pytest
```

## 快速开始

计算 WER：

```python
from prama.evaluator import get_wer

result = get_wer(
    references=["the quick brown fox jumps over the lazy dog"],
    hypotheses=["the quick brown fox jumped over lazy dog"],
    utterance_ids=["sample-a"],
)

print(result.wer)
print(result.summary.substitutions)
print(result.utterances[0].tokens)
```

计算 CER：

```python
from prama.evaluator import get_cer

result = get_cer(
    references=["你好世界"],
    hypotheses=["你好世"],
)

print(result.cer)
print(result.summary.deletions)
```

复用评估器：

```python
from prama.evaluator import Evaluator

with Evaluator() as evaluator:
    wer_result = evaluator.get_wer(["hello world"], ["hello word"])
    cer_result = evaluator.get_cer(["hello"], ["hallo"])

print(wer_result.wer)
print(cer_result.cer)
```

## VAD 帧级与段级评估

```python
import numpy as np
from prama.evaluator import VadEvaluator, evaluate_masks
from prama.models import VadEvaluationResult

reference = np.array([False, True, True, True, False, True, True, False])
prediction = np.array([False, True, True, False, False, True, True, False])

result = evaluate_masks(reference, prediction, hit_threshold=0.9)
# 复用相同阈值也可通过类接口调用。
assert VadEvaluator(hit_threshold=0.9).evaluate(reference, prediction) == result
print(result.segment_hit_count, result.segment_miss_count)
print(result.segment_precision, result.segment_recall, result.segment_f1)
print(result.frame_accuracy, result.frame_precision, result.frame_recall)
```

`VadEvaluationResult` 是不可变数据类，包含帧级 TP/TN/FP/FN、accuracy、
precision、recall、F1、specificity、balanced accuracy、误报率、漏检率，
以及参考/预测段数、段命中/漏检/误报数和对应比率。
**VAD 比率在 0–1 范围内，区别于 WER/CER 的百分数。**

输入需为长度相同的布尔 mask；支持只读数组、非连续视图，以及去掉单维度后为
一维的形状。不修改输入，也不保留共享计算状态，可在线程池中并发调用。
为了和原 prama-server 实现严格对齐，空 mask、squeeze 后变为标量的单元素 mask、
非布尔 dtype、形状不一致及不在 `[0, 1]` 的阈值都会报错。

连续 True 区间视为语音段，采用左闭右开边界。参考段命中要求某一个预测段与它的
交集长度除以参考段长度达到 `hit_threshold`，不会把多个预测段的覆盖率相加。
预测段与任一参考段有正重叠就不算误报，不要求一对一匹配；端点相接不算重叠。
阈值为 0 时延续原行为：只要预测段非空，每个参考段均算命中，即使不重叠。
没有参考段时 recall 为 0，没有预测段时 precision 为 0。

实现采用 NumPy 边界检测、`searchsorted` 和只枚举实际重叠候选的归约，
避免分配参考段数 × 预测段数的矩阵。正式实现复用已计算的命中数。
之前的 C 对照仅保留在实验目录；正式 VAD 路径使用纯 NumPy。

运行回归测试：

```bash
poetry run pytest -q tests/test_vad
```

## 高层 API

### `get_wer`

```python
get_wer(
    references: list[str],
    hypotheses: list[str],
    utterance_ids: list[str] | None = None,
) -> WerResult
```

### `get_cer`

```python
get_cer(
    references: list[str],
    hypotheses: list[str],
    utterance_ids: list[str] | None = None,
) -> WerResult
```

参数说明：

- `references`：参考文本列表。
- `hypotheses`：识别结果文本列表。
- `utterance_ids`：可选的 utterance ID 列表。未传入时自动生成 `utt0001`、`utt0002` 等 ID。

输入约束：

- `references`、`hypotheses` 和 `utterance_ids` 必须是 `list[str]`。
- `references` 和 `hypotheses` 允许长度不一致，缺失的一侧会按空文本参与评估。
- `utterance_ids` 如果传入，长度必须等于实际评估对数。
- `utterance_ids` 不能包含空字符串、括号或换行符。

## 返回结果

`get_wer` 和 `get_cer` 返回 `WerResult`：

```python
@dataclass(frozen=True, slots=True)
class WerResult:
    summary: ScliteCounts
    groups: list[ScliteGroup]
    utterances: list[WerUtterance]
    report: str
    metric: str
```

常用字段：

- `result.wer`：WER 数值。
- `result.cer`：CER 数值。CER 复用 `sclite` 的错误率字段。
- `result.accuracy`：准确率。
- `result.summary`：总体统计，包含 `correct`、`substitutions`、`deletions`、`insertions` 等字段。
- `result.groups`：`sclite` 分组统计。
- `result.utterances`：逐 utterance 的 token 对齐结果。
- `result.report`：`sclite` 生成的 PRA 文本报告。

## 底层 sclite 封装

如果需要直接评估 TRN、STM、CTM 等格式文件，可以使用 `ScliteClient`：

```python
from prama.sclite import Format, IdType, ScliteClient, ScliteOptions

with ScliteClient() as client:
    with client.align_files(
        "ref.trn",
        "hyp.trn",
        ref_format=Format.TRN,
        hyp_format=Format.TRN,
        options=ScliteOptions(id_type=IdType.SP),
    ) as result:
        print(result.summary().wer)
        print(result.report_text())
```

动态库查找顺序：

1. `ScliteClient(lib_path=...)` 显式传入的路径。
2. 环境变量 `SCLITE_LIB_PATH`。
3. 包内 `prama/lib/libsclite.so`。
4. 系统库搜索结果。

## 开发说明

本项目使用 Poetry 管理依赖和命令：

```bash
poetry install
poetry run pytest
```

测试用例位于 `tests/test_sclite`，覆盖高层评估 API 和底层 `sclite` wrapper。

## 从源码构建与安装产物

C 源码随项目维护，不需要旧版本的 `libsclite.so`。构建环境需要 Linux、C11 编译器、系统 C 开发头文件、Python 和 Poetry：

```bash
poetry install
poetry run python build_native.py  # 开发环境编译
poetry build                      # 生成 sdist，并重新编译 C 库生成 wheel
```

`dist/` 中的 wheel 包含 Python 代码和原生动态库，安装后可以直接使用，运行时不需要编译器，也不会从其他项目复制动态库：

```bash
# 将下面的文件名替换为实际生成的 wheel 文件名
poetry add ./dist/prama-0.1.0a1-cp310-cp310-linux_x86_64.whl
```

wheel 对应构建时的 Python、Linux 架构和系统运行库，不能跨操作系统使用。需要其他 Python 版本或系统环境时，从 sdist 在目标环境运行 `poetry build`。源码包包含完整原生源码和构建脚本。

## 逐条读取评测结果

```python
from prama.evaluator import iter_wer

with iter_wer(
    ["hello world", "speech recognition"],
    ["hello word", "speech recognition now"],
) as stream:
    for record in stream:
        print(record.sequence, record.utterance.id)
        print(record.utterance.tokens)
        print(record.counts.wer, record.cumulative.wer)
    result = stream.result()

print(result.report)
```

- `iter_cer` 用法相同；复用评估器时调用 `Evaluator.iter_wer` / `iter_cer`。
- 底层使用 `ScliteClient.iter_align_texts` / `iter_align_files`，参数与批量方法一致。事件额外提供时间、文件、channel、标签及完整 token 元数据。
- 每条记录在原生对齐和元数据补齐后交付，按原生处理顺序输出；最终结果保持原有分组顺序。
- 输入仍是完整文本或文本列表；流式能力针对结果输出，不改变原版分段或对齐算法。
- 生产线程通过容量为 16 的队列交付结果，慢消费者会产生背压。最终结果保留所有对齐信息，内存仍随结果规模增长。
- 提前 `break` 时使用 `with`，或显式 `close()`。关闭会请求取消并等待生产线程释放资源；单条记录的原生计算完成后才能响应记录边界上的取消。
- `result()` 必须在迭代结束后调用。底层 `ScliteResult` 随流关闭；已交付事件和高层 `WerResult` 是独立 Python 数据，关闭后仍可读取。
- 后台错误在迭代时抛出，已交付记录不失效，失败或取消的任务不返回完整最终结果。

## 多线程使用

新库的原生可变状态采用线程局部存储，包括编码、动态规划缓存、报告缓存、回调和错误恢复状态。不同线程可同时进行批量计算、流式计算和报告生成；一个流暂停或取消不会阻塞其他任务，不需要多进程。

```python
from concurrent.futures import ThreadPoolExecutor
from prama.evaluator import get_wer

with ThreadPoolExecutor(max_workers=8) as pool:
    results = list(pool.map(
        lambda pair: get_wer([pair[0]], [pair[1]]),
        [("hello world", "hello word"), ("a b", "a b c")],
    ))
```

共享同一个 `Evaluator` / `ScliteClient` 的批量调用也支持多线程使用，同一 client 的入口调用由锁保护。需要原生计算同时执行时，每个线程使用自己的 client，或使用模块级函数。多个流分别持有自己的原生上下文，可以同时运行。

单个流使用一个消费者线程；允许从其他线程调用 `close()` 取消它。结果对象的方法和关闭操作有锁保护。直接调用 C ABI 时，同一个 context/result 句柄须由调用者同步；不得从原生回调中递归发起对齐或报告生成。

旧版本 `.so` 仍可用于批量接口兼容性验证；它不提供新增流式接口，也不保证上述原生线程隔离能力。

## 格式、选项与错误处理

当前构建启用 TRN/TRN、STM/CTM 和 CTM/CTM，支持字符对齐、大小写、可选删除、片段匹配、时间对齐、分段裁剪、词权重和两种分词推断算法。`infer_word_seg` 为 `0`、`1` 或 `2`，分别表示关闭、algo1、algo2。

与基准构建一致，GNU diff 与 SLM 未启用：STM/TXT 和语言模型选项会明确报错。互不兼容的格式和选项不会被静默忽略。数据解析失败转换为 `ScliteError`，不会由 C 的 `exit()` 终止 Python 进程。

`wer` 和 `accuracy` 使用百分数；为兼容已有接口，`accuracy = 100 - wer`。参考词数为零时沿用 sclite 的 `wer = 0` 约定。

## 可复现验证

```bash
# 从未修改的 SCTK 工作副本构建权威基准
poetry run python scripts/build_reference.py
poetry run pytest

# 固定种子的 10,000 对数据，同时验证 WER 与 CER
poetry run python scripts/check_alignment.py \
  --cli build/original/sclite/sclite --count 10000

# 实际 poetry build、独立安装 wheel、从 sdist 重建并重复测试
poetry run python scripts/verify_distribution.py
```

分发验收会在仓库之外创建两个独立 Poetry 环境，清除源码路径和动态库路径覆盖，确认实际加载安装目录中的 Python 包与 `.so`，并在两套产物上分别运行测试和 10,000 对数据对照。日志与 SHA-256 写入 `outputs/distribution/`。

原生内存和线程检查使用 `scripts/native_stress.c`、`scripts/native_threads.c`，覆盖正常返回、报告、错误、取消、并发回调及跨线程释放。ASan/UBSan/LSan、Valgrind Memcheck 和 Helgrind 的日志保存到 `outputs/`。报告比较仅规范化文件路径和生成日期；计分、token 和报告正文与原版对齐。

旧 `.so` 的一个已确认差异：连续调用时 SGML 的 `sequence` 序号会跨任务累加。新库每次任务从零开始，与每次独立执行原版 `sclite` 一致。对照脚本会单独记录此差异，不会通过忽略 token、计数或报告正文来掩盖算法差异。
