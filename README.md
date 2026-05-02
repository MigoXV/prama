# prama

`prama` 是一个基于 `sclite` 的语音识别评估引擎，用于在 Python 中计算 ASR 结果的 WER（Word Error Rate）和 CER（Character Error Rate），并返回可继续分析的对齐结果、汇总统计和 `sclite` 报告文本。

当前包的定位是轻量评估库：高层 API 面向文本列表评估，底层保留 `ScliteClient` 以便直接调用 `sclite` 对齐能力。

## 功能特性

- 计算 WER 和 CER。
- 支持多条 utterance 批量评估。
- 返回总体统计、分组统计、逐 token 对齐结果和 PRA 文本报告。
- 封装 `libsclite.so`，默认从包内 `src/prama/lib/libsclite.so` 查找动态库。
- 支持通过 `SCLITE_LIB_PATH` 或初始化参数指定自定义 `libsclite.so` 路径。

## 环境要求

- Python `>=3.10, <3.13`
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
